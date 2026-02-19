"""Tests for TiltStrategy classes (SequentialTilt and ProportionalTilt)."""

from xknx.devices import TravelCalculator

from custom_components.cover_time_based.tilt_strategy import (
    ProportionalTilt,
    SequentialTilt,
    _calc_coupled_target,
)


# ===================================================================
# _calc_coupled_target helper
# ===================================================================


class TestCalcCoupledTarget:
    """Test the module-level _calc_coupled_target helper."""

    def test_closing_from_zero(self):
        """Closing from position 0 should move forward proportionally."""
        calc = TravelCalculator(10.0, 10.0)
        calc.set_position(0)
        # 5s movement with 10s total = 50% distance
        result = _calc_coupled_target(
            5.0,
            closing=True,
            coupled_calc=calc,
            coupled_time_close=10.0,
            coupled_time_open=10.0,
        )
        assert result == 50

    def test_closing_from_midpoint(self):
        """Closing from 50 with 25% distance should reach 75."""
        calc = TravelCalculator(10.0, 10.0)
        calc.set_position(50)
        # 2.5s movement with 10s total = 25% distance
        result = _calc_coupled_target(
            2.5,
            closing=True,
            coupled_calc=calc,
            coupled_time_close=10.0,
            coupled_time_open=10.0,
        )
        assert result == 75

    def test_closing_clamped_at_100(self):
        """Closing should not exceed 100."""
        calc = TravelCalculator(10.0, 10.0)
        calc.set_position(80)
        # 5s movement with 10s total = 50% distance, 80+50=130 -> clamped to 100
        result = _calc_coupled_target(
            5.0,
            closing=True,
            coupled_calc=calc,
            coupled_time_close=10.0,
            coupled_time_open=10.0,
        )
        assert result == 100

    def test_opening_from_100(self):
        """Opening from position 100 should move backward proportionally."""
        calc = TravelCalculator(10.0, 10.0)
        calc.set_position(100)
        # 5s movement with 10s total = 50% distance
        result = _calc_coupled_target(
            5.0,
            closing=False,
            coupled_calc=calc,
            coupled_time_close=10.0,
            coupled_time_open=10.0,
        )
        assert result == 50

    def test_opening_from_midpoint(self):
        """Opening from 50 with 25% distance should reach 25."""
        calc = TravelCalculator(10.0, 10.0)
        calc.set_position(50)
        # 2.5s movement with 10s total = 25% distance
        result = _calc_coupled_target(
            2.5,
            closing=False,
            coupled_calc=calc,
            coupled_time_close=10.0,
            coupled_time_open=10.0,
        )
        assert result == 25

    def test_opening_clamped_at_0(self):
        """Opening should not go below 0."""
        calc = TravelCalculator(10.0, 10.0)
        calc.set_position(20)
        # 5s movement with 10s total = 50% distance, 20-50=-30 -> clamped to 0
        result = _calc_coupled_target(
            5.0,
            closing=False,
            coupled_calc=calc,
            coupled_time_close=10.0,
            coupled_time_open=10.0,
        )
        assert result == 0

    def test_asymmetric_times_closing(self):
        """Closing should use coupled_time_close."""
        calc = TravelCalculator(10.0, 20.0)
        calc.set_position(0)
        # 5s movement with 10s close time = 50% distance
        result = _calc_coupled_target(
            5.0,
            closing=True,
            coupled_calc=calc,
            coupled_time_close=10.0,
            coupled_time_open=20.0,
        )
        assert result == 50

    def test_asymmetric_times_opening(self):
        """Opening should use coupled_time_open."""
        calc = TravelCalculator(10.0, 20.0)
        calc.set_position(100)
        # 5s movement with 20s open time = 25% distance
        result = _calc_coupled_target(
            5.0,
            closing=False,
            coupled_calc=calc,
            coupled_time_close=10.0,
            coupled_time_open=20.0,
        )
        assert result == 75


# ===================================================================
# SequentialTilt
# ===================================================================


class TestSequentialTiltCalcTiltForTravel:
    """SequentialTilt.calc_tilt_for_travel returns proportional value."""

    def test_closing_returns_proportional_tilt(self):
        """When travel moves while closing, tilt should couple proportionally."""
        strategy = SequentialTilt()
        tilt_calc = TravelCalculator(10.0, 10.0)
        tilt_calc.set_position(0)
        # 5s movement with 10s tilt close time = 50% distance
        result = strategy.calc_tilt_for_travel(
            movement_time=5.0,
            closing=True,
            tilt_calc=tilt_calc,
            tilt_time_close=10.0,
            tilt_time_open=10.0,
        )
        assert result == 50

    def test_opening_returns_proportional_tilt(self):
        """When travel moves while opening, tilt should couple proportionally."""
        strategy = SequentialTilt()
        tilt_calc = TravelCalculator(10.0, 10.0)
        tilt_calc.set_position(100)
        result = strategy.calc_tilt_for_travel(
            movement_time=5.0,
            closing=False,
            tilt_calc=tilt_calc,
            tilt_time_close=10.0,
            tilt_time_open=10.0,
        )
        assert result == 50


class TestSequentialTiltCalcTravelForTilt:
    """SequentialTilt.calc_travel_for_tilt returns None (no coupling)."""

    def test_returns_none(self):
        """Tilt movement should not couple travel in sequential mode."""
        strategy = SequentialTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        travel_calc.set_position(50)
        result = strategy.calc_travel_for_tilt(
            movement_time=2.0,
            closing=True,
            travel_calc=travel_calc,
            travel_time_close=30.0,
            travel_time_open=30.0,
        )
        assert result is None


class TestSequentialTiltEnforceConstraints:
    """SequentialTilt.enforce_constraints is a no-op."""

    def test_no_op_at_boundary(self):
        """Tilt should remain unchanged at travel boundaries."""
        strategy = SequentialTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        tilt_calc = TravelCalculator(5.0, 5.0)
        travel_calc.set_position(0)
        tilt_calc.set_position(50)

        strategy.enforce_constraints(travel_calc, tilt_calc)

        assert tilt_calc.current_position() == 50  # unchanged

    def test_no_op_at_closed_boundary(self):
        """Tilt should remain unchanged when travel is fully closed."""
        strategy = SequentialTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        tilt_calc = TravelCalculator(5.0, 5.0)
        travel_calc.set_position(100)
        tilt_calc.set_position(50)

        strategy.enforce_constraints(travel_calc, tilt_calc)

        assert tilt_calc.current_position() == 50  # unchanged


class TestSequentialTiltCanCalibrate:
    """SequentialTilt.can_calibrate_tilt returns True."""

    def test_can_calibrate(self):
        strategy = SequentialTilt()
        assert strategy.can_calibrate_tilt() is True


# ===================================================================
# ProportionalTilt
# ===================================================================


class TestProportionalTiltCalcTiltForTravel:
    """ProportionalTilt.calc_tilt_for_travel returns proportional value."""

    def test_closing_returns_proportional_tilt(self):
        """When travel moves while closing, tilt should couple proportionally."""
        strategy = ProportionalTilt()
        tilt_calc = TravelCalculator(10.0, 10.0)
        tilt_calc.set_position(0)
        result = strategy.calc_tilt_for_travel(
            movement_time=5.0,
            closing=True,
            tilt_calc=tilt_calc,
            tilt_time_close=10.0,
            tilt_time_open=10.0,
        )
        assert result == 50

    def test_opening_returns_proportional_tilt(self):
        """When travel moves while opening, tilt should couple proportionally."""
        strategy = ProportionalTilt()
        tilt_calc = TravelCalculator(10.0, 10.0)
        tilt_calc.set_position(100)
        result = strategy.calc_tilt_for_travel(
            movement_time=5.0,
            closing=False,
            tilt_calc=tilt_calc,
            tilt_time_close=10.0,
            tilt_time_open=10.0,
        )
        assert result == 50


class TestProportionalTiltCalcTravelForTilt:
    """ProportionalTilt.calc_travel_for_tilt returns proportional value."""

    def test_closing_returns_proportional_travel(self):
        """When tilt moves while closing, travel should couple proportionally."""
        strategy = ProportionalTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        travel_calc.set_position(50)
        # 2.5s movement with 30s travel close time = 8.33% distance
        result = strategy.calc_travel_for_tilt(
            movement_time=2.5,
            closing=True,
            travel_calc=travel_calc,
            travel_time_close=30.0,
            travel_time_open=30.0,
        )
        # 50 + (2.5/30)*100 = 50 + 8.33 = 58 (int truncated)
        assert result == 58

    def test_opening_returns_proportional_travel(self):
        """When tilt moves while opening, travel should couple proportionally."""
        strategy = ProportionalTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        travel_calc.set_position(50)
        result = strategy.calc_travel_for_tilt(
            movement_time=2.5,
            closing=False,
            travel_calc=travel_calc,
            travel_time_close=30.0,
            travel_time_open=30.0,
        )
        # 50 - (2.5/30)*100 = 50 - 8.33 = 41 (int truncated)
        assert result == 41


class TestProportionalTiltEnforceConstraints:
    """ProportionalTilt.enforce_constraints forces tilt at travel boundaries."""

    def test_forces_tilt_to_0_when_travel_at_0(self):
        """When travel is fully open (0), tilt must be forced to 0."""
        strategy = ProportionalTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        tilt_calc = TravelCalculator(5.0, 5.0)
        travel_calc.set_position(0)
        tilt_calc.set_position(50)

        strategy.enforce_constraints(travel_calc, tilt_calc)

        assert tilt_calc.current_position() == 0

    def test_forces_tilt_to_100_when_travel_at_100(self):
        """When travel is fully closed (100), tilt must be forced to 100."""
        strategy = ProportionalTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        tilt_calc = TravelCalculator(5.0, 5.0)
        travel_calc.set_position(100)
        tilt_calc.set_position(50)

        strategy.enforce_constraints(travel_calc, tilt_calc)

        assert tilt_calc.current_position() == 100

    def test_no_op_at_midpoint(self):
        """When travel is at midpoint, tilt should remain unchanged."""
        strategy = ProportionalTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        tilt_calc = TravelCalculator(5.0, 5.0)
        travel_calc.set_position(50)
        tilt_calc.set_position(30)

        strategy.enforce_constraints(travel_calc, tilt_calc)

        assert tilt_calc.current_position() == 30  # unchanged

    def test_no_op_when_tilt_already_matches_at_0(self):
        """When travel and tilt are both at 0, no change needed."""
        strategy = ProportionalTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        tilt_calc = TravelCalculator(5.0, 5.0)
        travel_calc.set_position(0)
        tilt_calc.set_position(0)

        strategy.enforce_constraints(travel_calc, tilt_calc)

        assert tilt_calc.current_position() == 0

    def test_no_op_when_tilt_already_matches_at_100(self):
        """When travel and tilt are both at 100, no change needed."""
        strategy = ProportionalTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        tilt_calc = TravelCalculator(5.0, 5.0)
        travel_calc.set_position(100)
        tilt_calc.set_position(100)

        strategy.enforce_constraints(travel_calc, tilt_calc)

        assert tilt_calc.current_position() == 100


class TestProportionalTiltCanCalibrate:
    """ProportionalTilt.can_calibrate_tilt returns False."""

    def test_cannot_calibrate(self):
        strategy = ProportionalTilt()
        assert strategy.can_calibrate_tilt() is False
