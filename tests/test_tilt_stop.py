"""Stopping tilt-motor movements — audit findings core-C1a/C1b."""

import asyncio

import pytest
from unittest.mock import MagicMock, patch

from homeassistant.const import SERVICE_OPEN_COVER

from custom_components.cover_time_based.cover import (
    CONTROL_MODE_PULSE,
    CONTROL_MODE_SWITCH,
    CONTROL_MODE_TOGGLE,
    CONTROL_MODE_TOGGLE_OPPOSITE,
)


def _make_state_event(entity_id, old_state, new_state):
    """Create a mock state change event like HA fires (see test_state_monitoring)."""
    old = MagicMock()
    old.state = old_state
    old.attributes = {}
    new = MagicMock()
    new.state = new_state
    new.attributes = {}
    event = MagicMock()
    event.data = {
        "entity_id": entity_id,
        "old_state": old,
        "new_state": new,
    }
    return event


def _tilt_switch_calls(cover, start=0):
    calls = cover.hass.services.async_call.call_args_list[start:]
    return [
        (c[0][1], c[0][2].get("entity_id"))
        for c in calls
        if c[0][2].get("entity_id") in ("switch.tilt_open", "switch.tilt_close")
    ]


DUAL = dict(
    tilt_time_close=5.0,
    tilt_time_open=5.0,
    tilt_mode="dual_motor",
    tilt_open_switch="switch.tilt_open",
    tilt_close_switch="switch.tilt_close",
)


@pytest.mark.asyncio
async def test_stop_cover_releases_plain_tilt_motor_move(make_cover):
    """A user stop during a plain dual-motor tilt move must turn the tilt relay off."""
    cover = make_cover(**DUAL)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(30)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(80)
        assert cover.tilt_calc.is_traveling() and cover._moving_tilt_motor
        n = len(cover.hass.services.async_call.call_args_list)
        await cover.async_stop_cover()
    offs = [c for c in _tilt_switch_calls(cover, n) if c[0] == "turn_off"]
    assert offs, "stop must de-energize the running tilt relay"


@pytest.mark.asyncio
async def test_stop_cover_tilt_stops_tilt_move(make_cover):
    """cover.stop_cover_tilt must actually stop tilt (STOP_TILT is advertised)."""
    cover = make_cover(**DUAL)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(30)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(80)
        n = len(cover.hass.services.async_call.call_args_list)
        await cover.async_stop_cover_tilt()
    assert not cover.tilt_calc.is_traveling()
    offs = [c for c in _tilt_switch_calls(cover, n) if c[0] == "turn_off"]
    assert offs


@pytest.mark.asyncio
async def test_external_tilt_stop_still_releases_travel_relay(make_cover):
    """An external tilt-stop press must not strand a self-driven travel relay.

    The TILT relay is the one that reported, not the TRAVEL relay — nothing
    external stopped the travel motor, so async_stop_cover's relay-echo
    suppression must not swallow the travel _send_stop() here (mirror image
    of _should_stop_tilt_motor).
    """
    cover = make_cover(
        travel_time_close=5.0,
        travel_time_open=5.0,
        tilt_time_close=1.0,
        tilt_time_open=1.0,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        tilt_stop_switch="switch.tilt_stop",
        safe_tilt_position=100,
    )
    cover.travel_calc.set_position(0)
    cover.tilt_calc.set_position(100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()  # latches switch.open ON
        n = len(cover.hass.services.async_call.call_args_list)

        async def ext_tilt_stop():
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_stop", "off", "on"
                )
            finally:
                cover._triggered_externally = False

        await asyncio.get_event_loop().create_task(ext_tilt_stop())
    assert not cover.travel_calc.is_traveling()
    calls = [
        (c[0][1], c[0][2].get("entity_id"))
        for c in cover.hass.services.async_call.call_args_list[n:]
    ]
    assert ("turn_off", "switch.open") in calls, calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "control_mode,tilt_press_switch,expected_relay",
    [
        # Same-button toggle: the button that's moving tilt, pressed again,
        # is the "stop" edge (ToggleModeCover._handle_external_tilt_state_change).
        ("toggle", "switch.tilt_open", "switch.open"),
        # Opposite-button toggle: the *other* tilt button, pressed while tilt
        # moves the first way, is the "stop" edge
        # (ToggleOppositeModeCover._handle_external_tilt_state_change).
        ("toggle_opposite", "switch.tilt_close", "switch.close"),
    ],
    ids=["toggle-same-button", "toggle-opposite-button"],
)
async def test_external_tilt_stop_still_releases_travel_relay_toggle(
    make_cover, control_mode, tilt_press_switch, expected_relay
):
    """Toggle-hardware counterpart of test_external_tilt_stop_still_releases_travel_relay.

    Toggle hardware has no dedicated tilt-stop relay — unlike switch/pulse mode,
    ToggleModeCover/ToggleOppositeModeCover._handle_external_tilt_state_change
    never reference a ``tilt_stop_switch`` at all. On this hardware "stop" is a
    same-direction (same-button) or opposite-direction (opposite-button) press
    on the tilt_open/tilt_close relay while tilt is already moving, so that is
    the event fired here instead of a ``switch.tilt_stop`` press.

    This exercises the mirrored ``elif`` added to ToggleBaseCover.async_stop_cover
    (cover_toggle_base.py) directly, which the switch-mode test above does not
    reach. It matters more here than on switch/pulse hardware: toggle's
    ``_send_stop`` PULSES a relay rather than turning one off, so a wrongly-open
    gate doesn't just skip a de-energize — on a stopped motor a pulse is itself
    a movement command (#153-class hazard). This test must PASS on the current
    code (the fix is already in) — it is regression coverage, not a TDD RED/GREEN
    step.
    """
    cover = make_cover(
        control_mode=control_mode,
        tilt_time_close=5.0,
        tilt_time_open=5.0,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
    )
    assert cover._has_tilt_motor()

    # Self-initiated travel move already under way, driving switch.open —
    # nothing external is going to stop this motor.
    cover.travel_calc.set_position(50)
    cover.travel_calc.start_travel(100)
    cover._last_command = SERVICE_OPEN_COVER
    assert cover.travel_calc.is_traveling()
    assert cover._self_initiated_movement

    # Independent tilt motor also moving (dual_motor = separate motor from
    # travel), opening from 40 -> 100.
    cover.tilt_calc.set_position(40)
    cover.tilt_calc.start_travel(100)

    with patch.object(cover, "async_write_ha_state"):
        n = len(cover.hass.services.async_call.call_args_list)

        async def ext_tilt_press():
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    tilt_press_switch, "off", "on"
                )
            finally:
                cover._triggered_externally = False

        await asyncio.get_event_loop().create_task(ext_tilt_press())

    assert not cover.travel_calc.is_traveling()
    calls = [
        (c[0][1], c[0][2].get("entity_id"))
        for c in cover.hass.services.async_call.call_args_list[n:]
    ]
    assert ("turn_on", expected_relay) in calls, calls


@pytest.mark.asyncio
async def test_abandon_travel_prestep_does_not_pulse_idle_tilt_relay(make_cover):
    """Audit finding B4: a stale ``_last_tilt_direction`` must not pulse an
    idle tilt motor when a travel pre-step is abandoned.

    Sequence:
    1. Tilt opens to its endpoint (100) and completes via auto-stop. Toggle
       hardware self-stops at the tilt endpoint, so ``_tilt_settle`` skips the
       relay stop and (before this fix) ``_last_tilt_direction`` was left
       stale at "open".
    2. A tilt command above ``max_tilt_allowed_position`` starts a *travel*
       pre-step (dual_motor): travel runs first, the tilt motor stays idle.
    3. A new command (``set_position``) abandons the pre-step. Before this
       fix, ``_abandon_active_lifecycle`` unconditionally fired
       ``_send_tilt_stop()``, which — keyed off the stale "open" direction —
       pulsed ``switch.tilt_open`` on an idle motor: an untracked movement
       (a #153-class phantom pulse). After the fix the tilt stop is gated on
       the tilt motor actually having been driven, so no pulse fires.
    """
    cover = make_cover(
        control_mode="toggle",
        travel_time_close=0.2,
        travel_time_open=0.2,
        tilt_time_close=0.2,
        tilt_time_open=0.2,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        safe_tilt_position=100,
        max_tilt_allowed_position=50,
    )
    cover.travel_calc.set_position(40)
    cover.tilt_calc.set_position(30)

    with patch.object(cover, "async_write_ha_state"):
        # 1. Tilt move to the tilt endpoint (100). Completes via auto-stop:
        #    _tilt_settle skips the stop at the endpoint (toggle self-stops).
        await cover.async_open_cover_tilt()
        assert cover._last_tilt_direction == "open"
        await asyncio.sleep(0.3)
        await cover.auto_stop_if_necessary()

        # 2. Travel pre-step: tilt requested above max_tilt_allowed_position,
        #    so travel runs first; tilt motor is idle in this phase.
        cover.travel_calc.set_position(80)
        await cover.set_tilt_position(20)
        assert cover._pending_tilt_target == 20  # travel pre-step active
        assert not cover.tilt_calc.is_traveling()  # tilt motor NOT running

        # 3. New command abandons the pre-step.
        n = len(cover.hass.services.async_call.call_args_list)
        await cover.set_position(70)

    calls = _tilt_switch_calls(cover, n)
    assert ("turn_on", "switch.tilt_open") not in calls, calls


@pytest.mark.asyncio
async def test_tilt_restore_completion_clears_stale_direction(make_cover):
    """Audit finding B4 (gap found in review): a tilt-restore phase that lands
    exactly at a tilt endpoint must also clear ``_last_tilt_direction``.

    ``_on_tilt_motor_move_complete`` was only wired up at the two sites the
    original brief named (the plain dual-motor tilt-move settle branch and
    the externally-triggered completion branch). The ``_tilt_restore_active``
    completion branch in ``auto_stop_if_necessary`` also calls
    ``_tilt_settle()`` to end a tilt-motor drive, and can equally land at an
    endpoint (0/100) and take the self-stop-skip path there — leaving the
    direction stale for the same reason B4 originally found. A stale
    direction is read with no idle-motor gate by the toggle
    ``_raw_direction_command`` override that the calibration screen drives,
    so this is the same #153-class phantom-pulse hazard, just reached via a
    different lifecycle phase.

    Sequence (dual-motor toggle, ``close_includes_tilt`` — the default —
    drives tilt to 0 after travel):
    1. ``async_close_cover()`` starts the tilt pre-step (30 -> safe 100).
    2. Pre-step completes -> travel phase starts (50 -> 0), restore target
       queued at 0.
    3. Travel completes -> ``_start_tilt_restore`` drives the tilt motor
       closed (100 -> 0), setting ``_last_tilt_direction = "close"``.
    4. Restore completes with tilt exactly at 0 (a tilt endpoint) ->
       ``_tilt_settle`` takes the self-stop-skip path (toggle self-stops at
       its limit) -> the ``_tilt_restore_active`` branch must still clear the
       stale direction.
    """
    cover = make_cover(
        control_mode="toggle",
        travel_time_close=0.2,
        travel_time_open=0.2,
        tilt_time_close=0.2,
        tilt_time_open=0.2,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        close_includes_tilt=True,
    )
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(30)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()  # tilt pre-step: 30 -> 100 (safe)
        assert cover.tilt_calc.is_traveling()
        await asyncio.sleep(0.3)
        await cover.auto_stop_if_necessary()  # pre-step complete -> travel starts
        assert cover.travel_calc.is_traveling()
        assert cover._tilt_restore_target == 0

        await asyncio.sleep(0.3)
        await cover.auto_stop_if_necessary()  # travel complete -> tilt restore starts
        assert cover._tilt_restore_active is True
        assert cover.tilt_calc.is_traveling()
        assert cover._last_tilt_direction == "close"

        await asyncio.sleep(0.3)
        await cover.auto_stop_if_necessary()  # restore completes at endpoint 0

    assert cover._tilt_restore_active is False
    assert cover.tilt_calc.current_position() == 0
    assert cover._last_tilt_direction is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "control_mode",
    [
        CONTROL_MODE_SWITCH,
        CONTROL_MODE_TOGGLE,
        CONTROL_MODE_TOGGLE_OPPOSITE,
        CONTROL_MODE_PULSE,
    ],
)
async def test_external_tilt_press_before_tilt_calibration_does_not_crash(
    make_cover, control_mode
):
    """Audit Task 5: dual_motor + tilt switches wired, but tilt times NOT yet
    set is a supported pre-calibration state — ``_tilt_strategy`` is ``None``
    and ``tilt_calc`` doesn't exist. An external press on a tilt switch must
    not crash any of the four mode dispatchers.

    Driven through ``_async_switch_state_changed`` (the real listener HA
    invokes on a state-change event — registered unconditionally for
    ``_tilt_open_switch_id``/``_tilt_close_switch_id``/``_tilt_stop_switch_id``
    in ``async_added_to_hass``), not the mode-specific
    ``_handle_external_tilt_state_change`` directly, so the test exercises
    the guard actually added at the dispatch site rather than bypassing it.
    """
    kwargs = dict(
        control_mode=control_mode,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
    )
    if control_mode == CONTROL_MODE_PULSE:
        # Pulse mode requires a dedicated stop switch, and its tilt axis has
        # its own dedicated stop relay too (see DUAL fixtures above).
        kwargs["stop_switch"] = "switch.stop"
        kwargs["tilt_stop_switch"] = "switch.tilt_stop"

    cover = make_cover(**kwargs)
    assert not cover._has_tilt_support()

    event = _make_state_event("switch.tilt_open", "off", "on")
    with patch.object(cover, "async_write_ha_state"):
        await cover._async_switch_state_changed(event)  # must not raise
