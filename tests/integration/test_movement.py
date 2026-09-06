"""Integration tests for movement lifecycle.

Tests open/close/stop, position tracking, auto-stop, and endpoint resync
through the real HA service calls and event bus.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from tests.helpers import FakeClock

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
    entity_comp = hass.data[DATA_INSTANCES]["cover"]
    entities = [e for e in entity_comp.entities if e.entity_id == "cover.test_cover"]
    assert entities, "Cover entity not found"
    return entities[0]


async def _advance_time(hass: HomeAssistant, mock_clock: FakeClock, seconds: float):
    """Advance the calculator's clock and fire HA timer handles.

    Uses fire_all=True to fire ALL scheduled timer handles (regardless
    of how far in the future they're scheduled), since async_track_time_interval
    uses loop.call_at which needs this to fire in tests.
    """
    mock_clock.advance(seconds)
    # We need a future timestamp for _async_fire_time_changed to fire the
    # scheduled timer handles. fire_all=True fires all handles regardless.
    future = dt_util.utcnow() + timedelta(seconds=seconds)
    async_fire_time_changed(hass, future, fire_all=True)
    await hass.async_block_till_done()


async def test_open_track_auto_stop(hass: HomeAssistant, setup_cover, mock_clock):
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
    await _advance_time(hass, mock_clock, 5.0)
    pos = cover.current_cover_position
    assert pos is not None
    assert 20 <= pos <= 80, f"Expected ~50%, got {pos}%"

    # Advance past full travel
    await _advance_time(hass, mock_clock, 7.0)
    assert cover.current_cover_position == 100
    assert hass.states.get("input_boolean.open_switch").state == "off"


async def test_stop_during_movement(hass: HomeAssistant, setup_cover, mock_clock):
    """Stop during movement freezes position at intermediate value."""
    cover = _get_cover_entity(hass)

    await cover.set_known_position(position=0)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": "cover.test_cover"}, blocking=True
    )
    await hass.async_block_till_done()

    await _advance_time(hass, mock_clock, 5.0)

    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": "cover.test_cover"}, blocking=True
    )
    await hass.async_block_till_done()

    pos = cover.current_cover_position
    assert pos is not None
    assert 20 <= pos <= 80, f"Expected ~50%, got {pos}%"
    assert hass.states.get("input_boolean.open_switch").state == "off"


async def test_set_position_mid_range(hass: HomeAssistant, setup_cover, mock_clock):
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

    await _advance_time(hass, mock_clock, 7.0)

    pos = cover.current_cover_position
    assert pos is not None
    assert 40 <= pos <= 60, f"Expected ~50%, got {pos}%"
    assert hass.states.get("input_boolean.open_switch").state == "off"


async def test_endpoint_resync(
    hass: HomeAssistant, setup_input_booleans, base_options, mock_clock
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


async def test_resync_mid_travel_releases_the_relay(
    hass: HomeAssistant, setup_cover, mock_clock
):
    """Declaring a known position while we are driving the cover stops the motor.

    The tracker parking on its own left the open relay latched and the motor
    running to its limit while HA reported the declared position.
    """
    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": "cover.test_cover"}, blocking=True
    )
    await _advance_time(hass, mock_clock, 3)
    assert hass.states.get("input_boolean.open_switch").state == "on"

    await hass.services.async_call(
        DOMAIN,
        "resync",
        {"entity_id": "cover.test_cover", "state": "closed"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get("input_boolean.open_switch").state == "off"
    state = hass.states.get("cover.test_cover")
    assert state.state == "closed"
    assert state.attributes["current_position"] == 0

    # Nothing keeps running: the position does not creep afterwards.
    await _advance_time(hass, mock_clock, 20)
    state = hass.states.get("cover.test_cover")
    assert state.state == "closed"
    assert state.attributes["current_position"] == 0
