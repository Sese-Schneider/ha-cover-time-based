"""Cover Time Based integration."""

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .position_storage import async_get_position_store
from .websocket_api import async_register_websocket_api

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.COVER]
_PANEL_URL = f"/{DOMAIN}_panel"
_CARD_JS_URL = f"{_PANEL_URL}/cover-time-based-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the Lovelace card and WebSocket API once per HA session."""
    async_register_websocket_api(hass)
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                _PANEL_URL,
                str(Path(__file__).parent / "frontend"),
                cache_headers=False,
            )
        ]
    )
    frontend.add_extra_js_url(hass, _CARD_JS_URL)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cover Time Based from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries between versions."""
    _LOGGER.debug(
        "Migrating config entry %s from version %s", entry.entry_id, entry.version
    )

    if entry.version < 3:
        new_options = dict(entry.options)
        if new_options.get("tilt_mode") == "sequential":
            new_options["tilt_mode"] = "sequential_close"
        hass.config_entries.async_update_entry(entry, options=new_options, version=3)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a config entry — drop its saved position."""
    store = await async_get_position_store(hass)
    await store.async_remove(entry.entry_id)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update - reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)
