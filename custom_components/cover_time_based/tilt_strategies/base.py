"""Base class and shared helpers for tilt strategies."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from xknx.devices import TravelCalculator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TiltTo:
    """Step: move tilt to target position."""

    target: int
    coupled_travel: int | None = None


@dataclass(frozen=True)
class TravelTo:
    """Step: move travel to target position."""

    target: int
    coupled_tilt: int | None = None


MovementStep = TiltTo | TravelTo


def calc_coupled_target(
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
