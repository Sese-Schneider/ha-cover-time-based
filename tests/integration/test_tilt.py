"""Integration tests for tilt lifecycle.

Tests sequential tilt constraints through real HA service calls.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch
import time as time_mod

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from .conftest import DOMAIN


class MockTime:
    """Controllable time source for TravelCalculator."""

    def __init__(self):
        self._base = time_mod.time()
        self._total_offset = 0.0

    def time(self):
        return self._base + self._total_offset

    def advance(self, seconds: float):
        self._total_offset += seconds


def _get_cover_entity(hass: HomeAssistant):
    """Return the CoverTimeBased entity object."""
    entity_comp = hass.data["entity_components"]["cover"]
    entities = [e for e in entity_comp.entities if e.entity_id == "cover.test_cover"]
    assert entities, "Cover entity not found"
    return entities[0]


async def test_sequential_tilt_moves_before_travel(
    hass: HomeAssistant, setup_input_booleans
):
    """Sequential tilt: opening from closed moves tilt to 100% before travel.

    When cover is at position 0 with tilt at partial position,
    calling open_cover should first tilt to 100%, then travel.
    """
    options = {
        "control_mode": "switch",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 10.0,
        "travel_time_close": 10.0,
        "tilt_mode": "sequential",
        "tilt_time_open": 2.0,
        "tilt_time_close": 2.0,
        "endpoint_runon_time": 0,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, title="Test Cover", data={}, options=options
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    mt = MockTime()
    with patch("time.time", mt.time):
        cover = _get_cover_entity(hass)

        # Start at position 0 (closed), tilt at 30%
        await cover.set_known_position(position=0)
        await cover.set_known_tilt_position(tilt_position=30)
        await hass.async_block_till_done()
        assert cover.current_cover_position == 0
        assert cover.current_cover_tilt_position == 30

        # Open cover — sequential tilt should tilt first
        await hass.services.async_call(
            "cover", "open_cover", {"entity_id": "cover.test_cover"}, blocking=True
        )
        await hass.async_block_till_done()

        # Tilt should be moving first (open switch on for tilt pre-step)
        assert cover.is_opening

        # Advance past tilt time (2s for tilt + margin)
        mt.advance(3.0)
        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=3), fire_all=True
        )
        await hass.async_block_till_done()

        # After tilt completes, travel should begin
        # Tilt should be at 100%, position should be increasing
        tilt = cover.current_cover_tilt_position
        assert tilt is not None
        assert tilt >= 90, f"Expected tilt >= 90% after pre-step, got {tilt}%"

        # Advance past travel time
        mt.advance(12.0)
        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=12), fire_all=True
        )
        await hass.async_block_till_done()

        # Position should be at 100%
        assert cover.current_cover_position == 100


async def test_sequential_tilt_rejected_when_not_at_endpoint(
    hass: HomeAssistant, setup_input_booleans
):
    """Sequential tilt: tilt commands are rejected when cover is not at an endpoint.

    In sequential mode, tilt is only allowed at position 0 or 100.
    """
    options = {
        "control_mode": "switch",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 10.0,
        "travel_time_close": 10.0,
        "tilt_mode": "sequential",
        "tilt_time_open": 2.0,
        "tilt_time_close": 2.0,
        "endpoint_runon_time": 0,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, title="Test Cover", data={}, options=options
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = _get_cover_entity(hass)

    # Position at 50% (mid-range), tilt at 50%
    await cover.set_known_position(position=50)
    await cover.set_known_tilt_position(tilt_position=50)
    await hass.async_block_till_done()

    # Try to set tilt — should be silently ignored since not at endpoint
    await hass.services.async_call(
        "cover",
        "set_cover_tilt_position",
        {"entity_id": "cover.test_cover", "tilt_position": 80},
        blocking=True,
    )
    await hass.async_block_till_done()

    # Tilt should not have changed from 50%
    assert cover.current_cover_tilt_position == 50
