"""Tests for __init__.py integration setup/teardown."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.cover_time_based import (
    async_setup_entry,
    async_unload_entry,
    async_update_options,
)


class TestIntegrationSetup:
    """Test the integration lifecycle."""

    @pytest.mark.asyncio
    async def test_setup_entry_forwards_platforms(self):
        hass = MagicMock()
        hass.data = {}
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        hass.http.async_register_static_paths = AsyncMock()
        entry = MagicMock()
        entry.async_on_unload = MagicMock()
        entry.add_update_listener = MagicMock()

        result = await async_setup_entry(hass, entry)

        assert result is True
        hass.config_entries.async_forward_entry_setups.assert_awaited_once()
        entry.async_on_unload.assert_called_once()

    @pytest.mark.asyncio
    async def test_unload_entry_unloads_platforms(self):
        hass = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        entry = MagicMock()

        result = await async_unload_entry(hass, entry)

        assert result is True
        hass.config_entries.async_unload_platforms.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_options_reloads_entry(self):
        hass = MagicMock()
        hass.config_entries.async_reload = AsyncMock()
        entry = MagicMock()
        entry.entry_id = "test_entry_id"

        await async_update_options(hass, entry)

        hass.config_entries.async_reload.assert_awaited_once_with("test_entry_id")
