"""Tilt strategy planning helpers."""

from __future__ import annotations

from .base import TiltTo, TravelTo


def extract_coupled_tilt(steps: list[TiltTo | TravelTo]) -> int | None:
    """Extract the tilt target from a movement plan.

    For coupled steps, returns the coupled_tilt value.
    For multi-step plans (sequential), returns the TiltTo target.
    Returns None if no tilt movement in the plan.
    """
    for step in steps:
        if isinstance(step, TravelTo) and step.coupled_tilt is not None:
            return step.coupled_tilt
        if isinstance(step, TiltTo):
            return step.target
    return None


def extract_coupled_travel(steps: list[TiltTo | TravelTo]) -> int | None:
    """Extract the travel target from a movement plan.

    For coupled steps, returns the coupled_travel value.
    For multi-step plans (sequential), returns the TravelTo target.
    Returns None if no travel movement in the plan.
    """
    for step in steps:
        if isinstance(step, TiltTo) and step.coupled_travel is not None:
            return step.coupled_travel
        if isinstance(step, TravelTo):
            return step.target
    return None


def has_travel_pre_step(steps: list[TiltTo | TravelTo]) -> bool:
    """Return True if the plan requires a TravelTo before a TiltTo.

    This pattern occurs when a dual-motor tilt move requires the cover
    to travel to an allowed position first.
    """
    return (
        len(steps) >= 2
        and isinstance(steps[0], TravelTo)
        and isinstance(steps[1], TiltTo)
    )


def calculate_pre_step_delay(steps, tilt_strategy, tilt_calc, travel_calc) -> float:
    """Calculate delay before the primary calculator should start tracking.

    In sequential tilt mode (single motor), the strategy may plan a
    pre-step (e.g. TiltTo before TravelTo). The pre-step must complete
    before the primary movement begins, since both share the same motor.
    Returns 0.0 if no pre-step or if the strategy uses a separate tilt motor.
    """
    if tilt_strategy is None or tilt_strategy.uses_tilt_motor or len(steps) < 2:
        return 0.0

    first, second = steps[0], steps[1]

    # TiltTo before TravelTo: tilt is the pre-step
    if isinstance(first, TiltTo) and isinstance(second, TravelTo):
        current_tilt = tilt_calc.current_position()
        if current_tilt is None:
            return 0.0
        return tilt_calc.calculate_travel_time(current_tilt, first.target)

    # TravelTo before TiltTo: travel is the pre-step
    if isinstance(first, TravelTo) and isinstance(second, TiltTo):
        current_pos = travel_calc.current_position()
        if current_pos is None:
            return 0.0
        return travel_calc.calculate_travel_time(current_pos, first.target)

    return 0.0
