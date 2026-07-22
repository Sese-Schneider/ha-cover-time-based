"""Cover that wraps an existing cover entity."""

import logging
import time

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_CURRENT_TILT_POSITION,
    ATTR_TILT_POSITION,
    CoverEntityFeature,
)
from homeassistant.const import (
    ATTR_SUPPORTED_FEATURES,
    SERVICE_OPEN_COVER,
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_OPEN,
    STATE_OPENING,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.helpers.event import async_track_state_change_event

from .cover_base import CoverTimeBased
from .drivers import (
    NativePositionDriver,
    NativeTiltDriver,
    PositionDriver,
    TimedPositionDriver,
)
from .tilt_strategies.inline import InlineTilt

_LOGGER = logging.getLogger(__name__)

_MOVING_STATES = {STATE_OPENING, STATE_CLOSING}
_STOPPED_STATES = {STATE_OPEN, STATE_CLOSED}
# The states a command-echo cover reports as a travel command (its `unknown`
# is the stop command, and is deliberately not one of these).
_COMMANDED_STATES = _MOVING_STATES | _STOPPED_STATES

# After we issue a command to the wrapped cover, ignore external state
# changes for this many seconds. Some wrapped covers (e.g. Tuya TS130F on
# ZHA) briefly bounce back to their pre-command state before settling on
# the destination state — within this window we trust our own time-based
# position calculation rather than the wrapped cover's transient state.
# Observed bounces happen <250 ms after the command; 500 ms gives a 2×
# safety margin without interfering with legitimate later state changes.
_BOUNCE_GRACE_PERIOD = 0.5


class WrappedCoverTimeBased(CoverTimeBased):
    """A cover that delegates open/close/stop to an underlying cover entity."""

    def __init__(
        self,
        cover_entity_id,
        ignore_reported_position=False,
        force_time_based_position=False,
        reports_command_not_endpoint=False,
        invert=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._cover_entity_id = cover_entity_id
        self._ignore_reported_position = ignore_reported_position
        self._force_time_based_position = force_time_based_position
        self._reports_command_not_endpoint = reports_command_not_endpoint
        self._invert = invert
        self._last_self_command_time: float | None = None
        # Set while a command-echo cover is mid-reconnect, so the retained
        # state landing after the stop hop is not replayed as a command
        # (see _is_stale_reappearance).
        self._returning_from_unavailable = False
        self._native_position_driver = NativePositionDriver(self)
        self._timed_position_driver = TimedPositionDriver(self)
        self._native_tilt_driver = NativeTiltDriver(self)

    def _invert_position(self, x: int) -> int:
        """Translate a position between our frame and the underlying's.

        An involution (100 - x), so the same call serves both directions.
        A no-op when invert is off (issue #160).
        """
        return 100 - x if self._invert else x

    async def async_added_to_hass(self):
        """Register state listener for the wrapped cover entity."""
        await super().async_added_to_hass()
        if self._cover_entity_id:
            self._state_listener_unsubs.append(
                async_track_state_change_event(
                    self.hass,
                    [self._cover_entity_id],
                    self._async_switch_state_changed,
                )
            )

        # The cover may have been moved (app/remote) while HA was down; the
        # store's snapshot is then stale and the first timed move would run
        # the wrong distance in possibly the wrong direction. Trust a live
        # reported position over the stored one at startup.
        live = self._wrapped_reported_position(trust_closed=False)
        if live is not None and live != self.travel_calc.current_position():
            self._log(
                "async_added_to_hass :: syncing to underlying's live position %d",
                live,
            )
            self.travel_calc.set_position(live)
            # Persist the correction, not just the in-memory tracker: without
            # this, a second restart with the underlying unavailable (or
            # otherwise unable to report) would restore the now-stale stored
            # snapshot all over again instead of the corrected live value.
            await self._async_persist_position()

    def _are_entities_configured(self) -> bool:
        """Return True if the wrapped cover entity is configured."""
        return bool(self._cover_entity_id)

    def _target_entity_ids(self) -> list[str]:
        """Wrapped mode drives the wrapped cover entity."""
        ids = super()._target_entity_ids()
        if self._cover_entity_id:
            ids.append(self._cover_entity_id)
        return ids

    def _movement_target(self, closing: bool) -> str | None:
        """Wrapped mode drives the wrapped cover entity for all travel."""
        return self._cover_entity_id

    def _tilt_movement_target(self, command: str) -> str | None:
        """Wrapped mode drives the wrapped cover entity for all tilt."""
        return self._cover_entity_id

    def _wrapped_features(self) -> int | None:
        """Return the wrapped entity's supported_features bitmask, or None.

        None means "unknown" — the entity is missing, unavailable, or reports
        no integer feature bitmask. Mirrors _wrapped_supports_tilt's treatment
        of an offline entity as "don't assume capabilities".
        """
        state = self.hass.states.get(self._cover_entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        features = state.attributes.get(ATTR_SUPPORTED_FEATURES)
        if not isinstance(features, int):
            return None
        return features

    def _wrapped_supports_set_position(self) -> bool:
        """Return True if the wrapped cover advertises native SET_POSITION."""
        features = self._wrapped_features()
        return features is not None and bool(features & CoverEntityFeature.SET_POSITION)

    def _wrapped_supports_stop(self) -> bool:
        """Return True if the wrapped cover advertises native STOP."""
        features = self._wrapped_features()
        return features is not None and bool(features & CoverEntityFeature.STOP)

    def _wrapped_supports_set_tilt_position(self) -> bool:
        """Return True if the wrapped cover advertises native SET_TILT_POSITION."""
        features = self._wrapped_features()
        return features is not None and bool(
            features & CoverEntityFeature.SET_TILT_POSITION
        )

    def _use_native_tilt(self) -> bool:
        """Return True if tilt commands should be forwarded to the wrapped
        cover's own tilt instead of simulated with the main motor.

        Restricted to InlineTilt: the device positions its own slats, so the
        inline strategy's no-op snap_trackers_to_physical leaves our
        natively-set tilt intact. Dual-motor/sequential strategies re-derive
        tilt from travel and keep the timed path. Command-echo covers report
        nothing trustworthy to snap back from, so they keep the timed path too.
        """
        if self._reports_command_not_endpoint:
            return False
        if not self._has_tilt_support():
            return False
        if not isinstance(self._tilt_strategy, InlineTilt):
            return False
        return self._wrapped_supports_set_tilt_position()

    async def _plan_tilt_for_travel(self, target, command, current_pos, current_tilt):
        """Sweep the tilt DISPLAY to the direction endpoint during native travel.

        The wrapped device positions its own slats, so we drive no physical
        tilt. But the slats visibly track travel on a venetian (close going
        down, open going up), so animate tilt_calc to that endpoint for display;
        the base feeds this coupled target to tilt_calc.start_travel(). No
        restore is scheduled — the device owns the final angle, and the
        settle-snap syncs tilt to the reported value once travel completes.
        Non-native covers keep the base coupling (physical, main-motor).
        """
        if self._use_native_tilt():
            self._tilt_restore_target = None
            if current_pos is None or current_tilt is None:
                return None, 0.0, False
            tilt_endpoint = 0 if target < current_pos else 100
            return tilt_endpoint, 0.0, False
        return await super()._plan_tilt_for_travel(
            target, command, current_pos, current_tilt
        )

    def _use_native_set_position(self) -> bool:
        """Return True if set_cover_position should be forwarded natively.

        Auto-detected from the wrapped entity's SET_POSITION support, with three
        opt-outs:
          - the force_time_based_position override (always legacy tracking),
          - reports_command_not_endpoint (the wrapped entity's state/position is
            a command echo, so it's tracked purely by time — never forward a
            native position to it; this also keeps the command-echo
            reinterpretation in _handle_external_state_change from ever racing a
            self-driven native move), and
          - a configured *timed* tilt strategy: native forwarding drives travel
            only and can't express the tilt coupling/pre-steps the time-based
            path plans, so a *timed* tilt strategy keeps the timed path
            (dual-motor/sequential, and inline covers whose wrapped entity
            can't forward tilt); native-tilt covers drive position natively
            too. A native-tilt cover (_use_native_tilt()) already owns its
            slats independently of our travel motor, so driving position
            natively is coupling-safe there.
        """
        if self._force_time_based_position:
            return False
        if self._reports_command_not_endpoint:
            return False
        # A configured tilt strategy normally keeps the timed path so the
        # tilt coupling/pre-steps can run. But when tilt is itself forwarded
        # natively (_use_native_tilt) the wrapped device owns its slats, so
        # driving position natively is coupling-safe and gives device-accurate
        # positioning. Dual-motor/sequential (timed tilt) keep the timed path.
        if self._tilt_strategy is not None and not self._use_native_tilt():
            return False
        return self._wrapped_supports_set_position()

    def _position_driver(self) -> PositionDriver:
        """Select the position actuation driver from current capabilities.

        Re-evaluated per call: the wrapped entity's supported_features can
        change at runtime (e.g. it goes unavailable and back).
        """
        if self._use_native_set_position():
            return self._native_position_driver
        return self._timed_position_driver

    def _motor_stops_itself(self) -> bool:
        """The device holds the target itself — the auto-updater must not send
        a relay stop.

        True during a native tilt move (the wrapped cover positions its own
        slats), and for native set_position covers (Plan 1). Timed covers on
        either axis must be told to stop, so False otherwise.
        """
        if self._moving_tilt and self._use_native_tilt():
            return True
        return self._position_driver().holds_itself

    def _self_stops_at_endpoints(self) -> bool:
        """Command-echo wrapped covers have no endstop and must be stopped.

        A wrapped cover whose state is a command echo
        (``reports_command_not_endpoint``) reports no real endpoint and, in
        practice, drives an endstop-less motor that merely stalls against the
        mechanical stop while powered. The base assumption that the motor
        self-stops at its limit does not hold, so return False: the endpoint
        stop must be sent to de-energize the motor rather than let it stall
        until the device's own max-time cutoff (issue #152).

        A normal wrapped cover (real position/endpoint feedback) keeps the base
        default of True — its underlying motor stops at its own limits, so the
        endpoint stop stays redundant and is skipped.
        """
        if self._reports_command_not_endpoint:
            return False
        return super()._self_stops_at_endpoints()

    def _skip_open_resync_at_endpoint(self) -> bool:
        """A command-echo wrapped cover treats open-at-100 as a no-op.

        With no endpoint feedback and an endstop-less motor, re-commanding open
        while already settled at 100% is a pointless relay pulse that
        re-energizes (and stalls) the motor — so skip the resync, mirroring
        async_close_cover's skip-at-0 (issue #152). A plain wrapped cover keeps
        the base resync behaviour.
        """
        return self._reports_command_not_endpoint

    def _start_bounce_grace_window(self) -> None:
        self._last_self_command_time = time.monotonic()

    def _in_bounce_grace_window(self) -> bool:
        if self._last_self_command_time is None:
            return False
        return time.monotonic() - self._last_self_command_time < _BOUNCE_GRACE_PERIOD

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle state changes on the wrapped cover entity.

        Mirrors the inner cover's state transitions — start, stop, and
        direction changes. When the wrapped cover settles into a stopped
        state we snap to its reported position; for covers without a
        current_position attribute we fall back to stopping the tracker.
        On settle we also snap tilt to the wrapped cover's reported tilt
        (native-tilt covers only, via _maybe_snap_to_reported_tilt).
        When self._invert is set, the underlying's opening/closing are
        interpreted as our close/open (swapped).
        """
        if self._in_bounce_grace_window():
            self._log(
                "_handle_external_state_change :: ignoring %s -> %s"
                " within bounce grace window",
                old_val,
                new_val,
            )
            return

        # Command-echo covers report no position and never settle to a snap
        # target: every reported state is a command. Short-circuit here, before
        # the endpoint and native-set-position logic below — neither applies to
        # them (they have no set_position, so the native-move guard is a no-op
        # for them anyway, and we never snap).
        if self._reports_command_not_endpoint:
            await self._handle_command_state(new_val)
            return

        # While we animate a native set_position move, the wrapped cover's own
        # opening/closing state is a side effect of the command we forwarded —
        # not an external open/close. Don't let it hijack the move into a full
        # travel. The settle (stopped) state below is still honored so we snap
        # to the wrapped cover's reported position when it arrives.
        if (
            new_val in _MOVING_STATES
            and self._use_native_set_position()
            and self.travel_calc.is_traveling()
        ):
            self._log(
                "_handle_external_state_change :: ignoring self-driven %s"
                " during native set_position move",
                new_val,
            )
            return

        # Same for a self-driven native tilt move: the wrapped cover's own
        # opening/closing while its slats run is a side effect of the tilt we
        # forwarded, not an external travel. tilt_calc is traveling for the
        # duration of our animation; mirror the native set_position guard above.
        if (
            new_val in _MOVING_STATES
            and self._use_native_tilt()
            and self.tilt_calc.is_traveling()
        ):
            self._log(
                "_handle_external_state_change :: ignoring self-driven %s"
                " during native tilt move",
                new_val,
            )
            return

        # Timed-path counterpart of the native-move guard above. A time-based
        # wrapped cover (Force time-based, or one lacking native set_position)
        # reaches a partial target by forwarding open_cover/close_cover; the
        # wrapped cover then reports its own opening/closing as a side effect of
        # that command. If that report lands after the bounce grace window --
        # e.g. a template cover driven by a physical binary sensor that lags the
        # relay by >0.5s (issue #165) -- it must not be reinterpreted as a fresh
        # external full open/close that hijacks our in-flight partial move. Only
        # the same-direction echo of our own self-initiated move is suppressed;
        # an opposite-direction report is a genuine external reversal (e.g. the
        # wall switch pressed the other way) and still falls through below.
        #
        # The echo can also land *before* travel_calc starts, inside the
        # travel_startup_delay window: guarding only on is_traveling() there let
        # it slip through to async_open/close_cover -> _async_move_to_endpoint,
        # which flipped _self_initiated_movement to False and dropped the auto-
        # stop -> runaway to endpoint. So the guard covers the startup-delay
        # window too, using the command we just issued for direction (the
        # tracker's is unset until it starts traveling).
        in_startup_window = (
            self._startup_delay_task is not None and not self._startup_delay_task.done()
        )
        if (
            new_val in _MOVING_STATES
            and self._self_initiated_movement
            and (self.travel_calc.is_traveling() or in_startup_window)
        ):
            echo_is_open = (new_val == STATE_OPENING) != self._invert
            if in_startup_window and not self.travel_calc.is_traveling():
                # Tracker not started yet, so its direction is unset — compare
                # the echo against the command we just issued instead.
                cmd_is_open = self._last_command == SERVICE_OPEN_COVER
                if cmd_is_open == echo_is_open:
                    self._log(
                        "_handle_external_state_change :: ignoring self-driven %s"
                        " during startup delay",
                        new_val,
                    )
                    return
            # While traveling, is_opening() is the exact complement of
            # is_closing(), so comparing it to the echo's direction (both in our
            # frame) tells same- from opposite-direction directly.
            elif self.travel_calc.is_opening() == echo_is_open:
                self._log(
                    "_handle_external_state_change :: ignoring self-driven %s"
                    " during timed move",
                    new_val,
                )
                return

        if new_val == STATE_OPENING:
            self._log("_handle_external_state_change :: wrapped cover opening")
            if self._invert:
                await self.async_close_cover()
            else:
                await self.async_open_cover()
        elif new_val == STATE_CLOSING:
            self._log("_handle_external_state_change :: wrapped cover closing")
            if self._invert:
                await self.async_open_cover()
            else:
                await self.async_close_cover()
        elif new_val in _STOPPED_STATES:
            # A cover that has just come back online is announcing whatever its
            # integration starts up in, which for one with no position feedback
            # is a plain `closed` — not a report that it is at the 0% endpoint
            # (100%, when inverted). Trust a position it actually reports; keep
            # the position we tracked before it dropped out otherwise (#160).
            came_back = self._came_back_online(old_val)
            target = self._wrapped_reported_position(trust_closed=not came_back)
            if target is not None:
                await self._snap_to_position(target)
            elif came_back:
                # Deliberately not async_stop_cover: a travel still running
                # when the entity dropped out keeps running here. Its motor
                # never stopped — an integration reload is not a stop — so the
                # time-based estimate remains the best guess, where snapping
                # to an endpoint we don't believe would be a worse one.
                self._log(
                    "_handle_external_state_change :: wrapped cover came back"
                    " reporting no position, keeping the tracked position"
                )
            elif old_val in _MOVING_STATES:
                self._log(
                    "_handle_external_state_change :: wrapped cover stopped,"
                    " no position info"
                )
                await self.async_stop_cover(supersede=False)
            await self._maybe_snap_to_reported_tilt()

    async def _handle_command_state(self, new_val: str) -> None:
        """Reinterpret the wrapped entity's state as a command echo.

        Some covers (e.g. single-DP Tuya shutters, issue #137) report no
        position and no opening/closing transition — their state mirrors the
        last command (open/close/stop) rather than a real endpoint. With this
        opt-in, map each reported state straight to a time-based command and
        never snap to an endpoint. A genuine command-echo device never reports
        opening/closing; if one ever does, it is treated as the matching
        open/close command — a harmless same-direction continuation. The
        async_* paths run with _triggered_externally set (the dispatcher sets
        it before calling us), so they update the tracker without bouncing a
        command back to the wrapped cover. When self._invert is set, an open
        echo drives our close and a close echo drives our open (swapped);
        the stop echo is unchanged.
        """
        if new_val in (STATE_OPEN, STATE_OPENING):
            if self._invert:
                self._log("_handle_command_state :: open echo → close (inverted)")
                await self.async_close_cover()
            else:
                self._log("_handle_command_state :: open command")
                await self.async_open_cover()
        elif new_val in (STATE_CLOSED, STATE_CLOSING):
            if self._invert:
                self._log("_handle_command_state :: close echo → open (inverted)")
                await self.async_open_cover()
            else:
                self._log("_handle_command_state :: close command")
                await self.async_close_cover()
        elif new_val == STATE_UNKNOWN:
            self._log("_handle_command_state :: stop command")
            await self.async_stop_cover(supersede=False)
        else:
            # STATE_UNAVAILABLE / anything else: not a command, ignore.
            self._log("_handle_command_state :: ignoring non-command state %s", new_val)

    async def _handle_external_attribute_change(self, event):
        """Handle attribute-only updates on the wrapped cover.

        When the wrapped cover is in a stopped state and its
        current_position attribute changes, trust the new position.
        Mid-travel attribute updates (state opening/closing) are ignored
        because their values may be stale or live depending on the device.

        While a self-initiated timed move is in flight, reports are ignored
        outright rather than checked for opening/closing: an underlying that
        reports current_position but never opening/closing (e.g. an MQTT
        position-topic-only cover) always looks "stopped" to that check, so
        its mid-travel reports would otherwise snap the tracker and cancel
        the pending auto-stop (see the is_traveling guard below). Native
        (holds_itself) moves are unaffected and keep snapping.

        Command-echo covers (reports_command_not_endpoint) report no
        trustworthy position or endpoint, so we ignore their attribute-only
        updates entirely — mirroring the short-circuit in
        _handle_external_state_change. Without this, an attribute update while
        the device sits in 'closed' would snap us to 0% via the
        state==closed -> 0 shortcut, the very snap this option exists to avoid.
        After handling position, we also snap tilt to the wrapped cover's
        reported tilt (native-tilt covers only, via
        _maybe_snap_to_reported_tilt).
        """
        if event.data.get("entity_id") != self._cover_entity_id:
            return
        if self._reports_command_not_endpoint:
            return
        if self._in_bounce_grace_window():
            return
        # A self-initiated TIMED move in flight: the pending auto-stop is the
        # only thing that will halt the underlying, and _snap_to_position would
        # kill it (set_known_position -> _handle_stop -> stop_auto_updater).
        # Underlyings that report positions without ever reporting
        # opening/closing (e.g. MQTT position-topic-only) hit this mid-travel;
        # their report describes a lagging past, not a settled present. Native
        # moves keep snapping — the device holds itself.
        if (
            self.travel_calc.is_traveling()
            and self._self_initiated_movement
            and not self._position_driver().holds_itself
        ):
            self._log(
                "_handle_external_attribute_change :: ignoring mid-timed-move"
                " position report"
            )
            return
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state not in _STOPPED_STATES:
            return
        # Only the reported position, never the closed-state fallback: an
        # attribute touch that carries no position says nothing new about
        # endpoints (the transition *into* closed already snapped, above), and
        # trusting it here would re-open issue #160 through the side door —
        # a reappearance whose bare `closed` we just refused snaps anyway on
        # whatever attribute the entity settles next.
        target = self._wrapped_reported_position(trust_closed=False)
        if target is not None:
            await self._snap_to_position(target)
        await self._maybe_snap_to_reported_tilt()

    async def _snap_to_position(self, target: int) -> None:
        """Snap our tracker to a known position.

        Always goes through set_known_position so that a still-running
        auto-updater is stopped even when our calculated position happens
        to match the target at this instant.
        """
        self._log("_snap_to_position :: snapping to %d", target)
        # The device reporting where it ended up, not a command — it must not
        # cancel a reversal waiting out its settle gap.
        await self.set_known_position(position=target, supersede=False)
        self._last_command = None

    def _is_stale_reappearance(self, old_val, new_val) -> bool:
        """A command-echo cover coming back online is not issuing a command.

        With ``reports_command_not_endpoint`` the wrapped entity's state *is*
        the last command it was given, so the open/closed it carries on the way
        back is that retained value resurfacing rather than something anyone
        just asked for. Replaying it would run a phantom timed travel — a full
        open, when the cover is also inverted (issue #160).

        ``unknown`` is this mode's *stop* command, so it can't be read as
        evidence of having been away and is let through: it freezes the tracker
        (and any auto-updater still running) rather than moving it. But a
        reconnect commonly lands in two hops — ``unavailable -> unknown ->
        <retained value>`` — as the entity becomes available before its first
        message arrives, so the veto has to survive the intervening stop.
        _returning_from_unavailable carries it across; without that, the
        retained value in the second hop is replayed as a command. It is only
        ever set by an ``unavailable ->`` transition, so an ordinary
        stop-then-close (``unknown -> closed``, a real command pair) is
        untouched.

        Covers we read endpoints from are guarded in the handler instead — a
        returning entity may still carry a trustworthy position, and vetoing
        the whole transition here would throw that away along with the
        opening/closing and tilt handling it also drives.
        """
        if not self._reports_command_not_endpoint:
            return False
        if old_val == STATE_UNAVAILABLE:
            self._returning_from_unavailable = new_val == STATE_UNKNOWN
            return new_val in _COMMANDED_STATES
        still_returning = self._returning_from_unavailable and old_val == STATE_UNKNOWN
        self._returning_from_unavailable = False
        return still_returning and new_val in _COMMANDED_STATES

    def _wrapped_reported_position(self, *, trust_closed: bool = True) -> int | None:
        """Return the wrapped cover's reported position, or None if unknown.

        Prefers the current_position attribute. Falls back to 0 for
        state=closed (unambiguous); state=open without an attribute is
        ambiguous (could be any position > 0) and returns None. Both the
        attribute and the closed fallback are translated through
        _invert_position, so when self._invert is set the reported value is
        100 - position and the closed fallback becomes 100.

        ``trust_closed=False`` drops that fallback, for a caller holding a
        state it does not consider a real endpoint report (see the reappearance
        handling in _handle_external_state_change).
        """
        state = self.hass.states.get(self._cover_entity_id)
        if state is None:
            return None
        # When configured to ignore the reported position, behave like a cover
        # that reports no position at all: track purely by time. The closed
        # state below is still trusted — it is an unambiguous endpoint, not a
        # reported position number.
        if not self._ignore_reported_position:
            attr_pos = state.attributes.get(ATTR_CURRENT_POSITION)
            if isinstance(attr_pos, (int, float)) and 0 <= attr_pos <= 100:
                return self._invert_position(int(attr_pos))
        if trust_closed and state.state == STATE_CLOSED:
            return self._invert_position(0)
        return None

    def _wrapped_reported_tilt_position(self) -> int | None:
        """Return the wrapped cover's reported tilt position, or None.

        Honors ignore_reported_position — a device whose reported values are
        untrustworthy is untrustworthy on both axes. Unlike
        _wrapped_reported_position there is no closed-state fallback: a closed
        cover implies nothing unambiguous about its slat angle.
        """
        if self._ignore_reported_position:
            return None
        state = self.hass.states.get(self._cover_entity_id)
        if state is None:
            return None
        attr_tilt = state.attributes.get(ATTR_CURRENT_TILT_POSITION)
        if isinstance(attr_tilt, (int, float)) and 0 <= attr_tilt <= 100:
            return int(attr_tilt)
        return None

    async def _maybe_snap_to_reported_tilt(self) -> None:
        """Snap tilt_calc to the wrapped cover's reported tilt once it settles.

        Gated on _use_native_tilt(): only covers whose tilt we forward natively
        treat the reported tilt as source of truth. For dual-motor/sequential
        the coupling model owns the tilt tracker, so we must not clobber it.
        Skipped while our own tilt animation is still in flight.
        """
        if not self._use_native_tilt():
            return
        if self.tilt_calc.is_traveling():
            return
        target = self._wrapped_reported_tilt_position()
        if target is None or self.tilt_calc.current_position() == target:
            return
        self._log("_maybe_snap_to_reported_tilt :: snapping tilt to %d", target)
        await self.set_known_tilt_position(tilt_position=target)

    async def _command_position_move(self, target, command, already_moving_same_dir):
        """Drive a mid-position move via the selected position driver.

        Native covers forward set_cover_position and hold themselves; timed
        covers run the base relay drive (latched open/close + timed stop).
        """
        await self._position_driver().command_move(
            target, command, already_moving_same_dir
        )

    async def _call_set_cover_position(self, position: int) -> None:
        """Forward a set_cover_position command to the wrapped entity.

        The forwarded value is translated to the underlying's frame
        (100 - position when inverted); the caller works in user frame.
        """
        self._start_bounce_grace_window()
        await self.hass.services.async_call(
            "cover",
            "set_cover_position",
            {
                "entity_id": self._cover_entity_id,
                "position": self._invert_position(position),
            },
            False,
        )

    async def _call_cover_service(self, service: str, expected: int = 1) -> None:
        self._mark_switch_pending(self._cover_entity_id, expected)
        self._start_bounce_grace_window()
        await self.hass.services.async_call(
            "cover", service, {"entity_id": self._cover_entity_id}, False
        )

    async def _send_open(self) -> None:
        """User-intent open. When inverted, drives the underlying close."""
        if self._invert:
            await self._send_underlying_close()
        else:
            await self._send_underlying_open()

    async def _send_close(self) -> None:
        """User-intent close. When inverted, drives the underlying open."""
        if self._invert:
            await self._send_underlying_open()
        else:
            await self._send_underlying_close()

    async def _send_underlying_open(self) -> None:
        # If the wrapped cover is currently closing, the open command produces
        # two state transitions (closing→open, then open→opening).
        state = self.hass.states.get(self._cover_entity_id)
        expected = 2 if state and state.state == STATE_CLOSING else 1
        await self._call_cover_service("open_cover", expected)

    async def _send_underlying_close(self) -> None:
        # If the wrapped cover is currently opening, the close command produces
        # two state transitions (opening→open, then open→closing).
        state = self.hass.states.get(self._cover_entity_id)
        expected = 2 if state and state.state == STATE_OPENING else 1
        await self._call_cover_service("close_cover", expected)

    async def _send_stop(self) -> None:
        # A cover that lacks native stop_cover but supports set_cover_position
        # is stopped by re-issuing its current (time-based) position as a
        # target: the device runs to where it already is and halts there. Only
        # do this when we positively know stop is unsupported and set position
        # is — otherwise keep the legacy stop_cover (covers an entity whose
        # capabilities are momentarily unknown, e.g. while unavailable).
        features = self._wrapped_features()
        supports_stop = features is not None and bool(
            features & CoverEntityFeature.STOP
        )
        supports_set_position = features is not None and bool(
            features & CoverEntityFeature.SET_POSITION
        )
        if not supports_stop and supports_set_position:
            pos = self.travel_calc.current_position()
            if pos is not None:
                self._log(
                    "_send_stop :: no native stop; freezing via set_cover_position(%d)",
                    int(round(pos)),
                )
                await self._call_set_cover_position(int(round(pos)))
                return
        await self._call_cover_service("stop_cover")

    # --- Tilt motor relay commands ---

    def _has_tilt_motor(self) -> bool:
        """Wrapped covers use the cover entity for tilt commands."""
        return self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor

    def _has_dual_motor_tilt_route(self) -> bool:
        """Wrapped covers route tilt through the underlying cover entity, so the
        dual-motor tilt route exists whenever a cover entity is configured —
        there are no dedicated tilt switch ids to check (mirrors the
        _has_tilt_motor override). Without this the calibration bootstrap would
        fall back to the switch-id check and drive the whole shade (close_cover)
        instead of the underlying's close_cover_tilt on a first-time tilt
        calibration.
        """
        return self._cover_entity_id is not None

    def _wrapped_supports_tilt(self) -> bool:
        """Return True if the wrapped cover advertises native tilt support.

        Dual-motor tilt delegates open/close/stop_cover_tilt to the wrapped
        entity, which only works if that entity exposes tilt. A config may pair
        dual_motor with a cover that doesn't support tilt (hand-edited options,
        or a cover that dropped tilt support after a device/firmware change);
        firing tilt services at it would error. When the wrapped cover is
        unavailable its features read as 0 — treat that as "unknown, don't
        delegate" rather than firing a doomed command.
        """
        state = self.hass.states.get(self._cover_entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False
        features = state.attributes.get(ATTR_SUPPORTED_FEATURES) or 0
        return bool(
            features & (CoverEntityFeature.OPEN_TILT | CoverEntityFeature.CLOSE_TILT)
        )

    def _skip_tilt_command(self, service: str) -> None:
        _LOGGER.warning(
            "%s: wrapped cover %s does not report tilt support (it may not"
            " support tilt, or be unavailable); skipping %s. If this cover never"
            " supports tilt, change the tilt mode away from 'separate tilt"
            " motor' for it.",
            self.entity_id,
            self._cover_entity_id,
            service,
        )

    async def _call_set_cover_tilt_position(self, position: int) -> None:
        """Forward a set_cover_tilt_position command to the wrapped entity.

        No bounce-grace window here (unlike the position forward): the
        self-driven-tilt guard already suppresses the wrapped cover's own
        opening/closing echo, and a bounce window would swallow a fast settle
        report that the tilt settle-snap needs.
        """
        await self.hass.services.async_call(
            "cover",
            "set_cover_tilt_position",
            {"entity_id": self._cover_entity_id, ATTR_TILT_POSITION: position},
            False,
        )

    async def _prepare_native_tilt(self) -> None:
        """Stop any in-flight move before forwarding a native tilt.

        The base tilt entry points abandon the active lifecycle and stop an
        in-flight travel before tilting. _abandon_active_lifecycle early-returns
        without stopping a plain (non-restore, non-pre-step) timed travel, so
        stop that here explicitly — including its physical relay — otherwise a
        tilt issued mid-travel leaves the wrapped cover's position motor running.
        """
        await self._abandon_active_lifecycle()
        if self.travel_calc.is_traveling():
            self.travel_calc.stop()
            self.stop_auto_updater()
            if not self._triggered_externally:
                await self._send_stop()

    async def async_set_cover_tilt_position(self, **kwargs):
        """Forward tilt-to-position natively when the wrapped cover can."""
        if ATTR_TILT_POSITION in kwargs and self._use_native_tilt():
            await self._native_tilt_driver.move_to(int(kwargs[ATTR_TILT_POSITION]))
            return
        await super().async_set_cover_tilt_position(**kwargs)

    async def _async_move_tilt_to_endpoint(self, target):
        """Route open/close-tilt through native forwarding when available."""
        if self._use_native_tilt():
            await self._native_tilt_driver.move_to(target)
            return
        await super()._async_move_tilt_to_endpoint(target)

    async def _send_tilt_open(self) -> None:
        if not self._wrapped_supports_tilt():
            self._skip_tilt_command("open_cover_tilt")
            return
        await self._call_cover_service("open_cover_tilt")

    async def _send_tilt_close(self) -> None:
        if not self._wrapped_supports_tilt():
            self._skip_tilt_command("close_cover_tilt")
            return
        await self._call_cover_service("close_cover_tilt")

    async def _send_tilt_stop(self) -> None:
        if not self._wrapped_supports_tilt():
            self._skip_tilt_command("stop_cover_tilt")
            return
        await self._call_cover_service("stop_cover_tilt")
