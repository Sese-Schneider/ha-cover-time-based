"""Sequential tilt strategy.

Tilt couples proportionally when travel moves, but travel does NOT
couple when tilt moves. No boundary constraints are enforced.
Tilt calibration is allowed.
"""

from __future__ import annotations

import logging

from .base import TiltStrategy, TiltTo, TravelTo

_LOGGER = logging.getLogger(__name__)


class SequentialTilt(TiltStrategy):
    """Sequential tilt mode.

    Tilt couples proportionally when travel moves, but travel does NOT
    couple when tilt moves. No boundary constraints are enforced.
    Tilt calibration is allowed.
    """

    def can_calibrate_tilt(self) -> bool:
        """Tilt calibration is allowed in sequential mode."""
        return True

    @property
    def name(self) -> str:
        return "sequential"

    @property
    def uses_tilt_motor(self) -> bool:
        return False

    @property
    def restores_tilt(self) -> bool:
        return False

    def plan_move_position(
        self, target_pos: int, current_pos: int, current_tilt: int
    ) -> list[TiltTo | TravelTo]:
        steps: list[TiltTo | TravelTo] = []
        if current_tilt != 100:
            steps.append(TiltTo(100))  # flatten slats (fully open) before travel
        steps.append(TravelTo(target_pos))
        return steps

    def plan_move_tilt(
        self, target_tilt: int, current_pos: int, current_tilt: int
    ) -> list[TiltTo | TravelTo]:
        steps: list[TiltTo | TravelTo] = []
        if current_pos != 0:
            steps.append(TravelTo(0))  # must be at closed position
        steps.append(TiltTo(target_tilt))
        return steps

    def snap_trackers_to_physical(self, travel_calc, tilt_calc):
        current_travel = travel_calc.current_position()
        current_tilt_pos = tilt_calc.current_position()
        if current_travel is None or current_tilt_pos is None:
            return
        if current_travel != 0 and current_tilt_pos != 100:
            _LOGGER.debug(
                "SequentialTilt :: Travel at %d%% (not closed), forcing tilt to 100%% (was %d%%)",
                current_travel,
                current_tilt_pos,
            )
            tilt_calc.set_position(100)
