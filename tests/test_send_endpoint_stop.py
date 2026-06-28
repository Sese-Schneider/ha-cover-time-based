"""Configurable endpoint stop for pulse mode (issue #133).

"Pulse mode" serves two physically opposite momentary controllers:

- A **latching** controller (issue #129) keeps running until it receives a
  dedicated stop pulse — it MUST get the endpoint stop or it stays stuck
  "moving". This is the default (``send_endpoint_stop=True``).
- An **auto-stop** controller (issue #133) halts itself at its 0%/100% limits;
  a stop pulse received while already stopped is read as "go to favourite",
  repositioning the cover. For this hardware the endpoint stop is harmful and
  must be skipped (``send_endpoint_stop=False``).

These tests pin the per-cover ``send_endpoint_stop`` option that selects
between the two, mirroring the toggle-mode ``relay_reports_off`` option.
"""

import asyncio

import pytest
from unittest.mock import patch

from homeassistant.const import SERVICE_CLOSE_COVER

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


def _make_pulse(make_cover, send_endpoint_stop=None, **kwargs):
    """Build a pulse cover, optionally setting send_endpoint_stop."""
    return make_cover(
        control_mode=CONTROL_MODE_PULSE,
        stop_switch="switch.stop",
        send_endpoint_stop=send_endpoint_stop,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Default sends the endpoint stop (deferred by run-on) — guards #129.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_pulse_sends_endpoint_stop(make_cover):
    """Default (option unset) pulse cover at an endpoint still pulses its stop
    relay (deferred by run-on) — the #129 behaviour, unchanged."""
    cover = _make_pulse(make_cover, endpoint_runon_time=2.0)
    assert cover._self_stops_at_endpoints() is False
    cover._self_initiated_movement = True
    cover._last_command = SERVICE_CLOSE_COVER
    cover.travel_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    assert cover._delay_task is not None, (
        "default pulse must defer the endpoint stop to the run-on timer (#129)"
    )
    await _cancel_tasks(cover)


# ---------------------------------------------------------------------------
# 2. Option off skips the endpoint stop, but a mid-travel stop still fires.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_option_off_pulse_skips_endpoint_stop(make_cover):
    """With send_endpoint_stop=False the pulse cover behaves as self-stopping:
    reaching an endpoint fires NO relay stop and schedules no run-on (#133)."""
    cover = _make_pulse(make_cover, send_endpoint_stop=False, endpoint_runon_time=2.0)
    assert cover._self_stops_at_endpoints() is True
    cover._self_initiated_movement = True
    cover._last_command = SERVICE_CLOSE_COVER
    cover.travel_calc.set_position(0)

    cover.hass.services.async_call.reset_mock()
    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    assert _ha_calls(cover) == [], "option off must send no endpoint stop pulse (#133)"
    assert cover._delay_task is None, "option off must not schedule run-on at endpoint"
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_option_off_pulse_mid_travel_still_stops(make_cover):
    """send_endpoint_stop=False only suppresses the stop AT an endpoint — a
    mid-travel stop (nothing self-stops there) must still pulse the stop relay."""
    cover = _make_pulse(make_cover, send_endpoint_stop=False, endpoint_runon_time=0)
    cover._self_initiated_movement = True
    cover._last_command = SERVICE_CLOSE_COVER
    cover.travel_calc.set_position(50)  # mid-travel, not an endpoint

    cover.hass.services.async_call.reset_mock()
    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    stop_on = [
        c
        for c in _ha_calls(cover)
        if c.args[1] == "turn_on" and c.args[2].get("entity_id") == "switch.stop"
    ]
    assert stop_on, "mid-travel stop must still pulse the stop relay"
    await _cancel_tasks(cover)


# ---------------------------------------------------------------------------
# 3. Tilt endpoint follows the flag (dual-motor pulse).
# ---------------------------------------------------------------------------


def _make_pulse_dual_motor(make_cover, send_endpoint_stop=None):
    return make_cover(
        control_mode=CONTROL_MODE_PULSE,
        stop_switch="switch.stop",
        send_endpoint_stop=send_endpoint_stop,
        tilt_time_close=2.0,
        tilt_time_open=2.0,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        tilt_stop_switch="switch.tilt_stop",
    )


async def _run_tilt_move(cover, target):
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(target)
        cover.hass.services.async_call.reset_mock()
        cover.tilt_calc.set_position(target)
        await cover.auto_stop_if_necessary()


@pytest.mark.asyncio
async def test_option_off_pulse_dual_motor_skips_tilt_endpoint_stop(make_cover):
    """With the option off, a pulse dual-motor cover skips the tilt-stop relay at
    a tilt endpoint (the same flag gates _tilt_settle)."""
    cover = _make_pulse_dual_motor(make_cover, send_endpoint_stop=False)
    cover.travel_calc.set_position(50)  # mid-travel: isolate tilt
    cover.tilt_calc.set_position(0)

    await _run_tilt_move(cover, 100)  # tilt to its open endpoint

    tilt_stop_on = [
        c
        for c in _ha_calls(cover)
        if c.args[1] == "turn_on" and c.args[2].get("entity_id") == "switch.tilt_stop"
    ]
    assert tilt_stop_on == [], "option off must skip the tilt endpoint stop (#133)"
    await _cancel_tasks(cover)


@pytest.mark.asyncio
async def test_default_pulse_dual_motor_pulses_tilt_endpoint_stop(make_cover):
    """With the option on (default), a pulse dual-motor cover still pulses its
    tilt-stop relay at a tilt endpoint — the tilt twin of #129."""
    cover = _make_pulse_dual_motor(make_cover)  # option unset → default on
    cover.travel_calc.set_position(50)  # mid-travel: isolate tilt
    cover.tilt_calc.set_position(0)

    await _run_tilt_move(cover, 100)  # tilt to its open endpoint

    tilt_stop_on = [
        c
        for c in _ha_calls(cover)
        if c.args[1] == "turn_on" and c.args[2].get("entity_id") == "switch.tilt_stop"
    ]
    assert tilt_stop_on, "default pulse must pulse the tilt endpoint stop (#129)"
    await _cancel_tasks(cover)


# ---------------------------------------------------------------------------
# 4. Run-on still applies when the option is on.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_option_on_pulse_defers_endpoint_stop_by_runon(make_cover):
    """With the option on and a run-on time set, the endpoint stop is deferred by
    that run-on, not fired immediately (a _delay_task is scheduled)."""
    cover = _make_pulse(make_cover, send_endpoint_stop=True, endpoint_runon_time=2.0)
    cover._self_initiated_movement = True
    cover._last_command = SERVICE_CLOSE_COVER
    cover.travel_calc.set_position(0)

    cover.hass.services.async_call.reset_mock()
    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    assert cover._delay_task is not None, (
        "option on must defer the endpoint stop by the run-on time"
    )
    # The immediate stop relay must NOT have fired yet (it is deferred).
    stop_on = [
        c
        for c in _ha_calls(cover)
        if c.args[1] == "turn_on" and c.args[2].get("entity_id") == "switch.stop"
    ]
    assert stop_on == [], "the deferred stop must not fire immediately"
    await _cancel_tasks(cover)


# ---------------------------------------------------------------------------
# 5. Other modes unchanged — toggle and wrapped ignore the option.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_ignores_send_endpoint_stop(make_cover):
    """Toggle mode always self-stops at endpoints regardless of the option, which
    it does not even accept."""
    cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
    assert cover._self_stops_at_endpoints() is True


@pytest.mark.asyncio
async def test_wrapped_ignores_send_endpoint_stop(make_cover):
    """A wrapped (non-native-position) cover self-stops at endpoints regardless
    of the option."""
    cover = make_cover(cover_entity_id="cover.inner")
    assert cover._self_stops_at_endpoints() is True


@pytest.mark.asyncio
async def test_switch_ignores_send_endpoint_stop(make_cover):
    """Switch mode never self-stops at endpoints (latched relay) regardless of
    the option."""
    cover = make_cover(control_mode=CONTROL_MODE_SWITCH)
    assert cover._self_stops_at_endpoints() is False
