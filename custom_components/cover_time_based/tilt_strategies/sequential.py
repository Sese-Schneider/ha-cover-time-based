"""Sequential tilt strategies.

Tilt couples proportionally when travel moves, but travel does NOT
couple when tilt moves. No boundary constraints are enforced.
Tilt calibration is allowed.

Two concrete variants share this logic:

- SequentialCloseTilt (the conventional behavior):  slats physically
  sit at tilt=100 (open) while the cover is not at the closed
  position. Tilt-close from the closed position sends CLOSE (motor
  down); tilt-open sends OPEN (motor up).
- SequentialOpenTilt (Sese-Schneider/ha-cover-time-based#61):  slats
  physically sit at tilt=0 (closed) while the cover is not at the
  closed position. Tilt-open articulates the slats by driving the
  motor further DOWN past the cover-closed position; tilt-close
  sends OPEN (motor up).
"""

from __future__ import annotations

import logging

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from .base import TiltStrategy, TiltTo, TravelTo

_LOGGER = logging.getLogger(__name__)


class SequentialTilt(TiltStrategy):
    """Sequential tilt base.

    Shared planning and snap logic for sequential modes. Subclasses
    set ``implicit_tilt_during_travel`` — the tilt value physically
    enforced whenever the cover is not at the closed position — and
    optionally override ``tilt_command_for``.
    """

    implicit_tilt_during_travel: int = 100

    def can_calibrate_tilt(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "sequential_close"

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
        if current_tilt != self.implicit_tilt_during_travel:
            steps.append(TiltTo(self.implicit_tilt_during_travel))
        steps.append(TravelTo(target_pos))
        return steps

    def plan_move_tilt(
        self, target_tilt: int, current_pos: int, current_tilt: int
    ) -> list[TiltTo | TravelTo]:
        steps: list[TiltTo | TravelTo] = []
        if current_pos != 0:
            steps.append(TravelTo(0))
        steps.append(TiltTo(target_tilt))
        return steps

    def allows_endpoint_runon(self, position: int) -> bool:
        # Run-on at position 0 would drive the motor further down past
        # cover-closed — which for sequential modes is a slat-articulation
        # direction (tilt-close for sequential_close; tilt-open for
        # sequential_open). Blocking here is correct for both the post-
        # TiltTo(0) case and for a bare TravelTo(0) with no trailing tilt.
        return position != 0

    def snap_trackers_to_physical(self, travel_calc, tilt_calc):
        current_travel = travel_calc.current_position()
        current_tilt_pos = tilt_calc.current_position()
        if current_travel is None or current_tilt_pos is None:
            return
        implicit = self.implicit_tilt_during_travel
        if current_travel != 0 and current_tilt_pos != implicit:
            _LOGGER.debug(
                "%s :: Travel at %d%% (not closed), forcing tilt to %d%% (was %d%%)",
                type(self).__name__,
                current_travel,
                implicit,
                current_tilt_pos,
            )
            tilt_calc.set_position(implicit)


class SequentialCloseTilt(SequentialTilt):
    """Conventional sequential tilt.

    Slats are physically at tilt=100 (open) while the cover is not at
    the closed position. Tilt-close sends CLOSE (motor down);
    tilt-open sends OPEN (motor up).

    Inherits all behavior from SequentialTilt; exists as a distinct
    type so callers can distinguish conventional and inverted sequential
    variants via isinstance checks (see SequentialOpenTilt).
    """


class SequentialOpenTilt(SequentialTilt):
    """Inverted sequential tilt (Sese-Schneider/ha-cover-time-based#61).

    Slats are physically at tilt=0 (closed) while the cover is not at
    the closed position. Tilt-open articulates the slats by driving
    the motor further DOWN past the cover-closed position; tilt-close
    sends OPEN (motor up to return from the open-slats position to
    the slats-closed position).
    """

    implicit_tilt_during_travel: int = 0

    @property
    def name(self) -> str:
        return "sequential_open"

    def tilt_command_for(self, closing_tilt: bool) -> str:
        return SERVICE_OPEN_COVER if closing_tilt else SERVICE_CLOSE_COVER
