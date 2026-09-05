"""Single-button control mode (down/stop/up/stop).

One button; each press advances the motor's cycle. We track the phase by dead
reckoning (no feedback) and translate open/close/stop into the press sequence
the planner returns, spaced by the fixed DIRECTION_CHANGE_DELAY. Full
open/close run to the physical limit and re-anchor position; a wrong phase is
not self-healing (see the design spec) -- the resync service corrects it.
"""

from __future__ import annotations

import asyncio
import contextlib
from asyncio import sleep

from .const import DIRECTION_CHANGE_DELAY
from .cover_switch import SwitchCoverTimeBased
from .single_button_cycle import Action, Phase, plan

# The phase a self-stopping motor is in once it has reached a travel limit.
_PHASE_AT_ENDPOINT: dict[int, Phase] = {100: Phase.AT_OPEN, 0: Phase.AT_CLOSED}


def _live(task: asyncio.Task | None) -> asyncio.Task | None:
    """The task if it is still running, else None."""
    return task if task is not None and not task.done() else None


class SingleButtonModeCover(SwitchCoverTimeBased):
    """A cover driven by a single cycling button."""

    supports_tilt = False
    _missing_entities_label = "button entity"

    def __init__(self, pulse_time, **kwargs):
        super().__init__(**kwargs)
        self._pulse_time = pulse_time
        self._phase = Phase.AT_CLOSED
        self._press_task: asyncio.Task | None = None
        self._settle_task: asyncio.Task | None = None
        # True only while a press's ON pulse is actually in flight (between
        # turn_on and turn_off). Lets _supersede_active_press tell a press
        # that was genuinely interrupted mid-pulse (button left latched ON,
        # needs a cleanup turn_off) from one cancelled between presses (the
        # button is already OFF there -- no cleanup needed).
        self._press_active = False

    # --- configuration -------------------------------------------------
    def _are_entities_configured(self) -> bool:
        """One button is enough for this mode."""
        return bool(self._open_switch_entity_id)

    # --- capabilities --------------------------------------------------
    def _self_stops_at_endpoints(self) -> bool:
        return True

    def _supports_stepped_calibration(self) -> bool:
        # A restart in the same direction after a stop is a reversal press
        # sequence here (the motor first runs the wrong way), so the stepped
        # overhead and minimum-movement tests measure nothing on this cycle.
        return False

    async def _handle_external_state_change(self, entity_id, old_state, new_state):
        # The button is an output we drive; its state changes are our own
        # echoes, and this mode has no feedback to read. Ignore them.
        self._log("single_button :: ignoring external state change on %s", entity_id)

    # --- press sequencing ---------------------------------------------
    async def _release_button(self) -> None:
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._open_switch_entity_id},
            False,
        )

    def _start_press_sequence(self, action: Action) -> None:
        """Plan from the current phase and schedule the press sequence.

        Callers must already have awaited _supersede_active_press() before
        calling this, so there is nothing live left to cancel here -- we
        only need to plan (from the now-settled phase) and schedule.

        A movement arms wait_for_relay_feedback on the button. The arm has to
        be set here, synchronously: the base consumes it the moment the command
        returns, before the first press has gone out.
        """
        self._feedback_armed_entity = None
        phases = plan(self._phase, action)
        if not phases:
            return
        armed = action is not Action.STOP and self._arm_relay_feedback(
            self._open_switch_entity_id
        )
        self._press_task = self.hass.async_create_task(
            self._run_press_sequence(phases, mark_final_press=armed)
        )

    async def _supersede_active_press(self) -> None:
        """Cleanly end any in-flight press sequence before a new command.

        Cancels the live press task and awaits it so its `finally` (which
        self-clears _press_task) runs to completion BEFORE anything else --
        deterministic ordering, with no race against the replacement
        sequence we are about to schedule.

        If a press was actually interrupted mid-pulse -- the cancelled task
        never reached its own turn_off, so the button is left latched ON --
        we turn it off ourselves and wait out DIRECTION_CHANGE_DELAY so the
        replacement sequence starts from a clean, distinct OFF window.
        Without this, the replacement's first press (which skips its own
        leading gap) would fire turn_on on an already-ON relay and merge
        with the interrupted press instead of registering as a second one.

        A no-op when nothing is in flight, so a command from rest (the
        common case) stays latency-free -- only an actual interruption pays
        for the cleanup turn_off and gap.

        `_press_active` is checked unconditionally after the cancel step,
        not only when a live task was found: an unexpected mid-pulse error
        in `_run_press_sequence` (a service call raising) also resets the
        flag and turns the button off itself before the task exits, but as
        defence in depth against any other way `_press_task` could end up
        done/None while `_press_active` is still True, this still performs
        the same cleanup rather than trusting the task's own exit path.
        """
        task = _live(self._press_task)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if not self._press_active:
            return
        self._press_active = False
        await self._release_button()
        await sleep(DIRECTION_CHANGE_DELAY)

    async def _run_press_sequence(
        self, phases: list[Phase], *, mark_final_press: bool = False
    ) -> None:
        """Press once per planned phase, gap-spaced, updating phase each time.

        Each press is a discrete, self-contained pulse performed inline: ON,
        wait pulse_time, OFF -- fully resolved before the next press's gap
        even starts. This guarantees the button is OFF between consecutive
        presses regardless of how pulse_time compares to
        DIRECTION_CHANGE_DELAY.

        `_phase` is updated -- and `_press_active` raised -- immediately
        after the ON edge, before the pulse-time sleep, not after the OFF: a
        command arriving mid-pulse must plan from the phase this press is
        already committing to, not the stale pre-press phase, or it can plan
        as if the motor hadn't moved yet (e.g. a stop that finds nothing to
        stop). Cancellation itself is left for _supersede_active_press to
        clean up -- this method does not issue its own turn_off on
        cancellation, since that would race the superseding command's
        cleanup.

        ``mark_final_press`` pre-counts the ON and OFF echoes of the LAST press
        only. The base starts a parked feedback wait from the echo-filter
        branch, so a pre-counted ON echo is what anchors tracking -- and the
        press that actually starts the motor is the last one of the plan, not
        a nudge before it. Uncounted echoes fall through to
        _handle_external_state_change, which ignores them.
        """
        entity_id = self._open_switch_entity_id
        try:
            for index, phase in enumerate(phases):
                if index:
                    await sleep(DIRECTION_CHANGE_DELAY)
                if mark_final_press and index == len(phases) - 1:
                    self._mark_switch_pending(
                        entity_id,
                        2,
                        timeout=self._armed_echo_window(
                            self._held_echo_window(self._pulse_time)
                        ),
                    )
                await self.hass.services.async_call(
                    "homeassistant", "turn_on", {"entity_id": entity_id}, False
                )
                self._phase = phase
                self._press_active = True
                await sleep(self._pulse_time)
                await self._release_button()
                self._press_active = False
        except asyncio.CancelledError:
            # Cleanup (compensating turn_off + gap, if the pulse was actually
            # in flight) is owned by _supersede_active_press, which reads
            # _press_active AFTER awaiting this task -- do not touch it here.
            pass
        except Exception:
            # An unexpected error mid-pulse (e.g. the turn_on/turn_off
            # service call itself raising) must not leave the relay latched
            # ON or _press_active stuck True -- either would let the next
            # press merge onto an already-ON relay. Best-effort turn the
            # button off (suppressed: cleanup must not raise a second error
            # over the original one) and clear the flag, then re-raise so
            # the error is still surfaced/logged by asyncio.
            with contextlib.suppress(Exception):
                await self._release_button()
            self._press_active = False
            raise
        finally:
            if self._press_task is asyncio.current_task():
                self._press_task = None

    async def _abort_press_plan(self) -> None:
        """Drop the pending plan so nothing left over presses the button.

        A settle task would re-anchor the phase, and an in-flight sequence would
        keep pressing from the phase it planned against — both against whatever
        replaces the plan. A press caught mid-pulse is released by
        _supersede_active_press.
        """
        self._cancel_settle()
        await self._supersede_active_press()

    def _cancel_settle(self) -> None:
        task = _live(self._settle_task)
        if task is not None:
            task.cancel()
        self._settle_task = None

    # --- removal / reload -----------------------------------------------
    async def _cancel_background_pulses(self) -> None:
        """On removal, stop pressing and leave the button relay OFF.

        A config-entry reload (every card save) can land mid-sequence: the
        press sequence's inter-press gap, a single press's own inline pulse,
        or the settle margin after an endpoint may all be in flight. Left
        alone, the OLD entity would keep issuing presses against the
        physical button after the new entity takes over -- real motor
        desync. Mirrors PulseModeCover._cancel_background_pulses
        (cover_pulse_mode.py): cancel the in-flight task, then
        unconditionally turn the button off so a press caught mid-pulse is
        not left latched ON.
        """
        task = _live(self._press_task)
        if task is not None:
            task.cancel()
        self._press_task = None
        self._cancel_settle()
        if self._open_switch_entity_id:
            await self._release_button()

    # --- the mode contract --------------------------------------------
    async def _send_open(self) -> None:
        await self._abort_press_plan()
        self._start_press_sequence(Action.OPEN)

    async def _send_close(self) -> None:
        await self._abort_press_plan()
        self._start_press_sequence(Action.CLOSE)

    async def _send_stop(self) -> None:
        await self._abort_press_plan()
        self._start_press_sequence(Action.STOP)

    # --- endpoint re-anchor -------------------------------------------
    def _on_endpoint_reached(self, endpoint: int) -> None:
        """Anchor the phase at the limit the tracker just reached.

        The tracker counts from the command, but the motor only moves once the
        press sequence has delivered its last press -- for a short move that is
        after the tracker's arrival. An anchor written while presses are still
        to come would be overwritten by them, so it waits for the sequence, and
        then for the settle margin (endpoint_runon_time), during which a
        re-press still predicts STOP rather than a reversal.
        """
        target = _PHASE_AT_ENDPOINT[endpoint]
        margin = self._endpoint_runon_time or 0
        press = _live(self._press_task)
        if press is None and margin <= 0:
            self._phase = target
            return
        self._cancel_settle()
        self._settle_task = self.hass.async_create_task(
            self._settle_endpoint(press, margin, target)
        )

    async def _settle_endpoint(
        self, press_task: asyncio.Task | None, margin: float, target: Phase
    ) -> None:
        try:
            if press_task is not None:
                # Passive: _supersede_active_press owns cancelling the
                # sequence; this only waits for it to end either way.
                await asyncio.wait([press_task])
            if margin > 0:
                await sleep(margin)
            self._phase = target
        except asyncio.CancelledError:
            pass
        finally:
            if self._settle_task is asyncio.current_task():
                self._settle_task = None

    # --- known position ------------------------------------------------
    async def _halt_for_known_position(self) -> None:
        """Cancel the press plan instead of stopping, then park the tracker.

        The button is a cycle input: a "stop" press on a motor already parked at
        the declared position would start it, so nothing is pressed here.
        """
        await self._abort_press_plan()
        self._neutralize_tracked_movement()

    def _on_known_position(self, position: int) -> None:
        """Anchor the tracked phase when an endpoint is declared.

        An intermediate position says nothing about where the motor is in its
        cycle, so the phase is left alone.
        """
        phase = _PHASE_AT_ENDPOINT.get(position)
        if phase is not None:
            self._phase = phase

    # --- persistence -----------------------------------------------------
    def _extra_persist_data(self) -> dict:
        return {"phase": self._phase.value}

    def _apply_restored_extra(self, stored: dict) -> None:
        value = stored.get("phase")
        if value is None:
            return
        try:
            self._phase = Phase(value)
        except ValueError:
            # Corrupted store or a renamed/removed Phase value -- keep the
            # current/default phase rather than breaking entity restore.
            self._log("single_button :: ignoring unknown stored phase %r", value)
