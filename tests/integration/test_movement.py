"""Integration tests for movement lifecycle.

Tests open/close/stop, position tracking, auto-stop, and endpoint resync
through the real HA service calls and event bus.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import patch
import time as time_mod

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from .conftest import DOMAIN


@pytest.fixture
def base_options():
    """Short travel times, no endpoint run-on for basic tests."""
    return {
        "control_mode": "switch",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 10.0,
        "travel_time_close": 10.0,
        "endpoint_runon_time": 0,
    }


def _get_cover_entity(hass: HomeAssistant):
    """Return the CoverTimeBased entity object (not just state)."""
    entity_comp = hass.data["entity_components"]["cover"]
    entities = [e for e in entity_comp.entities if e.entity_id == "cover.test_cover"]
    assert entities, "Cover entity not found"
    return entities[0]


class MockTime:
    """Controllable time source for TravelCalculator.

    Patches time.time so the TravelCalculator sees time advancing.
    Does NOT interfere with async_fire_time_changed which relies on
    the real time.time for its mock_seconds_into_future calculation.
    """

    def __init__(self):
        self._base = time_mod.time()
        self._total_offset = 0.0

    @property
    def real_base(self):
        return self._base

    def time(self):
        return self._base + self._total_offset

    def advance(self, seconds: float):
        self._total_offset += seconds


async def _advance_time(hass: HomeAssistant, mock_time: MockTime, seconds: float):
    """Advance mock time.time and fire HA timer handles.

    Uses fire_all=True to fire ALL scheduled timer handles (regardless
    of how far in the future they're scheduled), since async_track_time_interval
    uses loop.call_at which needs this to fire in tests.
    """
    mock_time.advance(seconds)
    # We need a future timestamp for _async_fire_time_changed to fire the
    # scheduled timer handles. fire_all=True fires all handles regardless.
    future = dt_util.utcnow() + timedelta(seconds=seconds)
    async_fire_time_changed(hass, future, fire_all=True)
    await hass.async_block_till_done()


@pytest.fixture
def mock_time():
    """Provide a controllable time source and patch time.time."""
    mt = MockTime()
    with patch("time.time", mt.time):
        yield mt


async def test_open_track_auto_stop(hass: HomeAssistant, setup_cover, mock_time):
    """Open -> position tracks upward -> auto-stops at 100%."""
    cover = _get_cover_entity(hass)

    await cover.set_known_position(position=0)
    await hass.async_block_till_done()
    assert cover.current_cover_position == 0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": "cover.test_cover"}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.states.get("input_boolean.open_switch").state == "on"

    # Advance to ~50%
    await _advance_time(hass, mock_time, 5.0)
    pos = cover.current_cover_position
    assert pos is not None
    assert 20 <= pos <= 80, f"Expected ~50%, got {pos}%"

    # Advance past full travel
    await _advance_time(hass, mock_time, 7.0)
    assert cover.current_cover_position == 100
    assert hass.states.get("input_boolean.open_switch").state == "off"


async def test_stop_during_movement(hass: HomeAssistant, setup_cover, mock_time):
    """Stop during movement freezes position at intermediate value."""
    cover = _get_cover_entity(hass)

    await cover.set_known_position(position=0)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": "cover.test_cover"}, blocking=True
    )
    await hass.async_block_till_done()

    await _advance_time(hass, mock_time, 5.0)

    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": "cover.test_cover"}, blocking=True
    )
    await hass.async_block_till_done()

    pos = cover.current_cover_position
    assert pos is not None
    assert 20 <= pos <= 80, f"Expected ~50%, got {pos}%"
    assert hass.states.get("input_boolean.open_switch").state == "off"


async def test_set_position_mid_range(hass: HomeAssistant, setup_cover, mock_time):
    """set_cover_position(50) moves to target and stops."""
    cover = _get_cover_entity(hass)

    await cover.set_known_position(position=0)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": "cover.test_cover", "position": 50},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get("input_boolean.open_switch").state == "on"

    await _advance_time(hass, mock_time, 7.0)

    pos = cover.current_cover_position
    assert pos is not None
    assert 40 <= pos <= 60, f"Expected ~50%, got {pos}%"
    assert hass.states.get("input_boolean.open_switch").state == "off"


async def test_endpoint_resync(
    hass: HomeAssistant, setup_input_booleans, base_options, mock_time
):
    """Closing when already at 0 should still fire relay + run-on."""
    options = {**base_options, "endpoint_runon_time": 2.0}
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Test Cover",
        data={},
        options=options,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = _get_cover_entity(hass)

    await cover.set_known_position(position=0)
    await hass.async_block_till_done()
    assert cover.current_cover_position == 0

    # Patch asyncio.sleep so the _delayed_stop completes instantly
    real_sleep = asyncio.sleep

    async def instant_sleep(delay, *args, **kwargs):
        await real_sleep(0)

    with patch("asyncio.sleep", instant_sleep):
        await hass.services.async_call(
            "cover", "close_cover", {"entity_id": "cover.test_cover"}, blocking=True
        )
        await hass.async_block_till_done()

    assert hass.states.get("input_boolean.close_switch").state == "off"
    assert cover.current_cover_position == 0

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
