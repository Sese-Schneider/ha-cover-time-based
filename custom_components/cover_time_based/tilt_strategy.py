"""Strategy classes for tilt mode behavior.

Tilt modes determine how travel and tilt movements are coupled:
- SequentialTilt ("before_after"): tilt moves proportionally when travel moves,
  but travel does NOT move when tilt moves.
- ProportionalTilt ("during"): travel and tilt are fully coupled in both
  directions, and tilt is forced to match at travel boundaries (0% / 100%).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from xknx.devices import TravelCalculator

_LOGGER = logging.getLogger(__name__)


def _calc_coupled_target(
    movement_time: float,
    closing: bool,
    coupled_calc: TravelCalculator,
    coupled_time_close: float,
    coupled_time_open: float,
) -> int:
    """Calculate target position for a coupled calculator based on primary movement time.

    When travel moves, tilt moves proportionally (and vice versa when
    travel_moves_with_tilt is enabled). This computes how far the coupled
    calculator should move given the primary movement duration.
    """
    coupled_time = coupled_time_close if closing else coupled_time_open
    coupled_distance = (movement_time / coupled_time) * 100.0
    current = coupled_calc.current_position()
    assert current is not None, (
        "coupled calculator position must be set before coupling"
    )
    if closing:
        return min(100, int(current + coupled_distance))
    return max(0, int(current - coupled_distance))


class TiltStrategy(ABC):
    """Base class for tilt mode strategies."""

    @abstractmethod
    def calc_tilt_for_travel(
        self,
        movement_time: float,
        closing: bool,
        tilt_calc: TravelCalculator,
        tilt_time_close: float,
        tilt_time_open: float,
    ) -> int | None:
        """When travel moves, what tilt target? None = no coupling."""

    @abstractmethod
    def calc_travel_for_tilt(
        self,
        movement_time: float,
        closing: bool,
        travel_calc: TravelCalculator,
        travel_time_close: float,
        travel_time_open: float,
    ) -> int | None:
        """When tilt moves, what travel target? None = no coupling."""

    @abstractmethod
    def enforce_constraints(
        self,
        travel_calc: TravelCalculator,
        tilt_calc: TravelCalculator,
    ) -> None:
        """Enforce constraints after stop."""

    @abstractmethod
    def can_calibrate_tilt(self) -> bool:
        """Whether tilt calibration is allowed."""


class SequentialTilt(TiltStrategy):
    """Sequential tilt mode ("before_after").

    Tilt couples proportionally when travel moves, but travel does NOT
    couple when tilt moves. No boundary constraints are enforced.
    Tilt calibration is allowed.
    """

    def calc_tilt_for_travel(
        self,
        movement_time: float,
        closing: bool,
        tilt_calc: TravelCalculator,
        tilt_time_close: float,
        tilt_time_open: float,
    ) -> int | None:
        """Return proportional tilt target when travel moves."""
        return _calc_coupled_target(
            movement_time, closing, tilt_calc, tilt_time_close, tilt_time_open
        )

    def calc_travel_for_tilt(
        self,
        movement_time: float,
        closing: bool,
        travel_calc: TravelCalculator,
        travel_time_close: float,
        travel_time_open: float,
    ) -> int | None:
        """Tilt movement does not couple travel in sequential mode."""
        return None

    def enforce_constraints(
        self,
        travel_calc: TravelCalculator,
        tilt_calc: TravelCalculator,
    ) -> None:
        """No constraints in sequential mode."""

    def can_calibrate_tilt(self) -> bool:
        """Tilt calibration is allowed in sequential mode."""
        return True


class ProportionalTilt(TiltStrategy):
    """Proportional tilt mode ("during").

    Travel and tilt are fully coupled in both directions. At travel
    boundaries (0% or 100%), tilt is forced to match. Tilt calibration
    is not allowed because tilt is derived from travel position.
    """

    def calc_tilt_for_travel(
        self,
        movement_time: float,
        closing: bool,
        tilt_calc: TravelCalculator,
        tilt_time_close: float,
        tilt_time_open: float,
    ) -> int | None:
        """Return proportional tilt target when travel moves."""
        return _calc_coupled_target(
            movement_time, closing, tilt_calc, tilt_time_close, tilt_time_open
        )

    def calc_travel_for_tilt(
        self,
        movement_time: float,
        closing: bool,
        travel_calc: TravelCalculator,
        travel_time_close: float,
        travel_time_open: float,
    ) -> int | None:
        """Return proportional travel target when tilt moves."""
        return _calc_coupled_target(
            movement_time, closing, travel_calc, travel_time_close, travel_time_open
        )

    def enforce_constraints(
        self,
        travel_calc: TravelCalculator,
        tilt_calc: TravelCalculator,
    ) -> None:
        """Force tilt to match at travel boundaries (0% or 100%)."""
        current_travel = travel_calc.current_position()
        current_tilt = tilt_calc.current_position()

        if current_travel == 0 and current_tilt != 0:
            _LOGGER.debug(
                "ProportionalTilt :: Travel at 0%%, forcing tilt to 0%% (was %d%%)",
                current_tilt,
            )
            tilt_calc.set_position(0)
        elif current_travel == 100 and current_tilt != 100:
            _LOGGER.debug(
                "ProportionalTilt :: Travel at 100%%, forcing tilt to 100%% (was %d%%)",
                current_tilt,
            )
            tilt_calc.set_position(100)

    def can_calibrate_tilt(self) -> bool:
        """Tilt calibration is not allowed in proportional mode."""
        return False
