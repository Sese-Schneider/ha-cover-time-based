"""Shared fixtures for cover_time_based tests."""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.cover_time_based.cover import (
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_COVER_ENTITY_ID,
    CONF_DEVICE_TYPE,
    CONF_INPUT_MODE,
    CONF_MAX_TILT_ALLOWED_POSITION,
    CONF_MIN_MOVEMENT_TIME,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_SAFE_TILT_POSITION,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_ENDPOINT_RUNON_TIME,
    CONF_TILT_CLOSE_SWITCH,
    CONF_TILT_MODE,
    CONF_TILT_OPEN_SWITCH,
    CONF_TILT_STARTUP_DELAY,
    CONF_TILT_STOP_SWITCH,
    CONF_TILT_TIME_CLOSE,
    CONF_TILT_TIME_OPEN,
    CONF_TRAVEL_STARTUP_DELAY,
    CONF_TRAVEL_TIME_CLOSE,
    CONF_TRAVEL_TIME_OPEN,
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
        travel_time_close=DEFAULT_TRAVEL_TIME,
        travel_time_open=DEFAULT_TRAVEL_TIME,
        tilt_time_close=None,
        tilt_time_open=None,
        tilt_mode="none",
        travel_startup_delay=None,
        tilt_startup_delay=None,
        endpoint_runon_time=None,
        min_movement_time=None,
        tilt_open_switch=None,
        tilt_close_switch=None,
        tilt_stop_switch=None,
        safe_tilt_position=None,
        max_tilt_allowed_position=None,
    ):
        if cover_entity_id is not None:
            options = {
                CONF_DEVICE_TYPE: DEVICE_TYPE_COVER,
                CONF_COVER_ENTITY_ID: cover_entity_id,
                CONF_TRAVEL_TIME_CLOSE: travel_time_close,
                CONF_TRAVEL_TIME_OPEN: travel_time_open,
            }
        else:
            options = {
                CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
                CONF_OPEN_SWITCH_ENTITY_ID: open_switch,
                CONF_CLOSE_SWITCH_ENTITY_ID: close_switch,
                CONF_STOP_SWITCH_ENTITY_ID: stop_switch,
                CONF_INPUT_MODE: input_mode,
                CONF_PULSE_TIME: pulse_time,
                CONF_TRAVEL_TIME_CLOSE: travel_time_close,
                CONF_TRAVEL_TIME_OPEN: travel_time_open,
            }

        if tilt_time_close is not None:
            options[CONF_TILT_TIME_CLOSE] = tilt_time_close
        if tilt_time_open is not None:
            options[CONF_TILT_TIME_OPEN] = tilt_time_open
        # Default to sequential when tilt times are provided but no explicit mode
        effective_tilt_mode = tilt_mode
        if (
            effective_tilt_mode == "none"
            and tilt_time_close is not None
            and tilt_time_open is not None
        ):
            effective_tilt_mode = "sequential"
        if effective_tilt_mode != "none":
            options[CONF_TILT_MODE] = effective_tilt_mode
        if travel_startup_delay is not None:
            options[CONF_TRAVEL_STARTUP_DELAY] = travel_startup_delay
        if tilt_startup_delay is not None:
            options[CONF_TILT_STARTUP_DELAY] = tilt_startup_delay
        if endpoint_runon_time is not None:
            options[CONF_ENDPOINT_RUNON_TIME] = endpoint_runon_time
        if min_movement_time is not None:
            options[CONF_MIN_MOVEMENT_TIME] = min_movement_time
        if tilt_open_switch is not None:
            options[CONF_TILT_OPEN_SWITCH] = tilt_open_switch
        if tilt_close_switch is not None:
            options[CONF_TILT_CLOSE_SWITCH] = tilt_close_switch
        if tilt_stop_switch is not None:
            options[CONF_TILT_STOP_SWITCH] = tilt_stop_switch
        if safe_tilt_position is not None:
            options[CONF_SAFE_TILT_POSITION] = safe_tilt_position
        if max_tilt_allowed_position is not None:
            options[CONF_MAX_TILT_ALLOWED_POSITION] = max_tilt_allowed_position

        cover = _create_cover_from_options(
            options,
            device_id="test_cover",
            name="Test Cover",
        )
        cover.hass = make_hass()
        cover._config_entry_id = "test_cover"
        covers.append(cover)
        return cover

    yield _make

    for cover in covers:
        for attr in ("_startup_delay_task", "_delay_task"):
            task = getattr(cover, attr, None)
            if task is not None and not task.done():
                task.cancel()
        calibration = getattr(cover, "_calibration", None)
        if calibration is not None:
            for cal_attr in ("timeout_task", "automation_task"):
                task = getattr(calibration, cal_attr, None)
                if task is not None and not task.done():
                    task.cancel()
