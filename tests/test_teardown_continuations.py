"""Entity removal must silence the parked continuation coroutines (item 3.19).

``async_will_remove_from_hass`` cancels the two ghost *timers* (the endpoint
run-on stop and the startup-delay arming) but nothing cancels or supersedes the
continuations that run on the auto-updater's fire-and-forget task
(``hass.async_create_task(self.auto_stop_if_necessary())``, never retained) or
inside a plain service-call coroutine:

* ``_start_tilt_restore`` parked in its settle sleep / travel stop,
* ``_maybe_start_recalibrated_leg`` parked in ``asyncio.wait({delay_task})`` or
  in ``_settle_before_reversing``,
* ``_settle_before_reversing`` itself, inside a reversal.

Every card save reloads the config entry, which removes and re-creates the
entity. A continuation that resumes after removal drives the physical relays,
re-arms the auto-updater and persists a position on behalf of an entity Home
Assistant has already thrown away.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

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


def assert_quiescent(cover, store, mark, saves, *, tracking=True, what=""):
    """Every way a removed entity can still act, reported together.

    Only motor-starting relay calls are flagged; cleanup stops remain permitted.

    One assert per symptom would stop at the first, hiding whether the others
    also fire — and the point of these tests is the full blast radius of one
    resumed continuation.
    """
    problems = []
    after = [
        call
        for call in relay_calls(cover, mark)
        if call[0]
        in {
            "turn_on",
            "open_cover",
            "close_cover",
            "set_cover_position",
            "open_cover_tilt",
            "close_cover_tilt",
            "set_cover_tilt_position",
        }
    ]
    if after:
        problems.append(f"drove the relays: {after}")
    if cover._unsubscribe_auto_updater is not None:
        problems.append("re-armed the auto-updater")
    if cover._delay_task is not None and not cover._delay_task.done():
        problems.append("armed a new endpoint run-on stop")
    if store.async_save.call_count != saves:
        problems.append("wrote the position store")
    if tracking and (
        cover.travel_calc.is_traveling()
        or (cover._has_tilt_support() and cover.tilt_calc.is_traveling())
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
    """Removal mid-settle must not let the old entity reverse the motor.

    The restore has already sent its STOP and is asleep in
    ``_direction_change_delay``. Nothing in removal touches
    ``_tilt_restore_active``/``_tilt_restore_epoch``, so the post-sleep
    ``_tilt_restore_superseded`` check passes and the dead entity energizes the
    travel relay and re-subscribes the auto-updater.
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
    """Same hole on the dedicated-tilt-motor branch.

    The dual-motor restore's await is ``_stop_travel_relay_if_needed`` (a real
    relay service call). Removal landing there leaves the epoch untouched, so
    the removed entity goes on to energize the tilt relay.
    """
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
    """Removal cancels ``_delay_task``, which *releases* the run-on wait.

    ``_maybe_start_recalibrated_leg`` parks in ``asyncio.wait({delay_task})``
    precisely so a cancellation of its own task cannot kill the pending
    ``_delayed_stop``. Removal cancels that stop directly, so the wait returns
    immediately, the epoch is unchanged, and leg B drives the relays on an
    entity that no longer exists.
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
    """A ``set_position`` reversal is parked in ``_settle_before_reversing``.

    ``_settle_before_reversing`` compares ``_movement_epoch`` across its own
    sleep. Removal never bumps that epoch, so the reversal resumes and turns
    the open relay on for a removed entity — on switch mode a latched relay
    with nothing left to switch it off.
    """
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
    """The external variant of the same await, where the relay stays silent.

    An external open-while-closing takes the reversal through
    ``_settle_before_reversing`` too, but the relay command is swallowed by the
    external-trigger echo suppression — so the visible damage is different, not
    absent: the resumed reversal arms a *fresh* ``_delay_task`` on the removed
    entity, after removal has already cancelled the one it knew about. Nothing
    will ever cancel that one.
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
# (e) the run-on stop that removal cancels never de-energizes the relay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_removal_with_pending_runon_de_energizes_the_latched_relay(make_cover):
    """A latched relay whose only scheduled stop is cancelled stays ON.

    ``_delayed_stop`` is the sole thing that will ever take the endpoint run-on
    relay down. ``async_will_remove_from_hass`` cancels it (correctly — a late
    stop would hit the *reloaded* entity), but sends no stop of its own, so
    switch-mode hardware is left energized and drives past its endpoint. This
    is the same hazard the mid-calibration branch of removal already handles.
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
    """The store write is downstream of the re-armed auto-updater.

    The other tests catch the removed entity re-subscribing the auto-updater
    and restarting the tracker; this pins what that costs. The next tick
    reaching the target runs ``auto_stop_if_necessary`` again, whose
    tilt-restore-complete branch persists — a ghost entity writing the position
    key the *reloaded* entity restores from.
    """
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

        # The restore the removed entity started now reaches its target — in
        # production this is its own re-armed auto-updater tick.
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
    """Dual-motor pre-step: tilt reached safe, travel is about to be sent.

    ``_start_pending_travel`` captured its target before awaiting the tilt
    stop and checks nothing after it, so the travel relay went out and
    tracking started on the removed entity.
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
