"""Shared fixtures for cover_time_based tests."""

import asyncio
import logging
from asyncio import sleep

import pytest
from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
)

from custom_components.cover_time_based.cover import (
    CoverTimeBased,
    DEFAULT_PULSE_TIME,
    DEFAULT_TRAVEL_TIME,
    INPUT_MODE_PULSE,
    INPUT_MODE_SWITCH,
    INPUT_MODE_TOGGLE,
)

_LOGGER = logging.getLogger(__name__)


class CoverTimeBasedTest(CoverTimeBased):
    """Concrete test subclass implementing the relay logic from the original code."""

    async def _send_close(self) -> None:
        """Send the close command to the underlying device."""
        if self._cover_entity_id is not None:
            await self.hass.services.async_call(
                "cover",
                "close_cover",
                {"entity_id": self._cover_entity_id},
                False,
            )
        else:
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

            if self._input_mode in (INPUT_MODE_PULSE, INPUT_MODE_TOGGLE):
                await sleep(self._pulse_time)

                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_off",
                    {"entity_id": self._close_switch_entity_id},
                    False,
                )

    async def _send_open(self) -> None:
        """Send the open command to the underlying device."""
        if self._cover_entity_id is not None:
            await self.hass.services.async_call(
                "cover",
                "open_cover",
                {"entity_id": self._cover_entity_id},
                False,
            )
        else:
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
            if self._input_mode in (INPUT_MODE_PULSE, INPUT_MODE_TOGGLE):
                await sleep(self._pulse_time)

                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_off",
                    {"entity_id": self._open_switch_entity_id},
                    False,
                )

    async def _send_stop(self) -> None:
        """Send the stop command to the underlying device."""
        if self._cover_entity_id is not None:
            await self.hass.services.async_call(
                "cover",
                "stop_cover",
                {"entity_id": self._cover_entity_id},
                False,
            )
        elif self._input_mode == INPUT_MODE_TOGGLE:
            # Toggle mode: pulse the last-used direction button to stop
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
                _LOGGER.debug(
                    "_async_handle_command :: STOP in toggle mode with no last command, skipping"
                )
        else:
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
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_on",
                    {"entity_id": self._stop_switch_entity_id},
                    False,
                )

                if self._input_mode == INPUT_MODE_PULSE:
                    await sleep(self._pulse_time)

                    await self.hass.services.async_call(
                        "homeassistant",
                        "turn_off",
                        {"entity_id": self._stop_switch_entity_id},
                        False,
                    )


@pytest.fixture
def make_hass():
    """Return a factory that creates a minimal mock HA instance."""

    def _make():
        hass = MagicMock()
        hass.services.async_call = AsyncMock()
        hass.async_create_task = lambda coro: asyncio.ensure_future(coro)
        return hass

    return _make


@pytest.fixture
def make_cover(make_hass):
    """Return a factory that creates a CoverTimeBasedTest wired to a mock hass."""

    def _make(
        input_mode=INPUT_MODE_SWITCH,
        cover_entity_id=None,
        open_switch="switch.open",
        close_switch="switch.close",
        stop_switch=None,
        pulse_time=DEFAULT_PULSE_TIME,
        travel_time_down=DEFAULT_TRAVEL_TIME,
        travel_time_up=DEFAULT_TRAVEL_TIME,
    ):
        # When wrapping a real cover entity, the switch entities are unused
        if cover_entity_id is not None:
            open_switch = None
            close_switch = None
            stop_switch = None

        cover = CoverTimeBasedTest(
            device_id="test_cover",
            name="Test Cover",
            travel_moves_with_tilt=False,
            travel_time_down=travel_time_down,
            travel_time_up=travel_time_up,
            tilt_time_down=None,
            tilt_time_up=None,
            travel_delay_at_end=None,
            min_movement_time=None,
            travel_startup_delay=None,
            tilt_startup_delay=None,
            open_switch_entity_id=open_switch,
            close_switch_entity_id=close_switch,
            stop_switch_entity_id=stop_switch,
            input_mode=input_mode,
            pulse_time=pulse_time,
            cover_entity_id=cover_entity_id,
        )
        cover.hass = make_hass()
        return cover

    return _make
