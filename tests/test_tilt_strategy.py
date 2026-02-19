"""Tests for TiltStrategy classes (SequentialTilt and ProportionalTilt)."""

from xknx.devices import TravelCalculator

from custom_components.cover_time_based.tilt_strategies import (
    DualMotorTilt,
    ProportionalTilt,
    SequentialTilt,
    TiltTo,
    TravelTo,
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
# SequentialTilt
# ===================================================================


class TestSequentialTiltCanCalibrate:
    """SequentialTilt.can_calibrate_tilt returns True."""

    def test_can_calibrate(self):
        strategy = SequentialTilt()
        assert strategy.can_calibrate_tilt() is True


# ===================================================================
# ProportionalTilt
# ===================================================================


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
        steps = strategy.plan_move_position(
            target_pos=30, current_pos=100, current_tilt=100
        )
        assert steps == [TravelTo(30, coupled_tilt=30)]

    def test_fully_open(self):
        strategy = ProportionalTilt()
        steps = strategy.plan_move_position(
            target_pos=0, current_pos=100, current_tilt=100
        )
        assert steps == [TravelTo(0, coupled_tilt=0)]

    def test_fully_closed(self):
        strategy = ProportionalTilt()
        steps = strategy.plan_move_position(
            target_pos=100, current_pos=0, current_tilt=0
        )
        assert steps == [TravelTo(100, coupled_tilt=100)]


class TestProportionalPlanMoveTilt:
    def test_returns_tilt_with_coupled_travel(self):
        strategy = ProportionalTilt()
        steps = strategy.plan_move_tilt(
            target_tilt=50, current_pos=80, current_tilt=100
        )
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


# --- Sequential new interface tests ---


class TestSequentialTiltProperties:
    def test_name(self):
        assert SequentialTilt().name == "sequential"

    def test_uses_tilt_motor(self):
        assert SequentialTilt().uses_tilt_motor is False


class TestSequentialPlanMovePosition:
    def test_flattens_tilt_before_travel(self):
        strategy = SequentialTilt()
        steps = strategy.plan_move_position(
            target_pos=30, current_pos=100, current_tilt=80
        )
        assert steps == [TiltTo(0), TravelTo(30)]

    def test_skips_tilt_when_already_flat(self):
        strategy = SequentialTilt()
        steps = strategy.plan_move_position(
            target_pos=30, current_pos=100, current_tilt=0
        )
        assert steps == [TravelTo(30)]

    def test_opening_fully(self):
        strategy = SequentialTilt()
        steps = strategy.plan_move_position(
            target_pos=0, current_pos=100, current_tilt=100
        )
        assert steps == [TiltTo(0), TravelTo(0)]

    def test_closing_fully_from_open(self):
        strategy = SequentialTilt()
        steps = strategy.plan_move_position(
            target_pos=100, current_pos=0, current_tilt=0
        )
        assert steps == [TravelTo(100)]

    def test_partial_move_with_flat_tilt(self):
        strategy = SequentialTilt()
        steps = strategy.plan_move_position(
            target_pos=50, current_pos=80, current_tilt=0
        )
        assert steps == [TravelTo(50)]


class TestSequentialPlanMoveTilt:
    def test_travels_to_closed_before_tilting(self):
        strategy = SequentialTilt()
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=30, current_tilt=0)
        assert steps == [TravelTo(100), TiltTo(50)]

    def test_tilts_directly_when_at_closed(self):
        strategy = SequentialTilt()
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=100, current_tilt=0)
        assert steps == [TiltTo(50)]

    def test_tilt_fully_closed(self):
        strategy = SequentialTilt()
        steps = strategy.plan_move_tilt(
            target_tilt=100, current_pos=100, current_tilt=0
        )
        assert steps == [TiltTo(100)]

    def test_tilt_open_from_partially_tilted(self):
        strategy = SequentialTilt()
        steps = strategy.plan_move_tilt(target_tilt=0, current_pos=100, current_tilt=50)
        assert steps == [TiltTo(0)]


class TestSequentialSnapTrackers:
    def test_forces_tilt_to_zero_when_not_at_closed(self):
        strategy = SequentialTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(50)
        tilt.set_position(30)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0

    def test_no_op_when_at_closed(self):
        strategy = SequentialTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(100)
        tilt.set_position(50)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 50

    def test_no_op_when_already_flat(self):
        strategy = SequentialTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(30)
        tilt.set_position(0)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0

    def test_forces_at_fully_open(self):
        strategy = SequentialTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(0)
        tilt.set_position(10)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0


# ===================================================================
# DualMotorTilt
# ===================================================================


class TestDualMotorTiltProperties:
    def test_name(self):
        assert DualMotorTilt().name == "dual_motor"

    def test_uses_tilt_motor(self):
        assert DualMotorTilt().uses_tilt_motor is True

    def test_can_calibrate_tilt(self):
        assert DualMotorTilt().can_calibrate_tilt() is True


class TestDualMotorPlanMovePosition:
    def test_moves_tilt_to_safe_before_travel(self):
        strategy = DualMotorTilt(safe_tilt_position=0)
        steps = strategy.plan_move_position(
            target_pos=30, current_pos=100, current_tilt=50
        )
        assert steps == [TiltTo(0), TravelTo(30)]

    def test_skips_tilt_when_already_safe(self):
        strategy = DualMotorTilt(safe_tilt_position=0)
        steps = strategy.plan_move_position(
            target_pos=30, current_pos=100, current_tilt=0
        )
        assert steps == [TravelTo(30)]

    def test_custom_safe_position(self):
        strategy = DualMotorTilt(safe_tilt_position=50)
        steps = strategy.plan_move_position(
            target_pos=30, current_pos=100, current_tilt=80
        )
        assert steps == [TiltTo(50), TravelTo(30)]

    def test_already_at_custom_safe(self):
        strategy = DualMotorTilt(safe_tilt_position=50)
        steps = strategy.plan_move_position(
            target_pos=30, current_pos=100, current_tilt=50
        )
        assert steps == [TravelTo(30)]


class TestDualMotorPlanMoveTilt:
    def test_tilts_directly_when_no_boundary(self):
        strategy = DualMotorTilt()
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=30, current_tilt=0)
        assert steps == [TiltTo(50)]

    def test_travels_to_boundary_when_below_min(self):
        strategy = DualMotorTilt(min_tilt_allowed_position=80)
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=30, current_tilt=0)
        assert steps == [TravelTo(80), TiltTo(50)]

    def test_tilts_directly_when_at_boundary(self):
        strategy = DualMotorTilt(min_tilt_allowed_position=80)
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=80, current_tilt=0)
        assert steps == [TiltTo(50)]

    def test_tilts_directly_when_beyond_boundary(self):
        strategy = DualMotorTilt(min_tilt_allowed_position=80)
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=100, current_tilt=0)
        assert steps == [TiltTo(50)]

    def test_no_boundary_set(self):
        strategy = DualMotorTilt(min_tilt_allowed_position=None)
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=10, current_tilt=0)
        assert steps == [TiltTo(50)]


class TestDualMotorSnapTrackers:
    def test_forces_tilt_to_safe_when_below_min(self):
        strategy = DualMotorTilt(safe_tilt_position=0, min_tilt_allowed_position=80)
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(50)
        tilt.set_position(30)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0

    def test_no_op_when_at_boundary(self):
        strategy = DualMotorTilt(safe_tilt_position=0, min_tilt_allowed_position=80)
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(80)
        tilt.set_position(30)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 30

    def test_no_op_when_no_boundary(self):
        strategy = DualMotorTilt(safe_tilt_position=0, min_tilt_allowed_position=None)
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(30)
        tilt.set_position(50)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 50

    def test_already_at_safe_position(self):
        strategy = DualMotorTilt(safe_tilt_position=0, min_tilt_allowed_position=80)
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(50)
        tilt.set_position(0)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0
