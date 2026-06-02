"""Cover Time Based integration."""

import hashlib
import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .card_resources import (
    async_register_card_resource,
    async_unregister_card_resource,
)
from .const import DOMAIN
from .position_storage import async_get_position_store
from .websocket_api import async_register_websocket_api

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.COVER]
_FRONTEND_DIR = Path(__file__).parent / "frontend"


def _compute_frontend_hash(files: list[Path]) -> str:
    """Short content hash for cache busting. Order-independent."""
    h = hashlib.sha256()
    for f in sorted(files):
        h.update(f.read_bytes())
    return h.hexdigest()[:8]


# Versioning the static-path prefix (rather than appending ?v= to the outer
# URL) busts both the main card and any relative-import siblings (e.g.
# entity-filter.js) on every file change, since the relative imports resolve
# under the same hashed prefix.
_FRONTEND_HASH = _compute_frontend_hash(list(_FRONTEND_DIR.glob("*.js")))
# Hash-independent prefix used to recognise (and cache-bust in place) a card
# resource left over from a previous version.
_CARD_BASE_URL = f"/{DOMAIN}_panel/"
_PANEL_URL = f"/{DOMAIN}_panel/{_FRONTEND_HASH}"
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
    await async_register_card_resource(hass, _CARD_BASE_URL, _CARD_JS_URL)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cover Time Based from a config entry."""
    # Idempotent: re-establishes the card resource whenever an entry is added,
    # including re-adding a cover after the last one was removed (which
    # unregisters the resource) — async_setup only runs once per session.
    await async_register_card_resource(hass, _CARD_BASE_URL, _CARD_JS_URL)
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
    """Remove a config entry — drop its saved position.

    When the last entry is removed (full uninstall) also clean up the card's
    Lovelace resource so it doesn't linger in Settings → Dashboards → Resources.
    """
    store = await async_get_position_store(hass)
    await store.async_remove(entry.entry_id)

    remaining = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id
    ]
    if not remaining:
        await async_unregister_card_resource(hass, _CARD_JS_URL)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update - reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)
