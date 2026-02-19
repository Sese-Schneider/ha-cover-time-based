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
            attribute="travel_time_close",
            timeout=120.0,
        )
        assert state.attribute == "travel_time_close"
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
        assert CALIBRATION_OVERHEAD_STEPS == 8
        assert CALIBRATION_MIN_MOVEMENT_START == 0.1
        assert CALIBRATION_MIN_MOVEMENT_INCREMENT == 0.1
        assert len(CALIBRATABLE_ATTRIBUTES) == 7
        assert SERVICE_START_CALIBRATION == "start_calibration"
        assert SERVICE_STOP_CALIBRATION == "stop_calibration"


class TestGetCalibratableAttributes:
    """Test get_calibratable_attributes filters by tilt mode."""

    def test_none_mode_excludes_tilt(self):
        from custom_components.cover_time_based.calibration import (
            get_calibratable_attributes,
        )

        attrs = get_calibratable_attributes("none")
        assert "travel_time_close" in attrs
        assert "travel_time_open" in attrs
        assert "travel_startup_delay" in attrs
        assert "min_movement_time" in attrs
        assert "tilt_time_close" not in attrs
        assert "tilt_time_open" not in attrs
        assert "tilt_startup_delay" not in attrs

    def test_sequential_includes_tilt(self):
        from custom_components.cover_time_based.calibration import (
            get_calibratable_attributes,
        )

        attrs = get_calibratable_attributes("sequential")
        assert "travel_time_close" in attrs
        assert "tilt_time_close" in attrs
        assert "tilt_time_open" in attrs
        assert "tilt_startup_delay" in attrs

    def test_proportional_excludes_tilt(self):
        from custom_components.cover_time_based.calibration import (
            get_calibratable_attributes,
        )

        attrs = get_calibratable_attributes("proportional")
        assert "travel_time_close" in attrs
        assert "tilt_time_close" not in attrs
        assert "tilt_time_open" not in attrs
        assert "tilt_startup_delay" not in attrs

    def test_dual_motor_includes_tilt(self):
        from custom_components.cover_time_based.calibration import (
            get_calibratable_attributes,
        )

        attrs = get_calibratable_attributes("dual_motor")
        assert "travel_time_close" in attrs
        assert "tilt_time_close" in attrs
        assert "tilt_time_open" in attrs
        assert "tilt_startup_delay" in attrs

    def test_returns_list(self):
        from custom_components.cover_time_based.calibration import (
            get_calibratable_attributes,
        )

        result = get_calibratable_attributes("none")
        assert isinstance(result, list)


class TestStartCalibrationTravelTime:
    @pytest.mark.asyncio
    async def test_start_travel_time_close_moves_cover(self, make_cover):
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_close", timeout=120.0)
        assert cover._calibration is not None
        assert cover._calibration.attribute == "travel_time_close"
        cover.hass.services.async_call.assert_awaited()

    @pytest.mark.asyncio
    async def test_start_travel_time_open_moves_cover(self, make_cover):
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_open", timeout=120.0)
        assert cover._calibration is not None
        assert cover._calibration.attribute == "travel_time_open"

    @pytest.mark.asyncio
    async def test_cannot_start_while_calibrating(self, make_cover):
        from homeassistant.exceptions import HomeAssistantError

        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_close", timeout=120.0)
            with pytest.raises(HomeAssistantError, match="already"):
                await cover.start_calibration(
                    attribute="travel_time_open", timeout=120.0
                )

    @pytest.mark.asyncio
    async def test_calibration_exposes_state_attributes(self, make_cover):
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_close", timeout=120.0)
        attrs = cover.extra_state_attributes
        assert attrs["calibration_active"] is True
        assert attrs["calibration_attribute"] == "travel_time_close"

    @pytest.mark.asyncio
    async def test_no_calibration_attributes_when_inactive(self, make_cover):
        cover = make_cover()
        attrs = cover.extra_state_attributes
        assert "calibration_active" not in attrs


class TestStopCalibrationTravelTime:
    @pytest.mark.asyncio
    async def test_stop_calculates_elapsed_time(self, make_cover):
        cover = make_cover()

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_close", timeout=120.0)
            cover._calibration.started_at -= 45.0
            result = await cover.stop_calibration()

        assert result["attribute"] == "travel_time_close"
        assert result["value"] == pytest.approx(45.0, abs=0.5)
        assert cover._calibration is None

    @pytest.mark.asyncio
    async def test_stop_with_cancel_discards(self, make_cover):
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_close", timeout=120.0)
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
            await cover.start_calibration(attribute="travel_time_close", timeout=120.0)
            timeout_task = cover._calibration.timeout_task
            await cover.stop_calibration()

        await asyncio.sleep(0)  # Let event loop process cancellation
        assert timeout_task.cancelled()


class TestCancelDoesNotReturn:
    """When cancelled, cover should stop but NOT automatically return."""

    @pytest.mark.asyncio
    async def test_cancel_stops_motor_without_return(self, make_cover):
        """Cancelling should stop the motor but not drive cover back."""
        cover = make_cover(travel_time_close=20, travel_time_open=20)
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_close", timeout=120.0)
            result = await cover.stop_calibration(cancel=True)

        assert cover._calibration is None
        assert "value" not in result
        # No return trip: no open command after the initial close + stop
        open_calls = [
            c
            for c in cover.hass.services.async_call.await_args_list
            if c.args[1] == "turn_on" and "open" in str(c.args[2].get("entity_id", ""))
        ]
        # Only the initial close was sent, no open command for return
        assert len(open_calls) == 0

    @pytest.mark.asyncio
    async def test_cancel_does_not_update_position(self, make_cover):
        """Cancelling should not change the tracked position."""
        cover = make_cover(travel_time_close=20, travel_time_open=20)
        cover.travel_calc.set_position(50)
        original_position = cover.travel_calc.current_position()

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_close", timeout=120.0)
            await cover.stop_calibration(cancel=True)

        assert cover.travel_calc.current_position() == original_position

    @pytest.mark.asyncio
    async def test_successful_stop_sets_endpoint_position(self, make_cover):
        """Successful stop should set tracked position to the endpoint."""
        cover = make_cover(travel_time_close=20, travel_time_open=20)

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_close", timeout=120.0)
            await cover.stop_calibration()

        # Position at the close endpoint (0 in travel_calc = close direction endpoint)
        assert cover.travel_calc.current_position() == 0


class TestCalibrationTiltTime:
    @pytest.mark.asyncio
    async def test_start_tilt_time_close(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="tilt_time_close", timeout=30.0)
        assert cover._calibration.attribute == "tilt_time_close"

    @pytest.mark.asyncio
    async def test_start_tilt_time_open(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="tilt_time_open", timeout=30.0)
        assert cover._calibration.attribute == "tilt_time_open"

    @pytest.mark.asyncio
    async def test_tilt_rejected_when_tilt_mode_during(self, make_cover):
        from homeassistant.exceptions import HomeAssistantError

        cover = make_cover(
            tilt_time_close=5.0, tilt_time_open=5.0, tilt_mode="proportional"
        )
        with pytest.raises(HomeAssistantError, match="proportional tilt mode"):
            await cover.start_calibration(attribute="tilt_time_close", timeout=30.0)


class TestMotorOverheadCalibration:
    @pytest.mark.asyncio
    async def test_prerequisite_travel_time_required(self, make_cover):
        from homeassistant.exceptions import HomeAssistantError

        cover = make_cover()
        # Factory defaults travel_time to 30, so manually clear it
        cover._travel_time_close = None
        cover._travel_time_open = None
        with pytest.raises(HomeAssistantError, match="[Tt]ravel time"):
            await cover.start_calibration(
                attribute="travel_startup_delay", timeout=300.0
            )

    @pytest.mark.asyncio
    async def test_starts_automated_steps(self, make_cover):
        cover = make_cover(travel_time_close=60.0, travel_time_open=60.0)
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_startup_delay", timeout=300.0
            )
        assert cover._calibration.automation_task is not None
        assert cover._calibration.step_duration == 6.0

    @pytest.mark.asyncio
    async def test_overhead_calculation(self, make_cover):
        cover = make_cover(travel_time_close=60.0, travel_time_open=60.0)
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        import time as time_mod

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_startup_delay", timeout=300.0
            )
            # Simulate 8 stepped moves completed, then continuous phase
            cover._calibration.step_count = 8
            # Continuous phase started 28s ago: 12s expected (0.2*60) + 16s overhead (8*2)
            cover._calibration.continuous_start = time_mod.monotonic() - 28.0
            result = await cover.stop_calibration()

        # overhead = (28.0 - 0.2*60) / 8 = (28.0 - 12.0) / 8 = 2.0
        assert result["value"] == pytest.approx(2.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_tilt_overhead_prerequisite(self, make_cover):
        from homeassistant.exceptions import HomeAssistantError

        cover = make_cover()  # No tilt time configured
        with pytest.raises(HomeAssistantError, match="[Tt]ilt time"):
            await cover.start_calibration(attribute="tilt_startup_delay", timeout=300.0)

    @pytest.mark.asyncio
    async def test_tilt_overhead_starts(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="tilt_startup_delay", timeout=300.0)
        assert cover._calibration.automation_task is not None
        assert cover._calibration.step_duration == 0.5


class TestMinMovementTimeCalibration:
    @pytest.mark.asyncio
    async def test_starts_incremental_pulses(self, make_cover):
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="min_movement_time", timeout=60.0)
        assert cover._calibration.automation_task is not None

    @pytest.mark.asyncio
    async def test_min_movement_result_is_last_pulse(self, make_cover):
        cover = make_cover()
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="min_movement_time", timeout=60.0)
            # Simulate 5 pulses (0.1, 0.2, 0.3, 0.4, 0.5)
            cover._calibration.step_count = 5
            cover._calibration.last_pulse_duration = 0.5
            result = await cover.stop_calibration()

        assert result["value"] == pytest.approx(0.5)


class TestCalibrationTimeout:
    @pytest.mark.asyncio
    async def test_timeout_stops_motor_and_clears_state(self, make_cover):
        """Timeout should stop motor, clear calibration, and not crash."""
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_close", timeout=0.1)
            # Wait for timeout to fire
            await asyncio.sleep(0.2)
        assert cover._calibration is None

    @pytest.mark.asyncio
    async def test_timeout_cancels_automation_task(self, make_cover):
        """Timeout during overhead test should cancel automation task."""
        cover = make_cover(travel_time_close=60.0, travel_time_open=60.0)
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_startup_delay", timeout=0.1)
            automation_task = cover._calibration.automation_task
            await asyncio.sleep(0.3)
        assert cover._calibration is None
        assert automation_task.done()  # Should be cancelled
