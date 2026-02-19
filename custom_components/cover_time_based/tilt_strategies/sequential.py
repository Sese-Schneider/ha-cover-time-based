"""Sequential tilt strategy.

Tilt couples proportionally when travel moves, but travel does NOT
couple when tilt moves. No boundary constraints are enforced.
Tilt calibration is allowed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import TiltStrategy, TiltTo, TravelTo, calc_coupled_target

_LOGGER = logging.getLogger(__name__)

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

    @property
    def name(self) -> str:
        return "sequential"

    @property
    def uses_tilt_motor(self) -> bool:
        return False

    def plan_move_position(self, target_pos, current_pos, current_tilt):
        steps = []
        if current_tilt != 0:
            steps.append(TiltTo(0))  # flatten slats before travel
        steps.append(TravelTo(target_pos))
        return steps

    def plan_move_tilt(self, target_tilt, current_pos, current_tilt):
        steps = []
        if current_pos != 100:
            steps.append(TravelTo(100))  # must be at closed position
        steps.append(TiltTo(target_tilt))
        return steps

    def snap_trackers_to_physical(self, travel_calc, tilt_calc):
        current_travel = travel_calc.current_position()
        current_tilt_pos = tilt_calc.current_position()
        if current_travel != 100 and current_tilt_pos != 0:
            _LOGGER.debug(
                "SequentialTilt :: Travel at %d%% (not closed), forcing tilt to 0%% (was %d%%)",
                current_travel,
                current_tilt_pos,
            )
            tilt_calc.set_position(0)
