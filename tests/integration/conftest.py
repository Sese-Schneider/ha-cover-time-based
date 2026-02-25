"""Integration test fixtures for cover_time_based.

Uses pytest-homeassistant-custom-component for a real HA instance.
input_boolean entities simulate physical relay switches.
"""

from __future__ import annotations

import pytest
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "cover_time_based"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests in this directory."""
    return


@pytest.fixture(autouse=True)
def stub_frontend(hass: HomeAssistant):
    """Stub frontend data so the integration can register extra JS URLs."""
    from homeassistant.components.frontend import UrlManager

    if DATA_EXTRA_MODULE_URL not in hass.data:
        hass.data[DATA_EXTRA_MODULE_URL] = UrlManager(lambda *_: None, [])


@pytest.fixture
async def setup_input_booleans(hass: HomeAssistant):
    """Create input_boolean entities to act as mock switches.

    Also sets up the homeassistant component (turn_on/turn_off services)
    which the cover uses to control relays.
    """
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(
        hass,
        "input_boolean",
        {
            "input_boolean": {
                "open_switch": {"name": "Open Switch"},
                "close_switch": {"name": "Close Switch"},
                "stop_switch": {"name": "Stop Switch"},
                "tilt_open": {"name": "Tilt Open"},
                "tilt_close": {"name": "Tilt Close"},
            }
        },
    )
    await hass.async_block_till_done()


@pytest.fixture
def base_options():
    """Return minimal config options for a switch-mode cover."""
    return {
        "control_mode": "switch",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 30.0,
        "travel_time_close": 30.0,
    }


@pytest.fixture
async def setup_cover(hass: HomeAssistant, setup_input_booleans, base_options):
    """Create and load a cover_time_based config entry.

    Yields the entry, then unloads it on teardown to cancel all timers
    and listeners (auto_updater_hook, state change listeners, etc.).
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Test Cover",
        data={},
        options=base_options,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("cover.test_cover")
    assert state is not None, "Cover entity was not created"

    yield entry

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
