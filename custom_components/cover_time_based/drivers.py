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
