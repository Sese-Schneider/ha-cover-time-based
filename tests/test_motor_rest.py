"""Covers the moves that reach the motor without a reversal's own settle:
after any travel-motor stop (stop button, wall switch, end of travel, a run-on
cut short, calibration), a newer command during a reversal's settle, a parked
start cancelled for the other direction, and a recalibrating move or forced
re-drive.
"""

import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import SERVICE_STOP_COVER

from custom_components.cover_time_based import (
    cover_base,
    cover_calibration,
    cover_lifecycle,
    travel_calculator,
)
from custom_components.cover_time_based.calibration import CALIBRATION_STEP_PAUSE
from custom_components.cover_time_based.const import DIRECTION_CHANGE_DELAY
from tests.helpers import FakeClock, relay_calls, stub_switches
from tests.test_cover_wrapped import (
    _F_CLOSE,
    _F_OPEN,
    _F_SET_POSITION,
    _F_SET_TILT,
    _F_STOP,
    _set_wrapped_features,
)
from tests.test_relay_feedback import _echo_event

_OPEN_ON = ("turn_on", "switch.open")
_CLOSE_ON = ("turn_on", "switch.close")


class _GatedSleep:
    """Park every cover_base sleep until released and record what it asked for.

    Each sleep gets its own gate, so cancelling one (a parked start) leaves the
    others parked. Tasks started through ``spawn`` are collected at teardown.
    """

    def __init__(self):
        self.slept = []
        self.tasks = []
        self._gates = []
        self._sleeping = set()
        self._sleeps_by_task = {}
        self._changed = asyncio.Event()

    async def __call__(self, seconds):
        self.slept.append(seconds)
        task = asyncio.current_task()
        self._sleeps_by_task.setdefault(task, []).append(seconds)
        gate = asyncio.get_running_loop().create_future()
        self._gates.append((task, gate))
        self._sleeping.add(task)
        self._changed.set()
        try:
            await gate
        finally:
            self._sleeping.discard(task)

    def spawn(self, coro):
        task = asyncio.ensure_future(coro)
        self.tasks.append(task)
        return task

    async def until_parked(self, task):
        """Wait until ``task`` is waiting in a sleep, or has finished."""
        await self._wait(task, lambda: task in self._sleeping)

    async def until_next_sleep(self, task):
        """Wait until ``task`` starts another sleep, or has finished; return
        what it asked for."""
        sleeps = self._sleeps_by_task.setdefault(task, [])
        count = len(sleeps)
        await self._wait(task, lambda: len(sleeps) > count)
        return sleeps[-1] if len(sleeps) > count else None

    async def _wait(self, task, reached):
        while not reached() and not task.done():
            self._changed.clear()
            changed = asyncio.ensure_future(self._changed.wait())
            await asyncio.wait({changed, task}, return_when=asyncio.FIRST_COMPLETED)
            changed.cancel()
            with suppress(asyncio.CancelledError):
                await changed

    def release(self, task=None):
        """Let every parked sleep go on, or only ``task``'s."""
        for owner, gate in self._gates:
            if (task is None or owner is task) and not gate.done():
                gate.set_result(None)
        self._gates = [(o, g) for o, g in self._gates if not g.done()]

    async def close(self):
        self.release()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


@pytest.fixture
def clock():
    clock = FakeClock()
    with (
        patch.object(cover_base, "time", clock),
        patch.object(travel_calculator, "time", clock),
    ):
        yield clock


@pytest.fixture
async def gated_sleep():
    gate = _GatedSleep()
    with patch.object(cover_base, "sleep", gate):
        try:
            yield gate
        finally:
            await gate.close()


def _cover(make_cover, **kwargs):
    cover = make_cover(**kwargs)
    stub_switches(cover)
    cover.async_write_ha_state = lambda: None
    return cover


def _mark(cover):
    return len(cover.hass.services.async_call.call_args_list)


async def _drives_before_resting(cover, gated_sleep, move):
    """Start ``move``, return the relay calls it made before resting, then let
    it finish."""
    mark = _mark(cover)
    task = gated_sleep.spawn(move)
    await gated_sleep.until_parked(task)
    calls = relay_calls(cover, mark)
    gated_sleep.release()
    await task
    return calls


async def _rests_then_drives(cover, gated_sleep, move, drive, rest=None):
    """Start ``move``: it waits out ``rest`` (the whole settle gap by default)
    without driving, then sends ``drive`` once the wait ends."""
    mark = _mark(cover)
    task = gated_sleep.spawn(move)
    await gated_sleep.until_parked(task)
    assert drive not in relay_calls(cover, mark), "drove without resting"
    expected = DIRECTION_CHANGE_DELAY if rest is None else rest
    assert gated_sleep.slept == [pytest.approx(expected)]
    gated_sleep.release()
    await task
    assert drive in relay_calls(cover, mark), "never drove after the rest"


async def _wall_switch(cover, entity, old, new):
    """The relay changes state with no command of ours behind it."""
    for pending in list(cover._pending_switch):
        cover._clear_pending_switch(pending)
    await cover._async_switch_state_changed(_echo_event(entity, old, new))


async def _closing_then_stopped(make_cover, clock, **kwargs):
    cover = _cover(make_cover, **kwargs)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)
    await cover.async_stop_cover()
    return cover


# ---------------------------------------------------------------------------
# A newer command during a reversal's settle gap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_newer_target_during_settle_waits_out_the_rest(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.set_position(0)
    clock.advance(2)

    first = gated_sleep.spawn(cover.set_position(80))
    await gated_sleep.until_parked(first)
    mark = _mark(cover)
    second = gated_sleep.spawn(cover.set_position(90))
    await gated_sleep.until_parked(second)

    assert _OPEN_ON not in relay_calls(cover, mark), "drove inside the settle gap"

    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await asyncio.gather(first, second)

    assert relay_calls(cover, mark)[-1] == _OPEN_ON
    assert cover.travel_calc._travel_to_position == 90


# ---------------------------------------------------------------------------
# A stop followed at once by the other direction
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

    opening = gated_sleep.spawn(cover.async_open_cover())
    await gated_sleep.until_parked(opening)

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

    moving = gated_sleep.spawn(cover.set_position(90))
    await gated_sleep.until_parked(moving)

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
async def test_the_rest_waits_through_the_settle_hook(make_cover, clock):
    """Tests that no-op the settle gap no-op the rest with it."""
    cover = await _closing_then_stopped(make_cover, clock)
    clock.advance(0.25)

    with patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle:
        await cover.async_open_cover()

    settle.assert_awaited_once_with(pytest.approx(DIRECTION_CHANGE_DELAY - 0.25))
    assert cover.travel_calc.is_opening()


@pytest.mark.asyncio
async def test_a_stop_during_the_rest_cancels_the_move(make_cover, clock, gated_sleep):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)
    await cover.async_stop_cover()
    mark = _mark(cover)

    opening = gated_sleep.spawn(cover.async_open_cover())
    await gated_sleep.until_parked(opening)
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

    reversing = gated_sleep.spawn(cover.set_position(80))
    await gated_sleep.until_parked(reversing)
    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await reversing

    assert gated_sleep.slept == [DIRECTION_CHANGE_DELAY]
    assert relay_calls(cover)[-1] == _OPEN_ON


@pytest.mark.parametrize("stop_path", ["stop button", "internal stop"])
@pytest.mark.asyncio
async def test_the_rest_runs_from_when_the_stop_went_out(
    make_cover, clock, gated_sleep, stop_path
):
    """A relay that takes 0.6s to accept the stop: that time is not rest."""
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)

    async def slow_turn_off(domain, service, data, *args):
        if service == "turn_off" and data["entity_id"] == "switch.close":
            clock.advance(0.6)

    cover.hass.services.async_call.side_effect = slow_turn_off
    if stop_path == "stop button":
        await cover.async_stop_cover()
    else:
        cover.travel_calc.stop()
        await cover._async_handle_command(SERVICE_STOP_COVER)
    cover.hass.services.async_call.side_effect = None

    calls = await _drives_before_resting(cover, gated_sleep, cover.async_open_cover())

    assert _OPEN_ON not in calls
    assert gated_sleep.slept == [pytest.approx(DIRECTION_CHANGE_DELAY)]


@pytest.mark.asyncio
async def test_a_suppressed_idle_stop_does_not_restart_the_rest(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover, control_mode="pulse", stop_switch="switch.stop")
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    await cover.async_stop_cover()
    cover._skip_stop_when_idle = True
    clock.advance(2)

    await cover.async_stop_cover()
    await cover.async_open_cover()

    assert gated_sleep.slept == []


# ---------------------------------------------------------------------------
# Every stop of the travel motor starts the rest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "entity", "old", "new"),
    [
        ("switch", "switch.close", "on", "off"),
        ("toggle", "switch.close", "off", "on"),
        ("toggle_opposite", "switch.open", "off", "on"),
        ("pulse", "switch.stop", "off", "on"),
    ],
)
@pytest.mark.asyncio
async def test_open_straight_after_a_wall_switch_stop_waits_out_the_rest(
    make_cover, clock, gated_sleep, mode, entity, old, new
):
    cover = _cover(make_cover, control_mode=mode, stop_switch="switch.stop")
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)
    for pending in list(cover._pending_switch):
        cover._clear_pending_switch(pending)
    await cover._async_switch_state_changed(_echo_event(entity, old, new))
    assert not cover.travel_calc.is_traveling()

    calls = await _drives_before_resting(cover, gated_sleep, cover.async_open_cover())

    assert _OPEN_ON not in calls, "drove straight after the wall switch stopped it"
    assert gated_sleep.slept == [pytest.approx(DIRECTION_CHANGE_DELAY)]


@pytest.mark.parametrize("mode", ["switch", "toggle", "toggle_opposite", "pulse"])
@pytest.mark.asyncio
async def test_open_straight_after_reaching_the_bottom_waits_out_the_rest(
    make_cover, clock, gated_sleep, mode
):
    cover = _cover(
        make_cover,
        control_mode=mode,
        stop_switch="switch.stop",
        endpoint_runon_time=0,
        travel_time_close=10,
    )
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(6)
    await cover.auto_stop_if_necessary()
    assert cover.travel_calc.current_position() == 0

    await _rests_then_drives(cover, gated_sleep, cover.async_open_cover(), _OPEN_ON)


@pytest.mark.asyncio
async def test_open_during_the_endpoint_run_on_waits_out_the_rest(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover, endpoint_runon_time=2, travel_time_close=10)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(6)
    await cover.auto_stop_if_necessary()
    assert cover._delay_task is not None
    mark = _mark(cover)

    await _rests_then_drives(cover, gated_sleep, cover.async_open_cover(), _OPEN_ON)

    assert relay_calls(cover, mark)[0] == ("turn_off", "switch.close")


@pytest.mark.asyncio
async def test_set_position_straight_after_a_calibration_stop_waits_out_the_rest(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover._raw_direction_command("close")
    await cover._raw_direction_command("stop")

    await _rests_then_drives(cover, gated_sleep, cover.set_position(90), _OPEN_ON)


@pytest.mark.asyncio
async def test_a_calibration_stop_replaces_an_older_stop(
    make_cover, clock, gated_sleep
):
    """The motor last stopped going up, so a move up need not wait."""
    cover = await _closing_then_stopped(make_cover, clock)
    await cover._raw_direction_command("open")
    await cover._raw_direction_command("stop")

    calls = await _drives_before_resting(cover, gated_sleep, cover.set_position(90))

    assert gated_sleep.slept == []
    assert _OPEN_ON in calls


@pytest.mark.asyncio
async def test_a_wall_switch_drive_ends_the_rest_of_an_earlier_stop(
    make_cover, clock, gated_sleep
):
    """The motor already runs up, so a recalibrating move up rides it at once."""
    cover = await _closing_then_stopped(
        make_cover, clock, recalibrate_before_position=True
    )
    for pending in list(cover._pending_switch):
        cover._clear_pending_switch(pending)
    await cover._async_switch_state_changed(_echo_event("switch.open", "off", "on"))
    assert cover.travel_calc.is_opening()

    task = gated_sleep.spawn(cover.set_position(80))
    await gated_sleep.until_parked(task)

    assert gated_sleep.slept == []
    assert await task is True


@pytest.mark.asyncio
async def test_open_straight_after_a_wall_switch_close_ends_waits_out_the_rest(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover, travel_time_close=10)
    cover.travel_calc.set_position(60)
    await _wall_switch(cover, "switch.close", "off", "on")
    assert cover.travel_calc.is_closing()
    clock.advance(10)
    await cover.auto_stop_if_necessary()
    assert cover.travel_calc.current_position() == 0

    await _rests_then_drives(cover, gated_sleep, cover.async_open_cover(), _OPEN_ON)


@pytest.mark.asyncio
async def test_open_straight_after_a_wall_switch_cancels_a_parked_close_waits(
    make_cover, clock, gated_sleep
):
    """The wall switch stops the energised close relay; HA sends nothing."""
    cover = _cover(make_cover, travel_startup_delay=20)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    await gated_sleep.until_parked(cover._startup_delay_task)
    await _wall_switch(cover, "switch.open", "off", "on")
    assert cover._startup_delay_task is None
    gated_sleep.slept.clear()

    await _rests_then_drives(cover, gated_sleep, cover.async_open_cover(), _OPEN_ON)


@pytest.mark.asyncio
async def test_close_straight_after_an_open_resync_at_the_top_waits_out_the_rest(
    make_cover, clock, gated_sleep
):
    """A toggle cover re-pulsed open at 100% runs into its limit and stops."""
    cover = _cover(make_cover, control_mode="toggle")
    cover.travel_calc.set_position(100)
    mark = _mark(cover)
    await cover.async_open_cover()
    assert _OPEN_ON in relay_calls(cover, mark)

    await _rests_then_drives(cover, gated_sleep, cover.async_close_cover(), _CLOSE_ON)


@pytest.mark.asyncio
async def test_open_straight_after_reaching_the_bottom_before_a_tilt_restore_waits(
    make_cover, clock, gated_sleep
):
    """Dual-motor: the travel motor stops itself at 0% before the slats turn."""
    cover = _cover(
        make_cover,
        control_mode="toggle",
        tilt_mode="dual_motor",
        tilt_time_close=5,
        tilt_time_open=5,
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        travel_time_close=10,
    )
    cover.travel_calc.set_position(60)
    cover.tilt_calc.set_position(100)
    await cover.async_close_cover()
    clock.advance(10)
    await cover.auto_stop_if_necessary()
    assert cover.travel_calc.current_position() == 0

    await _rests_then_drives(cover, gated_sleep, cover.async_open_cover(), _OPEN_ON)


@pytest.mark.asyncio
async def test_an_open_during_a_calibration_reversals_settle_waits_too(
    make_cover, clock, gated_sleep
):
    """Toggle calibration: an open after a close first taps a stop."""
    cover = _cover(make_cover, control_mode="toggle")
    cover.travel_calc.set_position(60)
    await cover._raw_direction_command("close")
    raw_open = gated_sleep.spawn(cover._raw_direction_command("open"))
    await gated_sleep.until_parked(raw_open)
    mark = _mark(cover)

    opening = gated_sleep.spawn(cover.async_open_cover())
    await gated_sleep.until_parked(opening)

    assert not opening.done(), "drove during the calibration's settle"
    assert _OPEN_ON not in relay_calls(cover, mark)


@pytest.mark.asyncio
async def test_open_straight_after_stopping_a_travel_calibration_waits(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.start_calibration(attribute="travel_time_close", timeout=120.0)
    await cover.stop_calibration()

    await _rests_then_drives(cover, gated_sleep, cover.async_open_cover(), _OPEN_ON)


@pytest.mark.asyncio
async def test_a_calibration_ended_at_the_limit_leaves_no_direction_for_an_idle_stop(
    make_cover, clock, gated_sleep
):
    """Pulse hardware stops itself at the limit, so ending the calibration
    sends nothing; a stop pressed later on the idle cover is no reason to wait."""
    cover = _cover(
        make_cover,
        control_mode="pulse",
        stop_switch="switch.stop",
        send_endpoint_stop=False,
    )
    assert cover._self_stops_at_endpoints()
    cover.travel_calc.set_position(60)
    await cover.start_calibration(attribute="travel_time_close", timeout=120.0)
    await cover.stop_calibration()
    clock.advance(2)
    await cover.async_stop_cover()

    calls = await _drives_before_resting(cover, gated_sleep, cover.async_open_cover())

    assert gated_sleep.slept == []
    assert _OPEN_ON in calls


@pytest.mark.asyncio
async def test_open_straight_after_a_calibration_times_out_at_the_limit_waits(
    make_cover, clock, gated_sleep
):
    """Pulse hardware stops itself at the limit, so the timeout sends nothing."""
    cover = _cover(
        make_cover,
        control_mode="pulse",
        stop_switch="switch.stop",
        send_endpoint_stop=False,
    )
    cover.travel_calc.set_position(60)
    calibration_sleep = _GatedSleep()
    with patch.object(cover_calibration, "sleep", calibration_sleep):
        try:
            await cover.start_calibration(attribute="travel_time_close", timeout=120.0)
            timing_out = cover._calibration.timeout_task
            await calibration_sleep.until_parked(timing_out)
            calibration_sleep.release(timing_out)
            await timing_out
        finally:
            await calibration_sleep.close()
    assert cover._calibration is None

    await _rests_then_drives(cover, gated_sleep, cover.async_open_cover(), _OPEN_ON)


@pytest.mark.asyncio
async def test_the_rest_after_a_minimum_movement_pulse_runs_from_its_stop(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    calibration_sleep = _GatedSleep()
    with patch.object(cover_calibration, "sleep", calibration_sleep):
        try:
            await cover.start_calibration(
                attribute="min_movement_time", timeout=120.0, direction="close"
            )
            pulsing = cover._calibration.automation_task
            await calibration_sleep.until_parked(pulsing)  # the initial pause
            calibration_sleep.release(pulsing)
            await calibration_sleep.until_next_sleep(pulsing)  # the pulse
            calibration_sleep.release(pulsing)
            pause = await calibration_sleep.until_next_sleep(pulsing)
            assert pause == CALIBRATION_STEP_PAUSE
            clock.advance(0.6)
            await cover.stop_calibration()
        finally:
            await calibration_sleep.close()

    await _rests_then_drives(
        cover, gated_sleep, cover.async_open_cover(), _OPEN_ON, rest=0.4
    )


def _wrapped(make_cover, features, **kwargs):
    cover = _cover(make_cover, cover_entity_id="cover.device", **kwargs)
    _set_wrapped_features(cover, features, state="open", current_position=60)
    cover.travel_calc.set_position(60)
    return cover


@pytest.mark.asyncio
async def test_open_straight_after_stopping_a_native_position_move_waits(
    make_cover, clock, gated_sleep
):
    cover = _wrapped(make_cover, _F_OPEN | _F_CLOSE | _F_STOP | _F_SET_POSITION)
    await cover.set_position(30)
    clock.advance(1)
    await cover.async_stop_cover()

    await _rests_then_drives(
        cover, gated_sleep, cover.async_open_cover(), ("open_cover", "cover.device")
    )


@pytest.mark.asyncio
async def test_open_straight_after_a_native_position_move_arrives_waits(
    make_cover, clock, gated_sleep
):
    cover = _wrapped(make_cover, _F_OPEN | _F_CLOSE | _F_STOP | _F_SET_POSITION)
    await cover.set_position(30)
    clock.advance(60)
    await cover.auto_stop_if_necessary()
    assert cover.travel_calc.current_position() == 30

    await _rests_then_drives(
        cover, gated_sleep, cover.async_open_cover(), ("open_cover", "cover.device")
    )


async def _wrapped_reports(cover, state, position):
    _set_wrapped_features(
        cover, _F_OPEN | _F_CLOSE | _F_STOP, state=state, current_position=position
    )
    cover._last_self_command_time = None  # past the bounce grace window
    await cover._handle_external_state_change("cover.device", "closing", state)


@pytest.mark.parametrize(
    ("state", "position"),
    [("open", 40), ("closed", 0)],
    ids=["stopped-mid-travel", "closed-before-the-timer"],
)
@pytest.mark.asyncio
async def test_open_straight_after_the_wrapped_cover_reports_stopping_waits(
    make_cover, clock, gated_sleep, state, position
):
    cover = _wrapped(make_cover, _F_OPEN | _F_CLOSE | _F_STOP)
    await cover.async_close_cover()
    clock.advance(2)
    await _wrapped_reports(cover, state, position)
    assert cover.travel_calc.current_position() == position
    assert not cover.travel_calc.is_traveling()

    await _rests_then_drives(
        cover, gated_sleep, cover.async_open_cover(), ("open_cover", "cover.device")
    )


@pytest.mark.asyncio
async def test_a_reported_stop_leaves_no_direction_for_a_later_idle_stop(
    make_cover, clock, gated_sleep
):
    cover = _wrapped(make_cover, _F_OPEN | _F_CLOSE | _F_STOP)
    await cover.async_close_cover()
    clock.advance(2)
    await _wrapped_reports(cover, "open", 40)
    clock.advance(2)
    await cover.async_stop_cover()

    calls = await _drives_before_resting(cover, gated_sleep, cover.async_open_cover())

    assert gated_sleep.slept == []
    assert ("open_cover", "cover.device") in calls


@pytest.mark.asyncio
async def test_open_straight_after_a_native_tilt_stopped_travel_waits_out_the_rest(
    make_cover, clock, gated_sleep
):
    cover = _cover(
        make_cover,
        cover_entity_id="cover.device",
        tilt_time_close=5,
        tilt_time_open=5,
        tilt_mode="inline",
    )
    _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_TILT)
    cover.travel_calc.set_position(60)
    cover.tilt_calc.set_position(100)
    await cover.async_close_cover()
    clock.advance(2)
    mark = _mark(cover)
    await cover.async_set_cover_tilt_position(tilt_position=30)
    assert ("stop_cover", "cover.device") in relay_calls(cover, mark)
    cover.tilt_calc.set_position(30)

    await _rests_then_drives(
        cover, gated_sleep, cover.async_open_cover(), ("open_cover", "cover.device")
    )


# ---------------------------------------------------------------------------
# A recalibrating move resting before its drive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_stop_during_a_recalibrating_moves_rest_cancels_it(
    make_cover, clock, gated_sleep
):
    cover = await _closing_then_stopped(
        make_cover, clock, recalibrate_before_position=True
    )
    stopped_at = cover.travel_calc.current_position()
    moving = gated_sleep.spawn(cover.set_position(40))
    await gated_sleep.until_parked(moving)
    assert not moving.done(), "the recalibrating move did not rest"

    await cover.async_stop_cover()
    mark = _mark(cover)
    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()

    assert await moving is False
    calls = relay_calls(cover, mark)
    assert _OPEN_ON not in calls and _CLOSE_ON not in calls, "the move drove anyway"
    assert not cover.travel_calc.is_traveling()
    assert cover.travel_calc.current_position() == stopped_at


@pytest.mark.asyncio
async def test_the_newest_of_two_recalibrating_moves_in_one_rest_wins(
    make_cover, clock, gated_sleep
):
    cover = await _closing_then_stopped(
        make_cover, clock, recalibrate_before_position=True
    )
    first = gated_sleep.spawn(cover.set_position(40))
    await gated_sleep.until_parked(first)
    clock.advance(0.3)
    second = gated_sleep.spawn(cover.set_position(70))
    await gated_sleep.until_parked(second)
    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()

    assert await asyncio.gather(first, second) == [False, True]
    assert cover._pending_recalibrated_target == 70


@pytest.mark.asyncio
async def test_a_known_position_during_a_recalibrating_moves_rest_stands(
    make_cover, clock, gated_sleep
):
    cover = await _closing_then_stopped(
        make_cover, clock, recalibrate_before_position=True
    )
    moving = gated_sleep.spawn(cover.set_position(40))
    await gated_sleep.until_parked(moving)
    assert not moving.done(), "the recalibrating move did not rest"

    await cover.set_known_position(position=75)
    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await moving

    assert cover.travel_calc.current_position() == 75
    assert not cover.travel_calc.is_traveling()


@pytest.mark.asyncio
async def test_a_stop_during_a_recalibrating_moves_rest_after_a_run_on_cancels_it(
    make_cover, clock, gated_sleep
):
    cover = _cover(
        make_cover,
        endpoint_runon_time=2,
        travel_time_close=10,
        recalibrate_before_position=True,
    )
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(6)
    await cover.auto_stop_if_necessary()
    assert cover._delay_task is not None

    moving = gated_sleep.spawn(cover.set_position(40))
    await gated_sleep.until_parked(moving)
    assert not moving.done(), "the recalibrating move did not rest"
    await cover.async_stop_cover()
    mark = _mark(cover)
    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()

    assert await moving is False
    assert _OPEN_ON not in relay_calls(cover, mark), "the move drove anyway"
    assert cover.travel_calc.current_position() == 0


@pytest.mark.parametrize(
    ("endpoint", "leave", "redrive", "drive_on"),
    [
        (100, "async_close_cover", "async_open_cover", _OPEN_ON),
        (0, "async_open_cover", "async_close_cover", _CLOSE_ON),
    ],
    ids=["open", "close"],
)
@pytest.mark.asyncio
async def test_a_forced_redrive_rests_before_seeding_the_full_travel(
    make_cover, clock, gated_sleep, endpoint, leave, redrive, drive_on
):
    """The re-drive models a start from the other end; resting after that
    would show that end for the whole rest, and a stop in it would read as a
    re-drive that never started."""
    cover = _cover(make_cover, force_endpoint_redrive=True)
    cover.travel_calc.set_position(endpoint)
    await getattr(cover, leave)()
    clock.advance(0.05)
    await cover.async_stop_cover()
    assert cover.travel_calc.current_position() == endpoint

    moving = gated_sleep.spawn(getattr(cover, redrive)())
    await gated_sleep.until_parked(moving)
    assert not moving.done(), "the forced re-drive did not rest"
    assert cover.travel_calc.current_position() == endpoint

    await cover.async_stop_cover()
    mark = _mark(cover)
    gated_sleep.release()
    await moving

    assert drive_on not in relay_calls(cover, mark)
    assert cover.travel_calc.current_position() == endpoint


@pytest.mark.asyncio
async def test_a_recalibrating_move_after_a_stop_rests_once(
    make_cover, clock, gated_sleep
):
    cover = await _closing_then_stopped(
        make_cover, clock, recalibrate_before_position=True
    )
    mark = _mark(cover)

    moving = gated_sleep.spawn(cover.set_position(40))
    await gated_sleep.until_parked(moving)
    assert _OPEN_ON not in relay_calls(cover, mark)
    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await moving

    assert gated_sleep.slept == [DIRECTION_CHANGE_DELAY]
    assert relay_calls(cover, mark)[-1] == _OPEN_ON


# ---------------------------------------------------------------------------
# Set position against a start still parked the other way
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_position_against_a_parked_start_rests_before_driving(
    make_cover, clock, gated_sleep
):
    cover = _cover(make_cover, travel_startup_delay=20)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    assert cover._startup_delay_task is not None
    await gated_sleep.until_parked(cover._startup_delay_task)
    mark = _mark(cover)

    moving = gated_sleep.spawn(cover.set_position(90))
    await gated_sleep.until_parked(moving)

    calls = relay_calls(cover, mark)
    assert ("turn_off", "switch.close") in calls
    assert _OPEN_ON not in calls, "drove back with no rest"

    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await moving

    assert relay_calls(cover, mark)[-1] == _OPEN_ON


# ---------------------------------------------------------------------------
# Set position to where the cover has only just left
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

    moving = gated_sleep.spawn(cover.set_position(target))
    await gated_sleep.until_parked(moving)
    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await moving

    assert running in relay_calls(cover, mark)
    assert not cover.travel_calc.is_traveling()
    assert cover.travel_calc.current_position() == target


@pytest.mark.asyncio
async def test_set_position_to_where_a_move_from_unknown_is_seeded_is_not_done(
    make_cover,
):
    """A move from an unknown position seeds the tracker at 0% before it
    starts; a set position of 0% meanwhile has not been served."""
    cover = _cover(make_cover)
    assert cover.travel_calc.current_position() is None
    gate = asyncio.get_running_loop().create_future()
    held = asyncio.Event()
    drive = cover._command_position_move

    async def held_drive(target, command, already_moving_same_dir):
        held.set()
        await gate
        await drive(target, command, already_moving_same_dir)

    with patch.object(cover, "_command_position_move", held_drive):
        first = asyncio.ensure_future(cover.set_position(80))
        try:
            await asyncio.wait_for(held.wait(), 1)
            assert cover.travel_calc.current_position() == 0

            assert await cover.set_position(0) is False
        finally:
            gate.set_result(None)
            await first

    assert cover.travel_calc._travel_to_position == 80


@pytest.mark.parametrize(
    ("target", "drive"),
    [(70, _OPEN_ON), (30, _CLOSE_ON), (100, _OPEN_ON), (0, _CLOSE_ON)],
    ids=["70", "30", "100", "0"],
)
@pytest.mark.asyncio
async def test_set_position_from_an_unknown_position_drives_the_motor(
    make_cover, target, drive
):
    """With no known position the move is modelled from the opposite end. The
    tracker used to read as already moving that way, so no relay was sent."""
    cover = _cover(make_cover)
    cover.travel_calc.clear_position()

    assert await cover.set_position(target)

    assert relay_calls(cover)[-1] == drive
    assert cover.travel_calc._travel_to_position == target


@pytest.mark.asyncio
async def test_the_rest_runs_from_when_a_slow_stop_finally_goes_out(
    make_cover, clock, gated_sleep
):
    """A move the other way that arrives while the stop is still being sent
    waits for the stop, then rests the full gap from when it went out."""

    async def _yield():
        for _ in range(10):
            await asyncio.sleep(0)

    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)
    stop_gate = asyncio.Event()
    send_stop = cover._send_stop

    async def slow_stop():
        await stop_gate.wait()
        await send_stop()

    with patch.object(cover, "_send_stop", slow_stop):
        stopping = asyncio.ensure_future(cover.async_stop_cover())
        await _yield()
        mark = _mark(cover)
        opening = asyncio.ensure_future(cover.async_open_cover())
        await _yield()

        assert gated_sleep.slept == [], "rested before the stop went out"

        clock.advance(0.6)
        stop_gate.set()
        await stopping
        await _yield()

    assert gated_sleep.slept == [pytest.approx(DIRECTION_CHANGE_DELAY)]
    assert _OPEN_ON not in relay_calls(cover, mark)

    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await opening

    assert relay_calls(cover, mark)[-1] == _OPEN_ON


async def _yield_turns():
    for _ in range(10):
        await asyncio.sleep(0)


def _slow_first_stop(cover, *, fail=False):
    """Hold the first _send_stop until the returned event is set; with
    ``fail`` it then raises instead of sending."""
    gate = asyncio.Event()
    sends = []
    send_stop = cover._send_stop

    async def slow():
        sends.append(None)
        if len(sends) == 1:
            await gate.wait()
            if fail:
                raise RuntimeError("relay unavailable")
        await send_stop()

    return gate, sends, slow


@pytest.mark.asyncio
async def test_a_stop_during_a_recalibrating_reversals_stop_wins(make_cover, clock):
    """Leg A of a recalibrated move reverses a closing cover. A stop pressed
    while leg A's own stop is still being sent must win."""
    cover = _cover(make_cover, recalibrate_before_position=True)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)
    gate, sends, slow = _slow_first_stop(cover)
    with (
        patch.object(cover, "_send_stop", slow),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        moving = asyncio.ensure_future(cover.set_position(30))
        await _yield_turns()
        assert sends, "leg A's stop is being sent"
        await cover.async_stop_cover()
        gate.set()
        assert await moving is False

    assert _OPEN_ON not in relay_calls(cover)
    assert not cover.travel_calc.is_traveling()


@pytest.mark.asyncio
async def test_a_stop_during_a_recalibrating_moves_run_on_stop_wins(make_cover, clock):
    """A recalibrated move cuts a pending endpoint run-on short with a stop. A
    stop pressed while that stop is still being sent must win."""
    cover = _cover(make_cover, recalibrate_before_position=True)
    cover.travel_calc.set_position(0)
    cover._last_command = "close_cover"
    cover._travel_motor_direction = "close_cover"
    run_on = asyncio.ensure_future(asyncio.sleep(100))
    cover._delay_task = run_on
    gate, sends, slow = _slow_first_stop(cover)
    try:
        with (
            patch.object(cover, "_send_stop", slow),
            patch.object(cover, "_direction_change_delay", new=AsyncMock()),
        ):
            moving = asyncio.ensure_future(cover.set_position(50))
            await _yield_turns()
            assert sends, "the run-on stop is being sent"
            await cover.async_stop_cover()
            gate.set()
            assert await moving is False
    finally:
        run_on.cancel()

    assert _OPEN_ON not in relay_calls(cover)


@pytest.mark.asyncio
async def test_a_stop_that_fails_to_send_does_not_release_a_waiting_move(
    make_cover, clock
):
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)
    gate, _sends, slow = _slow_first_stop(cover, fail=True)
    with (
        patch.object(cover, "_send_stop", slow),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        stopping = asyncio.ensure_future(cover.async_stop_cover())
        await _yield_turns()
        mark = _mark(cover)
        opening = asyncio.ensure_future(cover.async_open_cover())
        await _yield_turns()
        gate.set()
        with pytest.raises(RuntimeError):
            await stopping
        await opening

    assert _OPEN_ON not in relay_calls(cover, mark)


@pytest.mark.asyncio
async def test_a_move_waits_for_every_stop_still_being_sent(
    make_cover, clock, gated_sleep
):
    """Two stops can be in flight at once. One finishing first must not let a
    move the other way drive while the other is still being sent."""
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)
    gate, sends, slow = _slow_first_stop(cover)
    with patch.object(cover, "_send_stop", slow):
        first = asyncio.ensure_future(cover.async_stop_cover())
        await _yield_turns()
        await cover.async_stop_cover()
        assert len(sends) == 2, "the second stop went out while the first waits"
        mark = _mark(cover)
        opening = asyncio.ensure_future(cover.async_open_cover())
        await _yield_turns()

        assert gated_sleep.slept == [], "rested before the first stop went out"

        clock.advance(0.6)
        gate.set()
        await first
        await _yield_turns()

    assert gated_sleep.slept == [pytest.approx(DIRECTION_CHANGE_DELAY)]
    assert _OPEN_ON not in relay_calls(cover, mark)
    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await opening
    assert relay_calls(cover, mark)[-1] == _OPEN_ON


@pytest.mark.asyncio
async def test_the_rest_runs_from_a_resent_stop_when_the_run_on_stop_was_cancelled(
    make_cover, clock, gated_sleep
):
    """The endpoint run-on's stop is cut off mid-send by an open, which sends
    the stop again. The rest counts from when that second stop went out, not
    from when the cancelled one started."""
    cover = _cover(make_cover, endpoint_runon_time=2, travel_time_close=10)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(6)
    run_on_sleep = _GatedSleep()
    send_stop = cover._send_stop
    gates = []

    async def slow_stop():
        gate = asyncio.Event()
        gates.append(gate)
        await gate.wait()
        await send_stop()

    with (
        patch.object(cover_lifecycle, "sleep", run_on_sleep),
        patch.object(cover, "_send_stop", slow_stop),
    ):
        try:
            await cover.auto_stop_if_necessary()
            run_on = cover._delay_task
            await run_on_sleep.until_parked(run_on)
            run_on_sleep.release(run_on)
            await _yield_turns()
            assert len(gates) == 1, "the run-on's stop is being sent"

            clock.advance(0.3)
            mark = _mark(cover)
            opening = gated_sleep.spawn(cover.async_open_cover())
            await _yield_turns()
            assert run_on.cancelled()
            assert len(gates) == 2, "the open sends the stop again"

            clock.advance(0.8)
            gates[1].set()
            await gated_sleep.until_parked(opening)
        finally:
            await run_on_sleep.close()

    assert ("turn_off", "switch.close") in relay_calls(cover, mark)
    assert _OPEN_ON not in relay_calls(cover, mark), "drove straight after the stop"
    assert gated_sleep.slept == [pytest.approx(DIRECTION_CHANGE_DELAY)]
    clock.advance(DIRECTION_CHANGE_DELAY)
    gated_sleep.release()
    await opening
    assert relay_calls(cover, mark)[-1] == _OPEN_ON


@pytest.mark.asyncio
async def test_a_late_stop_does_not_count_as_sending_a_newer_one(
    make_cover, clock, gated_sleep
):
    """A stop still being sent when the wall switch drives the motor again
    finishes after a newer stop has been recorded. It must not mark that newer
    stop as gone out: if the newer stop is then cancelled, the stop sent after
    it is the one the rest counts from."""
    cover = _cover(make_cover)
    cover.travel_calc.set_position(60)
    await cover.async_close_cover()
    clock.advance(2)
    send_stop = cover._send_stop
    gates = []

    async def slow_first_two_stops():
        if len(gates) < 2:
            gate = asyncio.Event()
            gates.append(gate)
            await gate.wait()
        await send_stop()

    with patch.object(cover, "_send_stop", slow_first_two_stops):
        older = asyncio.ensure_future(cover.async_stop_cover())
        await _yield_turns()
        await _wall_switch(cover, "switch.open", "off", "on")
        assert cover.travel_calc.is_opening()
        newer = asyncio.ensure_future(cover.async_stop_cover())
        await _yield_turns()
        assert len(gates) == 2, "both stops are being sent"

        clock.advance(0.3)
        gates[0].set()
        await older
        newer.cancel()
        with suppress(asyncio.CancelledError):
            await newer
        clock.advance(0.3)
        await cover.async_stop_cover()
        clock.advance(0.5)

    await _rests_then_drives(
        cover, gated_sleep, cover.async_close_cover(), _CLOSE_ON, rest=0.5
    )
