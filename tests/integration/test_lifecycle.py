"""Integration tests for config lifecycle and restart.

Entity creation from config, position restore across restart and reload, and config-entry migrations.
"""

from __future__ import annotations

from homeassistant.components.cover import ATTR_CURRENT_POSITION, CoverEntityFeature
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_component import DATA_INSTANCES
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from .conftest import DOMAIN


def _get_cover_entity(hass: HomeAssistant):
    """Return the CoverTimeBased entity object."""
    entity_comp = hass.data[DATA_INSTANCES]["cover"]
    entities = [e for e in entity_comp.entities if e.entity_id == "cover.test_cover"]
    assert entities, "Cover entity not found"
    return entities[0]


async def _assert_reload_replaces_cover(hass: HomeAssistant, entry: MockConfigEntry):
    """Reload the entry as a card save does; return the replacement entity.

    A removal that raises leaves the old entity half-removed, so HA refuses
    the replacement as a duplicate unique ID and the cover vanishes until a
    restart (issue #245).
    """
    old = _get_cover_entity(hass)

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    # The state and the registry row exist whether or not the replacement was
    # added, so look for the live entity object.
    new = _get_cover_entity(hass)
    assert new is not old
    return new


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


async def test_reload_of_a_new_cover_without_relays_keeps_the_entity(
    hass: HomeAssistant, setup_input_booleans
):
    """A cover straight from the config flow has no options, so no relays.

    Its first card save reloads it, and the removal stop must not send
    homeassistant.turn_off to an empty entity id.
    """
    entry = MockConfigEntry(
        domain=DOMAIN, version=4, title="Test Cover", data={}, options={}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await _assert_reload_replaces_cover(hass, entry)

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_reload_with_only_the_opening_time_keeps_the_entity(
    hass: HomeAssistant, setup_input_booleans
):
    """Calibration saves the opening time before the closing time is measured.

    Removal of a stopped cover at a known position must not need the missing
    closing time, and the replacement restores that position.
    """
    options = {
        "control_mode": "switch",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 30.0,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, version=4, title="Test Cover", data={}, options=options
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await _get_cover_entity(hass).set_known_position(position=50)
    await hass.async_block_till_done()

    cover = await _assert_reload_replaces_cover(hass, entry)
    assert cover.current_cover_position == 50

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_migrate_v2_sequential_to_v3_sequential_close(hass: HomeAssistant):
    """v2 entries with tilt_mode='sequential' migrate to v3 'sequential_close'."""
    from custom_components.cover_time_based import async_migrate_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Test",
        data={},
        options={"tilt_mode": "sequential", "travel_time_open": 10},
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 4
    assert entry.options["tilt_mode"] == "sequential_close"
    assert entry.options["travel_time_open"] == 10


async def test_migrate_v2_non_sequential_bumps_version_only(hass: HomeAssistant):
    """v2 entries whose tilt_mode is not 'sequential' only bump the version."""
    from custom_components.cover_time_based import async_migrate_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Test",
        data={},
        options={"tilt_mode": "inline"},
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 4
    assert entry.options["tilt_mode"] == "inline"


async def test_migrate_v3_to_v4_preserves_tilt_mode(hass: HomeAssistant):
    """v3 entries migrate to v4, keeping tilt_mode untouched."""
    from custom_components.cover_time_based import async_migrate_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        title="Test",
        data={},
        options={"tilt_mode": "sequential_close"},
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 4
    assert entry.options["tilt_mode"] == "sequential_close"


async def test_migrate_is_noop_on_current_version(hass: HomeAssistant):
    """v4 entries (the current version) are left untouched."""
    from custom_components.cover_time_based import async_migrate_entry

    options = {
        "tilt_mode": "sequential_close",
        "position_reporting": "reliable",
        "travel_time_open": 10,
        "travel_time_close": 12,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        title="Test",
        data={},
        options=options,
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 4
    assert entry.options == options


async def test_state_has_position_attribute_after_movement(
    hass: HomeAssistant, setup_input_booleans
):
    """After set_known_position, the HA state should expose current_position.

    This is what RestoreStateData saves to disk at HA shutdown. If the
    attribute is missing, position cannot be restored on restart.
    """
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
    await cover.set_known_position(position=37)
    await hass.async_block_till_done()

    state = hass.states.get("cover.test_cover")
    assert state is not None
    assert state.attributes.get(ATTR_CURRENT_POSITION) == 37

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_position_restored_from_ha_restart(
    hass: HomeAssistant, setup_input_booleans
):
    """Position is restored from RestoreStateData after a full HA restart.

    Simulates a real HA restart (not just config entry reload) by seeding
    the restore cache with a prior state, then setting up the config entry.
    The cover should read the saved state and restore its position.
    """
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

    # Seed the restore cache as if HA had saved state before restart.
    mock_restore_cache(
        hass,
        [
            State(
                "cover.test_cover",
                "open",
                {ATTR_CURRENT_POSITION: 42},
            )
        ],
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = _get_cover_entity(hass)
    assert cover.current_cover_position == 42

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
