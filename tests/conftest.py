"""Shared fixtures for cover_time_based tests."""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.cover_time_based.cover import (
    DEFAULT_PULSE_TIME,
    DEFAULT_TRAVEL_TIME,
    INPUT_MODE_SWITCH,
    _create_cover_from_options,
    CONF_COVER_ENTITY_ID,
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_DEVICE_TYPE,
    CONF_INPUT_MODE,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_TRAVELLING_TIME_DOWN,
    CONF_TRAVELLING_TIME_UP,
    DEVICE_TYPE_COVER,
    DEVICE_TYPE_SWITCH,
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
    """Return a factory that creates the appropriate cover subclass wired to a mock hass."""

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
        if cover_entity_id is not None:
            options = {
                CONF_DEVICE_TYPE: DEVICE_TYPE_COVER,
                CONF_COVER_ENTITY_ID: cover_entity_id,
                CONF_TRAVELLING_TIME_DOWN: travel_time_down,
                CONF_TRAVELLING_TIME_UP: travel_time_up,
            }
        else:
            options = {
                CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
                CONF_OPEN_SWITCH_ENTITY_ID: open_switch,
                CONF_CLOSE_SWITCH_ENTITY_ID: close_switch,
                CONF_STOP_SWITCH_ENTITY_ID: stop_switch,
                CONF_INPUT_MODE: input_mode,
                CONF_PULSE_TIME: pulse_time,
                CONF_TRAVELLING_TIME_DOWN: travel_time_down,
                CONF_TRAVELLING_TIME_UP: travel_time_up,
            }

        cover = _create_cover_from_options(
            options,
            device_id="test_cover",
            name="Test Cover",
        )
        cover.hass = make_hass()
        return cover

    return _make
