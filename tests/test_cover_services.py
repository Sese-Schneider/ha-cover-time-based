"""Tests for cover.py service registration and resolve_entity."""

import json
from pathlib import Path

import pytest
import voluptuous as vol
import yaml
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import HomeAssistantError

from custom_components.cover_time_based.helpers import resolve_entity
from custom_components.cover_time_based.cover import (
    _register_services,
    _create_cover_from_options,
    CONF_CONTROL_MODE,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_TRAVEL_TIME_CLOSE,
    CONF_TRAVEL_TIME_OPEN,
    CONTROL_MODE_SWITCH,
    SERVICE_START_CALIBRATION,
    SERVICE_STOP_CALIBRATION,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_DIR = REPO_ROOT / "custom_components" / "cover_time_based"


# ---------------------------------------------------------------------------
# resolve_entity
# ---------------------------------------------------------------------------


class TestResolveEntity:
    """Test resolve_entity from cover.py (raises on error)."""

    def test_raises_when_no_cover_component(self):
        hass = MagicMock()
        hass.data = {}

        with pytest.raises(HomeAssistantError, match="Cover platform not loaded"):
            resolve_entity(hass, "cover.test")

    def test_raises_when_entity_components_has_no_cover(self):
        hass = MagicMock()
        hass.data = {"entity_components": {}}

        with pytest.raises(HomeAssistantError, match="Cover platform not loaded"):
            resolve_entity(hass, "cover.test")

    def test_raises_when_entity_not_found(self):
        component = MagicMock()
        component.get_entity.return_value = None

        hass = MagicMock()
        hass.data = {"entity_components": {"cover": component}}

        with pytest.raises(HomeAssistantError, match="cover.test"):
            resolve_entity(hass, "cover.test")

    def test_raises_when_not_cover_time_based(self):
        """Entity exists but is not a CoverTimeBased instance."""
        component = MagicMock()
        component.get_entity.return_value = MagicMock()  # not CoverTimeBased

        hass = MagicMock()
        hass.data = {"entity_components": {"cover": component}}

        with pytest.raises(HomeAssistantError, match="not a cover_time_based"):
            resolve_entity(hass, "cover.test")

    def test_returns_valid_entity(self):
        """Valid CoverTimeBased entity is returned."""
        entity = _create_cover_from_options(
            {
                CONF_CONTROL_MODE: CONTROL_MODE_SWITCH,
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                CONF_TRAVEL_TIME_CLOSE: 30,
                CONF_TRAVEL_TIME_OPEN: 30,
            },
            device_id="test",
            name="Test",
        )

        component = MagicMock()
        component.get_entity.return_value = entity

        hass = MagicMock()
        hass.data = {"entity_components": {"cover": component}}

        result = resolve_entity(hass, "cover.test")
        assert result is entity


# ---------------------------------------------------------------------------
# _register_services (calibration handlers)
# ---------------------------------------------------------------------------


class TestServiceHandlers:
    """Test calibration service handler closures."""

    @pytest.mark.asyncio
    async def test_start_calibration_handler(self):
        """_handle_start_calibration resolves entity and calls start_calibration."""
        hass = MagicMock()
        hass.services.has_service.return_value = False
        hass.services.async_register = MagicMock()

        platform = MagicMock()
        platform.hass = hass

        _register_services(platform)

        # Find the start_calibration handler from async_register calls
        handler = None
        for call in hass.services.async_register.call_args_list:
            if call[0][1] == SERVICE_START_CALIBRATION:
                handler = call[0][2]
                break
        assert handler is not None

        # Mock entity and call the handler
        mock_entity = MagicMock()
        mock_entity.start_calibration = AsyncMock()

        service_call = MagicMock()
        service_call.data = {
            "entity_id": "cover.test",
            "attribute": "travel_time_close",
            "timeout": 60.0,
        }

        from unittest.mock import patch

        with patch(
            "custom_components.cover_time_based.cover.resolve_entity",
            return_value=mock_entity,
        ):
            await handler(service_call)

        mock_entity.start_calibration.assert_awaited_once_with(
            attribute="travel_time_close", timeout=60.0
        )

    @pytest.mark.asyncio
    async def test_stop_calibration_handler(self):
        """_handle_stop_calibration resolves entity and calls stop_calibration."""
        hass = MagicMock()
        hass.services.has_service.return_value = False
        hass.services.async_register = MagicMock()

        platform = MagicMock()
        platform.hass = hass

        _register_services(platform)

        # Find the stop_calibration handler
        handler = None
        for call in hass.services.async_register.call_args_list:
            if call[0][1] == SERVICE_STOP_CALIBRATION:
                handler = call[0][2]
                break
        assert handler is not None

        mock_entity = MagicMock()
        mock_entity.stop_calibration = AsyncMock(
            return_value={"attribute": "travel_time_close", "value": 45.0}
        )

        service_call = MagicMock()
        service_call.data = {"entity_id": "cover.test", "cancel": False}

        from unittest.mock import patch

        with patch(
            "custom_components.cover_time_based.cover.resolve_entity",
            return_value=mock_entity,
        ):
            await handler(service_call)

        mock_entity.stop_calibration.assert_awaited_once_with(cancel=False)


# ---------------------------------------------------------------------------
# start_calibration service schema — timeout ceiling
# ---------------------------------------------------------------------------


class TestStartCalibrationServiceSchemaValidation:
    """services.yaml advertises a 600s max timeout; the service schema
    registered here must enforce it too (it previously only enforced a
    minimum of 1, matching the same gap fixed in the ws schema)."""

    @staticmethod
    def _get_schema():
        hass = MagicMock()
        hass.services.has_service.return_value = False
        hass.services.async_register = MagicMock()

        platform = MagicMock()
        platform.hass = hass

        _register_services(platform)

        for call in hass.services.async_register.call_args_list:
            if call[0][1] == SERVICE_START_CALIBRATION:
                return call[1]["schema"]
        raise AssertionError("start_calibration service was not registered")

    def test_timeout_over_600_rejected(self):
        schema = self._get_schema()
        with pytest.raises(vol.Invalid):
            schema(
                {
                    "entity_id": "cover.test",
                    "attribute": "travel_time_close",
                    "timeout": 100000,
                }
            )

    def test_timeout_within_range_accepted(self):
        schema = self._get_schema()
        validated = schema(
            {
                "entity_id": "cover.test",
                "attribute": "travel_time_close",
                "timeout": 100,
            }
        )
        assert validated["timeout"] == 100.0


# ---------------------------------------------------------------------------
# strings.json service fields must match services.yaml field names
# ---------------------------------------------------------------------------


class TestServiceFieldTranslationsMatchServicesYaml:
    """strings.json documents each service's fields for the HA service UI;
    a field key that doesn't match the corresponding services.yaml field
    renders untranslated (raw key) or documents a field that doesn't exist.

    set_known_tilt_position previously keyed its field "position" instead of
    the real "tilt_position" (untranslated in the UI), and both
    set_known_position and set_known_tilt_position listed a phantom
    "entity_id" field even though those services are target:-based, not
    entity_id-field-based. This guards both directions for every service.
    """

    @staticmethod
    def _services_yaml_fields() -> dict[str, set[str]]:
        services = yaml.safe_load(
            (COMPONENT_DIR / "services.yaml").read_text(encoding="utf-8")
        )
        return {
            name: set((definition.get("fields") or {}).keys())
            for name, definition in services.items()
        }

    @staticmethod
    def _strings_json_fields() -> dict[str, set[str]]:
        strings = json.loads(
            (COMPONENT_DIR / "strings.json").read_text(encoding="utf-8")
        )
        return {
            name: set(definition.get("fields", {}).keys())
            for name, definition in strings["services"].items()
        }

    def test_every_service_has_matching_field_keys(self):
        yaml_fields = self._services_yaml_fields()
        strings_fields = self._strings_json_fields()

        assert set(strings_fields) == set(yaml_fields), (
            "strings.json services and services.yaml services must be the same "
            f"set: strings.json has {sorted(strings_fields)}, "
            f"services.yaml has {sorted(yaml_fields)}"
        )

        for service in yaml_fields:
            assert strings_fields[service] == yaml_fields[service], (
                f"{service}: strings.json field keys {sorted(strings_fields[service])} "
                f"must match services.yaml field keys {sorted(yaml_fields[service])} "
                "— a mismatched key renders untranslated, a phantom key documents a "
                "field that doesn't exist"
            )

    def test_entity_id_stays_a_real_field_on_calibration_services(self):
        """start_calibration/stop_calibration genuinely define entity_id in
        services.yaml (they are not target:-based) — the cross-check above
        must not have been satisfied by deleting it from those too."""
        yaml_fields = self._services_yaml_fields()
        strings_fields = self._strings_json_fields()

        for service in ("start_calibration", "stop_calibration"):
            assert "entity_id" in yaml_fields[service]
            assert "entity_id" in strings_fields[service]
