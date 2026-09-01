"""Single-button control mode (down/stop/up/stop).

One button; each press advances the motor's cycle. We track the phase by dead
reckoning (no feedback) and translate open/close/stop into the press sequence
the planner returns, spaced by the fixed DIRECTION_CHANGE_DELAY. Full
open/close run to the physical limit and re-anchor position; a wrong phase is
not self-healing (see the design spec) -- the resync service corrects it.
"""

from __future__ import annotations

import asyncio
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
        self._pulse_tasks: dict[str, asyncio.Task] = {}

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

    # --- pressing the button ------------------------------------------
    async def _pulse_button(self) -> None:
        """Momentarily energise the button line (ON now, OFF in background)."""
        entity_id = self._open_switch_entity_id
        await self.hass.services.async_call(
            "homeassistant", "turn_on", {"entity_id": entity_id}, False
        )
        self._pulse_tasks[entity_id] = self.hass.async_create_task(
            self._complete_pulse(entity_id)
        )

    async def _complete_pulse(self, entity_id) -> None:
        try:
            await sleep(self._pulse_time)
            await self.hass.services.async_call(
                "homeassistant", "turn_off", {"entity_id": entity_id}, False
            )
        except asyncio.CancelledError:
            pass
        finally:
            if self._pulse_tasks.get(entity_id) is asyncio.current_task():
                self._pulse_tasks.pop(entity_id, None)

    # --- press sequencing ---------------------------------------------
    def _start_press_sequence(self, action: Action) -> None:
        phases = plan(self._phase, action)
        if not phases:
            return
        if self._press_task is not None and not self._press_task.done():
            self._press_task.cancel()
        self._press_task = self.hass.async_create_task(self._run_press_sequence(phases))

    async def _run_press_sequence(self, phases: list[Phase]) -> None:
        """Pulse once per planned phase, gap-spaced, updating phase each time."""
        try:
            for index, phase in enumerate(phases):
                if index:
                    await sleep(DIRECTION_CHANGE_DELAY)
                await self._pulse_button()
                self._phase = phase
        except asyncio.CancelledError:
            pass
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
        press sequence's inter-press gap, the settle margin after an
        endpoint, or a single pulse's own completion may all be in flight.
        Left alone, the OLD entity would keep issuing presses against the
        physical button after the new entity takes over -- real motor
        desync. Mirrors PulseModeCover._cancel_background_pulses
        (cover_pulse_mode.py): cancel every in-flight task, then
        unconditionally turn the button off so a pulse caught mid-flight is
        not left latched ON.
        """
        if self._press_task is not None and not self._press_task.done():
            self._press_task.cancel()
        self._press_task = None
        self._cancel_settle()
        pending = list(self._pulse_tasks.values())
        self._pulse_tasks.clear()
        for task in pending:
            if not task.done():
                task.cancel()
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
        self._start_press_sequence(Action.OPEN)

    async def _send_close(self) -> None:
        self._cancel_settle()
        self._start_press_sequence(Action.CLOSE)

    async def _send_stop(self) -> None:
        self._cancel_settle()
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
        if value is not None:
            self._phase = Phase(value)
