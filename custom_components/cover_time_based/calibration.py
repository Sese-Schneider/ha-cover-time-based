"""Calibration support for cover_time_based."""

from __future__ import annotations

import time
from asyncio import Task
from dataclasses import dataclass, field

CALIBRATION_STEP_PAUSE = 2.0
CALIBRATION_OVERHEAD_STEPS = 8
CALIBRATION_MIN_MOVEMENT_START = 0.1
CALIBRATION_MIN_MOVEMENT_INCREMENT = 0.1
CALIBRATION_MIN_MOVEMENT_INITIAL_PAUSE = 5.0

CALIBRATABLE_ATTRIBUTES = [
    "travel_time_close",
    "travel_time_open",
    "travel_startup_delay",
    "tilt_time_close",
    "tilt_time_open",
    "tilt_startup_delay",
    "min_movement_time",
]

# Tilt modes that support independent tilt calibration
_TILT_CALIBRATION_MODES = {"sequential", "dual_motor"}


def get_calibratable_attributes(tilt_mode: str) -> list[str]:
    """Return calibratable attributes filtered by tilt mode.

    Proportional and none modes exclude tilt attributes because
    tilt is either derived from position or not configured.
    """
    if tilt_mode in _TILT_CALIBRATION_MODES:
        return list(CALIBRATABLE_ATTRIBUTES)
    return [a for a in CALIBRATABLE_ATTRIBUTES if not a.startswith("tilt_")]


SERVICE_START_CALIBRATION = "start_calibration"
SERVICE_STOP_CALIBRATION = "stop_calibration"


@dataclass
class CalibrationState:
    """Holds state for an in-progress calibration test."""

    attribute: str
    timeout: float
    started_at: float = field(default_factory=time.monotonic)
    step_count: int = 0
    step_duration: float | None = None
    last_pulse_duration: float | None = None
    continuous_start: float | None = None
    move_command: str | None = None
    timeout_task: Task | None = field(default=None, repr=False)
    automation_task: Task | None = field(default=None, repr=False)
