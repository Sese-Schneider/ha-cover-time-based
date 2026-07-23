"""Integration tests for mode-specific behavior.

Tests toggle mode stop-before-reverse and pulse mode relay pulsing.
"""

from __future__ import annotations

import time as time_mod
from datetime import timedelta
from unittest.mock import patch

import pytest
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


async def test_toggle_in_motion_close_stops(hass: HomeAssistant, setup_input_booleans):
    """Toggle mode: UI close_cover while opening just stops (no reverse).

    Reversing direction now requires either a second click or a
    set_cover_position call (which keeps its stop-then-reverse behavior).
    """
    options = {
        "control_mode": "toggle",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 10.0,
        "travel_time_close": 10.0,
        "endpoint_runon_time": 0,
        "pulse_time": 0,
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

        # Now close — UI click stops the cover (does not reverse)
        await hass.services.async_call(
            "cover", "close_cover", {"entity_id": "cover.test_cover"}, blocking=True
        )
        await hass.async_block_till_done()

        # Cover should be stopped, not closing
        assert not cover.is_opening
        assert not cover.is_closing

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_toggle_same_direction_retarget_does_not_repulse(
    hass: HomeAssistant, setup_input_booleans
):
    """Toggle mode: retargeting in the same direction must not re-pulse.

    Reproduces the runaway-cover bug: a cover was moving (closing) when a
    second set_cover_position arrived for a still-lower target (same
    direction). The old code re-issued the CLOSE command, which in toggle
    mode is a second same-direction pulse that *stops* the motor — desyncing
    it from the position tracker. The later auto-stop pulse then restarted
    the motor, which ran to the endpoint.

    The motor is already moving the right way, so no new directional pulse
    should be sent: only the initial start pulse and the final stop pulse.
    """
    options = {
        "control_mode": "toggle",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 10.0,
        "travel_time_close": 10.0,
        "endpoint_runon_time": 0,
        "pulse_time": 0,
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
        # Fire HA time changes off a single base, with offsets that match the
        # cumulative MockTime advance, so the scheduler and TravelCalculator
        # clocks stay aligned.
        now = dt_util.utcnow()

        # Cover fully open
        await cover.set_known_position(position=100)
        await hass.async_block_till_done()

        with patch.object(cover, "_send_close", wraps=cover._send_close) as send_close:
            # First target: start closing toward 60
            await hass.services.async_call(
                "cover",
                "set_cover_position",
                {"entity_id": "cover.test_cover", "position": 60},
                blocking=True,
            )
            await hass.async_block_till_done()
            assert cover.is_closing
            assert send_close.call_count == 1, "initial close should pulse once"

            # Let it travel partway (to ~80)
            mt.advance(2.0)
            async_fire_time_changed(hass, now + timedelta(seconds=2), fire_all=True)
            await hass.async_block_till_done()

            # Second target while still closing: lower again (same direction).
            # Must NOT re-pulse the close switch.
            await hass.services.async_call(
                "cover",
                "set_cover_position",
                {"entity_id": "cover.test_cover", "position": 30},
                blocking=True,
            )
            await hass.async_block_till_done()
            assert cover.is_closing
            assert send_close.call_count == 1, (
                "same-direction retarget must not re-pulse the motor"
            )

            # Travel long enough to reach the new target (30) and stop.
            mt.advance(6.0)
            async_fire_time_changed(hass, now + timedelta(seconds=8), fire_all=True)
            await hass.async_block_till_done()

        # Stopped at the new target, not the original one.
        assert not cover.is_closing
        assert cover.current_cover_position == 30
        # Exactly one directional start was issued for the whole sequence.
        # (The auto-stop goes through _send_stop, not _send_close.)
        assert send_close.call_count == 1

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_pulse_mode_relay_pulsing(hass: HomeAssistant, setup_input_booleans):
    """Pulse mode: open switch pulses on then off after pulse_time."""
    options = {
        "control_mode": "pulse",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "stop_switch_entity_id": "input_boolean.stop_switch",
        "travel_time_open": 10.0,
        "travel_time_close": 10.0,
        "endpoint_runon_time": 0,
        "pulse_time": 0,
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

        await cover.set_known_position(position=50)
        await hass.async_block_till_done()

        # Open the cover
        await hass.services.async_call(
            "cover", "open_cover", {"entity_id": "cover.test_cover"}, blocking=True
        )
        await hass.async_block_till_done()

        # In pulse mode, switch should pulse on then off (instant with pulse_time=0)
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

        # Stop switch should have pulsed (on then off, instant with pulse_time=0)
        assert hass.states.get("input_boolean.stop_switch").state == "off"
        assert not cover.is_opening
        assert not cover.is_closing

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    "extra_options",
    [
        pytest.param({"control_mode": "switch"}, id="switch"),
        pytest.param(
            {
                "control_mode": "pulse",
                "stop_switch_entity_id": "input_boolean.stop_switch",
                "pulse_time": 0,
            },
            id="pulse",
        ),
    ],
)
async def test_same_direction_retarget_does_not_repulse(
    hass: HomeAssistant, setup_input_booleans, extra_options
):
    """Switch and pulse modes: same-direction retarget must not re-command.

    These modes never had the toggle-mode runaway (a held relay / a
    dedicated stop switch absorb a redundant directional command), but the
    shared set_position fix should still skip the redundant command so a
    same-direction slider drag issues exactly one directional start.
    """
    options = {
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 10.0,
        "travel_time_close": 10.0,
        "endpoint_runon_time": 0,
        **extra_options,
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
        now = dt_util.utcnow()

        await cover.set_known_position(position=100)
        await hass.async_block_till_done()

        with patch.object(cover, "_send_close", wraps=cover._send_close) as send_close:
            await hass.services.async_call(
                "cover",
                "set_cover_position",
                {"entity_id": "cover.test_cover", "position": 60},
                blocking=True,
            )
            await hass.async_block_till_done()
            assert cover.is_closing
            assert send_close.call_count == 1

            mt.advance(2.0)
            async_fire_time_changed(hass, now + timedelta(seconds=2), fire_all=True)
            await hass.async_block_till_done()

            # Same-direction retarget while still closing.
            await hass.services.async_call(
                "cover",
                "set_cover_position",
                {"entity_id": "cover.test_cover", "position": 30},
                blocking=True,
            )
            await hass.async_block_till_done()
            assert cover.is_closing
            assert send_close.call_count == 1, (
                "same-direction retarget must not re-command the motor"
            )

            # Reaches the new target and stops there.
            mt.advance(6.0)
            async_fire_time_changed(hass, now + timedelta(seconds=8), fire_all=True)
            await hass.async_block_till_done()

        assert not cover.is_closing
        assert cover.current_cover_position == 30
        assert send_close.call_count == 1

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
