"""Pure phase/press-planning logic for the single-button control mode.

A single-button cover exposes ONE control input; each press advances a fixed
cycle (down -> stop -> up -> stop) and the motor auto-stops at its physical
limits. With no feedback we model the motor's phase by dead reckoning and plan
the presses needed to satisfy an open/close/stop request.

Deliberately pure (no Home Assistant, no I/O) so the cycle maths can be
unit-tested in isolation -- that is where the subtle bugs live.
"""

from __future__ import annotations

from enum import Enum


class Phase(str, Enum):
    """The motor's position in the down/stop/up/stop cycle, as we track it."""

    AT_CLOSED = "at_closed"
    MOVING_UP = "moving_up"
    STOPPED_AFTER_UP = "stopped_after_up"
    AT_OPEN = "at_open"
    MOVING_DOWN = "moving_down"
    STOPPED_AFTER_DOWN = "stopped_after_down"


class Action(str, Enum):
    """A requested cover action to plan presses for."""

    OPEN = "open"
    CLOSE = "close"
    STOP = "stop"


# What a single press does from each phase. Endpoint arrivals (moving_* ->
# at_open/at_closed) are NOT here: those happen by time, not by a press, and
# are applied by the caller when travel reaches an endpoint.
PRESS_TRANSITION: dict[Phase, Phase] = {
    Phase.AT_CLOSED: Phase.MOVING_UP,
    Phase.MOVING_UP: Phase.STOPPED_AFTER_UP,
    Phase.STOPPED_AFTER_UP: Phase.MOVING_DOWN,  # reversal-on-stop
    Phase.AT_OPEN: Phase.MOVING_DOWN,
    Phase.MOVING_DOWN: Phase.STOPPED_AFTER_DOWN,
    Phase.STOPPED_AFTER_DOWN: Phase.MOVING_UP,  # reversal-on-stop
}

# Phases that already satisfy a request (no presses needed).
_SATISFIED: dict[Action, set[Phase]] = {
    Action.OPEN: {Phase.MOVING_UP, Phase.AT_OPEN},
    Action.CLOSE: {Phase.MOVING_DOWN, Phase.AT_CLOSED},
    Action.STOP: {
        Phase.AT_CLOSED,
        Phase.AT_OPEN,
        Phase.STOPPED_AFTER_UP,
        Phase.STOPPED_AFTER_DOWN,
    },
}

# The phase OPEN/CLOSE want to reach. STOP is handled separately (it wants
# "not moving", not a specific phase).
_GOAL: dict[Action, Phase] = {
    Action.OPEN: Phase.MOVING_UP,
    Action.CLOSE: Phase.MOVING_DOWN,
}

_MOVING: set[Phase] = {Phase.MOVING_UP, Phase.MOVING_DOWN}


def next_phase(phase: Phase) -> Phase:
    """Return the phase after a single press."""
    return PRESS_TRANSITION[phase]


def is_moving(phase: Phase) -> bool:
    """Return True if the motor is travelling in ``phase``."""
    return phase in _MOVING


def plan(phase: Phase, action: Action) -> list[Phase]:
    """Return the phase after each press needed to satisfy ``action``.

    One entry per press, in order; each entry is the predicted phase after
    that press. An empty list means the request is already satisfied. The
    last entry is the phase the caller treats as current once all presses
    have been sent.
    """
    if phase in _SATISFIED[action]:
        return []

    if action is Action.STOP:
        # Only reachable while moving; one press stops.
        return [next_phase(phase)]

    goal = _GOAL[action]
    steps: list[Phase] = []
    current = phase
    # Advance the cycle a press at a time until heading the right way. Max 3
    # presses (the nudge case); the bound guards a corrupt state.
    for _ in range(len(PRESS_TRANSITION)):
        current = next_phase(current)
        steps.append(current)
        if current is goal:
            return steps
    raise ValueError(f"cannot plan {action} from {phase}")
