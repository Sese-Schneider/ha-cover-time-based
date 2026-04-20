"""Integration tests for the dedicated position storage.

The integration writes cover positions to its own Store so that position
survives even when Home Assistant does not persist entity state to disk
(e.g. non-graceful shutdown, unavailable states, intermediate crashes).
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

from custom_components.cover_time_based.position_storage import (
    STORAGE_KEY,
    async_get_position_store,
)

from .conftest import DOMAIN

POSITION_STORE_KEY = STORAGE_KEY


def _get_cover_entity(hass: HomeAssistant):
    entity_comp = hass.data["entity_components"]["cover"]
    entities = [e for e in entity_comp.entities if e.entity_id == "cover.test_cover"]
    assert entities, "Cover entity not found"
    return entities[0]


def _make_entry(options):
    return MockConfigEntry(
        domain=DOMAIN, version=2, title="Test Cover", data={}, options=options
    )


BASIC_OPTIONS = {
    "control_mode": "switch",
    "open_switch_entity_id": "input_boolean.open_switch",
    "close_switch_entity_id": "input_boolean.close_switch",
    "travel_time_open": 10.0,
    "travel_time_close": 10.0,
    "endpoint_runon_time": 0,
}


class _MockTime:
    def __init__(self):
        self._base = time_mod.time()
        self._offset = 0.0

    def time(self):
        return self._base + self._offset

    def advance(self, seconds: float):
        self._offset += seconds


@pytest.fixture
def mock_time():
    mt = _MockTime()
    with patch("time.time", mt.time):
        yield mt


async def _advance_time(hass: HomeAssistant, mock_time: _MockTime, seconds: float):
    mock_time.advance(seconds)
    future = dt_util.utcnow() + timedelta(seconds=seconds)
    async_fire_time_changed(hass, future, fire_all=True)
    await hass.async_block_till_done()


async def _flush_position_store(hass: HomeAssistant) -> None:
    """Force any debounced writes from PositionStore to disk."""
    store = await async_get_position_store(hass)
    await store.async_flush()


async def test_set_known_position_writes_to_store(
    hass: HomeAssistant, hass_storage, setup_input_booleans
):
    """set_known_position should persist the position to our Store."""
    entry = _make_entry(BASIC_OPTIONS)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = _get_cover_entity(hass)
    await cover.set_known_position(position=42)
    await hass.async_block_till_done()
    await _flush_position_store(hass)

    stored = hass_storage.get(POSITION_STORE_KEY)
    assert stored is not None, "Position store file was not created"
    assert stored["data"][entry.entry_id]["position"] == 42

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_store_entry_removed_when_config_entry_removed(
    hass: HomeAssistant, hass_storage, setup_input_booleans
):
    """Removing a config entry must purge its data from the position store."""
    entry = _make_entry(BASIC_OPTIONS)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = _get_cover_entity(hass)
    await cover.set_known_position(position=42)
    await hass.async_block_till_done()
    await _flush_position_store(hass)
    assert entry.entry_id in hass_storage[POSITION_STORE_KEY]["data"]

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.entry_id not in hass_storage[POSITION_STORE_KEY]["data"]


async def test_set_known_tilt_position_writes_to_store(
    hass: HomeAssistant, hass_storage, setup_input_booleans
):
    """set_known_tilt_position should persist tilt to the Store."""
    options = {
        **BASIC_OPTIONS,
        "tilt_mode": "sequential_close",
        "tilt_time_open": 2.0,
        "tilt_time_close": 2.0,
    }
    entry = _make_entry(options)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = _get_cover_entity(hass)
    await cover.set_known_position(position=50)
    await cover.set_known_tilt_position(tilt_position=30)
    await hass.async_block_till_done()
    await _flush_position_store(hass)

    stored = hass_storage[POSITION_STORE_KEY]["data"][entry.entry_id]
    assert stored["position"] == 50
    assert stored["tilt_position"] == 30

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_movement_completion_writes_to_store(
    hass: HomeAssistant, hass_storage, setup_input_booleans, mock_time
):
    """When a movement finishes at an endpoint, position should be saved."""
    entry = _make_entry(BASIC_OPTIONS)
    entry.add_to_hass(hass)
    hass_storage[POSITION_STORE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": POSITION_STORE_KEY,
        "data": {entry.entry_id: {"position": 0}},
    }

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = _get_cover_entity(hass)
    assert cover.current_cover_position == 0

    await cover.async_open_cover()
    await hass.async_block_till_done()

    # Advance past full travel — auto-stop should fire and persist.
    await _advance_time(hass, mock_time, 11.0)
    await _flush_position_store(hass)

    assert cover.current_cover_position == 100
    assert hass_storage[POSITION_STORE_KEY]["data"][entry.entry_id]["position"] == 100

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_mid_movement_stop_writes_to_store(
    hass: HomeAssistant, hass_storage, setup_input_booleans, mock_time
):
    """Stopping mid-travel should save the intermediate position."""
    entry = _make_entry(BASIC_OPTIONS)
    entry.add_to_hass(hass)
    hass_storage[POSITION_STORE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": POSITION_STORE_KEY,
        "data": {entry.entry_id: {"position": 0}},
    }
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = _get_cover_entity(hass)
    assert cover.current_cover_position == 0

    await cover.async_open_cover()
    await hass.async_block_till_done()

    await _advance_time(hass, mock_time, 3.0)
    await cover.async_stop_cover()
    await hass.async_block_till_done()
    await _flush_position_store(hass)

    saved = hass_storage[POSITION_STORE_KEY]["data"][entry.entry_id]["position"]
    assert 10 <= saved <= 50, f"Expected mid-travel position, got {saved}"

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_position_loaded_from_store_on_startup(
    hass: HomeAssistant, hass_storage, setup_input_booleans
):
    """When the Store has a position, the cover should use it on startup.

    HA's async_get_last_state is cleared to simulate the production failure
    mode where HA never persisted the state (non-graceful shutdown). The
    Store must be the authoritative source in that case.
    """
    entry = _make_entry(BASIC_OPTIONS)
    entry.add_to_hass(hass)

    hass_storage[POSITION_STORE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": POSITION_STORE_KEY,
        "data": {entry.entry_id: {"position": 73}},
    }

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = _get_cover_entity(hass)
    assert cover.current_cover_position == 73

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_tilt_position_loaded_from_store_on_startup(
    hass: HomeAssistant, hass_storage, setup_input_booleans
):
    """Tilt position from the Store is restored on startup alongside travel."""
    options = {
        **BASIC_OPTIONS,
        "tilt_mode": "sequential_close",
        "tilt_time_open": 2.0,
        "tilt_time_close": 2.0,
    }
    entry = _make_entry(options)
    entry.add_to_hass(hass)

    hass_storage[POSITION_STORE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": POSITION_STORE_KEY,
        "data": {entry.entry_id: {"position": 60, "tilt_position": 25}},
    }

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = _get_cover_entity(hass)
    assert cover.current_cover_position == 60
    assert cover.current_cover_tilt_position == 25

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
