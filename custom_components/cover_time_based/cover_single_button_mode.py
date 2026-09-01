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


class SingleButtonModeCover(SwitchCoverTimeBased):
    """A cover driven by a single cycling button."""

    supports_tilt = False

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

    def _get_missing_configuration(self) -> list[str]:
        missing = []
        if not self._are_entities_configured():
            missing.append("button entity")
        if self._travel_time_close is None and self._travel_time_open is None:
            missing.append("travel times")
        return missing

    # --- capabilities --------------------------------------------------
    def _self_stops_at_endpoints(self) -> bool:
        return True

    async def _handle_external_state_change(self, entity_id, old_state, new_state):
        # The button is an output we drive; its state changes are our own
        # echoes, and this mode has no feedback to read. Ignore them.
        self._log("single_button :: ignoring external state change on %s", entity_id)

    # --- press sequencing ---------------------------------------------
    def _start_press_sequence(self, action: Action) -> None:
        """Plan from the current phase and schedule the press sequence.

        Callers must already have awaited _supersede_active_press() before
        calling this, so there is nothing live left to cancel here -- we
        only need to plan (from the now-settled phase) and schedule.
        """
        phases = plan(self._phase, action)
        if not phases:
            return
        self._press_task = self.hass.async_create_task(self._run_press_sequence(phases))

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
        task = self._press_task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if not self._press_active:
            return
        self._press_active = False
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._open_switch_entity_id},
            False,
        )
        await sleep(DIRECTION_CHANGE_DELAY)

    async def _run_press_sequence(self, phases: list[Phase]) -> None:
        """Press once per planned phase, gap-spaced, updating phase each time.

        Each press is a discrete, self-contained pulse performed inline: ON,
        wait pulse_time, OFF -- fully resolved before the next press's gap
        even starts. This guarantees the button is OFF between consecutive
        presses regardless of how pulse_time compares to
        DIRECTION_CHANGE_DELAY (the previous behaviour scheduled each press's
        OFF as a background task, so with the default pulse_time equal to
        DIRECTION_CHANGE_DELAY a re-press could race and cancel the prior
        press's pending OFF -- the motor would then register fewer presses
        than intended, desyncing the tracked phase).

        `_phase` is updated -- and `_press_active` raised -- immediately
        after the ON edge, before the pulse-time sleep, not after the OFF: a
        command arriving mid-pulse must plan from the phase this press is
        already committing to, not the stale pre-press phase, or it can plan
        as if the motor hadn't moved yet (e.g. a stop that finds nothing to
        stop). Cancellation itself is left for _supersede_active_press to
        clean up -- this method does not issue its own turn_off on
        cancellation, since that would race the superseding command's
        cleanup.
        """
        entity_id = self._open_switch_entity_id
        try:
            for index, phase in enumerate(phases):
                if index:
                    await sleep(DIRECTION_CHANGE_DELAY)
                await self.hass.services.async_call(
                    "homeassistant", "turn_on", {"entity_id": entity_id}, False
                )
                self._phase = phase
                self._press_active = True
                await sleep(self._pulse_time)
                await self.hass.services.async_call(
                    "homeassistant", "turn_off", {"entity_id": entity_id}, False
                )
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
                await self.hass.services.async_call(
                    "homeassistant", "turn_off", {"entity_id": entity_id}, False
                )
            self._press_active = False
            raise
        finally:
            if self._press_task is asyncio.current_task():
                self._press_task = None

    def _cancel_settle(self) -> None:
        if self._settle_task is not None and not self._settle_task.done():
            self._settle_task.cancel()
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
        if self._press_task is not None and not self._press_task.done():
            self._press_task.cancel()
        self._press_task = None
        self._cancel_settle()
        if self._open_switch_entity_id:
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": self._open_switch_entity_id},
                False,
            )

    # --- the mode contract --------------------------------------------
    async def _send_open(self) -> None:
        self._cancel_settle()
        await self._supersede_active_press()
        self._start_press_sequence(Action.OPEN)

    async def _send_close(self) -> None:
        self._cancel_settle()
        await self._supersede_active_press()
        self._start_press_sequence(Action.CLOSE)

    async def _send_stop(self) -> None:
        self._cancel_settle()
        await self._supersede_active_press()
        self._start_press_sequence(Action.STOP)

    # --- endpoint re-anchor -------------------------------------------
    def _on_endpoint_reached(self, endpoint: int) -> None:
        target = Phase.AT_OPEN if endpoint == 100 else Phase.AT_CLOSED
        margin = self._endpoint_runon_time
        if not margin or margin <= 0:
            self._phase = target
            return
        # Keep the moving phase for a settle margin so a re-press during the
        # motor's final run predicts STOP, not a reversal; then anchor.
        self._cancel_settle()
        self._settle_task = self.hass.async_create_task(
            self._settle_endpoint(margin, target)
        )

    async def _settle_endpoint(self, margin, target) -> None:
        try:
            await sleep(margin)
            self._phase = target
        except asyncio.CancelledError:
            pass
        finally:
            if self._settle_task is asyncio.current_task():
                self._settle_task = None

    # --- resync ----------------------------------------------------------
    async def async_resync(self, state: str) -> None:
        """Re-anchor phase and position after off-system control."""
        if state == "closed":
            self._phase = Phase.AT_CLOSED
            self.travel_calc.set_position(0)
        elif state == "open":
            self._phase = Phase.AT_OPEN
            self.travel_calc.set_position(100)
        else:
            raise ValueError(f"unknown resync state: {state}")
        self.async_write_ha_state()
        await self._async_persist_position()

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
