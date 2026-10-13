"""reverse_on_opposite_command: an in-motion open/close re-targets through
set_position (stop, settle, drive the other way) instead of only stopping.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tests.helpers import relay_calls, stub_switches


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
