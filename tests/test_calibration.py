"""Tests for calibration services."""

import asyncio

import pytest
from unittest.mock import patch, MagicMock


class TestConfigEntryAccess:
    """Test that config entry ID is available on the entity."""

    def test_config_entry_id_stored(self, make_cover):
        """Cover should store its config entry ID."""
        cover = make_cover()
        assert cover._config_entry_id == "test_cover"


class TestCalibrationState:
    """Test the CalibrationState dataclass."""

    def test_initial_state(self):
        """CalibrationState should initialize with required fields."""
        from custom_components.cover_time_based.calibration import CalibrationState

        state = CalibrationState(
            attribute="travel_time_down",
            timeout=120.0,
        )
        assert state.attribute == "travel_time_down"
        assert state.timeout == 120.0
        assert state.started_at is not None
        assert state.step_count == 0
        assert state.step_duration is None
        assert state.last_pulse_duration is None
        assert state.timeout_task is None
        assert state.automation_task is None

    def test_constants_defined(self):
        """Calibration constants should be accessible."""
        from custom_components.cover_time_based.calibration import (
            CALIBRATION_STEP_PAUSE,
            CALIBRATION_OVERHEAD_STEPS,
            CALIBRATION_MIN_MOVEMENT_START,
            CALIBRATION_MIN_MOVEMENT_INCREMENT,
            CALIBRATABLE_ATTRIBUTES,
            SERVICE_START_CALIBRATION,
            SERVICE_STOP_CALIBRATION,
        )

        assert CALIBRATION_STEP_PAUSE == 2.0
        assert CALIBRATION_OVERHEAD_STEPS == 10
        assert CALIBRATION_MIN_MOVEMENT_START == 0.1
        assert CALIBRATION_MIN_MOVEMENT_INCREMENT == 0.1
        assert len(CALIBRATABLE_ATTRIBUTES) == 7
        assert SERVICE_START_CALIBRATION == "start_calibration"
        assert SERVICE_STOP_CALIBRATION == "stop_calibration"


class TestStartCalibrationTravelTime:
    @pytest.mark.asyncio
    async def test_start_travel_time_down_moves_cover(self, make_cover):
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_down", timeout=120.0)
        assert cover._calibration is not None
        assert cover._calibration.attribute == "travel_time_down"
        cover.hass.services.async_call.assert_awaited()

    @pytest.mark.asyncio
    async def test_start_travel_time_up_moves_cover(self, make_cover):
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_up", timeout=120.0)
        assert cover._calibration is not None
        assert cover._calibration.attribute == "travel_time_up"

    @pytest.mark.asyncio
    async def test_cannot_start_while_calibrating(self, make_cover):
        from homeassistant.exceptions import HomeAssistantError

        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_down", timeout=120.0)
            with pytest.raises(HomeAssistantError, match="already"):
                await cover.start_calibration(attribute="travel_time_up", timeout=120.0)

    @pytest.mark.asyncio
    async def test_calibration_exposes_state_attributes(self, make_cover):
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_down", timeout=120.0)
        attrs = cover.extra_state_attributes
        assert attrs["calibration_active"] is True
        assert attrs["calibration_attribute"] == "travel_time_down"

    @pytest.mark.asyncio
    async def test_no_calibration_attributes_when_inactive(self, make_cover):
        cover = make_cover()
        attrs = cover.extra_state_attributes
        assert "calibration_active" not in attrs


class TestStopCalibrationTravelTime:
    @pytest.mark.asyncio
    async def test_stop_calculates_elapsed_time(self, make_cover):
        cover = make_cover()
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_down", timeout=120.0)
            cover._calibration.started_at -= 45.0
            result = await cover.stop_calibration()

        assert result["value"] == pytest.approx(45.0, abs=0.5)
        assert cover._calibration is None
        cover.hass.config_entries.async_update_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_with_cancel_discards(self, make_cover):
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_down", timeout=120.0)
            result = await cover.stop_calibration(cancel=True)
        assert cover._calibration is None
        assert "value" not in result

    @pytest.mark.asyncio
    async def test_stop_without_active_calibration_raises(self, make_cover):
        from homeassistant.exceptions import HomeAssistantError

        cover = make_cover()
        with pytest.raises(HomeAssistantError, match="[Nn]o calibration"):
            await cover.stop_calibration()

    @pytest.mark.asyncio
    async def test_stop_cancels_timeout_task(self, make_cover):
        cover = make_cover()
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_down", timeout=120.0)
            timeout_task = cover._calibration.timeout_task
            await cover.stop_calibration()

        await asyncio.sleep(0)  # Let event loop process cancellation
        assert timeout_task.cancelled()
