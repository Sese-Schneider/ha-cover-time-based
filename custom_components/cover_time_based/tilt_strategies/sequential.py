"""Sequential tilt strategy.

Tilt couples proportionally when travel moves, but travel does NOT
couple when tilt moves. No boundary constraints are enforced.
Tilt calibration is allowed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import TiltStrategy, calc_coupled_target

if TYPE_CHECKING:
    from xknx.devices import TravelCalculator


class SequentialTilt(TiltStrategy):
    """Sequential tilt mode.

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
        return calc_coupled_target(
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
