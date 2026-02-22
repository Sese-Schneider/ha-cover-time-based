"""Tilt strategy classes for cover_time_based.

Tilt strategies determine how travel and tilt movements are coupled.
"""

from .base import MovementStep, TiltStrategy, TiltTo, TravelTo
from .dual_motor import DualMotorTilt
from .inline import InlineTilt
from .planning import calculate_pre_step_delay, extract_coupled_tilt, extract_coupled_travel
from .sequential import SequentialTilt

__all__ = [
    "DualMotorTilt",
    "InlineTilt",
    "MovementStep",
    "SequentialTilt",
    "TiltStrategy",
    "TiltTo",
    "TravelTo",
    "calculate_pre_step_delay",
    "extract_coupled_tilt",
    "extract_coupled_travel",
]
