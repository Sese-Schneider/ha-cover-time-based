"""Base class for time-based cover entities."""

import asyncio
import logging
import time
from abc import abstractmethod
from asyncio import sleep
from contextvars import ContextVar
from datetime import timedelta
from enum import Enum, auto
from typing import Literal

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_CURRENT_TILT_POSITION,
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity

from .calibration import CalibrationState
from .const import (
    CONF_ENDPOINT_RUNON_TIME,
    CONF_FORCE_ENDPOINT_REDRIVE,
    CONF_MIN_MOVEMENT_TIME,
    CONF_RECALIBRATE_BEFORE_POSITION,
    CONF_TILT_MODE,
    CONF_TILT_STARTUP_DELAY,
    CONF_TILT_TIME_CLOSE,
    CONF_TILT_TIME_OPEN,
    CONF_TRAVEL_STARTUP_DELAY,
    CONF_TRAVEL_TIME_CLOSE,
    CONF_TRAVEL_TIME_OPEN,
    CONF_WAIT_FOR_RELAY_FEEDBACK,
    DIRECTION_CHANGE_DELAY,
    RESYNC_POSITIONS,
)
from .cover_calibration import CalibrationMixin
from .cover_echo_filter import SwitchEchoMixin
from .cover_lifecycle import MovementLifecycleMixin
from .cover_movement import MovementMixin
from .position_storage import async_get_position_store
from .tilt_strategies import InlineTilt, SequentialTilt
from .travel_calculator import TravelCalculator, TravelStatus

_LOGGER = logging.getLogger(__name__)

# (task, cover) pairs for the external-state handlers currently running.
#
# One module-level var holding a set, rather than one var per entity: context
# variables are never reclaimed, so creating them per instance would leak on
# every integration reload.
#
# The task is part of the key, not incidental. A context is *copied into* every
# task and timer callback created while it is active — and HA's interval timer
# reschedules itself from inside that copy — so storing the flag in a
# ContextVar alone hands it to the entire auto-updater chain for the life of
# the movement, long after the handler that raised it returned. Pairing it with
# the owning task means an inherited copy is still there but no longer matches,
# which is exactly the scope we want: the handler's own awaits, nothing it
# schedules. See CoverTimeBased._triggered_externally.
_EXTERNAL_TRIGGER: ContextVar[frozenset] = ContextVar(
    "cover_time_based_external_trigger", default=frozenset()
)


class RawCommandNotSupported(HomeAssistantError):
    """A raw command the configured hardware cannot take (tilt without a tilt motor)."""


# "travel" drives self.travel_calc; "tilt" drives self.tilt_calc on a
# dedicated tilt motor (dual_motor). Named here once so a typo reads as a
# type error instead of silently picking the wrong branch — see the axis
# dispatch in _recalibration_plan / _start_recalibration_drive /
# _arm_recalibrated_leg.
RecalibrationAxis = Literal["travel", "tilt"]


class RecalibrationPlan(Enum):
    """What a position command should do about recalibration (issue #179)."""

    NONE = auto()
    TWO_LEG = auto()
    FORCED_ENDPOINT = auto()


class CoverTimeBased(
    CalibrationMixin,
    SwitchEchoMixin,
    MovementMixin,
    MovementLifecycleMixin,
    CoverEntity,
    RestoreEntity,
):
    """Time-based cover with position tracking."""

    # Push-based: the auto-updater writes state; there is no async_update, so a
    # poll would only rewrite unchanged state.
    _attr_should_poll = False

    # Direction relay entity ids, set by the relay-driven mode mixins
    # (CoverSwitch and its subclasses). Declared here because base methods such
    # as _movement_target reference them; a wrapped cover sets neither and never
    # reaches those methods.
    _open_switch_entity_id: str | None
    _close_switch_entity_id: str | None

    # Whether this control mode can drive tilt at all. A single-button cover
    # cannot choose a direction, so it sets this False (see the design spec).
    supports_tilt = True

    # What _get_missing_configuration calls the driving entities; modes with a
    # different input vocabulary override it.
    _missing_entities_label = "input entities"

    # Whether a stop on this hardware is a momentary tap (toggle, single
    # button) rather than a de-energise. A tap sent before the relay confirms
    # the start can be swallowed, or stop a run nothing is tracking yet, so a
    # stop or reversal waits the confirmation out — see
    # _await_confirmation_before_stop.
    _stop_is_a_tap = False

    # How many of an armed drive's own echoes follow its confirming ON on the
    # same relay: a pulse's deferred OFF, a press's release. A filtered ON is
    # that drive's confirmation only when it leaves no more than this many
    # transitions outstanding — anything more is an earlier tap's echo.
    _own_echoes_after_confirming_on = 0

    def __init__(
        self,
        device_id,
        name,
        tilt_strategy,
        travel_time_close,
        travel_time_open,
        tilt_time_close,
        tilt_time_open,
        travel_startup_delay,
        tilt_startup_delay,
        endpoint_runon_time,
        min_movement_time,
        tilt_open_switch=None,
        tilt_close_switch=None,
        tilt_stop_switch=None,
        tilt_mode_str="none",
        close_includes_tilt=True,
        assumed_state=True,
        force_endpoint_redrive=False,
        wait_for_relay_feedback=False,
        recalibrate_before_position=False,
    ):
        """Initialize the cover."""
        self._unique_id = device_id
        self._assumed_state = assumed_state
        self._force_endpoint_redrive = force_endpoint_redrive
        self._wait_for_relay_feedback = wait_for_relay_feedback
        self._recalibrate_before_position = recalibrate_before_position

        self._tilt_strategy = tilt_strategy
        # Keep the raw configured mode so calibration can still pick the right
        # relay before tilt times are set (when _tilt_strategy is None).
        self._tilt_mode_str = tilt_mode_str
        self._travel_time_close = travel_time_close
        self._travel_time_open = travel_time_open
        self._tilting_time_close = tilt_time_close
        self._tilting_time_open = tilt_time_open
        self._travel_startup_delay = travel_startup_delay
        self._tilt_startup_delay = tilt_startup_delay
        self._endpoint_runon_time = endpoint_runon_time
        self._min_movement_time = min_movement_time
        self._tilt_open_switch_id = tilt_open_switch
        self._tilt_close_switch_id = tilt_close_switch
        self._tilt_stop_switch_id = tilt_stop_switch
        self._close_includes_tilt = close_includes_tilt

        if name:
            self._name = name
        else:
            self._name = device_id

        self._config_entry_id: str | None = None
        self._calibration: CalibrationState | None = None
        self._unsubscribe_auto_updater = None
        self._auto_updater_last_written: tuple | None = None
        self._delay_task = None
        self._startup_delay_task = None
        self._last_command = None
        # Claimed by every command that supersedes an in-flight movement; read
        # across the settle gap by _settle_before_reversing.
        self._movement_epoch = 0
        self._removed = False
        # Drives the post-travel tilt phase via _start_tilt_restore (consumed
        # by the auto-updater when travel reaches endpoint). Set by:
        #   - _plan_tilt_for_travel (mid-position moves: restore prior tilt;
        #     dual-motor endpoint moves: snap tilt to endpoint).
        #   - _start_tilt_pre_step (after pre-step + travel completes).
        #   - async_close_cover when close_includes_tilt is on and the tilt
        #     strategy doesn't already drive tilt to 0 during close travel
        #     (sequential_close, dual_motor — not inline or sequential_open).
        self._tilt_restore_target: int | None = None
        self._tilt_restore_active: bool = False
        # Identity for the active restore, bumped on every claim. The bool says
        # only that *a* restore is live, which a restore resuming from an await
        # cannot distinguish from its own — see _tilt_restore_superseded.
        self._tilt_restore_epoch: int = 0
        self._pending_travel_target: int | None = None
        self._pending_travel_command: str | None = None
        self._pending_tilt_target: int | None = None
        self._pending_tilt_command: str | None = None
        # Second leg of a recalibrated move (issue #179). Leg A drives to a
        # physical endpoint; this is the move the user actually asked for,
        # consumed by auto_stop_if_necessary once leg A completes. The epoch is
        # leg A's movement epoch: any newer command bumps _movement_epoch and
        # the mismatch drops the follow-up.
        self._pending_recalibrated_target: int | None = None
        self._pending_recalibrated_axis: RecalibrationAxis | None = None
        self._recalibration_epoch: int | None = None
        self._self_initiated_movement = True
        # True while the active movement drives a dedicated tilt motor (dual
        # motor), so auto-stop settles the tilt motor instead of travel.
        self._moving_tilt_motor = False
        # True while the active movement is a tilt move (any tilt mode). The
        # endpoint run-on is a *travel* concept — it keeps a latched relay
        # energized so the shutter seats against its physical limit. A tilt
        # move that finishes while the cover is parked at a travel endpoint is
        # not at a limit, so it must not run on (issue #125).
        self._moving_tilt = False
        self._state = True
        self._pending_switch = {}
        # What we last commanded a latching relay to be, held only while that
        # command's echo is still outstanding (see _relay_is_on).
        self._relay_intent: dict[str, bool] = {}
        self._pending_switch_timers = {}
        # Absolute monotonic expiry per entity, so a re-mark can never shorten
        # an outstanding window (see _mark_switch_pending).
        self._pending_switch_deadlines = {}
        self._state_listener_unsubs = []
        # Relay-feedback timing (wait_for_relay_feedback). Three short-lived
        # fields spanning one deferred move:
        #   _feedback_armed_entity — set by the _send_* that just energized a
        #     relay OFF->ON; read and cleared by _begin_movement to decide
        #     whether to defer tracking. Never outlives the send->begin hop.
        #     Each _send_* clears this first, and that eager per-send clear is
        #     load-bearing, not redundant: _movement_epoch is too coarse to
        #     reject a stale arm centrally (a tilt-to-safe pre-step and its
        #     deferred travel leg share one epoch yet drive different relays,
        #     and the command dispatchers do not bump it), so an arm stranded by
        #     one phase would otherwise be consumed by the next on the wrong
        #     relay — see test_travel_leg_after_tilt_pre_step_does_not_inherit_tilt_arm.
        #   _feedback_wait_entity / _feedback_wait_future — the relay whose ON
        #     echo the deferred move (or a feedback-timed calibration drive) is
        #     waiting on, and the future its confirming echo resolves. Live only
        #     while the wait is in flight.
        self._feedback_armed_entity: str | None = None
        self._feedback_wait_entity: str | None = None
        self._feedback_wait_future: asyncio.Future | None = None

        self.travel_calc = TravelCalculator(
            self._travel_time_close,
            self._travel_time_open,
            name="travel",
        )
        if self._tilting_time_close is not None and self._tilting_time_open is not None:
            self.tilt_calc = TravelCalculator(
                self._tilting_time_close,
                self._tilting_time_open,
                name="tilt",
            )

    def _log(self, msg, *args):
        """Log a debug message prefixed with the entity ID.

        Guarded: this is called on every tick and event, so the format
        concat and the logger call must cost nothing with DEBUG off.
        """
        if not _LOGGER.isEnabledFor(logging.DEBUG):
            return
        _LOGGER.debug("(%s) " + msg, self.entity_id, *args)

    def _extra_persist_data(self) -> dict:
        """Mode-specific data to merge into the persisted position dict."""
        return {}

    def _apply_restored_extra(self, stored: dict) -> None:
        """Apply mode-specific fields from the restored position dict."""
        return

    async def _async_load_restored_positions(self) -> tuple[int | None, int | None]:
        """Return (position, tilt_position) for restore.

        PositionStore is authoritative; RestoreEntity state is only used
        when the Store has no record for this entry (pre-Store installs
        or fresh entries).
        """
        if self._config_entry_id is not None:
            store = await async_get_position_store(self.hass)
            stored = await store.async_get(self._config_entry_id)
            if stored is not None:
                self._apply_restored_extra(stored)
                return stored.get("position"), stored.get("tilt_position")

        old_state = await self.async_get_last_state()
        self._log("async_added_to_hass :: oldState %s", old_state)
        if old_state is None:
            return None, None
        return (
            old_state.attributes.get(ATTR_CURRENT_POSITION),
            old_state.attributes.get(ATTR_CURRENT_TILT_POSITION),
        )

    async def _async_persist_position(self) -> None:
        """Write the current travel/tilt position to the position store.

        Refused once removed: the store keeps one shared, delay-saved record
        per entry, so a late write from a replaced entity would overwrite
        whatever its replacement has already recorded. Removal writes its own
        final record through _write_position_record.
        """
        if self._removed:
            return
        await self._write_position_record()

    async def _write_position_record(self, *, final: bool = False) -> None:
        if self._config_entry_id is None:
            return
        data: dict[str, int | str] = {}
        position = self.travel_calc.current_position()
        if position is not None:
            data["position"] = int(position)
        if self._has_tilt_support():
            tilt_position = self.tilt_calc.current_position()
            if tilt_position is not None:
                data["tilt_position"] = int(tilt_position)
        data.update(self._extra_persist_data())
        store = await async_get_position_store(self.hass)
        if self._removed and not final:
            # Removal landed while this write was parked on the store; only
            # removal's own final record may land after the flag.
            return
        await store.async_save(self._config_entry_id, data)

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    # Single source of truth for the switch-target attribute names. Used both
    # to register state-change listeners and to enumerate configured targets.
    _SWITCH_TARGET_ATTRS = (
        "_open_switch_entity_id",
        "_close_switch_entity_id",
        "_stop_switch_entity_id",
        "_tilt_open_switch_id",
        "_tilt_close_switch_id",
        "_tilt_stop_switch_id",
    )

    async def async_added_to_hass(self):
        """Only cover's position and tilt matters."""
        pos, tilt_pos = await self._async_load_restored_positions()
        # The two trackers restore independently: the store can hold a tilt
        # with no travel position (a raw command clears one tracker only).
        if self.travel_calc is not None and pos is not None:
            self.travel_calc.set_position(int(pos))
        if self._has_tilt_support() and tilt_pos is not None:
            self.tilt_calc.set_position(int(tilt_pos))

        # Register state change listeners for switch entities
        for attr in self._SWITCH_TARGET_ATTRS:
            entity_id = getattr(self, attr, None)
            if entity_id:
                self._state_listener_unsubs.append(
                    async_track_state_change_event(
                        self.hass,
                        [entity_id],
                        self._async_switch_state_changed,
                    )
                )

    async def _cancel_background_pulses(self) -> None:
        """Cancel any background relay-pulse / press-sequence work on removal.

        No-op in the base class. Pulse mode overrides this to cancel its
        in-flight ``_complete_pulse`` tasks and turn the affected relays off,
        so a relay caught mid-pulse is not left latched ON. Single-button
        mode overrides it similarly, additionally cancelling an in-flight
        press sequence and endpoint settle margin so the OLD entity does not
        keep pressing the physical button after a reload.
        """
        return

    async def async_will_remove_from_hass(self):
        """Clean up when entity is removed.

        Removal leaves the relays of hardware that cannot stop itself
        de-energised, whether or not it knew of a move.

        A removed entity may only stop. Every card save reloads the entry, so
        this runs with continuations parked on awaits and commands mid-flight;
        none of them may start a relay, start tracking or write the store once
        it has run. The flag, the epoch and the multi-phase clear are set
        before the first await so nothing that resumes during this method's
        own yields can slip through. The auto-stop task is deliberately not
        cancelled: a STOP it is half-way through sending must still go out,
        which is why stops declare themselves to _call_service.
        """
        self._removed = True
        self._supersede_movement()
        self._clear_multiphase_tilt_state()
        self.stop_auto_updater()
        for unsub in self._state_listener_unsubs:
            unsub()
        self._state_listener_unsubs.clear()
        for timer in self._pending_switch_timers.values():
            timer()
        self._pending_switch_timers.clear()
        self._pending_switch_deadlines.clear()
        self._relay_intent.clear()
        # Capture movement before cancelling its timers so each tracker can
        # settle independently; shared-motor tilt drives the travel motor
        # with only tilt_calc travelling.
        tilt_axis_driving = self._has_tilt_support() and self.tilt_calc.is_traveling()
        deferred = self._cancel_startup_delay_task()
        runon = self._cancel_delay_task()
        # A cancelled deferred start is a move already at the relay with both
        # trackers still idle. ``_moving_tilt`` names the axis it belongs to;
        # ``_moving_tilt_motor`` only names the motor, so a shared-motor tilt
        # read off that flag would settle the travel axis at the tilt's limit
        # and leave the slats recorded where they no longer are.
        deferred_tilt = deferred and self._moving_tilt
        # A calibration time test (or an overhead test's final step) drives the
        # motor continuously toward an endpoint with no live tracker — the
        # calibration owns the motor and bypasses it. Self-stopping hardware
        # still reaches that limit after removal, so treat the calibrated axis
        # as driving to park its tracker there. A stepped/pulsed test that has
        # not reached its final continuous phase drives only short bursts, so it
        # is excluded (an overhead step that does run the tracker is caught by
        # the axis's own is_traveling above).
        calibration = self._calibration
        calibration_tilt = False
        calibration_travel = False
        if calibration is not None and self._driven_continuously_to_endpoint():
            calibration_tilt = calibration.uses_tilt_motor
            calibration_travel = not calibration.uses_tilt_motor
        tilt_driving = (
            tilt_axis_driving
            or (self._has_tilt_motor() and self._moving_tilt_motor)
            or deferred_tilt
            or calibration_tilt
        )
        # A shared-motor tilt runs the travel motor, so it drives both axes.
        travel_driving = (
            self.travel_calc.is_traveling()
            or ((tilt_axis_driving or deferred_tilt) and not self._has_tilt_motor())
            or runon
            or (deferred and not self._moving_tilt)
            or calibration_travel
        )
        await self._cancel_background_pulses()
        # A start may have reached the relay before its tracker was armed, so
        # hardware that cannot stop itself always receives a stop. On hardware
        # that self-stops, a stop tap at the limit is a movement command (#153);
        # leave that motor to its limit switch and park its tracker there.
        stops_itself = self._self_stops_at_endpoints()
        fallback_limit = self._limit_for_last_command()
        tilt_fallback_limit = self._tilt_limit_for_last_command()
        # A calibration drives its axis to the endpoint named by its own command,
        # not by _last_command — a dedicated-tilt or overhead calibration never
        # records the travel _last_command — so park the calibrated axis there.
        if calibration_tilt:
            tilt_fallback_limit = self._calibration_endpoint()
        elif calibration_travel:
            fallback_limit = self._calibration_endpoint()
        # Calibration owns its motor stop, including tracked overhead steps.
        if self._calibration is None and not stops_itself:
            await self._async_handle_command(SERVICE_STOP_COVER)
            self._last_command = None
            if self._has_tilt_motor():
                await self._send_tilt_stop()
        self._settle_axis_after_removal(
            self.travel_calc, driving=travel_driving, fallback_limit=fallback_limit
        )
        if self._has_tilt_support():
            self._settle_axis_after_removal(
                self.tilt_calc,
                driving=tilt_driving,
                fallback_limit=tilt_fallback_limit,
            )
        self._moving_tilt_motor = False
        self._moving_tilt = False
        if self._calibration is not None:
            # Calibration may drive without a live tracker. Cancelling its
            # safety timeout therefore also requires a stop, unless the motor
            # stops itself at its limit and a stop tap could restart it (#153).
            self._restore_calibration_startup_delay()
            self._cancel_calibration_tasks()
            try:
                if not stops_itself:
                    await self._calibration_stop()
            finally:
                self._calibration = None
        # The reload creates the replacement only after this returns, so this
        # is the record it restores from.
        await self._write_position_record(final=True)

    # -----------------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------------

    @property
    def name(self):
        """Return the name of the cover."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique id."""
        return "cover_timebased_uuid_" + self._unique_id

    @property
    def device_class(self):
        """Return the device class of the cover."""
        return None

    @property
    def available(self) -> bool:
        """Return True if the cover is configured and its targets are available."""
        return (
            not self._get_missing_configuration() and not self._any_target_unavailable()
        )

    @property
    def assumed_state(self):
        """Return whether Home Assistant should treat the position as assumed.

        Defaults to True because a time-based cover's position is calculated
        from travel time with no feedback. Users who trust the calculation can
        set this False so the UI greys out unavailable actions (e.g. close when
        already closed).
        """
        return self._assumed_state

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Flag supported features."""
        supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )

        if self._has_tilt_support():
            supported_features |= (
                CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.STOP_TILT
                | CoverEntityFeature.SET_TILT_POSITION
            )

        return supported_features

    @property
    def current_cover_position(self) -> int | None:
        """Return the current position of the cover."""
        return self.travel_calc.current_position()

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return the current tilt of the cover."""
        if self._has_tilt_support():
            return self.tilt_calc.current_position()
        return None

    @property
    def is_opening(self):
        """Return if the cover is opening or not."""
        return (
            self.travel_calc.is_traveling()
            and self.travel_calc.travel_direction == TravelStatus.DIRECTION_UP
        ) or (
            self._has_tilt_support()
            and self.tilt_calc.is_traveling()
            and self.tilt_calc.travel_direction == TravelStatus.DIRECTION_UP
        )

    @property
    def is_closing(self):
        """Return if the cover is closing or not."""
        return (
            self.travel_calc.is_traveling()
            and self.travel_calc.travel_direction == TravelStatus.DIRECTION_DOWN
        ) or (
            self._has_tilt_support()
            and self.tilt_calc.is_traveling()
            and self.tilt_calc.travel_direction == TravelStatus.DIRECTION_DOWN
        )

    def _travel_axis_opening(self) -> bool:
        """Whether the *travel* axis is opening, for reversal decisions.

        On dual_motor a dedicated tilt motor moves independently of travel, so
        a moving tilt motor must not read as the cover opening (that would make
        a travel command stop-and-settle the running tilt motor). A travel
        operation still counts while its tilt-to-safe pre-step runs — travel is
        pending though ``travel_calc`` hasn't started — so the pending travel
        command's direction is honoured (the queued travel direction, not the
        tilt pre-step's own motion, which may be the opposite way). Shared-motor
        tilt (inline/sequential) has no separate motor — its tilt phase IS the
        travel motor running — so the cover-level property is retained there to
        keep settle-before-reverse.

        External-toggle handlers must judge physical motion without this pending
        direction: see ``ToggleBaseCover._motor_opening``.
        """
        if not self._has_tilt_motor():
            return self.is_opening
        if self.travel_calc.is_opening():
            return True
        if self._pending_travel_target is not None:
            return self._pending_travel_command == SERVICE_OPEN_COVER
        return False

    def _travel_axis_closing(self) -> bool:
        """Travel-axis counterpart of :meth:`_travel_axis_opening`."""
        if not self._has_tilt_motor():
            return self.is_closing
        if self.travel_calc.is_closing():
            return True
        if self._pending_travel_target is not None:
            return self._pending_travel_command == SERVICE_CLOSE_COVER
        return False

    @property
    def is_closed(self):
        """Return if the cover is closed.

        Tracks travel position only — tilt is reported independently via
        current_cover_tilt_position. This matches HA's general cover
        semantics and is what drives the built-in toggle action.
        """
        return self.travel_calc.is_closed()

    @property
    def extra_state_attributes(self):
        """Return the device state attributes."""
        attr = {}
        if self._tilt_strategy is not None:
            attr[CONF_TILT_MODE] = self._tilt_strategy.name
        if self._travel_time_close is not None:
            attr[CONF_TRAVEL_TIME_CLOSE] = self._travel_time_close
        if self._travel_time_open is not None:
            attr[CONF_TRAVEL_TIME_OPEN] = self._travel_time_open
        if self._tilting_time_close is not None:
            attr[CONF_TILT_TIME_CLOSE] = self._tilting_time_close
        if self._tilting_time_open is not None:
            attr[CONF_TILT_TIME_OPEN] = self._tilting_time_open
        if self._travel_startup_delay is not None:
            attr[CONF_TRAVEL_STARTUP_DELAY] = self._travel_startup_delay
        if self._tilt_startup_delay is not None:
            attr[CONF_TILT_STARTUP_DELAY] = self._tilt_startup_delay
        if self._endpoint_runon_time is not None:
            attr[CONF_ENDPOINT_RUNON_TIME] = self._endpoint_runon_time
        if self._min_movement_time is not None:
            attr[CONF_MIN_MOVEMENT_TIME] = self._min_movement_time
        attr[CONF_FORCE_ENDPOINT_REDRIVE] = self._force_endpoint_redrive
        attr[CONF_WAIT_FOR_RELAY_FEEDBACK] = self._wait_for_relay_feedback
        attr[CONF_RECALIBRATE_BEFORE_POSITION] = self._recalibrate_before_position
        if self._calibration is not None:
            attr["calibration_active"] = True
            attr["calibration_attribute"] = self._calibration.attribute
            if self._calibration.final_step:
                attr["calibration_final_step"] = True
            elif self._calibration.step_count > 0:
                attr["calibration_step"] = self._calibration.step_count
        return attr

    # -----------------------------------------------------------------------
    # Public HA service handlers
    # -----------------------------------------------------------------------

    async def async_close_cover(self, **kwargs):
        """Close the cover fully.

        Travel is moved to 0 unless already settled there (no resync motor
        pulse — matches HA convention that close_cover re-applied is a no-op).

        When close_includes_tilt is True and the cover has tilt support and
        tilt is not already at 0, the slats are closed afterward. This makes
        close_cover land at (0, 0) on strategies that would otherwise park
        tilt at an implicit-open or safe position (sequential_close, dual_motor).
        """
        self._require_configured()
        self._log("async_close_cover")
        if not self._triggered_externally and (
            self._travel_axis_opening() or self._travel_axis_closing()
        ):
            # In-motion UI click stops the cover. Reversing direction requires
            # a second click after the stop, or use set_cover_position which
            # keeps its existing stop-then-reverse behavior. External triggers
            # (wall switches) keep the legacy "stop and reverse if needed"
            # behavior to honor the physical user intent. Decisions key off the
            # travel axis so a moving independent tilt motor (dual_motor) isn't
            # stopped by a travel command.
            self._log("async_close_cover :: cover is in motion, stopping")
            await self.async_stop_cover()
            return
        if self._triggered_externally and self._travel_axis_opening():
            # External trigger: stop the opposite-direction motion, settle,
            # then proceed with close (legacy reverse behavior).
            self._log("async_close_cover :: external close while opening, reversing")
            # This stop is the reversal's own prelude, not a command to halt —
            # superseding here would cancel the movement it is starting.
            await self.async_stop_cover(supersede=False)
            if not await self._settle_before_reversing():
                return

        # Skip the re-drive when already settled at 0 (HA convention: a
        # re-applied close is a no-op). _settled_at_endpoint keeps the
        # carve-outs that must still reach _async_move_to_endpoint — a pending
        # opposite-direction startup delay to cancel, or an external sequential
        # close that articulates the slats.
        settled = self._settled_at_endpoint(0)
        force_redrive = settled and self._force_endpoint_redrive
        if force_redrive:
            # issue #167: don't trust "already closed" — re-drive the full close
            # so a remote-opened, no-feedback cover actually closes.
            await self._force_full_redrive(target=0)
        elif not settled:
            await self._async_move_to_endpoint(target=0)
        # Travel was skipped only when settled at 0 without a forced re-drive.
        skip_travel = settled and not force_redrive

        # Skip inline: its close already drives tilt to 0 via a TiltTo pre-step,
        # so the trailing restore would be a no-op AND would short-circuit the
        # endpoint_runon_time block in auto_stop_if_necessary.
        if (
            self._close_includes_tilt
            and self._has_tilt_support()
            and not isinstance(self._tilt_strategy, InlineTilt)
            and self.tilt_calc.current_position() not in (None, 0)
        ):
            if skip_travel:
                # Already settled at travel=0. The auto-updater isn't running
                # to consume _tilt_restore_target, so drive tilt directly.
                self._log(
                    "async_close_cover :: travel already at 0, closing tilt directly"
                )
                await self._async_move_tilt_to_endpoint(target=0)
            elif self._tilt_restore_target is None:
                # Travel is in flight via the auto-updater. Set the restore
                # target so the auto-updater chains _start_tilt_restore after
                # travel completes. This avoids _abandon_active_lifecycle
                # cancelling the in-flight travel.
                #
                # Guarded on `is None` so we don't overwrite a value that
                # _plan_tilt_for_travel may already have set (e.g. dual_motor
                # pre-step path sets _tilt_restore_target = target).
                self._log("async_close_cover :: scheduling tilt-close after travel")
                self._tilt_restore_target = 0

    async def async_open_cover(self, **kwargs):
        """Open the cover fully.

        In-motion UI click stops the cover. Reversing direction requires a
        second click, or use set_cover_position which keeps its existing
        stop-then-reverse behavior. External triggers (wall switches) keep
        the legacy "stop and reverse if needed" behavior.
        """
        self._require_configured()
        self._log("async_open_cover")
        if not self._triggered_externally and (
            self._travel_axis_opening() or self._travel_axis_closing()
        ):
            self._log("async_open_cover :: cover is in motion, stopping")
            await self.async_stop_cover()
            return
        if self._triggered_externally and self._travel_axis_closing():
            self._log("async_open_cover :: external open while closing, reversing")
            # Reversal prelude, not a halt command — see async_close_cover.
            await self.async_stop_cover(supersede=False)
            if not await self._settle_before_reversing():
                return
        # Mirror async_close_cover's skip-at-0 for covers that treat an endpoint
        # re-command as a pointless re-energize rather than a resync (command-
        # echo wrapped, issue #152). Relay modes keep the resync re-drive.
        settled_open = self._settled_at_endpoint(100)
        if settled_open and self._force_endpoint_redrive:
            # issue #167: don't trust "already open" — re-drive the full open,
            # overriding both the command-echo skip and the short resync.
            await self._force_full_redrive(target=100)
            return
        if self._skip_open_resync_at_endpoint() and settled_open:
            self._log("async_open_cover :: already settled at 100, skipping resync")
            return
        await self._async_move_to_endpoint(target=100)

    def _settled_at_endpoint(self, endpoint: int) -> bool:
        """Return True when the tracker is stopped exactly at ``endpoint`` (0 or
        100) and a re-drive there would be a pure resync — nothing to cancel or
        articulate.

        Excludes two cases that must still reach ``_async_move_to_endpoint``: a
        pending opposite-direction startup delay (which that method cancels),
        and an external close on sequential-tilt hardware (which drives past 0
        to articulate the slats). The sequential carve-out is an endpoint-0
        concern only — the drive-past redirect in ``_async_move_to_endpoint`` is
        gated on ``target == 0`` — so it is not applied at 100, where it would
        needlessly defeat the open-at-100 no-op.
        """
        opposite = SERVICE_OPEN_COVER if endpoint == 0 else SERVICE_CLOSE_COVER
        pending_opposite_startup = (
            self._startup_delay_task is not None
            and not self._startup_delay_task.done()
            and self._last_command == opposite
        )
        external_sequential = (
            endpoint == 0
            and self._triggered_externally
            and isinstance(self._tilt_strategy, SequentialTilt)
        )
        return (
            not (pending_opposite_startup or external_sequential)
            and self.travel_calc.current_position() == endpoint
            and self.travel_calc.travel_direction == TravelStatus.STOPPED
        )

    def _skip_open_resync_at_endpoint(self) -> bool:
        """Whether ``open_cover`` at the open endpoint (100%) is a no-op rather
        than a resync re-drive.

        Relay-driven modes return False: re-driving to the endpoint physically
        resyncs a drifted cover, and the pulse (#129) and toggle (#105) resync
        paths depend on it. A command-echo wrapped cover overrides this to True
        — it has no feedback to resync and drives an endstop-less motor, so
        re-commanding open there only re-energizes (and stalls) it (issue #152).
        ``async_close_cover`` already treats 0% as a universal no-op; this
        brings open into line for the covers that need it.
        """
        return False

    async def _force_full_redrive(
        self, target: int, *, suppress_start_command: bool = False
    ) -> None:
        """Re-drive fully to ``target`` (0 or 100) even though the tracker
        believes it is already settled there (issue #167).

        For a cover with no position feedback that an external remote may have
        moved, the believed endpoint is untrustworthy. Model the start as the
        opposite endpoint so the normal endpoint move runs the motor for the
        full travel time (and each mode's tilt phases) instead of skipping or
        firing only a short resync pulse.

        Correctness relies on callers only invoking this from a settled
        endpoint: _settled_at_endpoint already excludes the states where
        _async_move_to_endpoint would early-return without starting travel (a
        pending opposite-direction startup delay, an external sequential close),
        so seeding the opposite endpoint always reaches the full-travel branch.
        Keep that exclusion in sync if those guards ever change.

        Validates BEFORE seeding the opposite endpoint: _async_move_to_endpoint
        performs the same _require_travel_time / _require_movement_target_available
        checks itself further down its own path, so this is belt-and-braces
        pre-validation, not duplicated logic that can drift out of sync — its
        only job is to keep a failed command from mutating travel_calc first.
        Without it, a raise from either check (e.g. the switch entity going
        unavailable) left the tracker seeded at the opposite endpoint with no
        movement ever started to correct it, so a stale/wrong position got
        persisted on the next state write. _self_initiated_movement is
        refreshed first (mirroring _async_move_to_endpoint's own first line)
        so _require_movement_target_available's gate sees this call's trigger
        source rather than a value left over from a previous movement.

        ``suppress_start_command`` is forwarded straight through to
        _async_move_to_endpoint — the caller must decide it BEFORE calling
        here, because the seed below erases the evidence it is derived from
        (see _start_recalibration_drive).
        """
        closing = target == 0
        self._self_initiated_movement = not self._triggered_externally
        self._require_travel_time(closing)
        self._require_movement_target_available(self._movement_target(closing))

        opposite = 100 if target == 0 else 0
        self._log(
            "_force_full_redrive :: target=%d modeled from opposite=%d",
            target,
            opposite,
        )
        # The travel target is pre-validated above, but a dual-motor redrive
        # seeds the opposite endpoint and then drives the tilt-to-safe pre-step
        # BEFORE travel — and that pre-step validates the tilt switch and fires
        # the tilt relay deeper in (_start_tilt_pre_step), AFTER this seed. A
        # tilt-phase failure there would otherwise leave the tracker parked at
        # the opposite endpoint with no movement started to correct it (a wrong
        # position then persisted), and the pre-step's continuation fields
        # dangling. Snapshot before seeding and roll back on any failure. The
        # seed can't move earlier — _async_move_to_endpoint needs it in place to
        # reach the full-travel branch, and the deferred travel derives its
        # direction from it.
        snapshot = self.travel_calc.snapshot()
        self.travel_calc.set_position(opposite)
        try:
            await self._async_move_to_endpoint(
                target=target, suppress_start_command=suppress_start_command
            )
        except Exception:
            self.travel_calc.restore(snapshot)
            self._pending_travel_target = None
            self._pending_travel_command = None
            self._tilt_restore_target = None
            raise

    async def _force_full_tilt_redrive(
        self, target: int, *, suppress_start_command: bool = False
    ) -> None:
        """Re-drive tilt fully to ``target`` (0 or 100) on a dedicated tilt
        motor, even though the tracker believes it is already there (#179).

        The dual-motor analogue of _force_full_redrive: model the start as the
        opposite tilt endpoint so the tilt motor runs for its full tilt time
        and stalls at its own limit, giving a true datum for a cover an
        external remote may have moved.

        Only valid where the tilt motor is independent. On a shared-motor
        strategy the excess would not stall — it would bleed into cover travel
        and desync the travel tracker — so _start_recalibration_drive routes
        those to the travel re-drive instead.

        Mirrors _force_full_redrive's rollback scope: _async_move_tilt_to_endpoint
        has the same shape as _async_move_to_endpoint — on a boundary-locked
        dual_motor cover it may run a travel pre-step first
        (_start_travel_pre_step), which sets the continuation fields
        _pending_tilt_target / _pending_tilt_command *before* firing the travel
        relay command. A failure there (e.g. the travel switch entity going
        unavailable) leaves those dangling with no travel movement ever
        started to reach the auto-updater continuation that would otherwise
        consume them, so they must be cleared alongside the tracker restore.

        ``suppress_start_command`` is forwarded straight through, exactly as
        in _force_full_redrive: the seed below erases the "was travelling"
        evidence the caller derives it from.
        """
        opposite = 100 if target == 0 else 0
        self._self_initiated_movement = not self._triggered_externally
        self._log(
            "_force_full_tilt_redrive :: target=%d modeled from opposite=%d",
            target,
            opposite,
        )
        snapshot = self.tilt_calc.snapshot()
        self.tilt_calc.set_position(opposite)
        try:
            await self._async_move_tilt_to_endpoint(
                target=target, suppress_start_command=suppress_start_command
            )
        except Exception:
            self.tilt_calc.restore(snapshot)
            self._pending_tilt_target = None
            self._pending_tilt_command = None
            raise

    def _recalibration_plan(
        self, recalibrate: bool, position: int, *, axis: RecalibrationAxis
    ) -> RecalibrationPlan:
        """Decide what this position command should do about recalibration
        (issue #179):

        - ``NONE``: an ordinary timed move, no recalibration.
        - ``TWO_LEG``: drive to the fully-open datum first (leg A), then a
          second leg to the requested position (leg B).
        - ``FORCED_ENDPOINT``: a single forced full re-drive straight to the
          target — no second leg, because the target itself already IS the
          datum.

        The endpoint carve-out is asymmetric. A travel endpoint target (0/100)
        never gets a two-leg recalibration — the target itself is the datum's
        own axis, so there is nothing left to drive to once it's reached.
        That does NOT mean an endpoint target is trusted as-is, though: an
        ordinary timed move would compute its duration from the tracker's
        BELIEVED current position, which is exactly the value this feature
        exists to distrust — so a travel endpoint target gets
        ``FORCED_ENDPOINT`` instead of ``NONE``, routing it through the same
        forced-full-redrive machinery as leg A (issue #179 finding 3).

        On hardware that self-stops at its physical limits
        (``_self_stops_at_endpoints`` True) the wrong duration from an
        ordinary timed move is masked: ``auto_stop_if_necessary`` skips the
        explicit stop there, so the relay stays live and the motor runs into
        its limit regardless of the computed duration. Switch mode does not
        self-stop — its relay is latched for the computed duration and cut by
        an explicit stop at the end of it — so drift there strands the cover
        short of the endpoint. Routing every mode through ``FORCED_ENDPOINT``
        fixes this uniformly, and is a no-op change on hardware where the bug
        was already masked.

        Tilt endpoints qualify for the no-second-leg carve-out only on a
        dedicated tilt motor: on the shared-motor strategies a tilt endpoint
        is reached by driving the travel motor for a tilt time, with nothing
        to stall against, so every tilt target there still gets ``TWO_LEG``.

        Where the carve-out does apply — a dedicated tilt motor — it is
        ``FORCED_ENDPOINT``, not ``NONE``, for exactly the reason spelled out
        above for travel: ``NONE`` is an ordinary timed move computed from the
        BELIEVED tilt position, and the masking that makes that survive on
        self-stopping hardware is absent in switch mode and in pulse with the
        default ``send_endpoint_stop`` — there ``_tilt_settle`` de-energises
        the tilt relay on time and the motor never stalls. A believed-90 → 100
        move is then a 10%-of-tilt-time nudge; if the real tilt were at 20 it
        lands at ~30. Routed through ``_force_full_tilt_redrive(target)``, it
        runs the full tilt time from the opposite tilt endpoint and stalls
        against the tilt motor's own limit instead.
        """
        if not self._recalibrate_before_position or not recalibrate:
            return RecalibrationPlan.NONE
        if self._triggered_externally:
            return RecalibrationPlan.NONE
        if axis == "travel":
            if position not in (0, 100):
                return RecalibrationPlan.TWO_LEG
            return RecalibrationPlan.FORCED_ENDPOINT
        if self._tilt_strategy is None:
            # Defensive, not reachable today: HA's required_features gate
            # keeps set_tilt_position from ever running without tilt
            # configured. But the rest of this function tolerates
            # _tilt_strategy is None (see the three checks above and in the
            # travel branch), and set_tilt_position itself dereferences
            # _tilt_strategy.uses_tilt_motor unconditionally right after
            # calling this — an AttributeError there would slip past
            # _maybe_start_recalibrated_leg's `except HomeAssistantError`.
            # Returning NONE here keeps this function's own local invariant
            # (tolerate None) rather than relying on the unreachability
            # holding forever.
            return RecalibrationPlan.NONE
        if self._tilt_strategy.uses_tilt_motor:
            if position not in (0, 100):
                return RecalibrationPlan.TWO_LEG
            return RecalibrationPlan.FORCED_ENDPOINT
        return RecalibrationPlan.TWO_LEG

    def _movement_started(
        self, *, prior_startup_task: asyncio.Task | None = None
    ) -> bool:
        """Whether the movement just commanded is actually under way.

        A recalibration leg arms its follow-up only if leg A really started.
        _async_move_to_endpoint and _async_move_tilt_to_endpoint both return
        None and have several silent early returns of their own (a
        same-direction startup delay already active, a direction-change
        cancel, a resync/no-op at an already-matching target, a
        settle-gap supersede) — arming behind any of them would strand the
        pending target with no completion ever coming to consume it. With no
        return value to read from those methods, this instead probes every
        piece of state a started drive could have touched:

        - ``travel_calc.is_traveling()`` — a plain travel drive began.
        - a NEW ``_startup_delay_task`` (see ``prior_startup_task`` below) —
          the relay is on and the motor is pending its startup delay.
        - ``_pending_travel_target`` — a tilt-before-travel pre-step began.
        - ``tilt_calc.is_traveling()`` (dual_motor only) — a tilt drive (or
          its own pre-step) began.

        Each early return in the two funnel methods must leave every one of
        these untouched, or this reads a leg A that never actually moved as
        "started" and arms a leg B with nothing left to trigger it — see the
        comment at each such return in those two methods.

        ``prior_startup_task`` is the startup-delay task that was already
        live *before* this drive was attempted, if any. Without it, a startup
        delay left over from an earlier, unrelated move reads as "this drive
        started" even when the drive's own early-return left it untouched —
        the caller must pass the task it captured immediately before driving,
        so only a delay task the drive itself created counts.

        One of three deliberately different "is anything moving" checks: this
        one asks whether the move *just commanded* began, _movement_in_progress
        asks whether anything at all is still being driven, and toggle's
        ``was_active`` asks only whether a tap would stop rather than start the
        motor.
        """
        if self.travel_calc.is_traveling():
            return True
        if (
            self._startup_delay_task is not None
            and not self._startup_delay_task.done()
            and self._startup_delay_task is not prior_startup_task
        ):
            return True
        if self._pending_travel_target is not None:
            return True
        return self._has_tilt_support() and self.tilt_calc.is_traveling()

    def _is_direction_change(self, command: str) -> bool:
        """Whether ``command`` reverses the last one we sent."""
        return self._last_command is not None and self._last_command != command

    async def _stop_and_settle_before_recalibration_drive(self, command: str) -> bool:
        """Stop and settle an in-flight movement a recalibration drive is
        about to reverse (issue #179).

        A travel-axis recalibration drive funnels through
        ``_force_full_redrive`` -> ``_async_move_to_endpoint``, which —
        unlike its tilt counterpart ``_async_move_tilt_to_endpoint`` — has no
        in-motion-reversal handling of its own: past its startup-delay
        branch it just issues ``command`` at whatever is already running.
        On hardware whose direction relays are independently addressable
        (Switch) that is silently harmless, but on Toggle (opposite button)
        an opposite-direction pulse while moving IS a stop
        (``cover_toggle_opposite_mode.py``) — so the motor halts mid-travel
        while the tracker keeps counting toward the recalibration drive's
        fabricated full-travel target, and the eventual endpoint stop then
        pulses the *other* relay at an already-stopped motor: a #153-class
        phantom move. Even where the relays are independent, skipping this
        drops the fixed settle gap every other reversal in this class gets.

        Mirrors ``set_position``'s own direction-change block (the plain,
        non-recalibrated path further down) rather than a second reversal
        mechanism, so both callers there — leg A of a mid-position
        recalibrated move (always drives OPEN, reverses only while closing)
        and a forced endpoint redrive (drives OPEN or CLOSE, reverses either
        way) — share the same stop-then-settle behaviour the rest of the
        class already relies on. ``set_tilt_position`` reuses it too for its
        own ``axis="travel"`` recalibration leg (the shared-motor tilt
        strategies — inline, sequential): that leg drives the plain travel
        OPEN command exactly like ``set_position``'s leg A, whichever tilt
        strategy is configured — a shared-motor tilt move's own command
        (from ``tilt_command_for``, inverted on ``sequential_open``) still
        ends up in ``_last_command`` as whichever relay it actually energised,
        so the plain ``_last_command != command`` check here already accounts
        for that inversion with no special-casing needed. The dual-motor
        tilt leg (``axis="tilt"``) is a different, independent motor and has
        its own counterpart — see
        ``_stop_and_settle_tilt_before_recalibration_drive``.

        Returns False if the movement was superseded during the settle gap.
        The caller must return immediately rather than fall back to a plain
        move — something else has already claimed the movement, mirroring
        the plain path's own ``if not await self._settle_before_reversing():
        return``.
        """
        shared_motor_tilt_traveling = (
            self._has_tilt_support()
            and not self._tilt_strategy.uses_tilt_motor
            and self.tilt_calc.is_traveling()
        )
        is_direction_change = self._is_direction_change(command)
        if not (
            is_direction_change
            and (self.travel_calc.is_traveling() or shared_motor_tilt_traveling)
        ):
            return True
        self._log(
            "_stop_and_settle_before_recalibration_drive :: reversing"
            " in-flight movement before driving %s",
            command,
        )
        self.travel_calc.stop()
        self.stop_auto_updater()
        if self._has_tilt_support() and self.tilt_calc.is_traveling():
            self.tilt_calc.stop()
        await self._async_handle_command(SERVICE_STOP_COVER)
        return await self._settle_before_reversing()

    async def _stop_and_settle_tilt_before_recalibration_drive(
        self, command: str, was_tilt_motor_move: bool
    ) -> bool:
        """Tilt-axis counterpart of ``_stop_and_settle_before_recalibration_drive``,
        for a dual-motor recalibration leg (``axis="tilt"``, issue #179).

        The gap here has a different mechanism than the travel axis, but the
        same effect. ``_force_full_tilt_redrive`` seeds ``tilt_calc`` to the
        opposite endpoint *before* ``_async_move_tilt_to_endpoint`` ever
        runs — and that seed sets the tracker's target equal to its own
        position, so ``tilt_calc.is_traveling()`` reads False by the time
        ``_async_move_tilt_to_endpoint``'s own in-motion-reversal check runs.
        That check does exist (unlike the travel axis, which has none at
        all) but is defeated for every recalibration-drive caller, because
        it always runs after the seed has already erased the "was
        travelling" signal it depends on. This must be evaluated from the
        tracker's TRUE state, before ``_start_recalibration_drive`` (and the
        seed inside it) ever runs.

        Mirrors ``set_tilt_position``'s own direction-change block: the same
        ``is_direction_change`` formula, and the same axis-aware stop
        (``_stop_displaced_movement_for_tilt``) rather than a blind travel
        STOP — a moving dedicated tilt motor must get a tilt stop, not a
        travel STOP off a stale ``_last_command`` (#153).

        ``was_tilt_motor_move`` must be the caller's own snapshot of
        ``self._moving_tilt_motor``, taken before anything resets it —
        mirrors ``set_tilt_position``'s own capture for the same reason (see
        ``_stop_displaced_movement_for_tilt``).

        Returns False if the movement was superseded during the settle gap;
        the caller must return immediately rather than fall back to a plain
        move or the drive itself.
        """
        is_direction_change = self._is_direction_change(command)
        was_moving = self.tilt_calc.is_traveling() or self.travel_calc.is_traveling()
        if not (is_direction_change and was_moving):
            return True
        self._log(
            "_stop_and_settle_tilt_before_recalibration_drive :: reversing"
            " in-flight movement before driving %s",
            command,
        )
        if self.tilt_calc.is_traveling():
            self.tilt_calc.stop()
        if self.travel_calc.is_traveling():
            self.travel_calc.stop()
        self.stop_auto_updater()
        await self._stop_displaced_movement_for_tilt(was_tilt_motor_move)
        return await self._settle_before_reversing()

    def _already_driving_travel_toward(self, target: int) -> bool:
        """Whether the travel motor is ALREADY running the direction a forced
        re-drive to ``target`` would command (issue #179).

        The mirror image of ``_stop_and_settle_before_recalibration_drive``'s
        reversal test, and gated on the same two facts for the same reasons:
        ``_last_command`` for the direction (a shared-motor tilt phase records
        whichever relay it actually energised there, inversions included) and
        "is anything actually moving" so a stale command outliving its movement
        — a bare ``_handle_stop`` leaves exactly that — cannot suppress a drive
        at a stopped motor. Deliberately ``== command`` rather than ``not
        _is_direction_change(command)``: the latter also matches
        ``_last_command is None``, and suppressing on *no* recorded direction
        would animate the tracker over a motor nobody started.

        Must be evaluated BEFORE the forced re-drive seeds the opposite
        endpoint — the seed clears ``is_traveling()`` — hence a caller-side
        decision rather than a check inside the funnel.
        """
        command = SERVICE_CLOSE_COVER if target == 0 else SERVICE_OPEN_COVER
        shared_motor_tilt_traveling = (
            self._has_tilt_support()
            and not self._tilt_strategy.uses_tilt_motor
            and self.tilt_calc.is_traveling()
        )
        return self._last_command == command and (
            self.travel_calc.is_traveling() or shared_motor_tilt_traveling
        )

    def _already_driving_tilt_toward(self, target: int) -> bool:
        """Tilt-axis counterpart of ``_already_driving_travel_toward``, for a
        dedicated tilt motor (dual_motor, issue #179).

        Reads ``tilt_calc`` rather than ``_last_command``, which is ambiguous
        on this axis: dual_motor's ``tilt_command_for`` returns the plain
        open/close services, so a *travel* move heading open leaves
        ``_last_command`` indistinguishable from a tilt move heading open.
        Suppressing off that would skip the tilt pulse while the tilt motor
        sits idle and its tracker animates — the very desync this guard exists
        to prevent, inverted. ``tilt_calc`` has no such ambiguity: this is only
        ever called for a dedicated tilt motor (the caller passes ``"tilt"``
        only when ``uses_tilt_motor``), and there the tilt tracker moves only
        while that motor is energised — a plain tilt move, a tilt-to-safe
        pre-step, or a tilt restore. A travel move never couples it into
        motion (dual_motor's plans never set ``coupled_tilt``, and the
        pre-step-skipped path starts it already at its target).

        Deliberately NOT also conjoined with ``_moving_tilt_motor``: only a
        plain tilt move sets that flag, so requiring it would re-pulse a tilt
        motor that a pre-step or a restore has running. Neither of those gets
        a compensating stop from ``_abandon_active_lifecycle`` either — the
        forced re-drive's seed clears ``tilt_calc.is_traveling()`` before that
        runs, so its ``was_tilt_traveling`` term reads False as well.
        """
        return self.tilt_calc.is_traveling() and self.tilt_calc.is_closing() == (
            target == 0
        )

    async def _start_recalibration_drive(
        self, axis: RecalibrationAxis, target: int = 100
    ) -> bool:
        """Drive a forced full re-drive to ``target``. True if it actually
        started.

        Restores the tracker the forced re-drive seeded when the drive silently
        did not start, so the caller's fallback plain move is planned from the
        believed position rather than from the modelled opposite endpoint.

        ``target`` defaults to 100: leg A of a mid-position recalibrated move
        always drives to the fully-open datum, since the position the user
        actually asked for is planned as a separate leg B afterwards (see
        set_position / set_tilt_position). An endpoint travel target (0 or
        100) has no separate leg — driving to it fully IS the whole move — so
        that caller passes its own ``target`` instead of taking the default
        (issue #179 finding 3).

        ``axis`` selects which tracker leg A drives, and with it which
        calculator is snapshotted/restored and which redrive coroutine runs.
        The caller only passes ``"tilt"`` when the strategy uses a dedicated
        tilt motor (dual_motor) — the only hardware where a tilt drive stalls
        against its own limit and so is a true datum; every other
        tilt-triggered call passes ``"travel"`` instead, since on shared-motor
        hardware the tilt "motor" IS the travel motor and the datum is a
        travel endpoint. No further guard is needed here.

        The drive's start command is suppressed when the motor is already
        running that way. This is the counterpart of the caller's own
        stop-and-settle for the reversing case, and it has to be decided here
        rather than downstream: the forced re-drive seeds the opposite endpoint
        before issuing anything, which erases the "was travelling" evidence.
        Re-issuing the start command at a motor already driving that direction
        is what the plain path guards with ``already_moving_same_dir`` — on
        toggle (same-button) hardware the second edge stops the motor, and the
        seeded tracker then animates a full travel over a motor at a standstill
        (issue #179). Suppressed uniformly across modes, exactly as the plain
        path does: elsewhere the re-command is merely redundant, so there is
        nothing to gain from a per-mode carve-out.
        """
        calc = self.tilt_calc if axis == "tilt" else self.travel_calc
        redrive = (
            self._force_full_tilt_redrive
            if axis == "tilt"
            else self._force_full_redrive
        )
        already_driving = (
            self._already_driving_tilt_toward(target)
            if axis == "tilt"
            else self._already_driving_travel_toward(target)
        )
        if already_driving:
            self._log(
                "_start_recalibration_drive :: %s motor already driving toward"
                " %d%%, riding it rather than re-commanding",
                axis,
                target,
            )
        snapshot = calc.snapshot()
        prior_startup_task = self._startup_delay_task
        await redrive(target=target, suppress_start_command=already_driving)
        if self._movement_started(prior_startup_task=prior_startup_task):
            return True
        calc.restore(snapshot)
        return False

    def _arm_recalibrated_leg(self, target: int, axis: RecalibrationAxis) -> None:
        """Record the move to make once leg A reaches the endpoint."""
        self._pending_recalibrated_target = target
        self._pending_recalibrated_axis = axis
        self._recalibration_epoch = self._movement_epoch

    def _disarm_recalibrated_leg(self) -> None:
        """Drop any armed recalibration leg without running it."""
        self._pending_recalibrated_target = None
        self._pending_recalibrated_axis = None
        self._recalibration_epoch = None

    async def _direction_change_delay(self):
        """Pause between stop and direction change to let the motor settle.

        Fixed, not per-cover — see DIRECTION_CHANGE_DELAY in const.py.
        """
        await sleep(DIRECTION_CHANGE_DELAY)

    @property
    def _triggered_externally(self) -> bool:
        """Whether *this* call is handling something the hardware did.

        Set by the external-state dispatcher around its handler, and read all
        over to suppress relay writes (never echo a command back at hardware
        that is already doing it) and to pick external-trigger behaviour.

        Scoped to the task that raised it. An external handler holds this
        across every await it makes — including a reversal's whole settle gap —
        so as plain instance state it leaked onto anything that ran meanwhile:
        a UI stop landing in that window inherited the suppression and sent no
        relay command at all, halting the tracker while the motor ran on. HA
        dispatches each service call as its own task, so keying on the task
        means the handler still sees it across its own awaits while a
        concurrent caller does not.

        Keying on the *task* rather than only on the context is what stops the
        scope widening again the other way — see _EXTERNAL_TRIGGER.
        """
        return (asyncio.current_task(), self) in _EXTERNAL_TRIGGER.get()

    @_triggered_externally.setter
    def _triggered_externally(self, value: bool) -> None:
        entry = (asyncio.current_task(), self)
        current = _EXTERNAL_TRIGGER.get()
        _EXTERNAL_TRIGGER.set(current | {entry} if value else current - {entry})

    # Services that energise a relay or start the underlying cover. After
    # removal they are refused unless the caller declares the call a stop
    # (a Pulse stop is a turn_on of the stop relay; a Toggle stop taps a
    # direction relay). turn_off / stop_cover are never refused.
    _MOTOR_STARTING_SERVICES = frozenset(
        {
            "turn_on",
            "open_cover",
            "close_cover",
            "set_cover_position",
            "open_cover_tilt",
            "close_cover_tilt",
            "set_cover_tilt_position",
        }
    )

    async def _call_service(
        self, domain: str, service: str, data: dict, *, stop: bool = False
    ) -> None:
        """The one path every relay and underlying-cover service call takes.

        A removed entity may only stop: a motor-starting service is dropped
        here, where the relay is actually switched, so no mode's override, no
        native forward and no command parked between an OFF and an ON can
        energise a relay after the reload. ``stop`` is the caller's word that
        the call halts the motor; those go out so a STOP interrupted by
        removal, and removal's own owed stops, still reach the hardware.
        """
        if self._removed and not stop and service in self._MOTOR_STARTING_SERVICES:
            self._log("_call_service :: %s.%s refused, entity removed", domain, service)
            return
        await self.hass.services.async_call(domain, service, data, False)

    def _supersede_movement(self) -> None:
        """Claim the movement, cancelling any reversal waiting out its settle."""
        self._movement_epoch += 1

    def _claim_tilt_restore(self) -> int:
        """Mark a tilt restore active and return its identity."""
        self._tilt_restore_active = True
        self._tilt_restore_epoch += 1
        return self._tilt_restore_epoch

    def _release_tilt_restore(self) -> None:
        """Mark no restore active, cancelling any still parked on an await.

        Deliberately leaves the epoch alone: releasing does not hand identity
        to anyone, and the next claim bumps it anyway. That is why
        _tilt_restore_superseded has to test the flag as well as the epoch.
        """
        self._tilt_restore_active = False

    def _clear_multiphase_tilt_state(self) -> None:
        """Drop every in-flight movement phase — restore, pre-step, recalibration."""
        self._tilt_restore_target = None
        self._release_tilt_restore()
        self._pending_travel_target = None
        self._pending_travel_command = None
        self._pending_tilt_target = None
        self._pending_tilt_command = None
        self._disarm_recalibrated_leg()

    def _tilt_restore_superseded(self, epoch: int) -> bool:
        """Whether the restore holding ``epoch`` has been cancelled or replaced.

        The active flag alone answers "is a restore live", not "is mine". A
        restore cancelled while parked on an await, then replaced by a newer one
        before it resumed, read its own True back and carried on — driving the
        motor a second time and retargeting the tilt tracker at the goal it had
        already been told to abandon.
        """
        return not self._tilt_restore_active or epoch != self._tilt_restore_epoch

    async def _settle_before_reversing(self) -> bool:
        """Await the settle gap; False if this movement was superseded.

        A reversal stops the motor, waits for it to come to rest, then drives
        the other way — but the caller is a plain service-call coroutine, not a
        task anything can cancel. Without this check a stop (or a newer target)
        arriving inside the gap is overridden the moment the reversal resumes,
        moving the cover up to a second after the user stopped it.
        """
        epoch = self._movement_epoch
        await self._direction_change_delay()
        if epoch != self._movement_epoch:
            self._log("_settle_before_reversing :: superseded during settle, aborting")
            return False
        return True

    async def _stop_displaced_movement_for_tilt(
        self, was_tilt_motor_move: bool
    ) -> None:
        """Stop whatever a tilt command is displacing, on the right axis.

        A moving dedicated tilt motor gets a tilt stop ONLY — routing through
        the travel STOP would pulse an idle travel relay off a stale
        ``_last_command``, which on toggle hardware is a movement command
        (#153). Shared-motor tilt (and a genuinely moving travel axis) keeps
        the travel STOP.

        ``was_tilt_motor_move`` is captured by the caller *before*
        ``_abandon_active_lifecycle`` resets ``_moving_tilt_motor``; the flag
        is already False by the time the direction-change branches run, so the
        decision has to be passed in rather than read off the instance here.
        """
        if was_tilt_motor_move and not self.travel_calc.is_traveling():
            await self._send_tilt_stop()
        else:
            await self._async_handle_command(SERVICE_STOP_COVER)
            if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
                await self._send_tilt_stop()

    async def _release_displaced_tilt_motor(self, was_tilt_motor_move: bool) -> None:
        """Stop a dedicated tilt motor that a travel command displaced but
        never took over.

        The caller captures ``_moving_tilt_motor`` before
        ``_abandon_active_lifecycle`` clears it. Unless a tilt-to-safe pre-step
        takes over, every exit must release that motor: auto-stop can no longer
        identify it from the cleared flag. The caller handles the travel relay.

        The tracker's travelling flag distinguishes departure from arrival,
        not its position: a motor leaving an endpoint still needs a real stop.
        A tracker that has arrived settles without re-pulsing a momentary
        relay at its limit. A deferred start still pending (a feedback-wait or
        startup-delay tilt) means the relay is energized but tracking has not
        begun, so the motor is departing and must get a real stop — settling it
        would let an endpoint self-stop skip swallow a motor leaving its limit.
        Cancelling the deferred start also stops a late relay confirmation from
        restarting tracking after the motor is released.

        External travel presses leave the independent tilt motor running, so
        ``_triggered_externally`` prevents echoing a stop to that motor, just as
        it does in ``_abandon_active_lifecycle``.
        """
        if not was_tilt_motor_move or self._triggered_externally:
            return
        self._log("_release_displaced_tilt_motor :: stopping displaced tilt motor")
        deferred = self._cancel_startup_delay_task()
        departing = self.tilt_calc.is_traveling() or deferred
        self.tilt_calc.stop()
        self.stop_auto_updater()
        if departing:
            await self._send_tilt_stop()
        else:
            await self._tilt_settle()
        self._on_tilt_motor_move_complete()

    async def async_stop_cover(
        self, *, supersede: bool = True, tilt_axis_reported: bool = False, **kwargs
    ):
        """Stop the cover and publish the result.

        See _stop_hardware for ``supersede`` and ``tilt_axis_reported``.
        """
        self._log("async_stop_cover")
        await self._stop_hardware(
            supersede=supersede, tilt_axis_reported=tilt_axis_reported
        )
        self.async_write_ha_state()
        await self._async_persist_position()

    async def _stop_hardware(
        self, *, supersede: bool = True, tilt_axis_reported: bool = False
    ) -> None:
        """Stop the cover without publishing the result.

        Everything async_stop_cover does bar the trailing write and persist, so
        a caller that publishes its own outcome — set_known_position — writes
        and persists once rather than twice.

        ``supersede`` defaults True so a stop arriving from HA (service call,
        UI, automation) always claims the movement; the internal and
        external-trigger callers that are echoes or reversal preludes pass
        False. See _handle_stop.

        ``tilt_axis_reported`` says the tilt relay is the one that reported,
        so a stop must not be echoed back at it — see _should_stop_tilt_motor.
        """
        self._require_configured()
        await self._await_confirmation_before_stop()
        tilt_restore_was_active = self._tilt_restore_active
        tilt_pre_step_was_active = (
            self._pending_travel_target is not None
            or self._pending_tilt_target is not None
        )
        stop_tilt = self._should_stop_tilt_motor(
            tilt_restore_was_active
            or tilt_pre_step_was_active
            or self._moving_tilt_motor,  # plain dual-motor tilt move
            tilt_axis_reported=tilt_axis_reported,
        )
        travel_was_moving = self.travel_calc.is_traveling()
        self._neutralize_tracked_movement(supersede=supersede)
        if self._has_tilt_support():
            self._tilt_strategy.snap_trackers_to_physical(
                self.travel_calc, self.tilt_calc
            )
        if not self._triggered_externally and not (
            self._has_tilt_motor()
            and self._self_stops_at_endpoints()
            and not travel_was_moving
        ):
            # Skip the internal TRAVEL stop only for a dual-motor cover whose
            # travel axis did not move (a plain tilt move): it leaves
            # _last_command at the travel command (DualMotorTilt inherits
            # tilt_command_for) while the travel motor is idle, so an ungated
            # _send_stop pulses a stopped travel motor — a movement command on
            # toggle (#153), a go-to-favourite on pulse send_endpoint_stop=False
            # (#133). Everything else is unchanged: switch mode
            # (_self_stops_at_endpoints False) always de-energizes its latched
            # relay; non-dual-motor covers (no _has_tilt_motor — wrapped,
            # single-motor) keep sending _send_stop, and a genuine dual-motor
            # mid-travel stop (travel_was_moving) still fires. The tilt axis is
            # settled by _tilt_settle below, independently of this.
            await self._send_stop()
        elif tilt_axis_reported and travel_was_moving and self._self_initiated_movement:
            # The TILT relay reported, not the travel relay. The travel motor
            # is one we drive ourselves and nothing external stopped it —
            # suppressing here strands a latched relay (switch mode) or a
            # running motor. Mirror image of _should_stop_tilt_motor.
            await self._send_stop()
        if stop_tilt:
            # _tilt_settle, not a bare stop: at 0%/100% the motor is already
            # stopped on its limit switch and a momentary relay re-pulsed there
            # starts it again.
            await self._tilt_settle()
        self._moving_tilt_motor = False
        self._moving_tilt = False
        self._last_command = None

    def _should_stop_tilt_motor(
        self, tilt_phase_was_active: bool, *, tilt_axis_reported: bool
    ) -> bool:
        """Whether abandoning this movement leaves a tilt motor to take down.

        Only dual-motor covers have a tilt motor of their own; elsewhere tilt
        is the travel motor and _send_stop already covered it.

        The relay suppression that guards _send_stop is about not echoing a
        command back at hardware that already did it — which is true of the
        relay the external event was about, and of no other. The tilt motor is
        a separate relay we drive ourselves, so when a *travel* event abandons
        a live tilt phase nothing else will ever stop it: the tracker halts,
        the phase is forgotten, and the motor keeps running. Hence this is
        deliberately not gated on _triggered_externally.

        It is gated on ``tilt_axis_reported``, because when the tilt relay is
        the one that reported, echoing a stop back at it is exactly the thing
        the suppression exists to prevent — and on toggle hardware
        _send_tilt_stop is a *pulse*, so it would start the motor moving again
        rather than stop it.
        """
        return (
            tilt_phase_was_active and self._has_tilt_motor() and not tilt_axis_reported
        )

    async def async_stop_cover_tilt(self, **kwargs):
        """Stop tilt movement (STOP_TILT service/button).

        Delegates to the full stop: on shared-motor strategies the tilt phase
        IS the travel motor, and on dual-motor async_stop_cover now settles a
        running tilt motor too (see _should_stop_tilt_motor).
        """
        await self.async_stop_cover(**kwargs)

    async def async_close_cover_tilt(self, **kwargs):
        """Tilt the cover fully closed."""
        self._log("async_close_cover_tilt")
        await self._async_move_tilt_to_endpoint(target=0)

    async def async_open_cover_tilt(self, **kwargs):
        """Tilt the cover fully open."""
        self._log("async_open_cover_tilt")
        await self._async_move_tilt_to_endpoint(target=100)

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        self._require_configured()
        if ATTR_POSITION in kwargs:
            position = kwargs[ATTR_POSITION]
            self._log("async_set_cover_position: %d", position)
            await self.set_position(position)

    async def async_set_cover_tilt_position(self, **kwargs):
        """Move the cover tilt to a specific position."""
        if ATTR_TILT_POSITION in kwargs:
            position = kwargs[ATTR_TILT_POSITION]
            self._log("async_set_cover_tilt_position: %d", position)
            await self.set_tilt_position(position)

    def _movement_in_progress(self) -> bool:
        """Whether this entity is still driving the cover under its own lifecycle.

        Everything that leaves a relay energised or a follow-up pending: a live
        travel or tilt tracker, a startup-delay or relay-feedback wait, an
        endpoint run-on, a tilt pre-step or restore, and a dedicated tilt motor.

        Broader than the other two "is anything moving" checks on purpose:
        _movement_started asks only whether the move just commanded began, and
        toggle's ``was_active`` (cover_toggle_base) only whether a tap would
        stop the motor rather than start it.
        """

        def pending(task):
            return task is not None and not task.done()

        return (
            self.travel_calc.is_traveling()
            or (self._has_tilt_support() and self.tilt_calc.is_traveling())
            or pending(self._startup_delay_task)
            or pending(self._delay_task)
            or self._tilt_restore_active
            or self._pending_travel_target is not None
            or self._pending_tilt_target is not None
            or self._moving_tilt_motor
        )

    async def _halt_for_known_position(self) -> None:
        """Stop whatever this entity is still driving, leaving the publish to the caller.

        Parking the tracker alone is not enough: the relay stays latched and the
        motor runs to its limit while HA reports the declared position.

        The idle branch is still a supersession, not a no-op: the epoch bump in
        _handle_stop cancels a reversal parked in its settle gap, which would
        otherwise drive away from the position just declared.
        """
        if self._movement_in_progress():
            await self._stop_hardware()
        else:
            self._handle_stop()

    async def set_known_position(self, *, supersede: bool = True, **kwargs):
        """Declare the cover's real position (0=closed, 100=open).

        A user declaring where the cover *is* — the service, the card's presets,
        async_resync — is a real command (``supersede`` True): it claims the
        movement and stops the hardware first. Wrapped covers pass
        ``supersede=False`` to snap to a position the device just reported, which
        must neither claim the movement nor send anything — see _handle_stop.
        """
        position = kwargs[ATTR_POSITION]
        self._log("set_known_position: %d", position)
        if supersede:
            await self._halt_for_known_position()
        else:
            self._handle_stop(supersede=False)
        self.travel_calc.set_position(position)
        if self._has_tilt_support():
            self._tilt_strategy.snap_trackers_to_physical(
                self.travel_calc, self.tilt_calc
            )
        self._on_known_position(position)
        self.async_write_ha_state()
        await self._async_persist_position()

    def _on_known_position(self, position: int) -> None:
        """Hook: a position was declared for the travel axis.

        Base is a no-op. Overridden by modes that must re-anchor internal
        state against a declared position (e.g. single-button phase tracking).
        """
        return

    async def set_known_tilt_position(self, *, supersede: bool = True, **kwargs):
        """Declare the cover's real tilt (0=closed, 100=open).

        The tilt twin of set_known_position — the card fires the two back to
        back for a closed-and-tilted preset. A user declaring where the slats
        *are* is a real command (``supersede`` True): it claims the movement and
        stops the hardware first, so a dedicated tilt motor is not left driving
        past the angle just declared. Wrapped covers pass ``supersede=False`` to
        snap to a tilt the device just reported, which must neither claim the
        movement nor send anything — see _handle_stop.

        The travel position is untouched, so _on_known_position is not called.
        """
        if not self._has_tilt_support():
            return
        position = kwargs[ATTR_TILT_POSITION]
        self._log("set_known_tilt_position: %d", position)
        if supersede:
            await self._halt_for_known_position()
        self.tilt_calc.set_position(position)
        self.async_write_ha_state()
        await self._async_persist_position()

    async def async_resync(self, state: str) -> None:
        """Re-anchor the reported position to fully closed or fully open.

        The endpoint shortcut of set_known_position for every control mode:
        maps ``state`` via RESYNC_POSITIONS and declares that position.
        """
        if state not in RESYNC_POSITIONS:
            raise HomeAssistantError(f"unknown resync state: {state!r}")
        await self.set_known_position(position=RESYNC_POSITIONS[state])

    async def async_raw_command(self, command: str) -> None:
        """Drive the device directly, bypassing the position tracker.

        The card's calibration-screen buttons. Outside a calibration the tracked
        position becomes unknown and is persisted as such, so a restart does not
        re-anchor at the stale pre-command value; during a calibration the
        session owns the tracker and only the command is sent.

        Deliberately not gated on _require_configured: these buttons are how you
        position a cover in order to measure its travel times, so they have to
        work before any are configured.
        """
        self._log("async_raw_command: %s", command)
        is_tilt = command.startswith("tilt_")
        if is_tilt and not self._has_tilt_motor():
            raise RawCommandNotSupported("Tilt motor not configured")
        in_calibration = self._calibration is not None
        if not in_calibration:
            self._neutralize_tracked_movement()
        await self._raw_direction_command(command)
        if in_calibration:
            return
        if is_tilt:
            if self._has_tilt_support():
                self.tilt_calc.clear_position()
        else:
            self.travel_calc.clear_position()
        self.async_write_ha_state()
        await self._async_persist_position()

    # -----------------------------------------------------------------------
    # Movement tracking
    # -----------------------------------------------------------------------

    def _begin_movement(
        self,
        target,
        coupled_target,
        primary_calc,
        coupled_calc,
        startup_delay,
        pre_step_delay: float = 0.0,
    ):
        """Start position tracking on primary and optionally coupled calculator.

        Begins travel on the primary calculator toward `target`, and if a
        coupled_target is provided, also starts the coupled calculator.
        Then starts the auto updater. Honors motor startup delay if configured.

        If pre_step_delay > 0, the coupled calculator is a pre-step that must
        complete before the primary starts (e.g. tilt-before-travel in
        sequential mode). The primary calculator's start is offset by this
        delay so its position stays put until the pre-step finishes.
        """

        if self._removed:
            self._log("_begin_movement :: refused, entity removed")
            return

        def start(base_monotonic=None, extra_delay=0.0):
            self._log(
                "_begin_movement.start :: target=%d from=%s coupled=%s base_mono=%s "
                "extra_delay=%s self_initiated=%s external=%s",
                target,
                primary_calc.current_position(),
                coupled_target,
                base_monotonic,
                extra_delay,
                self._self_initiated_movement,
                self._triggered_externally,
            )
            primary_calc.start_travel(
                target,
                delay=pre_step_delay + extra_delay,
                base_monotonic=base_monotonic,
            )
            if coupled_target is not None:
                # extra_delay (the mechanical startup delay) applies to the
                # coupled calc too so both calcs start together; pre_step_delay
                # is the primary's alone — the coupled calc IS the pre-step.
                coupled_calc.start_travel(
                    int(coupled_target),
                    delay=extra_delay,
                    base_monotonic=base_monotonic,
                )
            self.start_auto_updater()

        # A _send_* that just energized a relay OFF->ON under
        # wait_for_relay_feedback parks the start here until that relay's ON echo
        # (or a timeout), instead of the fixed startup-delay sleep. The variable
        # Zigbee round-trip then falls outside the tracked travel (issue #231).
        feedback_entity = self._consume_feedback_arm()
        if feedback_entity is not None:
            # Stamped here rather than inside the wait: the fallback anchor is
            # the moment the relay was commanded, not the moment the waiting
            # coroutine happened to run. Monotonic, like everything the tracker reads.
            commanded_at = time.monotonic()
            self._startup_delay_task = self.hass.async_create_task(
                self._run_deferred_start(
                    lambda: self._await_relay_confirmation(
                        feedback_entity, commanded_at
                    ),
                    start,
                    startup_delay=startup_delay or 0.0,
                )
            )
        else:
            self._start_movement(startup_delay, start)

    def _start_movement(self, startup_delay, start_callback):
        """Start position tracking, optionally after a motor startup delay.

        If startup_delay is set, the relay is already ON but the motor hasn't
        started moving yet. We wait for the delay, then begin tracking.
        Otherwise we start tracking immediately.
        """
        if startup_delay and startup_delay > 0:
            self._startup_delay_task = self.hass.async_create_task(
                self._run_deferred_start(
                    lambda: self._await_startup_delay(startup_delay), start_callback
                )
            )
        else:
            start_callback()

    async def _await_startup_delay(self, startup_delay):
        """Sleep out the motor startup delay; tracking then starts from now."""
        self._log(
            "_await_startup_delay :: waiting %fs before starting position tracking",
            startup_delay,
        )
        await sleep(startup_delay)
        self._log("_await_startup_delay :: startup delay complete")
        return None

    async def _run_deferred_start(
        self, make_waiter, start_callback, *, startup_delay=0.0
    ):
        """Await the wait ``make_waiter`` builds, then start tracking from the
        anchor it returns, offset by ``startup_delay``.

        The wait is either a fixed motor startup delay (no anchor — tracking
        starts now) or a relay-feedback wait, on whose anchor the mechanical
        delay is folded. The waiter is built here rather than passed in
        already-created: it is then only created when the task actually runs, so
        the command time is stamped at the call site and a task cancelled before
        its first step owns no unstarted coroutine.

        Runs as ``_startup_delay_task`` so every consumer of that task —
        _movement_started, the reverse/same-direction conflict blocks and
        _cancel_startup_delay_task — treats both deferrals alike.
        """
        try:
            anchor = await make_waiter()
            start_callback(base_monotonic=anchor, extra_delay=startup_delay)
        except asyncio.CancelledError:
            self._log("_run_deferred_start :: cancelled")
            raise
        finally:
            # Only the owner nulls the slot: a replacement move registers its
            # own task before this one's cancellation handler runs.
            if self._startup_delay_task is asyncio.current_task():
                self._startup_delay_task = None

    def _cancel_delay_task(self):
        """Cancel any active delay task."""
        if self._delay_task is not None and not self._delay_task.done():
            self._log("_cancel_delay_task :: cancelling active delay task")
            self._delay_task.cancel()
            self._delay_task = None
            return True
        return False

    def _cancel_startup_delay_task(self) -> bool:
        """Cancel any active startup delay task; True if one was pending."""
        if self._startup_delay_task is not None and not self._startup_delay_task.done():
            self._log(
                "_cancel_startup_delay_task :: cancelling active startup delay task"
            )
            self._startup_delay_task.cancel()
            self._startup_delay_task = None
            return True
        return False

    def start_auto_updater(self):
        """Start the autoupdater to update HASS while cover is moving."""
        if self._removed:
            return
        self._log("start_auto_updater")
        if self._unsubscribe_auto_updater is None:
            self._log("init _unsubscribe_auto_updater")
            # Forget the last written positions so the first tick always writes.
            self._auto_updater_last_written = None
            interval = timedelta(seconds=0.1)
            self._unsubscribe_auto_updater = async_track_time_interval(
                self.hass, self.auto_updater_hook, interval
            )

    @callback
    def auto_updater_hook(self, _now):
        """Call for the autoupdater.

        Write only when the reported position or tilt changed; spawn the
        auto-stop only on arrival.
        """
        positions = (self.current_cover_position, self.current_cover_tilt_position)
        if positions != self._auto_updater_last_written:
            self._auto_updater_last_written = positions
            self.async_schedule_update_ha_state()
        if self.position_reached(positions=positions):
            self._log("auto_updater_hook :: position_reached")
            self.stop_auto_updater()
            self.hass.async_create_task(self.auto_stop_if_necessary())

    def stop_auto_updater(self):
        """Stop the autoupdater."""
        self._log("stop_auto_updater")
        if self._unsubscribe_auto_updater is not None:
            self._unsubscribe_auto_updater()
            self._unsubscribe_auto_updater = None

    def position_reached(
        self, *, positions: tuple[int | None, int | None] | None = None
    ) -> bool:
        """Return if cover has reached its final position.

        ``positions`` is a ``(position, tilt_position)`` pair a caller already
        computed (the auto-updater tick), handed down so neither calculator
        recalculates. Its tilt member is ignored when tilt is unsupported.
        """
        travel_pos, tilt_pos = (None, None) if positions is None else positions
        return self.travel_calc.position_reached(travel_pos) and (
            not self._has_tilt_support() or self.tilt_calc.position_reached(tilt_pos)
        )

    # -----------------------------------------------------------------------
    # Relay command dispatch
    # -----------------------------------------------------------------------

    async def _async_handle_command(self, command, *_args):
        cmd = command
        # Read once: the state below is decided on this value, and the log line
        # has to report the same one the gates used. Nothing awaits before the
        # gates, so this is the value each would have read for itself.
        suppressed = self._triggered_externally
        if command == SERVICE_CLOSE_COVER:
            cmd = "CLOSE"
            self._state = False
            self._last_command = command
            if not suppressed:
                await self._send_close()
        elif command == SERVICE_OPEN_COVER:
            cmd = "OPEN"
            self._state = True
            self._last_command = command
            if not suppressed:
                await self._send_open()
        elif command == SERVICE_STOP_COVER:
            cmd = "STOP"
            self._state = True
            if not suppressed:
                await self._send_stop()

        # Say whether the relay actually fired. This line is in every debug log
        # users send, and without the marker a command whose pulse went out and
        # one that was swallowed by the external-trigger guard read identically
        # — which made #153 undiagnosable from logs twice over.
        self._log(
            "_async_handle_command :: %s%s",
            cmd,
            " (suppressed: external trigger in flight, no relay command sent)"
            if suppressed
            else "",
        )
        self.async_write_ha_state()

    @abstractmethod
    async def _send_open(self) -> None:
        """Send the open command to the underlying device."""

    @abstractmethod
    async def _send_close(self) -> None:
        """Send the close command to the underlying device."""

    @abstractmethod
    async def _send_stop(self) -> None:
        """Send the stop command to the underlying device."""

    async def _raw_direction_command(self, command: str) -> None:
        """Execute a raw direction command (for calibration screen buttons).

        Sets _last_command / _last_tilt_direction and sends relay commands.
        Override in subclasses that need stop-before-direction-change
        (e.g. toggle mode where opposite-direction = stop, not reverse).
        """
        if command == "open":
            self._last_command = SERVICE_OPEN_COVER
            await self._send_open()
        elif command == "close":
            self._last_command = SERVICE_CLOSE_COVER
            await self._send_close()
        elif command == "stop":
            await self._send_stop()
            self._last_command = None
        elif command == "tilt_open":
            await self._send_tilt_open()
        elif command == "tilt_close":
            await self._send_tilt_close()
        elif command == "tilt_stop":
            await self._send_tilt_stop()

    # -----------------------------------------------------------------------
    # Tilt motor relay commands (dual_motor only)
    # -----------------------------------------------------------------------

    def _has_tilt_motor(self) -> bool:
        """Return True if a dedicated tilt motor is configured (dual_motor mode)."""
        return (
            self._tilt_strategy is not None
            and self._tilt_strategy.uses_tilt_motor
            and bool(self._tilt_open_switch_id and self._tilt_close_switch_id)
        )

    def _has_dual_motor_tilt_route(self) -> bool:
        """Whether a dual-motor tilt actuator is wired up, independent of the
        resolved TiltStrategy.

        Used by calibration's strategy-None bootstrap: the very first tilt
        calibration on a freshly-configured dual_motor cover runs before a
        TiltStrategy exists (calibration is the only way to set the tilt times
        _resolve_tilt_strategy needs), so it can't consult _has_tilt_motor.
        The base cover drives dedicated tilt switches, so the route exists iff
        both are configured; WrappedCoverTimeBased overrides this since it
        routes tilt through the underlying cover, not tilt switch ids (mirrors
        the _has_tilt_motor base/override split).
        """
        return bool(self._tilt_open_switch_id and self._tilt_close_switch_id)

    async def _send_tilt_open(self) -> None:
        """Send open to the tilt motor (bypasses position tracker).

        Switch-mode (latching) semantics: each turn_on/turn_off produces
        at most one state-change event, and only when the switch isn't
        already in the target state. Mark pending=1 per expected echo,
        and only when the relay call will actually flip state. Otherwise
        the orphan pending count consumes the next real state change.

        Whether the turn_off will flip is judged from our own last command
        while its echo is outstanding (``_relay_is_on``), because HA's state
        lags a slow relay. The driving relay's ON decision stays on HA's
        state: it also arms relay feedback for this command.
        """
        self._feedback_armed_entity = None
        if self._relay_is_on(self._tilt_close_switch_id):
            self._mark_switch_pending(self._tilt_close_switch_id, 1)
        if not self._switch_is_on(self._tilt_open_switch_id):
            self._mark_driving_relay_pending(self._tilt_open_switch_id)
        self._note_relay_intent(self._tilt_close_switch_id, False)
        await self._call_service(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_close_switch_id},
        )
        self._note_relay_intent(self._tilt_open_switch_id, True)
        await self._call_service(
            "homeassistant",
            "turn_on",
            {"entity_id": self._tilt_open_switch_id},
        )

    async def _send_tilt_close(self) -> None:
        """Send close to the tilt motor (bypasses position tracker).

        See _send_tilt_open for the pending-count rationale.
        """
        self._feedback_armed_entity = None
        if self._relay_is_on(self._tilt_open_switch_id):
            self._mark_switch_pending(self._tilt_open_switch_id, 1)
        if not self._switch_is_on(self._tilt_close_switch_id):
            self._mark_driving_relay_pending(self._tilt_close_switch_id)
        self._note_relay_intent(self._tilt_open_switch_id, False)
        await self._call_service(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_open_switch_id},
        )
        self._note_relay_intent(self._tilt_close_switch_id, True)
        await self._call_service(
            "homeassistant",
            "turn_on",
            {"entity_id": self._tilt_close_switch_id},
        )

    async def _send_tilt_stop(self) -> None:
        """Send stop to the tilt motor (bypasses position tracker).

        See _send_tilt_open for the pending-count rationale.
        """
        if self._relay_is_on(self._tilt_open_switch_id):
            self._mark_switch_pending(self._tilt_open_switch_id, 1)
        if self._relay_is_on(self._tilt_close_switch_id):
            self._mark_switch_pending(self._tilt_close_switch_id, 1)
        self._note_relay_intent(self._tilt_open_switch_id, False)
        await self._call_service(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_open_switch_id},
        )
        self._note_relay_intent(self._tilt_close_switch_id, False)
        await self._call_service(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_close_switch_id},
        )
        if self._tilt_stop_switch_id:
            self._mark_switch_pending(self._tilt_stop_switch_id, 2)
            await self._call_service(
                "homeassistant",
                "turn_on",
                {"entity_id": self._tilt_stop_switch_id},
                stop=True,
            )

    # -----------------------------------------------------------------------
    # External state change handlers
    # -----------------------------------------------------------------------

    @staticmethod
    def _came_back_online(old_val) -> bool:
        """Whether this transition is a target entity re-announcing itself.

        Its integration reloaded, its device reconnected, or Home Assistant
        restarted. Whatever state follows is the one that integration starts
        up in — or the stale one it retained — rather than something the
        hardware just did, so no mode should read it as a fresh event without
        deciding it is trustworthy first.
        """
        return old_val in (STATE_UNAVAILABLE, STATE_UNKNOWN)

    def _is_stale_reappearance(self, old_val, new_val) -> bool:
        """Whether this transition is an unreliable relay (re)appearing.

        Default ``False`` — most relays report their own OFF, so they come back
        ``off`` after a restart and a real ``off->on`` press is unambiguous.
        Overridden by modes whose relay's reported state can't be trusted
        across a restart/reconnect (see ToggleModeCover with
        ``relay_reports_off`` disabled), so the dispatcher skips treating the
        reappearance as a command.
        """
        return False

    async def _handle_external_tilt_state_change(self, entity_id, old_val, new_val):
        """Handle external state change on tilt switches (dual_motor).

        Tilt switches use pulse-mode behavior. The ON signal (rising edge)
        is the button press. The OFF transition is just button release.
        """
        if new_val != "on":
            return

        if entity_id == self._tilt_open_switch_id:
            self._log(
                "_handle_external_tilt_state_change :: external tilt open pulse detected"
            )
            await self.async_open_cover_tilt()
        elif entity_id == self._tilt_close_switch_id:
            self._log(
                "_handle_external_tilt_state_change :: external tilt close pulse detected"
            )
            await self.async_close_cover_tilt()
        elif entity_id == self._tilt_stop_switch_id:
            self._log(
                "_handle_external_tilt_state_change :: external tilt stop pulse detected"
            )
            # A dedicated stop relay is a press, not a report — see
            # SwitchCoverTimeBased._handle_external_state_change. It is the
            # tilt hardware's own stop, so don't echo one back at it.
            await self.async_stop_cover(tilt_axis_reported=True)

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle external state change. Override in subclasses for mode-specific behavior."""

    async def _handle_external_attribute_change(self, event):
        """Handle attribute-only updates on monitored entities. Default no-op.

        Override in subclasses that need to react to attribute changes
        (e.g. a wrapped cover updating its current_position attribute).
        """
