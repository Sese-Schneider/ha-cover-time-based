"""Tests targeting specific uncovered lines in planning.py and cover_base.py.

Covers:
- planning.py lines 17, 32, 55, 62, 65
- cover_base.py lines 302, 832, 1199, 180, 991-999
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER
from homeassistant.exceptions import HomeAssistantError

from custom_components.cover_time_based.tilt_strategies.base import TiltTo, TravelTo
from custom_components.cover_time_based.tilt_strategies.planning import (
    calculate_pre_step_delay,
    extract_coupled_tilt,
    extract_coupled_travel,
)
from custom_components.cover_time_based.travel_calculator import TravelCalculator


# ===================================================================
# planning.py: extract_coupled_tilt
# ===================================================================


class TestExtractCoupledTilt:
    """Test extract_coupled_tilt from planning.py."""

    def test_returns_coupled_tilt_from_travel_to_step(self):
        """Line 17: TravelTo with coupled_tilt returns that value."""
        steps = [TravelTo(target=50, coupled_tilt=30)]
        result = extract_coupled_tilt(steps)
        assert result == 30

    def test_returns_tilt_to_target_when_no_coupling(self):
        """TiltTo step returns its target."""
        steps = [TiltTo(target=75)]
        result = extract_coupled_tilt(steps)
        assert result == 75

    def test_coupled_tilt_takes_precedence_over_later_tilt_to(self):
        """TravelTo with coupled_tilt found before TiltTo is returned."""
        steps = [TravelTo(target=50, coupled_tilt=30), TiltTo(target=75)]
        result = extract_coupled_tilt(steps)
        assert result == 30

    def test_returns_none_for_travel_to_without_coupling(self):
        """TravelTo without coupled_tilt, no TiltTo => returns TravelTo target."""
        steps = [TravelTo(target=50)]
        result = extract_coupled_tilt(steps)
        # TravelTo without coupled_tilt is not None check fails, then no TiltTo => None
        assert result is None

    def test_returns_none_for_empty_steps(self):
        """Empty step list returns None."""
        steps = []
        result = extract_coupled_tilt(steps)
        assert result is None


# ===================================================================
# planning.py: extract_coupled_travel
# ===================================================================


class TestExtractCoupledTravel:
    """Test extract_coupled_travel from planning.py."""

    def test_returns_coupled_travel_from_tilt_to_step(self):
        """Line 32: TiltTo with coupled_travel returns that value."""
        steps = [TiltTo(target=50, coupled_travel=20)]
        result = extract_coupled_travel(steps)
        assert result == 20

    def test_returns_travel_to_target_when_no_coupling(self):
        """TravelTo step returns its target."""
        steps = [TravelTo(target=80)]
        result = extract_coupled_travel(steps)
        assert result == 80

    def test_coupled_travel_takes_precedence_over_later_travel_to(self):
        """TiltTo with coupled_travel found before TravelTo is returned."""
        steps = [TiltTo(target=50, coupled_travel=20), TravelTo(target=80)]
        result = extract_coupled_travel(steps)
        assert result == 20

    def test_returns_none_for_tilt_to_without_coupling(self):
        """TiltTo without coupled_travel, no TravelTo => None."""
        steps = [TiltTo(target=50)]
        result = extract_coupled_travel(steps)
        # TiltTo without coupled_travel is not None check fails, then no TravelTo => None
        assert result is None

    def test_returns_none_for_empty_steps(self):
        """Empty step list returns None."""
        steps = []
        result = extract_coupled_travel(steps)
        assert result is None


# ===================================================================
# planning.py: calculate_pre_step_delay
# ===================================================================


class TestCalculatePreStepDelay:
    """Test calculate_pre_step_delay from planning.py."""

    def test_returns_zero_when_strategy_is_none(self):
        """Strategy is None => 0.0."""
        steps = [TiltTo(50), TravelTo(30)]
        result = calculate_pre_step_delay(steps, None, None, None)
        assert result == 0.0

    def test_returns_zero_when_strategy_uses_tilt_motor(self):
        """Strategy uses tilt motor => 0.0."""
        strategy = MagicMock()
        strategy.uses_tilt_motor = True
        steps = [TiltTo(50), TravelTo(30)]
        result = calculate_pre_step_delay(steps, strategy, None, None)
        assert result == 0.0

    def test_returns_zero_when_fewer_than_two_steps(self):
        """Single step => 0.0."""
        strategy = MagicMock()
        strategy.uses_tilt_motor = False
        steps = [TravelTo(30)]
        result = calculate_pre_step_delay(steps, strategy, None, None)
        assert result == 0.0

    def test_tilt_before_travel_with_none_current_tilt(self):
        """Line 55: TiltTo then TravelTo, current_tilt is None => 0.0."""
        strategy = MagicMock()
        strategy.uses_tilt_motor = False
        tilt_calc = MagicMock()
        tilt_calc.current_position.return_value = None
        travel_calc = MagicMock()

        steps = [TiltTo(50), TravelTo(30)]
        result = calculate_pre_step_delay(steps, strategy, tilt_calc, travel_calc)
        assert result == 0.0

    def test_travel_before_tilt_with_none_current_pos(self):
        """Line 62: TravelTo then TiltTo, current_pos is None => 0.0."""
        strategy = MagicMock()
        strategy.uses_tilt_motor = False
        tilt_calc = MagicMock()
        travel_calc = MagicMock()
        travel_calc.current_position.return_value = None

        steps = [TravelTo(30), TiltTo(50)]
        result = calculate_pre_step_delay(steps, strategy, tilt_calc, travel_calc)
        assert result == 0.0

    def test_default_return_for_unexpected_step_order(self):
        """Line 65: Two steps of same type => default 0.0."""
        strategy = MagicMock()
        strategy.uses_tilt_motor = False

        # Two TiltTo steps -- neither branch matches
        steps = [TiltTo(50), TiltTo(30)]
        result = calculate_pre_step_delay(steps, strategy, MagicMock(), MagicMock())
        assert result == 0.0

        # Two TravelTo steps -- neither branch matches
        steps = [TravelTo(50), TravelTo(30)]
        result = calculate_pre_step_delay(steps, strategy, MagicMock(), MagicMock())
        assert result == 0.0

    def test_tilt_before_travel_calculates_delay(self):
        """TiltTo then TravelTo with valid positions returns calculated delay."""
        strategy = MagicMock()
        strategy.uses_tilt_motor = False

        # Use real TravelCalculator for tilt_calc
        tilt_calc = TravelCalculator(2.0, 2.0)
        tilt_calc.set_position(0)
        travel_calc = MagicMock()

        steps = [TiltTo(50), TravelTo(30)]
        result = calculate_pre_step_delay(steps, strategy, tilt_calc, travel_calc)
        # Should be tilt_calc.calculate_travel_time(0, 50) = 2.0 * 50 / 100 = 1.0
        assert result == pytest.approx(1.0)

    def test_travel_before_tilt_calculates_delay(self):
        """TravelTo then TiltTo with valid positions returns calculated delay."""
        strategy = MagicMock()
        strategy.uses_tilt_motor = False

        tilt_calc = MagicMock()
        # Use real TravelCalculator for travel_calc
        travel_calc = TravelCalculator(10.0, 10.0)
        travel_calc.set_position(0)

        steps = [TravelTo(50), TiltTo(30)]
        result = calculate_pre_step_delay(steps, strategy, tilt_calc, travel_calc)
        # Should be travel_calc.calculate_travel_time(0, 50) = 10.0 * 50 / 100 = 5.0
        assert result == pytest.approx(5.0)


# ===================================================================
# cover_base.py line 302: calibration_step in extra_state_attributes
# ===================================================================


class TestCalibrationStepAttribute:
    """Test extra_state_attributes shows calibration_step when step_count > 0."""

    @pytest.mark.asyncio
    async def test_calibration_step_shown_when_step_count_positive(self, make_cover):
        """Line 302: calibration_step appears when step_count > 0."""
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_close", timeout=120.0)

        # Set step_count > 0 to trigger line 302
        cover._calibration.step_count = 3

        attrs = cover.extra_state_attributes
        assert attrs["calibration_active"] is True
        assert attrs["calibration_attribute"] == "travel_time_close"
        assert attrs["calibration_step"] == 3

    @pytest.mark.asyncio
    async def test_calibration_step_not_shown_when_step_count_zero(self, make_cover):
        """calibration_step should NOT appear when step_count == 0."""
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_close", timeout=120.0)

        assert cover._calibration.step_count == 0

        attrs = cover.extra_state_attributes
        assert attrs["calibration_active"] is True
        assert "calibration_step" not in attrs


# ===================================================================
# cover_base.py line 832: _require_travel_time raises for closing
# ===================================================================


class TestRequireTravelTimeRaisesClosing:
    """Test _require_travel_time raises HomeAssistantError when closing time is None."""

    def test_raises_when_travel_time_close_is_none(self, make_cover):
        """Line 832: calling _require_travel_time(closing=True) with _travel_time_close=None."""
        cover = make_cover()
        cover._travel_time_close = None

        with pytest.raises(HomeAssistantError, match="[Tt]ravel time"):
            cover._require_travel_time(closing=True)

    def test_raises_when_travel_time_open_is_none(self, make_cover):
        """Calling _require_travel_time(closing=False) with _travel_time_open=None."""
        cover = make_cover()
        cover._travel_time_open = None

        with pytest.raises(HomeAssistantError, match="[Tt]ravel time"):
            cover._require_travel_time(closing=False)

    def test_returns_value_when_configured(self, make_cover):
        """Returns the travel time when properly configured."""
        cover = make_cover()
        assert cover._require_travel_time(closing=True) == 30
        assert cover._require_travel_time(closing=False) == 30


# ===================================================================
# cover_base.py line 1199: _start_tilt_restore early return
# ===================================================================


class TestStartTiltRestoreEarlyReturn:
    """Test _start_tilt_restore returns early when tilt matches restore target."""

    @pytest.mark.asyncio
    async def test_returns_early_when_tilt_equals_restore_target(self, make_cover):
        """Line 1202: current_tilt == restore_target => early return with stop."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(75)

        # Set the restore target to match current tilt
        cover._tilt_restore_target = 75

        with patch.object(cover, "async_write_ha_state"):
            await cover._start_tilt_restore()

        # Should have sent stop command and cleared last_command
        assert cover._last_command is None
        # Tilt restore should NOT be active (early return path)
        assert cover._tilt_restore_active is False

    @pytest.mark.asyncio
    async def test_returns_early_when_current_tilt_is_none(self, make_cover):
        """Line 1202: current_tilt is None => early return with stop."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        # tilt_calc position is None (never set)

        cover._tilt_restore_target = 50

        with patch.object(cover, "async_write_ha_state"):
            await cover._start_tilt_restore()

        assert cover._last_command is None
        assert cover._tilt_restore_active is False

    @pytest.mark.asyncio
    async def test_returns_early_when_restore_target_is_none(self, make_cover):
        """Line 1198-1199: restore_target is None => immediate return."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        cover._tilt_restore_target = None

        with patch.object(cover, "async_write_ha_state"):
            await cover._start_tilt_restore()

        # Nothing should have happened
        assert cover._tilt_restore_active is False


# ===================================================================
# cover_base.py line 180: cancel calibration automation_task on removal
# ===================================================================


class TestRemovalCancelsCalibrationAutomationTask:
    """Test async_will_remove_from_hass cancels calibration automation_task."""

    @pytest.mark.asyncio
    async def test_cancels_running_automation_task(self, make_cover):
        """Line 180: automation_task.cancel() when task is running."""
        cover = make_cover(travel_time_close=60.0, travel_time_open=60.0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_startup_delay", timeout=300.0
            )

        # Verify automation_task was created (overhead calibration creates one)
        assert cover._calibration is not None
        assert cover._calibration.automation_task is not None
        automation_task = cover._calibration.automation_task
        assert not automation_task.done()

        # Also verify timeout_task exists
        timeout_task = cover._calibration.timeout_task

        await cover.async_will_remove_from_hass()
        await asyncio.sleep(0)  # Let event loop process cancellation

        assert cover._calibration is None
        assert automation_task.cancelled() or automation_task.done()
        assert timeout_task.cancelled() or timeout_task.done()

    @pytest.mark.asyncio
    async def test_handles_already_done_automation_task(self, make_cover):
        """No crash when automation_task is already done at removal time."""
        cover = make_cover(travel_time_close=60.0, travel_time_open=60.0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_startup_delay", timeout=300.0
            )

        # Cancel automation task manually before removal
        cover._calibration.automation_task.cancel()
        await asyncio.sleep(0)

        # Removal should not crash even though automation_task is already done
        await cover.async_will_remove_from_hass()
        assert cover._calibration is None


# ===================================================================
# cover_base.py lines 991-999: external movement auto-stop skips relay
# ===================================================================


class TestExternalMovementAutoStop:
    """Test auto_stop_if_necessary skips relay stop for external movements."""

    @pytest.mark.asyncio
    async def test_external_movement_skips_relay_stop(self, make_cover):
        """Lines 991-999: _self_initiated_movement=False => skip relay stop."""
        cover = make_cover()
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel(0)  # Already at target => position_reached

        cover._self_initiated_movement = False
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            with patch.object(cover, "_send_stop", new_callable=AsyncMock) as mock_stop:
                await cover.auto_stop_if_necessary()

        # Relay stop should NOT have been called
        mock_stop.assert_not_awaited()
        # Last command should have been cleared
        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_external_movement_with_tilt_snaps_trackers(self, make_cover):
        """Lines 994-997: external movement with tilt strategy snaps trackers."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        # Both at target => position_reached
        cover.travel_calc.start_travel(50)
        cover.tilt_calc.start_travel(100)

        cover._self_initiated_movement = False
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            with patch.object(
                cover._tilt_strategy,
                "snap_trackers_to_physical",
            ) as mock_snap:
                await cover.auto_stop_if_necessary()

        # snap_trackers_to_physical should have been called
        mock_snap.assert_called_once_with(cover.travel_calc, cover.tilt_calc)
        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_self_initiated_movement_sends_relay_stop(self, make_cover):
        """Contrast: self-initiated movement DOES send relay stop."""
        cover = make_cover()
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel(50)  # Already at target

        cover._self_initiated_movement = True
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover.auto_stop_if_necessary()

        # Relay stop SHOULD have been called (via _async_handle_command)
        cover.hass.services.async_call.assert_awaited()
        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_external_movement_stops_tilt_calc(self, make_cover):
        """External movement with tilt also stops tilt_calc."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)

        # Both at target => position_reached
        cover.travel_calc.start_travel(0)
        cover.tilt_calc.start_travel(0)

        cover._self_initiated_movement = False
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover.auto_stop_if_necessary()

        # Both calculators should have been stopped
        assert not cover.travel_calc.is_traveling()
        assert not cover.tilt_calc.is_traveling()
        assert cover._last_command is None


# ===================================================================
# cover_base.py line 488: _send_tilt_stop in _async_move_tilt_to_endpoint
# when startup delay active + direction change + dual motor
# ===================================================================


class TestMoveEndpointStartupDelayDualMotorTiltStop:
    """Test _send_tilt_stop during direction change with startup delay (dual motor)."""

    @pytest.mark.asyncio
    async def test_tilt_stop_sent_on_direction_change_with_startup_delay(
        self, make_cover
    ):
        """Line 488: dual motor sends _send_tilt_stop on direction change with startup delay."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        # Create an active startup delay task (not done)
        cover._startup_delay_task = asyncio.get_event_loop().create_future()
        # Last command was OPEN, so closing (target=0) is a direction change
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            with patch.object(
                cover, "_send_tilt_stop", new_callable=AsyncMock
            ) as mock_tilt_stop:
                await cover._async_move_tilt_to_endpoint(target=0)

        mock_tilt_stop.assert_awaited_once()


# ===================================================================
# cover_base.py line 499: _send_tilt_stop in _async_move_tilt_to_endpoint
# when relay_was_on + dual motor
# ===================================================================


class TestMoveEndpointRelayWasOnDualMotorTiltStop:
    """Test _send_tilt_stop when relay_was_on in dual motor tilt endpoint move."""

    @pytest.mark.asyncio
    async def test_tilt_stop_sent_when_relay_was_on(self, make_cover):
        """Line 499: dual motor sends _send_tilt_stop when relay was on."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        # Create an active delay task (not done) so _cancel_delay_task returns True
        cover._delay_task = asyncio.get_event_loop().create_future()

        with patch.object(cover, "async_write_ha_state"):
            with patch.object(
                cover, "_send_tilt_stop", new_callable=AsyncMock
            ) as mock_tilt_stop:
                await cover._async_move_tilt_to_endpoint(target=0)

        mock_tilt_stop.assert_awaited_once()


# ===================================================================
# cover_base.py line 594: early return in set_position when target == current
# after stopping travel on direction change
# ===================================================================


class TestSetPositionEarlyReturnAfterDirectionChange:
    """Test early return in set_position when target == current after stopping."""

    @pytest.mark.asyncio
    async def test_returns_early_when_target_equals_current_after_stop(
        self, make_cover
    ):
        """Line 594: target == current after stopping travel => early return."""
        from custom_components.cover_time_based.travel_calculator import (
            TravelCalculator,
        )

        cover = make_cover()

        # Set up cover traveling towards 100 with last_command=OPEN.
        # Calling set_position(49) triggers command=CLOSE (direction change).
        cover.travel_calc.set_position(51)
        cover.travel_calc.start_travel(100)
        cover._last_command = SERVICE_OPEN_COVER

        # Patch current_position at class level (TravelCalculator uses __slots__).
        # In set_position the call sequence for travel_calc.current_position is:
        #   call 1 (line 557): 51 => target(49) < 51 => CLOSE (direction change)
        #   call 2 (line 585 is_traveling): 51 => 51 != 100 => True
        #   call 3 (line 587 stop): 51
        #   call 4 (line 592): 49 => target(49) == 49 => early return
        call_count = [0]

        def mock_current(self_tc):
            call_count[0] += 1
            if call_count[0] <= 3:
                return 51
            return 49

        with patch.object(cover, "async_write_ha_state"):
            with patch.object(TravelCalculator, "current_position", mock_current):
                await cover.set_position(49)

        # Early return at line 594 means _last_command is NOT updated at line 606
        assert cover._last_command == SERVICE_OPEN_COVER


# ===================================================================
# cover_base.py line 666: _send_tilt_stop in set_tilt_position
# when direction change + dual motor
# ===================================================================


class TestSetTiltPositionDirectionChangeDualMotor:
    """Test _send_tilt_stop on direction change in set_tilt_position with dual motor."""

    @pytest.mark.asyncio
    async def test_tilt_stop_sent_on_direction_change(self, make_cover):
        """Line 666: dual motor sends _send_tilt_stop on direction change in set_tilt_position."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        # Start a tilt movement (opening)
        cover.tilt_calc.start_travel(100)
        # Last command was OPEN
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            with patch.object(
                cover, "_send_tilt_stop", new_callable=AsyncMock
            ) as mock_tilt_stop:
                # Set tilt to a position below current (closing) => direction change
                await cover.set_tilt_position(20)

        mock_tilt_stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_when_target_equals_current_after_direction_change(
        self, make_cover
    ):
        """Line 669: target == current after stopping => early return."""
        from custom_components.cover_time_based.travel_calculator import (
            TravelCalculator,
        )

        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(51)

        # Start tilt traveling towards 100
        cover.tilt_calc.start_travel(100)
        cover._last_command = SERVICE_OPEN_COVER

        # Patch current_position at class level (TravelCalculator uses __slots__).
        # In set_tilt_position the call sequence is:
        #   call 1 (line 631, tilt_calc): 51 => target(49) < 51 => CLOSE
        #   call 2 (line 659 tilt_calc.is_traveling): 51 => 51 != 100 => True
        #   call 3 (line 660 tilt_calc.stop): 51
        #   call 4 (line 661 travel_calc.is_traveling): 50 => 50 == 50 => False
        #   call 5 (line 667, tilt_calc): 49 => target(49) == 49 => return
        call_count = [0]

        def mock_current(self_tc):
            call_count[0] += 1
            if self_tc is cover.tilt_calc:
                if call_count[0] <= 3:
                    return 51
                return 49
            # travel_calc
            return 50

        with patch.object(cover, "async_write_ha_state"):
            with patch.object(TravelCalculator, "current_position", mock_current):
                await cover.set_tilt_position(49)

        # Early return at line 669 means _last_command NOT updated at line 699
        assert cover._last_command == SERVICE_OPEN_COVER


# ===================================================================
# cover_base.py line 675: _send_tilt_stop when relay_was_on
# in set_tilt_position + dual motor
# ===================================================================


class TestSetTiltPositionRelayWasOnDualMotor:
    """Test _send_tilt_stop when relay was on in set_tilt_position with dual motor."""

    @pytest.mark.asyncio
    async def test_tilt_stop_sent_when_relay_was_on(self, make_cover):
        """Line 675: dual motor sends _send_tilt_stop when relay was on."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        # Create an active delay task so _cancel_delay_task returns True
        cover._delay_task = asyncio.get_event_loop().create_future()

        with patch.object(cover, "async_write_ha_state"):
            with patch.object(
                cover, "_send_tilt_stop", new_callable=AsyncMock
            ) as mock_tilt_stop:
                await cover.set_tilt_position(80)

        mock_tilt_stop.assert_awaited_once()


# ===================================================================
# cover_base.py line 734: return when current_pos or current_tilt is None
# in _plan_tilt_for_travel
# ===================================================================


class TestPlanTiltForTravelNonePositions:
    """Test _plan_tilt_for_travel returns early when positions are None."""

    @pytest.mark.asyncio
    async def test_returns_early_when_current_pos_is_none(self, make_cover):
        """Line 734: current_pos is None => early return."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        # Don't set travel_calc position (it will be None)
        cover.tilt_calc.set_position(50)

        result = await cover._plan_tilt_for_travel(
            target=0,
            command=SERVICE_CLOSE_COVER,
            current_pos=None,
            current_tilt=50,
        )

        tilt_target, pre_step_delay, started = result
        assert tilt_target is None
        assert pre_step_delay == 0.0
        assert started is False

    @pytest.mark.asyncio
    async def test_returns_early_when_current_tilt_is_none(self, make_cover):
        """Line 734: current_tilt is None => early return."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        # Don't set tilt_calc position (it will be None)

        result = await cover._plan_tilt_for_travel(
            target=0,
            command=SERVICE_CLOSE_COVER,
            current_pos=50,
            current_tilt=None,
        )

        tilt_target, pre_step_delay, started = result
        assert tilt_target is None
        assert pre_step_delay == 0.0
        assert started is False


# ===================================================================
# cover_base.py line 761: _tilt_restore_target = target for dual motor
# endpoint when pre-step is skipped
# ===================================================================


class TestTiltRestoreTargetDualMotorEndpoint:
    """Test _tilt_restore_target is set for dual motor endpoint moves."""

    @pytest.mark.asyncio
    async def test_tilt_restore_target_set_for_endpoint_move(self, make_cover):
        """Line 761: dual motor moving to endpoint sets _tilt_restore_target = target."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        cover.travel_calc.set_position(50)
        # Set tilt to the tilt_target value that plan_move_position will return
        # so current_tilt == tilt_target (skip pre-step) but current_tilt != target (0)
        # For dual motor going to endpoint 0, tilt should be at safe position already
        # We need: tilt_target == current_tilt (skip pre-step), target in (0,100), current_tilt != target
        cover.tilt_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover._plan_tilt_for_travel(
                target=0,
                command=SERVICE_CLOSE_COVER,
                current_pos=50,
                current_tilt=50,
            )

        # The tilt_restore_target should be set to the endpoint target
        assert cover._tilt_restore_target == 0


class TestNoTiltRestoreOutsideAllowedZone:
    """Tilt should not restore when target position is outside allowed tilt zone."""

    @pytest.mark.asyncio
    async def test_no_restore_when_above_max_tilt_allowed(self, make_cover):
        """Moving to position 50 with max_tilt_allowed=0 should not restore tilt."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
            safe_tilt_position=100,
            max_tilt_allowed_position=0,
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover._plan_tilt_for_travel(
                target=50,
                command=SERVICE_OPEN_COVER,
                current_pos=0,
                current_tilt=50,
            )

        # Restore target should be safe position (100), not current tilt (50)
        assert cover._tilt_restore_target == 100

    @pytest.mark.asyncio
    async def test_restore_when_within_allowed_zone(self, make_cover):
        """Moving to position within allowed zone should restore tilt normally."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
            safe_tilt_position=100,
            max_tilt_allowed_position=50,
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover._plan_tilt_for_travel(
                target=30,
                command=SERVICE_OPEN_COVER,
                current_pos=0,
                current_tilt=50,
            )

        # Restore target should be current tilt (50) since target is within allowed zone
        assert cover._tilt_restore_target == 50


# ===================================================================
# cover_base.py line 843: base _are_entities_configured returns True
# ===================================================================


class TestBaseAreEntitiesConfigured:
    """Test the base _are_entities_configured method returns True."""

    def test_base_returns_true(self, make_cover):
        """Line 843: base class _are_entities_configured returns True."""
        # The switch mode cover overrides this, but we can test the base
        # by calling through _get_missing_configuration which checks it
        cover = make_cover()
        # Access the base class method directly
        from custom_components.cover_time_based.cover_base import CoverTimeBased

        result = CoverTimeBased._are_entities_configured(cover)
        assert result is True


# ===================================================================
# cover_base.py line 1091: travel_calc.stop() during _abandon_active_lifecycle
# when travel calc is traveling + tilt pre-step/restore active
# ===================================================================


class TestAbandonActiveLifecycleTravelStop:
    """Test travel_calc.stop() in _abandon_active_lifecycle."""

    @pytest.mark.asyncio
    async def test_travel_calc_stopped_during_pre_step_abandon(self, make_cover):
        """Line 1091: travel_calc.stop() called when abandoning pre-step with active travel."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        # Simulate active pre-step: travel is traveling + pending_travel_target set
        cover.travel_calc.start_travel(100)
        cover._pending_travel_target = 100
        cover._pending_travel_command = SERVICE_OPEN_COVER

        assert cover.travel_calc.is_traveling()

        with patch.object(cover, "async_write_ha_state"):
            await cover._abandon_active_lifecycle()

        # travel_calc should have been stopped
        assert not cover.travel_calc.is_traveling()
        assert cover._pending_travel_target is None

    @pytest.mark.asyncio
    async def test_travel_calc_stopped_during_restore_abandon(self, make_cover):
        """Line 1091: travel_calc.stop() called when abandoning restore with active travel."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        # Simulate active restore: travel is traveling + tilt_restore_active
        cover.travel_calc.start_travel(0)
        cover._tilt_restore_active = True

        assert cover.travel_calc.is_traveling()

        with patch.object(cover, "async_write_ha_state"):
            await cover._abandon_active_lifecycle()

        assert not cover.travel_calc.is_traveling()
        assert cover._tilt_restore_active is False


# ===================================================================
# cover_base.py line 1150: _send_tilt_close for tilt pre-step (dual motor)
# ===================================================================


class TestTiltPreStepSendClose:
    """Test _send_tilt_close in _start_tilt_pre_step for dual motor."""

    @pytest.mark.asyncio
    async def test_send_tilt_close_for_closing_pre_step(self, make_cover):
        """Line 1150: _send_tilt_close called when closing_tilt=True in pre-step."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(80)  # Current tilt is 80

        with patch.object(cover, "async_write_ha_state"):
            with patch.object(
                cover, "_send_tilt_close", new_callable=AsyncMock
            ) as mock_tilt_close:
                # tilt_target=30 < current_tilt=80 => closing_tilt=True
                await cover._start_tilt_pre_step(
                    tilt_target=30,
                    travel_target=0,
                    travel_command=SERVICE_CLOSE_COVER,
                    restore_target=80,
                )

        mock_tilt_close.assert_awaited_once()
        assert cover._pending_travel_target == 0
        assert cover._tilt_restore_target == 80


# ===================================================================
# cover_base.py line 1226: _send_tilt_open for tilt restore (dual motor)
# ===================================================================


class TestTiltRestoreSendOpen:
    """Test _send_tilt_open in _start_tilt_restore for dual motor."""

    @pytest.mark.asyncio
    async def test_send_tilt_open_for_restore(self, make_cover):
        """Line 1226: _send_tilt_open called when restoring to higher tilt position."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(20)  # Current tilt is 20

        # Set restore target to a higher value (opening)
        cover._tilt_restore_target = 80

        with patch.object(cover, "async_write_ha_state"):
            with patch.object(
                cover, "_send_tilt_open", new_callable=AsyncMock
            ) as mock_tilt_open:
                await cover._start_tilt_restore()

        mock_tilt_open.assert_awaited_once()
        assert cover._tilt_restore_active is True
        assert cover.tilt_calc.is_traveling()


# ===================================================================
# cover_base.py lines 1290, 1308, 1326, 1328: _mark_switch_pending
# conditionals in _send_tilt_open/close/stop
# ===================================================================


class TestTiltSendMarkSwitchPending:
    """Test _mark_switch_pending conditionals when opposite switch is on."""

    @pytest.mark.asyncio
    async def test_send_tilt_open_marks_close_switch_pending(self, make_cover):
        """Line 1290: _send_tilt_open marks close switch pending when it's on."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )

        with patch.object(
            cover,
            "_switch_is_on",
            side_effect=lambda eid: eid == "switch.tilt_close",
        ):
            with patch.object(cover, "_mark_switch_pending") as mock_mark:
                await cover._send_tilt_open()

        # Should mark close switch with 1 (it was on) and open switch with 2
        calls = mock_mark.call_args_list
        assert any(c.args == ("switch.tilt_close", 1) for c in calls), (
            f"Expected close switch marked with 1, got {calls}"
        )
        assert any(c.args == ("switch.tilt_open", 2) for c in calls), (
            f"Expected open switch marked with 2, got {calls}"
        )

    @pytest.mark.asyncio
    async def test_send_tilt_close_marks_open_switch_pending(self, make_cover):
        """Line 1308: _send_tilt_close marks open switch pending when it's on."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )

        with patch.object(
            cover,
            "_switch_is_on",
            side_effect=lambda eid: eid == "switch.tilt_open",
        ):
            with patch.object(cover, "_mark_switch_pending") as mock_mark:
                await cover._send_tilt_close()

        calls = mock_mark.call_args_list
        assert any(c.args == ("switch.tilt_open", 1) for c in calls), (
            f"Expected open switch marked with 1, got {calls}"
        )
        assert any(c.args == ("switch.tilt_close", 2) for c in calls), (
            f"Expected close switch marked with 2, got {calls}"
        )

    @pytest.mark.asyncio
    async def test_send_tilt_stop_marks_open_switch_pending(self, make_cover):
        """Line 1326: _send_tilt_stop marks open switch pending when it's on."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )

        with patch.object(
            cover,
            "_switch_is_on",
            side_effect=lambda eid: eid == "switch.tilt_open",
        ):
            with patch.object(cover, "_mark_switch_pending") as mock_mark:
                await cover._send_tilt_stop()

        calls = mock_mark.call_args_list
        assert any(c.args == ("switch.tilt_open", 1) for c in calls), (
            f"Expected open switch marked with 1, got {calls}"
        )

    @pytest.mark.asyncio
    async def test_send_tilt_stop_marks_close_switch_pending(self, make_cover):
        """Line 1328: _send_tilt_stop marks close switch pending when it's on."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )

        with patch.object(
            cover,
            "_switch_is_on",
            side_effect=lambda eid: eid == "switch.tilt_close",
        ):
            with patch.object(cover, "_mark_switch_pending") as mock_mark:
                await cover._send_tilt_stop()

        calls = mock_mark.call_args_list
        assert any(c.args == ("switch.tilt_close", 1) for c in calls), (
            f"Expected close switch marked with 1, got {calls}"
        )

    @pytest.mark.asyncio
    async def test_send_tilt_stop_marks_both_switches_when_both_on(self, make_cover):
        """Lines 1326+1328: _send_tilt_stop marks both switches when both are on."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )

        with patch.object(
            cover,
            "_switch_is_on",
            return_value=True,
        ):
            with patch.object(cover, "_mark_switch_pending") as mock_mark:
                await cover._send_tilt_stop()

        calls = mock_mark.call_args_list
        assert any(c.args == ("switch.tilt_open", 1) for c in calls), (
            f"Expected open switch marked with 1, got {calls}"
        )
        assert any(c.args == ("switch.tilt_close", 1) for c in calls), (
            f"Expected close switch marked with 1, got {calls}"
        )


# ===================================================================
# cover_base.py lines 1437-1444: external tilt switch state change
# via _async_switch_state_changed
# ===================================================================


class TestExternalTiltSwitchStateChange:
    """Test external tilt/main switch state changes via _async_switch_state_changed.

    External state changes delegate to the mode-specific handlers
    (_handle_external_tilt_state_change / _handle_external_state_change)
    with _triggered_externally=True. Position is tracked, not cleared.
    """

    @pytest.mark.asyncio
    async def test_tilt_switch_delegates_to_tilt_handler(self, make_cover):
        """Tilt switch state change delegates to _handle_external_tilt_state_change."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )

        event = MagicMock()
        event.data = {
            "entity_id": "switch.tilt_open",
            "old_state": MagicMock(state="off"),
            "new_state": MagicMock(state="on"),
        }

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_handle_external_tilt_state_change", new_callable=AsyncMock
            ) as handler,
        ):
            await cover._async_switch_state_changed(event)

        handler.assert_awaited_once_with("switch.tilt_open", "off", "on")

    @pytest.mark.asyncio
    async def test_main_switch_delegates_to_main_handler(self, make_cover):
        """Main switch state change delegates to _handle_external_state_change."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )

        event = MagicMock()
        event.data = {
            "entity_id": "switch.open",
            "old_state": MagicMock(state="off"),
            "new_state": MagicMock(state="on"),
        }

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_handle_external_state_change", new_callable=AsyncMock
            ) as handler,
        ):
            await cover._async_switch_state_changed(event)

        handler.assert_awaited_once_with("switch.open", "off", "on")

    @pytest.mark.asyncio
    async def test_triggered_externally_set_during_handler(self, make_cover):
        """_triggered_externally is True during handler execution."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        captured_flag = None

        async def capture_flag(*_args):
            nonlocal captured_flag
            captured_flag = cover._triggered_externally

        event = MagicMock()
        event.data = {
            "entity_id": "switch.tilt_open",
            "old_state": MagicMock(state="off"),
            "new_state": MagicMock(state="on"),
        }

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_handle_external_tilt_state_change", side_effect=capture_flag
            ),
        ):
            await cover._async_switch_state_changed(event)

        assert captured_flag is True
        assert cover._triggered_externally is False
