"""Toggle mode cover."""

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
    """

    def __init__(self, pulse_time, **kwargs):
        super().__init__(**kwargs)
        self._pulse_time = pulse_time
        self._last_external_toggle_time = {}

    # --- Public HA service overrides ---

    async def async_close_cover(self, **kwargs):
        """Close the cover; if already closing, treat as stop.

        For external triggers: any movement (opening OR closing) -> stop.
        The physical motor already stopped when the user pressed the button.
        For HA UI: same direction -> stop, opposite direction -> reverse (base class).
        """
        if self.is_closing:
            await self.async_stop_cover()
            return
        if self._triggered_externally and self.is_opening:
            self._log(
                "async_close_cover :: external close while opening, treating as stop"
            )
            await self.async_stop_cover()
            return
        await super().async_close_cover(**kwargs)

    async def async_open_cover(self, **kwargs):
        """Open the cover; if already opening, treat as stop.

        For external triggers: any movement (opening OR closing) -> stop.
        The physical motor already stopped when the user pressed the button.
        For HA UI: same direction -> stop, opposite direction -> reverse (base class).
        """
        if self.is_opening:
            await self.async_stop_cover()
            return
        if self._triggered_externally and self.is_closing:
            self._log(
                "async_open_cover :: external open while closing, treating as stop"
            )
            await self.async_stop_cover()
            return
        await super().async_open_cover(**kwargs)

    async def async_stop_cover(self, **kwargs):
        """Stop the cover, only sending relay command if it was active."""
        was_active = (
            self.is_opening
            or self.is_closing
            or (self._startup_delay_task and not self._startup_delay_task.done())
            or (self._delay_task and not self._delay_task.done())
        )
        self._cancel_startup_delay_task()
        self._cancel_delay_task()
        self._handle_stop()
        if self._tilt_strategy is not None:
            self._tilt_strategy.snap_trackers_to_physical(
                self.travel_calc, self.tilt_calc
            )
        if not self._triggered_externally and was_active:
            await self._send_stop()
        self.async_write_ha_state()
        self._last_command = None

    # --- External state change handlers ---

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle external state change in toggle mode.

        In toggle mode, each switch transition toggles the motor.
        We react to both OFF->ON and ON->OFF (unlike pulse mode which
        only reacts to ON->OFF), since the user's switch may be latching
        (alternates ON/OFF on each click).

        A debounce prevents double-triggering for momentary switches that
        produce OFF->ON->OFF per click. The debounce window is pulse_time + 0.5s
        to account for switches that stay ON for approximately pulse_time before
        auto-resetting.
        """
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

        Same debounce and toggle logic as the main cover handler.
        If tilt is already moving, treat any toggle as stop.
        """
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
                    "_handle_external_tilt_state_change :: tilt open toggle while traveling, stopping"
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
                    "_handle_external_tilt_state_change :: tilt close toggle while traveling, stopping"
                )
                await self.async_stop_cover()
            else:
                self._log(
                    "_handle_external_tilt_state_change :: external tilt close toggle detected"
                )
                await self.async_close_cover_tilt()

    # --- Internal relay commands ---

    async def _send_open(self) -> None:
        if self._switch_is_on(self._close_switch_entity_id):
            self._mark_switch_pending(self._close_switch_entity_id, 1)
        self._mark_switch_pending(self._open_switch_entity_id, 2)
        if self._stop_switch_entity_id is not None:
            if self._switch_is_on(self._stop_switch_entity_id):
                self._mark_switch_pending(self._stop_switch_entity_id, 1)
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
        if self._stop_switch_entity_id is not None:
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": self._stop_switch_entity_id},
                False,
            )
        await sleep(self._pulse_time)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._open_switch_entity_id},
            False,
        )

    async def _send_close(self) -> None:
        if self._switch_is_on(self._open_switch_entity_id):
            self._mark_switch_pending(self._open_switch_entity_id, 1)
        self._mark_switch_pending(self._close_switch_entity_id, 2)
        if self._stop_switch_entity_id is not None:
            if self._switch_is_on(self._stop_switch_entity_id):
                self._mark_switch_pending(self._stop_switch_entity_id, 1)
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
        if self._stop_switch_entity_id is not None:
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": self._stop_switch_entity_id},
                False,
            )
        await sleep(self._pulse_time)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._close_switch_entity_id},
            False,
        )

    async def _send_stop(self) -> None:
        if self._last_command == SERVICE_CLOSE_COVER:
            self._mark_switch_pending(self._close_switch_entity_id, 2)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._close_switch_entity_id},
                False,
            )
            await sleep(self._pulse_time)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": self._close_switch_entity_id},
                False,
            )
        elif self._last_command == SERVICE_OPEN_COVER:
            self._mark_switch_pending(self._open_switch_entity_id, 2)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._open_switch_entity_id},
                False,
            )
            await sleep(self._pulse_time)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": self._open_switch_entity_id},
                False,
            )
        else:
            self._log("_send_stop :: toggle mode with no last command, skipping")
