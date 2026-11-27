"""Integration tests for release_relay_after_pulse in the toggle modes.

A toggle relay normally releases itself, so only a turn_on is sent. With the
option on the relay is an ordinary one and the cover turns it off again after
the pulse time.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.util import dt as dt_util

from tests.ha_harness import MockConfigEntry, async_fire_time_changed
from tests.helpers import FakeClock

from .conftest import DOMAIN

OPEN = "input_boolean.open_switch"
CLOSE = "input_boolean.close_switch"
TILT_OPEN = "input_boolean.tilt_open"
TILT_CLOSE = "input_boolean.tilt_close"
COVER = "cover.test_cover"


def _cover(hass: HomeAssistant):
    entity_comp = hass.data[DATA_INSTANCES]["cover"]
    return next(e for e in entity_comp.entities if e.entity_id == COVER)


async def _advance(hass: HomeAssistant, clock: FakeClock, seconds: float):
    clock.advance(seconds)
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=seconds), fire_all=True
    )
    await hass.async_block_till_done()


async def _settle():
    """Let queued work run without waiting for a release parked on the pulse."""
    for _ in range(50):
        await asyncio.sleep(0)


async def _call(hass: HomeAssistant, service: str):
    await hass.services.async_call(
        "cover", service, {"entity_id": COVER}, blocking=True
    )
    await _settle()


@pytest.fixture
def pulse_sleep():
    """Let a test decide when the pulse time has passed."""
    gate = asyncio.Event()

    async def _sleep(_seconds):
        await gate.wait()

    with patch("custom_components.cover_time_based.cover_toggle_base.sleep", _sleep):
        yield gate
        gate.set()


@pytest.fixture
async def make_cover(hass: HomeAssistant, setup_input_booleans):
    entries = []

    async def _make(**options):
        base = {
            "control_mode": "toggle",
            "open_switch_entity_id": OPEN,
            "close_switch_entity_id": CLOSE,
            "travel_time_open": 10.0,
            "travel_time_close": 10.0,
            "endpoint_runon_time": 0,
            "pulse_time": 1.0,
        }
        base.update(options)
        entry = MockConfigEntry(
            domain=DOMAIN, version=2, title="Test Cover", data={}, options=base
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entries.append(entry)
        return _cover(hass)

    yield _make

    for entry in entries:
        await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_off_by_default_the_relay_is_left_to_release_itself(
    hass, make_cover, mock_clock, pulse_sleep
):
    cover = await make_cover()
    await cover.set_known_position(position=100)

    await _call(hass, "close_cover")
    pulse_sleep.set()
    await hass.async_block_till_done()

    assert hass.states.get(CLOSE).state == "on"


@pytest.mark.parametrize("mode", ["toggle", "toggle_opposite"])
async def test_the_relay_is_released_after_the_pulse_time(
    hass, make_cover, mock_clock, pulse_sleep, mode
):
    cover = await make_cover(control_mode=mode, release_relay_after_pulse=True)
    await cover.set_known_position(position=100)

    await _call(hass, "close_cover")
    assert hass.states.get(CLOSE).state == "on"
    assert cover.is_closing

    pulse_sleep.set()
    await hass.async_block_till_done()
    assert hass.states.get(CLOSE).state == "off"
    assert cover.is_closing, "our own release is not a press"

    await _advance(hass, mock_clock, 10.5)
    assert cover.current_cover_position == 0
    assert hass.states.get(CLOSE).state == "off"


async def test_a_stop_inside_the_pulse_still_taps_the_relay_and_releases_it(
    hass, make_cover, mock_clock, pulse_sleep
):
    cover = await make_cover(release_relay_after_pulse=True)
    await cover.set_known_position(position=100)
    edges = []
    hass.bus.async_listen(
        "state_changed",
        lambda e: (
            edges.append(e.data["new_state"].state)
            if e.data["entity_id"] == CLOSE
            else None
        ),
    )

    await _call(hass, "close_cover")
    mock_clock.advance(0.5)
    await _call(hass, "stop_cover")
    # Still inside the first pulse: released, then tapped again for the stop.
    assert edges == ["on", "off", "on"]
    assert not cover.is_closing

    pulse_sleep.set()
    await hass.async_block_till_done()
    assert edges == ["on", "off", "on", "off"]
    assert not cover.is_closing and not cover.is_opening


async def test_a_wall_press_after_a_released_pulse_is_still_followed(
    hass, make_cover, mock_clock, pulse_sleep
):
    cover = await make_cover(release_relay_after_pulse=True)
    await cover.set_known_position(position=100)

    await _call(hass, "close_cover")
    pulse_sleep.set()
    await hass.async_block_till_done()
    await _advance(hass, mock_clock, 3.0)
    assert cover.is_closing

    # The same button pressed on the wall stops the motor.
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": CLOSE}, blocking=True
    )
    await hass.async_block_till_done()
    assert not cover.is_closing


async def test_reload_mid_pulse_does_not_leave_the_relay_on(
    hass, make_cover, mock_clock, pulse_sleep
):
    cover = await make_cover(release_relay_after_pulse=True)
    await cover.set_known_position(position=100)

    await _call(hass, "close_cover")
    assert hass.states.get(CLOSE).state == "on"

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_reload(entry.entry_id)
    await _settle()
    assert hass.states.get(CLOSE).state == "off"
    pulse_sleep.set()


async def test_without_a_reported_off_the_relay_is_never_turned_off(
    hass, make_cover, mock_clock, pulse_sleep
):
    """A turn_off is an activation pulse on that hardware (issue #105)."""
    cover = await make_cover(release_relay_after_pulse=True, relay_reports_off=False)
    await cover.set_known_position(position=100)

    await _call(hass, "close_cover")
    pulse_sleep.set()
    await hass.async_block_till_done()

    assert hass.states.get(CLOSE).state == "on"


def _record_edges(hass: HomeAssistant, *entity_ids):
    """Record every state change of the given relays, in order."""
    edges = []
    hass.bus.async_listen(
        "state_changed",
        lambda e: (
            edges.append((e.data["entity_id"], e.data["new_state"].state))
            if e.data["entity_id"] in entity_ids
            else None
        ),
    )
    return edges


async def test_opposite_stop_inside_the_pulse_releases_the_driving_relay_first(
    hass, make_cover, mock_clock, pulse_sleep
):
    """Both direction contacts must never be closed together."""
    cover = await make_cover(
        control_mode="toggle_opposite", release_relay_after_pulse=True
    )
    await cover.set_known_position(position=100)
    edges = _record_edges(hass, OPEN, CLOSE)

    await _call(hass, "close_cover")
    mock_clock.advance(0.5)
    await _call(hass, "stop_cover")
    # Still inside the close pulse: it is released before the open relay taps.
    assert edges == [(CLOSE, "on"), (CLOSE, "off"), (OPEN, "on")]
    assert not cover.is_closing

    pulse_sleep.set()
    await hass.async_block_till_done()
    assert edges[-1] == (OPEN, "off")
    assert hass.states.get(CLOSE).state == "off"
    assert not cover.is_closing and not cover.is_opening


async def test_opposite_tilt_stop_inside_the_pulse_releases_the_driving_relay_first(
    hass, make_cover, mock_clock, pulse_sleep
):
    cover = await make_cover(
        control_mode="toggle_opposite",
        release_relay_after_pulse=True,
        tilt_mode="dual_motor",
        tilt_time_open=5.0,
        tilt_time_close=5.0,
        tilt_open_switch=TILT_OPEN,
        tilt_close_switch=TILT_CLOSE,
    )
    await cover.set_known_position(position=0)
    await cover.set_known_tilt_position(tilt_position=100)
    edges = _record_edges(hass, TILT_OPEN, TILT_CLOSE)

    await _call(hass, "close_cover_tilt")
    mock_clock.advance(0.5)
    await _call(hass, "stop_cover_tilt")
    assert edges == [(TILT_CLOSE, "on"), (TILT_CLOSE, "off"), (TILT_OPEN, "on")]

    pulse_sleep.set()
    await hass.async_block_till_done()
    assert edges[-1] == (TILT_OPEN, "off")
    assert hass.states.get(TILT_CLOSE).state == "off"


async def test_opposite_stop_without_the_option_leaves_the_driving_relay_alone(
    hass, make_cover, mock_clock, pulse_sleep
):
    cover = await make_cover(control_mode="toggle_opposite")
    await cover.set_known_position(position=100)
    edges = _record_edges(hass, OPEN, CLOSE)

    await _call(hass, "close_cover")
    mock_clock.advance(0.5)
    await _call(hass, "stop_cover")
    assert edges == [(CLOSE, "on"), (OPEN, "on")]


async def test_a_wall_press_soon_after_a_stop_inside_the_pulse_is_followed(
    hass, make_cover, mock_clock
):
    """A cancelled release must not leave an echo counted for it."""
    cover = await make_cover(release_relay_after_pulse=True, pulse_time=0.3)
    await cover.set_known_position(position=100)

    await _call(hass, "close_cover")
    mock_clock.advance(0.1)
    await _call(hass, "stop_cover")
    await asyncio.sleep(0.5)  # the release fires
    await hass.async_block_till_done()
    assert hass.states.get(CLOSE).state == "off"
    assert not cover.is_closing

    mock_clock.advance(1.0)
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": CLOSE}, blocking=True
    )
    await hass.async_block_till_done()
    assert cover.is_closing
    await asyncio.sleep(0.5)


async def test_a_wall_press_soon_after_an_opposite_stop_inside_the_pulse_is_followed(
    hass, make_cover, mock_clock
):
    """Releasing the driving relay must drop the echo counted for its release."""
    cover = await make_cover(
        control_mode="toggle_opposite", release_relay_after_pulse=True, pulse_time=0.3
    )
    await cover.set_known_position(position=100)

    await _call(hass, "close_cover")
    mock_clock.advance(0.1)
    await _call(hass, "stop_cover")
    await asyncio.sleep(0.5)  # the stop pulse's release fires
    await hass.async_block_till_done()
    assert hass.states.get(CLOSE).state == "off"
    assert hass.states.get(OPEN).state == "off"
    assert not cover.is_closing

    mock_clock.advance(1.0)
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": CLOSE}, blocking=True
    )
    await hass.async_block_till_done()
    assert cover.is_closing
    await asyncio.sleep(0.5)
