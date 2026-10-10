"""reverse_on_opposite_command: an in-motion open/close re-targets through
set_position (stop, settle, drive the other way) instead of only stopping.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_open_while_closing_reverses(make_cover):
    cover = make_cover(reverse_on_opposite_command=True)
    cover.travel_calc.set_position(60)
    cover.travel_calc.start_travel_down()

    with (
        patch.object(cover, "set_position", new_callable=AsyncMock) as set_pos,
        patch.object(cover, "async_stop_cover", new_callable=AsyncMock) as stop,
    ):
        await cover.async_open_cover()

    set_pos.assert_awaited_once_with(100)
    stop.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_while_opening_reverses(make_cover):
    cover = make_cover(reverse_on_opposite_command=True)
    cover.travel_calc.set_position(40)
    cover.travel_calc.start_travel_up()

    with patch.object(cover, "set_position", new_callable=AsyncMock) as set_pos:
        await cover.async_close_cover()

    set_pos.assert_awaited_once_with(0)


@pytest.mark.asyncio
async def test_same_direction_command_keeps_moving(make_cover):
    """Re-targeting to the endpoint already headed for continues the move."""
    cover = make_cover(reverse_on_opposite_command=True)
    cover.travel_calc.set_position(40)
    cover.travel_calc.start_travel_up()

    with patch.object(cover, "set_position", new_callable=AsyncMock) as set_pos:
        await cover.async_open_cover()

    set_pos.assert_awaited_once_with(100)


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
