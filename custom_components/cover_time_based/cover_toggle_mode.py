"""Toggle mode cover."""

import logging
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

    def __init__(
        self,
        device_id,
        name,
        travel_moves_with_tilt,
        travel_time_down,
        travel_time_up,
        tilt_time_down,
        tilt_time_up,
        travel_delay_at_end,
        min_movement_time,
        travel_startup_delay,
        tilt_startup_delay,
        open_switch_entity_id,
        close_switch_entity_id,
        stop_switch_entity_id,
        input_mode,
        pulse_time,
        cover_entity_id,
    ):
        super().__init__(
            device_id,
            name,
            travel_moves_with_tilt,
            travel_time_down,
            travel_time_up,
            tilt_time_down,
            tilt_time_up,
            travel_delay_at_end,
            min_movement_time,
            travel_startup_delay,
            tilt_startup_delay,
            open_switch_entity_id,
            close_switch_entity_id,
            stop_switch_entity_id,
            input_mode,
            pulse_time,
            cover_entity_id,
        )

    async def _send_open(self):
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

    async def _send_close(self):
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

    async def _send_stop(self):
        if self._last_command == SERVICE_CLOSE_COVER:
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
            _LOGGER.debug("_send_stop :: toggle mode with no last command, skipping")

    async def async_close_cover(self, **kwargs):
        """Close the cover; if already closing, treat as stop."""
        if self.is_closing:
            await self.async_stop_cover()
            return
        await super().async_close_cover(**kwargs)

    async def async_open_cover(self, **kwargs):
        """Open the cover; if already opening, treat as stop."""
        if self.is_opening:
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
        self._enforce_tilt_constraints()
        if was_active:
            await self._send_stop()
        self.async_write_ha_state()
        self._last_command = None
