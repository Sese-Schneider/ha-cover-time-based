"""Integration tests for the favourite position.

The favourite is recalled by service, by both inputs held on, or by a trigger
entity holding a state. A recalled favourite is either driven (relays switched)
or tracked (the motor moves by itself, nothing is sent).
"""

from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.util import dt as dt_util

from tests.ha_harness import MockConfigEntry, async_fire_time_changed
from tests.helpers import FakeClock

from .conftest import DOMAIN

OPEN = "input_boolean.open_switch"
CLOSE = "input_boolean.close_switch"
TRIGGER = "input_boolean.stop_switch"


def _cover(hass: HomeAssistant):
    entity_comp = hass.data[DATA_INSTANCES]["cover"]
    return next(e for e in entity_comp.entities if e.entity_id == "cover.test_cover")


async def _advance(hass: HomeAssistant, clock: FakeClock, seconds: float):
    clock.advance(seconds)
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=seconds), fire_all=True
    )
    await hass.async_block_till_done()


async def _tick(hass: HomeAssistant, clock: FakeClock, seconds: float):
    """Let ``seconds`` pass without firing timers that are due later than that."""
    clock.advance(seconds)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def _press(hass: HomeAssistant, entity_id: str, on: bool = True):
    await hass.services.async_call(
        "input_boolean",
        "turn_on" if on else "turn_off",
        {"entity_id": entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()


async def _setup(hass: HomeAssistant, options: dict):
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, title="Test Cover", data={}, options=options
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


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
        }
        base.update(options)
        entries.append(await _setup(hass, base))
        return _cover(hass)

    yield _make

    for entry in entries:
        await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


class TestService:
    async def test_without_a_favourite_the_service_is_refused(
        self, hass, make_cover, mock_clock
    ):
        cover = await make_cover()
        await cover.set_known_position(position=100)
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "go_to_favourite",
                {"entity_id": "cover.test_cover"},
                blocking=True,
            )

    async def test_drives_the_cover_to_the_favourite(
        self, hass, make_cover, mock_clock
    ):
        cover = await make_cover(control_mode="switch", favourite_position=40)
        await cover.set_known_position(position=100)

        await hass.services.async_call(
            DOMAIN, "go_to_favourite", {"entity_id": "cover.test_cover"}, blocking=True
        )
        await hass.async_block_till_done()
        assert hass.states.get(CLOSE).state == "on"

        await _advance(hass, mock_clock, 6.0)
        assert cover.current_cover_position == 40
        assert hass.states.get(CLOSE).state == "off"


class TestBothInputsGesture:
    async def test_held_gesture_is_tracked_without_touching_the_relays(
        self, hass, make_cover, mock_clock
    ):
        cover = await make_cover(favourite_position=30, favourite_gesture="both_inputs")
        await cover.set_known_position(position=100)

        await _press(hass, CLOSE)
        await _tick(hass, mock_clock, 0.2)
        await _press(hass, OPEN)
        # The lone close press was followed for 0.2 s; the gesture undoes it.
        assert cover.current_cover_position == 100
        assert not cover.is_closing and not cover.is_opening

        await _advance(hass, mock_clock, 3.0)
        assert cover.is_closing
        # Nothing was commanded: both inputs are still exactly as held.
        assert hass.states.get(OPEN).state == "on"
        assert hass.states.get(CLOSE).state == "on"

        await _advance(hass, mock_clock, 4.0)
        await _press(hass, OPEN, on=False)
        await _press(hass, CLOSE, on=False)
        assert cover.is_closing, "releasing the buttons is not a stop"

        await _advance(hass, mock_clock, 3.0)
        assert cover.current_cover_position == 30
        assert not cover.is_closing

    async def test_released_before_the_hold_time_nothing_moves(
        self, hass, make_cover, mock_clock
    ):
        cover = await make_cover(favourite_position=30, favourite_gesture="both_inputs")
        await cover.set_known_position(position=100)

        await _press(hass, OPEN)
        await _press(hass, CLOSE)
        await _tick(hass, mock_clock, 1.0)
        await _press(hass, OPEN, on=False)
        await _press(hass, CLOSE, on=False)
        await _advance(hass, mock_clock, 5.0)

        assert cover.current_cover_position == 100
        assert not cover.is_closing and not cover.is_opening

    async def test_presses_are_ordinary_again_after_the_gesture(
        self, hass, make_cover, mock_clock
    ):
        cover = await make_cover(favourite_position=30, favourite_gesture="both_inputs")
        await cover.set_known_position(position=100)

        await _press(hass, OPEN)
        await _press(hass, CLOSE)
        await _press(hass, OPEN, on=False)
        await _press(hass, CLOSE, on=False)

        await _press(hass, CLOSE)
        assert cover.is_closing

    async def test_gesture_off_leaves_both_presses_alone(
        self, hass, make_cover, mock_clock
    ):
        cover = await make_cover(favourite_position=30)
        await cover.set_known_position(position=100)

        await _press(hass, CLOSE)
        await _press(hass, OPEN)
        await _advance(hass, mock_clock, 5.0)

        assert cover.current_cover_position != 30


class TestTriggerEntityGesture:
    async def test_held_state_drives_the_cover(self, hass, make_cover, mock_clock):
        cover = await make_cover(
            control_mode="switch",
            favourite_position=40,
            favourite_gesture="entity",
            favourite_trigger_entity_id=TRIGGER,
            favourite_trigger_state="on",
            favourite_action="drive",
            favourite_hold_time=2.0,
        )
        await cover.set_known_position(position=100)

        await _press(hass, TRIGGER)
        await _tick(hass, mock_clock, 1.0)
        assert hass.states.get(CLOSE).state == "off"

        await _advance(hass, mock_clock, 1.5)
        assert hass.states.get(CLOSE).state == "on"

        await _advance(hass, mock_clock, 6.0)
        assert cover.current_cover_position == 40
        assert hass.states.get(CLOSE).state == "off"

    async def test_state_left_early_does_nothing(self, hass, make_cover, mock_clock):
        cover = await make_cover(
            control_mode="switch",
            favourite_position=40,
            favourite_gesture="entity",
            favourite_trigger_entity_id=TRIGGER,
            favourite_trigger_state="on",
            favourite_action="drive",
        )
        await cover.set_known_position(position=100)

        await _press(hass, TRIGGER)
        await _tick(hass, mock_clock, 1.0)
        await _press(hass, TRIGGER, on=False)
        await _advance(hass, mock_clock, 5.0)

        assert hass.states.get(CLOSE).state == "off"
        assert cover.current_cover_position == 100


class TestFavouriteWithSlats:
    """Sequential slats that open after the cover is down (sequential_open)."""

    SLATS: ClassVar[dict] = {
        "tilt_mode": "sequential_open",
        "tilt_time_open": 2.0,
        "tilt_time_close": 2.0,
        "favourite_position": 0,
        "favourite_tilt_position": 0,
        "favourite_gesture": "both_inputs",
    }

    async def test_from_down_with_slats_open_only_the_slats_are_tracked(
        self, hass, make_cover, mock_clock
    ):
        cover = await make_cover(**self.SLATS)
        await cover.set_known_position(position=0)
        await cover.set_known_tilt_position(tilt_position=100)

        await _press(hass, OPEN)
        await _press(hass, CLOSE)
        await _advance(hass, mock_clock, 3.0)
        await _advance(hass, mock_clock, 3.0)

        assert cover.current_cover_position == 0
        assert cover.current_cover_tilt_position == 0

    async def test_from_open_the_travel_is_tracked_and_slats_stay_closed(
        self, hass, make_cover, mock_clock
    ):
        cover = await make_cover(**self.SLATS)
        await cover.set_known_position(position=100)
        await cover.set_known_tilt_position(tilt_position=0)

        await _press(hass, OPEN)
        await _press(hass, CLOSE)
        await _advance(hass, mock_clock, 3.0)
        await _advance(hass, mock_clock, 11.0)

        assert cover.current_cover_position == 0
        assert cover.current_cover_tilt_position == 0
        assert hass.states.get(OPEN).state == "on"
        assert hass.states.get(CLOSE).state == "on"

    async def test_slats_that_move_after_the_travel_are_tracked_in_turn(
        self, hass, make_cover, mock_clock
    ):
        cover = await make_cover(**{**self.SLATS, "favourite_tilt_position": 50})
        await cover.set_known_position(position=100)
        await cover.set_known_tilt_position(tilt_position=0)

        await _press(hass, OPEN)
        await _press(hass, CLOSE)
        await _advance(hass, mock_clock, 3.0)
        await _advance(hass, mock_clock, 10.5)
        assert cover.current_cover_position == 0

        await _advance(hass, mock_clock, 1.5)
        assert cover.current_cover_tilt_position == 50
        assert hass.states.get(OPEN).state == "on"
        assert hass.states.get(CLOSE).state == "on"


class TestFavouriteWithATiltMotor:
    """A dedicated tilt motor: the slats move after the travel has arrived."""

    DUAL: ClassVar[dict] = {
        "tilt_mode": "dual_motor",
        "tilt_open_switch": "input_boolean.tilt_open",
        "tilt_close_switch": "input_boolean.tilt_close",
        "tilt_time_open": 2.0,
        "tilt_time_close": 2.0,
        "favourite_position": 50,
        "favourite_tilt_position": 30,
    }

    async def test_tracked_favourite_follows_travel_only(
        self, hass, make_cover, mock_clock
    ):
        """The gesture on the travel inputs says nothing about the tilt motor."""
        cover = await make_cover(favourite_gesture="both_inputs", **self.DUAL)
        await cover.set_known_position(position=100)
        await cover.set_known_tilt_position(tilt_position=100)

        await _press(hass, OPEN)
        await _press(hass, CLOSE)
        await _advance(hass, mock_clock, 3.0)
        await _advance(hass, mock_clock, 5.5)
        assert cover.current_cover_position == 50

        await _advance(hass, mock_clock, 2.0)
        assert cover.current_cover_tilt_position == 100
        assert hass.states.get("input_boolean.tilt_open").state == "off"
        assert hass.states.get("input_boolean.tilt_close").state == "off"

    async def test_driven_travel_is_followed_by_driven_tilt(
        self, hass, make_cover, mock_clock
    ):
        cover = await make_cover(control_mode="switch", **self.DUAL)
        await cover.set_known_position(position=100)
        await cover.set_known_tilt_position(tilt_position=100)

        await hass.services.async_call(
            DOMAIN, "go_to_favourite", {"entity_id": "cover.test_cover"}, blocking=True
        )
        await _advance(hass, mock_clock, 5.5)
        assert cover.current_cover_position == 50
        assert hass.states.get(CLOSE).state == "off"
        assert hass.states.get("input_boolean.tilt_close").state == "on"

        await _advance(hass, mock_clock, 2.0)
        assert cover.current_cover_tilt_position == 30
        assert hass.states.get("input_boolean.tilt_close").state == "off"
