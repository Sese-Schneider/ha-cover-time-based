"""External multi-phase moves must stay track-only across the phase boundary.

When a wall button (not HA) drives a dual-motor cover through a multi-phase
move, HA only *tracks* the motion; the hardware is doing the actual work. The
first phase (tilt-to-safe, or a travel pre-step) is entered on the external
handler's own task, where ``_triggered_externally`` is set. But the *second*
phase is started from ``auto_stop_if_necessary``, which the auto-updater hook
runs on a fresh ``hass.async_create_task`` — a task where the task-scoped
``_triggered_externally`` flag is always False. The only origin marker that
survives across that task boundary is the instance flag
``_self_initiated_movement``.

These tests reproduce the real task topology: the flag is set on the handler's
task, and the continuation runs on a *different* task, exactly like the
production ``auto_updater_hook``. The integration must fire no relay commands
at the phase boundary for an externally-triggered move.
"""

import asyncio
from unittest.mock import patch

import pytest

RELAY_ENTITIES = (
    "switch.open",
    "switch.close",
    "switch.tilt_open",
    "switch.tilt_close",
    "switch.tilt_stop",
)


def _relay_calls(cover, start_index=0):
    """Relay (service, entity_id) tuples fired since ``start_index``."""
    calls = cover.hass.services.async_call.call_args_list[start_index:]
    return [
        (c[0][1], c[0][2].get("entity_id"))
        for c in calls
        if c[0][2].get("entity_id") in RELAY_ENTITIES
    ]


@pytest.mark.asyncio
async def test_external_tilt_prestep_continuation_fires_no_relays(make_cover):
    """Dual-motor external close: tilt-to-safe pre-step, then travel.

    The wall button closed the cover. Tilt (30) is not at the safe position
    (100 default), so a tilt pre-step is queued and the travel to 0 is pending.
    When tilt reaches safe, the continuation must only start travel *tracking*
    — no tilt-stop and no close relay, because the hardware is driving both.
    """
    cover = make_cover(
        tilt_time_close=5.0,
        tilt_time_open=5.0,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
    )
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(30)

    # Production dispatcher shape: the external handler runs on its own task
    # with the flag set for the life of that call.
    async def external_close():
        cover._triggered_externally = True
        try:
            await cover.async_close_cover()
        finally:
            cover._triggered_externally = False

    with patch.object(cover, "async_write_ha_state"):
        await asyncio.get_event_loop().create_task(external_close())

    # Tilt pre-step is in flight; travel to 0 is pending, and the move is
    # correctly recorded as NOT self-initiated.
    assert cover._pending_travel_target == 0
    assert cover._self_initiated_movement is False

    n_before = len(cover.hass.services.async_call.call_args_list)

    # Pre-step completes (tilt reaches the safe position). The continuation
    # runs on its *own* task, exactly like auto_updater_hook's
    # hass.async_create_task(self.auto_stop_if_necessary()).
    cover.tilt_calc.set_position(100)
    with patch.object(cover, "async_write_ha_state"):
        await asyncio.get_event_loop().create_task(cover.auto_stop_if_necessary())

    relay_calls = _relay_calls(cover, n_before)
    assert relay_calls == [], (
        f"external tilt-pre-step continuation fired relay commands: {relay_calls}"
    )
    # Second phase is still *tracked* so the integration mirrors the motor.
    assert cover.travel_calc.is_traveling()
    assert cover.travel_calc._travel_to_position == 0


@pytest.mark.asyncio
async def test_external_travel_prestep_continuation_fires_no_relays(make_cover):
    """Dual-motor external tilt-close: travel pre-step, then tilt.

    ``max_tilt_allowed_position=20`` and travel is at 80, so tilt is not
    allowed yet. An external tilt-close first drives travel down to 20 (the
    pre-step), then tilts to 0. When the travel pre-step completes, the
    continuation must only start tilt *tracking* — no travel-stop and no tilt
    relay, because the hardware is driving both phases.
    """
    cover = make_cover(
        tilt_time_close=5.0,
        tilt_time_open=5.0,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        max_tilt_allowed_position=20,
    )
    cover.travel_calc.set_position(80)  # above max tilt allowed
    cover.tilt_calc.set_position(100)

    async def external_tilt():
        cover._triggered_externally = True
        try:
            await cover.async_close_cover_tilt()
        finally:
            cover._triggered_externally = False

    with patch.object(cover, "async_write_ha_state"):
        await asyncio.get_event_loop().create_task(external_tilt())

    # Travel pre-step in flight; tilt to 0 is pending; not self-initiated.
    assert cover._pending_tilt_target == 0
    assert cover._self_initiated_movement is False

    n_before = len(cover.hass.services.async_call.call_args_list)

    # Travel pre-step completes; continuation runs on its own task.
    cover.travel_calc.set_position(20)
    with patch.object(cover, "async_write_ha_state"):
        await asyncio.get_event_loop().create_task(cover.auto_stop_if_necessary())

    relay_calls = _relay_calls(cover, n_before)
    assert relay_calls == [], (
        f"external travel-pre-step continuation fired relay commands: {relay_calls}"
    )
    # Second phase (tilt) is still tracked.
    assert cover.tilt_calc.is_traveling()
    assert cover.tilt_calc._travel_to_position == 0
