"""Tests for __init__.py integration setup/teardown."""

import re

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.cover_time_based import (
    _CARD_BASE_URL,
    _CARD_JS_URL,
    _PANEL_URL,
    _compute_frontend_hash,
    async_remove_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
    async_update_options,
)
from custom_components.cover_time_based.card_resources import _RESOURCE_ID_KEY
from custom_components.cover_time_based.const import DOMAIN


class FakeResources:
    """Minimal stand-in for HA's Lovelace resource collection."""

    def __init__(self, items=None, loaded=False):
        self._items = list(items or [])
        self.loaded = loaded
        self.created = []
        self.updated = []
        self.deleted = []

    def async_items(self):
        return list(self._items)

    async def async_load(self):
        self.loaded = True

    async def async_create_item(self, data):
        item = {"id": "new-id", **data}
        self.created.append(data)
        self._items.append(item)
        return item

    async def async_update_item(self, item_id, data):
        self.updated.append((item_id, data))

    async def async_delete_item(self, item_id):
        self.deleted.append(item_id)
        self._items = [i for i in self._items if i.get("id") != item_id]


def _make_setup_hass(resources):
    """A hass whose Lovelace resource collection is `resources` (or None)."""
    hass = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    if resources is None:
        hass.data = {}
    else:
        lovelace = MagicMock()
        lovelace.resources = resources
        hass.data = {"lovelace": lovelace}
    return hass


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
    async def test_setup_entry_does_not_register_static_path_or_websocket(self):
        """Static paths and the websocket API are global (async_setup), not per-entry."""
        resources = FakeResources()
        hass = _make_setup_hass(resources)
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        entry = MagicMock()
        entry.async_on_unload = MagicMock()
        entry.add_update_listener = MagicMock()

        with patch(
            "custom_components.cover_time_based.async_register_websocket_api"
        ) as mock_reg_ws:
            await async_setup_entry(hass, entry)

        mock_reg_ws.assert_not_called()
        hass.http.async_register_static_paths.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_setup_entry_registers_card_resource(self):
        """Each entry (re)registers the card resource, so re-adding a cover
        after the last one was removed restores the card without an HA restart."""
        resources = FakeResources()
        hass = _make_setup_hass(resources)
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        entry = MagicMock()
        entry.async_on_unload = MagicMock()
        entry.add_update_listener = MagicMock()

        await async_setup_entry(hass, entry)

        assert len(resources.created) == 1
        assert resources.created[0]["url"] == _CARD_JS_URL

    @pytest.mark.asyncio
    async def test_re_add_after_full_removal_reregisters_card(self):
        """Regression: removing the last entry unregisters the resource; adding
        a new entry in the same session must register it again."""
        resources = FakeResources()
        hass = _make_setup_hass(resources)
        hass.config_entries.async_forward_entry_setups = AsyncMock()

        # Initial install registers the resource.
        await async_setup(hass, {})
        assert len(resources.created) == 1
        assert resources.async_items()  # resource present

        # Remove the last (only) entry → resource is unregistered.
        entry = MagicMock()
        entry.entry_id = "e1"
        hass.config_entries.async_entries = MagicMock(return_value=[])
        with patch(
            "custom_components.cover_time_based.async_get_position_store"
        ) as mock_store:
            mock_store.return_value.async_remove = AsyncMock()
            await async_remove_entry(hass, entry)
        assert resources.async_items() == []  # resource gone

        # Re-add an entry in the same session → resource restored.
        await async_setup_entry(hass, entry)
        assert resources.async_items()
        assert resources.async_items()[0]["url"] == _CARD_JS_URL


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
    async def test_setup_registers_static_path(self):
        resources = FakeResources()
        hass = _make_setup_hass(resources)

        with patch("homeassistant.components.frontend.add_extra_js_url"):
            result = await async_setup(hass, {})

        assert result is True
        hass.http.async_register_static_paths.assert_awaited_once()


class TestCardResourceRegistration:
    """The card must be registered as a Lovelace *resource* (loaded during
    Lovelace init, after HA swaps in the scoped-custom-element-registry
    polyfill) rather than via add_extra_js_url (injected at page load, before
    the swap — which drops the element and yields a 'custom element doesn't
    exist' configuration error until a refresh)."""

    @pytest.mark.asyncio
    async def test_setup_registers_card_as_lovelace_resource(self):
        resources = FakeResources()
        hass = _make_setup_hass(resources)

        with patch("homeassistant.components.frontend.add_extra_js_url") as mock_add_js:
            await async_setup(hass, {})

        assert resources.loaded is True
        assert len(resources.created) == 1
        assert resources.created[0]["res_type"] == "module"
        assert resources.created[0]["url"] == _CARD_JS_URL
        mock_add_js.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_records_id_when_resource_already_current(self):
        """After a restart hass.data is empty but the resource is already
        current; setup must still record its id so a later uninstall can
        delete it (rather than leaving it orphaned in Dashboards → Resources)."""
        resources = FakeResources(
            items=[{"id": "abc", "url": _CARD_JS_URL}], loaded=True
        )
        hass = _make_setup_hass(resources)

        with patch("homeassistant.components.frontend.add_extra_js_url"):
            await async_setup(hass, {})

        assert hass.data[DOMAIN][_RESOURCE_ID_KEY] == "abc"

    @pytest.mark.asyncio
    async def test_setup_updates_existing_resource_on_version_change(self):
        stale_url = f"{_CARD_BASE_URL}deadbeef/cover-time-based-card.js"
        resources = FakeResources(items=[{"id": "old", "url": stale_url}], loaded=True)
        hass = _make_setup_hass(resources)

        with patch("homeassistant.components.frontend.add_extra_js_url"):
            await async_setup(hass, {})

        assert resources.updated == [("old", {"url": _CARD_JS_URL})]
        assert resources.created == []

    @pytest.mark.asyncio
    async def test_setup_skips_when_resource_already_current(self):
        resources = FakeResources(items=[{"id": "x", "url": _CARD_JS_URL}], loaded=True)
        hass = _make_setup_hass(resources)

        with patch("homeassistant.components.frontend.add_extra_js_url"):
            await async_setup(hass, {})

        assert resources.created == []
        assert resources.updated == []

    @pytest.mark.asyncio
    async def test_setup_falls_back_to_add_extra_js_url_without_resources(self):
        hass = _make_setup_hass(None)

        with patch("homeassistant.components.frontend.add_extra_js_url") as mock_add_js:
            await async_setup(hass, {})

        mock_add_js.assert_called_once()
        _, js_url = mock_add_js.call_args.args
        assert js_url == _CARD_JS_URL


class TestManifest:
    """Manifest invariants the frontend fix depends on."""

    def test_orders_after_lovelace(self):
        # `after_dependencies: ["lovelace"]` guarantees Lovelace (and its
        # resource store) is set up before us, so async_setup registers the
        # card as a resource instead of silently falling back to the
        # add_extra_js_url path that drops the element on cold load.
        import json
        from pathlib import Path

        manifest = json.loads(
            (
                Path(__file__).parent.parent
                / "custom_components"
                / "cover_time_based"
                / "manifest.json"
            ).read_text()
        )
        assert "lovelace" in manifest.get("after_dependencies", [])


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


class TestCardResourceUnregistration:
    """On full uninstall (removal of the last config entry) the Lovelace
    resource should be cleaned up; removing one of several entries must leave
    it in place."""

    def _make_remove_hass(self, resources, remaining, stored_id="new-id"):
        hass = MagicMock()
        lovelace = MagicMock()
        lovelace.resources = resources
        data = {"lovelace": lovelace}
        if stored_id is not None:
            data[DOMAIN] = {"card_resource_id": stored_id}
        hass.data = data
        hass.config_entries.async_entries = MagicMock(return_value=remaining)
        return hass

    @pytest.mark.asyncio
    async def test_remove_last_entry_unregisters_card_resource(self):
        resources = FakeResources(
            items=[{"id": "new-id", "url": _CARD_JS_URL}], loaded=True
        )
        entry = MagicMock()
        entry.entry_id = "e1"
        # Only this entry exists; HA has already dropped it from the registry.
        hass = self._make_remove_hass(resources, remaining=[])

        with patch(
            "custom_components.cover_time_based.async_get_position_store"
        ) as mock_store:
            mock_store.return_value.async_remove = AsyncMock()
            await async_remove_entry(hass, entry)

        assert resources.deleted == ["new-id"]

    @pytest.mark.asyncio
    async def test_uninstall_deletes_already_current_resource(self):
        """Regression: after a restart the resource is already current and
        hass.data is empty; setup records the id so full uninstall deletes the
        resource instead of falling back to the no-op remove_extra_js_url."""
        resources = FakeResources(
            items=[{"id": "abc", "url": _CARD_JS_URL}], loaded=True
        )
        hass = _make_setup_hass(resources)

        with patch("homeassistant.components.frontend.add_extra_js_url"):
            await async_setup(hass, {})

        entry = MagicMock()
        entry.entry_id = "e1"
        hass.config_entries.async_entries = MagicMock(return_value=[])
        with patch(
            "custom_components.cover_time_based.async_get_position_store"
        ) as mock_store:
            mock_store.return_value.async_remove = AsyncMock()
            await async_remove_entry(hass, entry)

        assert resources.deleted == ["abc"]

    @pytest.mark.asyncio
    async def test_remove_entry_keeps_resource_when_others_remain(self):
        resources = FakeResources(
            items=[{"id": "new-id", "url": _CARD_JS_URL}], loaded=True
        )
        entry = MagicMock()
        entry.entry_id = "e1"
        other = MagicMock()
        other.entry_id = "e2"
        hass = self._make_remove_hass(resources, remaining=[other])

        with patch(
            "custom_components.cover_time_based.async_get_position_store"
        ) as mock_store:
            mock_store.return_value.async_remove = AsyncMock()
            await async_remove_entry(hass, entry)

        assert resources.deleted == []

    @pytest.mark.asyncio
    async def test_remove_entry_excludes_self_from_remaining(self):
        # HA may still list the entry being removed; it must not count as a
        # surviving consumer of the resource.
        resources = FakeResources(
            items=[{"id": "new-id", "url": _CARD_JS_URL}], loaded=True
        )
        entry = MagicMock()
        entry.entry_id = "e1"
        hass = self._make_remove_hass(resources, remaining=[entry])

        with patch(
            "custom_components.cover_time_based.async_get_position_store"
        ) as mock_store:
            mock_store.return_value.async_remove = AsyncMock()
            await async_remove_entry(hass, entry)

        assert resources.deleted == ["new-id"]

    @pytest.mark.asyncio
    async def test_remove_last_entry_falls_back_to_remove_extra_js_url(self):
        # Registered via the add_extra_js_url fallback → no stored resource id.
        entry = MagicMock()
        entry.entry_id = "e1"
        hass = self._make_remove_hass(None, remaining=[], stored_id=None)

        with (
            patch(
                "custom_components.cover_time_based.async_get_position_store"
            ) as mock_store,
            patch(
                "homeassistant.components.frontend.remove_extra_js_url"
            ) as mock_remove_js,
        ):
            mock_store.return_value.async_remove = AsyncMock()
            await async_remove_entry(hass, entry)

        mock_remove_js.assert_called_once()
        _, js_url = mock_remove_js.call_args.args
        assert js_url == _CARD_JS_URL
