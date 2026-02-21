"""Tilt strategy classes for cover_time_based.

Tilt strategies determine how travel and tilt movements are coupled.
"""

from .base import MovementStep, TiltStrategy, TiltTo, TravelTo, calc_coupled_target
from .dual_motor import DualMotorTilt
from .inline import InlineTilt
from .sequential import SequentialTilt

__all__ = [
    "DualMotorTilt",
    "InlineTilt",
    "MovementStep",
    "SequentialTilt",
    "TiltStrategy",
    "TiltTo",
    "TravelTo",
    "calc_coupled_target",
]
