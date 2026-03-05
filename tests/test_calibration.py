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
            CALIBRATION_TILT_OVERHEAD_STEPS,
            CALIBRATION_MIN_MOVEMENT_START,
            CALIBRATION_MIN_MOVEMENT_INCREMENT,
            CALIBRATABLE_ATTRIBUTES,
            SERVICE_START_CALIBRATION,
            SERVICE_STOP_CALIBRATION,
        )

        assert CALIBRATION_STEP_PAUSE == 2.0
        assert CALIBRATION_OVERHEAD_STEPS == 8
        assert CALIBRATION_TILT_OVERHEAD_STEPS == 3
        assert CALIBRATION_MIN_MOVEMENT_START == 0.1
        assert CALIBRATION_MIN_MOVEMENT_INCREMENT == 0.1
        assert len(CALIBRATABLE_ATTRIBUTES) == 7
        assert SERVICE_START_CALIBRATION == "start_calibration"
        assert SERVICE_STOP_CALIBRATION == "stop_calibration"


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
    async def test_zeros_startup_delay_during_test(self, make_cover):
        """Startup delay is zeroed during test and restored after."""
        cover = make_cover(
            travel_time_close=60.0,
            travel_time_open=60.0,
            travel_startup_delay=0.5,
        )
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        import time as time_mod

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_startup_delay", timeout=300.0
            )
            # During test, delay should be zeroed
            assert cover._travel_startup_delay is None
            assert cover._calibration.saved_startup_delay == 0.5

            # Stop calibration (simulate completed test)
            cover._calibration.step_count = 8
            cover._calibration.continuous_start = time_mod.monotonic() - 28.0
            await cover.stop_calibration()

        # After test, delay should be restored
        assert cover._travel_startup_delay == 0.5

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
            # expected_remaining = (1 - 8/10) * 60 = 12s
            # Continuous phase started 28s ago: 12s expected + 16s overhead (8*2)
            cover._calibration.continuous_start = time_mod.monotonic() - 28.0
            result = await cover.stop_calibration()

        # overhead = (28.0 - 12.0) / 8 = 2.0
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
        # tilt: 3 steps, total_divisions=5, step_pct=20, step_duration=5.0*20/100=1.0
        assert cover._calibration.step_duration == 1.0

    @pytest.mark.asyncio
    async def test_tilt_zeros_startup_delay(self, make_cover):
        """Tilt startup delay is zeroed during test and restored after."""
        cover = make_cover(
            tilt_time_close=10.0,
            tilt_time_open=10.0,
            tilt_startup_delay=0.3,
        )
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        import time as time_mod

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="tilt_startup_delay", timeout=300.0)
            assert cover._tilt_startup_delay is None
            assert cover._calibration.saved_startup_delay == 0.3

            cover._calibration.step_count = 3
            cover._calibration.continuous_start = time_mod.monotonic() - 10.0
            await cover.stop_calibration()

        assert cover._tilt_startup_delay == 0.3

    @pytest.mark.asyncio
    async def test_tilt_overhead_calculation(self, make_cover):
        """Tilt overhead uses 3 steps, so expected_remaining = 0.7 * total_time."""
        cover = make_cover(tilt_time_close=10.0, tilt_time_open=10.0)
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        import time as time_mod

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="tilt_startup_delay", timeout=300.0)
            # Simulate 3 stepped moves completed, then continuous phase
            cover._calibration.step_count = 3
            # expected_remaining = (1 - 3/10) * 10 = 7.0s
            # Continuous phase started 10s ago: 7s expected + 3s overhead (3*1.0)
            cover._calibration.continuous_start = time_mod.monotonic() - 10.0
            result = await cover.stop_calibration()

        # overhead = (10.0 - 7.0) / 3 = 1.0
        assert result["value"] == pytest.approx(1.0, abs=0.1)


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


class TestCalibrationEdgeCases:
    """Test edge cases for calibration."""

    @pytest.mark.asyncio
    async def test_tilt_calibration_rejected_when_strategy_forbids(self, make_cover):
        """Tilt time calibration should be rejected when strategy says no."""
        from homeassistant.exceptions import HomeAssistantError

        cover = make_cover(
            tilt_time_close=5.0, tilt_time_open=5.0, tilt_mode="sequential"
        )
        # Mock strategy to reject tilt calibration
        cover._tilt_strategy.can_calibrate_tilt = lambda: False
        with pytest.raises(HomeAssistantError, match="[Tt]ilt.*not available"):
            await cover.start_calibration(attribute="tilt_time_close", timeout=30.0)

    def test_resolve_direction_explicit_close(self, make_cover):
        """_resolve_direction returns CLOSE for explicit 'close'."""
        from custom_components.cover_time_based.cover_base import CoverTimeBased
        from homeassistant.const import SERVICE_CLOSE_COVER

        result = CoverTimeBased._resolve_direction("close", 75)
        assert result == SERVICE_CLOSE_COVER

    def test_resolve_direction_explicit_open(self, make_cover):
        """_resolve_direction returns OPEN for explicit 'open'."""
        from custom_components.cover_time_based.cover_base import CoverTimeBased
        from homeassistant.const import SERVICE_OPEN_COVER

        result = CoverTimeBased._resolve_direction("open", 25)
        assert result == SERVICE_OPEN_COVER

    def test_resolve_direction_auto_from_low_position(self, make_cover):
        """_resolve_direction auto-detects OPEN when position < 50."""
        from custom_components.cover_time_based.cover_base import CoverTimeBased
        from homeassistant.const import SERVICE_OPEN_COVER

        result = CoverTimeBased._resolve_direction(None, 25)
        assert result == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_stop_min_movement_no_pulses_returns_zero(self, make_cover):
        """Stopping min_movement calibration before any pulses returns 0."""
        cover = make_cover()
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="min_movement_time", timeout=60.0)
            # Cancel the automation task before any pulses
            cover._calibration.automation_task.cancel()
            await asyncio.sleep(0)
            result = await cover.stop_calibration()

        assert result["value"] == 0.0

    @pytest.mark.asyncio
    async def test_stop_overhead_before_continuous_returns_zero(self, make_cover):
        """Stopping overhead calibration before continuous phase returns 0."""
        cover = make_cover(travel_time_close=60.0, travel_time_open=60.0)
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_startup_delay", timeout=300.0
            )
            # Cancel automation task before continuous phase
            cover._calibration.automation_task.cancel()
            await asyncio.sleep(0)
            # continuous_start is still None
            result = await cover.stop_calibration()

        assert result["value"] == 0.0

    @pytest.mark.asyncio
    async def test_start_with_explicit_direction(self, make_cover):
        """start_calibration with direction='close' passes through."""
        from homeassistant.const import SERVICE_CLOSE_COVER

        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_time_close", timeout=120.0, direction="close"
            )

        assert cover._calibration.move_command == SERVICE_CLOSE_COVER


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


class TestOverheadFallbackTravelTime:
    """Test fallback travel_time selection in _start_overhead_test (lines 141, 152)."""

    @pytest.mark.asyncio
    async def test_travel_startup_delay_open_direction_falls_back_to_close_time(
        self, make_cover
    ):
        """Line 141: travel_time = self._travel_time_open or self._travel_time_close.

        When direction=open but only travel_time_close is configured,
        the fallback branch should use travel_time_close.
        """
        cover = make_cover(travel_time_close=60.0, travel_time_open=60.0)
        # Clear open time so the `or` fallback fires
        cover._travel_time_open = None
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_startup_delay", timeout=300.0, direction="open"
            )
        assert cover._calibration is not None
        assert cover._calibration.automation_task is not None
        # step_duration = travel_time / 10 = 60 / 10 = 6.0
        assert cover._calibration.step_duration == 6.0

    @pytest.mark.asyncio
    async def test_tilt_startup_delay_open_direction_falls_back_to_close_time(
        self, make_cover
    ):
        """Line 152: travel_time = self._tilting_time_open or self._tilting_time_close.

        When direction=open but only tilting_time_close is configured,
        the fallback branch should use tilting_time_close.
        """
        cover = make_cover(tilt_time_close=10.0, tilt_time_open=10.0)
        # Clear open time so the `or` fallback fires
        cover._tilting_time_open = None
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="tilt_startup_delay", timeout=300.0, direction="open"
            )
        assert cover._calibration is not None
        assert cover._calibration.automation_task is not None
        # tilt: 3 steps, total_divisions=5, step_pct=20, step_duration=10.0*20/100=2.0
        assert cover._calibration.step_duration == 2.0


class TestSetPositionAfterCalibrationNoTilt:
    """Test _set_position_after_calibration with tilt attr but no tilt_calc (line 357)."""

    def test_tilt_attr_on_cover_without_tilt_support(self, make_cover):
        """Line 357: if is_tilt and not hasattr(self, 'tilt_calc'): return.

        Create a cover without tilt support, then call
        _set_position_after_calibration with a tilt attribute.
        It should return early without error.
        """
        from custom_components.cover_time_based.calibration import CalibrationState
        from homeassistant.const import SERVICE_CLOSE_COVER

        cover = make_cover()  # No tilt configured => no tilt_calc
        # Ensure no tilt_calc exists
        if hasattr(cover, "tilt_calc"):
            delattr(cover, "tilt_calc")

        cal_state = CalibrationState(attribute="tilt_time_close", timeout=30.0)
        cal_state.move_command = SERVICE_CLOSE_COVER

        # Should return early without raising
        original_position = cover.travel_calc.current_position()
        cover._set_position_after_calibration(cal_state)
        # Travel position should be unchanged (tilt path was a no-op)
        assert cover.travel_calc.current_position() == original_position


class TestCalibrationResultOpenDirection:
    """Test _calculate_calibration_result for OPEN direction (lines 385, 390)."""

    @pytest.mark.asyncio
    async def test_travel_startup_delay_open_direction_result(self, make_cover):
        """Lines 384-385: total_time = self._travel_time_open or self._travel_time_close.

        Run calibration result calculation for travel_startup_delay
        in the OPEN direction.
        """
        import time as time_mod
        from homeassistant.const import SERVICE_OPEN_COVER

        cover = make_cover(travel_time_close=60.0, travel_time_open=60.0)
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_startup_delay", timeout=300.0, direction="open"
            )
            assert cover._calibration.move_command == SERVICE_OPEN_COVER
            # Simulate 8 stepped moves completed, then continuous phase
            cover._calibration.step_count = 8
            # expected_remaining = (1 - 8/10) * 60 = 12s
            # Continuous phase started 28s ago: 12s expected + 16s overhead (8*2)
            cover._calibration.continuous_start = time_mod.monotonic() - 28.0
            result = await cover.stop_calibration()

        # overhead = (28.0 - 12.0) / 8 = 2.0
        assert result["value"] == pytest.approx(2.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_tilt_startup_delay_open_direction_result(self, make_cover):
        """Lines 389-390: total_time = self._tilting_time_open or self._tilting_time_close.

        Run calibration result calculation for tilt_startup_delay
        in the OPEN direction.
        """
        import time as time_mod
        from homeassistant.const import SERVICE_OPEN_COVER

        cover = make_cover(tilt_time_close=10.0, tilt_time_open=10.0)
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="tilt_startup_delay", timeout=300.0, direction="open"
            )
            assert cover._calibration.move_command == SERVICE_OPEN_COVER
            # Simulate 3 stepped moves completed, then continuous phase
            cover._calibration.step_count = 3
            # expected_remaining = (1 - 3/10) * 10 = 7.0s
            # Continuous phase started 10s ago: 7s expected + 3s overhead (3*1.0)
            cover._calibration.continuous_start = time_mod.monotonic() - 10.0
            result = await cover.stop_calibration()

        # overhead = (10.0 - 7.0) / 3 = 1.0
        assert result["value"] == pytest.approx(1.0, abs=0.1)


class TestCalibrationResultTotalTimeNone:
    """Test _calculate_calibration_result when total_time is None (lines 393-396)."""

    @pytest.mark.asyncio
    async def test_travel_startup_delay_with_no_travel_times_returns_zero(
        self, make_cover
    ):
        """Lines 392-396: total_time is None warning branch.

        Set both travel times to None after starting calibration, then
        call _calculate_calibration_result — should return 0.0 with warning.
        """
        import time as time_mod

        cover = make_cover(travel_time_close=60.0, travel_time_open=60.0)
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_startup_delay", timeout=300.0
            )
            # Simulate some progress
            cover._calibration.step_count = 8
            cover._calibration.continuous_start = time_mod.monotonic() - 28.0
            # Now clear both travel times so total_time resolves to None
            cover._travel_time_close = None
            cover._travel_time_open = None
            result = await cover.stop_calibration()

        assert result["value"] == 0.0


class TestPulseTimeSubtraction:
    """Test pulse_time subtraction in _calculate_calibration_result (line 410)."""

    @pytest.mark.asyncio
    async def test_pulse_time_subtracted_from_continuous_time(self, make_cover):
        """Line 410: continuous_time -= pulse_time.

        Set _pulse_time on the cover, run travel_startup_delay calibration,
        verify that pulse_time is subtracted from continuous_time in the
        overhead calculation.
        """
        import time as time_mod

        cover = make_cover(travel_time_close=60.0, travel_time_open=60.0)
        # Simulate a pulse/toggle mode cover by adding _pulse_time
        cover._pulse_time = 0.5
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_startup_delay", timeout=300.0
            )
            cover._calibration.step_count = 8
            # Without pulse subtraction: overhead = (28 - 12) / 8 = 2.0
            # With pulse_time=0.5: continuous_time becomes 28 - 0.5 = 27.5
            # overhead = (27.5 - 12) / 8 = 1.9375
            cover._calibration.continuous_start = time_mod.monotonic() - 28.0
            result = await cover.stop_calibration()

        # overhead = (28 - 0.5 - 12) / 8 = 1.9375
        assert result["value"] == pytest.approx(1.94, abs=0.1)


class TestUnexpectedCalibrationAttribute:
    """Test ValueError for unexpected attribute (line 433)."""

    @pytest.mark.asyncio
    async def test_unexpected_attribute_raises_value_error(self, make_cover):
        """Line 433: raise ValueError(...) for unexpected attribute.

        Manually set calibration attribute to something invalid, then
        call _calculate_calibration_result — should raise ValueError.
        """
        from custom_components.cover_time_based.calibration import CalibrationState

        cover = make_cover()
        cover._calibration = CalibrationState(attribute="bogus_attribute", timeout=60.0)
        with pytest.raises(ValueError, match="Unexpected calibration attribute"):
            cover._calculate_calibration_result()


class TestOverheadStepsFullRun:
    """Test the position-polling loop and continuous phase of _run_overhead_steps (lines 209, 223-234)."""

    @pytest.mark.asyncio
    async def test_run_overhead_steps_reaches_continuous_phase(self, make_cover):
        """Lines 209, 223-234: The position-polling loop and continuous phase.

        Run the full overhead automation task with a travel calculator
        that reaches target quickly so the step loop completes and
        the continuous phase begins.
        """
        cover = make_cover(travel_time_close=1.0, travel_time_open=1.0)

        # Use very short travel times so steps complete fast.
        # Patch CALIBRATION_STEP_PAUSE to speed up the test (lazily
        # imported from calibration module inside _run_overhead_steps).
        with (
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.cover_time_based.calibration.CALIBRATION_STEP_PAUSE",
                0.05,
            ),
        ):
            await cover.start_calibration(
                attribute="travel_startup_delay", timeout=300.0
            )
            # Let the automation run through the steps.
            # With travel_time=1.0, step_duration=0.1, each step
            # targets 10% increments which the travel_calc should reach
            # quickly.
            for _ in range(500):
                await asyncio.sleep(0.05)
                if (
                    cover._calibration is not None
                    and cover._calibration.continuous_start is not None
                ):
                    break

            # Verify the continuous phase was reached
            assert cover._calibration is not None
            assert cover._calibration.continuous_start is not None
            assert cover._calibration.step_count == 8

            # Now stop calibration to calculate result
            mock_entry = MagicMock()
            mock_entry.options = {}
            cover.hass.config_entries.async_get_entry = MagicMock(
                return_value=mock_entry
            )
            cover.hass.config_entries.async_update_entry = MagicMock()
            result = await cover.stop_calibration()

        assert result["attribute"] == "travel_startup_delay"
        assert result["value"] >= 0


class TestMinMovementPulseLoop:
    """Test min_movement pulse loop (lines 260-272)."""

    @pytest.mark.asyncio
    async def test_min_movement_runs_multiple_pulses(self, make_cover):
        """Lines 260-272: min_movement pulse loop.

        Start min_movement calibration, let it run a couple pulses,
        then stop and verify step_count and last_pulse_duration.
        """
        cover = make_cover()
        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        cover.hass.config_entries.async_update_entry = MagicMock()

        with patch.object(cover, "async_write_ha_state"):
            # Patch the initial pause to be very short so pulses start quickly.
            # These constants are lazily imported from the calibration module
            # inside _run_min_movement_pulses, so patching the source works.
            with (
                patch(
                    "custom_components.cover_time_based.calibration.CALIBRATION_MIN_MOVEMENT_INITIAL_PAUSE",
                    0.05,
                ),
                patch(
                    "custom_components.cover_time_based.calibration.CALIBRATION_STEP_PAUSE",
                    0.05,
                ),
            ):
                await cover.start_calibration(
                    attribute="min_movement_time", timeout=60.0
                )
                # Wait for at least 2 pulses to complete
                for _ in range(200):
                    await asyncio.sleep(0.05)
                    if (
                        cover._calibration is not None
                        and cover._calibration.step_count >= 2
                    ):
                        break

                assert cover._calibration is not None
                assert cover._calibration.step_count >= 2
                assert cover._calibration.last_pulse_duration is not None
                # Each pulse is 0.1s + 0.1s increment, so after 2 pulses
                # last_pulse_duration should be 0.2
                assert cover._calibration.last_pulse_duration == pytest.approx(
                    0.1 * cover._calibration.step_count, abs=0.01
                )

                result = await cover.stop_calibration()

        assert cover._calibration is None
        assert result["attribute"] == "min_movement_time"
        assert result["value"] >= 0.2
