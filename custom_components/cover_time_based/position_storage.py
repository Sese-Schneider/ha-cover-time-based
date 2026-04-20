"""Dedicated storage for cover positions.

HA's RestoreEntity saves state periodically (every 15 min) and at graceful
shutdown. Positions are lost if HA is killed or the entity is unavailable
at save time. This Store is written whenever position stabilises, so
restore survives those cases.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORAGE_KEY = f"{DOMAIN}.positions"
STORAGE_VERSION = 1
SAVE_DELAY = 1.0  # Coalesce bursts of saves into one disk write.
_DATA_STORE = f"{DOMAIN}_position_store"


class PositionStore:
    """Persist cover positions keyed by config entry id."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, dict]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, dict] | None = None

    async def _ensure_loaded(self) -> dict[str, dict]:
        if self._data is None:
            self._data = await self._store.async_load() or {}
        return self._data

    async def async_get(self, entry_id: str) -> dict | None:
        """Return stored data for an entry, or None."""
        return (await self._ensure_loaded()).get(entry_id)

    async def async_save(self, entry_id: str, data: dict[str, int]) -> None:
        """Save entry data, debounced. Skips if nothing would change."""
        if not data:
            return
        current = await self._ensure_loaded()
        if current.get(entry_id) == data:
            return
        current[entry_id] = data
        self._store.async_delay_save(lambda: self._data, SAVE_DELAY)

    async def async_remove(self, entry_id: str) -> None:
        """Remove an entry — writes synchronously so cleanup is durable."""
        current = await self._ensure_loaded()
        if entry_id in current:
            del current[entry_id]
            await self._store.async_save(current)


@singleton(_DATA_STORE)
async def async_get_position_store(hass: HomeAssistant) -> PositionStore:
    """Return the per-hass singleton PositionStore."""
    return PositionStore(hass)
