"""Shared fixtures for cover_time_based tests."""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.cover_time_based.cover import (
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_COVER_ENTITY_ID,
    CONF_DEVICE_TYPE,
    CONF_INPUT_MODE,
    CONF_MIN_MOVEMENT_TIME,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_TILT_MOTOR_OVERHEAD,
    CONF_TILTING_TIME_DOWN,
    CONF_TILTING_TIME_UP,
    CONF_TRAVEL_MOTOR_OVERHEAD,
    CONF_TRAVEL_MOVES_WITH_TILT,
    CONF_TRAVELLING_TIME_DOWN,
    CONF_TRAVELLING_TIME_UP,
    DEFAULT_PULSE_TIME,
    DEFAULT_TRAVEL_TIME,
    DEVICE_TYPE_COVER,
    DEVICE_TYPE_SWITCH,
    INPUT_MODE_SWITCH,
    _create_cover_from_options,
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
    covers = []

    def _make(
        input_mode=INPUT_MODE_SWITCH,
        cover_entity_id=None,
        open_switch="switch.open",
        close_switch="switch.close",
        stop_switch=None,
        pulse_time=DEFAULT_PULSE_TIME,
        travel_time_down=DEFAULT_TRAVEL_TIME,
        travel_time_up=DEFAULT_TRAVEL_TIME,
        tilt_time_down=None,
        tilt_time_up=None,
        travel_moves_with_tilt=False,
        travel_motor_overhead=None,
        tilt_motor_overhead=None,
        min_movement_time=None,
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

        if tilt_time_down is not None:
            options[CONF_TILTING_TIME_DOWN] = tilt_time_down
        if tilt_time_up is not None:
            options[CONF_TILTING_TIME_UP] = tilt_time_up
        if travel_moves_with_tilt:
            options[CONF_TRAVEL_MOVES_WITH_TILT] = travel_moves_with_tilt
        if travel_motor_overhead is not None:
            options[CONF_TRAVEL_MOTOR_OVERHEAD] = travel_motor_overhead
        if tilt_motor_overhead is not None:
            options[CONF_TILT_MOTOR_OVERHEAD] = tilt_motor_overhead
        if min_movement_time is not None:
            options[CONF_MIN_MOVEMENT_TIME] = min_movement_time

        cover = _create_cover_from_options(
            options,
            device_id="test_cover",
            name="Test Cover",
        )
        cover.hass = make_hass()
        covers.append(cover)
        return cover

    yield _make

    for cover in covers:
        for attr in ("_startup_delay_task", "_delay_task"):
            task = getattr(cover, attr, None)
            if task is not None and not task.done():
                task.cancel()
