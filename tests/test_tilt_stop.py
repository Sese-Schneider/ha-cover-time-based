"""Stopping tilt-motor movements — audit findings core-C1a/C1b."""

import asyncio

import pytest
from unittest.mock import patch

from homeassistant.const import SERVICE_OPEN_COVER


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
