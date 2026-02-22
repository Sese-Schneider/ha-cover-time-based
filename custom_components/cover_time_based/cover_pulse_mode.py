"""Momentary pulse mode cover."""

import asyncio
from asyncio import sleep

from .cover_switch import SwitchCoverTimeBased


class PulseModeCover(SwitchCoverTimeBased):
    """Cover controlled by momentary pulse relays (pulse mode).

    In pulse mode, the direction switch is turned ON for a short pulse
    (pulse_time seconds) then turned OFF. The motor controller latches
    on the ON edge — the OFF is just relay cleanup.

    The send methods return immediately after the ON edge so that position
    tracking starts from the moment the motor begins moving. The pulse
    completion (sleep + turn_off) runs in the background.
    """

    def __init__(self, pulse_time, **kwargs):
        super().__init__(**kwargs)
        self._pulse_time = pulse_time

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
        # Motor controller latches on ON edge; complete pulse in background
        self.hass.async_create_task(self._complete_pulse(self._open_switch_entity_id))

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
        # Motor controller latches on ON edge; complete pulse in background
        self.hass.async_create_task(self._complete_pulse(self._close_switch_entity_id))

    async def _send_stop(self) -> None:
        if self._switch_is_on(self._close_switch_entity_id):
            self._mark_switch_pending(self._close_switch_entity_id, 1)
        if self._switch_is_on(self._open_switch_entity_id):
            self._mark_switch_pending(self._open_switch_entity_id, 1)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._close_switch_entity_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._open_switch_entity_id},
            False,
        )
        if self._stop_switch_entity_id is not None:
            self._mark_switch_pending(self._stop_switch_entity_id, 2)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._stop_switch_entity_id},
                False,
            )
            # Motor stops on ON edge; complete pulse in background
            self.hass.async_create_task(
                self._complete_pulse(self._stop_switch_entity_id)
            )

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

    async def _send_tilt_stop(self) -> None:
        if self._switch_is_on(self._tilt_open_switch_id):
            self._mark_switch_pending(self._tilt_open_switch_id, 1)
        if self._switch_is_on(self._tilt_close_switch_id):
            self._mark_switch_pending(self._tilt_close_switch_id, 1)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_open_switch_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_close_switch_id},
            False,
        )
        if self._tilt_stop_switch_id:
            self._mark_switch_pending(self._tilt_stop_switch_id, 2)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._tilt_stop_switch_id},
                False,
            )
            self.hass.async_create_task(self._complete_pulse(self._tilt_stop_switch_id))
