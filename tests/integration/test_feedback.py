"""Integration tests for switch feedback loop.

Tests echo filtering (cover-initiated switch changes are not treated as
external) and external button detection (direct switch changes trigger
movement).
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch
import time as time_mod

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed


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


async def test_echo_filtering(hass: HomeAssistant, setup_cover):
    """Cover-initiated switch ON should not be treated as external press.

    When cover.open_cover turns on the open switch, the resulting
    state_changed event should be filtered by echo detection, not
    interpreted as an external button press (which would cause double-start).
    """
    mt = MockTime()
    with patch("time.time", mt.time):
        cover = _get_cover_entity(hass)

        await cover.set_known_position(position=50)
        await hass.async_block_till_done()

        # Open the cover — this turns on the open switch internally
        await hass.services.async_call(
            "cover", "open_cover", {"entity_id": "cover.test_cover"}, blocking=True
        )
        await hass.async_block_till_done()

        # Cover should be opening, switch should be on
        assert hass.states.get("input_boolean.open_switch").state == "on"
        assert cover.is_opening

        # Advance time a bit — if echo filtering failed, the external handler
        # would have called async_open_cover again, potentially causing issues
        mt.advance(2.0)
        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=2), fire_all=True
        )
        await hass.async_block_till_done()

        # Cover should still be opening normally (not stopped or restarted)
        assert cover.is_opening
        pos = cover.current_cover_position
        assert pos is not None
        assert pos > 50, f"Expected position > 50, got {pos}"


async def test_external_button_press(hass: HomeAssistant, setup_cover):
    """Directly toggling a switch should be detected as external movement.

    Turning on the open switch without going through the cover service
    should trigger the cover to start tracking movement.
    """
    mt = MockTime()
    with patch("time.time", mt.time):
        cover = _get_cover_entity(hass)

        await cover.set_known_position(position=50)
        await hass.async_block_till_done()

        # Directly turn on the open switch (simulating physical button press)
        await hass.services.async_call(
            "input_boolean",
            "turn_on",
            {"entity_id": "input_boolean.open_switch"},
            blocking=True,
        )
        await hass.async_block_till_done()

        # The cover should detect this as an external state change
        # and start tracking movement
        assert cover.is_opening

        # Advance time to verify position is tracking
        mt.advance(3.0)
        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=3), fire_all=True
        )
        await hass.async_block_till_done()

        pos = cover.current_cover_position
        assert pos is not None
        assert pos > 50, f"Expected position > 50 after external open, got {pos}"
