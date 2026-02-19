"""Cover Time Based integration."""

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .websocket_api import async_register_websocket_api

_LOGGER = logging.getLogger(__name__)

DOMAIN = "cover_time_based"
PLATFORMS: list[Platform] = [Platform.COVER]
_FRONTEND_KEY = f"{DOMAIN}_frontend_registered"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cover Time Based from a config entry."""
    # Register frontend and WebSocket API once (not per entry).
    # Done before platform setup so the card works even if the entity fails.
    if _FRONTEND_KEY not in hass.data:
        hass.data[_FRONTEND_KEY] = True

        async_register_websocket_api(hass)

        if hass.http is not None:
            await hass.http.async_register_static_paths(
                [
                    StaticPathConfig(
                        "/cover_time_based_panel",
                        str(Path(__file__).parent / "frontend"),
                        cache_headers=False,
                    )
                ]
            )

            hass.data.setdefault(frontend.DATA_EXTRA_MODULE_URL, set())
            frontend.add_extra_js_url(
                hass, "/cover_time_based_panel/cover-time-based-card.js"
            )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update - reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to current version."""
    if entry.version == 1:
        _LOGGER.debug("Migrating config entry %s from version 1 to 2", entry.entry_id)
        new_options = dict(entry.options)

        # Rename keys
        _rename_key(new_options, "travelling_time_down", "travel_time_close")
        _rename_key(new_options, "travelling_time_up", "travel_time_open")
        _rename_key(new_options, "tilting_time_down", "tilt_time_close")
        _rename_key(new_options, "tilting_time_up", "tilt_time_open")

        # Set tilt_mode based on whether tilt times are configured.
        # travel_moves_with_tilt is kept as a separate boolean option.
        if "tilt_mode" not in new_options:
            has_tilt = (
                new_options.get("tilt_time_close") is not None
                or new_options.get("tilt_time_open") is not None
            )
            new_options["tilt_mode"] = "sequential" if has_tilt else "none"

        hass.config_entries.async_update_entry(entry, options=new_options, version=2)
        _LOGGER.debug("Migration to version 2 complete for %s", entry.entry_id)

    return True


def _rename_key(d: dict, old: str, new: str) -> None:
    """Rename a dict key if present."""
    if old in d:
        if new not in d:
            d[new] = d[old]
        del d[old]
