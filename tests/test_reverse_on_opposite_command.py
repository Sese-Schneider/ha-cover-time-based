"""reverse_on_opposite_command: an in-motion open/close re-targets through
set_position (stop, settle, drive the other way) instead of only stopping.
"""

import asyncio
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
    cover = make_cover()
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
    assert make_cover().extra_state_attributes["reverse_on_opposite_command"] is False


# ---------------------------------------------------------------------------
# What the relays actually do
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_direction_close_sends_nothing_with_recalibrate_before_position(
    make_cover,
):
    """ "Fully open before moving to a position" must not turn a repeated
    close into a stop and a forced full re-drive from 100."""
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


def _single_button():
    cover = SingleButtonModeCover(
        device_id="test_sb",
        name="Test SB",
        tilt_strategy=None,
        travel_time_close=30,
        travel_time_open=30,
        tilt_time_close=None,
        tilt_time_open=None,
        travel_startup_delay=None,
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
