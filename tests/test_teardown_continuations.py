"""Removal must silence continuations waiting between movement phases.

Every card save reloads the entry and replaces its entity. A tilt restore,
recalibrated second leg, pre-step or reversal that resumes after removal must
leave the relays, trackers and replacement's saved position alone. Stops
already in flight must still reach the hardware.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import SERVICE_OPEN_COVER
from homeassistant.core import State

from custom_components.cover_time_based.calibration import CalibrationState
from custom_components.cover_time_based.cover_base import CoverTimeBased
from tests.helpers import relay_calls, stub_switches


class Gate:
    """An awaitable stand-in for a continuation's await.

    Signals when the continuation parks on it and blocks until released, so the
    test can run removal at exactly that point. Only the first call gates;
    later calls (leg B's own settle, a replacement restore's gap) pass straight
    through so the test never deadlocks on them.
    """

    def __init__(self):
        self.entered = asyncio.Event()
        self.proceed = asyncio.Event()
        self.calls = 0

    async def __call__(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls > 1:
            return
        self.entered.set()
        await self.proceed.wait()

    async def parked(self):
        await asyncio.wait_for(self.entered.wait(), 2)


def assert_quiescent(cover, store, mark, saves, *, what=""):
    """Report every forbidden effect of a resumed continuation together.

    Checking all symptoms in one assertion shows whether it started a motor,
    restarted tracking, armed a timer or overwrote the replacement's record.
    """
    problems = []
    after = [
        call
        for call in relay_calls(cover, mark)
        if call[0] in CoverTimeBased._MOTOR_STARTING_SERVICES
    ]
    if after:
        problems.append(f"drove the relays: {after}")
    if cover._unsubscribe_auto_updater is not None:
        problems.append("re-armed the auto-updater")
    if cover._delay_task is not None and not cover._delay_task.done():
        problems.append("armed a new endpoint run-on stop")
    if store.async_save.call_count != saves:
        problems.append("wrote the position store")
    if cover.travel_calc.is_traveling() or (
        cover._has_tilt_support() and cover.tilt_calc.is_traveling()
    ):
        problems.append("restarted position tracking")
    assert not problems, f"removed entity {what}: " + "; ".join(problems)


def _inline_cover(make_cover, **kw):
    """Shared-motor tilt: the restore reverses the travel motor itself."""
    return make_cover(tilt_time_close=2.0, tilt_time_open=2.0, tilt_mode="inline", **kw)


def _dual_motor_cover(make_cover, **kw):
    return make_cover(
        tilt_mode="dual_motor",
        tilt_time_close=5.0,
        tilt_time_open=5.0,
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        **kw,
    )


# ---------------------------------------------------------------------------
# (a) shared-motor tilt restore, parked in the settle sleep
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_removal_during_inline_tilt_restore_settle_is_silent(
    make_cover, _mock_position_store
):
    """Removal during the restore's settle gap must prevent its reversal.

    The restore has sent STOP before waiting in _direction_change_delay;
    removal must invalidate that restore before the wait resumes.
    """
    cover = _inline_cover(make_cover)
    stub_switches(cover)
    cover.travel_calc.set_position(80)
    cover.tilt_calc.set_position(100)
    gate = Gate()

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(30)  # closing; restore target = tilt 100
        cover.travel_calc.set_position(30)
        cover.tilt_calc.set_position(0)
        assert cover._tilt_restore_target == 100

        with patch.object(cover, "_direction_change_delay", new=gate):
            task = asyncio.ensure_future(cover.auto_stop_if_necessary())
            await gate.parked()

            await cover.async_will_remove_from_hass()
            mark = len(cover.hass.services.async_call.call_args_list)
            saves = _mock_position_store.async_save.call_count

            gate.proceed.set()
            await asyncio.wait_for(task, 2)

    assert_quiescent(
        cover, _mock_position_store, mark, saves, what="after its settle sleep elapsed"
    )


# ---------------------------------------------------------------------------
# (b) dual-motor tilt restore, parked before the tilt motor start
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_removal_during_dual_motor_restore_does_not_start_tilt_motor(
    make_cover, _mock_position_store
):
    """Removal during the travel stop must prevent the dedicated tilt start."""
    cover = _dual_motor_cover(make_cover)
    stub_switches(cover)
    cover.travel_calc.set_position(30)
    cover.tilt_calc.set_position(0)
    cover._tilt_restore_target = 100
    gate = Gate()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_stop_travel_relay_if_needed", new=gate),
    ):
        task = asyncio.ensure_future(cover._start_tilt_restore())
        await gate.parked()

        await cover.async_will_remove_from_hass()
        mark = len(cover.hass.services.async_call.call_args_list)
        saves = _mock_position_store.async_save.call_count

        gate.proceed.set()
        await asyncio.wait_for(task, 2)

    assert_quiescent(
        cover, _mock_position_store, mark, saves, what="after the travel stop returned"
    )


# ---------------------------------------------------------------------------
# (c) recalibrated leg B (#179)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_removal_during_recalibrated_runon_wait_does_not_run_leg_b(
    make_cover, _mock_position_store
):
    """Cancelling the run-on stop must invalidate the waiting second leg.

    asyncio.wait releases when removal cancels the stop task, so the second
    leg must check ownership before it can command the motor.
    """
    cover = make_cover(recalibrate_before_position=True, endpoint_runon_time=5.0)
    stub_switches(cover)
    cover.travel_calc.set_position(75)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_position(25)  # leg A: full open, leg B armed for 25
        assert cover._pending_recalibrated_target == 25
        cover.travel_calc.set_position(100)  # leg A arrives at the datum

        task = asyncio.ensure_future(cover.auto_stop_if_necessary())
        await asyncio.sleep(0.05)  # park in asyncio.wait({delay_task})
        assert cover._delay_task is not None and not cover._delay_task.done()

        await cover.async_will_remove_from_hass()
        mark = len(cover.hass.services.async_call.call_args_list)
        saves = _mock_position_store.async_save.call_count

        await asyncio.wait_for(task, 2)

    assert_quiescent(cover, _mock_position_store, mark, saves, what="ran leg B")


@pytest.mark.asyncio
async def test_removal_during_recalibrated_settle_does_not_run_leg_b(
    make_cover, _mock_position_store
):
    """Variant: no run-on armed, so leg B is parked in the settle gap instead."""
    cover = make_cover(recalibrate_before_position=True, endpoint_runon_time=0)
    stub_switches(cover)
    cover.travel_calc.set_position(75)
    gate = Gate()

    with patch.object(cover, "async_write_ha_state"):
        with patch.object(cover, "_direction_change_delay", new=AsyncMock()):
            await cover.set_position(25)
        assert cover._pending_recalibrated_target == 25
        cover.travel_calc.set_position(100)

        with patch.object(cover, "_direction_change_delay", new=gate):
            task = asyncio.ensure_future(cover.auto_stop_if_necessary())
            await gate.parked()

            await cover.async_will_remove_from_hass()
            mark = len(cover.hass.services.async_call.call_args_list)
            saves = _mock_position_store.async_save.call_count

            gate.proceed.set()
            await asyncio.wait_for(task, 2)

    assert_quiescent(cover, _mock_position_store, mark, saves, what="ran leg B")


# ---------------------------------------------------------------------------
# (d) reversal settle inside a service call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_removal_during_reversal_settle_does_not_energize_the_relay(
    make_cover, _mock_position_store
):
    """Removal must invalidate a set_position reversal waiting for the motor."""
    cover = make_cover()  # switch mode
    stub_switches(cover)
    cover.travel_calc.set_position(50)
    gate = Gate()

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()
        assert cover.travel_calc.is_closing()

        with patch.object(cover, "_direction_change_delay", new=gate):
            task = asyncio.ensure_future(cover.set_position(80))
            await gate.parked()

            await cover.async_will_remove_from_hass()
            mark = len(cover.hass.services.async_call.call_args_list)
            saves = _mock_position_store.async_save.call_count

            gate.proceed.set()
            await asyncio.wait_for(task, 2)

    assert_quiescent(
        cover, _mock_position_store, mark, saves, what="after its settle gap"
    )


@pytest.mark.asyncio
async def test_removal_during_external_open_reversal_arms_no_new_ghost_timer(
    make_cover,
):
    """An external reversal must not arm a run-on stop after removal.

    External-trigger suppression keeps the relay silent, but the resumed
    command must also leave the removed entity's timers inactive.
    """
    cover = make_cover()  # switch mode
    stub_switches(cover)
    cover.travel_calc.set_position(100)
    gate = Gate()

    async def external_open():
        cover._triggered_externally = True  # keyed on the running task
        await cover.async_open_cover()

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()
        assert cover.travel_calc.is_closing()

        with patch.object(cover, "_direction_change_delay", new=gate):
            task = asyncio.ensure_future(external_open())
            await gate.parked()

            await cover.async_will_remove_from_hass()
            gate.proceed.set()
            await asyncio.wait_for(task, 2)

        armed = cover._delay_task is not None and not cover._delay_task.done()

    assert not armed, (
        "the removed entity armed a new endpoint run-on stop after removal"
    )


# ---------------------------------------------------------------------------
# (e) removal owns the stop when it cancels the endpoint run-on
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_removal_with_pending_runon_de_energizes_the_latched_relay(make_cover):
    """Removal must stop a latched relay when it cancels the scheduled stop.

    The relay needs an immediate release because a delayed stop could stop
    the replacement entity's movement.
    """
    cover = make_cover(
        travel_time_close=0.2, travel_time_open=0.2, endpoint_runon_time=5.0
    )
    stub_switches(cover)
    cover.travel_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()
        await asyncio.sleep(0.3)
        cover.travel_calc.set_position(100)
        await cover.auto_stop_if_necessary()  # arms the endpoint run-on
        assert cover._delay_task is not None and not cover._delay_task.done()

        mark = len(cover.hass.services.async_call.call_args_list)
        await cover.async_will_remove_from_hass()
        await asyncio.sleep(0.05)

    offs = [c for c in relay_calls(cover, mark) if c[0] == "turn_off"]
    assert offs, (
        "removal cancelled the only pending stop and left the relay latched ON: "
        f"{relay_calls(cover, mark)}"
    )


@pytest.mark.asyncio
async def test_removal_mid_overhead_calibration_sends_one_pulse_stop(make_cover):
    """Calibration owns the stop even while its stepped move has a live tracker."""
    cover = make_cover(
        control_mode="pulse",
        stop_switch="switch.stop",
        send_endpoint_stop=True,
    )
    stub_switches(cover)
    cover._calibration = CalibrationState(
        attribute="travel_startup_delay",
        timeout=600,
        move_command=SERVICE_OPEN_COVER,
    )
    cover.travel_calc.set_position(0)
    cover.travel_calc.start_travel(10)
    with patch.object(cover, "async_write_ha_state"):
        await cover._calibration_drive(SERVICE_OPEN_COVER)
        assert cover.travel_calc.is_traveling()
        mark = len(cover.hass.services.async_call.call_args_list)

        await cover.async_will_remove_from_hass()

    assert relay_calls(cover, mark).count(("turn_on", "switch.stop")) == 1
    assert cover._calibration is None
    assert not cover.travel_calc.is_traveling()


@pytest.mark.asyncio
async def test_removal_mid_travel_de_energizes_the_latched_relay(
    make_cover, _mock_position_store
):
    """A plain move in progress: the relay is latched and nothing else stops it."""
    cover = make_cover(travel_time_close=5.0, travel_time_open=5.0)
    stub_switches(cover)
    cover.travel_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()
        await asyncio.sleep(0.2)
        assert cover.travel_calc.is_traveling()
        mark = len(cover.hass.services.async_call.call_args_list)
        await cover.async_will_remove_from_hass()

    offs = [c for c in relay_calls(cover, mark) if c[0] == "turn_off"]
    assert offs, f"relay left latched: {relay_calls(cover, mark)}"
    assert not cover.travel_calc.is_traveling()
    assert cover.travel_calc.current_position() not in (None, 0, 100)
    _, data = _mock_position_store.async_save.await_args.args
    assert data["position"] == cover.travel_calc.current_position()


@pytest.mark.asyncio
async def test_removal_during_startup_delay_de_energizes_the_latched_relay(
    make_cover,
):
    """A deferred start cancelled by removal leaves the relay ON with no tracker."""
    cover = make_cover(
        travel_time_close=5.0, travel_time_open=5.0, travel_startup_delay=1.0
    )
    stub_switches(cover)
    cover.travel_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()
        assert cover._startup_delay_task is not None
        assert not cover._startup_delay_task.done()
        mark = len(cover.hass.services.async_call.call_args_list)
        await cover.async_will_remove_from_hass()

    offs = [c for c in relay_calls(cover, mark) if c[0] == "turn_off"]
    assert offs, f"relay left latched: {relay_calls(cover, mark)}"


@pytest.mark.asyncio
async def test_removal_mid_tilt_motor_move_stops_the_tilt_relays(make_cover):
    """A dedicated tilt motor is owed a tilt stop, which the travel STOP never sends."""
    cover = _dual_motor_cover(make_cover)
    stub_switches(cover)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(80)
        await asyncio.sleep(0.2)
        assert cover.tilt_calc.is_traveling()
        mark = len(cover.hass.services.async_call.call_args_list)
        await cover.async_will_remove_from_hass()

    offs = {c[1] for c in relay_calls(cover, mark) if c[0] == "turn_off"}
    assert "switch.tilt_open" in offs, (
        f"tilt relay left latched: {relay_calls(cover, mark)}"
    )


@pytest.mark.asyncio
async def test_removal_mid_inline_tilt_de_energizes_the_travel_relay(make_cover):
    """Shared-motor tilt drives the travel motor with only tilt_calc travelling."""
    cover = _inline_cover(make_cover, travel_time_close=5.0, travel_time_open=5.0)
    stub_switches(cover)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(80)
        await asyncio.sleep(0.2)
        assert cover.tilt_calc.is_traveling()
        assert not cover.travel_calc.is_traveling()
        mark = len(cover.hass.services.async_call.call_args_list)
        await cover.async_will_remove_from_hass()

    offs = [c for c in relay_calls(cover, mark) if c[0] == "turn_off"]
    assert offs, f"travel relay left latched: {relay_calls(cover, mark)}"


@pytest.mark.asyncio
async def test_removal_mid_travel_on_toggle_sends_nothing_and_parks_at_the_limit(
    make_cover, _mock_position_store
):
    """Momentary hardware runs on to its limit; a stop tap there would be a move.

    The axis is parked at the limit it is heading for, so the replacement
    restores where the motor will actually be.
    """
    cover = make_cover(
        control_mode="toggle", travel_time_close=5.0, travel_time_open=5.0
    )
    stub_switches(cover)
    cover.travel_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()
        await asyncio.sleep(0.2)
        assert cover.travel_calc.is_traveling()
        mark = len(cover.hass.services.async_call.call_args_list)
        await cover.async_will_remove_from_hass()

    assert relay_calls(cover, mark) == []
    assert cover.travel_calc.current_position() == 100
    _, data = _mock_position_store.async_save.await_args.args
    assert data["position"] == 100


@pytest.mark.asyncio
async def test_removed_entity_restore_completion_overwrites_position_store(
    make_cover, _mock_position_store
):
    """A restore completing after removal must not overwrite the saved position."""
    cover = _inline_cover(make_cover)
    stub_switches(cover)
    cover.travel_calc.set_position(80)
    cover.tilt_calc.set_position(100)
    gate = Gate()

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(30)
        cover.travel_calc.set_position(30)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "_direction_change_delay", new=gate):
            task = asyncio.ensure_future(cover.auto_stop_if_necessary())
            await gate.parked()
            await cover.async_will_remove_from_hass()
            saves = _mock_position_store.async_save.call_count
            gate.proceed.set()
            await asyncio.wait_for(task, 2)

        # A stale updater tick may still report the restore target after removal;
        # it must not persist that position.
        cover.tilt_calc.set_position(100)
        await cover.auto_stop_if_necessary()

    assert _mock_position_store.async_save.call_count == saves, (
        "a removed entity persisted a position after removal"
    )


# ---------------------------------------------------------------------------
# (g) removal lands inside an await that precedes the continuation's check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_removal_during_pre_step_tilt_stop_does_not_start_travel(
    make_cover, _mock_position_store
):
    """Removal during a dual-motor pre-step's tilt stop must prevent travel.

    The continuation already captured its travel target before the await;
    clearing the pending target alone cannot prevent the resumed start.
    """
    cover = _dual_motor_cover(make_cover, travel_time_close=5.0, travel_time_open=5.0)
    stub_switches(cover)
    cover.travel_calc.set_position(100)
    cover.tilt_calc.set_position(0)
    gate = Gate()

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(20)  # tilt-to-safe pre-step first
        assert cover._pending_travel_target == 20
        cover.tilt_calc.set_position(100)  # pre-step arrives

        with patch.object(cover, "_send_tilt_stop", new=gate):
            task = asyncio.ensure_future(cover.auto_stop_if_necessary())
            await gate.parked()

            await cover.async_will_remove_from_hass()
            mark = len(cover.hass.services.async_call.call_args_list)
            saves = _mock_position_store.async_save.call_count

            gate.proceed.set()
            await asyncio.wait_for(task, 2)

    assert_quiescent(
        cover, _mock_position_store, mark, saves, what="after the pre-step tilt stop"
    )


@pytest.mark.asyncio
async def test_removal_between_a_switch_commands_off_and_on_refuses_the_on(
    make_cover, _mock_position_store
):
    """Switch mode sends turn_off(opposite) then turn_on(direction).

    Removal landing between the two must refuse the turn_on: the command
    has already passed every command-level check, so only the service call
    itself can stop it.
    """
    cover = make_cover(travel_time_close=5.0, travel_time_open=5.0)
    stub_switches(cover)
    cover.travel_calc.set_position(0)
    gate = Gate()
    real_call = cover.hass.services.async_call

    async def gated_call(domain, service, data, *args, **kwargs):
        result = await real_call(domain, service, data, *args, **kwargs)
        if service == "turn_off":
            await gate()  # park after the OFF has been recorded
        return result

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover.hass.services, "async_call", side_effect=gated_call),
    ):
        task = asyncio.ensure_future(cover.async_open_cover())
        await gate.parked()

        await cover.async_will_remove_from_hass()
        mark = len(real_call.call_args_list)
        saves = _mock_position_store.async_save.call_count

        gate.proceed.set()
        await asyncio.wait_for(task, 2)

    ons = [c for c in relay_calls(cover, mark) if c[0] == "turn_on"]
    assert not ons, f"removed entity energised a relay: {relay_calls(cover, mark)}"
    assert_quiescent(
        cover, _mock_position_store, mark, saves, what="after its relay call returned"
    )


@pytest.mark.asyncio
async def test_deferred_start_elapsing_inside_removal_does_not_arm_the_updater(
    make_cover,
):
    """Removal's first await must come after every synchronous cancel.

    If the startup-delay task is cancelled only after removal has yielded
    (to the background-pulse cleanup), a delay that elapses during that
    yield starts tracking and re-arms the updater on the dead entity.
    """
    cover = make_cover(
        travel_time_close=5.0, travel_time_open=5.0, travel_startup_delay=0.05
    )
    stub_switches(cover)
    cover.travel_calc.set_position(0)

    async def slow_cleanup():
        await asyncio.sleep(0.2)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()
        assert cover._startup_delay_task is not None
        with patch.object(cover, "_cancel_background_pulses", new=slow_cleanup):
            await cover.async_will_remove_from_hass()

    assert cover._unsubscribe_auto_updater is None, "updater armed during removal"
    assert not cover.travel_calc.is_traveling(), "tracking started during removal"


@pytest.mark.asyncio
async def test_persist_parked_on_the_store_does_not_write_after_removal(
    make_cover, _mock_position_store
):
    """A persist that passed its guard and is awaiting the store must re-check."""
    cover = make_cover()
    cover.travel_calc.set_position(40)
    gate = Gate()
    store = _mock_position_store

    async def gated_get_store(_hass):
        await gate()
        return store

    with patch(
        "custom_components.cover_time_based.cover_base.async_get_position_store",
        new=gated_get_store,
    ):
        task = asyncio.ensure_future(cover._async_persist_position())
        await gate.parked()
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_will_remove_from_hass()
        saves = store.async_save.call_count
        gate.proceed.set()
        await asyncio.wait_for(task, 2)

    assert store.async_save.call_count == saves, (
        "a persist parked across removal wrote the store"
    )


@pytest.mark.asyncio
async def test_removal_refuses_a_subclass_tilt_start(make_cover, _mock_position_store):
    """Toggle overrides _send_tilt_open without calling the base; the guard must still bite."""
    cover = make_cover(
        control_mode="toggle",
        tilt_mode="dual_motor",
        tilt_time_close=5.0,
        tilt_time_open=5.0,
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
    )
    stub_switches(cover)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_will_remove_from_hass()
        mark = len(cover.hass.services.async_call.call_args_list)
        await cover._send_tilt_open()

    ons = [c for c in relay_calls(cover, mark) if c[0] == "turn_on"]
    assert ons == [], (
        f"removed toggle entity pulsed a tilt relay: {relay_calls(cover, mark)}"
    )


@pytest.mark.asyncio
async def test_pulse_stop_interrupted_by_removal_still_pulses_the_stop_relay(
    make_cover,
):
    """Auto-stop stops its tracker, then sends STOP; removal lands mid-STOP.

    Pulse mode's STOP is turn_off(direction relays) then turn_on(stop relay).
    Removal landing between them sees no tracker travelling and no timer, so
    it owes nothing itself; the resumed STOP's turn_on must therefore not be
    refused, or a latching pulse controller never receives its stop.
    """
    cover = make_cover(
        control_mode="pulse",
        travel_time_close=0.2,
        travel_time_open=0.2,
        stop_switch="switch.stop",
    )
    stub_switches(cover)
    cover.travel_calc.set_position(0)
    gate = Gate()
    real_call = cover.hass.services.async_call

    async def gated_call(domain, service, data, *args, **kwargs):
        result = await real_call(domain, service, data, *args, **kwargs)
        if service == "turn_off":
            await gate()  # park after the first direction-relay OFF of the STOP
        return result

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(50)
        await asyncio.sleep(0.15)
        cover.travel_calc.set_position(50)
        with patch.object(cover.hass.services, "async_call", side_effect=gated_call):
            task = asyncio.ensure_future(cover.auto_stop_if_necessary())
            await gate.parked()
            await cover.async_will_remove_from_hass()
            mark = len(real_call.call_args_list)
            gate.proceed.set()
            await asyncio.wait_for(task, 2)

    ons = [c for c in relay_calls(cover, mark) if c[0] == "turn_on"]
    assert ("turn_on", "switch.stop") in ons, (
        f"the interrupted STOP never pulsed the stop relay: {relay_calls(cover, mark)}"
    )


@pytest.mark.asyncio
async def test_removed_wrapped_cover_can_stop_via_current_position():
    """A device without native STOP still receives its position-based stop."""
    from tests.test_cover_wrapped import _make_wrapped_cover, _set_wrapped_features

    cover = _make_wrapped_cover()
    _set_wrapped_features(cover, 7)  # SET_POSITION, no STOP
    cover.travel_calc.set_position(43)
    await cover.async_will_remove_from_hass()

    await cover._send_stop()

    cover.hass.services.async_call.assert_awaited_once_with(
        "cover",
        "set_cover_position",
        {"entity_id": "cover.inner", "position": 43},
        False,
    )


@pytest.mark.asyncio
async def test_removal_stop_does_not_leave_relay_echo_timers(make_cover):
    """A stop still releases the motor after its echo listener is removed."""
    cover = make_cover(travel_time_close=5.0, travel_time_open=5.0)
    stub_switches(cover)
    cover.travel_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()
        stub_switches(cover, on=("switch.open",))
        mark = len(cover.hass.services.async_call.call_args_list)
        await cover.async_will_remove_from_hass()

    assert ("turn_off", "switch.open") in relay_calls(cover, mark)
    assert cover._pending_switch_timers == {}


@pytest.mark.parametrize("direction", ["open", "close"])
@pytest.mark.parametrize("axis", ["travel", "inline", "dual_motor"])
async def test_removal_inside_latched_turn_on_releases_relay(
    make_cover, direction, axis
):
    """An ON already delivered must be stopped even before tracking is armed."""
    options = {}
    if axis != "travel":
        options.update(tilt_mode=axis, tilt_time_open=10, tilt_time_close=10)
    if axis == "dual_motor":
        options.update(
            tilt_open_switch="switch.tilt_open", tilt_close_switch="switch.tilt_close"
        )
    cover = make_cover(**options)
    cover.travel_calc.set_position(50)
    if axis != "travel":
        cover.tilt_calc.set_position(50)
    states = {}
    events = []
    gate = Gate()

    def get_state(entity):
        return State(entity, states.get(entity, "off"))

    cover.hass.states.get = get_state

    async def service(domain, name, data, *_args):
        entity = data["entity_id"]
        events.append((name, entity))
        states[entity] = "on" if name == "turn_on" else "off"
        if name == "turn_on":
            await gate()

    cover.hass.services.async_call.side_effect = service
    command = getattr(
        cover, f"async_{direction}_cover" + ("_tilt" if axis != "travel" else "")
    )
    with patch.object(cover, "async_write_ha_state"):
        task = asyncio.create_task(command())
        try:
            await gate.parked()
            await cover.async_will_remove_from_hass()
            at_removal = dict(states)
        finally:
            gate.proceed.set()
            await asyncio.wait_for(task, 2)
    print(f"{axis}/{direction}: removal={at_removal}; final={states}; calls={events}")
    assert "on" not in at_removal.values(), (
        f"removal returned with relay ON: {at_removal}; calls={events}"
    )
    assert "on" not in states.values()
    assert cover._unsubscribe_auto_updater is None


@pytest.mark.parametrize("mode", ["pulse", "wrapped_echo"])
@pytest.mark.parametrize("direction", ["open", "close"])
async def test_removal_inside_nonself_start_stops_motor(make_cover, mode, direction):
    """A pulse latch or an endstop-less wrapped motor needs its removal stop."""
    from tests.test_cover_wrapped import _set_wrapped_features

    if mode == "pulse":
        cover = make_cover(
            control_mode="pulse", stop_switch="switch.stop", pulse_time=0.01
        )
        stub_switches(cover)
    else:
        cover = make_cover(
            cover_entity_id="cover.inner", reports_command_not_endpoint=True
        )
        _set_wrapped_features(cover, 11)
    cover.travel_calc.set_position(50)
    gate = Gate()
    running = False
    events = []

    async def service(domain, name, data, *_):
        nonlocal running
        events.append((name, data["entity_id"]))
        if name == "stop_cover" or (
            name == "turn_on" and data["entity_id"] == "switch.stop"
        ):
            running = False
        elif name in ("open_cover", "close_cover", "turn_on"):
            running = True
            await gate()

    cover.hass.services.async_call.side_effect = service
    with patch.object(cover, "async_write_ha_state"):
        task = asyncio.create_task(getattr(cover, f"async_{direction}_cover")())
        try:
            await gate.parked()
            await cover.async_will_remove_from_hass()
            running_at_removal = running
        finally:
            gate.proceed.set()
            await asyncio.wait_for(task, 2)
    print(
        f"{mode}/{direction}: motor running at removal={running_at_removal}; calls={events}"
    )
    assert not running_at_removal


async def test_removal_at_pending_travel_start_releases_travel_relay(make_cover):
    """The tilt-to-safe continuation must own its new travel relay before yielding."""
    cover = make_cover(
        tilt_mode="dual_motor",
        tilt_time_open=10,
        tilt_time_close=10,
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
    )
    stub_switches(cover)
    cover.travel_calc.set_position(30)
    cover.tilt_calc.set_position(100)
    cover._self_initiated_movement = True
    cover._pending_travel_target = 20
    cover._pending_travel_command = "close_cover"
    cover._moving_tilt_motor = True
    states = {}

    async def service(domain, name, data, *_):
        states[data["entity_id"]] = "on" if name == "turn_on" else "off"

    cover.hass.services.async_call.side_effect = service
    original = cover._async_handle_command
    gate = Gate()

    async def command(*args):
        await original(*args)
        await gate()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", new=command),
    ):
        task = asyncio.create_task(cover.auto_stop_if_necessary())
        try:
            await gate.parked()
            await cover.async_will_remove_from_hass()
        finally:
            gate.proceed.set()
            await asyncio.wait_for(task, 2)
    print(f"pending travel: final relays={states}")
    assert states["switch.close"] == "off"
