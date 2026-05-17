"""Tests for __init__.py integration setup/teardown."""

import re

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.cover_time_based import (
    _CARD_JS_URL,
    _PANEL_URL,
    _compute_frontend_hash,
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


class TestFrontendCacheBuster:
    """Frontend cache buster — the static-path prefix and JS URL include a
    short content hash of the JS files so each release / file change forces
    browsers to fetch fresh JS."""

    def test_compute_hash_is_deterministic(self, tmp_path):
        a = tmp_path / "a.js"
        a.write_text("alpha")
        b = tmp_path / "b.js"
        b.write_text("beta")

        h1 = _compute_frontend_hash([a, b])
        h2 = _compute_frontend_hash([a, b])

        assert h1 == h2
        assert isinstance(h1, str)
        assert len(h1) > 0

    def test_compute_hash_is_order_independent(self, tmp_path):
        a = tmp_path / "a.js"
        a.write_text("alpha")
        b = tmp_path / "b.js"
        b.write_text("beta")

        assert _compute_frontend_hash([a, b]) == _compute_frontend_hash([b, a])

    def test_compute_hash_changes_when_a_file_changes(self, tmp_path):
        a = tmp_path / "a.js"
        a.write_text("alpha")
        b = tmp_path / "b.js"
        b.write_text("beta")
        before = _compute_frontend_hash([a, b])

        b.write_text("beta-changed")
        after = _compute_frontend_hash([a, b])

        assert before != after

    def test_panel_url_includes_hash(self):
        # Hash segment is 8 lowercase hex characters
        assert re.fullmatch(r"/cover_time_based_panel/[0-9a-f]{8}", _PANEL_URL)

    def test_card_js_url_lives_under_hashed_prefix(self):
        # Inner relative imports resolve under the same hashed prefix, so
        # `entity-filter.js` busts together with the main card.
        assert _CARD_JS_URL == f"{_PANEL_URL}/cover-time-based-card.js"


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
