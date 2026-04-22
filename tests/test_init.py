"""Tests for __init__.py integration setup/teardown."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.cover_time_based import (
    async_setup,
    async_setup_entry,
    async_unload_entry,
    async_update_options,
)


class TestIntegrationSetup:
    """Test the integration lifecycle."""

    @pytest.mark.asyncio
    async def test_setup_entry_forwards_platforms(self):
        hass = MagicMock()
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        entry = MagicMock()
        entry.async_on_unload = MagicMock()
        entry.add_update_listener = MagicMock()

        result = await async_setup_entry(hass, entry)

        assert result is True
        hass.config_entries.async_forward_entry_setups.assert_awaited_once()
        entry.async_on_unload.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_entry_does_not_register_frontend(self):
        """Frontend is registered by async_setup, not per-entry."""
        hass = MagicMock()
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        hass.http.async_register_static_paths = AsyncMock()
        entry = MagicMock()
        entry.async_on_unload = MagicMock()
        entry.add_update_listener = MagicMock()

        with (
            patch("homeassistant.components.frontend.add_extra_js_url") as mock_add_js,
            patch(
                "custom_components.cover_time_based.async_register_websocket_api"
            ) as mock_reg_ws,
        ):
            await async_setup_entry(hass, entry)

        mock_add_js.assert_not_called()
        mock_reg_ws.assert_not_called()
        hass.http.async_register_static_paths.assert_not_awaited()


class TestGlobalSetup:
    """Tests for async_setup — runs once when the integration loads."""

    @pytest.mark.asyncio
    async def test_setup_registers_websocket_api(self):
        hass = MagicMock()
        hass.http.async_register_static_paths = AsyncMock()

        with (
            patch(
                "custom_components.cover_time_based.async_register_websocket_api"
            ) as mock_reg_ws,
            patch("homeassistant.components.frontend.add_extra_js_url"),
        ):
            result = await async_setup(hass, {})

        assert result is True
        mock_reg_ws.assert_called_once_with(hass)

    @pytest.mark.asyncio
    async def test_setup_registers_static_path_and_card_js(self):
        hass = MagicMock()
        hass.http.async_register_static_paths = AsyncMock()

        with patch("homeassistant.components.frontend.add_extra_js_url") as mock_add_js:
            result = await async_setup(hass, {})

        assert result is True
        hass.http.async_register_static_paths.assert_awaited_once()
        mock_add_js.assert_called_once()
        _, js_url = mock_add_js.call_args.args
        assert js_url.endswith("/cover-time-based-card.js")


class TestIntegrationTeardown:
    """Test the integration teardown."""

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
