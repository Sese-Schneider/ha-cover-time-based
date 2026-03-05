"""Smoke test: verify integration loads and creates an entity."""

from homeassistant.core import HomeAssistant


async def test_integration_loads(hass: HomeAssistant, setup_cover):
    """Config entry loads and creates a cover entity."""
    state = hass.states.get("cover.test_cover")
    assert state is not None
    assert state.state in ("open", "closed", "unknown")
