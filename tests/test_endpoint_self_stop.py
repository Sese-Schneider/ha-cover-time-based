"""Endpoint self-stop behaviour.

Motors with internal limit switches self-stop at the physical endpoints
(0% / 100%). For every relay mode whose relays are momentary or delegated
(toggle, pulse, wrapped) the integration must therefore NOT send a stop at
an endpoint — the motor has already stopped, and a stop there is at best
redundant and at worst (toggle) re-pulses the relay and restarts the motor.

Switch mode is the exception: its direction relay is latched ON for the
whole travel, so reaching an endpoint must still de-energize it. Switch
mode therefore keeps both the endpoint stop and endpoint run-on.

Mid-travel stops (position 1..99) are unaffected in every mode — nothing
self-stops there, so the timed stop is essential.
"""

import asyncio

import pytest
from unittest.mock import MagicMock, patch

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from custom_components.cover_time_based.cover import (
    CONTROL_MODE_PULSE,
    CONTROL_MODE_SWITCH,
    CONTROL_MODE_TOGGLE,
)


async def _cancel_tasks(cover):
    tasks = getattr(cover.hass, "_test_tasks", [])
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        tasks.clear()


def _ha_calls(cover):
    """Relay (homeassistant.turn_on/turn_off) service calls."""
    return [
        c
        for c in cover.hass.services.async_call.call_args_list
        if c.args[0] == "homeassistant"
    ]


@pytest.mark.asyncio
async def test_toggle_reaching_endpoint_sends_no_relay_stop(make_cover):
    """Toggle at an endpoint must not re-pulse the relay (issue #105).

    With the default run-on (2.0s) the stop is currently deferred to a
    background ``_delayed_stop`` task, so assert the stop is neither issued
    now nor scheduled.
    """
    cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
    cover._self_initiated_movement = True
    cover._last_command = SERVICE_CLOSE_COVER
    cover.travel_calc.set_position(0)

    cover.hass.services.async_call.reset_mock()
    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    assert _ha_calls(cover) == []
    assert cover._delay_task is None
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_switch_reaching_endpoint_still_de_energizes(make_cover):
    """Switch mode latches the direction relay ON, so an endpoint must still
    turn it OFF. Run-on disabled here so the stop is immediate."""
    cover = make_cover(control_mode=CONTROL_MODE_SWITCH, endpoint_runon_time=0)
    cover._self_initiated_movement = True
    cover._last_command = SERVICE_CLOSE_COVER
    cover.travel_calc.set_position(0)

    cover.hass.services.async_call.reset_mock()
    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    off_calls = [c for c in _ha_calls(cover) if c.args[1] == "turn_off"]
    assert off_calls, "switch mode must de-energize its relays at an endpoint"
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_switch_keeps_endpoint_runon(make_cover):
    """Switch mode keeps run-on: an endpoint schedules the delayed stop."""
    cover = make_cover(control_mode=CONTROL_MODE_SWITCH, endpoint_runon_time=2.0)
    cover._self_initiated_movement = True
    cover._last_command = SERVICE_CLOSE_COVER
    cover.travel_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    assert cover._delay_task is not None
    await _cancel_tasks(cover)


def _stub_switch_on(cover, on_entity):
    """Make ``_switch_is_on`` report only ``on_entity`` as ON."""

    def _get(entity_id):
        state = MagicMock()
        state.state = "on" if entity_id == on_entity else "off"
        return state

    cover.hass.states.get.side_effect = _get


@pytest.mark.asyncio
async def test_switch_external_open_de_energizes_at_endpoint(make_cover):
    """An externally-triggered switch-mode open must still de-energize at the
    endpoint.

    When the direction relay is energized outside HA (a wall switch wired to
    the relay), the observe path tracks the move with ``_self_initiated_movement``
    False, so auto-stop takes its external-skip branch. For momentary modes that
    is correct — the pulse already self-released — but switch mode latches the
    relay ON for the whole travel, so skipping the stop leaves it energized at
    the endpoint forever. The latched relay must be turned off (only if still
    on, mirroring the interlock), exactly as the self-initiated path does.
    """
    cover = make_cover(control_mode=CONTROL_MODE_SWITCH, endpoint_runon_time=0)
    cover._self_initiated_movement = False  # externally triggered move
    cover._last_command = SERVICE_OPEN_COVER
    cover.travel_calc.set_position(100)  # reached the open endpoint
    _stub_switch_on(cover, "switch.open")  # relay still latched ON

    cover.hass.services.async_call.reset_mock()
    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    off_calls = [
        c
        for c in _ha_calls(cover)
        if c.args[1] == "turn_off" and c.args[2].get("entity_id") == "switch.open"
    ]
    assert off_calls, (
        "external switch-mode open must de-energize the latched relay at the endpoint"
    )
    close_off = [
        c
        for c in _ha_calls(cover)
        if c.args[1] == "turn_off" and c.args[2].get("entity_id") == "switch.close"
    ]
    assert not close_off, "must not de-energize the opposite (already-off) relay"
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_pulse_reaching_endpoint_sends_no_relay_stop(make_cover):
    """Pulse mode at an endpoint sends no stop pulse and schedules no run-on."""
    cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
    cover._self_initiated_movement = True
    cover._last_command = SERVICE_CLOSE_COVER
    cover.travel_calc.set_position(0)

    cover.hass.services.async_call.reset_mock()
    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    assert _ha_calls(cover) == []
    assert cover._delay_task is None
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_wrapped_non_native_reaching_endpoint_sends_no_stop(make_cover):
    """A wrapped cover with no native position support self-stops at endpoints
    (real cover + reports its settled state), so no stop_cover is sent."""
    cover = make_cover(cover_entity_id="cover.inner")
    assert not cover._motor_stops_itself()  # mock entity advertises no features
    cover._self_initiated_movement = True
    cover._last_command = SERVICE_CLOSE_COVER
    cover.travel_calc.set_position(0)

    cover.hass.services.async_call.reset_mock()
    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    assert cover.hass.services.async_call.call_args_list == []
    assert cover._delay_task is None
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_toggle_mid_travel_still_stops(make_cover):
    """Mid-travel (not an endpoint) still issues the timed stop in every mode —
    nothing self-stops between the endpoints."""
    cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
    cover._self_initiated_movement = True
    cover._last_command = SERVICE_CLOSE_COVER
    cover.travel_calc.set_position(50)

    cover.hass.services.async_call.reset_mock()
    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    on_calls = [c for c in _ha_calls(cover) if c.args[1] == "turn_on"]
    assert on_calls, "mid-travel stop must still re-pulse the relay"
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_toggle_resync_at_endpoint_schedules_no_stop(make_cover):
    """Commanding to the endpoint we already sit at (resync) re-drives the
    motor but must not schedule a stop for a self-stopping mode (issue #105).

    This is the _async_move_to_endpoint resync path (open-at-100), distinct
    from the auto-stop path.
    """
    cover = make_cover(control_mode=CONTROL_MODE_TOGGLE, endpoint_runon_time=2.0)
    cover.travel_calc.set_position(100)

    cover.hass.services.async_call.reset_mock()
    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()

    # Resync re-pulses the open relay to drive physically to the limit...
    on_calls = [
        c
        for c in _ha_calls(cover)
        if c.args[1] == "turn_on" and c.args[2].get("entity_id") == "switch.open"
    ]
    assert on_calls, "resync should re-pulse the direction relay"
    # ...but must not schedule a run-on/stop that would re-pulse (restart) it.
    assert cover._delay_task is None
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_sequential_close_still_stops_at_closed_without_runon(make_cover):
    """Sequential close-then-tilt-closed drives the motor PAST cover-closed to
    articulate the slats, so travel=0 is not a hard limit — the slats-closed
    position is timed and the motor must be stopped there. A stop is therefore
    sent (toggle re-pulse), but with no run-on (it would overdrive the tilt).
    """
    cover = make_cover(
        control_mode=CONTROL_MODE_TOGGLE,
        tilt_time_close=2.0,
        tilt_time_open=2.0,
        tilt_mode="sequential_close",
        endpoint_runon_time=2.0,
    )
    cover._self_initiated_movement = True
    cover._last_command = SERVICE_CLOSE_COVER
    cover.travel_calc.set_position(0)
    cover.tilt_calc.set_position(0)

    cover.hass.services.async_call.reset_mock()
    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    on_calls = [c for c in _ha_calls(cover) if c.args[1] == "turn_on"]
    assert on_calls, "sequential close must still stop the motor at the tilt end"
    assert cover._delay_task is None, "but without run-on (would overdrive tilt)"
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_mid_tilt_at_travel_endpoint_still_stops_tilt(make_cover):
    """At a travel endpoint, a mid-tilt move must still stop the tilt motor.

    The tilt-motor settle takes priority over the travel-endpoint self-stop
    skip: if the travel-endpoint skip ran first (cover at travel=100), the tilt
    motor would never be stopped, and a stale travel _last_command could
    re-pulse the travel relay. A mid-tilt target isolates the tilt branch — the
    travel-endpoint skip alone would leave the tilt motor running.
    """
    cover = make_cover(
        control_mode=CONTROL_MODE_TOGGLE,
        tilt_time_close=2.0,
        tilt_time_open=2.0,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
    )
    cover.travel_calc.set_position(100)  # cover at a travel endpoint
    cover.tilt_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(50)  # mid-tilt
        cover.hass.services.async_call.reset_mock()
        cover.tilt_calc.set_position(50)  # tilt reaches its mid target
        await cover.auto_stop_if_necessary()

    tilt_calls = [
        c
        for c in _ha_calls(cover)
        if c.args[2].get("entity_id") in ("switch.tilt_open", "switch.tilt_close")
    ]
    travel_calls = [
        c
        for c in _ha_calls(cover)
        if c.args[2].get("entity_id") in ("switch.open", "switch.close")
    ]
    assert tilt_calls, "mid-tilt at a travel endpoint must still stop the tilt motor"
    assert travel_calls == [], "tilt completion must not drive the travel motor"
    await _cancel_tasks(cover)


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"control_mode": CONTROL_MODE_TOGGLE}, True),
        ({"control_mode": CONTROL_MODE_PULSE, "stop_switch": "switch.stop"}, True),
        ({"cover_entity_id": "cover.inner"}, True),
        ({"control_mode": CONTROL_MODE_SWITCH}, False),
    ],
)
def test_self_stops_at_endpoints_per_mode(make_cover, kwargs, expected):
    """Only switch mode (latched relay) must stop at endpoints."""
    cover = make_cover(**kwargs)
    assert cover._self_stops_at_endpoints() is expected


# ===================================================================
# Tilt endpoints (dual-motor: separate tilt motor with its own limits)
# ===================================================================


def _travel_calls(cover):
    return [
        c
        for c in _ha_calls(cover)
        if c.args[2].get("entity_id") in ("switch.open", "switch.close")
    ]


def _tilt_calls(cover):
    return [
        c
        for c in _ha_calls(cover)
        if c.args[2].get("entity_id") in ("switch.tilt_open", "switch.tilt_close")
    ]


def _make_dual_motor(make_cover, control_mode=CONTROL_MODE_TOGGLE):
    return make_cover(
        control_mode=control_mode,
        tilt_time_close=2.0,
        tilt_time_open=2.0,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
    )


async def _run_tilt_move(cover, target):
    """Drive a real dual-motor tilt move to `target` and complete it."""
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(target)
        cover.hass.services.async_call.reset_mock()
        cover.tilt_calc.set_position(target)
        await cover.auto_stop_if_necessary()


@pytest.mark.asyncio
async def test_dual_motor_tilt_to_endpoint_sends_no_stop(make_cover):
    """A dual-motor tilt reaching a tilt endpoint must not stop the tilt motor
    (it self-stops at its limit) and must never drive the travel motor."""
    cover = _make_dual_motor(make_cover)
    cover.travel_calc.set_position(50)  # mid-travel: isolate tilt behaviour
    cover.tilt_calc.set_position(0)

    await _run_tilt_move(cover, 100)  # tilt to its open endpoint

    assert _tilt_calls(cover) == [], "tilt motor self-stops at its endpoint"
    assert _travel_calls(cover) == [], "tilt move must not drive the travel motor"
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_dual_motor_tilt_to_mid_still_stops_tilt(make_cover):
    """A dual-motor tilt reaching a mid position must stop the tilt motor
    (nothing self-stops there) and must not drive the travel motor."""
    cover = _make_dual_motor(make_cover)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(0)

    await _run_tilt_move(cover, 50)  # mid tilt

    assert _tilt_calls(cover), "mid-tilt must stop the tilt motor"
    assert _travel_calls(cover) == [], "tilt move must not drive the travel motor"
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_switch_dual_motor_tilt_to_endpoint_de_energizes(make_cover):
    """Switch mode latches the tilt relay ON, so a tilt endpoint must still turn
    it off."""
    cover = _make_dual_motor(make_cover, control_mode=CONTROL_MODE_SWITCH)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(100)
        cover.hass.services.async_call.reset_mock()
        cover.tilt_calc.set_position(100)
        await cover.auto_stop_if_necessary()

    off = [c for c in _tilt_calls(cover) if c.args[1] == "turn_off"]
    assert off, "switch mode must de-energize the tilt relay at a tilt endpoint"
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_switch_dual_motor_external_tilt_de_energizes_at_endpoint(make_cover):
    """The latched tilt relay must also be de-energized after an *externally*
    triggered tilt move reaches its endpoint (mirrors the travel case)."""
    cover = _make_dual_motor(make_cover, control_mode=CONTROL_MODE_SWITCH)
    cover._self_initiated_movement = False  # externally triggered tilt move
    cover._last_command = SERVICE_OPEN_COVER
    cover.travel_calc.set_position(50)  # mid-travel: isolate tilt behaviour
    cover.tilt_calc.set_position(100)  # tilt reached its open endpoint
    _stub_switch_on(cover, "switch.tilt_open")  # tilt relay still latched ON

    cover.hass.services.async_call.reset_mock()
    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    tilt_off = [c for c in _tilt_calls(cover) if c.args[1] == "turn_off"]
    assert tilt_off, "external tilt move must de-energize the latched tilt relay"
    assert _travel_calls(cover) == [], "must not touch the (off) travel relays"
    await _cancel_tasks(cover)


# ===================================================================
# Dual-motor external multi-click / multi-phase sequencing
# ===================================================================


def _switch_event(entity_id, old, new):
    """A state-change event shaped like the one HA fires."""
    old_s = MagicMock()
    old_s.state = old
    old_s.attributes = {}
    new_s = MagicMock()
    new_s.state = new
    new_s.attributes = {}
    event = MagicMock()
    event.data = {"entity_id": entity_id, "old_state": old_s, "new_state": new_s}
    return event


def _stub_switch_states(cover, states):
    """Back ``_switch_is_on`` with a mutable {entity_id: 'on'|'off'} dict."""

    def _get(entity_id):
        m = MagicMock()
        m.state = states.get(entity_id, "off")
        return m

    cover.hass.states.get.side_effect = _get


@pytest.mark.asyncio
async def test_switch_dual_motor_external_tilt_can_reverse_twice(make_cover):
    """External tilt: open → reverse to close → reverse to open again.

    The third click (tilt-open again) must be honoured. Previously the reverse
    de-energized the opposite relay twice (interlock + the tilt-motor send),
    marking two pending echoes for a single physical transition; the leftover
    echo silently swallowed the user's next real tilt-open event.
    """
    cover = _make_dual_motor(make_cover, control_mode=CONTROL_MODE_SWITCH)
    cover.travel_calc.set_position(50)  # mid-travel: isolate tilt
    cover.tilt_calc.set_position(50)  # mid-tilt: reversals never hit the endpoint
    states = {"switch.tilt_open": "off", "switch.tilt_close": "off"}
    _stub_switch_states(cover, states)

    with patch.object(cover, "async_write_ha_state"):
        # Click 1 — external tilt-open.
        states["switch.tilt_open"] = "on"
        await cover._async_switch_state_changed(
            _switch_event("switch.tilt_open", "off", "on")
        )
        open_cmd = cover._last_command

        # Click 2 — external tilt-close (reverse). Interlock turns tilt_open off.
        states["switch.tilt_close"] = "on"
        await cover._async_switch_state_changed(
            _switch_event("switch.tilt_close", "off", "on")
        )
        close_cmd = cover._last_command
        # The tilt_open relay physically settles off (one transition → one echo).
        states["switch.tilt_open"] = "off"
        await cover._async_switch_state_changed(
            _switch_event("switch.tilt_open", "on", "off")
        )

        # Click 3 — external tilt-open again (reverse back). Must NOT be filtered.
        states["switch.tilt_open"] = "on"
        await cover._async_switch_state_changed(
            _switch_event("switch.tilt_open", "off", "on")
        )

    assert open_cmd != close_cmd, "open and close tilt commands must differ"
    assert cover._last_command == open_cmd, (
        "third external tilt-open was swallowed by a stale pending echo"
    )
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_switch_dual_motor_external_open_continues_into_travel(make_cover):
    """External cover-open on a dual-motor cover must continue into the travel
    phase after the tilt pre-step — a single click should open, not stall.

    The pre-step arms ``_pending_travel_target``; when it completes, the
    external branch of auto-stop must start the travel phase instead of
    returning early.
    """
    cover = _make_dual_motor(make_cover, control_mode=CONTROL_MODE_SWITCH)
    cover._self_initiated_movement = False  # externally triggered move
    cover.travel_calc.set_position(0)  # cover closed (pre-step start)
    cover.tilt_calc.set_position(100)  # tilt reached its safe/pre-step target
    # Arm the pending travel phase exactly as _start_tilt_pre_step would have.
    cover._pending_travel_target = 100
    cover._pending_travel_command = SERVICE_OPEN_COVER
    _stub_switch_states(cover, {})  # all relays currently off

    cover.hass.services.async_call.reset_mock()
    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    assert cover._pending_travel_target is None, (
        "external tilt pre-step must continue into the travel phase"
    )
    open_on = [
        c
        for c in _ha_calls(cover)
        if c.args[1] == "turn_on" and c.args[2].get("entity_id") == "switch.open"
    ]
    assert open_on, "the travel phase must drive the cover-open relay"
    await _cancel_tasks(cover)
