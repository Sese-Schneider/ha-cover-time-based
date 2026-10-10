"""Options for covers that are also driven by a latching wall switch.

- reverse_on_opposite_command: an in-motion open/close re-targets through
  set_position (stop, settle, drive the other way) instead of only stopping.
- keep_external_latch (switch mode): the relay a wall switch latched ON is left
  ON at the end of travel, so a rocker on a toggle-input module stays in step.
- block_while_external (switch mode): while a wall switch holds a direction
  relay ON, HA commands are refused with an event and an error.
"""

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.cover_time_based.const import EVENT_COMMAND_BLOCKED
from custom_components.cover_time_based.errors import (
    CoverBlockedByExternalSwitchError,
)
from tests.helpers import relay_calls, stub_switches

_CALL_LATER = "custom_components.cover_time_based.cover_echo_filter.async_call_later"


async def _wall_switch(cover, entity_id, new_val):
    """Drive the switch-mode external handler the way the dispatcher does."""
    old_val = "off" if new_val == "on" else "on"
    cover._triggered_externally = True
    try:
        with (
            patch(_CALL_LATER),
            patch.object(cover, "async_open_cover", new_callable=AsyncMock),
            patch.object(cover, "async_close_cover", new_callable=AsyncMock),
            patch.object(cover, "async_stop_cover", new_callable=AsyncMock),
        ):
            await cover._handle_external_state_change(entity_id, old_val, new_val)
    finally:
        cover._triggered_externally = False


# ---------------------------------------------------------------------------
# reverse_on_opposite_command
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# keep_external_latch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keep_external_latch_leaves_the_relay_on(make_cover):
    cover = make_cover(keep_external_latch=True)
    stub_switches(cover, on=("switch.open",))

    await cover._settle_external_endpoint()

    cover.hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_without_keep_external_latch_the_relay_is_released(make_cover):
    cover = make_cover()
    stub_switches(cover, on=("switch.open",))

    with patch(_CALL_LATER):
        await cover._settle_external_endpoint()

    assert relay_calls(cover) == [("turn_off", "switch.open")]


# ---------------------------------------------------------------------------
# block_while_external
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commands_refused_while_wall_switch_holds(make_cover):
    cover = make_cover(block_while_external=True)
    stub_switches(cover, on=("switch.open",))
    await _wall_switch(cover, "switch.open", "on")

    for call in (
        cover.async_close_cover(),
        cover.async_open_cover(),
        cover.async_set_cover_position(position=30),
        cover.async_stop_cover(),
    ):
        with pytest.raises(CoverBlockedByExternalSwitchError) as err:
            await call
        assert err.value.switch_entity_id == "switch.open"

    fired = [c.args for c in cover.hass.bus.async_fire.call_args_list]
    assert [f[0] for f in fired] == [EVENT_COMMAND_BLOCKED] * 4
    assert fired[0][1]["service"] == "close_cover"
    assert fired[0][1]["switch_entity_id"] == "switch.open"
    cover.hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_and_internal_stops_are_never_refused(make_cover):
    """The wall switch's own release and internal stops pass supersede=False."""
    cover = make_cover(block_while_external=True)
    stub_switches(cover, on=("switch.open",))
    await _wall_switch(cover, "switch.open", "on")

    with (
        patch.object(cover, "_stop_hardware", new_callable=AsyncMock) as hw,
        patch.object(cover, "async_write_ha_state"),
    ):
        await cover.async_stop_cover(supersede=False)
    hw.assert_awaited_once()


@pytest.mark.asyncio
async def test_hardware_dispatched_commands_are_not_refused(make_cover):
    cover = make_cover(block_while_external=True)
    stub_switches(cover, on=("switch.open",))
    await _wall_switch(cover, "switch.open", "on")

    cover._triggered_externally = True
    try:
        cover._refuse_if_blocked_by_external_switch("open_cover")
    finally:
        cover._triggered_externally = False


@pytest.mark.asyncio
async def test_released_switch_allows_commands_again(make_cover):
    cover = make_cover(block_while_external=True)
    stub_switches(cover, on=("switch.open",))
    await _wall_switch(cover, "switch.open", "on")

    stub_switches(cover)  # rocker back to neutral, relay reports off
    await _wall_switch(cover, "switch.open", "off")

    assert cover._external_switch_holding() is None
    cover._refuse_if_blocked_by_external_switch("close_cover")
    cover.hass.bus.async_fire.assert_not_called()


@pytest.mark.asyncio
async def test_relay_reported_off_without_event_also_releases(make_cover):
    """The hold is read live from the relay's state."""
    cover = make_cover(block_while_external=True)
    stub_switches(cover, on=("switch.close",))
    await _wall_switch(cover, "switch.close", "on")
    assert cover._external_switch_holding() == "switch.close"

    stub_switches(cover)
    assert cover._external_switch_holding() is None


@pytest.mark.asyncio
async def test_ha_command_takes_the_relay_over(make_cover):
    """After an HA command went ahead, HA turning the same relay on is not
    mistaken for the wall switch holding it."""
    cover = make_cover(block_while_external=True)
    stub_switches(cover, on=("switch.open",))
    await _wall_switch(cover, "switch.open", "on")
    stub_switches(cover)
    await _wall_switch(cover, "switch.open", "off")

    cover._external_on_switch = "switch.open"  # stale record, relay off
    cover._refuse_if_blocked_by_external_switch("open_cover")
    assert cover._external_on_switch is None

    stub_switches(cover, on=("switch.open",))  # HA's own open energized it
    assert cover._external_switch_holding() is None


@pytest.mark.asyncio
async def test_option_off_never_refuses(make_cover):
    cover = make_cover()
    stub_switches(cover, on=("switch.open",))
    await _wall_switch(cover, "switch.open", "on")

    assert cover._external_switch_holding() is None
    with (
        patch.object(cover, "_stop_hardware", new_callable=AsyncMock) as hw,
        patch.object(cover, "async_write_ha_state"),
    ):
        await cover.async_stop_cover()
    hw.assert_awaited_once()


def test_switch_mode_options_in_state_attributes(make_cover):
    cover = make_cover(keep_external_latch=True, block_while_external=True)
    attr = cover.extra_state_attributes
    assert attr["keep_external_latch"] is True
    assert attr["block_while_external"] is True
    assert attr["external_switch_holding"] is None


# ---------------------------------------------------------------------------
# pause_on_external_reversal
# ---------------------------------------------------------------------------

_MODE_SLEEP = "custom_components.cover_time_based.cover_switch_mode.sleep"
_BASE_SLEEP = "custom_components.cover_time_based.cover_base.sleep"


async def _external_on(cover, entity_id, *, mode_sleep=None):
    """Dispatch a wall switch turning ``entity_id`` on, the way HA does."""
    cover._triggered_externally = True
    try:
        with (
            patch(_CALL_LATER),
            patch(_MODE_SLEEP, mode_sleep or AsyncMock()),
            patch(_BASE_SLEEP, AsyncMock()),
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "_async_handle_command", new_callable=AsyncMock),
        ):
            await cover._handle_external_state_change(entity_id, "off", "on")
    finally:
        cover._triggered_externally = False


@pytest.mark.asyncio
async def test_external_reversal_pauses_and_reenergizes(make_cover):
    """Opening, then the wall switch turns close on: close off, open off,
    pause, close back on — and the cover tracks closing."""
    cover = make_cover(pause_on_external_reversal=True)
    cover.travel_calc.set_position(30)
    cover.travel_calc.start_travel_up()
    stub_switches(cover, on=("switch.open", "switch.close"))

    await _external_on(cover, "switch.close")

    assert relay_calls(cover) == [
        ("turn_off", "switch.close"),
        ("turn_off", "switch.open"),
        ("turn_on", "switch.close"),
    ]
    assert cover._travel_axis_closing()
    assert cover._pending_switch.get("switch.close") == 2


@pytest.mark.asyncio
async def test_external_reversal_from_standstill_pauses_before_tracking(make_cover):
    """A latched opposite relay with the tracker idle still gets the pause."""
    cover = make_cover(pause_on_external_reversal=True)
    cover.travel_calc.set_position(100)
    stub_switches(cover, on=("switch.open", "switch.close"))
    pause = AsyncMock()

    await _external_on(cover, "switch.close", mode_sleep=pause)

    pause.assert_awaited()
    assert relay_calls(cover)[-1] == ("turn_on", "switch.close")


@pytest.mark.asyncio
async def test_command_during_the_pause_cancels_the_reenergize(make_cover):
    cover = make_cover(pause_on_external_reversal=True)
    cover.travel_calc.set_position(100)
    stub_switches(cover, on=("switch.open", "switch.close"))

    async def stop_during_pause(_seconds):
        await cover._send_stop()

    await _external_on(cover, "switch.close", mode_sleep=stop_during_pause)

    assert ("turn_on", "switch.close") not in relay_calls(cover)


@pytest.mark.asyncio
async def test_no_pause_when_opposite_relay_is_off(make_cover):
    cover = make_cover(pause_on_external_reversal=True)
    cover.travel_calc.set_position(100)
    stub_switches(cover, on=("switch.close",))

    await _external_on(cover, "switch.close")

    assert relay_calls(cover) == []


@pytest.mark.asyncio
async def test_option_off_keeps_the_plain_interlock(make_cover):
    cover = make_cover()
    cover.travel_calc.set_position(30)
    cover.travel_calc.start_travel_up()
    stub_switches(cover, on=("switch.open", "switch.close"))

    await _external_on(cover, "switch.close")

    assert relay_calls(cover) == [("turn_off", "switch.open")]


def test_pause_option_in_state_attributes(make_cover):
    attr = make_cover(pause_on_external_reversal=True).extra_state_attributes
    assert attr["pause_on_external_reversal"] is True
    assert make_cover().extra_state_attributes["pause_on_external_reversal"] is False
