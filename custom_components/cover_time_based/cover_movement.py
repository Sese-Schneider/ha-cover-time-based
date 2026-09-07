"""Movement orchestration mixin for time-based cover entities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
    STATE_UNAVAILABLE,
)
from homeassistant.exceptions import HomeAssistantError

from .recalibration import RecalibrationPlan
from .tilt_strategies import SequentialTilt
from .tilt_strategies.planning import (
    calculate_pre_step_delay,
    extract_coupled_tilt,
    extract_coupled_travel,
    has_travel_pre_step,
)

if TYPE_CHECKING:
    from .cover_host import _CoverHost

    _MixinBase = _CoverHost
else:
    _MixinBase = object

_LOGGER = logging.getLogger(__name__)


class MovementMixin(_MixinBase):
    """Mixin providing movement orchestration for CoverTimeBased."""

    async def _async_move_to_endpoint(self, target, *, suppress_start_command=False):
        """Move cover to an endpoint (0=fully closed, 100=fully open).

        ``suppress_start_command`` drives the tracker without touching a relay,
        for the one caller that knows the motor is ALREADY running the
        direction this move would command: a forced full re-drive
        (_force_full_redrive) issued while the cover travels that way already.
        Re-issuing the start command there is the hazard the plain
        ``set_position`` path guards with ``already_moving_same_dir`` — on
        toggle (same-button) hardware a second rising edge on the driving relay
        STOPS the motor. This cannot be detected from inside here: the caller's
        seed sets travel_calc to the opposite endpoint before we run, which
        erases the "is travelling" evidence entirely (the same trap the
        dual-motor tilt reversal works around by evaluating before the seed).
        Hence a flag decided by the caller rather than a check here. The motor
        keeps running toward the endpoint and stalls at its limit, which is
        exactly what a forced re-drive wants; the startup delay is dropped too,
        since the motor is already up to speed.
        """
        # NB: _self_initiated_movement is assigned only once this call is
        # committed to acting, past the startup-delay early-returns below.
        # A same-direction command that reaches an already-active startup delay
        # (e.g. an underlying's lagged echo of our own move, issue #165) returns
        # from the "not restarting" branch without touching the flag, so it
        # cannot flip an in-flight self-initiated move to "external" and drop
        # its auto-stop. The sequential-redirect below delegates to
        # set_tilt_position, which sets the flag itself.

        # External close on sequential hardware runs the full journey:
        # the motor drives all the way past cover-closed to the articulated
        # extreme (tilt=100 on sequential_open, tilt=0 on sequential_close).
        # Redirect to set_tilt_position so tracking plans both phases as
        # [TravelTo(0), TiltTo(articulated)].
        #
        # Open externally is already handled correctly by the default plan
        # (plan_move_position restores tilt to implicit before travel when
        # starting from the articulated state).
        if (
            target == 0
            and self._triggered_externally
            and isinstance(self._tilt_strategy, SequentialTilt)
        ):
            articulated = 100 - self._tilt_strategy.implicit_tilt_during_travel
            self._log(
                "_async_move_to_endpoint :: external close on sequential → "
                "set_tilt_position(%d) for full-journey tracking",
                articulated,
            )
            await self.set_tilt_position(articulated)
            return

        # Capture before _abandon_active_lifecycle resets it — see
        # _release_displaced_tilt_motor.
        was_tilt_motor_move = self._moving_tilt_motor
        await self._abandon_active_lifecycle()

        closing = target == 0
        command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
        opposite_command = SERVICE_OPEN_COVER if closing else SERVICE_CLOSE_COVER

        # Check startup delay conflicts BEFORE position check, since during
        # startup delay the position hasn't started changing yet.
        if self._startup_delay_task and not self._startup_delay_task.done():
            if self._last_command == opposite_command:
                self._log(
                    "_async_move_to_endpoint :: direction change, stopping the parked move"
                )
                await self._neutralize_parked_move()
                await self._async_handle_command(SERVICE_STOP_COVER)
                self._last_command = None
                await self._release_displaced_tilt_motor(was_tilt_motor_move)
                # Silent: no travel started. _movement_started must read this
                # as "not started" — see its docstring.
                return
            else:
                self._log(
                    "_async_move_to_endpoint :: startup delay already active, not restarting"
                )
                await self._release_displaced_tilt_motor(was_tilt_motor_move)
                # Silent: no travel started. _movement_started must read this
                # as "not started" — see its docstring.
                return

        # Committed to acting: now claim the movement's bookkeeping. Unlike the
        # tilt funnel (_async_move_tilt_to_endpoint, which sets this flag then
        # runs a post-flag in-motion reversal), the travel funnel's only
        # direction change is the startup-delay cancel above, which returns
        # before this line — so on that path _self_initiated_movement is left
        # stale. Benign: the cover is fully stopped there and the next funnel
        # call overwrites the flag.
        self._self_initiated_movement = not self._triggered_externally

        current = self.travel_calc.current_position()
        if current is not None and current == target:
            # Resync: send command + endpoint run-on even though tracker
            # says we're already there. Physical cover may need resyncing.
            self._cancel_delay_task()
            self._last_command = command
            await self._async_handle_command(command)
            if self._self_stops_at_endpoints() and self._at_endpoint(target):
                # The re-drive above resyncs the cover physically; the motor
                # self-stops at its limit. A stop here is redundant (and for
                # toggle re-pulses → restart), so skip it and any run-on.
                self._log(
                    "_async_move_to_endpoint :: motor self-stops at endpoint,"
                    " no relay stop"
                )
            elif (
                self._endpoint_runon_time is not None and self._endpoint_runon_time > 0
            ):
                self._delay_task = self.hass.async_create_task(
                    self._delayed_stop(self._endpoint_runon_time)
                )
            else:
                await self._async_handle_command(SERVICE_STOP_COVER)
            await self._release_displaced_tilt_motor(was_tilt_motor_move)
            # Silent: a relay resync fires here, but travel_calc never enters
            # "traveling" — _movement_started must still read this as "not
            # started". Not reachable from _force_full_redrive (it seeds the
            # opposite endpoint first, so current never equals target here),
            # but a future caller of this method directly would hit it.
            return

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)

        if current is None:
            # Position unknown — assume opposite endpoint so full travel occurs
            current = 100 if closing else 0
            self.travel_calc.update_position(current)

        travel_distance = abs(target - current)
        travel_time = self._require_travel_time(closing)
        movement_time = (travel_distance / 100.0) * travel_time

        self._log(
            "_async_move_to_endpoint :: target=%d, travel_distance=%f%%, movement_time=%fs",
            target,
            travel_distance,
            movement_time,
        )

        self._last_command = command

        tilt_target = None
        pre_step_delay = 0.0
        # Plan tilt for every trigger including external. Even when the cover
        # motor is externally controlled, the hardware itself is expected to
        # move tilt to safe before travel (interlock behavior); tracking the
        # pre-step keeps the integration's tilt_calc in sync with reality
        # without needing snap_trackers_to_physical to "correct" the tracker
        # at stop time. The pre-step phase (_start_tilt_pre_step /
        # _start_travel_pre_step) runs on the handler's own task and skips
        # relay firing on _triggered_externally; the continuation phase
        # (_start_pending_travel / _start_pending_tilt) runs on the
        # auto-updater's task and skips on _self_initiated_movement — the
        # instance flag that survives across the phase boundary, unlike the
        # task-scoped _triggered_externally. Either way the integration only
        # mirrors the physical motion in its calculators for external moves.
        current_tilt = (
            self.tilt_calc.current_position() if self._tilt_strategy else None
        )
        self._require_movement_target_available(self._movement_target(closing))
        tilt_target, pre_step_delay, started = await self._plan_tilt_for_travel(
            target, command, current, current_tilt
        )
        if started:
            return

        # No pre-step took over: release tilt before energising the travel relay.
        await self._release_displaced_tilt_motor(was_tilt_motor_move)

        if not suppress_start_command:
            await self._async_handle_command(command)
        coupled_calc = self.tilt_calc if tilt_target is not None else None
        self._begin_movement(
            target,
            tilt_target,
            self.travel_calc,
            coupled_calc,
            None if suppress_start_command else self._travel_startup_delay,
            pre_step_delay,
        )

    async def _async_move_tilt_to_endpoint(
        self, target, *, suppress_start_command=False
    ):
        """Move tilt to an endpoint (0=fully closed, 100=fully open).

        ``suppress_start_command`` is the tilt-axis counterpart of the travel
        funnel's flag — see _async_move_to_endpoint. Same caller
        (_force_full_tilt_redrive), same reason: its seed erases the evidence,
        so the decision has to be made before the drive.
        """
        # As in _async_move_to_endpoint: assign _self_initiated_movement only
        # once committed to acting, past the "startup delay already active, not
        # restarting" early-return below, so a same-direction command reaching
        # an active startup delay can't flip an in-flight self-initiated move to
        # "external". _abandon_active_lifecycle does not read the flag.
        # Capture before _abandon_active_lifecycle resets it — see
        # _stop_displaced_movement_for_tilt.
        was_tilt_motor_move = self._moving_tilt_motor
        await self._abandon_active_lifecycle()

        closing = target == 0
        if self._tilt_strategy is not None:
            command = self._tilt_strategy.tilt_command_for(closing)
            opposite_command = self._tilt_strategy.tilt_command_for(not closing)
        else:
            command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
            opposite_command = SERVICE_OPEN_COVER if closing else SERVICE_CLOSE_COVER

        if self._startup_delay_task and not self._startup_delay_task.done():
            if self._last_command == opposite_command:
                self._log(
                    "_async_move_tilt_to_endpoint :: direction change, stopping the parked move"
                )
                await self._neutralize_parked_move()
                # Mirror the travel counterpart: a direction change at a parked
                # move stops the axis and returns — a second press then drives
                # the new direction. Route the stop through the axis-aware
                # helper so a dedicated tilt motor is not stopped via a travel
                # STOP off a stale _last_command (#153).
                await self._stop_displaced_movement_for_tilt(was_tilt_motor_move)
                self._last_command = None
                # Silent: no tilt drive started. _movement_started must read
                # this as "not started" — see its docstring.
                return
            else:
                self._log(
                    "_async_move_tilt_to_endpoint :: startup delay already active, not restarting"
                )
                # Silent: no tilt drive started. _movement_started must read
                # this as "not started" — see its docstring.
                return

        # Committed to acting (a direction change above falls through to here):
        # now claim the movement's bookkeeping.
        self._self_initiated_movement = not self._triggered_externally

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)
            if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
                await self._send_tilt_stop()

        self._stop_travel_if_traveling()

        current_tilt = self.tilt_calc.current_position()
        if current_tilt is not None and current_tilt == target:
            if self.tilt_calc.is_traveling():
                # The animation is momentarily sitting on the target while still
                # travelling away from it (a reversal landing on the endpoint it
                # is leaving). A press for that endpoint is a user stop, not a
                # no-op — the old early-return left the motor running.
                await self.async_stop_cover(tilt_axis_reported=False)
            # Silent either way: no tilt drive started. _movement_started
            # must read this as "not started" — see its docstring.
            return

        # In-motion reversal: the new tilt direction opposes the tilt already in
        # flight. A reversal is never a single step — stop the axis, let it come
        # to rest (settle gap), then drive the other way (#147/#153). Bail if a
        # stop or newer target claimed the movement inside the gap. Only for
        # self-driven moves: an external reversal was already stopped-and-turned
        # by the hardware, so firing a stop here would just mark phantom relay
        # echoes and swallow the user's next press — we only retrack it.
        if (
            not self._triggered_externally
            and self.tilt_calc.is_traveling()
            and self.tilt_calc.is_closing() != closing
        ):
            self._log(
                "_async_move_tilt_to_endpoint :: in-motion reversal, stop + settle"
            )
            self.tilt_calc.stop()
            if self.travel_calc.is_traveling():
                self.travel_calc.stop()
            self.stop_auto_updater()
            await self._stop_displaced_movement_for_tilt(was_tilt_motor_move)
            if not await self._settle_before_reversing():
                # Silent: superseded mid-settle, both calcs already stopped
                # above. _movement_started must read this as "not started" —
                # see its docstring.
                return
            current_tilt = self.tilt_calc.current_position()
            if current_tilt is not None and current_tilt == target:
                # Silent: settled exactly at target, nothing left to drive.
                # _movement_started must read this as "not started" — see its
                # docstring.
                return

        if current_tilt is None:
            current_tilt = 100 if closing else 0
            self.tilt_calc.update_position(current_tilt)

        tilt_distance = abs(target - current_tilt)
        tilt_time = self._tilting_time_close if closing else self._tilting_time_open
        movement_time = (tilt_distance / 100.0) * tilt_time

        travel_target = None
        pre_step_delay = 0.0
        needs_travel_pre_step = False
        if self._tilt_strategy is not None:
            current_pos = self.travel_calc.current_position()
            if current_pos is not None:
                steps = self._tilt_strategy.plan_move_tilt(
                    target, current_pos, current_tilt
                )
                travel_target = extract_coupled_travel(steps)
                pre_step_delay = calculate_pre_step_delay(
                    steps, self._tilt_strategy, self.tilt_calc, self.travel_calc
                )
                if self._tilt_strategy.uses_tilt_motor and has_travel_pre_step(steps):
                    needs_travel_pre_step = True

        self._log(
            "_async_move_tilt_to_endpoint :: target=%d, tilt_distance=%f%%,"
            " movement_time=%fs, travel_pos=%s, travel_pre_step=%s",
            target,
            tilt_distance,
            movement_time,
            travel_target if travel_target is not None else "N/A",
            needs_travel_pre_step,
        )

        self._require_movement_target_available(self._tilt_movement_target(command))
        # The travel pre-step below isn't covered by the tilt gate above — see
        # _require_movement_target_available.
        if needs_travel_pre_step and travel_target is not None:
            await self._start_travel_pre_step(travel_target, target, command)
            return

        self._last_command = command
        # Committed past the no-op return above — mark this as a tilt move so it
        # doesn't run on at a travel endpoint (#125); see set_tilt_position.
        self._moving_tilt = True
        if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
            self._moving_tilt_motor = True
            # Externally triggered moves only track — the relay is already
            # driven from outside HA, and re-firing it here would turn the
            # opposite relay off a second time (the observe-path interlock in
            # _handle_external_tilt_state_change already did), double-marking
            # its pending echo and swallowing the user's next press. Mirrors
            # the _async_handle_command guard the non-tilt-motor branch uses.
            if not self._triggered_externally and not suppress_start_command:
                if closing:
                    await self._send_tilt_close()
                else:
                    await self._send_tilt_open()
        elif not suppress_start_command:
            await self._async_handle_command(command)
        self._begin_movement(
            target,
            travel_target,
            self.tilt_calc,
            self.travel_calc,
            None if suppress_start_command else self._tilt_startup_delay,
            pre_step_delay,
        )

    async def set_position(self, position, *, recalibrate: bool = True):
        """Move cover to a designated position.

        ``recalibrate`` is passed False by exactly one caller,
        ``_maybe_start_recalibrated_leg`` running leg B of a recalibrated
        move (issue #179), to stop this call from arming a leg of its own on
        top of one that already ran. It has a second, less obvious
        consequence: it also exempts the move from ``min_movement_time`` (see
        ``_is_movement_too_short``'s ``is_recalibrated_leg`` parameter, which
        is fed ``not recalibrate``) — leg A has already driven the motor a
        full travel, so leg B's own pulse is the point of the operation, not
        a redundant nudge to skip. A future caller passing ``recalibrate=False``
        for an unrelated reason would silently get that exemption too.
        """
        plan = self._recalibration_plan(recalibrate, position, axis="travel")
        if plan is RecalibrationPlan.TWO_LEG:
            # Leg A always drives OPEN (the fully-open datum), so it only
            # reverses an in-flight movement that is currently closing.
            # Stop and settle first if so (issue #179) — see
            # _stop_and_settle_before_recalibration_drive.
            if not await self._stop_and_settle_before_recalibration_drive(
                SERVICE_OPEN_COVER
            ):
                return
            # Arm only AFTER the drive, never before. _start_recalibration_drive
            # -> _force_full_redrive -> _async_move_to_endpoint funnels through
            # _abandon_active_lifecycle, whose first line is _supersede_movement()
            # (bumps _movement_epoch). _arm_recalibrated_leg stamps
            # _recalibration_epoch from self._movement_epoch, so arming before
            # the drive would capture the pre-bump epoch — leg A's own
            # completion would then read as a newer, unrelated movement and the
            # epoch check in _maybe_start_recalibrated_leg would silently drop
            # leg B.
            if await self._start_recalibration_drive("travel"):
                self._arm_recalibrated_leg(position, "travel")
                return
            self._log(
                "set_position :: recalibration leg did not start, moving directly"
            )
        elif plan is RecalibrationPlan.FORCED_ENDPOINT:
            # position is 0 or 100: driving there IS the recalibration, but
            # only when it is actually forced to cover the full travel
            # (issue #179 finding 3) rather than trusting the believed
            # position for an ordinary timed move. There is no second leg to
            # arm here — the endpoint target itself is the whole move — so
            # reuse _start_recalibration_drive purely for its snapshot/
            # rollback and not-started handling: _force_full_redrive can
            # silently fail to start (e.g. a same-direction startup delay
            # already active), and that path must not leave the tracker
            # seeded at a fabricated endpoint.
            #
            # Unlike leg A, this drive can reverse either way — target=0
            # drives CLOSE, target=100 drives OPEN — so stop and settle
            # first if it would (issue #179).
            endpoint_command = (
                SERVICE_CLOSE_COVER if position == 0 else SERVICE_OPEN_COVER
            )
            if not await self._stop_and_settle_before_recalibration_drive(
                endpoint_command
            ):
                return
            if await self._start_recalibration_drive("travel", target=position):
                return
            self._log(
                "set_position :: forced endpoint redrive did not start, moving directly"
            )
        self._self_initiated_movement = not self._triggered_externally
        # Capture before _abandon_active_lifecycle resets it — see
        # _release_displaced_tilt_motor.
        was_tilt_motor_move = self._moving_tilt_motor
        await self._abandon_active_lifecycle()
        current = self.travel_calc.current_position()
        target = position
        self._log(
            "set_position :: current: %s, target: %d",
            current if current is not None else "None",
            target,
        )

        if current is None:
            # Position unknown — assume opposite endpoint so full travel occurs
            closing = target <= 50
            command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
            current = 100 if closing else 0
            self.travel_calc.update_position(current)
        elif target < current:
            command = SERVICE_CLOSE_COVER
        elif target > current:
            command = SERVICE_OPEN_COVER
        else:
            await self._release_displaced_tilt_motor(was_tilt_motor_move)
            return

        closing = command == SERVICE_CLOSE_COVER

        should_proceed, is_direction_change = await self._handle_pre_movement_checks(
            command
        )
        if not should_proceed:
            await self._release_displaced_tilt_motor(was_tilt_motor_move)
            return

        # A shared-motor (inline/sequential) tilt move drives the same physical
        # motor as travel, with only tilt_calc traveling. Dual-motor tilt is
        # excluded — its tilt motor is independent of travel. Direction
        # comparability holds because a shared-motor tilt move set
        # _last_command to the motor direction it drives (tilt_command_for).
        shared_motor_tilt_traveling = (
            self._has_tilt_support()
            and not self._tilt_strategy.uses_tilt_motor
            and self.tilt_calc.is_traveling()
        )

        # A running dedicated tilt motor never reaches this branch:
        # shared_motor_tilt_traveling excludes uses_tilt_motor strategies by
        # construction, and every tilt-motor entry point stops travel_calc on
        # its way in — so was_tilt_motor_move implies neither condition holds.
        if is_direction_change and (
            self.travel_calc.is_traveling() or shared_motor_tilt_traveling
        ):
            self._log("set_position :: stopping active travel movement")
            self.travel_calc.stop()
            self.stop_auto_updater()
            if self._has_tilt_support() and self.tilt_calc.is_traveling():
                self.tilt_calc.stop()
            await self._async_handle_command(SERVICE_STOP_COVER)
            if not await self._settle_before_reversing():
                return
            current = self.travel_calc.current_position()
            if target == current:
                return
            # Travel was live when we entered this branch, so the tracker holds
            # a known position after the settle.
            assert current is not None

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)

        travel_time = self._require_travel_time(closing)
        movement_time = (abs(target - current) / 100.0) * travel_time

        if self._is_movement_too_short(
            movement_time,
            target,
            current,
            "set_position",
            is_recalibrated_leg=not recalibrate,
        ):
            await self._release_displaced_tilt_motor(was_tilt_motor_move)
            return

        self._last_command = command

        # If the cover is already travelling the right way, the motor is
        # running and only the stop target needs to change. Re-issuing the
        # start command would, in toggle mode, pulse the direction switch a
        # second time and stop the motor — desyncing it from the position
        # tracker (a later auto-stop pulse then restarts it and runs the cover
        # to the endpoint). Tilt coupling is still recomputed below for the new
        # target before we retarget.
        already_moving_same_dir = not is_direction_change and (
            self.travel_calc.is_traveling() or shared_motor_tilt_traveling
        )

        current_tilt = (
            self.tilt_calc.current_position() if self._tilt_strategy else None
        )
        # A tilt pre-step started here returns before the gate below — see
        # _require_movement_target_available.
        tilt_target, pre_step_delay, started = await self._plan_tilt_for_travel(
            target, command, current, current_tilt
        )
        if started:
            return

        # No pre-step took the tilt motor over — see _async_move_to_endpoint's
        # equivalent site.
        await self._release_displaced_tilt_motor(was_tilt_motor_move)

        coupled_calc = self.tilt_calc if tilt_target is not None else None

        # Drive the motor toward the target, then begin tracking. When already
        # moving the right way the motor is left running and only the tracker is
        # retargeted (no startup delay re-applied). _command_position_move is the
        # seam subclasses override when the device has native position control.
        if already_moving_same_dir:
            self._log("set_position :: retargeting active movement to %d", target)
        await self._command_position_move(target, command, already_moving_same_dir)
        startup_delay = None if already_moving_same_dir else self._travel_startup_delay
        self._begin_movement(
            target,
            tilt_target,
            self.travel_calc,
            coupled_calc,
            startup_delay,
            pre_step_delay,
        )

    async def _command_position_move(self, target, command, already_moving_same_dir):
        """Drive the travel motor for a mid-position ``set_position`` move.

        Base behavior: when already travelling the right way, leave the motor
        running (the caller only retargets the tracker); otherwise check target
        availability and latch the directional relay, relying on the tracker to
        stop it on arrival. Subclasses whose device has native position control
        (e.g. a wrapped cover exposing ``set_cover_position``) override this to
        forward the target straight to the device instead.
        """
        if already_moving_same_dir:
            return
        self._require_movement_target_available(
            self._movement_target(command == SERVICE_CLOSE_COVER)
        )
        await self._async_handle_command(command)

    async def set_tilt_position(self, position, *, recalibrate: bool = True):
        """Move cover tilt to a designated position.

        ``recalibrate`` is passed False by exactly one caller,
        ``_maybe_start_recalibrated_leg`` running leg B of a recalibrated
        move (issue #179), to stop this call from arming a leg of its own on
        top of one that already ran. It has a second, less obvious
        consequence: it also exempts the move from ``min_movement_time`` (see
        ``_is_movement_too_short``'s ``is_recalibrated_leg`` parameter, which
        is fed ``not recalibrate``) — leg A has already driven the motor a
        full travel, so leg B's own pulse is the point of the operation, not
        a redundant nudge to skip. A future caller passing ``recalibrate=False``
        for an unrelated reason would silently get that exemption too.
        """
        plan = self._recalibration_plan(recalibrate, position, axis="tilt")
        if plan is RecalibrationPlan.TWO_LEG:
            # The drive axis is "tilt" only where the tilt motor is independent
            # (dual_motor) and so stalls against its own limit; everywhere else
            # the tilt "motor" IS the travel motor, so the datum is a travel
            # endpoint and leg A drives "travel" instead. The *armed* axis is
            # always "tilt" regardless — leg B is the tilt move the caller
            # asked for either way.
            axis = "tilt" if self._tilt_strategy.uses_tilt_motor else "travel"
            # Leg A always drives fully open (closing=False). Stop and settle
            # first if that reverses an in-flight movement (issue #179,
            # mirroring set_position's own leg A). dual_motor's tilt motor is
            # independent, so it needs the axis-aware tilt helper (a moving
            # dedicated tilt motor must get a tilt stop, not a travel STOP —
            # #153); every other strategy drives leg A via the plain travel
            # OPEN command, so it reuses the same helper set_position already
            # uses.
            if axis == "tilt":
                was_tilt_motor_move = self._moving_tilt_motor
                if not await self._stop_and_settle_tilt_before_recalibration_drive(
                    self._tilt_strategy.tilt_command_for(False), was_tilt_motor_move
                ):
                    return
            elif not await self._stop_and_settle_before_recalibration_drive(
                SERVICE_OPEN_COVER
            ):
                return
            # Arm only AFTER the drive, never before — mirrors set_position.
            # _start_recalibration_drive funnels through _async_move_to_endpoint
            # or _async_move_tilt_to_endpoint, both of which start with
            # _abandon_active_lifecycle -> _supersede_movement() (bumps
            # _movement_epoch). _arm_recalibrated_leg stamps _recalibration_epoch
            # from self._movement_epoch, so arming before the drive would
            # capture the pre-bump epoch — leg A's own completion would then
            # read as a newer, unrelated movement and the epoch check in
            # _maybe_start_recalibrated_leg would silently drop leg B.
            if await self._start_recalibration_drive(axis):
                self._arm_recalibrated_leg(position, "tilt")
                return
            self._log(
                "set_tilt_position :: recalibration leg did not start, moving directly"
            )
        elif plan is RecalibrationPlan.FORCED_ENDPOINT:
            # A tilt endpoint on a dedicated tilt motor: driving there IS the
            # recalibration, so there is no second leg to arm — but only when
            # the drive is actually forced to cover the full tilt time rather
            # than trusting the believed tilt for an ordinary timed move.
            # Exactly set_position's endpoint branch, on the tilt axis; see
            # _recalibration_plan for why NONE was wrong here. This plan is
            # only ever produced for uses_tilt_motor, so the drive axis is
            # always "tilt".
            #
            # Like the travel endpoint drive (and unlike leg A, which always
            # opens) this can reverse either way — target=0 drives the tilt
            # motor closed, target=100 open — so stop and settle first if it
            # would, through the axis-aware tilt helper.
            endpoint_command = self._tilt_strategy.tilt_command_for(position == 0)
            was_tilt_motor_move = self._moving_tilt_motor
            if not await self._stop_and_settle_tilt_before_recalibration_drive(
                endpoint_command, was_tilt_motor_move
            ):
                return
            # _start_recalibration_drive is reused purely for its snapshot /
            # rollback and not-started handling — _force_full_tilt_redrive can
            # silently fail to start, and that must not leave tilt_calc seeded
            # at a fabricated endpoint.
            if await self._start_recalibration_drive("tilt", target=position):
                return
            self._log(
                "set_tilt_position :: forced tilt endpoint redrive did not"
                " start, moving directly"
            )
        self._self_initiated_movement = not self._triggered_externally
        # Capture before _abandon_active_lifecycle resets it: a dedicated tilt
        # motor being displaced must get an axis-aware stop, not a travel STOP
        # off a stale _last_command (#153) — see _stop_displaced_movement_for_tilt.
        was_tilt_motor_move = self._moving_tilt_motor
        await self._abandon_active_lifecycle()
        current = self.tilt_calc.current_position()
        target = position
        self._log(
            "set_tilt_position :: current: %s, target: %d",
            current if current is not None else "None",
            target,
        )

        if current is None:
            closing = target <= 50
            current = 100 if closing else 0
            self.tilt_calc.update_position(current)
        elif target < current:
            closing = True
        elif target > current:
            closing = False
        else:
            await self._release_displaced_tilt_motor(was_tilt_motor_move)
            return

        if self._tilt_strategy is not None:
            command = self._tilt_strategy.tilt_command_for(closing)
        else:
            command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER

        should_proceed, is_direction_change = await self._handle_pre_movement_checks(
            command
        )
        if not should_proceed:
            await self._release_displaced_tilt_motor(was_tilt_motor_move)
            return

        if is_direction_change:
            was_moving = (
                self.tilt_calc.is_traveling() or self.travel_calc.is_traveling()
            )
            if self.tilt_calc.is_traveling():
                self.tilt_calc.stop()
            if self.travel_calc.is_traveling():
                self.travel_calc.stop()
            self.stop_auto_updater()
            await self._stop_displaced_movement_for_tilt(was_tilt_motor_move)
            # A reversal is stop → settle → go: give the motor (or momentary
            # relay) time to come to rest before driving the other way, and bail
            # if a stop/newer target claimed the movement inside the gap. This
            # settle is intentionally NOT gated on _triggered_externally: the
            # dual-motor drive below (_send_tilt_close/open) is itself ungated on
            # external, so an external redirect reaching here (e.g. a sequential
            # external close) still drives the motor and must get its rest gap —
            # reversing a physical cover too fast can trip its supply. Do not
            # "optimise" this to skip the settle when external.
            if was_moving and not await self._settle_before_reversing():
                return
            current = self.tilt_calc.current_position()
            if target == current:
                return

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)
            if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
                await self._send_tilt_stop()

        if not is_direction_change:
            self._stop_travel_if_traveling()

        tilt_time = self._tilting_time_close if closing else self._tilting_time_open
        movement_time = (abs(target - current) / 100.0) * tilt_time

        travel_target = None
        pre_step_delay = 0.0
        needs_travel_pre_step = False
        if self._tilt_strategy is not None:
            current_pos = self.travel_calc.current_position()
            if current is not None and current_pos is not None:
                steps = self._tilt_strategy.plan_move_tilt(target, current_pos, current)
                travel_target = extract_coupled_travel(steps)
                pre_step_delay = calculate_pre_step_delay(
                    steps, self._tilt_strategy, self.tilt_calc, self.travel_calc
                )
                if self._tilt_strategy.uses_tilt_motor and has_travel_pre_step(steps):
                    needs_travel_pre_step = True

        if self._is_movement_too_short(
            movement_time,
            target,
            current,
            "set_tilt_position",
            is_recalibrated_leg=not recalibrate,
        ):
            await self._release_displaced_tilt_motor(was_tilt_motor_move)
            return

        self._require_movement_target_available(self._tilt_movement_target(command))
        # The travel pre-step below isn't covered by the tilt gate above — see
        # _require_movement_target_available.
        if needs_travel_pre_step and travel_target is not None:
            await self._start_travel_pre_step(travel_target, target, command)
            return

        self._last_command = command
        # Set only now that the move is committed (past every no-op/too-short
        # early return) — a tilt move must not run on at a travel endpoint, but
        # leaking this onto a bailed-out call would wrongly suppress an
        # in-flight travel move's run-on (issue #125).
        self._moving_tilt = True

        if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
            self._moving_tilt_motor = True
            if closing:
                await self._send_tilt_close()
            else:
                await self._send_tilt_open()
        else:
            await self._async_handle_command(command)
        self._begin_movement(
            target,
            travel_target,
            self.tilt_calc,
            self.travel_calc,
            self._tilt_startup_delay,
            pre_step_delay,
        )

    async def _plan_tilt_for_travel(
        self, target: int, command: str, current_pos, current_tilt
    ) -> tuple[int | None, float, bool]:
        """Plan tilt coupling for a travel movement.

        Returns (tilt_target, pre_step_delay, started_pre_step).
        If started_pre_step is True, the caller should return immediately
        because _start_tilt_pre_step has taken over the movement lifecycle.
        """
        tilt_target = None
        pre_step_delay = 0.0
        self._tilt_restore_target = None

        if self._tilt_strategy is None:
            return tilt_target, pre_step_delay, False

        if current_pos is None or current_tilt is None:
            return tilt_target, pre_step_delay, False

        steps = self._tilt_strategy.plan_move_position(
            target, current_pos, current_tilt
        )
        tilt_target = extract_coupled_tilt(steps)
        pre_step_delay = calculate_pre_step_delay(
            steps, self._tilt_strategy, self.tilt_calc, self.travel_calc
        )

        # Dual motor: tilt to safe position first, then travel
        if (
            tilt_target is not None
            and self._tilt_strategy.uses_tilt_motor
            and current_tilt != tilt_target
        ):
            if target in (0, 100):
                restore = target
                if target == 0 and not self._close_includes_tilt:
                    # close_includes_tilt off: close travels only; the slats
                    # stay at the safe position the pre-step drove them to.
                    restore = tilt_target
            elif self._tilt_strategy.allows_tilt_at_position(target):
                restore = current_tilt
            else:
                restore = tilt_target  # stay at safe position
            await self._start_tilt_pre_step(tilt_target, target, command, restore)
            return tilt_target, pre_step_delay, True

        # Dual motor: pre-step skipped, but still snap tilt to endpoint.
        # Same close_includes_tilt guard as above: on a close with the option
        # off, don't schedule a restore to 0 — leave tilt at the safe position.
        if (
            tilt_target is not None
            and self._tilt_strategy.uses_tilt_motor
            and target in (0, 100)
            and current_tilt != target
            and not (target == 0 and not self._close_includes_tilt)
        ):
            self._tilt_restore_target = target

        # Shared motor with restore: save tilt for post-travel restore
        if (
            tilt_target is not None
            and self._tilt_strategy.restores_tilt
            and not self._tilt_strategy.uses_tilt_motor
            and target not in (0, 100)
        ):
            self._tilt_restore_target = current_tilt

        return tilt_target, pre_step_delay, False

    async def _handle_pre_movement_checks(self, command):
        """Handle startup delay conflicts and relay delay before a movement.

        Returns (should_proceed, is_direction_change).
        """
        is_direction_change = self._is_direction_change(command)

        # If startup delay active for same direction, don't restart
        if self._startup_delay_task and not self._startup_delay_task.done():
            if not is_direction_change:
                self._log(
                    "_handle_pre_movement_checks :: startup delay active, skipping"
                )
                return False, is_direction_change
            # On tap hardware the stop waits the relay confirmation out, and
            # the confirmation runs the parked start: the move is then in
            # motion, and the caller's own in-motion direction-change block
            # stops it, settles, and drives the other way. Only a start that is
            # still parked afterwards is cancelled unrun and stopped here.
            await self._await_confirmation_before_stop()
            if self._startup_delay_task and not self._startup_delay_task.done():
                self._log(
                    "_handle_pre_movement_checks :: direction change, cancelling startup delay"
                )
                self._cancel_startup_delay_task()
                await self._async_handle_command(SERVICE_STOP_COVER)
            else:
                self._log(
                    "_handle_pre_movement_checks :: direction change, the confirmed"
                    " move is reversed in motion"
                )

        return True, is_direction_change

    def _is_movement_too_short(
        self,
        movement_time,
        target,
        current,
        label,
        *,
        is_recalibrated_leg: bool = False,
    ):
        """Check if movement time is below minimum. Returns True if movement should be skipped.

        ``is_recalibrated_leg`` marks leg B of a recalibrated move (#179) — the
        caller passed ``recalibrate=False``. min_movement_time exists to skip
        pointless motor pulses for imperceptible moves, but by the time leg B
        runs, leg A has already driven the motor a full travel to reach a true
        datum; the second pulse to the position the user actually asked for IS
        the point of the operation, not a redundant nudge. Rejecting it here
        would silently strand the cover at leg A's endpoint instead of where
        it was asked to go, so leg B is exempt from this check entirely.
        """
        if is_recalibrated_leg:
            return False
        is_to_endpoint = target in (0, 100)
        if (
            self._min_movement_time is not None
            and self._min_movement_time > 0
            and not is_to_endpoint
            and movement_time < self._min_movement_time
        ):
            _LOGGER.info(
                "%s :: movement too short (%fs < %fs), ignoring - from %d%% to %d%%",
                label,
                movement_time,
                self._min_movement_time,
                current,
                target,
            )
            self.async_write_ha_state()
            return True
        return False

    def _require_configured(self) -> None:
        """Raise if the cover is not properly configured."""
        missing = self._get_missing_configuration()
        if missing:
            raise HomeAssistantError(
                f"Cover not configured: missing {', '.join(missing)}. "
                "Please configure using the Cover Time Based card."
            )

    def _require_travel_time(self, closing: bool) -> float:
        """Return travel time for the given direction, or raise if not configured."""
        travel_time = self._travel_time_close if closing else self._travel_time_open
        if travel_time is None:
            raise HomeAssistantError(
                "Travel time not configured. Please configure travel times "
                "using the Cover Time Based card."
            )
        return travel_time

    def _are_entities_configured(self) -> bool:
        """Return True if the required input entities are configured.

        Subclasses override this to check their specific entity IDs.
        """
        return True

    def _get_missing_configuration(self) -> list[str]:
        """Return list of missing configuration items."""
        missing = []
        if not self._are_entities_configured():
            missing.append(self._missing_entities_label)
        if self._travel_time_close is None and self._travel_time_open is None:
            missing.append("travel times")
        return missing

    def _target_entity_ids(self) -> list[str]:
        """Return the configured target entity IDs this cover drives.

        These are the switch/button/script entities that actually move the
        device. Subclasses (e.g. wrapped mode) extend this with their own
        targets.
        """
        return [
            entity_id
            for attr in self._SWITCH_TARGET_ATTRS
            if (entity_id := getattr(self, attr, None))
        ]

    @staticmethod
    def _entity_unavailable(state) -> bool:
        """Return True if a target entity is unavailable.

        Unavailable means the entity is missing (state is None) or its state is
        STATE_UNAVAILABLE. STATE_UNKNOWN is treated as available (a connected
        entity whose value isn't known yet, e.g. a button after a restart).
        """
        return state is None or state.state == STATE_UNAVAILABLE

    def _any_target_unavailable(self) -> bool:
        """Short-circuiting check used by the hot-path `available` property."""
        if self.hass is None:
            return False
        return any(
            self._entity_unavailable(self.hass.states.get(entity_id))
            for entity_id in self._target_entity_ids()
        )

    def _movement_target(self, closing: bool) -> str | None:
        """Entity driven to move the cover in the given travel direction."""
        return self._close_switch_entity_id if closing else self._open_switch_entity_id

    def _tilt_movement_target(self, command: str) -> str | None:
        """Entity driven for a resolved tilt command.

        ``command`` is what the funnel already computed via ``tilt_command_for``
        (which some strategies, e.g. sequential_open, invert). Dual-motor tilt
        uses dedicated tilt switches; shared-motor tilt drives the main travel
        switch.
        """
        closing = command == SERVICE_CLOSE_COVER
        if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
            return self._tilt_close_switch_id if closing else self._tilt_open_switch_id
        return self._movement_target(closing)

    def _require_movement_target_available(self, target: str | None) -> None:
        """Reject a fresh, self-initiated movement whose target is unavailable.

        Only fresh user/automation movement is gated (`_self_initiated_movement`).
        Stops, reverses, external reactions, retargets, and internal
        continuations never reach here (or have `_self_initiated_movement` False),
        so the cover can always be halted regardless of target availability.

        Movement that runs via a pre-step (dual-motor / sequential) returns from
        the funnel before reaching the funnel's own per-direction gate, so each
        pre-step phase calls this directly for its target (in
        `_start_tilt_pre_step` / `_start_travel_pre_step`). The all-targets
        `available` flag (the cover reports unavailable whenever any target is
        down) is the backstop covering both paths.
        """
        if not self._self_initiated_movement or self.hass is None:
            return
        if target and self._entity_unavailable(self.hass.states.get(target)):
            raise HomeAssistantError(
                f"Cover target '{target}' is unavailable; cannot start movement."
            )

    def _has_tilt_support(self):
        """Return if cover has tilt support."""
        return (
            self.supports_tilt
            and self._tilt_strategy is not None
            and hasattr(self, "tilt_calc")
        )
