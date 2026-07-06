"""Actuation drivers for wrapped covers.

A driver encapsulates the one thing that differs between a natively-driven
wrapped cover and a time-based one: how a position move is actuated, and
whether the device drives to the target and holds there itself. Everything
else — display animation, settle-snap, stop, coupling — stays on the cover.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .cover_base import CoverTimeBased


class PositionDriver(ABC):
    """Actuates a position move for a wrapped cover's position axis."""

    #: Whether the device drives to the target and holds there on its own.
    holds_itself: bool = False

    def __init__(self, cover) -> None:
        self._cover = cover

    @abstractmethod
    async def command_move(self, target, command, already_moving_same_dir) -> None:
        """Actuate a mid-position move toward ``target``."""


class TimedPositionDriver(PositionDriver):
    """Relay-driven position: latched open/close + timed stop (base behaviour)."""

    holds_itself = False

    async def command_move(self, target, command, already_moving_same_dir) -> None:
        await CoverTimeBased._command_position_move(
            self._cover, target, command, already_moving_same_dir
        )


class NativePositionDriver(PositionDriver):
    """Native position: forward set_cover_position; the device holds itself.

    Forwarding fires unconditionally, including on a same-direction retarget
    (the device changes course to the new target) — which is why
    ``already_moving_same_dir`` is ignored here, unlike the timed path.
    """

    holds_itself = True

    async def command_move(self, target, command, already_moving_same_dir) -> None:
        cover = self._cover
        cover._require_movement_target_available(cover._cover_entity_id)
        cover._log(
            "_command_position_move :: forwarding set_cover_position(%d)", target
        )
        await cover._call_set_cover_position(int(round(target)))


class TiltDriver(ABC):
    """Actuates a tilt move for a wrapped cover's tilt axis."""

    #: Whether the device drives to the tilt target and holds there on its own.
    holds_itself: bool = False

    def __init__(self, cover) -> None:
        self._cover = cover

    @abstractmethod
    async def move_to(self, target) -> None:
        """Actuate a tilt move toward ``target`` (0-100)."""


class NativeTiltDriver(TiltDriver):
    """Native tilt: forward set_cover_tilt_position; the device holds itself.

    Forwards the command, then animates ``tilt_calc`` toward the target so the
    integration reports live motion; the auto-updater issues no relay stop
    (the cover's ``_motor_stops_itself`` is tilt-aware), and the settle-snap
    corrects ``tilt_calc`` to the device's reported tilt once it stops.
    """

    holds_itself = True

    async def move_to(self, target) -> None:
        cover = self._cover
        await cover._prepare_native_tilt()
        current = cover.tilt_calc.current_position()
        if current is not None and int(current) == target:
            return
        cover._self_initiated_movement = not cover._triggered_externally
        cover._moving_tilt = True
        cover._log("NativeTiltDriver :: forwarding set_cover_tilt_position(%d)", target)
        await cover._call_set_cover_tilt_position(target)
        if current is None:
            cover.tilt_calc.update_position(100 if target <= 50 else 0)
        cover.tilt_calc.start_travel(target)
        cover.start_auto_updater()
