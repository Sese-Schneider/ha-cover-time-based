"""The travel motor rests DIRECTION_CHANGE_DELAY between a stop and a move the
other way, whichever command asks for the move.

The settle gap used to belong to the command that reversed the cover: a newer
command arriving during the gap, a stop followed straight away by the opposite
direction, or a start still parked when the opposite command came, all drove
the motor the other way without the rest.
"""

import asyncio
from unittest.mock import patch

import pytest

from custom_components.cover_time_based import cover_base, travel_calculator
from custom_components.cover_time_based.const import DIRECTION_CHANGE_DELAY
from tests.helpers import FakeClock, relay_calls, stub_switches

_OPEN_ON = ("turn_on", "switch.open")
_CLOSE_ON = ("turn_on", "switch.close")


class _GatedSleep:
    """Park every cover_base sleep until released and record what it asked for.

    Each sleep gets its own gate, so cancelling one (a parked start) leaves the
    others parked.
    """

    def __init__(self):
        self.slept = []
        self._gates = []

    async def __call__(self, seconds):
        self.slept.append(seconds)
        gate = asyncio.get_running_loop().create_future()
        self._gates.append(gate)
        await gate

    def release(self):
        for gate in self._gates:
            if not gate.done():
                gate.set_result(None)
        self._gates = []


@pytest.fixture
def clock():
    clock = FakeClock()
    with (
        patch.object(cover_base, "time", clock),
        patch.object(travel_calculator, "time", clock),
    ):
        yield clock


@pytest.fixture
def gated_sleep():
    gate = _GatedSleep()
    with patch.object(cover_base, "sleep", gate):
        yield gate


async def _turns(n=10):
    for _ in range(n):
        await asyncio.sleep(0)


def _cover(make_cover, **kwargs):
    cover = make_cover(**kwargs)
    stub_switches(cover)
    cover.async_write_ha_state = lambda: None
    return cover


def _mark(cover):
    return len(cover.hass.services.async_call.call_args_list)


# ---------------------------------------------------------------------------
# Gap A: a newer command during a reversal's settle gap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_newer_target_during_settle_waits_out_the_rest(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.set_position(0)
    clock.advance(2)

    first = asyncio.ensure_future(cover.set_position(80))
    await _turns()
    mark = _mark(cover)
    second = asyncio.ensure_future(cover.set_position(90))
    await _turns()

    assert _OPEN_ON not in relay_calls(cover, mark), "drove inside the settle gap"

    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await asyncio.gather(first, second)

    assert relay_calls(cover, mark)[-1] == _OPEN_ON
    assert cover.travel_calc._travel_to_position == 90


# ---------------------------------------------------------------------------
# Stop, then the other way at once
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_straight_after_stopping_a_close_waits_out_the_rest(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)
    await cover.async_stop_cover()
    clock.advance(0.25)
    mark = _mark(cover)

    opening = asyncio.ensure_future(cover.async_open_cover())
    await _turns()

    assert _OPEN_ON not in relay_calls(cover, mark)
    assert gated_sleep.slept == [pytest.approx(DIRECTION_CHANGE_DELAY - 0.25)]

    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await opening

    assert relay_calls(cover, mark)[-1] == _OPEN_ON
    assert cover.travel_calc.is_opening()


@pytest.mark.asyncio
async def test_set_position_straight_after_stopping_waits_out_the_rest(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)
    await cover.async_stop_cover()
    mark = _mark(cover)

    moving = asyncio.ensure_future(cover.set_position(90))
    await _turns()

    assert _OPEN_ON not in relay_calls(cover, mark)

    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await moving

    assert relay_calls(cover, mark)[-1] == _OPEN_ON


@pytest.mark.asyncio
async def test_same_direction_straight_after_stopping_does_not_wait(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)
    await cover.async_stop_cover()
    mark = _mark(cover)

    await cover.async_close_cover()

    assert gated_sleep.slept == []
    assert relay_calls(cover, mark)[-1] == _CLOSE_ON


@pytest.mark.asyncio
async def test_opposite_direction_after_the_rest_has_passed_does_not_wait(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)
    await cover.async_stop_cover()
    clock.advance(DIRECTION_CHANGE_DELAY + 0.1)
    mark = _mark(cover)

    await cover.async_open_cover()

    assert gated_sleep.slept == []
    assert relay_calls(cover, mark)[-1] == _OPEN_ON


@pytest.mark.asyncio
async def test_a_stop_during_the_rest_cancels_the_move(make_cover, clock, gated_sleep):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)
    await cover.async_stop_cover()
    mark = _mark(cover)

    opening = asyncio.ensure_future(cover.async_open_cover())
    await _turns()
    await cover.async_stop_cover()
    gated_sleep.release()
    await opening

    assert _OPEN_ON not in relay_calls(cover, mark)
    assert not cover.travel_calc.is_traveling()


@pytest.mark.asyncio
async def test_a_completed_reversal_does_not_rest_twice(make_cover, clock, gated_sleep):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.set_position(0)
    clock.advance(2)

    reversing = asyncio.ensure_future(cover.set_position(80))
    await _turns()
    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await reversing

    assert gated_sleep.slept == [DIRECTION_CHANGE_DELAY]
    assert relay_calls(cover)[-1] == _OPEN_ON


# ---------------------------------------------------------------------------
# Gap C: set position against a start still parked the other way
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_position_against_a_parked_start_rests_before_driving(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover, travel_startup_delay=20)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    await _turns()
    assert cover._startup_delay_task is not None
    mark = _mark(cover)

    moving = asyncio.ensure_future(cover.set_position(90))
    await _turns()

    calls = relay_calls(cover, mark)
    assert ("turn_off", "switch.close") in calls
    assert _OPEN_ON not in calls, "drove back with no rest"

    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await moving

    assert relay_calls(cover, mark)[-1] == _OPEN_ON


# ---------------------------------------------------------------------------
# Gap B: set position to where the cover has only just left
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "first", "target", "running"),
    [
        (0, "async_open_cover", 0, ("turn_off", "switch.open")),
        (100, "async_close_cover", 100, ("turn_off", "switch.close")),
    ],
    ids=["set-0-just-after-leaving-0", "set-100-just-after-leaving-100"],
)
@pytest.mark.asyncio
async def test_set_position_to_the_endpoint_just_left_stops_the_cover(
    make_cover, clock, gated_sleep, start, first, target, running
):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(start)
    await getattr(cover, first)()
    clock.advance(0.1)  # still reads the endpoint on the whole-percent tracker
    assert cover.travel_calc.current_position() == start
    mark = _mark(cover)

    moving = asyncio.ensure_future(cover.set_position(target))
    await _turns()
    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await moving

    assert running in relay_calls(cover, mark)
    assert not cover.travel_calc.is_traveling()
    assert cover.travel_calc.current_position() == target
