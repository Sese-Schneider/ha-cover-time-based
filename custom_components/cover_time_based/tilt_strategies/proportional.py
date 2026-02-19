"""Proportional tilt strategy.

Travel and tilt are fully coupled in both directions. At travel
boundaries (0% or 100%), tilt is forced to match. Tilt calibration
is not allowed because tilt is derived from travel position.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import TiltStrategy, TiltTo, TravelTo, calc_coupled_target

if TYPE_CHECKING:
    from xknx.devices import TravelCalculator

_LOGGER = logging.getLogger(__name__)


class ProportionalTilt(TiltStrategy):
    """Proportional tilt mode.

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
        """Return proportional travel target when tilt moves."""
        return calc_coupled_target(
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

    @property
    def name(self) -> str:
        return "proportional"

    @property
    def uses_tilt_motor(self) -> bool:
        return False

    def plan_move_position(
        self, target_pos: int, current_pos: int, current_tilt: int
    ) -> list[TiltTo | TravelTo]:
        return [TravelTo(target_pos, coupled_tilt=target_pos)]

    def plan_move_tilt(
        self, target_tilt: int, current_pos: int, current_tilt: int
    ) -> list[TiltTo | TravelTo]:
        return [TiltTo(target_tilt, coupled_travel=target_tilt)]

    def snap_trackers_to_physical(self, travel_calc, tilt_calc):
        # Same logic as existing enforce_constraints
        current_travel = travel_calc.current_position()
        current_tilt_pos = tilt_calc.current_position()
        if current_travel == 0 and current_tilt_pos != 0:
            _LOGGER.debug(
                "ProportionalTilt :: Travel at 0%%, forcing tilt to 0%% (was %d%%)",
                current_tilt_pos,
            )
            tilt_calc.set_position(0)
        elif current_travel == 100 and current_tilt_pos != 100:
            _LOGGER.debug(
                "ProportionalTilt :: Travel at 100%%, forcing tilt to 100%% (was %d%%)",
                current_tilt_pos,
            )
            tilt_calc.set_position(100)
