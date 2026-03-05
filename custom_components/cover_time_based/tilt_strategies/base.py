"""Base class and shared helpers for tilt strategies."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..travel_calculator import TravelCalculator

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


class TiltStrategy(ABC):
    """Base class for tilt mode strategies."""

    @abstractmethod
    def can_calibrate_tilt(self) -> bool:
        """Whether tilt calibration is allowed."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for config/state."""

    @property
    @abstractmethod
    def uses_tilt_motor(self) -> bool:
        """Whether TiltTo steps require a separate tilt motor."""

    @property
    @abstractmethod
    def restores_tilt(self) -> bool:
        """Whether tilt should be restored after a position change."""

    @abstractmethod
    def plan_move_position(
        self,
        target_pos: int,
        current_pos: int,
        current_tilt: int,
    ) -> list[TiltTo | TravelTo]:
        """Plan steps to move cover to target_pos."""

    @abstractmethod
    def plan_move_tilt(
        self,
        target_tilt: int,
        current_pos: int,
        current_tilt: int,
    ) -> list[TiltTo | TravelTo]:
        """Plan steps to move tilt to target_tilt."""

    def allows_tilt_at_position(self, _position: int) -> bool:
        """Whether tilt is allowed at the given cover position."""
        return True

    @abstractmethod
    def snap_trackers_to_physical(
        self,
        travel_calc: TravelCalculator,
        tilt_calc: TravelCalculator,
    ) -> None:
        """Correct tracker drift after stop to match physical reality."""
