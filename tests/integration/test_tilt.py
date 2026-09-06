"""Integration tests for tilt lifecycle.

Tests sequential tilt constraints through real HA service calls.
"""

from __future__ import annotations

import time
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

from custom_components.cover_time_based import travel_calculator
from tests.helpers import FakeClock

from .conftest import DOMAIN


def _get_cover_entity(hass: HomeAssistant):
    """Return the CoverTimeBased entity object."""
    entity_comp = hass.data[DATA_INSTANCES]["cover"]
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

    mt = FakeClock(wall=time.time(), mono=time.monotonic())
    with patch.object(travel_calculator, "time", mt):
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

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


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

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_sequential_open_close_drives_close_relay_from_top(
    hass: HomeAssistant, setup_input_booleans
):
    """sequential_open: closing from the top sends the close relay (motor down).

    End-to-end check that the inverted tilt direction doesn't leak into the
    main travel direction — close is still the close relay, open is still
    the open relay. Slats stay at implicit (tilt=0) during the travel.
    """
    options = {
        "control_mode": "switch",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 10.0,
        "travel_time_close": 10.0,
        "tilt_mode": "sequential_open",
        "tilt_time_open": 2.0,
        "tilt_time_close": 2.0,
        "endpoint_runon_time": 0,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, title="Test Cover", data={}, options=options
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = _get_cover_entity(hass)
    await cover.set_known_position(position=100)
    await cover.set_known_tilt_position(tilt_position=0)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "cover", "close_cover", {"entity_id": "cover.test_cover"}, blocking=True
    )
    await hass.async_block_till_done()

    # Close switch on, open switch off — travel driven by the close relay
    # (tilt=0 is implicit, no tilt pre-step needed).
    assert hass.states.get("input_boolean.close_switch").state == "on"
    assert hass.states.get("input_boolean.open_switch").state == "off"

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_sequential_open_tilt_open_drives_close_relay(
    hass: HomeAssistant, setup_input_booleans
):
    """sequential_open: opening the tilt sends the close relay (motor further down).

    This is the key inversion: articulating slats "open" physically requires
    driving the motor down past the cover-closed position.
    """
    options = {
        "control_mode": "switch",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 10.0,
        "travel_time_close": 10.0,
        "tilt_mode": "sequential_open",
        "tilt_time_open": 2.0,
        "tilt_time_close": 2.0,
        "endpoint_runon_time": 0,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, title="Test Cover", data={}, options=options
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = _get_cover_entity(hass)
    await cover.set_known_position(position=0)
    await cover.set_known_tilt_position(tilt_position=0)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "cover",
        "open_cover_tilt",
        {"entity_id": "cover.test_cover"},
        blocking=True,
    )
    await hass.async_block_till_done()

    # Inverted: opening the tilt drives the motor DOWN.
    assert hass.states.get("input_boolean.close_switch").state == "on"
    assert hass.states.get("input_boolean.open_switch").state == "off"

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_same_direction_retarget_tilt_cover_does_not_reissue_command(
    hass: HomeAssistant, setup_input_booleans
):
    """Same-direction retarget on a tilt cover must not re-issue travel.

    The same-direction retarget fast-path is taken for tilt-coupled covers
    too. It must recompute tilt coupling for the new target (it runs through
    _plan_tilt_for_travel like a normal move) while skipping the redundant
    travel command, and the cover must still stop at the new target.
    """
    options = {
        "control_mode": "switch",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 10.0,
        "travel_time_close": 10.0,
        "tilt_mode": "inline",
        "tilt_time_open": 1.0,
        "tilt_time_close": 1.0,
        "endpoint_runon_time": 0,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, title="Test Cover", data={}, options=options
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    mt = FakeClock(wall=time.time(), mono=time.monotonic())
    with patch.object(travel_calculator, "time", mt):
        cover = _get_cover_entity(hass)
        # Fire HA time changes off a single base with offsets matching the
        # cumulative FakeClock advance, keeping the scheduler and
        # TravelCalculator clocks aligned.
        now = dt_util.utcnow()

        await cover.set_known_position(position=100)
        await cover.set_known_tilt_position(tilt_position=50)
        await hass.async_block_till_done()

        with patch.object(cover, "_send_close", wraps=cover._send_close) as send_close:
            # Mid-position move (closing).
            await hass.services.async_call(
                "cover",
                "set_cover_position",
                {"entity_id": "cover.test_cover", "position": 60},
                blocking=True,
            )
            await hass.async_block_till_done()
            assert cover.is_closing
            assert send_close.call_count == 1

            # Let the inline tilt pre-step finish and travel get underway.
            mt.advance(2.0)
            async_fire_time_changed(hass, now + timedelta(seconds=2), fire_all=True)
            await hass.async_block_till_done()
            assert cover.travel_calc.is_traveling()

            # Retarget (same direction) to a lower mid-position.
            await hass.services.async_call(
                "cover",
                "set_cover_position",
                {"entity_id": "cover.test_cover", "position": 30},
                blocking=True,
            )
            await hass.async_block_till_done()
            assert cover.is_closing
            assert send_close.call_count == 1, (
                "same-direction retarget must not re-command a tilt cover"
            )

            # Reaches the new target and stops there.
            mt.advance(8.0)
            async_fire_time_changed(hass, now + timedelta(seconds=10), fire_all=True)
            await hass.async_block_till_done()

        assert not cover.is_closing
        assert cover.current_cover_position == 30

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


class TiltMotor:
    """Physical tilt direction driven by latching or momentary relay commands."""

    def __init__(self, mode):
        self.mode = mode
        self.direction = None
        self.calls = []

    async def handle(self, call):
        entity = call.data["entity_id"]
        self.calls.append((call.service, entity))
        if entity not in ("input_boolean.tilt_open", "input_boolean.tilt_close"):
            return
        direction = "open" if entity.endswith("tilt_open") else "close"
        if self.mode == "switch":
            if call.service == "turn_on":
                self.direction = direction
            elif self.direction == direction:
                self.direction = None
        elif call.service == "turn_on":
            if self.direction is None:
                self.direction = direction
            elif (self.mode == "toggle" and self.direction == direction) or (
                self.mode == "toggle_opposite" and self.direction != direction
            ):
                self.direction = None


class TestDisplacedTiltMotor:
    """Travel displacement stops a departing motor without restarting an arrival."""

    @pytest.fixture
    def base_options(self, control_mode):
        return {
            "control_mode": control_mode,
            "open_switch_entity_id": "input_boolean.open_switch",
            "close_switch_entity_id": "input_boolean.close_switch",
            "travel_time_open": 30.0,
            "travel_time_close": 30.0,
            "tilt_mode": "dual_motor",
            "tilt_time_open": 5.0,
            "tilt_time_close": 5.0,
            "tilt_open_switch": "input_boolean.tilt_open",
            "tilt_close_switch": "input_boolean.tilt_close",
        }

    @pytest.fixture
    def tilt_motor(self, hass, setup_cover, control_mode):
        motor = TiltMotor(control_mode)
        hass.services.async_register("homeassistant", "turn_on", motor.handle)
        hass.services.async_register("homeassistant", "turn_off", motor.handle)
        return motor

    @pytest.mark.parametrize("control_mode", ["toggle", "toggle_opposite", "switch"])
    async def test_noop_travel_stops_tilt_departing_endpoint(self, hass, tilt_motor):
        """A tilt move just leaving 100 must stop even while its tracker reads 100."""
        cover = _get_cover_entity(hass)
        await cover.set_known_position(position=50)
        await cover.set_known_tilt_position(tilt_position=100)
        with patch.object(travel_calculator, "time", FakeClock(wall=1000, mono=1000)):
            await hass.services.async_call(
                "cover",
                "set_cover_tilt_position",
                {"entity_id": cover.entity_id, "tilt_position": 30},
                blocking=True,
            )
            await hass.async_block_till_done()
            assert tilt_motor.direction == "close"
            assert cover.tilt_calc.is_traveling()
            assert cover.tilt_calc.current_position() == 100
            tilt_motor.calls.clear()

            await hass.services.async_call(
                "cover",
                "set_cover_position",
                {"entity_id": cover.entity_id, "position": 50},
                blocking=True,
            )
            await hass.async_block_till_done()
            assert tilt_motor.direction is None, tilt_motor.calls
            assert not cover.tilt_calc.is_traveling()
            if tilt_motor.mode != "switch":
                assert cover._last_tilt_direction is None

    @pytest.mark.parametrize("control_mode", ["toggle", "toggle_opposite"])
    async def test_noop_travel_does_not_repulse_tilt_arrived_at_endpoint(
        self, hass, tilt_motor
    ):
        """Arrival before the auto-updater tick must leave a self-stopped motor idle."""
        cover = _get_cover_entity(hass)
        await cover.set_known_position(position=50)
        await cover.set_known_tilt_position(tilt_position=50)
        mt = FakeClock(wall=time.time(), mono=time.monotonic())
        with patch.object(travel_calculator, "time", mt):
            await hass.services.async_call(
                "cover",
                "set_cover_tilt_position",
                {"entity_id": cover.entity_id, "tilt_position": 100},
                blocking=True,
            )
            await hass.async_block_till_done()
            assert tilt_motor.direction == "open"
            assert cover.tilt_calc.is_traveling()

            # The motor self-stops at its limit before the next updater tick.
            mt.advance(3)
            tilt_motor.direction = None
            assert cover.tilt_calc.current_position() == 100
            assert not cover.tilt_calc.is_traveling()
            assert cover._moving_tilt_motor
            tilt_motor.calls.clear()

            for _ in range(2):
                await hass.services.async_call(
                    "cover",
                    "set_cover_position",
                    {"entity_id": cover.entity_id, "position": 50},
                    blocking=True,
                )
                await hass.async_block_till_done()

            assert tilt_motor.calls == []
            assert tilt_motor.direction is None
            assert not cover.tilt_calc.is_traveling()
            assert cover._last_tilt_direction is None
