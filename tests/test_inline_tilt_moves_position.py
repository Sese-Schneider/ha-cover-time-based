"""Inline tilt: changing only the slats also moves the cover (issue #233).

One motor turns the slats and moves the cover, so a slat change shifts the
position by ``|tilt turned| x tilt_time / travel_time`` in the slats'
direction. The shift is applied once, when the slats stop. The covers below
use a 0.1 ratio (0.2s slat time over 2.0s travel time).
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.cover_time_based import travel_calculator
from tests.helpers import FakeClock, relay_calls, stub_switches
from tests.test_cover_wrapped import (
    _F_CLOSE,
    _F_OPEN,
    _F_SET_TILT,
    _make_wrapped_cover,
    _set_wrapped_features,
    _stub_updates,
)

INLINE = {
    "tilt_mode": "inline",
    "travel_time_close": 2.0,
    "travel_time_open": 2.0,
    "tilt_time_close": 0.2,
    "tilt_time_open": 0.2,
}

# Relay calls for a 100 -> 0 slat move, driven by _drive below; the position
# shift must not add any.
SWITCH_SLAT_CLOSE_CALLS = [
    ("turn_off", "switch.open"),
    ("turn_on", "switch.close"),
    ("turn_off", "switch.close"),
    ("turn_off", "switch.open"),
]
TOGGLE_SLAT_CLOSE_CALLS = [
    ("turn_off", "switch.open"),
    ("turn_on", "switch.close"),
    ("turn_on", "switch.close"),
]


@pytest.fixture
def clock():
    """Drive the trackers' clock by hand."""
    fake = FakeClock()
    with patch.object(travel_calculator, "time", fake):
        yield fake


def _no_settle():
    return patch(
        "custom_components.cover_time_based.cover_base.sleep", new_callable=AsyncMock
    )


def _inline(make_cover, **kwargs):
    cover = make_cover(**{"control_mode": "switch", **INLINE, **kwargs})
    stub_switches(cover)
    return cover


async def _flush():
    for _ in range(5):
        await asyncio.sleep(0)


async def _advance(cover, clock, seconds):
    """Let ``seconds`` pass; stop on arrival as the auto-updater would."""
    for _ in range(round(seconds / 0.01)):
        clock.advance(0.01)
        if cover.position_reached():
            await cover.auto_stop_if_necessary()
            break
    await _flush()


async def _to_completion(cover, clock):
    for _ in range(10):
        await _advance(cover, clock, 0.5)
        if not cover.travel_calc.is_traveling() and not cover.tilt_calc.is_traveling():
            return
    raise AssertionError("movement did not complete")


async def _cancel_tasks(cover):
    tasks = getattr(cover.hass, "_test_tasks", [])
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        tasks.clear()


def _at(cover, position, tilt):
    cover.travel_calc.set_position(position)
    cover.tilt_calc.set_position(tilt)


@pytest.mark.asyncio
async def test_set_tilt_position_moves_position_when_slats_stop(make_cover, clock):
    cover = _inline(make_cover)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        await _advance(cover, clock, 0.1)
        assert cover.tilt_calc.is_traveling()
        assert not cover.travel_calc.is_traveling()
        assert cover.travel_calc.current_position() == 50
        await _to_completion(cover, clock)
    assert cover.travel_calc.current_position() == 40
    assert cover.tilt_calc.current_position() == 0
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_close_tilt_moves_position(make_cover, clock):
    cover = _inline(make_cover)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover_tilt()
        await _to_completion(cover, clock)
    assert cover.travel_calc.current_position() == 40
    assert cover.tilt_calc.current_position() == 0
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_open_tilt_moves_position(make_cover, clock):
    cover = _inline(make_cover)
    _at(cover, 50, 0)
    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover_tilt()
        await _to_completion(cover, clock)
    assert cover.travel_calc.current_position() == 60
    assert cover.tilt_calc.current_position() == 100
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_stop_partway_shifts_by_the_part_turned(make_cover, clock):
    cover = _inline(make_cover)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        await _advance(cover, clock, 0.1)
        await cover.async_stop_cover_tilt()
    tilt_at_stop = cover.tilt_calc.current_position()
    assert 0 < tilt_at_stop < 100
    assert cover.travel_calc.current_position() == 50 - round(
        (100 - tilt_at_stop) * 0.1
    )
    assert 40 < cover.travel_calc.current_position() < 50
    assert not cover.travel_calc.is_traveling()
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_near_a_limit_the_position_is_capped(make_cover, clock):
    cover = _inline(make_cover)
    _at(cover, 3, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        await _to_completion(cover, clock)
    assert relay_calls(cover) == SWITCH_SLAT_CLOSE_CALLS
    assert cover.tilt_calc.current_position() == 0
    assert cover.travel_calc.current_position() == 0
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_slat_move_relay_calls_unchanged(make_cover, clock):
    cover = _inline(make_cover)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        await _to_completion(cover, clock)
    assert relay_calls(cover) == SWITCH_SLAT_CLOSE_CALLS
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_back_and_forth_returns_to_start(make_cover, clock):
    cover = _inline(make_cover)
    _at(cover, 50, 0)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(100)
        await _to_completion(cover, clock)
        assert cover.travel_calc.current_position() == 60
        await cover.set_tilt_position(0)
        await _to_completion(cover, clock)
    assert cover.travel_calc.current_position() == 50
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_too_short_slat_move_moves_nothing(make_cover, clock):
    cover = _inline(make_cover, min_movement_time=1.0)
    _at(cover, 50, 50)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(40)
    assert not cover.tilt_calc.is_traveling()
    assert cover.travel_calc.current_position() == 50
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_same_direction_retarget_shifts_by_the_whole_turn(make_cover, clock):
    cover = _inline(make_cover)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(50)
        await _advance(cover, clock, 0.04)
        assert cover.tilt_calc.is_traveling()
        await cover.set_tilt_position(0)
        await _to_completion(cover, clock)
    assert cover.tilt_calc.current_position() == 0
    assert cover.travel_calc.current_position() == 40
    await _cancel_tasks(cover)


@pytest.mark.parametrize(("target", "relays"), [(80, "opposite"), (20, "same")])
@pytest.mark.asyncio
async def test_cover_move_mid_slat_move_starts_from_shifted_position(
    make_cover, clock, target, relays
):
    cover = _inline(make_cover)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"), _no_settle():
        await cover.set_tilt_position(0)
        await _advance(cover, clock, 0.1)
        assert cover.tilt_calc.current_position() == 50
        watermark = len(cover.hass.services.async_call.call_args_list)
        await cover.set_position(target)
        assert cover.travel_calc.current_position() == 45
        assert cover.travel_calc.is_traveling()
        if relays == "same":
            # Already driving that way: the motor is left running.
            assert relay_calls(cover, watermark) == []
        await _to_completion(cover, clock)
    assert cover.travel_calc.current_position() == target
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_endpoint_move_mid_slat_move_starts_from_shifted_position(
    make_cover, clock
):
    cover = _inline(make_cover)
    _at(cover, 50, 0)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(100)
        await _advance(cover, clock, 0.1)
        assert cover.tilt_calc.current_position() == 50
        # The endpoint funnel itself: async_open_cover would just stop here.
        await cover._async_move_to_endpoint(target=100)
        assert cover.travel_calc.current_position() == 55
        assert cover.travel_calc.is_traveling()
        await _to_completion(cover, clock)
    assert cover.travel_calc.current_position() == 100
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_stop_during_startup_delay_shifts_nothing(make_cover, clock):
    cover = _inline(make_cover, tilt_startup_delay=1.0)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        await cover.async_stop_cover_tilt()
        assert cover.travel_calc.current_position() == 50
        # A later tracker-only tilt move (as calibration runs) must not pick
        # up the abandoned slat move.
        cover.tilt_calc.start_travel(0)
        clock.advance(0.1)
        cover.tilt_calc.stop()
    assert cover.travel_calc.current_position() == 50
    await _cancel_tasks(cover)


@pytest.mark.parametrize("supersede", [True, False])
@pytest.mark.asyncio
async def test_declared_tilt_drops_the_pending_shift(make_cover, clock, supersede):
    cover = _inline(make_cover)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        await cover.set_known_tilt_position(tilt_position=30, supersede=supersede)
        cover.tilt_calc.start_travel(0)
        clock.advance(0.1)
        cover.tilt_calc.stop()
    assert cover.travel_calc.current_position() == 50
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_tilt_restore_after_cover_move_does_not_shift(make_cover, clock):
    cover = _inline(make_cover)
    _at(cover, 50, 50)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(30)
        await _to_completion(cover, clock)
        await _to_completion(cover, clock)
    assert cover.travel_calc.current_position() == 30
    assert cover.tilt_calc.current_position() == 50
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_toggle_mode_slat_move(make_cover, clock):
    cover = _inline(make_cover, control_mode="toggle")
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        await _to_completion(cover, clock)
    assert relay_calls(cover) == TOGGLE_SLAT_CLOSE_CALLS
    assert cover.travel_calc.current_position() == 40
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_sequential_slat_move_unchanged(make_cover, clock):
    cover = make_cover(
        control_mode="switch", **{**INLINE, "tilt_mode": "sequential_close"}
    )
    stub_switches(cover)
    _at(cover, 0, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        await _to_completion(cover, clock)
    assert cover.travel_calc.current_position() == 0
    assert cover.tilt_calc.current_position() == 0
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_dual_motor_slat_move_unchanged(make_cover, clock):
    cover = make_cover(
        control_mode="switch",
        **{**INLINE, "tilt_mode": "dual_motor"},
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
    )
    stub_switches(cover)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        await _to_completion(cover, clock)
    assert cover.travel_calc.current_position() == 50
    assert cover.tilt_calc.current_position() == 0
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_wrapped_native_tilt_does_not_shift(clock):
    cover = _make_wrapped_cover(
        tilt_time_close=0.2, tilt_time_open=0.2, tilt_mode="inline"
    )
    _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_TILT)
    _stub_updates(cover)
    _at(cover, 50, 100)
    await cover.async_set_cover_tilt_position(tilt_position=0)
    assert cover.tilt_calc.is_traveling()
    clock.advance(0.3)
    await cover.auto_stop_if_necessary()
    assert cover.tilt_calc.current_position() == 0
    assert cover.travel_calc.current_position() == 50
    await _cancel_tasks(cover)


def _held_startup():
    """Hold every startup delay until the returned event is set."""
    release = asyncio.Event()

    async def held(_seconds):
        await release.wait()

    return release, patch("custom_components.cover_time_based.cover_base.sleep", held)


@pytest.mark.parametrize("stop", ["async_stop_cover_tilt", "async_stop_cover"])
@pytest.mark.asyncio
async def test_stop_after_slats_arrive_before_auto_stop_shifts(make_cover, clock, stop):
    cover = _inline(make_cover)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        clock.advance(0.3)
        assert not cover.tilt_calc.is_traveling()
        await getattr(cover, stop)()
    assert cover.tilt_calc.current_position() == 0
    assert cover.travel_calc.current_position() == 40
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_next_slat_move_before_auto_stop_keeps_the_first_turn(make_cover, clock):
    cover = _inline(make_cover)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(50)
        clock.advance(0.15)
        assert not cover.tilt_calc.is_traveling()
        await cover.set_tilt_position(0)
        await _to_completion(cover, clock)
    assert cover.tilt_calc.current_position() == 0
    assert cover.travel_calc.current_position() == 40
    await _cancel_tasks(cover)


@pytest.mark.parametrize("funnel", ["set_position", "endpoint"])
@pytest.mark.asyncio
async def test_travel_request_ignored_in_slat_startup_keeps_the_shift(
    make_cover, clock, funnel
):
    cover = _inline(make_cover, tilt_startup_delay=1.0)
    _at(cover, 50, 100)
    release, held = _held_startup()
    with patch.object(cover, "async_write_ha_state"), held:
        await cover.set_tilt_position(0)
        if funnel == "set_position":
            assert await cover.set_position(20) is False
        else:
            await cover._async_move_to_endpoint(target=0)
        assert not cover.travel_calc.is_traveling()
        release.set()
        await _flush()
        assert cover.tilt_calc.is_traveling()
        await _to_completion(cover, clock)
    assert cover.tilt_calc.current_position() == 0
    assert cover.travel_calc.current_position() == 40
    await _cancel_tasks(cover)


@pytest.mark.parametrize(
    ("target", "extra"), [(45, {}), (44, {"min_movement_time": 1.0})]
)
@pytest.mark.asyncio
async def test_travel_request_ignored_mid_slat_move_keeps_the_shift(
    make_cover, clock, target, extra
):
    cover = _inline(make_cover, **extra)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        await _advance(cover, clock, 0.1)
        assert cover.tilt_calc.current_position() == 50
        await cover.set_position(target)
        assert cover.travel_calc.current_position() == 50
        assert cover.tilt_calc.is_traveling()
        await _to_completion(cover, clock)
    assert cover.tilt_calc.current_position() == 0
    assert cover.travel_calc.current_position() == 40
    await _cancel_tasks(cover)


@pytest.mark.parametrize("ignored_first", [False, True])
@pytest.mark.parametrize("target", [80, 20])
@pytest.mark.asyncio
async def test_slat_pre_step_and_restore_after_takeover_do_not_shift(
    make_cover, clock, target, ignored_first
):
    cover = _inline(make_cover)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"), _no_settle():
        await cover.set_tilt_position(0)
        await _advance(cover, clock, 0.1)
        if ignored_first:
            await cover.set_position(45)
            await _advance(cover, clock, 0.02)
        assert await cover.set_position(target)
        assert cover.travel_calc.current_position() == (44 if ignored_first else 45)
        await _to_completion(cover, clock)
        await _to_completion(cover, clock)
        await _to_completion(cover, clock)
    assert cover.travel_calc.current_position() == target
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_repeated_ignored_requests_shift_once_by_the_whole_turn(
    make_cover, clock
):
    cover = _inline(make_cover, min_movement_time=1.0)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        while cover.tilt_calc.is_traveling():
            clock.advance(0.01)
            # Same direction and too short to run: ignored every time.
            await cover.set_position(40)
            assert not cover.travel_calc.is_traveling()
            assert cover.travel_calc.current_position() == 50
        await _to_completion(cover, clock)
    assert cover.tilt_calc.current_position() == 0
    assert cover.travel_calc.current_position() == 40
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_ignored_request_does_not_round_the_shift_twice(make_cover, clock):
    cover = _inline(
        make_cover,
        travel_time_close=30.0,
        travel_time_open=30.0,
        tilt_time_close=1.5,
        tilt_time_open=1.5,
    )
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        await _advance(cover, clock, 0.75)
        assert cover.tilt_calc.current_position() == 50
        await cover.set_position(48)
        assert cover.tilt_calc.is_traveling()
        await _to_completion(cover, clock)
    assert cover.tilt_calc.current_position() == 0
    assert cover.travel_calc.current_position() == 45
    await _cancel_tasks(cover)


def _slat_close_calls(control_mode):
    if control_mode == "toggle":
        return TOGGLE_SLAT_CLOSE_CALLS
    return SWITCH_SLAT_CLOSE_CALLS


@pytest.mark.parametrize("control_mode", ["switch", "toggle"])
@pytest.mark.parametrize("start", [6, 0])
@pytest.mark.parametrize("ignored", [False, True])
@pytest.mark.asyncio
async def test_ignored_request_keeps_the_slat_move_stop(
    make_cover, clock, control_mode, start, ignored
):
    cover = _inline(make_cover, control_mode=control_mode, endpoint_runon_time=2.0)
    _at(cover, start, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        await _advance(cover, clock, 0.1)
        if ignored:
            # Where the slats have taken the cover so far: a no-op.
            await cover.set_position(max(0, start - 5))
            assert not cover.travel_calc.is_traveling()
        await _to_completion(cover, clock)
    assert cover.travel_calc.current_position() == 0
    assert relay_calls(cover) == _slat_close_calls(control_mode)
    assert cover._delay_task is None or cover._delay_task.done()
    await _cancel_tasks(cover)


@pytest.mark.parametrize("control_mode", ["switch", "toggle"])
@pytest.mark.parametrize("start", [6, 0])
@pytest.mark.asyncio
async def test_endpoint_request_in_slat_startup_keeps_the_slat_move_stop(
    make_cover, clock, control_mode, start
):
    cover = _inline(
        make_cover,
        control_mode=control_mode,
        endpoint_runon_time=2.0,
        tilt_startup_delay=1.0,
    )
    _at(cover, start, 100)
    release, held = _held_startup()
    with patch.object(cover, "async_write_ha_state"), held:
        await cover.set_tilt_position(0)
        await cover._async_move_to_endpoint(target=0)
        assert not cover.travel_calc.is_traveling()
        release.set()
        await _flush()
        await _to_completion(cover, clock)
    assert cover.travel_calc.current_position() == 0
    assert relay_calls(cover) == _slat_close_calls(control_mode)
    assert cover._delay_task is None or cover._delay_task.done()
    await _cancel_tasks(cover)


@pytest.mark.parametrize("funnel", ["set_position", "endpoint"])
@pytest.mark.asyncio
async def test_travel_taking_over_a_slat_move_gets_the_endpoint_runon(
    make_cover, clock, funnel
):
    cover = _inline(make_cover, endpoint_runon_time=2.0)
    _at(cover, 50, 100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(0)
        await _advance(cover, clock, 0.1)
        if funnel == "set_position":
            assert await cover.set_position(0)
        else:
            await cover._async_move_to_endpoint(target=0)
        assert cover.travel_calc.is_traveling()
        await _to_completion(cover, clock)
    assert cover.travel_calc.current_position() == 0
    assert cover._delay_task is not None and not cover._delay_task.done()
    await _cancel_tasks(cover)
