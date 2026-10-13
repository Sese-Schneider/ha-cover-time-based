"""reverse_on_opposite_command: an in-motion open/close re-targets through
set_position (stop, settle, drive the other way) instead of only stopping.
"""

import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.cover_time_based.cover_single_button_mode import (
    SingleButtonModeCover,
)
from tests.helpers import relay_calls, single_button_sleep_patch, stub_switches


async def _moving(cover, command, start):
    """Put a stubbed cover at ``start`` and start ``command`` for real."""
    stub_switches(cover)
    cover.travel_calc.set_position(start)
    await getattr(cover, command)()
    return len(cover.hass.services.async_call.call_args_list)


@pytest.mark.asyncio
async def test_open_while_closing_reverses(make_cover):
    cover = make_cover(reverse_on_opposite_command=True)
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        mark = await _moving(cover, "async_close_cover", 60)
        await cover.async_open_cover()

    calls = relay_calls(cover, mark)
    assert ("turn_off", "switch.close") in calls
    assert calls[-1] == ("turn_on", "switch.open")
    settle.assert_awaited_once()
    assert cover.travel_calc.is_opening()
    assert cover.travel_calc._travel_to_position == 100


@pytest.mark.asyncio
async def test_close_while_opening_reverses(make_cover):
    cover = make_cover(reverse_on_opposite_command=True)
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        mark = await _moving(cover, "async_open_cover", 40)
        await cover.async_close_cover()

    calls = relay_calls(cover, mark)
    assert ("turn_off", "switch.open") in calls
    assert calls[-1] == ("turn_on", "switch.close")
    settle.assert_awaited_once()
    assert cover.travel_calc.is_closing()
    assert cover.travel_calc._travel_to_position == 0


@pytest.mark.asyncio
async def test_same_direction_command_keeps_moving(make_cover):
    """Re-targeting to the endpoint already headed for continues the move."""
    cover = make_cover(reverse_on_opposite_command=True)
    with patch.object(cover, "async_write_ha_state"):
        mark = await _moving(cover, "async_open_cover", 40)
        await cover.async_open_cover()

    assert relay_calls(cover, mark) == []
    assert cover.travel_calc.is_opening()
    assert cover.travel_calc._travel_to_position == 100


@pytest.mark.asyncio
async def test_option_off_keeps_the_in_motion_stop(make_cover):
    cover = make_cover(reverse_on_opposite_command=False)
    cover.travel_calc.set_position(60)
    cover.travel_calc.start_travel_down()

    with (
        patch.object(cover, "set_position", new_callable=AsyncMock) as set_pos,
        patch.object(cover, "async_stop_cover", new_callable=AsyncMock) as stop,
    ):
        await cover.async_open_cover()

    stop.assert_awaited_once()
    set_pos.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_open_while_closing_is_not_rerouted(make_cover):
    """A wall-switch trigger keeps its own handling; the option is for commands."""
    cover = make_cover(reverse_on_opposite_command=True)
    cover.travel_calc.set_position(60)
    cover.travel_calc.start_travel_down()

    cover._triggered_externally = True
    try:
        with (
            patch.object(cover, "set_position", new_callable=AsyncMock) as set_pos,
            patch.object(cover, "async_stop_cover", new_callable=AsyncMock) as stop,
            patch.object(
                cover, "_settle_before_reversing", AsyncMock(return_value=False)
            ),
        ):
            await cover.async_open_cover()
    finally:
        cover._triggered_externally = False

    set_pos.assert_not_awaited()
    stop.assert_awaited_once_with(supersede=False)


@pytest.mark.asyncio
async def test_reverse_not_applied_with_tilt(make_cover):
    cover = make_cover(
        reverse_on_opposite_command=True,
        tilt_mode="dual_motor",
        tilt_time_close=5,
        tilt_time_open=5,
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
    )
    assert cover._has_tilt_support()
    assert cover._reverses_on_opposite_command() is False


def test_reverse_option_in_state_attributes(make_cover):
    assert (
        make_cover(reverse_on_opposite_command=True).extra_state_attributes[
            "reverse_on_opposite_command"
        ]
        is True
    )
    assert (
        make_cover(reverse_on_opposite_command=False).extra_state_attributes[
            "reverse_on_opposite_command"
        ]
        is False
    )


def test_reverse_is_on_by_default(make_cover):
    assert make_cover().extra_state_attributes["reverse_on_opposite_command"] is True


@pytest.mark.asyncio
async def test_a_cover_without_the_option_set_reverses(make_cover):
    """Existing covers have no stored value and get the new default."""
    cover = make_cover()
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        mark = await _moving(cover, "async_close_cover", 60)
        await cover.async_open_cover()

    calls = relay_calls(cover, mark)
    assert ("turn_off", "switch.close") in calls
    assert calls[-1] == ("turn_on", "switch.open")
    settle.assert_awaited_once()
    assert cover.travel_calc.is_opening()


# ---------------------------------------------------------------------------
# What the relays actually do
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_direction_close_sends_nothing_with_recalibrate_before_position(
    make_cover,
):
    """With "Fully open before moving to a position" on, a repeated close
    must not turn into a stop and a forced full re-drive from 100."""
    cover = make_cover(
        reverse_on_opposite_command=True, recalibrate_before_position=True
    )
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        mark = await _moving(cover, "async_close_cover", 60)
        await cover.async_close_cover()

    assert relay_calls(cover, mark) == []
    settle.assert_not_awaited()
    assert cover.travel_calc.is_closing()
    assert cover.travel_calc._last_known_position == 60


@pytest.mark.asyncio
async def test_opposite_open_reverses_from_the_tracked_position_with_recalibrate_before_position(
    make_cover,
):
    cover = make_cover(
        reverse_on_opposite_command=True, recalibrate_before_position=True
    )
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        mark = await _moving(cover, "async_close_cover", 60)
        await cover.async_open_cover()

    calls = relay_calls(cover, mark)
    assert ("turn_off", "switch.close") in calls
    assert calls[-1] == ("turn_on", "switch.open")
    assert ("turn_on", "switch.close") not in calls
    settle.assert_awaited_once()
    assert cover.travel_calc.is_opening()
    assert cover.travel_calc._last_known_position == 60, (
        "an ordinary reversal, not a forced full open modelled from 0"
    )


@pytest.mark.asyncio
async def test_same_direction_close_sends_nothing_in_toggle_mode_with_recalibrate_before_position(
    make_cover,
):
    """In toggle mode a stray stop pulse or re-drive pulse would move the motor."""
    cover = make_cover(
        control_mode="toggle",
        reverse_on_opposite_command=True,
        recalibrate_before_position=True,
    )
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        mark = await _moving(cover, "async_close_cover", 60)
        await cover.async_close_cover()

    assert relay_calls(cover, mark) == []
    settle.assert_not_awaited()
    assert cover.travel_calc.is_closing()
    assert cover.travel_calc._last_known_position == 60


@pytest.mark.asyncio
async def test_always_resend_does_not_redrive_a_cover_already_closing(make_cover):
    """Since #308 set_position(0) re-drives a cover settled at 0 when "Always
    re-send" is on. A cover still moving is not settled, so nothing is sent."""
    cover = make_cover(reverse_on_opposite_command=True, force_endpoint_redrive=True)
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        mark = await _moving(cover, "async_close_cover", 60)
        await cover.async_close_cover()

    assert relay_calls(cover, mark) == []
    settle.assert_not_awaited()
    assert cover.travel_calc._last_known_position == 60


# ---------------------------------------------------------------------------
# Wrapped and single-button covers
# ---------------------------------------------------------------------------

_F_OPEN_CLOSE_STOP = 1 | 2 | 8
_F_OPEN_CLOSE_SET_POSITION_STOP = 1 | 2 | 4 | 8


def _wrapped(make_cover, features):
    cover = make_cover(cover_entity_id="cover.inner", reverse_on_opposite_command=True)
    st = MagicMock()
    st.state = "open"
    st.attributes = {"supported_features": features}
    cover.hass.states.get = lambda eid: st if eid == "cover.inner" else None
    return cover


@pytest.mark.asyncio
async def test_wrapped_open_while_closing_stops_settles_and_opens(make_cover):
    cover = _wrapped(make_cover, _F_OPEN_CLOSE_STOP)
    cover.travel_calc.set_position(60)
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.async_close_cover()
        mark = len(cover.hass.services.async_call.call_args_list)
        await cover.async_open_cover()

    assert relay_calls(cover, mark) == [
        ("stop_cover", "cover.inner"),
        ("open_cover", "cover.inner"),
    ]
    settle.assert_awaited_once()
    assert cover.travel_calc.is_opening()


@pytest.mark.asyncio
async def test_wrapped_close_while_closing_sends_nothing(make_cover):
    cover = _wrapped(make_cover, _F_OPEN_CLOSE_STOP)
    cover.travel_calc.set_position(60)
    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()
        mark = len(cover.hass.services.async_call.call_args_list)
        await cover.async_close_cover()

    assert relay_calls(cover, mark) == []
    assert cover.travel_calc.is_closing()


@pytest.mark.asyncio
async def test_wrapped_with_native_position_reverses_through_set_cover_position(
    make_cover,
):
    cover = _wrapped(make_cover, _F_OPEN_CLOSE_SET_POSITION_STOP)
    cover.travel_calc.set_position(60)
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.async_close_cover()
        mark = len(cover.hass.services.async_call.call_args_list)
        await cover.async_open_cover()

    assert relay_calls(cover, mark) == [
        ("stop_cover", "cover.inner"),
        ("set_cover_position", "cover.inner"),
    ]
    assert cover.hass.services.async_call.call_args.args[2]["position"] == 100
    settle.assert_awaited_once()
    assert cover.travel_calc.is_opening()


def _single_button(travel_startup_delay=None):
    cover = SingleButtonModeCover(
        device_id="test_sb",
        name="Test SB",
        tilt_strategy=None,
        travel_time_close=30,
        travel_time_open=30,
        tilt_time_close=None,
        tilt_time_open=None,
        travel_startup_delay=travel_startup_delay,
        tilt_startup_delay=None,
        endpoint_runon_time=None,
        min_movement_time=None,
        open_switch_entity_id="switch.button",
        close_switch_entity_id=None,
        stop_switch_entity_id=None,
        pulse_time=1.0,
        wait_for_relay_feedback=False,
        reverse_on_opposite_command=True,
    )
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    tasks = []

    def create_task(coro):
        task = asyncio.ensure_future(coro)
        tasks.append(task)
        return task

    hass.async_create_task = create_task
    cover.hass = hass
    cover._test_tasks = tasks
    stub_switches(cover)
    return cover


async def _run_single_button(cover, command):
    await getattr(cover, command)()
    while cover._test_tasks:
        await cover._test_tasks.pop(0)


@pytest.mark.asyncio
async def test_single_button_close_while_opening_presses_stop_then_close():
    """The button cycles up, stop, down: reversing takes two presses."""
    cover = _single_button()
    cover.travel_calc.set_position(60)
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "start_auto_updater"),
        single_button_sleep_patch(),
    ):
        await _run_single_button(cover, "async_open_cover")
        mark = len(cover.hass.services.async_call.call_args_list)
        await _run_single_button(cover, "async_close_cover")

    press = [("turn_on", "switch.button"), ("turn_off", "switch.button")]
    assert relay_calls(cover, mark) == press * 2
    assert cover.travel_calc.is_closing()


@pytest.mark.asyncio
async def test_single_button_open_while_opening_presses_nothing():
    cover = _single_button()
    cover.travel_calc.set_position(60)
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "start_auto_updater"),
        single_button_sleep_patch(),
    ):
        await _run_single_button(cover, "async_open_cover")
        mark = len(cover.hass.services.async_call.call_args_list)
        await _run_single_button(cover, "async_open_cover")

    assert relay_calls(cover, mark) == []
    assert cover.travel_calc.is_opening()


# ---------------------------------------------------------------------------
# Just after leaving an endpoint the whole-percent tracker still reads it, so
# set_position(endpoint) alone would find the target reached and leave the
# motor running away from it. The cover is stopped and settled instead, then
# the command runs as it would on a cover stopped at that endpoint.
# ---------------------------------------------------------------------------


@contextmanager
def _just_left_endpoint(cover):
    """Hand-driven tracker clock, settle gap stubbed: yields (now, settle)."""
    now = [5000.0]
    with (
        patch(
            "custom_components.cover_time_based.travel_calculator.time",
            SimpleNamespace(monotonic=lambda: now[0]),
        ),
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        yield now, settle


async def _just_left(cover, now, command, start, run=None):
    """Start ``command`` from endpoint ``start`` and let 0.1 s of a 30 s
    travel pass; return the service-call watermark."""
    cover.travel_calc.set_position(start)
    await (run(cover, command) if run else getattr(cover, command)())
    now[0] += 0.1
    assert cover.travel_calc.current_position() == start
    assert cover.travel_calc.is_traveling()
    return len(cover.hass.services.async_call.call_args_list)


_OPEN_AFTER_CLOSING = ("async_close_cover", 100, "async_open_cover")
_CLOSE_AFTER_OPENING = ("async_open_cover", 0, "async_close_cover")
_SWITCH_STOP = [("turn_off", "switch.close"), ("turn_off", "switch.open")]
_SWITCH_OPEN = [("turn_off", "switch.close"), ("turn_on", "switch.open")]
_IDS = ["open-after-closing-from-100", "close-after-opening-from-0"]


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        (_OPEN_AFTER_CLOSING, _SWITCH_STOP + _SWITCH_OPEN),
        (_CLOSE_AFTER_OPENING, _SWITCH_STOP),
    ],
    ids=_IDS,
)
@pytest.mark.asyncio
async def test_switch_opposite_command_just_after_leaving_endpoint_stops(
    make_cover, case, expected
):
    first, start, second = case
    cover = make_cover(reverse_on_opposite_command=True)
    stub_switches(cover)
    with _just_left_endpoint(cover) as (now, settle):
        mark = await _just_left(cover, now, first, start)
        await getattr(cover, second)()

        assert relay_calls(cover, mark) == expected
        settle.assert_awaited_once()
        assert not cover.travel_calc.is_traveling()
        assert cover.travel_calc.current_position() == start


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        (
            _OPEN_AFTER_CLOSING,
            [
                ("turn_on", "switch.close"),
                ("turn_off", "switch.close"),
                ("turn_on", "switch.open"),
            ],
        ),
        (_CLOSE_AFTER_OPENING, [("turn_on", "switch.open")]),
    ],
    ids=_IDS,
)
@pytest.mark.asyncio
async def test_toggle_opposite_command_just_after_leaving_endpoint_stops(
    make_cover, case, expected
):
    """The stop is a pulse on the relay that started the move."""
    first, start, second = case
    cover = make_cover(control_mode="toggle", reverse_on_opposite_command=True)
    stub_switches(cover)
    with _just_left_endpoint(cover) as (now, settle):
        mark = await _just_left(cover, now, first, start)
        await getattr(cover, second)()

        assert relay_calls(cover, mark) == expected
        settle.assert_awaited_once()
        assert not cover.travel_calc.is_traveling()
        assert cover.travel_calc.current_position() == start


@pytest.mark.parametrize("case", [_OPEN_AFTER_CLOSING, _CLOSE_AFTER_OPENING], ids=_IDS)
@pytest.mark.asyncio
async def test_single_button_opposite_command_just_after_leaving_endpoint_stops(
    case,
):
    """One press stops the cover; the endpoint command adds none."""
    first, start, second = case
    cover = _single_button()
    with (
        _just_left_endpoint(cover) as (now, settle),
        patch.object(cover, "start_auto_updater"),
        single_button_sleep_patch(),
    ):
        mark = await _just_left(cover, now, first, start, run=_run_single_button)
        await _run_single_button(cover, second)

        assert relay_calls(cover, mark) == [
            ("turn_on", "switch.button"),
            ("turn_off", "switch.button"),
        ]
        settle.assert_awaited_once()
        assert not cover.travel_calc.is_traveling()
        assert cover.travel_calc.current_position() == start


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        (
            _OPEN_AFTER_CLOSING,
            [("stop_cover", "cover.inner"), ("open_cover", "cover.inner")],
        ),
        (_CLOSE_AFTER_OPENING, [("stop_cover", "cover.inner")]),
    ],
    ids=_IDS,
)
@pytest.mark.parametrize(
    "features",
    [_F_OPEN_CLOSE_STOP, _F_OPEN_CLOSE_SET_POSITION_STOP],
    ids=["open-close-stop", "native-position"],
)
@pytest.mark.asyncio
async def test_wrapped_opposite_command_just_after_leaving_endpoint_stops(
    make_cover, features, case, expected
):
    first, start, second = case
    cover = _wrapped(make_cover, features)
    with _just_left_endpoint(cover) as (now, settle):
        mark = await _just_left(cover, now, first, start)
        await getattr(cover, second)()

        assert relay_calls(cover, mark) == expected
        settle.assert_awaited_once()
        assert not cover.travel_calc.is_traveling()
        assert cover.travel_calc.current_position() == start


@pytest.mark.parametrize(
    ("command", "start"),
    [("async_close_cover", 100), ("async_open_cover", 0)],
    ids=["close-while-closing-from-100", "open-while-opening-from-0"],
)
@pytest.mark.asyncio
async def test_same_direction_command_just_after_leaving_endpoint_carries_on(
    make_cover, command, start
):
    cover = make_cover(reverse_on_opposite_command=True)
    stub_switches(cover)
    with _just_left_endpoint(cover) as (now, settle):
        mark = await _just_left(cover, now, command, start)
        await getattr(cover, command)()

        assert relay_calls(cover, mark) == []
        settle.assert_not_awaited()
        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._travel_to_position == 100 - start


@pytest.mark.parametrize("case", [_OPEN_AFTER_CLOSING, _CLOSE_AFTER_OPENING], ids=_IDS)
@pytest.mark.asyncio
async def test_option_off_opposite_command_just_after_leaving_endpoint_stops(
    make_cover, case
):
    """Control: with the option off the in-motion command only stops."""
    first, start, second = case
    cover = make_cover(reverse_on_opposite_command=False)
    stub_switches(cover)
    with _just_left_endpoint(cover) as (now, settle):
        mark = await _just_left(cover, now, first, start)
        await getattr(cover, second)()

        assert relay_calls(cover, mark) == _SWITCH_STOP
        settle.assert_not_awaited()
        assert not cover.travel_calc.is_traveling()
        assert cover.travel_calc.current_position() == start


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        (_OPEN_AFTER_CLOSING, _SWITCH_STOP + _SWITCH_OPEN),
        (_CLOSE_AFTER_OPENING, _SWITCH_STOP),
    ],
    ids=_IDS,
)
@pytest.mark.asyncio
async def test_always_resend_opposite_command_just_after_leaving_endpoint_is_not_a_redrive(
    make_cover, case, expected
):
    """A reversal stays an ordinary move with "Always re-send" on: no full
    re-drive modelled from the opposite end."""
    first, start, second = case
    cover = make_cover(reverse_on_opposite_command=True, force_endpoint_redrive=True)
    stub_switches(cover)
    with _just_left_endpoint(cover) as (now, settle):
        mark = await _just_left(cover, now, first, start)
        await getattr(cover, second)()

        assert relay_calls(cover, mark) == expected
        settle.assert_awaited_once()
        assert not cover.travel_calc.is_traveling()
        assert cover.travel_calc.current_position() == start


@pytest.mark.parametrize(
    ("command", "endpoint"),
    [("async_open_cover", 100), ("async_close_cover", 0)],
    ids=["open-at-100", "close-at-0"],
)
@pytest.mark.asyncio
async def test_always_resend_still_redrives_a_cover_stopped_at_the_endpoint(
    make_cover, command, endpoint
):
    """Control: with the option on, a command to a cover already stopped at
    the endpoint is still a full re-drive from the opposite end."""
    cover = make_cover(reverse_on_opposite_command=True, force_endpoint_redrive=True)
    stub_switches(cover)
    with _just_left_endpoint(cover) as (_now, settle):
        cover.travel_calc.set_position(endpoint)
        await getattr(cover, command)()

        settle.assert_not_awaited()
        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc.current_position() == 100 - endpoint
        assert cover.travel_calc._travel_to_position == endpoint


# ---------------------------------------------------------------------------
# A start still parked — waiting out travel_startup_delay or the relay's ON
# echo — has the relay commanded but the tracker not yet running. An opposite
# command must still stop, settle and drive the other way; a same-direction
# one must leave the parked start alone.
# ---------------------------------------------------------------------------


@contextmanager
def _settle_spy(cover):
    """Stub the settle gap, recording how many service calls preceded it."""
    at = []

    async def _settle():
        at.append(len(cover.hass.services.async_call.call_args_list))

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=_settle),
    ):
        yield at


async def _parked(cover, command, start):
    """Start ``command`` from ``start`` and leave it parked; return the
    service-call watermark."""
    stub_switches(cover)
    cover.travel_calc.set_position(start)
    await getattr(cover, command)()
    await asyncio.sleep(0)
    task = cover._startup_delay_task
    assert task is not None and not task.done()
    assert not cover.travel_calc.is_traveling()
    return len(cover.hass.services.async_call.call_args_list)


_SWITCH_STOP_CLOSE = [("turn_off", "switch.close"), ("turn_off", "switch.open")]
_SWITCH_STOP_OPEN = _SWITCH_STOP_CLOSE
_SWITCH_DRIVE_OPEN = [("turn_off", "switch.close"), ("turn_on", "switch.open")]
_SWITCH_DRIVE_CLOSE = [("turn_off", "switch.open"), ("turn_on", "switch.close")]

# (control mode, first, start, second, stop calls, drive calls, new target)
_PARKED_REVERSALS = [
    (
        "switch",
        "async_close_cover",
        60,
        "async_open_cover",
        _SWITCH_STOP_CLOSE,
        _SWITCH_DRIVE_OPEN,
        100,
    ),
    (
        "switch",
        "async_open_cover",
        40,
        "async_close_cover",
        _SWITCH_STOP_OPEN,
        _SWITCH_DRIVE_CLOSE,
        0,
    ),
    (
        "toggle",
        "async_close_cover",
        60,
        "async_open_cover",
        [("turn_on", "switch.close")],
        [("turn_off", "switch.close"), ("turn_on", "switch.open")],
        100,
    ),
    (
        "toggle",
        "async_open_cover",
        40,
        "async_close_cover",
        [("turn_on", "switch.open")],
        [("turn_off", "switch.open"), ("turn_on", "switch.close")],
        0,
    ),
]
_PARKED_IDS = [
    "switch-open-while-close-parked",
    "switch-close-while-open-parked",
    "toggle-open-while-close-parked",
    "toggle-close-while-open-parked",
]


@pytest.mark.parametrize(
    ("mode", "first", "start", "second", "stop", "drive", "target"),
    _PARKED_REVERSALS,
    ids=_PARKED_IDS,
)
@pytest.mark.asyncio
async def test_opposite_command_during_startup_delay_stops_settles_and_reverses(
    make_cover, mode, first, start, second, stop, drive, target
):
    cover = make_cover(
        control_mode=mode, reverse_on_opposite_command=True, travel_startup_delay=20
    )
    with _settle_spy(cover) as settled_at:
        mark = await _parked(cover, first, start)
        await getattr(cover, second)()

    assert relay_calls(cover, mark) == stop + drive
    assert settled_at == [mark + len(stop)], "settle between the stop and the drive"
    command = "open_cover" if target == 100 else "close_cover"
    assert cover._last_command == command
    assert cover._parked_travel_target == target
    assert cover.travel_calc.current_position() == start


@pytest.mark.parametrize("mode", ["switch", "toggle"])
@pytest.mark.parametrize(
    ("command", "start", "target"),
    [("async_close_cover", 60, 0), ("async_open_cover", 40, 100)],
    ids=["close-while-close-parked", "open-while-open-parked"],
)
@pytest.mark.asyncio
async def test_same_direction_command_during_startup_delay_sends_nothing(
    make_cover, mode, command, start, target
):
    cover = make_cover(
        control_mode=mode, reverse_on_opposite_command=True, travel_startup_delay=20
    )
    with _settle_spy(cover) as settled_at:
        mark = await _parked(cover, command, start)
        task = cover._startup_delay_task
        await getattr(cover, command)()

    assert relay_calls(cover, mark) == []
    assert settled_at == []
    assert cover._startup_delay_task is task
    assert cover._parked_travel_target == target


@pytest.mark.parametrize(
    ("mode", "first", "start", "second", "stop", "drive", "target"),
    _PARKED_REVERSALS,
    ids=_PARKED_IDS,
)
@pytest.mark.asyncio
async def test_option_off_opposite_command_during_startup_delay_only_stops(
    make_cover, mode, first, start, second, stop, drive, target
):
    """Control: with the option off the parked start is stopped, not reversed."""
    cover = make_cover(
        reverse_on_opposite_command=False, control_mode=mode, travel_startup_delay=20
    )
    with _settle_spy(cover) as settled_at:
        mark = await _parked(cover, first, start)
        await getattr(cover, second)()

    assert relay_calls(cover, mark) == stop
    assert settled_at == []
    assert cover._last_command is None
    assert cover._startup_delay_task is None


def _echo(entity_id, old, new):
    """A relay state-change event as HA fires it."""
    states = []
    for value in (old, new):
        st = MagicMock()
        st.state = value
        st.attributes = {}
        st.last_changed = datetime.now(UTC)
        states.append(st)
    event = MagicMock()
    event.data = {
        "entity_id": entity_id,
        "old_state": states[0],
        "new_state": states[1],
    }
    return event


@pytest.mark.parametrize(
    ("first", "start", "second", "stop", "drive", "target"),
    [p[1:] for p in _PARKED_REVERSALS if p[0] == "switch"],
    ids=[i for i in _PARKED_IDS if i.startswith("switch")],
)
@pytest.mark.asyncio
async def test_switch_opposite_command_during_relay_feedback_wait_reverses(
    make_cover, first, start, second, stop, drive, target
):
    """Switch relays de-energise to stop, so nothing waits for the echo."""
    cover = make_cover(reverse_on_opposite_command=True, wait_for_relay_feedback=True)
    driven = "switch.open" if target == 100 else "switch.close"
    with _settle_spy(cover) as settled_at:
        mark = await _parked(cover, first, start)
        assert cover._feedback_wait_entity is not None
        await getattr(cover, second)()
        await asyncio.sleep(0)

    assert relay_calls(cover, mark) == stop + drive
    assert settled_at == [mark + len(stop)]
    assert cover._last_command == ("open_cover" if target == 100 else "close_cover")
    assert cover._feedback_wait_entity == driven


@pytest.mark.asyncio
async def test_toggle_close_during_relay_feedback_wait_taps_stop_after_the_echo_then_closes(
    make_cover,
):
    """The stop tap is held until the open relay confirms (issue #268); the
    close drive follows the settle gap."""
    cover = make_cover(
        control_mode="toggle",
        reverse_on_opposite_command=True,
        wait_for_relay_feedback=True,
    )
    with _settle_spy(cover) as settled_at:
        mark = await _parked(cover, "async_open_cover", 40)
        assert cover._feedback_wait_entity == "switch.open"
        reversal = asyncio.ensure_future(cover.async_close_cover())
        for _ in range(5):
            await asyncio.sleep(0)
        assert relay_calls(cover, mark) == [], "no tap before the relay confirms"
        assert not reversal.done()

        await cover._async_switch_state_changed(_echo("switch.open", "off", "on"))
        await asyncio.wait_for(reversal, 1.0)
        await asyncio.sleep(0)

    assert relay_calls(cover, mark) == [
        ("turn_on", "switch.open"),
        ("turn_off", "switch.open"),
        ("turn_on", "switch.close"),
    ]
    assert settled_at == [mark + 1]
    assert cover._last_command == "close_cover"
    assert cover._feedback_wait_entity == "switch.close"


@pytest.mark.parametrize("mode", ["switch", "toggle"])
@pytest.mark.asyncio
async def test_same_direction_command_during_relay_feedback_wait_sends_nothing(
    make_cover, mode
):
    cover = make_cover(
        control_mode=mode,
        reverse_on_opposite_command=True,
        wait_for_relay_feedback=True,
    )
    with _settle_spy(cover) as settled_at:
        mark = await _parked(cover, "async_open_cover", 40)
        task = cover._startup_delay_task
        await cover.async_open_cover()

    assert relay_calls(cover, mark) == []
    assert settled_at == []
    assert cover._startup_delay_task is task
    assert cover._feedback_wait_entity == "switch.open"


@pytest.mark.asyncio
async def test_option_off_close_during_relay_feedback_wait_only_stops(make_cover):
    """Control: with the option off the parked open is stopped, not reversed."""
    cover = make_cover(reverse_on_opposite_command=False, wait_for_relay_feedback=True)
    with _settle_spy(cover) as settled_at:
        mark = await _parked(cover, "async_open_cover", 40)
        await cover.async_close_cover()
        await asyncio.sleep(0)

    assert relay_calls(cover, mark) == _SWITCH_STOP_OPEN
    assert settled_at == []
    assert cover._last_command is None
    assert cover._feedback_wait_entity is None


@pytest.mark.parametrize(
    ("first", "start", "second"),
    [
        ("async_close_cover", 100, "async_open_cover"),
        ("async_open_cover", 0, "async_close_cover"),
    ],
    ids=["open-while-close-from-100-parked", "close-while-open-from-0-parked"],
)
@pytest.mark.asyncio
async def test_opposite_command_during_startup_delay_from_an_endpoint(
    make_cover, first, start, second
):
    """Parked at the endpoint it is leaving: stopped and settled, then handled
    as a command to a cover stopped there (open re-drives, close at 0 is a
    no-op)."""
    cover = make_cover(reverse_on_opposite_command=True, travel_startup_delay=20)
    with _settle_spy(cover) as settled_at:
        mark = await _parked(cover, first, start)
        await getattr(cover, second)()

    calls = relay_calls(cover, mark)
    assert calls[:2] == _SWITCH_STOP_CLOSE
    assert settled_at == [mark + 2]
    if second == "async_open_cover":
        assert calls[2:] == _SWITCH_DRIVE_OPEN
    else:
        assert calls[2:] == []
        assert cover._last_command is None
    assert cover.travel_calc.current_position() == start


@pytest.mark.parametrize(
    ("first", "start", "second"),
    [
        ("async_close_cover", 100, "async_open_cover"),
        ("async_open_cover", 0, "async_close_cover"),
    ],
    ids=["open-while-close-from-100-parked", "close-while-open-from-0-parked"],
)
@pytest.mark.asyncio
async def test_always_resend_opposite_command_during_startup_delay_from_an_endpoint(
    make_cover, first, start, second
):
    """With "Always re-send" on the reversal is still an ordinary move, not a
    full re-drive modelled from the opposite end."""
    cover = make_cover(
        reverse_on_opposite_command=True,
        force_endpoint_redrive=True,
        travel_startup_delay=20,
    )
    with _settle_spy(cover) as settled_at:
        mark = await _parked(cover, first, start)
        await getattr(cover, second)()

    calls = relay_calls(cover, mark)
    assert calls[:2] == _SWITCH_STOP_CLOSE
    assert settled_at == [mark + 2]
    if second == "async_open_cover":
        assert calls[2:] == _SWITCH_DRIVE_OPEN
    else:
        assert calls[2:] == []
        assert cover._last_command is None
    assert cover.travel_calc.current_position() == start
    assert not cover.travel_calc.is_traveling()


async def _run_single_button_leaving_parked(cover, command):
    """Run ``command`` and the presses it schedules, leaving a parked start
    (which would otherwise be awaited for its whole delay) pending."""
    await getattr(cover, command)()
    while pending := [
        t for t in cover._test_tasks if t is not cover._startup_delay_task
    ]:
        for task in pending:
            cover._test_tasks.remove(task)
        await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_single_button_close_during_startup_delay_presses_stop_then_close():
    """A stop press, then a close press. The presses run as their own
    sequenced task, so only that the settle ran is asserted, not its place."""
    cover = _single_button(travel_startup_delay=20)
    try:
        with (
            _settle_spy(cover) as settled_at,
            patch.object(cover, "start_auto_updater"),
            single_button_sleep_patch(),
        ):
            cover.travel_calc.set_position(40)
            await _run_single_button_leaving_parked(cover, "async_open_cover")
            assert cover._startup_delay_task is not None
            assert not cover._startup_delay_task.done()
            mark = len(cover.hass.services.async_call.call_args_list)
            await _run_single_button_leaving_parked(cover, "async_close_cover")

        press = [("turn_on", "switch.button"), ("turn_off", "switch.button")]
        assert relay_calls(cover, mark) == press * 2
        assert len(settled_at) == 1
        assert cover._last_command == "close_cover"
        assert cover._parked_travel_target == 0
    finally:
        for task in cover._test_tasks:
            task.cancel()
        await asyncio.gather(*cover._test_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_stop_while_the_reversal_stop_is_in_flight_wins(make_cover):
    """The reversal claims the movement before its stop, which can wait (for a
    relay confirmation, say). A stop pressed meanwhile must not be overridden
    by the reversal resuming after the settle gap."""
    cover = make_cover()
    stub_switches(cover)
    gate = asyncio.Event()
    calls = []

    async def confirmation():
        calls.append(None)
        if len(calls) == 1:
            await gate.wait()

    with _just_left_endpoint(cover) as (now, _settle):
        await _just_left(cover, now, "async_close_cover", 100)
        with patch.object(cover, "_await_confirmation_before_stop", confirmation):
            reversal = asyncio.ensure_future(cover.async_open_cover())
            await asyncio.sleep(0)
            assert calls, "the reversal's stop is waiting"
            await cover.async_stop_cover()
            gate.set()
            await reversal

        mark_open = ("turn_on", "switch.open")
        assert mark_open not in relay_calls(cover)
        assert not cover.travel_calc.is_traveling()
