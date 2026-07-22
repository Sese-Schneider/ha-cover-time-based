"""Tests for TravelCalculator edge cases."""

from unittest.mock import patch

from custom_components.cover_time_based.travel_calculator import (
    TravelCalculator,
    TravelStatus,
)


class TestTravelCalculatorEdgeCases:
    """Test edge cases not covered by integration tests."""

    def test_stop_when_position_none(self):
        """stop() on a fresh calculator with no known position does nothing."""
        calc = TravelCalculator(travel_time_down=30, travel_time_up=30)
        assert calc.current_position() is None
        calc.stop()
        assert calc.current_position() is None
        assert calc.travel_direction == TravelStatus.STOPPED

    def test_start_travel_when_position_none(self):
        """start_travel() with unknown position snaps to target immediately."""
        calc = TravelCalculator(travel_time_down=30, travel_time_up=30)
        assert calc._last_known_position is None
        calc.start_travel(50)
        assert calc.current_position() == 50
        assert calc.travel_direction == TravelStatus.STOPPED

    def test_snapshot_restore_round_trips_full_state(self):
        """restore() puts back every field snapshot() captured, so a mutation
        made after the snapshot is fully undone (used for exception-safe
        rollback in _force_full_redrive)."""
        calc = TravelCalculator(travel_time_down=30, travel_time_up=30)
        calc.set_position(30)
        calc.start_travel(80)  # sets target, timestamp and DIRECTION_UP
        snap = calc.snapshot()
        before = (
            calc._last_known_position,
            calc._last_known_position_timestamp,
            calc._position_confirmed,
            calc._travel_to_position,
            calc.travel_direction,
        )

        # Mutate the captured fields (stop() flips direction to STOPPED and
        # retargets, so restoring must bring DIRECTION_UP and the target back).
        calc.stop()
        assert calc.travel_direction == TravelStatus.STOPPED
        assert calc._travel_to_position != before[3]

        calc.restore(snap)
        after = (
            calc._last_known_position,
            calc._last_known_position_timestamp,
            calc._position_confirmed,
            calc._travel_to_position,
            calc.travel_direction,
        )
        assert after == before

    def test_is_opening(self):
        """is_opening() returns True when traveling upward."""
        calc = TravelCalculator(travel_time_down=30, travel_time_up=30)
        calc.set_position(0)
        calc.start_travel(100)
        assert calc.is_opening() is True
        assert calc.is_closing() is False

    def test_is_closing(self):
        """is_closing() returns True when traveling downward."""
        calc = TravelCalculator(travel_time_down=30, travel_time_up=30)
        calc.set_position(100)
        calc.start_travel(0)
        assert calc.is_closing() is True
        assert calc.is_opening() is False

    def test_is_not_opening_when_stopped(self):
        """is_opening() returns False when not traveling."""
        calc = TravelCalculator(travel_time_down=30, travel_time_up=30)
        calc.set_position(50)
        assert calc.is_opening() is False

    def test_is_open(self):
        """is_open() returns True when at fully open position."""
        calc = TravelCalculator(travel_time_down=30, travel_time_up=30)
        calc.set_position(100)
        assert calc.is_open() is True

    def test_is_not_open(self):
        """is_open() returns False when not at fully open position."""
        calc = TravelCalculator(travel_time_down=30, travel_time_up=30)
        calc.set_position(0)
        assert calc.is_open() is False

    def test_position_returns_target_when_time_exceeded(self):
        """current_position() returns target when travel time has elapsed."""
        calc = TravelCalculator(travel_time_down=10, travel_time_up=10)
        calc.set_position(0)

        # Start travel, then advance time past the full travel duration
        with patch(
            "custom_components.cover_time_based.travel_calculator.time"
        ) as mock_time:
            mock_time.time.return_value = 1000.0
            calc.start_travel(100)
            # Now advance time past the travel duration (10s for full range)
            mock_time.time.return_value = 1020.0
            pos = calc.current_position()
            assert pos == 100
