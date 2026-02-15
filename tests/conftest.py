"""Shared fixtures for cover_time_based tests."""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.cover_time_based.cover import (
    CoverTimeBased,
    DEFAULT_PULSE_TIME,
    DEFAULT_TRAVEL_TIME,
    INPUT_MODE_SWITCH,
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
    """Return a factory that creates a CoverTimeBased wired to a mock hass."""

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

        cover = CoverTimeBased(
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
