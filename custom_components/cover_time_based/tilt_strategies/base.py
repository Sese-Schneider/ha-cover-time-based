"""Base class and shared helpers for tilt strategies."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

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

    @property
    def tilt_close_ends_at_a_stop(self) -> bool:
        """Whether a slat close ends against a limit wherever the slats start.

        A dedicated tilt motor stops at its own limit, and a slat close that
        drives the cover down stops at the closed end. One that drives the cover
        up (SequentialOpenTilt) would lift a closed cover whose slats were in
        fact already closed.
        """
        return (
            self.uses_tilt_motor
            or self.tilt_command_for(closing_tilt=True) == SERVICE_CLOSE_COVER
        )

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

    def allows_endpoint_runon(self, _position: int) -> bool:
        """Whether endpoint run-on should fire at the given endpoint.

        Strategies that run a tilt phase at an endpoint (e.g. sequential
        modes at position 0) should return False there, so that run-on
        does not extend the motor beyond the tilt phase.
        """
        return True

    def tilt_command_for(self, closing_tilt: bool) -> str:
        """Return the HA cover service to send for this tilt direction.

        The default maps closing_tilt=True to close and closing_tilt=False
        to open. Strategies with inverted physical direction (e.g.
        SequentialOpenTilt, where slats open by motor driving further down)
        override this.
        """
        return SERVICE_CLOSE_COVER if closing_tilt else SERVICE_OPEN_COVER

    @abstractmethod
    def snap_trackers_to_physical(
        self,
        travel_calc: TravelCalculator,
        tilt_calc: TravelCalculator,
    ) -> None:
        """Correct tracker drift after stop to match physical reality."""
