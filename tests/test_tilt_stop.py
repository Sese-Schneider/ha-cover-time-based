"""Stopping tilt-motor movements — audit findings core-C1a/C1b."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import SERVICE_OPEN_COVER

from custom_components.cover_time_based.cover import (
    CONTROL_MODE_PULSE,
    CONTROL_MODE_SWITCH,
    CONTROL_MODE_TOGGLE,
    CONTROL_MODE_TOGGLE_OPPOSITE,
)
from tests.helpers import relay_calls, stub_switches


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
    return [
        c
        for c in relay_calls(cover, start)
        if c[1] in ("switch.tilt_open", "switch.tilt_close")
    ]


DUAL = {
    "tilt_time_close": 5.0,
    "tilt_time_open": 5.0,
    "tilt_mode": "dual_motor",
    "tilt_open_switch": "switch.tilt_open",
    "tilt_close_switch": "switch.tilt_close",
}


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


# Travel-relay events that must NEVER fire when only the tilt axis moved: on
# toggle/toggle_opposite the travel "stop" is a *pulse* of a travel direction
# relay (#153), and on pulse send_endpoint_stop=False it is a go-to-favourite
# reposition (#133). switch.stop is pulse mode's dedicated travel-stop relay.
_TRAVEL_TURN_ON = [
    ("turn_on", "switch.open"),
    ("turn_on", "switch.close"),
    ("turn_on", "switch.stop"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_method", ["async_stop_cover_tilt", "async_stop_cover"])
@pytest.mark.parametrize(
    "control_mode,extra",
    [
        ("toggle", {}),
        ("toggle_opposite", {}),
        (
            "pulse",
            {
                "send_endpoint_stop": False,
                "stop_switch": "switch.stop",
                "tilt_stop_switch": "switch.tilt_stop",
            },
        ),
    ],
    ids=["toggle", "toggle_opposite", "pulse-no-endpoint-stop"],
)
async def test_stop_during_plain_tilt_move_does_not_pulse_travel_relay(
    make_cover, control_mode, extra, stop_method
):
    """Coverage gap M-T1: STOP / STOP_TILT during a *plain* dual-motor tilt move
    must not pulse the idle TRAVEL relay on momentary hardware.

    A plain dual-motor tilt move drives only the tilt motor; the travel motor
    sits idle, yet ``_last_command`` is left at the travel open/close command
    (``DualMotorTilt`` inherits ``tilt_command_for``).
    ``async_stop_cover_tilt`` delegates to ``async_stop_cover``, whose internal
    travel ``_send_stop`` was ungated on travel activity — so pressing STOP(_TILT)
    pulsed a stopped travel motor: a movement command on toggle hardware (#153),
    a go-to-favourite on pulse ``send_endpoint_stop=False`` (#133). The tilt axis
    is still settled by ``_tilt_settle`` in parallel; only the travel pulse is
    the defect.
    """
    cover = make_cover(control_mode=control_mode, **DUAL, **extra)
    assert cover._has_tilt_motor()
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(30)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(80)
        # Plain tilt move: tilt motor running, travel idle, but _last_command
        # left at the travel command — the phantom-pulse precondition.
        assert cover.tilt_calc.is_traveling() and cover._moving_tilt_motor
        assert not cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_OPEN_COVER
        n = len(cover.hass.services.async_call.call_args_list)
        await getattr(cover, stop_method)()

    calls = relay_calls(cover, n)
    for phantom in _TRAVEL_TURN_ON:
        assert phantom not in calls, (control_mode, stop_method, calls)
    # The tilt axis is still settled: tracker stopped and its relay was actioned.
    assert not cover.tilt_calc.is_traveling()
    tilt_actioned = _tilt_switch_calls(cover, n) or [
        c for c in calls if c[1] == "switch.tilt_stop"
    ]
    assert tilt_actioned, (control_mode, stop_method, calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_method", ["async_stop_cover_tilt", "async_stop_cover"])
async def test_switch_mode_stop_during_plain_tilt_still_deenergizes_travel(
    make_cover, stop_method
):
    """Switch-mode contrast to the momentary test above: the latched travel relay
    must ALWAYS be de-energized on stop, even during a plain tilt move.

    Switch mode's ``_self_stops_at_endpoints()`` is False, so the self-stop gate
    that suppresses the momentary phantom must NOT suppress the switch-mode
    ``turn_off`` — its behaviour is unchanged (finding: switch → turn_off only).
    """
    cover = make_cover(control_mode=CONTROL_MODE_SWITCH, **DUAL)
    assert cover._has_tilt_motor()
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(30)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(80)
        assert cover.tilt_calc.is_traveling() and cover._moving_tilt_motor
        n = len(cover.hass.services.async_call.call_args_list)
        await getattr(cover, stop_method)()

    calls = relay_calls(cover, n)
    # Travel relay is de-energized (never a pulse in switch mode) — unchanged.
    assert ("turn_off", "switch.open") in calls, calls
    assert ("turn_off", "switch.close") in calls, calls
    assert not any(c[0] == "turn_on" for c in calls), calls


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
    "control_mode,extra",
    [
        ("toggle", {}),
        ("toggle_opposite", {}),
        (
            "pulse",
            {
                "send_endpoint_stop": False,
                "stop_switch": "switch.stop",
                "tilt_stop_switch": "switch.tilt_stop",
            },
        ),
    ],
    ids=["toggle", "toggle_opposite", "pulse-no-endpoint-stop"],
)
async def test_plain_tilt_move_settling_at_endpoint_does_not_pulse_tilt_relay(
    make_cover, control_mode, extra
):
    """Task-1 coverage gap: the momentary *endpoint* tilt case.

    The existing plain-tilt-move stop tests all settle MID-tilt, so they only
    reach ``_tilt_settle``'s ``else`` branch (send the tilt stop). The endpoint
    branch — a tilt move that finishes exactly at a tilt limit (0/100) on
    momentary hardware, where the tilt motor self-stops on its own limit and a
    stop 'pulse' there would restart it (#153) / go-to-favourite (#133) — was
    only verified by code-reading. Drive a plain dual-motor tilt move to the
    tilt endpoint and let it complete via auto-stop: ``_tilt_settle`` must skip
    the relay stop, so NO tilt relay is actioned during the settle.
    """
    cover = make_cover(
        control_mode=control_mode,
        tilt_time_close=0.2,
        tilt_time_open=0.2,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        **extra,
    )
    assert cover._has_tilt_motor()
    assert cover._self_stops_at_endpoints()
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(90)  # close to the 100 endpoint

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(100)  # plain tilt move to the tilt endpoint
        assert cover.tilt_calc.is_traveling() and cover._moving_tilt_motor
        await asyncio.sleep(0.3)
        n = len(cover.hass.services.async_call.call_args_list)
        await cover.auto_stop_if_necessary()  # tilt reaches 100 -> _tilt_settle

    assert cover.tilt_calc.current_position() == 100
    calls = relay_calls(cover, n)
    # No tilt relay actioned at all during the endpoint settle: the motor
    # self-stopped at its limit, so a pulse would be a phantom movement.
    assert _tilt_switch_calls(cover, n) == [], calls
    assert not any(c[1] == "switch.tilt_stop" for c in calls), calls


@pytest.mark.asyncio
async def test_switch_mode_plain_tilt_move_at_endpoint_still_deenergizes_tilt(
    make_cover,
):
    """Switch-mode contrast to the momentary endpoint test: switch mode's
    latched tilt relay must ALWAYS be de-energized when a tilt move settles,
    even exactly at a tilt endpoint (``_self_stops_at_endpoints`` is False, so
    ``_tilt_settle`` sends the stop)."""
    cover = make_cover(control_mode=CONTROL_MODE_SWITCH, **DUAL)
    assert cover._has_tilt_motor()
    assert not cover._self_stops_at_endpoints()
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(90)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(100)
        assert cover.tilt_calc.is_traveling() and cover._moving_tilt_motor
        await asyncio.sleep(0.6)  # DUAL tilt_time is 5.0s -> 10% is 0.5s
        n = len(cover.hass.services.async_call.call_args_list)
        await cover.auto_stop_if_necessary()

    assert cover.tilt_calc.current_position() == 100
    offs = [c for c in _tilt_switch_calls(cover, n) if c[0] == "turn_off"]
    assert offs, "switch mode must de-energize the latched tilt relay at the endpoint"


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
    kwargs = {
        "control_mode": control_mode,
        "tilt_mode": "dual_motor",
        "tilt_open_switch": "switch.tilt_open",
        "tilt_close_switch": "switch.tilt_close",
    }
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


# --- A travel command that goes nowhere still releases a running tilt motor ---

# The tilt stop ``_tilt_settle`` emits mid-tilt, per control mode: switch mode
# de-energizes its latched relays, toggle re-pulses the last tilt direction.
_TILT_STOP_CALL = {
    CONTROL_MODE_SWITCH: ("turn_off", "switch.tilt_close"),
    CONTROL_MODE_TOGGLE: ("turn_on", "switch.tilt_close"),
}


def _tilt_state(cover):
    return (
        f"_moving_tilt_motor={cover._moving_tilt_motor}, "
        f"tilt_calc.is_traveling()={cover.tilt_calc.is_traveling()}, "
        f"tilt={cover.tilt_calc.current_position()}"
    )


async def _start_plain_tilt_motor_move(cover, target=0):
    """Dual-motor cover parked fully open, tilt half way, tilt motor now running."""
    cover.travel_calc.set_position(100)
    cover.tilt_calc.set_position(50)
    stub_switches(cover)
    await cover.set_tilt_position(target)
    assert cover._moving_tilt_motor, "precondition: dedicated tilt motor running"
    assert ("turn_on", "switch.tilt_close") in relay_calls(cover), (
        "precondition: tilt close relay energised"
    )
    return len(cover.hass.services.async_call.call_args_list)


class TestTravelCommandReleasesDisplacedTiltMotor:
    """A travel command displaces a running dedicated tilt motor even when the
    travel itself is a no-op.

    ``_abandon_active_lifecycle`` clears ``_moving_tilt_motor`` on entry to
    every movement method and returns without stopping anything when no
    multi-phase lifecycle is live, so the travel funnel and ``set_position``
    used to run their "already at target" branches — and their no-pre-step
    normal path — with the flag already False, leaving the tilt motor driving
    to its limit with nothing tracking it.
    """

    @pytest.mark.asyncio
    async def test_departing_endpoint_sends_tilt_stop_pulse(self, make_cover):
        """A tracker still at its departure endpoint needs a real toggle stop."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE, **DUAL)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)
        stub_switches(cover)
        with (
            patch.object(cover, "async_write_ha_state"),
            patch("time.time", return_value=1000),
        ):
            await cover.set_tilt_position(30)
            assert cover._moving_tilt_motor and cover.tilt_calc.is_traveling()
            assert cover.tilt_calc.current_position() == 100
            n = len(cover.hass.services.async_call.call_args_list)
            await cover.set_position(50)

        assert ("turn_on", "switch.tilt_close") in _tilt_switch_calls(cover, n)
        assert not cover.tilt_calc.is_traveling()
        assert cover._last_tilt_direction is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "control_mode",
        [CONTROL_MODE_SWITCH, CONTROL_MODE_TOGGLE],
        ids=["switch", "toggle"],
    )
    async def test_open_at_open_endpoint_releases_running_tilt_motor(
        self, make_cover, control_mode
    ):
        """open_cover while already at 100 must stop the running tilt motor."""
        cover = make_cover(control_mode=control_mode, **DUAL)
        with patch.object(cover, "async_write_ha_state"):
            n = await _start_plain_tilt_motor_move(cover)
            assert cover.tilt_calc.is_traveling()
            await cover.async_open_cover()

        tilt_calls = _tilt_switch_calls(cover, n)
        assert _TILT_STOP_CALL[control_mode] in tilt_calls, (
            "open_cover at the open endpoint left the tilt motor running; "
            f"tilt-relay calls after the travel command: {tilt_calls!r} "
            f"(all calls: {relay_calls(cover, n)!r}; {_tilt_state(cover)})"
        )

    @pytest.mark.asyncio
    async def test_open_at_endpoint_during_relay_feedback_wait_releases_tilt_motor(
        self, make_cover
    ):
        """Same, while the tilt move is still parked waiting for its relay echo.

        ``wait_for_relay_feedback`` means the tilt relay is commanded but
        tracking has not started, so ``tilt_calc.is_traveling()`` is False and
        the abandon also drops the arm — nothing left to ever stop the motor.
        """
        cover = make_cover(
            control_mode=CONTROL_MODE_SWITCH, wait_for_relay_feedback=True, **DUAL
        )
        with patch.object(cover, "async_write_ha_state"):
            n = await _start_plain_tilt_motor_move(cover)
            await asyncio.sleep(0)  # let the feedback task reach its await
            assert not cover.tilt_calc.is_traveling(), (
                "precondition: parked on the echo"
            )
            await cover.async_open_cover()

        tilt_calls = _tilt_switch_calls(cover, n)
        assert any(c[0] == "turn_off" for c in tilt_calls), (
            "open_cover at the open endpoint during the relay-feedback wait left "
            f"the tilt motor running; tilt-relay calls: {tilt_calls!r} "
            f"(all calls: {relay_calls(cover, n)!r}; {_tilt_state(cover)})"
        )

    @pytest.mark.asyncio
    async def test_set_position_to_current_releases_running_tilt_motor(
        self, make_cover
    ):
        """set_position(100) while already at 100 must stop the tilt motor."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, **DUAL)
        with patch.object(cover, "async_write_ha_state"):
            n = await _start_plain_tilt_motor_move(cover)
            await cover.set_position(100)

        tilt_calls = _tilt_switch_calls(cover, n)
        assert any(c[0] == "turn_off" for c in tilt_calls), (
            "set_position at the current position left the tilt motor running; "
            f"tilt-relay calls: {tilt_calls!r} (all calls: {relay_calls(cover, n)!r}; "
            f"{_tilt_state(cover)})"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "control_mode",
        [CONTROL_MODE_SWITCH, CONTROL_MODE_TOGGLE],
        ids=["switch", "toggle"],
    )
    async def test_release_lands_on_the_travel_command_not_on_auto_stop(
        self, make_cover, control_mode
    ):
        """The stop belongs to the travel command; auto-stop cannot supply it.

        The abandoned tilt move's own completion is no rescue: its
        "drove the dedicated tilt motor" branch in ``auto_stop_if_necessary``
        reads ``_moving_tilt_motor``, which the abandon already cleared, so it
        takes the travel branch and never touches the tilt relay.
        """
        cover = make_cover(control_mode=control_mode, **DUAL)
        with patch.object(cover, "async_write_ha_state"):
            # A MID-tilt target, so no mode can plead "the motor self-stops on
            # its limit switch": at 30% the motor has to be told to stop.
            n = await _start_plain_tilt_motor_move(cover, target=30)
            await cover.async_open_cover()
            during_travel = _tilt_switch_calls(cover, n)
            # The tilt motor's orphaned tracker eventually reaches its target.
            cover.tilt_calc.set_position(30)
            m = len(cover.hass.services.async_call.call_args_list)
            await cover.auto_stop_if_necessary()

        assert _TILT_STOP_CALL[control_mode] in during_travel, (
            "the travel command did not de-energise the tilt relay; "
            f"tilt-relay calls: {during_travel!r} ({_tilt_state(cover)})"
        )
        assert _tilt_switch_calls(cover, m) == [], (
            "auto_stop_if_necessary must have nothing left to do on the tilt "
            f"axis: {_tilt_switch_calls(cover, m)!r}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "travel",
        [
            lambda cover: cover.async_open_cover(),
            lambda cover: cover.set_position(90),
        ],
        ids=["open_cover", "set_position"],
    )
    async def test_travel_with_tilt_already_safe_releases_running_tilt_motor(
        self, make_cover, travel
    ):
        """The normal path strands the motor too when no pre-step is planned.

        Tilt already sits at the safe position, so ``_plan_tilt_for_travel``
        starts nothing and there is no pre-step to take the motor over — the
        travel relay would energise with the tilt relay still latched, and
        nothing downstream would de-energize it. Both travel funnels
        (``_async_move_to_endpoint`` and ``set_position``) reach that point.
        """
        cover = make_cover(
            control_mode=CONTROL_MODE_SWITCH, safe_tilt_position=100, **DUAL
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)
        stub_switches(cover)
        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(0)
            assert cover._moving_tilt_motor, "precondition: tilt motor running"
            n = len(cover.hass.services.async_call.call_args_list)
            await travel(cover)

        calls = relay_calls(cover, n)
        tilt_off = next(
            i
            for i, c in enumerate(calls)
            if c[0] == "turn_off" and c[1].startswith("switch.tilt_")
        )
        travel_on = next(
            i for i, c in enumerate(calls) if c == ("turn_on", "switch.open")
        )
        assert tilt_off < travel_on, (
            f"the tilt motor must be released before the travel relay: {calls!r}"
        )
        assert not cover.tilt_calc.is_traveling()
        assert cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_open_during_feedback_wait_cancels_the_tilt_deferred_start(
        self, make_cover
    ):
        """The released motor's deferred start must not resurrect its tracking.

        Under ``wait_for_relay_feedback`` the displaced tilt move's start is
        parked in ``_startup_delay_task`` awaiting its relay's ON echo. Left
        alive, that echo would start tilt tracking against a relay the release
        just de-energised — tracked phantom motion.
        """
        cover = make_cover(
            control_mode=CONTROL_MODE_SWITCH, wait_for_relay_feedback=True, **DUAL
        )
        with patch.object(cover, "async_write_ha_state"):
            await _start_plain_tilt_motor_move(cover)
            await asyncio.sleep(0)
            assert cover._startup_delay_task is not None, (
                "precondition: the tilt start is parked on its relay echo"
            )
            await cover.async_open_cover()

            assert (
                cover._startup_delay_task is None or cover._startup_delay_task.done()
            ), "the displaced tilt move's deferred start outlived its release"

            # The relay's ON echo finally arrives, long after the release.
            await cover._async_switch_state_changed(
                _make_state_event("switch.tilt_close", "off", "on")
            )
            await asyncio.sleep(0)

        assert not cover.tilt_calc.is_traveling(), (
            "a late relay echo resurrected tilt tracking against a de-energised "
            f"relay ({_tilt_state(cover)})"
        )

    @pytest.mark.asyncio
    async def test_external_travel_press_leaves_the_tilt_motor_running(
        self, make_cover
    ):
        """The release is for commands the integration drives, not wall presses.

        A press on the travel button did not de-energize the tilt relay, so the
        tilt motor really does keep its own move (and on momentary hardware a
        stop here would be a relay pulse).
        """
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, **DUAL)
        with patch.object(cover, "async_write_ha_state"):
            n = await _start_plain_tilt_motor_move(cover)
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "off", "on")
            )

        assert _tilt_switch_calls(cover, n) == [], (
            f"an external travel press touched the tilt relays: "
            f"{_tilt_switch_calls(cover, n)!r}"
        )
        assert cover.tilt_calc.is_traveling(), "the tilt motor keeps its own move"

    @pytest.mark.asyncio
    async def test_open_while_a_same_direction_startup_delay_runs_releases_tilt(
        self, make_cover
    ):
        """The "startup delay already active" no-op is a release site too.

        A dual-motor tilt open leaves ``_last_command`` at ``open_cover`` with
        the tilt move's deferred start still pending, so a following
        ``open_cover`` returns from that branch — having displaced the tilt
        motor without ever commanding travel.
        """
        cover = make_cover(
            control_mode=CONTROL_MODE_SWITCH, wait_for_relay_feedback=True, **DUAL
        )
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(50)
        stub_switches(cover)
        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(100)
            await asyncio.sleep(0)
            assert cover._last_command == SERVICE_OPEN_COVER
            assert cover._startup_delay_task is not None
            n = len(cover.hass.services.async_call.call_args_list)
            await cover.async_open_cover()

        tilt_calls = _tilt_switch_calls(cover, n)
        assert any(c[0] == "turn_off" for c in tilt_calls), (
            "the startup-delay no-op left the tilt motor running; "
            f"tilt-relay calls: {tilt_calls!r} ({_tilt_state(cover)})"
        )
        assert ("turn_on", "switch.open") not in relay_calls(cover, n), (
            "the branch must stay a no-op on the travel axis"
        )

    @pytest.mark.asyncio
    async def test_set_position_rejected_as_too_short_releases_tilt(self, make_cover):
        """A move below ``min_movement_time`` is a travel command going nowhere.

        It never reaches the tilt planner, so nothing downstream takes the
        displaced motor over.
        """
        cover = make_cover(
            control_mode=CONTROL_MODE_SWITCH,
            travel_time_open=30,
            travel_time_close=30,
            min_movement_time=5.0,
            **DUAL,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)
        stub_switches(cover)
        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(0)
            assert cover._moving_tilt_motor, "precondition: tilt motor running"
            n = len(cover.hass.services.async_call.call_args_list)
            await cover.set_position(51)  # 0.3s of travel, rejected as too short

        assert not cover.travel_calc.is_traveling(), (
            "precondition: the move really was rejected"
        )
        tilt_calls = _tilt_switch_calls(cover, n)
        assert any(c[0] == "turn_off" for c in tilt_calls), (
            "a rejected set_position left the tilt motor running; "
            f"tilt-relay calls: {tilt_calls!r} ({_tilt_state(cover)})"
        )
        assert not cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_set_position_while_a_same_direction_startup_delay_runs_releases_tilt(
        self, make_cover
    ):
        """``set_position``'s own "startup delay active, skipping" no-op.

        ``_handle_pre_movement_checks`` refuses to restart a same-direction move
        while a startup delay is pending — here the displaced tilt move's own
        deferred start.
        """
        cover = make_cover(
            control_mode=CONTROL_MODE_SWITCH,
            wait_for_relay_feedback=True,
            travel_time_open=30,
            travel_time_close=30,
            **DUAL,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)
        stub_switches(cover)
        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(100)
            await asyncio.sleep(0)
            assert cover._last_command == SERVICE_OPEN_COVER
            assert cover._startup_delay_task is not None
            n = len(cover.hass.services.async_call.call_args_list)
            await cover.set_position(90)  # same direction, so not restarted

        assert not cover.travel_calc.is_traveling(), (
            "precondition: the move really was skipped"
        )
        tilt_calls = _tilt_switch_calls(cover, n)
        assert any(c[0] == "turn_off" for c in tilt_calls), (
            "the startup-delay no-op left the tilt motor running; "
            f"tilt-relay calls: {tilt_calls!r} ({_tilt_state(cover)})"
        )
