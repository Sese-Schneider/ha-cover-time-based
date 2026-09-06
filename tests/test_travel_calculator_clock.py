"""The travel calculator must survive a wall-clock step mid-travel.

A Raspberry Pi that gets its NTP sync (or a DST/manual correction) while a
cover is moving steps ``time.time()`` by an arbitrary amount. Travel arithmetic
anchored on the wall clock then either declares the move finished instantly (a
forward step -> the relay is stopped early and the position is wrong) or never
lets it finish (a backward step -> the relay runs to the mechanical limit).

The tracker must therefore measure elapsed travel on a clock that cannot step:
``time.monotonic()``. These tests drive both clocks through the module's ``time``
attribute so they hold whichever of the two the calculator ends up reading.
"""

from unittest.mock import patch

import pytest

from custom_components.cover_time_based import travel_calculator
from custom_components.cover_time_based.travel_calculator import TravelCalculator
from tests.helpers import FakeClock


@pytest.fixture
def clock():
    """Install the fake clock as the calculator's ``time`` module."""
    fake = FakeClock()
    with patch.object(travel_calculator, "time", fake):
        yield fake


def _calc_at_zero() -> TravelCalculator:
    """A 10 s cover sitting closed."""
    calc = TravelCalculator(travel_time_down=10, travel_time_up=10)
    calc.set_position(0)
    return calc


class TestWallClockStepDuringTravel:
    """An NTP step mid-travel must not move the tracked position."""

    def test_forward_step_does_not_finish_the_move_early(self, clock):
        """+1 h on the wall clock 2 s into a 10 s open: still ~20%, still moving."""
        calc = _calc_at_zero()
        calc.start_travel(100)

        clock.advance(2.0)
        assert calc.current_position() == 20

        clock.step_wall(3600.0)

        assert calc.current_position() == 20
        assert calc.position_reached() is False
        assert calc.is_traveling() is True

    def test_backward_step_still_arrives_on_time(self, clock):
        """-1 h on the wall clock 9.9 s into a 10 s open: arrival stays at 10 s."""
        calc = _calc_at_zero()
        calc.start_travel(100)

        clock.advance(9.9)
        assert calc.position_reached() is False

        clock.step_wall(-3600.0)

        # Still just short of the target: the step changed nothing.
        assert calc.current_position() == 99
        assert calc.position_reached() is False

        # The remaining 0.2 s of real travel elapses; the move must complete.
        clock.advance(0.2)
        assert calc.current_position() == 100
        assert calc.position_reached() is True

    def test_forward_step_before_the_move_does_not_leak_into_it(self, clock):
        """A step that lands between the anchor and the move keeps the anchor sane."""
        calc = _calc_at_zero()
        clock.step_wall(3600.0)
        calc.start_travel(100)

        clock.advance(5.0)
        assert calc.current_position() == 50
        assert calc.position_reached() is False
