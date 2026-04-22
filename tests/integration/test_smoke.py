"""Smoke test: verify integration loads and creates an entity."""

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from .conftest import DOMAIN


async def test_integration_loads(hass: HomeAssistant, setup_cover):
    """Config entry loads and creates a cover entity."""
    state = hass.states.get("cover.test_cover")
    assert state is not None
    assert state.state in ("open", "closed", "unknown")


async def test_card_js_registered_without_config_entry(hass: HomeAssistant):
    """Card JS URL is registered when the integration loads, even with zero entries.

    Users with dashboard cards referencing custom:cover-time-based-card need
    the JS available regardless of whether any cover_time_based entity exists.
    """
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    urls = hass.data[DATA_EXTRA_MODULE_URL].urls
    assert any("cover-time-based-card.js" in url for url in urls)
