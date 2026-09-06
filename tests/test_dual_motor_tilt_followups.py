"""Tilt/dual-motor follow-up fixes — twins of the #274 items 3.13 / 3.18.

These are the twins the PR #274 reviews found but left unfixed: a plain-toggle
pre-step window, a ``set_tilt_position`` early return that strands a displaced
tilt motor, and a feedback-wait tilt at an endpoint that skipped its stop.

The dual-motor fixtures and driving style mirror tests/test_tilt_stop.py and
tests/test_cover_toggle_opposite_mode.py.
"""

import asyncio
import logging
from unittest.mock import MagicMock, patch

import pytest

from custom_components.cover_time_based import travel_calculator
from custom_components.cover_time_based.cover import (
    CONTROL_MODE_SWITCH,
    CONTROL_MODE_TOGGLE,
)
from tests.helpers import FakeClock, relay_calls, stub_switches

DUAL = {
    "tilt_time_close": 5.0,
    "tilt_time_open": 5.0,
    "tilt_mode": "dual_motor",
    "tilt_open_switch": "switch.tilt_open",
    "tilt_close_switch": "switch.tilt_close",
}


def _tilt_switch_calls(cover, start=0):
    return [
        c
        for c in relay_calls(cover, start)
        if c[1] in ("switch.tilt_open", "switch.tilt_close")
    ]


def _press(entity_id):
    """A relay rising edge, shaped like the HA state-changed event."""
    old = MagicMock()
    old.state = "off"
    old.attributes = {}
    new = MagicMock()
    new.state = "on"
    new.attributes = {}
    event = MagicMock()
    event.data = {"entity_id": entity_id, "old_state": old, "new_state": new}
    return event


# === ITEM 3: plain Toggle mode dual-motor pre-step window (twin of 3.13) ===
#
# ToggleModeCover keys its same-direction "press while moving -> stop" off the
# physical-motion helpers ``_motor_opening``/``_motor_closing``, so a dual-motor
# cover reads the travel motor as idle during a tilt-to-safe pre-step — a
# same-button press there continues the move, not tears it down as a stop.
@pytest.mark.asyncio
async def test_plain_toggle_press_during_tilt_to_safe_pre_step_starts_travel(
    make_cover, caplog
):
    """A same-direction press during a dual-motor tilt-to-safe pre-step must
    start/continue the idle travel motor, NOT stop it.

    Mirrors toggle_opposite's
    test_press_during_tilt_to_safe_pre_step_starts_travel (item 3.13).
    """
    caplog.set_level(logging.DEBUG)
    cover = make_cover(control_mode=CONTROL_MODE_TOGGLE, **DUAL)
    stub_switches(cover)
    assert cover._has_tilt_motor()
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(0)  # off the safe position -> pre-step planned

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(0)  # close, behind a tilt-to-safe pre-step
        assert cover._pending_travel_target == 0
        assert not cover.travel_calc.is_traveling(), "travel motor idle in the pre-step"
        assert cover.tilt_calc.is_traveling(), "the tilt motor runs the pre-step"
        # The base helper reports the pending close; the travel motor is idle.
        assert cover._travel_axis_closing()

        caplog.clear()
        # Same-button (close) press while the pre-step's travel is pending.
        with patch(
            "custom_components.cover_time_based.cover_base.sleep",
            new_callable=MagicMock,
        ):
            await cover._async_switch_state_changed(_press("switch.close"))

    messages = [r.getMessage() for r in caplog.records]
    assert not any("close toggle while closing, stopping" in m for m in messages), (
        f"the press during the pre-step was mis-read as a stop: {messages}"
    )
    assert any("external close toggle detected" in m for m in messages), messages
    assert cover._pending_travel_target == 0, (
        "the press must keep the close move tracked (pre-step re-planned), "
        "not discard it with a stop"
    )
    assert cover.tilt_calc.is_traveling(), (
        "the tilt-to-safe pre-step must be re-planned, not halted as on a stop"
    )


# === ITEM 4: set_tilt_position early-returns must stop a displaced motor (twin of 3.18) ===
#
# set_tilt_position captures ``was_tilt_motor_move`` before
# ``_abandon_active_lifecycle`` clears ``_moving_tilt_motor``, so every early
# return that leaves a dedicated tilt motor running (target == current,
# refused pre-movement check, too-short move) must release it — auto-stop can no
# longer find it once the flag is cleared. The travel-funnel twin is fix 3.18.
@pytest.mark.asyncio
async def test_set_tilt_position_to_current_releases_running_tilt_motor(make_cover):
    """A running dedicated tilt motor must be stopped when a fresh
    set_tilt_position early-returns because target == current."""
    cover = make_cover(control_mode=CONTROL_MODE_SWITCH, **DUAL)
    cover.travel_calc.set_position(100)
    cover.tilt_calc.set_position(50)
    stub_switches(cover)
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(travel_calculator, "time", FakeClock(wall=1000, mono=1000)),
    ):
        await cover.set_tilt_position(30)  # tilt motor 50 -> 30, mid-tilt
        assert cover._moving_tilt_motor and cover.tilt_calc.is_traveling()
        assert cover.tilt_calc.current_position() == 50
        n = len(cover.hass.services.async_call.call_args_list)
        # target == current (50): set_tilt_position takes its ``else: return``.
        await cover.set_tilt_position(50)

    tilt_calls = _tilt_switch_calls(cover, n)
    assert any(c[0] == "turn_off" for c in tilt_calls), (
        "the target==current early return left the tilt motor running; "
        f"tilt-relay calls after the command: {tilt_calls!r} "
        f"(all calls: {relay_calls(cover, n)!r})"
    )
    assert not cover.tilt_calc.is_traveling()


# The too-short early return is the third exit that must release a displaced
# tilt motor: a same-direction move too small to act on (below
# ``min_movement_time``) returns from ``_is_movement_too_short`` with the
# dedicated motor still running (never a direction change, so never stopped).
@pytest.mark.asyncio
async def test_set_tilt_position_too_short_releases_running_tilt_motor(make_cover):
    """A running dedicated tilt motor must be stopped when a fresh
    set_tilt_position early-returns because the move is below min_movement_time."""
    cover = make_cover(control_mode=CONTROL_MODE_SWITCH, min_movement_time=1.0, **DUAL)
    cover.travel_calc.set_position(100)
    cover.tilt_calc.set_position(50)
    stub_switches(cover)
    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(travel_calculator, "time", FakeClock(wall=1000, mono=1000)),
    ):
        await cover.set_tilt_position(0)  # tilt motor 50 -> 0, mid-tilt (closing)
        assert cover._moving_tilt_motor and cover.tilt_calc.is_traveling()
        assert cover.tilt_calc.current_position() == 50
        n = len(cover.hass.services.async_call.call_args_list)
        # 50 -> 49 is the same (closing) direction and only 0.05s of tilt time,
        # below the 1.0s minimum: set_tilt_position takes its too-short return.
        await cover.set_tilt_position(49)

    tilt_calls = _tilt_switch_calls(cover, n)
    assert any(c[0] == "turn_off" for c in tilt_calls), (
        "the too-short early return left the tilt motor running; "
        f"tilt-relay calls after the command: {tilt_calls!r} "
        f"(all calls: {relay_calls(cover, n)!r})"
    )
    assert not cover.tilt_calc.is_traveling()


# === ITEM 5: feedback-wait tilt at an endpoint skips the stop on toggle (twin of the departing-endpoint fix) ===
#
# _release_displaced_tilt_motor reads departure from ``tilt_calc.is_traveling()``
# OR a still-pending deferred start. Under ``wait_for_relay_feedback`` the tilt
# relay is commanded but tracking is parked on the ON echo, so is_traveling() is
# False — yet the pending deferred start marks it departing, so it gets a real
# tilt stop instead of the endpoint self-stop skip swallowing a motor that is
# actually leaving its limit.
@pytest.mark.asyncio
async def test_feedback_wait_tilt_at_endpoint_toggle_still_stops_displaced_motor(
    make_cover,
):
    """Toggle dual-motor + wait_for_relay_feedback: a travel command displacing a
    tilt motor that was just pulsed away from an endpoint must de-energise it,
    not read it as 'arrived and self-stopped'."""
    cover = make_cover(
        control_mode=CONTROL_MODE_TOGGLE, wait_for_relay_feedback=True, **DUAL
    )
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(100)  # tilt tracker parked AT the endpoint
    stub_switches(cover)
    with patch.object(cover, "async_write_ha_state"):
        # Pulse the tilt motor closed (100 -> 30). Under feedback wait, tracking
        # is parked on the relay ON echo, so tilt_calc is NOT traveling yet — but
        # the motor has been commanded to leave the endpoint.
        await cover.set_tilt_position(30)
        await asyncio.sleep(0)  # let the feedback task reach its await
        assert cover._moving_tilt_motor, "precondition: tilt motor commanded"
        assert not cover.tilt_calc.is_traveling(), "precondition: parked on the echo"
        assert cover._last_tilt_direction == "close"
        assert cover.tilt_calc.current_position() == 100
        n = len(cover.hass.services.async_call.call_args_list)
        # Travel command to the current position (already at 50): set_position
        # takes its ``target == current`` branch, which DOES call
        # _release_displaced_tilt_motor — exercising the release itself.
        await cover.set_position(50)

    tilt_calls = _tilt_switch_calls(cover, n)
    # Toggle stop re-pulses the last tilt direction -> a turn_on on tilt_close.
    assert ("turn_on", "switch.tilt_close") in tilt_calls, (
        "the feedback-wait tilt motor departing the endpoint was left energised; "
        f"tilt-relay calls after the travel command: {tilt_calls!r} "
        f"(all calls: {relay_calls(cover, n)!r})"
    )
