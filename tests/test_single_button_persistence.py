import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.cover_time_based.cover import CONTROL_MODE_SINGLE_BUTTON
from custom_components.cover_time_based.single_button_cycle import Action, Phase, plan
from tests.helpers import FakeClock, single_button_sleep_patch, stub_switches
from tests.test_cover_single_button_mode import _make_sb_cover
from tests.test_teardown_continuations import Gate


def test_extra_persist_data_carries_phase():
    cover = _make_sb_cover()
    cover._phase = Phase.STOPPED_AFTER_DOWN
    assert cover._extra_persist_data() == {"phase": "stopped_after_down"}


def test_apply_restored_extra_sets_phase():
    cover = _make_sb_cover()
    cover._phase = Phase.AT_CLOSED
    cover._apply_restored_extra({"position": 50, "phase": "moving_up"})
    assert cover._phase is Phase.MOVING_UP


def test_apply_restored_extra_ignores_missing_phase():
    cover = _make_sb_cover()
    cover._phase = Phase.AT_OPEN
    cover._apply_restored_extra({"position": 50})
    assert cover._phase is Phase.AT_OPEN


def test_apply_restored_extra_ignores_invalid_phase():
    # A corrupted store or a renamed/removed Phase value must not raise --
    # it should leave the current/default phase untouched instead of
    # breaking entity restore.
    cover = _make_sb_cover()
    cover._phase = Phase.AT_OPEN
    cover._apply_restored_extra({"position": 50, "phase": "not_a_real_phase"})
    assert cover._phase is Phase.AT_OPEN


@pytest.mark.asyncio
async def test_removal_mid_travel_persists_the_phase_at_the_limit(
    make_cover, _mock_position_store
):
    """The motor runs on to its limit; the restored phase must say so.

    A persisted MOVING_UP would plan a press for the next STOP, restarting a
    motor that is sitting at its limit.
    """
    cover = make_cover(
        control_mode=CONTROL_MODE_SINGLE_BUTTON,
        travel_time_close=5.0,
        travel_time_open=5.0,
    )
    stub_switches(cover)
    cover.travel_calc.set_position(0)
    cover._phase = Phase.AT_CLOSED

    with patch.object(cover, "async_write_ha_state"), single_button_sleep_patch():
        await cover.async_open_cover()
        await asyncio.sleep(0.2)
        assert cover.travel_calc.is_traveling()
        await cover.async_will_remove_from_hass()

    assert _mock_position_store.async_save.await_args is not None, "no final record"
    _, data = _mock_position_store.async_save.await_args.args
    assert data["position"] == 100
    assert data["phase"] == Phase.AT_OPEN.value


async def test_single_button_removal_during_endpoint_margin_restores_parked_phase(
    make_cover, _mock_position_store
):
    """A replacement must not STOP-tap a motor already at its endpoint."""
    from custom_components.cover_time_based import cover_base, travel_calculator

    clock = FakeClock()
    cover = make_cover(
        control_mode="single_button",
        travel_time_open=10,
        travel_time_close=10,
        endpoint_runon_time=5,
        pulse_time=0.01,
    )
    stub_switches(cover)
    cover.travel_calc.set_position(0)
    gate = Gate()

    async def sleep(delay):
        if delay == 5:
            await gate()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(travel_calculator, "time", clock),
        patch.object(cover_base, "time", clock),
        patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new=sleep,
        ),
    ):
        await cover.async_open_cover()
        await asyncio.sleep(0)
        clock.advance(10.1)
        await cover.auto_stop_if_necessary()
        await gate.parked()
        await cover.async_will_remove_from_hass()
        gate.proceed.set()
        await asyncio.sleep(0)
    data = _mock_position_store.async_save.await_args.args[1]
    replacement = make_cover(control_mode="single_button")
    replacement._apply_restored_extra(data)
    replacement.travel_calc.set_position(data["position"])
    stub_switches(replacement)
    next_stop = plan(replacement._phase, Action.STOP)
    with (
        patch.object(replacement, "async_write_ha_state"),
        patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new=AsyncMock(),
        ),
    ):
        await replacement.async_stop_cover()
        await asyncio.sleep(0)
    presses = [
        call
        for call in replacement.hass.services.async_call.call_args_list
        if call.args[1] == "turn_on"
    ]
    print(
        f"endpoint margin: stored={data}; replacement STOP plan={next_stop}; actual STOP presses={len(presses)}"
    )
    assert data["position"] == 100
    assert data["phase"] == Phase.AT_OPEN.value
    assert next_stop == []
    assert presses == []


async def test_single_button_removal_between_nudge_presses_saves_stopped_position(
    make_cover, _mock_position_store
):
    """An interrupted nudge leaves the phase exact and the position unknown.

    The tracker counted the planned direction, not the nudges, so its
    position estimate cannot be restored.
    """
    from custom_components.cover_time_based import cover_base, travel_calculator
    from custom_components.cover_time_based.single_button_cycle import PRESS_TRANSITION

    clock = FakeClock()
    cover = make_cover(
        control_mode="single_button",
        travel_time_open=10,
        travel_time_close=10,
        pulse_time=0.1,
    )
    stub_switches(cover)
    cover.travel_calc.set_position(50)
    cover._phase = Phase.STOPPED_AFTER_UP
    physical_phase = Phase.STOPPED_AFTER_UP
    physical_position = 50.0
    gate = Gate()
    gaps = 0

    async def service(domain, name, data, *_):
        nonlocal physical_phase
        if name == "turn_on":
            physical_phase = PRESS_TRANSITION[physical_phase]

    async def sleep(delay):
        nonlocal physical_position, gaps
        if delay == 1:
            gaps += 1
            if gaps == 2:
                await gate()
        if physical_phase == Phase.MOVING_DOWN:
            physical_position -= delay * 10
        elif physical_phase == Phase.MOVING_UP:
            physical_position += delay * 10
        clock.advance(delay)

    cover.hass.services.async_call.side_effect = service
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover_base, "time", clock),
        patch.object(travel_calculator, "time", clock),
        patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new=sleep,
        ),
    ):
        await cover.async_open_cover()
        await gate.parked()
        assert physical_phase == Phase.STOPPED_AFTER_DOWN
        await cover.async_will_remove_from_hass()
        gate.proceed.set()
        await asyncio.sleep(0)
    data = _mock_position_store.async_save.await_args.args[1]
    print(f"between presses: physical={physical_position}; stored={data}")
    # Preserve the exact phase, but discard the position the nudges invalidated.
    assert "position" not in data, (data, physical_position)
    assert data["phase"] == Phase.STOPPED_AFTER_DOWN.value
    _mock_position_store.async_get.return_value = data
    replacement = make_cover(control_mode="single_button")
    await replacement.async_added_to_hass()
    assert replacement.travel_calc.current_position() is None
    assert replacement._phase is Phase.STOPPED_AFTER_DOWN
    assert plan(replacement._phase, Action.STOP) == []
    assert plan(replacement._phase, Action.OPEN) == [Phase.MOVING_UP]


async def test_single_button_removal_during_delayed_departure_parks_at_destination(
    make_cover, _mock_position_store
):
    """An idle tracker at departure must not anchor the motor at that endpoint."""
    cover = make_cover(
        control_mode=CONTROL_MODE_SINGLE_BUTTON,
        travel_time_open=10,
        travel_time_close=10,
        travel_startup_delay=2,
    )
    stub_switches(cover)
    cover.travel_calc.set_position(100)
    cover._phase = Phase.AT_OPEN

    with patch.object(cover, "async_write_ha_state"), single_button_sleep_patch():
        await cover.async_close_cover()
        assert cover._press_task is not None
        await cover._press_task
        assert cover._phase is Phase.MOVING_DOWN
        assert not cover.travel_calc.is_traveling()
        assert cover.travel_calc.current_position() == 100
        assert cover._startup_delay_task is not None
        assert not cover._startup_delay_task.done()
        await cover.async_will_remove_from_hass()

    data = _mock_position_store.async_save.await_args.args[1]
    assert data == {"position": 0, "phase": "at_closed"}


async def test_single_button_removal_during_opposite_nudge_uses_phase(
    make_cover, _mock_position_store
):
    """A nudge drives the motor the other way while the tracker still reads open.

    Removal must record where the cycle actually leaves the cover — its phase —
    not the direction the tracker was seeded with before the nudge began.
    """
    cover = make_cover(control_mode=CONTROL_MODE_SINGLE_BUTTON, pulse_time=0.01)
    stub_switches(cover)
    cover.travel_calc.set_position(50)
    cover._phase = Phase.STOPPED_AFTER_UP
    gate = Gate()

    async def sleep(delay):
        if delay == 1:
            await gate()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new=sleep,
        ),
    ):
        await cover.async_open_cover()
        await gate.parked()
        assert cover._phase == Phase.MOVING_DOWN
        assert cover.travel_calc.is_opening()
        await cover.async_will_remove_from_hass()
        gate.proceed.set()
        await asyncio.sleep(0)

    assert _mock_position_store.async_save.await_args.args[1] == {
        "position": 0,
        "phase": "at_closed",
    }
