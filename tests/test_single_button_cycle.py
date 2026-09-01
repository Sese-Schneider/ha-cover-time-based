import pytest

from custom_components.cover_time_based.single_button_cycle import (
    Action,
    Phase,
    is_moving,
    next_phase,
    plan,
)


@pytest.mark.parametrize(
    "phase, expected",
    [
        (Phase.AT_CLOSED, Phase.MOVING_UP),
        (Phase.MOVING_UP, Phase.STOPPED_AFTER_UP),
        (Phase.STOPPED_AFTER_UP, Phase.MOVING_DOWN),  # reversal
        (Phase.AT_OPEN, Phase.MOVING_DOWN),
        (Phase.MOVING_DOWN, Phase.STOPPED_AFTER_DOWN),
        (Phase.STOPPED_AFTER_DOWN, Phase.MOVING_UP),  # reversal
    ],
)
def test_next_phase(phase, expected):
    assert next_phase(phase) == expected


@pytest.mark.parametrize(
    "phase, moving",
    [
        (Phase.MOVING_UP, True),
        (Phase.MOVING_DOWN, True),
        (Phase.AT_CLOSED, False),
        (Phase.AT_OPEN, False),
        (Phase.STOPPED_AFTER_UP, False),
        (Phase.STOPPED_AFTER_DOWN, False),
    ],
)
def test_is_moving(phase, moving):
    assert is_moving(phase) is moving


@pytest.mark.parametrize(
    "phase, expected",
    [
        (Phase.AT_CLOSED, [Phase.MOVING_UP]),
        (Phase.STOPPED_AFTER_DOWN, [Phase.MOVING_UP]),
        (Phase.MOVING_DOWN, [Phase.STOPPED_AFTER_DOWN, Phase.MOVING_UP]),
        (
            Phase.STOPPED_AFTER_UP,
            [Phase.MOVING_DOWN, Phase.STOPPED_AFTER_DOWN, Phase.MOVING_UP],
        ),  # nudge
        (Phase.MOVING_UP, []),
        (Phase.AT_OPEN, []),
    ],
)
def test_plan_open(phase, expected):
    assert plan(phase, Action.OPEN) == expected


@pytest.mark.parametrize(
    "phase, expected",
    [
        (Phase.AT_OPEN, [Phase.MOVING_DOWN]),
        (Phase.STOPPED_AFTER_UP, [Phase.MOVING_DOWN]),
        (Phase.MOVING_UP, [Phase.STOPPED_AFTER_UP, Phase.MOVING_DOWN]),
        (
            Phase.STOPPED_AFTER_DOWN,
            [Phase.MOVING_UP, Phase.STOPPED_AFTER_UP, Phase.MOVING_DOWN],
        ),  # nudge
        (Phase.MOVING_DOWN, []),
        (Phase.AT_CLOSED, []),
    ],
)
def test_plan_close(phase, expected):
    assert plan(phase, Action.CLOSE) == expected


@pytest.mark.parametrize(
    "phase, expected",
    [
        (Phase.MOVING_UP, [Phase.STOPPED_AFTER_UP]),
        (Phase.MOVING_DOWN, [Phase.STOPPED_AFTER_DOWN]),
        (Phase.AT_CLOSED, []),
        (Phase.AT_OPEN, []),
        (Phase.STOPPED_AFTER_UP, []),
        (Phase.STOPPED_AFTER_DOWN, []),
    ],
)
def test_plan_stop(phase, expected):
    assert plan(phase, Action.STOP) == expected
