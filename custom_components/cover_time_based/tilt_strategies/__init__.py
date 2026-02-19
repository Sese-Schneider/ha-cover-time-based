"""Tilt strategy classes for cover_time_based.

Tilt strategies determine how travel and tilt movements are coupled.
"""

from .base import TiltStrategy, calc_coupled_target
from .proportional import ProportionalTilt
from .sequential import SequentialTilt

__all__ = [
    "TiltStrategy",
    "calc_coupled_target",
    "ProportionalTilt",
    "SequentialTilt",
]
