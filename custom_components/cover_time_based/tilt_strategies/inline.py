"""Inline tilt strategy.

Single-motor roller shutter where tilt is embedded in the travel cycle.
At the start of any movement there is a fixed tilt phase, then travel
continues. Tilt works at any position. Tilt is restored after position
changes to non-endpoint targets.
"""

from __future__ import annotations

import logging

from .base import TiltStrategy, TiltTo, TravelTo

_LOGGER = logging.getLogger(__name__)


class InlineTilt(TiltStrategy):
    """Inline tilt mode.

    Single motor where tilt is part of the travel cycle. Each direction
    has a fixed tilt phase at the start of movement. Tilt works at any
    position in the travel range.
    """

    def can_calibrate_tilt(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "inline"

    @property
    def uses_tilt_motor(self) -> bool:
        return False

    @property
    def restores_tilt(self) -> bool:
        return True

    def plan_move_position(
        self, target_pos: int, current_pos: int, current_tilt: int
    ) -> list[TiltTo | TravelTo]:
        closing = target_pos < current_pos
        tilt_endpoint = 0 if closing else 100
        steps: list[TiltTo | TravelTo] = []
        if current_tilt != tilt_endpoint:
            steps.append(TiltTo(tilt_endpoint))
        steps.append(TravelTo(target_pos))
        return steps

    def plan_move_tilt(
        self, target_tilt: int, current_pos: int, current_tilt: int
    ) -> list[TiltTo | TravelTo]:
        return [TiltTo(target_tilt)]

    def snap_trackers_to_physical(self, travel_calc, tilt_calc):
        # No-op: inline tilt allows any tilt value at any position.
        # Endpoint coupling during travel is handled by plan_move_position
        # pre-steps (TiltTo before TravelTo), not by post-stop snapping.
        pass
