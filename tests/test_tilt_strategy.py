"""Tests for TiltStrategy classes (SequentialTilt and ProportionalTilt)."""

from xknx.devices import TravelCalculator

from custom_components.cover_time_based.tilt_strategies import (
    ProportionalTilt,
    SequentialTilt,
    TiltTo,
    TravelTo,
    calc_coupled_target,
)


# ===================================================================
# MovementStep dataclasses
# ===================================================================


class TestMovementSteps:
    """Test MovementStep dataclasses."""

    def test_tilt_to_defaults(self):
        step = TiltTo(50)
        assert step.target == 50
        assert step.coupled_travel is None

    def test_tilt_to_with_coupling(self):
        step = TiltTo(50, coupled_travel=30)
        assert step.target == 50
        assert step.coupled_travel == 30

    def test_travel_to_defaults(self):
        step = TravelTo(30)
        assert step.target == 30
        assert step.coupled_tilt is None

    def test_travel_to_with_coupling(self):
        step = TravelTo(30, coupled_tilt=30)
        assert step.target == 30
        assert step.coupled_tilt == 30

    def test_equality(self):
        assert TiltTo(50) == TiltTo(50)
        assert TravelTo(30) == TravelTo(30)
        assert TiltTo(50) != TravelTo(50)


# ===================================================================
# calc_coupled_target helper
# ===================================================================


class TestCalcCoupledTarget:
    """Test the module-level calc_coupled_target helper."""

    def test_closing_from_zero(self):
        """Closing from position 0 should move forward proportionally."""
        calc = TravelCalculator(10.0, 10.0)
        calc.set_position(0)
        # 5s movement with 10s total = 50% distance
        result = calc_coupled_target(
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
        result = calc_coupled_target(
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
        result = calc_coupled_target(
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
        result = calc_coupled_target(
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
        result = calc_coupled_target(
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
        result = calc_coupled_target(
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
        result = calc_coupled_target(
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
        result = calc_coupled_target(
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


# --- Proportional new interface tests ---


class TestProportionalTiltProperties:
    def test_name(self):
        assert ProportionalTilt().name == "proportional"

    def test_uses_tilt_motor(self):
        assert ProportionalTilt().uses_tilt_motor is False


class TestProportionalPlanMovePosition:
    def test_returns_travel_with_coupled_tilt(self):
        strategy = ProportionalTilt()
        steps = strategy.plan_move_position(target_pos=30, current_pos=100, current_tilt=100)
        assert steps == [TravelTo(30, coupled_tilt=30)]

    def test_fully_open(self):
        strategy = ProportionalTilt()
        steps = strategy.plan_move_position(target_pos=0, current_pos=100, current_tilt=100)
        assert steps == [TravelTo(0, coupled_tilt=0)]

    def test_fully_closed(self):
        strategy = ProportionalTilt()
        steps = strategy.plan_move_position(target_pos=100, current_pos=0, current_tilt=0)
        assert steps == [TravelTo(100, coupled_tilt=100)]


class TestProportionalPlanMoveTilt:
    def test_returns_tilt_with_coupled_travel(self):
        strategy = ProportionalTilt()
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=80, current_tilt=100)
        assert steps == [TiltTo(50, coupled_travel=50)]

    def test_fully_open(self):
        strategy = ProportionalTilt()
        steps = strategy.plan_move_tilt(target_tilt=0, current_pos=50, current_tilt=50)
        assert steps == [TiltTo(0, coupled_travel=0)]


class TestProportionalSnapTrackers:
    def test_forces_tilt_to_zero_at_travel_zero(self):
        strategy = ProportionalTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(0)
        tilt.set_position(5)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0

    def test_forces_tilt_to_100_at_travel_100(self):
        strategy = ProportionalTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(100)
        tilt.set_position(95)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 100

    def test_no_op_at_midpoint(self):
        strategy = ProportionalTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(50)
        tilt.set_position(30)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 30
