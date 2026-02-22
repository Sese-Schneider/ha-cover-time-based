"""Dual-motor tilt strategy.

Separate tilt motor with its own switch entities. Optionally boundary-locked
(tilt only allowed when cover position <= max_tilt_allowed_position).
Before travel, slats move to a configurable safe position.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import TiltStrategy, TiltTo, TravelTo

if TYPE_CHECKING:
    from ..travel_calculator import TravelCalculator

_LOGGER = logging.getLogger(__name__)


class DualMotorTilt(TiltStrategy):
    """Dual-motor tilt — independent tilt motor with optional boundary lock."""

    def __init__(
        self,
        safe_tilt_position: int = 100,
        max_tilt_allowed_position: int | None = None,
    ) -> None:
        self._safe_tilt_position = safe_tilt_position
        self._max_tilt_allowed_position = max_tilt_allowed_position

    def can_calibrate_tilt(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "dual_motor"

    @property
    def uses_tilt_motor(self) -> bool:
        return True

    @property
    def restores_tilt(self) -> bool:
        return True

    def plan_move_position(
        self, target_pos: int, current_pos: int, current_tilt: int
    ) -> list[TiltTo | TravelTo]:
        steps: list[TiltTo | TravelTo] = []
        if current_tilt != self._safe_tilt_position:
            steps.append(TiltTo(self._safe_tilt_position))
        steps.append(TravelTo(target_pos))
        return steps

    def plan_move_tilt(
        self, target_tilt: int, current_pos: int, current_tilt: int
    ) -> list[TiltTo | TravelTo]:
        steps: list[TiltTo | TravelTo] = []
        if (
            self._max_tilt_allowed_position is not None
            and current_pos > self._max_tilt_allowed_position
        ):
            steps.append(TravelTo(self._max_tilt_allowed_position))
        steps.append(TiltTo(target_tilt))
        return steps

    def snap_trackers_to_physical(
        self,
        travel_calc: TravelCalculator,
        tilt_calc: TravelCalculator,
    ) -> None:
        if self._max_tilt_allowed_position is None:
            return
        current_travel = travel_calc.current_position()
        current_tilt = tilt_calc.current_position()
        if current_travel is None or current_tilt is None:
            return
        if (
            current_travel > self._max_tilt_allowed_position
            and current_tilt != self._safe_tilt_position
        ):
            _LOGGER.debug(
                "DualMotorTilt :: Travel at %d%% (above max %d%%), "
                "forcing tilt to safe %d%% (was %d%%)",
                current_travel,
                self._max_tilt_allowed_position,
                self._safe_tilt_position,
                current_tilt,
            )
            tilt_calc.set_position(self._safe_tilt_position)
