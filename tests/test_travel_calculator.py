"""Tests for TravelCalculator edge cases."""

from unittest.mock import patch

import pytest

from custom_components.cover_time_based.travel_calculator import (
    TravelCalculator,
    TravelStatus,
)


@pytest.fixture
def mock_time():
    """Patch the calculator's clock, anchored at 1000.0, so a test drives
    travel progress by setting ``mock_time.monotonic.return_value``."""
    with patch(
        "custom_components.cover_time_based.travel_calculator.time"
    ) as mocked_time:
        mocked_time.monotonic.return_value = 1000.0
        yield mocked_time


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

    def test_position_returns_target_when_time_exceeded(self, mock_time):
        """current_position() returns target when travel time has elapsed."""
        calc = TravelCalculator(travel_time_down=10, travel_time_up=10)
        calc.set_position(0)

        calc.start_travel(100)
        # Advance time past the travel duration (10s for full range).
        mock_time.monotonic.return_value = 1020.0
        pos = calc.current_position()
        assert pos == 100

    def test_start_travel_base_monotonic_in_past_advances_position(self, mock_time):
        """start_travel(base_monotonic=...) anchors the move's start at that
        monotonic reading instead of 'now'. A base already in the past means travel
        that began then is already partly complete — this is how relay-feedback
        timing starts tracking from the switch echo's last_changed."""
        calc = TravelCalculator(travel_time_down=30, travel_time_up=30)
        calc.set_position(0)
        # Motor actually got power 15s ago — half of the 30s open travel.
        calc.start_travel(100, base_monotonic=985.0)
        assert calc.current_position() == 50

    def test_start_travel_base_monotonic_in_future_holds_position(self, mock_time):
        """A base_monotonic reading in the future holds the start position until real
        time reaches it (the fixed startup delay is folded in this way)."""
        calc = TravelCalculator(travel_time_down=30, travel_time_up=30)
        calc.set_position(0)
        # Base 5s in the future: no progress yet.
        calc.start_travel(100, base_monotonic=1005.0)
        assert calc.current_position() == 0


class TestArrivalIsDecidedByTime:
    """The target is reached only once the travel time has elapsed, in both
    directions."""

    # 60 s each way, so one position step is 0.6 s.
    @pytest.mark.parametrize(
        ("start", "target", "elapsed", "expected_midway"),
        [
            (50, 30, 12.0 * 0.951, 31),
            (30, 50, 12.0 * 0.999, 49),
            (51, 50, 0.3, 51),  # one-step close, half a step in
            (50, 51, 0.3, 50),  # one-step open, half a step in
            (52, 50, 0.6, 51),  # 50% of the 1.2 s move
            (52, 50, 0.9, 51),  # 75% in, past the step boundary
            (10, 0, 6.0 * 0.999, 1),  # close to the endpoint
        ],
        ids=[
            "close-mid",
            "open-mid",
            "one-step-close",
            "one-step-open",
            "two-step-half",
            "two-step-past-half",
            "to-endpoint",
        ],
    )
    def test_position_holds_short_of_target_until_time_elapses(
        self, mock_time, start, target, elapsed, expected_midway
    ):
        """Mid-move the position sits short of the target, reaching it only
        once the full travel time has elapsed."""
        calc = TravelCalculator(travel_time_down=60, travel_time_up=60)
        calc.set_position(start)
        calc.start_travel(target)

        mock_time.monotonic.return_value = 1000.0 + elapsed
        assert calc.current_position() == expected_midway
        assert not calc.position_reached()
        assert calc.is_traveling()
        if target == 0:
            assert not calc.is_closed()

        full_travel_time = abs(target - start) * 0.6
        mock_time.monotonic.return_value = 1000.0 + full_travel_time + 0.001
        assert calc.current_position() == target
        assert calc.position_reached()
        if target == 0:
            assert calc.is_closed()

    @pytest.mark.parametrize(
        ("start", "target"), [(50, 30), (30, 50)], ids=["close", "open"]
    )
    def test_arrival_at_the_exact_boundary(self, mock_time, start, target):
        """Elapsed includes equality: at exactly the travel time the target is
        reached, not held one step short."""
        calc = TravelCalculator(travel_time_down=60, travel_time_up=60)
        calc.set_position(start)
        calc.start_travel(target)

        mock_time.monotonic.return_value = 1000.0 + 12.0
        assert calc.current_position() == target
        assert calc.position_reached()

    def test_intermediate_position_is_rounded_symmetrically(self, mock_time):
        """The same fraction of a move reads the same distance travelled in
        either direction."""
        calc = TravelCalculator(travel_time_down=60, travel_time_up=60)
        calc.set_position(0)
        calc.start_travel(100)
        mock_time.monotonic.return_value = 1000.0 + 60 * 0.337  # 33.7 -> 34
        assert calc.current_position() == 34

        mock_time.monotonic.return_value = 1000.0
        calc = TravelCalculator(travel_time_down=60, travel_time_up=60)
        calc.set_position(100)
        calc.start_travel(0)
        mock_time.monotonic.return_value = 1000.0 + 60 * 0.337  # 66.3 -> 66
        assert calc.current_position() == 66
