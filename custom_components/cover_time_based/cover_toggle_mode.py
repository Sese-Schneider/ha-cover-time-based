"""Toggle mode cover."""

import asyncio
import logging
import time
from asyncio import sleep

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
)

from .cover_switch import SwitchCoverTimeBased

_LOGGER = logging.getLogger(__name__)


class ToggleModeCover(SwitchCoverTimeBased):
    """Cover controlled by toggle-style relays (toggle mode).

    In toggle mode, the motor controller toggles state on each pulse.
    A second pulse on the same direction button stops the motor.
    _send_stop therefore re-presses the last-used direction button.

    The send methods return immediately after the ON edge so that position
    tracking starts from the moment the motor begins moving. The pulse
    completion (sleep + turn_off) runs in the background.
    """

    def __init__(self, pulse_time, **kwargs):
        super().__init__(**kwargs)
        self._pulse_time = pulse_time
        self._last_external_toggle_time = {}
        self._last_tilt_direction = None

    async def _complete_pulse(self, entity_id):
        """Complete a relay pulse by turning OFF after pulse_time."""
        try:
            await sleep(self._pulse_time)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": entity_id},
                False,
            )
        except asyncio.CancelledError:
            pass

    async def async_stop_cover(self, **kwargs):
        """Stop the cover, only sending relay command if it was active."""
        was_active = (
            self.is_opening
            or self.is_closing
            or (self._startup_delay_task and not self._startup_delay_task.done())
            or (self._delay_task and not self._delay_task.done())
        )
        tilt_restore_was_active = self._tilt_restore_active
        tilt_pre_step_was_active = self._pending_travel_target is not None
        self._cancel_startup_delay_task()
        self._cancel_delay_task()
        self._handle_stop()
        if self._tilt_strategy is not None:
            self._tilt_strategy.snap_trackers_to_physical(
                self.travel_calc, self.tilt_calc
            )
        if not self._triggered_externally and was_active:
            await self._send_stop()
            if (
                tilt_restore_was_active or tilt_pre_step_was_active
            ) and self._has_tilt_motor():
                await self._send_tilt_stop()
        self.async_write_ha_state()
        self._last_command = None
        self._last_tilt_direction = None

    # --- External state change handlers ---

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle external state change in toggle mode.

        Only the rising edge (OFF→ON) is interesting — this is the button
        press. The ON→OFF transition is just the relay releasing and is ignored.

        A debounce prevents double-triggering for momentary switches that
        produce OFF->ON->OFF per click.
        """
        if new_val != "on":
            return

        now = time.monotonic()
        last = self._last_external_toggle_time.get(entity_id, 0)
        debounce_window = self._pulse_time + 0.5
        if now - last < debounce_window:
            self._log(
                "_handle_external_state_change :: debounced toggle on %s",
                entity_id,
            )
            return
        self._last_external_toggle_time[entity_id] = now

        if entity_id == self._open_switch_entity_id:
            self._log("_handle_external_state_change :: external open toggle detected")
            await self.async_open_cover()
        elif entity_id == self._close_switch_entity_id:
            self._log("_handle_external_state_change :: external close toggle detected")
            await self.async_close_cover()

    async def _handle_external_tilt_state_change(self, entity_id, old_val, new_val):
        """Handle external tilt state change in toggle mode.

        Only reacts on rising edge (OFF→ON). Same debounce as travel handler.
        If tilt is already moving, treat any toggle as stop.
        """
        if new_val != "on":
            return

        now = time.monotonic()
        last = self._last_external_toggle_time.get(entity_id, 0)
        debounce_window = self._pulse_time + 0.5
        if now - last < debounce_window:
            self._log(
                "_handle_external_tilt_state_change :: debounced toggle on %s",
                entity_id,
            )
            return
        self._last_external_toggle_time[entity_id] = now

        if entity_id == self._tilt_open_switch_id:
            if self.tilt_calc.is_traveling():
                self._log(
                    "_handle_external_tilt_state_change ::"
                    " tilt open toggle while traveling, stopping"
                )
                await self.async_stop_cover()
            else:
                self._log(
                    "_handle_external_tilt_state_change :: external tilt open toggle detected"
                )
                await self.async_open_cover_tilt()
        elif entity_id == self._tilt_close_switch_id:
            if self.tilt_calc.is_traveling():
                self._log(
                    "_handle_external_tilt_state_change ::"
                    " tilt close toggle while traveling, stopping"
                )
                await self.async_stop_cover()
            else:
                self._log(
                    "_handle_external_tilt_state_change :: external tilt close toggle detected"
                )
                await self.async_close_cover_tilt()

    # --- Raw direction commands (calibration screen) ---

    async def _raw_direction_command(self, command: str) -> None:
        """In toggle mode, opposite-direction = stop, not reverse.

        To change direction: stop first, wait for pulse, then send new direction.
        """
        if command in ("open", "close"):
            opposite = SERVICE_CLOSE_COVER if command == "open" else SERVICE_OPEN_COVER
            if self._last_command == opposite:
                await self._send_stop()
                await sleep(self._pulse_time)
        elif command in ("tilt_open", "tilt_close"):
            opposite_dir = "close" if command == "tilt_open" else "open"
            if self._last_tilt_direction == opposite_dir:
                await self._send_tilt_stop()
                await sleep(self._pulse_time)
        await super()._raw_direction_command(command)

    # --- Internal relay commands ---

    async def _send_open(self) -> None:
        if self._switch_is_on(self._close_switch_entity_id):
            self._mark_switch_pending(self._close_switch_entity_id, 1)
        self._mark_switch_pending(self._open_switch_entity_id, 2)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._close_switch_entity_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on",
            {"entity_id": self._open_switch_entity_id},
            False,
        )
        # Motor controller acts on ON edge; complete pulse in background
        self.hass.async_create_task(self._complete_pulse(self._open_switch_entity_id))

    async def _send_close(self) -> None:
        if self._switch_is_on(self._open_switch_entity_id):
            self._mark_switch_pending(self._open_switch_entity_id, 1)
        self._mark_switch_pending(self._close_switch_entity_id, 2)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._open_switch_entity_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on",
            {"entity_id": self._close_switch_entity_id},
            False,
        )
        # Motor controller acts on ON edge; complete pulse in background
        self.hass.async_create_task(self._complete_pulse(self._close_switch_entity_id))

    async def _send_stop(self) -> None:
        if self._last_command == SERVICE_CLOSE_COVER:
            self._mark_switch_pending(self._close_switch_entity_id, 2)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._close_switch_entity_id},
                False,
            )
            # Motor toggles on ON edge; complete pulse in background
            self.hass.async_create_task(
                self._complete_pulse(self._close_switch_entity_id)
            )
        elif self._last_command == SERVICE_OPEN_COVER:
            self._mark_switch_pending(self._open_switch_entity_id, 2)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._open_switch_entity_id},
                False,
            )
            # Motor toggles on ON edge; complete pulse in background
            self.hass.async_create_task(
                self._complete_pulse(self._open_switch_entity_id)
            )
        else:
            self._log("_send_stop :: toggle mode with no last command, skipping")

    # --- Tilt motor relay commands ---

    async def _send_tilt_open(self) -> None:
        if self._switch_is_on(self._tilt_close_switch_id):
            self._mark_switch_pending(self._tilt_close_switch_id, 1)
        self._mark_switch_pending(self._tilt_open_switch_id, 2)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_close_switch_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on",
            {"entity_id": self._tilt_open_switch_id},
            False,
        )
        self.hass.async_create_task(self._complete_pulse(self._tilt_open_switch_id))
        self._last_tilt_direction = "open"

    async def _send_tilt_close(self) -> None:
        if self._switch_is_on(self._tilt_open_switch_id):
            self._mark_switch_pending(self._tilt_open_switch_id, 1)
        self._mark_switch_pending(self._tilt_close_switch_id, 2)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_open_switch_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on",
            {"entity_id": self._tilt_close_switch_id},
            False,
        )
        self.hass.async_create_task(self._complete_pulse(self._tilt_close_switch_id))
        self._last_tilt_direction = "close"

    async def _send_tilt_stop(self) -> None:
        if self._last_tilt_direction == "close":
            self._mark_switch_pending(self._tilt_close_switch_id, 2)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._tilt_close_switch_id},
                False,
            )
            self.hass.async_create_task(
                self._complete_pulse(self._tilt_close_switch_id)
            )
        elif self._last_tilt_direction == "open":
            self._mark_switch_pending(self._tilt_open_switch_id, 2)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._tilt_open_switch_id},
                False,
            )
            self.hass.async_create_task(self._complete_pulse(self._tilt_open_switch_id))
        else:
            self._log(
                "_send_tilt_stop :: toggle mode with no last tilt direction, skipping"
            )
        self._last_tilt_direction = None
