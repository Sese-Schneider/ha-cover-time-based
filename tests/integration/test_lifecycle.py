"""Integration tests for config lifecycle and restart.

Tests correct entity creation from config and position restore on restart.
"""

from __future__ import annotations

from homeassistant.components.cover import CoverEntityFeature
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import DOMAIN


def _get_cover_entity(hass: HomeAssistant):
    """Return the CoverTimeBased entity object."""
    entity_comp = hass.data["entity_components"]["cover"]
    entities = [e for e in entity_comp.entities if e.entity_id == "cover.test_cover"]
    assert entities, "Cover entity not found"
    return entities[0]


async def test_config_creates_correct_entity(hass: HomeAssistant, setup_input_booleans):
    """Config entry with pulse mode and tilt creates entity with correct features."""
    options = {
        "control_mode": "pulse",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "stop_switch_entity_id": "input_boolean.stop_switch",
        "travel_time_open": 30.0,
        "travel_time_close": 30.0,
        "tilt_mode": "sequential",
        "tilt_time_open": 2.0,
        "tilt_time_close": 2.0,
        "pulse_time": 0.5,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, title="Test Cover", data={}, options=options
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("cover.test_cover")
    assert state is not None

    features = state.attributes.get("supported_features", 0)

    # Should support position (open/close/stop/set_position)
    assert features & CoverEntityFeature.OPEN
    assert features & CoverEntityFeature.CLOSE
    assert features & CoverEntityFeature.STOP
    assert features & CoverEntityFeature.SET_POSITION

    # Should support tilt (since tilt_mode is configured with times)
    assert features & CoverEntityFeature.SET_TILT_POSITION

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_position_restored_on_restart(hass: HomeAssistant, setup_input_booleans):
    """Position is restored after config entry unload and reload."""
    options = {
        "control_mode": "switch",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 30.0,
        "travel_time_close": 30.0,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, title="Test Cover", data={}, options=options
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = _get_cover_entity(hass)

    # Set position to 50
    await cover.set_known_position(position=50)
    await hass.async_block_till_done()
    assert cover.current_cover_position == 50

    # Unload
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # Reload
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Get the newly created entity
    cover = _get_cover_entity(hass)
    assert cover.current_cover_position == 50

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
