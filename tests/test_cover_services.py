"""Tests for cover.py service registration and _resolve_entity."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import HomeAssistantError

from custom_components.cover_time_based.cover import (
    _resolve_entity,
    _register_services,
    _create_cover_from_options,
    CONF_DEVICE_TYPE,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_INPUT_MODE,
    CONF_TRAVEL_TIME_CLOSE,
    CONF_TRAVEL_TIME_OPEN,
    DEVICE_TYPE_SWITCH,
    INPUT_MODE_SWITCH,
    SERVICE_START_CALIBRATION,
    SERVICE_STOP_CALIBRATION,
)


# ---------------------------------------------------------------------------
# _resolve_entity
# ---------------------------------------------------------------------------


class TestResolveEntity:
    """Test _resolve_entity from cover.py (raises on error)."""

    def test_raises_when_no_cover_component(self):
        hass = MagicMock()
        hass.data = {}

        with pytest.raises(HomeAssistantError, match="Cover platform not loaded"):
            _resolve_entity(hass, "cover.test")

    def test_raises_when_entity_components_has_no_cover(self):
        hass = MagicMock()
        hass.data = {"entity_components": {}}

        with pytest.raises(HomeAssistantError, match="Cover platform not loaded"):
            _resolve_entity(hass, "cover.test")

    def test_raises_when_entity_not_found(self):
        component = MagicMock()
        component.get_entity.return_value = None

        hass = MagicMock()
        hass.data = {"entity_components": {"cover": component}}

        with pytest.raises(HomeAssistantError, match="cover.test"):
            _resolve_entity(hass, "cover.test")

    def test_raises_when_not_cover_time_based(self):
        """Entity exists but is not a CoverTimeBased instance."""
        component = MagicMock()
        component.get_entity.return_value = MagicMock()  # not CoverTimeBased

        hass = MagicMock()
        hass.data = {"entity_components": {"cover": component}}

        with pytest.raises(HomeAssistantError, match="not a cover_time_based"):
            _resolve_entity(hass, "cover.test")

    def test_returns_valid_entity(self):
        """Valid CoverTimeBased entity is returned."""
        entity = _create_cover_from_options(
            {
                CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                CONF_INPUT_MODE: INPUT_MODE_SWITCH,
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

        result = _resolve_entity(hass, "cover.test")
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
            "custom_components.cover_time_based.cover._resolve_entity",
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
            "custom_components.cover_time_based.cover._resolve_entity",
            return_value=mock_entity,
        ):
            await handler(service_call)

        mock_entity.stop_calibration.assert_awaited_once_with(cancel=False)
