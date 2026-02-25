"""Integration tests for mode-specific behavior.

Tests toggle mode stop-before-reverse and pulse mode relay pulsing.
"""

from __future__ import annotations

import asyncio
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


async def test_toggle_stop_before_reverse(hass: HomeAssistant, setup_input_booleans):
    """Toggle mode: closing while opening sends stop then close."""
    real_sleep = asyncio.sleep

    async def instant_sleep(delay, *args, **kwargs):
        await real_sleep(0)

    options = {
        "control_mode": "toggle",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 10.0,
        "travel_time_close": 10.0,
        "endpoint_runon_time": 0,
        "pulse_time": 0.5,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, title="Test Cover", data={}, options=options
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    mt = MockTime()
    with patch("time.time", mt.time), patch("asyncio.sleep", instant_sleep):
        cover = _get_cover_entity(hass)

        await cover.set_known_position(position=50)
        await hass.async_block_till_done()

        # Start opening
        await hass.services.async_call(
            "cover", "open_cover", {"entity_id": "cover.test_cover"}, blocking=True
        )
        await hass.async_block_till_done()
        assert cover.is_opening

        mt.advance(2.0)
        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=2), fire_all=True
        )
        await hass.async_block_till_done()

        # Now close — toggle mode should stop first, then close
        await hass.services.async_call(
            "cover", "close_cover", {"entity_id": "cover.test_cover"}, blocking=True
        )
        await hass.async_block_till_done()

        # Cover should now be closing (stop + reverse happened)
        assert cover.is_closing


async def test_pulse_mode_relay_pulsing(hass: HomeAssistant, setup_input_booleans):
    """Pulse mode: open switch pulses on then off after pulse_time."""
    real_sleep = asyncio.sleep

    async def instant_sleep(delay, *args, **kwargs):
        await real_sleep(0)

    options = {
        "control_mode": "pulse",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "stop_switch_entity_id": "input_boolean.stop_switch",
        "travel_time_open": 10.0,
        "travel_time_close": 10.0,
        "endpoint_runon_time": 0,
        "pulse_time": 0.5,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, title="Test Cover", data={}, options=options
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    mt = MockTime()
    with patch("time.time", mt.time), patch("asyncio.sleep", instant_sleep):
        cover = _get_cover_entity(hass)

        await cover.set_known_position(position=50)
        await hass.async_block_till_done()

        # Open the cover
        await hass.services.async_call(
            "cover", "open_cover", {"entity_id": "cover.test_cover"}, blocking=True
        )
        await hass.async_block_till_done()

        # In pulse mode, switch should pulse on then off
        # With instant sleep, the pulse completes immediately
        assert hass.states.get("input_boolean.open_switch").state == "off"
        assert cover.is_opening

        # Stop the cover — should pulse stop switch
        mt.advance(2.0)
        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=2), fire_all=True
        )
        await hass.async_block_till_done()

        await hass.services.async_call(
            "cover", "stop_cover", {"entity_id": "cover.test_cover"}, blocking=True
        )
        await hass.async_block_till_done()

        # Stop switch should have pulsed (on then off with instant sleep)
        assert hass.states.get("input_boolean.stop_switch").state == "off"
        assert not cover.is_opening
        assert not cover.is_closing
