"""Tilt direction changes must be axis-aware and settle before reversing.

Audit Task 3 — three probe-confirmed defects, one coherent fix:

1. Wrong-axis stop: a tilt-only direction change sent a *travel* STOP keyed off a
   stale ``_last_command``; on toggle hardware that pulses an idle travel relay
   (a #153-class phantom travel).
2. No stop at all on an endpoint-funnel tilt reversal (and a
   ``current_tilt == target`` early-return that swallowed a mid-animation press).
3. No ``_settle_before_reversing`` gap on a tilt reversal.

``DUAL`` is redefined here (same dict as ``tests/test_tilt_stop.py``'s) — the
duplication is intentional per the plan.
"""

import asyncio

import pytest
from unittest.mock import patch


DUAL = dict(
    tilt_time_close=5.0,
    tilt_time_open=5.0,
    tilt_mode="dual_motor",
    tilt_open_switch="switch.tilt_open",
    tilt_close_switch="switch.tilt_close",
)


@pytest.mark.asyncio
async def test_toggle_opposite_tilt_direction_change_pulses_idle_travel_relay(
    make_cover,
):
    """A dual-motor toggle-opposite tilt direction change must not pulse a travel relay.

    On toggle-opposite hardware a travel STOP is a *pulse* of the opposite travel
    relay; firing it while the travel motor is stopped is itself a movement command
    (#153). A tilt-only direction change must stop the TILT axis, never pulse
    switch.open / switch.close.
    """
    cover = make_cover(control_mode="toggle_opposite", **DUAL)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(50)
    with patch.object(cover, "async_write_ha_state"):
        # 1. tilt close via slider -> tilt motor pulsed, _last_command = close_cover
        await cover.set_tilt_position(0)
        assert cover._last_command == "close_cover"
        assert cover.tilt_calc.is_traveling()
        assert not cover.travel_calc.is_traveling()
        n = len(cover.hass.services.async_call.call_args_list)

        # 2. user drags tilt slider the other way -> direction change
        await cover.set_tilt_position(100)

    travel_pulses = [
        c
        for c in cover.hass.services.async_call.call_args_list[n:]
        if c.args[1] == "turn_on"
        and c.args[2].get("entity_id") in ("switch.open", "switch.close")
    ]
    assert travel_pulses == [], (
        f"BUG: travel relay pulsed during tilt-only direction change: {travel_pulses}"
    )


@pytest.mark.asyncio
async def test_tilt_endpoint_reversal_stops_and_settles(make_cover):
    """close→open tilt reversal: stop first, then the 1.0s settle, then go."""
    import time as _t

    cover = make_cover(**DUAL)  # switch mode
    cover.travel_calc.set_position(0)
    cover.tilt_calc.set_position(80)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(20)  # tilt closing
        assert cover.tilt_calc.is_closing()
        t0 = _t.monotonic()
        await cover.async_open_cover_tilt()  # reverse mid-tilt
        elapsed = _t.monotonic() - t0
    assert elapsed >= 0.9, f"no settle gap on tilt reversal ({elapsed:.3f}s)"


@pytest.mark.asyncio
async def test_tilt_press_at_current_animated_position_stops(make_cover):
    """A tilt command targeting the instantaneous animated tilt is a stop, not a no-op.

    The tilt tracker can read an endpoint while still travelling: a tilt move
    commanded away from that endpoint whose tracking has not begun (the motor's
    startup-delay window) sits at the start position with ``is_traveling()``
    True. A press *for* that endpoint then lands on ``current_tilt == target``
    while the motor is running — the old code read that as a no-op and returned,
    leaving the tilt travelling. It must stop instead.

    The precondition state is built through the tracker's public API: a tilt move
    toward 0 whose tracking is parked (``delay``) holds the reading at 100 while
    formally travelling — the animated ``current == target`` state the old
    early-return mishandled, without the sub-percent race of reading a live
    animation.
    """
    cover = make_cover(**DUAL)
    cover.travel_calc.set_position(0)
    cover.tilt_calc.set_position(100)
    # Tilt commanded toward 0 but tracking parked (startup-delay window): the
    # tracker reads 100 while is_traveling() is True.
    cover.tilt_calc.start_travel(0, delay=3600)
    assert cover.tilt_calc.is_traveling() and cover.tilt_calc.current_position() == 100
    with patch.object(cover, "async_write_ha_state"):
        await (
            cover.async_open_cover_tilt()
        )  # press open: current(100) == target(100), still moving
    assert not cover.tilt_calc.is_traveling()


@pytest.mark.asyncio
async def test_set_position_during_shared_motor_tilt_does_not_repulse(make_cover):
    """set_position must not re-pulse a motor already running a shared-motor tilt move.

    Audit Task 5A: a shared-motor (inline/sequential) tilt move runs the SAME
    physical motor with only ``tilt_calc`` traveling. ``set_position``'s
    ``already_moving_same_dir`` and its direction-change stop check keyed only
    on ``travel_calc.is_traveling()``, so a same-direction ``set_position``
    call while a shared-motor tilt move was in flight re-issued the start
    command. On toggle hardware a second pulse of the same direction switch
    while the motor is running is read as STOP; the later auto-stop pulse
    then restarts the motor unsupervised.
    """
    cover = make_cover(
        control_mode="toggle",
        tilt_time_close=2.0,
        tilt_time_open=2.0,
        tilt_mode="inline",
    )
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(0)
    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover_tilt()  # motor running up (shared)
        assert cover.tilt_calc.is_traveling()
        n = len(cover.hass.services.async_call.call_args_list)
        await cover.set_position(80)  # same direction
    calls = [
        (c[0][1], c[0][2].get("entity_id"))
        for c in cover.hass.services.async_call.call_args_list[n:]
    ]
    assert ("turn_on", "switch.open") not in calls, calls
    assert cover.travel_calc.is_traveling()  # retargeted, not re-pulsed


# ---------------------------------------------------------------------------
# Audit Task 5B — lifecycle stops must respect the endpoint/self-stop gating.
#
# Two probe-reproduced sites sent a *travel* STOP to a motor that is idle or
# self-stopped at its limit. On toggle-opposite (momentary) hardware a travel
# STOP is a *pulse* of the opposite travel relay; firing it while the travel
# motor is stopped is itself a movement command (#153) / go-to-favourite (#133).
# The invariant under test: no travel-relay ``turn_on`` from a stop path while
# the travel motor is idle or self-stopped.
# ---------------------------------------------------------------------------


DUAL_TO = dict(
    control_mode="toggle_opposite",
    travel_time_close=0.2,
    travel_time_open=0.2,
    tilt_time_close=0.2,
    tilt_time_open=0.2,
    tilt_mode="dual_motor",
    tilt_open_switch="switch.tilt_open",
    tilt_close_switch="switch.tilt_close",
    safe_tilt_position=100,
)


@pytest.mark.asyncio
async def test_tilt_restore_at_endpoint_sends_no_travel_pulse(make_cover):
    cover = make_cover(**DUAL_TO)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(30)
    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()  # pre-step → travel → restore
        # run the lifecycle to completion
        for _ in range(30):
            await asyncio.sleep(0.05)
            await cover.auto_stop_if_necessary()
            if (
                cover.travel_calc.current_position() == 0
                and not cover._tilt_restore_active
                and cover._tilt_restore_target is None
                and not cover.tilt_calc.is_traveling()
            ):
                break
    travel_pulses = [
        (c[0][1], c[0][2].get("entity_id"))
        for c in cover.hass.services.async_call.call_args_list
        if c[0][1] == "turn_on"
        and c[0][2].get("entity_id") in ("switch.open", "switch.close")
    ]
    # exactly the initial close pulse — no restore-boundary stop pulse
    assert travel_pulses == [("turn_on", "switch.close")], travel_pulses


@pytest.mark.asyncio
async def test_abandon_tilt_prestep_sends_no_travel_pulse(make_cover):
    cover = make_cover(**{**DUAL_TO, "travel_time_close": 5.0, "travel_time_open": 5.0})
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(30)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(20)  # tilt-to-safe pre-step running
        assert cover._pending_travel_target == 20
        assert not cover.travel_calc.is_traveling()  # travel motor idle
        n = len(cover.hass.services.async_call.call_args_list)
        await cover.set_position(70)  # abandons the pre-step
    calls = [
        (c[0][1], c[0][2].get("entity_id"))
        for c in cover.hass.services.async_call.call_args_list[n:]
    ]
    unexpected = [c for c in calls if c == ("turn_on", "switch.open")]
    assert not unexpected, calls
