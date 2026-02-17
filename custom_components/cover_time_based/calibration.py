"""Calibration support for cover_time_based."""

from __future__ import annotations

import time
from asyncio import Task
from dataclasses import dataclass, field

CALIBRATION_STEP_PAUSE = 2.0
CALIBRATION_OVERHEAD_STEPS = 8
CALIBRATION_MIN_MOVEMENT_START = 0.1
CALIBRATION_MIN_MOVEMENT_INCREMENT = 0.1

CALIBRATABLE_ATTRIBUTES = [
    "travel_time_down",
    "travel_time_up",
    "tilt_time_down",
    "tilt_time_up",
    "travel_motor_overhead",
    "tilt_motor_overhead",
    "min_movement_time",
]

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
    timeout_task: Task | None = field(default=None, repr=False)
    automation_task: Task | None = field(default=None, repr=False)
