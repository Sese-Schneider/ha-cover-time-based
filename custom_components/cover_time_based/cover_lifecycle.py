"""Movement lifecycle (auto-stop, pre-step, restore) mixin for time-based cover entities."""

from __future__ import annotations

import asyncio
import logging
from asyncio import sleep
from typing import TYPE_CHECKING, Any

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
)
from homeassistant.exceptions import HomeAssistantError

from .travel_calculator import TravelCalculator, TravelStatus

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class MovementLifecycleMixin:
    """Mixin providing movement lifecycle (auto-stop, pre-step, restore) for CoverTimeBased."""

    if TYPE_CHECKING:
        hass: HomeAssistant
        entity_id: str
        travel_calc: TravelCalculator
        tilt_calc: TravelCalculator
        _tilt_strategy: Any
        _delay_task: asyncio.Task[Any] | None
        _last_command: str | None
        _endpoint_runon_time: float | None
        _movement_epoch: int
        _recalibration_epoch: int | None
        _removed: bool
        _self_initiated_movement: bool
        _triggered_externally: bool
        _moving_tilt: bool
        _moving_tilt_motor: bool
        _tilt_restore_active: bool
        _tilt_restore_target: int | None
        _travel_startup_delay: float | None
        _tilt_startup_delay: float | None
        _feedback_armed_entity: str | None
        _pending_travel_target: int | None
        _pending_travel_command: str | None
        _pending_tilt_target: int | None
        _pending_tilt_command: str | None
        _pending_recalibrated_target: int | None
        _pending_recalibrated_axis: str | None

        def _log(self, msg: str, *args: Any) -> None: ...
        def _has_tilt_support(self) -> bool: ...
        def _has_tilt_motor(self) -> bool: ...
        def position_reached(
            self, *, positions: tuple[int | None, int | None] | None = None
        ) -> bool: ...
        async def _async_handle_command(self, command: str, *_args: Any) -> None: ...
        async def _async_persist_position(self) -> None: ...
        def _begin_movement(
            self,
            target: Any,
            coupled_target: Any,
            primary_calc: Any,
            coupled_calc: Any,
            startup_delay: Any,
            pre_step_delay: float = 0.0,
        ) -> None: ...
        def _cancel_delay_task(self) -> bool: ...
        def _cancel_startup_delay_task(self) -> bool: ...
        def _claim_tilt_restore(self) -> int: ...
        def _clear_multiphase_tilt_state(self) -> None: ...
        async def _direction_change_delay(self) -> None: ...
        def _disarm_recalibrated_leg(self) -> None: ...
        def _movement_target(self, closing: bool) -> str | None: ...
        def _release_tilt_restore(self) -> None: ...
        def _require_movement_target_available(self, target: str | None) -> None: ...
        async def _send_tilt_close(self) -> None: ...
        async def _send_tilt_open(self) -> None: ...
        async def _send_tilt_stop(self) -> None: ...
        async def _settle_before_reversing(self) -> bool: ...
        async def set_position(
            self, position: Any, *, recalibrate: bool = True
        ) -> None: ...
        async def set_tilt_position(
            self, position: Any, *, recalibrate: bool = True
        ) -> None: ...
        def start_auto_updater(self) -> None: ...
        def stop_auto_updater(self) -> None: ...
        def _supersede_movement(self) -> None: ...
        def _tilt_movement_target(self, command: str) -> str | None: ...
        def _tilt_restore_superseded(self, epoch: int) -> bool: ...

    async def auto_stop_if_necessary(self):
        """Do auto stop if necessary.

        ``auto_updater_hook`` spawns this only on arrival, so anything added
        outside the ``position_reached`` check below would never run for it.
        """
        if self.position_reached():
            self._log(
                "auto_stop_if_necessary :: position reached (self_initiated=%s)",
                self._self_initiated_movement,
            )
            self.travel_calc.stop()
            if self._has_tilt_support():
                self.tilt_calc.stop()

            if not self._self_initiated_movement:
                # Movement was triggered externally. A multi-phase move still
                # has to chain its phases (dual-motor tilt pre-step → travel, or
                # travel pre-step → tilt); only the final endpoint relay handling
                # is special-cased below. Without continuing here the cover would
                # tilt-to-safe and then stall, needing a second press to travel.
                self._log("auto_stop_if_necessary :: external movement")
                if self._pending_travel_target is not None:
                    self._log(
                        "auto_stop_if_necessary :: external tilt pre-step complete"
                    )
                    await self._start_pending_travel()
                    return
                if self._pending_tilt_target is not None:
                    self._log(
                        "auto_stop_if_necessary :: external travel pre-step complete"
                    )
                    await self._start_pending_tilt()
                    return
                # Move complete: don't re-drive the relay, but a latched relay
                # (switch mode) must still be de-energized; momentary modes
                # self-released and no-op in _settle_external_endpoint.
                was_tilt_motor_move = self._moving_tilt_motor
                await self._settle_external_endpoint()
                if self._tilt_strategy is not None:
                    self._tilt_strategy.snap_trackers_to_physical(
                        self.travel_calc, self.tilt_calc
                    )
                self._last_command = None
                self._moving_tilt_motor = False
                self._moving_tilt = False
                if was_tilt_motor_move:
                    self._on_tilt_motor_move_complete()
                # The one terminal return here that does NOT dispatch an armed
                # recalibration leg — drop it instead (issue #179). Dispatching
                # would be wrong: leg B is a self-initiated move chained off a
                # datum leg A reached, and this branch is the *hardware* having
                # finished a move of its own. Driving the motor again off the
                # back of that is exactly the surprise-move the feature promises
                # never to make. A leg should not be armed here at all — an
                # external trigger gets RecalibrationPlan.NONE, and every route
                # that flips _self_initiated_movement to False runs
                # _abandon_active_lifecycle first, which clears the pending — so
                # this makes that invariant local and enforced rather than
                # inferred from four call sites. Self-limiting either way; the
                # point is that it cannot rot.
                self._disarm_recalibrated_leg()
                await self._async_persist_position()
                return

            if self._tilt_restore_active:
                self._log("auto_stop_if_necessary :: tilt restore complete")
                self._release_tilt_restore()
                if self._has_tilt_motor():
                    await self._tilt_settle()
                    self._on_tilt_motor_move_complete()
                else:
                    await self._async_handle_command(SERVICE_STOP_COVER)
                if self._tilt_strategy is not None:
                    self._tilt_strategy.snap_trackers_to_physical(
                        self.travel_calc, self.tilt_calc
                    )
                self._last_command = None
                self._moving_tilt_motor = False
                self._moving_tilt = False
                await self._async_persist_position()
                await self._maybe_start_recalibrated_leg()
                return

            if self._pending_travel_target is not None:
                # Tilt pre-step complete — start travel phase
                self._log("auto_stop_if_necessary :: tilt pre-step complete")
                await self._start_pending_travel()
                return

            if self._pending_tilt_target is not None:
                # Travel pre-step complete — start tilt phase
                self._log("auto_stop_if_necessary :: travel pre-step complete")
                await self._start_pending_tilt()
                return

            if self._tilt_strategy is not None:
                self._tilt_strategy.snap_trackers_to_physical(
                    self.travel_calc, self.tilt_calc
                )

            if self._tilt_restore_target is not None:
                # Travel just completed — start tilt restore phase. If the
                # restore target already matches where tilt is (issue #179:
                # leg A always targets 100, which coincides with the default
                # safe_tilt_position, so the dual-motor pre-step already
                # parked tilt exactly at the restore target), _start_tilt_restore
                # returns synchronously without driving a motor or re-arming
                # the auto-updater — this IS the terminal completion of the
                # move and must consume any armed recalibration leg. When a
                # real restore is claimed instead (_tilt_restore_active
                # becomes True), its own eventual completion is handled by
                # the _tilt_restore_active branch above — checking here too
                # would double-fire.
                await self._start_tilt_restore()
                if not self._tilt_restore_active:
                    # Mirrors the other two leg-B dispatch sites (issue #179):
                    # persist before consuming any armed recalibration leg,
                    # for consistency across the three otherwise-parallel
                    # sites. Impact is nil either way — leg B persists on its
                    # own completion — but the asymmetry reads as a bug later
                    # if left alone.
                    await self._async_persist_position()
                    await self._maybe_start_recalibrated_leg()
                return

            current_travel = self.travel_calc.current_position()
            # Endpoint handling (the self-stop skip and the run-on below) is a
            # *travel* concept: it only applies when a travel move reaches a
            # physical limit. A tilt move that merely finishes while the cover is
            # parked at a travel endpoint has driven the motor *off* that limit
            # to articulate the slats, so the motor will NOT self-stop there and
            # must always be stopped explicitly — never given the self-stop skip
            # (issue #142) or the run-on (issue #125).
            endpoint_applies = (
                self._at_endpoint(current_travel) and not self._moving_tilt
            )
            if self._motor_stops_itself():
                # The device drives to the target and holds there on its own
                # (e.g. a wrapped cover commanded via set_cover_position). Any
                # stop we issue here is at best redundant and at worst nudges it
                # off the exact target (a freeze re-commands the calculated, not
                # requested, position). Just settle the tracker.
                self._log("auto_stop_if_necessary :: device self-stops, no relay stop")
            elif self._has_tilt_motor() and self._moving_tilt_motor:
                # The completed movement drove the dedicated tilt motor — settle
                # that motor (skipping the stop at the tilt endpoints), not
                # travel. Without this a tilt move would fall through to the
                # travel stop below and re-pulse the travel relay off a stale
                # _last_command.
                await self._tilt_settle()
                self._on_tilt_motor_move_complete()
            elif endpoint_applies and self._self_stops_at_endpoints():
                # The motor self-stops at its physical limit switch. Sending a
                # stop here is redundant (and for toggle re-pulses → restart),
                # so skip the relay stop and any run-on; just settle the
                # tracker. The run-on (below) is therefore reached only by
                # hardware that does NOT self-stop at its endpoints — switch
                # mode, and pulse with send_endpoint_stop enabled.
                self._log(
                    "auto_stop_if_necessary :: motor self-stops at endpoint"
                    " (position=%d), no relay stop",
                    current_travel,
                )
            elif (
                endpoint_applies
                and self._endpoint_runon_time is not None
                and self._endpoint_runon_time > 0
            ):
                self._log(
                    "auto_stop_if_necessary :: at endpoint (position=%d),"
                    " delaying relay stop by %fs",
                    current_travel,
                    self._endpoint_runon_time,
                )
                self._delay_task = self.hass.async_create_task(
                    self._delayed_stop(self._endpoint_runon_time)
                )
            else:
                await self._async_handle_command(SERVICE_STOP_COVER)
            if endpoint_applies and not self._moving_tilt_motor:
                # endpoint_applies implies _at_endpoint(current_travel), which is
                # False for None, so the position is known here.
                assert current_travel is not None
                self._on_endpoint_reached(int(current_travel))
            self._last_command = None
            self._moving_tilt_motor = False
            self._moving_tilt = False
            await self._async_persist_position()
            await self._maybe_start_recalibrated_leg()

    def _motor_stops_itself(self) -> bool:
        """Return True if the device halts at the target without a stop command.

        Relay-driven covers (the default) must be told to stop when the tracker
        reaches the target, so this is False. Subclasses whose device has native
        position control and stops itself at the commanded position override this
        to True so auto-stop skips the redundant (and potentially target-nudging)
        relay stop.
        """
        return False

    def _self_stops_at_endpoints(self) -> bool:
        """Return True if the motor self-stops at the physical endpoints.

        Roller-shutter motors have internal limit switches that halt the motor
        at fully-open/closed on their own. For modes whose relays are momentary
        or delegated (toggle, pulse, wrapped), the stop we would otherwise send
        at 0%/100% is therefore redundant — and for toggle actively harmful, as
        re-pulsing the direction relay restarts the already-stopped motor. Such
        modes return True so auto-stop skips the relay stop (and run-on) at an
        endpoint while still stopping mid-travel, where nothing self-stops.

        Switch mode overrides this to False: its direction relay is latched ON
        for the whole travel, so reaching an endpoint must still de-energize it.
        """
        return True

    def _supports_stepped_calibration(self) -> bool:
        """Whether the overhead and minimum-movement tests can run on this mode.

        Both restart the motor in the same direction from a stop, which every
        relay-driven mode can do. A mode whose restart-after-stop is a
        reversal overrides this to False.
        """
        return True

    def _at_endpoint(self, position) -> bool:
        """Return True at a travel endpoint (0/100) where endpoint handling
        (self-stop skip or run-on) applies.

        Sequential tilt drives the motor past cover-closed to articulate the
        slats, so it disallows endpoint handling at 0 (``allows_endpoint_runon``).
        """
        return (
            position is not None
            and position in (0, 100)
            and (
                self._tilt_strategy is None
                or self._tilt_strategy.allows_endpoint_runon(position)
            )
        )

    async def _tilt_settle(self) -> None:
        """Stop the dedicated tilt motor at the end of a tilt-motor movement.

        Mirrors the travel endpoint logic: at the tilt endpoints (0%/100%) the
        tilt motor self-stops on its own limit, so the stop is skipped (and for
        toggle a re-pulse would restart it) — except in switch mode, whose
        latched tilt relay must still be de-energized. Mid-tilt always stops.
        """
        current_tilt = (
            self.tilt_calc.current_position() if self._has_tilt_support() else None
        )
        if (
            current_tilt is not None
            and current_tilt in (0, 100)
            and self._self_stops_at_endpoints()
        ):
            self._log(
                "_tilt_settle :: tilt motor self-stops at endpoint (%d), no relay stop",
                current_tilt,
            )
        else:
            await self._send_tilt_stop()

    def _on_tilt_motor_move_complete(self) -> None:
        """Hook: a dedicated-tilt-motor movement finished (settled or skipped).

        Called from ``auto_stop_if_necessary`` after a movement that drove the
        dedicated tilt motor completes, whether self-initiated (right after
        ``_tilt_settle``) or externally triggered. The base class has no tilt
        bookkeeping of its own to clear; toggle-style hardware overrides this
        to clear ``_last_tilt_direction`` so a stale direction can't outlive
        the move that set it (see ``_abandon_active_lifecycle``, which pulses
        a relay keyed off that direction).
        """

    async def _settle_external_endpoint(self) -> None:
        """De-energize any latched relay after an externally-triggered move
        reaches its endpoint.

        Auto-stop skips the relay stop for externally-triggered movements
        (``_self_initiated_movement`` False): the trigger came from outside HA,
        and for momentary modes (pulse/toggle/wrapped) the relay was a brief
        pulse that has already self-released — there is nothing to de-energize,
        so they keep this no-op. Switch mode latches its direction relay ON for
        the whole travel, so it overrides this to turn the relay off (only if
        still on); otherwise the relay stays energized at the endpoint forever.
        """
        return

    def _park_axis_at_limit(self, calc: TravelCalculator, limit: int) -> None:
        """Record an axis at the limit its motor will reach on its own.

        Used when this entity stops tracking a motor it cannot stop (removal
        on hardware that self-stops at its limits). Modes that carry more
        state than the tracker anchor it here too.
        """
        calc.set_position(limit)

    def _settle_axis_after_removal(
        self,
        calc: TravelCalculator,
        *,
        driving: bool,
        fallback_limit: int | None,
    ) -> None:
        """Leave one axis's tracker where the motor will actually be.

        Removal stops every motor it can stop, so an axis is still running
        afterwards only on hardware that halts at its own limits. Never
        driving, stopped by removal, or a device that holds its own target:
        the tracker's own position stands. Otherwise park at the limit in the
        direction of travel — from the tracker if it is travelling, else from
        the last command — or forget the axis when no direction is known.
        """
        if (
            not driving
            or not self._self_stops_at_endpoints()
            or self._motor_stops_itself()
        ):
            calc.stop()
            return
        if calc.is_traveling():
            limit = 100 if calc.travel_direction == TravelStatus.DIRECTION_UP else 0
            self._park_axis_at_limit(calc, limit)
        elif fallback_limit is not None:
            self._park_axis_at_limit(calc, fallback_limit)
        else:
            calc.clear_position()

    def _limit_for_last_command(self) -> int | None:
        if self._last_command == SERVICE_OPEN_COVER:
            return 100
        if self._last_command == SERVICE_CLOSE_COVER:
            return 0
        return None

    def _tilt_limit_for_last_command(self) -> int | None:
        """The tilt limit the command now running heads for, or None.

        The tilt tracker is idle across a deferred start, so the direction can
        only come from the command already at the relay. Inverting
        ``tilt_command_for`` — the same mapping the move used to choose that
        command — keeps strategies whose slats open by driving the motor the
        other way (sequential_open) pointing at the tilt limit rather than the
        motor's.
        """
        if self._last_command is None:
            return None
        strategy = self._tilt_strategy
        if strategy is None:
            return self._limit_for_last_command()
        if self._last_command == strategy.tilt_command_for(True):
            return 0
        if self._last_command == strategy.tilt_command_for(False):
            return 100
        return None

    def _on_endpoint_reached(self, endpoint: int) -> None:
        """Hook: a self-initiated travel move terminated at 0 or 100.

        Base is a no-op. Overridden by modes that must re-anchor internal
        state at a physical limit (e.g. single-button phase tracking).
        """
        return

    async def _delayed_stop(self, delay):
        """Stop the relay after a delay.

        Clears ``_delay_task`` only while it still points at this task: a
        cancel's cleanup runs a loop turn later, by which time a replacement
        run-on may already be registered, and clearing that would hide a
        pending relay stop from _cancel_delay_task and _movement_in_progress.
        """
        self._log("_delayed_stop :: waiting %fs before stopping relay", delay)
        try:
            await sleep(delay)
            self._log("_delayed_stop :: delay complete, stopping relay")
            await self._async_handle_command(SERVICE_STOP_COVER)
            self._last_command = None
        except asyncio.CancelledError:
            self._log("_delayed_stop :: delay cancelled")
            raise
        finally:
            if self._delay_task is asyncio.current_task():
                self._delay_task = None

    async def _stop_travel_relay_if_needed(self, *, travel_was_running: bool) -> None:
        """Send the travel STOP unless it would be a movement command.

        Momentary hardware self-stops at its limits, and a 'stop' pulse to a
        stopped motor is a movement command (#153) or a go-to-favourite (#133).
        Skip when the travel axis never ran under this lifecycle, or when it is
        settled at an endpoint the motor self-stopped at. Switch mode
        (_self_stops_at_endpoints False) always de-energizes.
        """
        if not self._self_stops_at_endpoints():
            await self._async_handle_command(SERVICE_STOP_COVER)
            return
        if not travel_was_running:
            self._log("_stop_travel_relay_if_needed :: travel idle, skipping stop")
            return
        if self._at_endpoint(self.travel_calc.current_position()):
            self._log(
                "_stop_travel_relay_if_needed :: self-stopped at endpoint,"
                " skipping stop"
            )
            return
        await self._async_handle_command(SERVICE_STOP_COVER)

    async def _abandon_active_lifecycle(self):
        """Abandon any active multi-phase tilt lifecycle (pre-step, restore).

        Called at the start of every movement method. If a tilt restore or
        tilt pre-step is in progress, stops all hardware and calculators.
        Always clears the pending restore target so it won't fire after
        the next travel completes.

        Being the one hook every movement entry point funnels through, this is
        also where a new movement claims the epoch — see
        _settle_before_reversing. Tilt counts: on shared-motor strategies tilt
        is driven by the travel motor, so a tilt command must invalidate a
        travel reversal parked in its settle gap just as a travel command does.
        """
        self._supersede_movement()
        # A fresh move must not inherit a relay-feedback arm left set by an
        # earlier operation that armed but never reached _begin_movement (e.g.
        # an endpoint resync). Otherwise a following suppress_start_command
        # redrive — which fires no _send_* to re-arm — would read the stale arm
        # and wait for an ON echo its already-latched relay will never send.
        self._feedback_armed_entity = None
        was_restoring = self._tilt_restore_active
        was_pre_stepping = (
            self._pending_travel_target is not None
            or self._pending_tilt_target is not None
        )
        # Captured before the resets below clear them: the tilt stop at the
        # bottom of this method must reflect whether the tilt motor was
        # actually driven, not whatever _moving_tilt_motor/tilt_calc read
        # after being reset here — an idle-motor pulse off a stale
        # _last_tilt_direction is a #153-class hazard (audit finding B4).
        was_tilt_motor = self._moving_tilt_motor
        was_tilt_traveling = self._has_tilt_support() and self.tilt_calc.is_traveling()
        # Captured before the calculator stops below: the travel stop at the
        # bottom must reflect whether the travel motor was actually driven under
        # this lifecycle. A dual-motor tilt pre-step never starts the travel
        # motor, so its abandon must not pulse a travel relay off a stale
        # _last_command at an idle motor (#153 / #133, audit Task 5B). A pending
        # run-on delay counts as still-driving (any mode with an endpoint run-on
        # arms _delay_task — e.g. pulse — not switch mode only).
        travel_was_running = self.travel_calc.is_traveling() or (
            self._delay_task is not None and not self._delay_task.done()
        )

        # Always clear multi-phase state
        self._clear_multiphase_tilt_state()
        # Each movement entry point funnels through here; default to a travel
        # move and let the tilt paths below opt in.
        self._moving_tilt_motor = False
        self._moving_tilt = False

        if not was_restoring and not was_pre_stepping:
            return

        self._log(
            "_abandon_active_lifecycle :: abandoning %s",
            "tilt restore" if was_restoring else "pre-step",
        )

        self._cancel_startup_delay_task()

        if self.travel_calc.is_traveling():
            self.travel_calc.stop()
        if self._has_tilt_support() and self.tilt_calc.is_traveling():
            self.tilt_calc.stop()
        self.stop_auto_updater()

        await self._stop_travel_relay_if_needed(travel_was_running=travel_was_running)
        # Deliberately still gated on _triggered_externally, unlike
        # async_stop_cover. This route cannot tell which axis reported: the
        # tilt entry points reach it too (async_open_cover_tilt ->
        # _async_move_tilt_to_endpoint -> here), so firing on an external tilt
        # event would echo a stop back at the very relay that reported — which
        # on toggle hardware starts the motor rather than stopping it. Until
        # the axis is threaded this far, suppressing is the safe direction.
        if (
            self._has_tilt_motor()
            and not self._triggered_externally
            and (was_tilt_motor or was_tilt_traveling)
        ):
            await self._send_tilt_stop()

    def _stop_travel_if_traveling(self):
        """Stop cover movement if it's currently traveling."""
        if self.travel_calc.is_traveling():
            self._log("_stop_travel_if_traveling :: stopping cover movement")
            self.travel_calc.stop()
            if self._has_tilt_support() and self.tilt_calc.is_traveling():
                self._log("_stop_travel_if_traveling :: also stopping tilt")
                self.tilt_calc.stop()

    def _handle_stop(self, *, supersede: bool = True):
        """Handle stop.

        ``supersede`` says whether this is a fresh command to halt the cover,
        which claims the movement and so keeps a reversal parked in its settle
        gap from driving afterwards. Every route that halts the cover lands
        here — through _neutralize_tracked_movement for both _stop_hardware
        implementations (CoverTimeBased's and ToggleBaseCover's, which does not
        call super), calibration start, a raw command and a direction change
        at a parked start (_neutralize_parked_move, which stops and returns
        rather than driving on, so it supersedes like a stop), and directly for
        the known-position declarations.

        Passive routes must pass ``supersede=False``: a wrapped cover reporting
        its settled position snaps via set_known_position, and a switch-mode
        relay's unmarked off (a hardware interlock clearing the opposite relay)
        calls async_stop_cover. Both can arrive inside the settle window — the
        wrapped self-echo suppressors are keyed on is_traveling(), which the
        reversal has already cleared — and treating them as supersessions would
        silently drop the user's move, or freeze the tracker while the motor
        runs. So must the stop a reversal issues as its own prelude, which would
        otherwise cancel the very movement it is starting.

        The caller has to say so because _triggered_externally cannot: it is
        ambient instance state held for the whole external call, settle gap
        included, so inferring from it read a genuine stop landing in that gap
        as a device echo and dropped it.
        """
        if supersede:
            self._supersede_movement()
        self._clear_multiphase_tilt_state()

        if self.travel_calc.is_traveling():
            self._log("_handle_stop :: button stops cover movement")
            self.travel_calc.stop()
            self.stop_auto_updater()

        if self._has_tilt_support() and self.tilt_calc.is_traveling():
            self._log("_handle_stop :: button stops tilt movement")
            self.tilt_calc.stop()
            self.stop_auto_updater()

    def _neutralize_tracked_movement(self, *, supersede: bool = True) -> None:
        """Park the tracker and cancel deferred starts, without touching a relay.

        The prelude every route that takes the movement away from the tracker
        shares: a deferred start left armed would later drive the motor, or fire
        a relay stop, against whatever took over.

        See _handle_stop for ``supersede``.
        """
        self._cancel_startup_delay_task()
        self._cancel_delay_task()
        self._handle_stop(supersede=supersede)

    async def _start_tilt_pre_step(
        self, tilt_target, travel_target, travel_command, restore_target
    ):
        """Move tilt to safe position before travel (dual_motor).

        Sends the tilt motor command and starts tilt_calc. When tilt reaches
        target, auto_stop_if_necessary will call _start_pending_travel to
        begin the actual cover travel.
        """
        current_tilt = self.tilt_calc.current_position()
        self._log(
            "_start_tilt_pre_step :: tilt %s→%d, pending travel→%d (%s)",
            current_tilt,
            tilt_target,
            travel_target,
            travel_command,
        )
        closing_tilt = tilt_target < current_tilt
        self._require_movement_target_available(
            self._tilt_movement_target(
                SERVICE_CLOSE_COVER if closing_tilt else SERVICE_OPEN_COVER
            )
        )
        self._pending_travel_target = travel_target
        self._pending_travel_command = travel_command
        self._tilt_restore_target = restore_target

        if not self._triggered_externally:
            if closing_tilt:
                await self._send_tilt_close()
            else:
                await self._send_tilt_open()

        if self._removed:
            return
        self.tilt_calc.start_travel(tilt_target)
        self.start_auto_updater()

    async def _start_pending_travel(self):
        """Start travel after tilt pre-step completes (dual_motor).

        Called by auto_stop_if_necessary when tilt_calc reaches the safe
        position. For self-initiated moves: stops the tilt motor and sends
        the travel command. For external triggers (where hardware is doing
        the multi-phase motion itself), only updates the integration's
        trackers — the relays are left to the hardware.

        The origin gate is the instance flag ``_self_initiated_movement``,
        NOT ``_triggered_externally``: this continuation runs on the
        auto-updater's own task (auto_updater_hook schedules it via
        hass.async_create_task), and ``_triggered_externally`` is task-scoped,
        so it is always False here regardless of how the move began.
        ``_self_initiated_movement`` is set once at the entry point and
        survives across the phase boundary, so it is the correct carrier.
        """
        target = self._pending_travel_target
        command = self._pending_travel_command
        assert target is not None and command is not None
        self._pending_travel_target = None
        self._pending_travel_command = None

        self._log(
            "_start_pending_travel :: starting travel to %d (%s)",
            target,
            command,
        )

        self._moving_tilt_motor = False
        if self._self_initiated_movement:
            # Stop tilt motor and send travel command.
            await self._send_tilt_stop()
            await self._async_handle_command(command)
        self._last_command = command
        self._begin_movement(
            target,
            None,
            self.travel_calc,
            None,
            self._travel_startup_delay,
        )

    async def _start_travel_pre_step(self, travel_target, tilt_target, tilt_command):
        """Move cover to allowed position before tilt (dual_motor).

        Sends the travel motor command and starts travel_calc. When travel
        reaches target, auto_stop_if_necessary will call _start_pending_tilt
        to begin the actual tilt movement.
        """
        current_pos = self.travel_calc.current_position()
        self._log(
            "_start_travel_pre_step :: travel %s→%d, pending tilt→%d (%s)",
            current_pos,
            travel_target,
            tilt_target,
            tilt_command,
        )
        closing = travel_target < current_pos
        command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
        self._require_movement_target_available(self._movement_target(closing))
        self._pending_tilt_target = tilt_target
        self._pending_tilt_command = tilt_command
        self._last_command = command
        await self._async_handle_command(command)

        self._begin_movement(
            travel_target,
            None,
            self.travel_calc,
            None,
            self._travel_startup_delay,
        )

    async def _start_pending_tilt(self):
        """Start tilt after travel pre-step completes (dual_motor).

        Called by auto_stop_if_necessary when travel_calc reaches the
        allowed position. For self-initiated moves: stops the travel motor,
        sends the tilt command, and starts tracking with tilt_calc. For
        external triggers (where the hardware is driving the multi-phase
        motion itself), only starts tilt tracking — the relays are left to
        the hardware.

        The origin gate is the instance flag ``_self_initiated_movement``,
        NOT ``_triggered_externally``: this continuation runs on the
        auto-updater's own task, and ``_triggered_externally`` is task-scoped,
        so it is always False here regardless of how the move began.
        ``_self_initiated_movement`` is set once at the entry point and
        survives across the phase boundary, so it is the correct carrier.
        """
        target = self._pending_tilt_target
        command = self._pending_tilt_command
        assert target is not None and command is not None
        self._pending_tilt_target = None
        self._pending_tilt_command = None

        self._log(
            "_start_pending_tilt :: starting tilt to %d (%s)",
            target,
            command,
        )

        # Stop travel motor
        if self._self_initiated_movement:
            await self._async_handle_command(SERVICE_STOP_COVER)

        # Send tilt command and start tracking
        self._moving_tilt_motor = True
        closing_tilt = command == SERVICE_CLOSE_COVER
        if self._self_initiated_movement:
            if closing_tilt:
                await self._send_tilt_close()
            else:
                await self._send_tilt_open()
        self._last_command = command
        self._begin_movement(
            target,
            None,
            self.tilt_calc,
            None,
            self._tilt_startup_delay,
        )

    async def _start_tilt_restore(self):
        """Restore tilt to its pre-movement position.

        For dual_motor: stops travel motor, starts tilt motor.
        For shared motor (inline): reverses main motor direction.
        """
        restore_target = self._tilt_restore_target
        self._tilt_restore_target = None
        if restore_target is None:
            return

        current_tilt = self.tilt_calc.current_position()
        if current_tilt is None or current_tilt == restore_target:
            self._log(
                "_start_tilt_restore :: no restore needed (current=%s, target=%s)",
                current_tilt,
                restore_target,
            )
            # Restore only runs after a travel phase, so the travel axis did run;
            # the endpoint check inside the helper skips the stop when the motor
            # self-stopped at its limit (a stop pulse there is a #153/#133 move).
            await self._stop_travel_relay_if_needed(travel_was_running=True)
            self._last_command = None
            return

        self._log(
            "_start_tilt_restore :: restoring tilt from %d%% to %d%%",
            current_tilt,
            restore_target,
        )

        closing = restore_target < current_tilt

        # Everything below runs on the auto-updater's background task, so every
        # await yields the event loop and a user STOP or a new movement command
        # can interleave. Mark the restore active *before* the first await so
        # those paths (async_stop_cover -> _handle_stop, other moves ->
        # _abandon_active_lifecycle) recognise it, stop the motor, and clear the
        # flag; we then re-check the flag after each await and bail so we never
        # (re)start or keep tracking a motor the user just stopped. The
        # auto-updater stays unsubscribed for this whole window (stopped when
        # travel reached its target, re-armed only at the tail below), so no
        # re-entrant auto_stop_if_necessary can take the restore-complete branch
        # mid-startup — keep it that way if this ever moves.
        epoch = self._claim_tilt_restore()

        if self._tilt_strategy.uses_tilt_motor:
            # Dual motor: stop travel, then start the separate tilt motor. The
            # travel motor self-stopped if travel just reached an endpoint, so
            # gate the stop (a pulse there re-opens the cover untracked — #153).
            await self._stop_travel_relay_if_needed(travel_was_running=True)
            # Clear only after the stop helper uses _last_command to pick its
            # relay. Tilt now owns the motion; a stale travel command would
            # make a mid-restore tilt command pulse the parked travel motor.
            self._last_command = None
            if self._tilt_restore_superseded(epoch):
                self._log("_start_tilt_restore :: cancelled before tilt motor start")
                return
            if closing:
                await self._send_tilt_close()
            else:
                await self._send_tilt_open()
        else:
            # Shared motor (inline tilt — the only strategy that both restores
            # tilt and drives it via the travel motor): the travel motor is
            # still running from the travel phase and the restore reverses it.
            # Stop and let the motor settle before commanding the opposite
            # direction (issue #147) — an instant reversal leaves a short
            # restore pulse's stop command dropped by the relay, so the cover
            # overruns to its physical endpoint.
            await self._async_handle_command(SERVICE_STOP_COVER)
            if self._tilt_restore_superseded(epoch):
                # Cancelled while stopping — bail before the settle delay so we
                # don't block the background task for a dead restore.
                self._log("_start_tilt_restore :: cancelled before settle delay")
                return
            await self._direction_change_delay()
            if self._tilt_restore_superseded(epoch):
                self._log("_start_tilt_restore :: cancelled during settle delay")
                return
            command = self._tilt_strategy.tilt_command_for(closing)
            await self._async_handle_command(command)

        if self._tilt_restore_superseded(epoch):
            # The motor is already energized: whoever cancelled us sent their
            # stop while we were awaiting this turn-on, so theirs went out
            # first and ours landed after it. Nothing else will take it down —
            # we are the only one that knows it went up — and on a latching
            # relay that means a cover driving to its endpoint untracked.
            self._log("_start_tilt_restore :: cancelled during motor start, stopping")
            await self._stop_restore_motor()
            return
        self.tilt_calc.start_travel(restore_target)
        self.start_auto_updater()

    async def _maybe_start_recalibrated_leg(self) -> None:
        """Run the second leg of a recalibrated move, if one is armed (#179).

        Leg A drove the cover to a physical endpoint, so the tracker is now
        true. Wait out any endpoint run-on and the motor settle gap, then make
        the move the user actually asked for.
        """
        target = self._pending_recalibrated_target
        if target is None:
            return
        axis = self._pending_recalibrated_axis
        armed_epoch = self._recalibration_epoch
        # Clear unconditionally, epoch match or not: a stale pending target
        # left behind by a superseded leg A must not linger forever waiting
        # for an epoch that will never come again.
        self._disarm_recalibrated_leg()
        if self._movement_epoch != armed_epoch:
            return

        # Leg A may have armed a delayed relay stop (endpoint_runon_time).
        # Settling while the relay is still energized would make the rest gap a
        # fiction, so let the run-on finish before starting the clock.
        #
        # asyncio.wait, not a bare `await delay_task`: a bare await makes
        # delay_task this coroutine's own suspension point, so cancelling
        # *this* task (e.g. the per-tick task from hass.async_create_task,
        # torn down on entity removal or HA shutdown) would cancel delay_task
        # right along with it -- killing the pending _delayed_stop before it
        # de-energises the relay, leaving it latched on. asyncio.wait's own
        # internal waiter absorbs that instead: delay_task keeps running to
        # completion regardless, while a cancellation of this task still
        # propagates out normally through the await.
        delay_task = self._delay_task
        if delay_task is not None and not delay_task.done():
            await asyncio.wait({delay_task})

        # The run-on wait above is itself an await — a stop or a new command
        # can land while it is in flight, and would otherwise go unnoticed:
        # _settle_before_reversing captures self._movement_epoch on entry and
        # compares it to itself after its OWN sleep, so it only ever catches a
        # supersede landing during its own wait — never one that already
        # landed during the run-on wait above, before settle even started
        # (issue #179). Re-check explicitly.
        if self._movement_epoch != armed_epoch:
            self._log("_maybe_start_recalibrated_leg :: superseded during run-on wait")
            return

        # auto_stop_if_necessary cleared _last_command, so leg B does not read
        # itself as a direction change and would skip DIRECTION_CHANGE_DELAY --
        # reversing the motor with no rest. Settle explicitly.
        if not await self._settle_before_reversing():
            self._log("_maybe_start_recalibrated_leg :: superseded during settle")
            return

        self._log("_maybe_start_recalibrated_leg :: %s leg to %d%%", axis, target)
        try:
            if axis == "tilt":
                await self.set_tilt_position(target, recalibrate=False)
            else:
                await self.set_position(target, recalibrate=False)
        except HomeAssistantError as err:
            # This runs on a fresh per-tick task from hass.async_create_task,
            # not literally "the auto-updater" — stop_auto_updater() has
            # already unsubscribed the interval timer by the time we get
            # here, so an escape would not take that down. It would still
            # surface only as a noisy unhandled-task-exception log, and worse,
            # silently abandon the move the user asked for. The cover is
            # parked at a true endpoint (leg A's), so leaving it there is
            # safe and correctly tracked — warn instead of losing it silently.
            _LOGGER.warning(
                "(%s) recalibrated move to %d%% failed: %s",
                self.entity_id,
                target,
                err,
            )

    async def _stop_restore_motor(self) -> None:
        """Take down whichever motor the restore energized.

        Only when nothing is tracking it. Superseders come in two kinds: a
        stop, which leaves no movement behind and so leaves our turn-on running
        with nobody to switch it off — the case this exists for — and a new
        *movement*, which abandoned the lifecycle and then energized a motor of
        its own. Stopping in the second case kills the replacement's motor
        while its calculator animates on, which is the same tracker-
        confidently-wrong desync approached from the other side. A live
        calculator is exactly the difference between the two.

        _tilt_settle rather than a bare stop because at 0%/100% the motor has
        already stopped on its own limit switch and re-pulsing a momentary
        relay there would start it moving again. A path added to avoid leaving
        a motor running must not do that either.
        """
        if self.travel_calc.is_traveling() or (
            self._has_tilt_support() and self.tilt_calc.is_traveling()
        ):
            self._log("_stop_restore_motor :: a movement is tracking, leaving it alone")
            return
        if self._has_tilt_motor():
            await self._tilt_settle()
            self._on_tilt_motor_move_complete()
        else:
            await self._async_handle_command(SERVICE_STOP_COVER)
