"""Recalibration planning enum for time-based cover entities.

Kept in its own leaf module so both ``cover_base`` and the ``MovementMixin``
can import it at module load: ``cover_base`` imports the movement mixin during
its own import, so an enum defined in ``cover_base`` cannot be imported from
the mixin without a cycle.
"""

from __future__ import annotations

from enum import Enum, auto


class RecalibrationPlan(Enum):
    """What a position command should do about recalibration (issue #179)."""

    NONE = auto()
    TWO_LEG = auto()
    FORCED_ENDPOINT = auto()
