"""Tracking the hardware "my"/favourite reposition on an idle stop (issue #251).

Some shutters (Somfy RTS and similar) drive themselves to a hardware
"my"/favourite preset when a stop is issued while they are already stopped.
``async_stop_cover`` already forwards that stop to the hardware — that IS the
"my" trigger. These tests pin the passive *tracking* CTB layers on top: on a
genuine, CTB-originated, idle stop with ``my_position`` configured it animates
``travel_calc`` from the current position to ``my_position`` over the normal
travel time and self-settles there — WITHOUT commanding any open/close and
WITHOUT sending any stop when the tracker arrives (the device stops itself at
"my"). It is passive tracking, never driving.

The behaviour matrix (cases A-H) is drawn from the feature spec. All are built
on a wrapped cover so the underlying's forwarded service calls (open/close/stop)
are directly observable, mirroring test_send_endpoint_stop.py /
test_relay_feedback.py. The completion is driven the way the rest of the suite
drives a self-initiated move to its end: snap travel_calc to the target, then
call auto_stop_if_necessary() (the auto-updater interval is inert under the mock
hass).
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import ATTR_SUPPORTED_FEATURES

from custom_components.cover_time_based.cover import CONTROL_MODE_PULSE


def _stub_underlying(cover, *, state="open", features=CoverEntityFeature.STOP):
    """Make hass.states.get return a fixed wrapped-cover state.

    Default: a real-endpoint cover that supports native STOP but NOT
    SET_POSITION, so CTB tracks it time-based (timed position driver, whose
    holds_itself is False) and forwards a plain stop_cover — the "my" trigger.
    This isolates the _my_move_active completion mechanic: only the flag can
    flip _motor_stops_itself True during the tracking move.
    """
    st = MagicMock()
    st.state = state
    st.attributes = {ATTR_SUPPORTED_FEATURES: int(features)}
    cover.hass.states.get = lambda entity_id: st


def _cover_calls(cover, service):
    """Service calls forwarded to the wrapped cover entity for `service`."""
    return [
        c
        for c in cover.hass.services.async_call.call_args_list
        if c.args and c.args[0] == "cover" and c.args[1] == service
    ]


def _make_my(make_cover, *, my=90, at=30, **kwargs):
    """Build a wrapped cover with my_position=`my`, believed idle at `at`."""
    cover = make_cover(cover_entity_id="cover.inner", **kwargs)
    _stub_underlying(cover)
    # No platform/entity_id in a unit-constructed cover; stub the state write
    # (as the rest of the suite does with patch.object(cover, ...)).
    cover.async_write_ha_state = MagicMock()
    cover._my_position = my
    if at is not None:
        cover.travel_calc.set_position(at)
    return cover


async def _drive_to_target(cover, target):
    """Simulate the tracker reaching `target` and run the completion tail."""
    cover.travel_calc.set_position(target)
    await cover.auto_stop_if_necessary()


def _ha_calls(cover, service):
    """homeassistant.<service> calls (relay pulses), as in the pulse suite
    (test_send_endpoint_stop.py / test_cover_pulse_mode.py)."""
    return [
        c
        for c in cover.hass.services.async_call.call_args_list
        if c.args and c.args[0] == "homeassistant" and c.args[1] == service
    ]


def _relay_turn_on(cover, entity_id):
    """homeassistant.turn_on calls targeting a specific relay entity."""
    return [
        c
        for c in _ha_calls(cover, "turn_on")
        if c.args[2].get("entity_id") == entity_id
    ]


async def _cancel_tasks(cover):
    """Cancel background pulse-completion tasks (mirrors test_send_endpoint_stop.py)."""
    tasks = getattr(cover.hass, "_test_tasks", [])
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        tasks.clear()


def _make_my_pulse(make_cover, *, my=80, at=30, stop_switch="switch.stop", **kwargs):
    """Build a pulse cover with my_position=`my`, believed idle at `at`.

    Pass ``stop_switch=None`` to build one with no dedicated stop relay
    (case J).
    """
    cover = make_cover(
        control_mode=CONTROL_MODE_PULSE, stop_switch=stop_switch, **kwargs
    )
    cover.async_write_ha_state = MagicMock()
    cover._my_position = my
    if at is not None:
        cover.travel_calc.set_position(at)
    return cover


# ---------------------------------------------------------------------------
# A. The core tracking move: idle stop → animate to my, settle, no drive.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_idle_stop_tracks_to_my_and_settles(make_cover):
    """wrapped, my=90, believed idle at 30, HA stop → tracker animates 30→90,
    settles at 90, and NO open/close/extra-stop is sent for the move."""
    cover = _make_my(make_cover, my=90, at=30)

    await cover.async_stop_cover()

    # The stop was forwarded once — the hardware "my" trigger — and the tracker
    # is now animating to my_position.
    assert cover._my_move_active is True
    assert cover.travel_calc.is_traveling() is True
    assert cover.travel_calc._travel_to_position == 90
    assert len(_cover_calls(cover, "stop_cover")) == 1
    assert _cover_calls(cover, "open_cover") == []
    assert _cover_calls(cover, "close_cover") == []

    # The tracker reaches my and self-settles: no second stop, no drive command.
    await _drive_to_target(cover, 90)

    assert cover.current_cover_position == 90
    assert cover._my_move_active is False
    assert cover.travel_calc.is_traveling() is False
    assert len(_cover_calls(cover, "stop_cover")) == 1, "no completion stop"
    assert _cover_calls(cover, "open_cover") == []
    assert _cover_calls(cover, "close_cover") == []
    assert _cover_calls(cover, "set_cover_position") == []


# ---------------------------------------------------------------------------
# B. A stop while MOVING just halts — no my-move.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b_moving_stop_halts_no_my_move(make_cover):
    """wrapped, my=90, moving → stop halts as today (no my-move; position is
    wherever it stopped, not 90)."""
    cover = _make_my(make_cover, my=90, at=0)
    cover.travel_calc.start_travel(100)  # now moving up
    assert cover.travel_calc.is_traveling() is True

    await cover.async_stop_cover()

    assert cover._my_move_active is False
    assert cover.travel_calc.is_traveling() is False
    assert cover.current_cover_position < 90  # halted near 0, not driven to my


# ---------------------------------------------------------------------------
# C. my unset (None) → idle stop unchanged.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c_my_unset_idle_stop_unchanged(make_cover):
    """wrapped, my unset (None) → idle stop unchanged (position stays put)."""
    cover = _make_my(make_cover, my=None, at=30)

    await cover.async_stop_cover()

    assert cover._my_move_active is False
    assert cover.travel_calc.is_traveling() is False
    assert cover.current_cover_position == 30


# ---------------------------------------------------------------------------
# D. An echo stop (supersede=False) → no my-move.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_d_echo_stop_no_my_move(make_cover):
    """echo stop (async_stop_cover(supersede=False)) → no my-move."""
    cover = _make_my(make_cover, my=90, at=30)

    await cover.async_stop_cover(supersede=False)

    assert cover._my_move_active is False
    assert cover.travel_calc.is_traveling() is False
    assert cover.current_cover_position == 30


# ---------------------------------------------------------------------------
# E. An externally-triggered stop → no my-move.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e_external_stop_no_my_move(make_cover):
    """external stop (_triggered_externally=True) → no my-move.

    The physical dedicated-stop relay press is out of scope (and invisible for
    RTS), so an external stop must never start a tracking move.
    """
    cover = _make_my(make_cover, my=90, at=30)

    cover._triggered_externally = True
    try:
        await cover.async_stop_cover()
    finally:
        cover._triggered_externally = False

    assert cover._my_move_active is False
    assert cover.travel_calc.is_traveling() is False
    assert cover.current_cover_position == 30


# ---------------------------------------------------------------------------
# F. current already == my → no move, no spurious command.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_f_current_equals_my_no_move(make_cover):
    """current already == my → no move, no spurious command."""
    cover = _make_my(make_cover, my=30, at=30)

    await cover.async_stop_cover()

    assert cover._my_move_active is False
    assert cover.travel_calc.is_traveling() is False
    assert cover.current_cover_position == 30
    # No tracking move means no drive command was queued for it.
    assert _cover_calls(cover, "open_cover") == []
    assert _cover_calls(cover, "close_cover") == []


# ---------------------------------------------------------------------------
# G. Unknown position → snaps to my.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_g_unknown_position_snaps_to_my(make_cover):
    """unknown position (travel_calc.clear_position()) → snaps to my."""
    cover = _make_my(make_cover, my=90, at=None)
    cover.travel_calc.clear_position()
    assert cover.travel_calc.current_position() is None

    await cover.async_stop_cover()

    # With no known start position the tracker has nothing to animate, so it
    # snaps straight to my — still no open/close driven.
    assert cover.current_cover_position == 90
    assert _cover_calls(cover, "open_cover") == []
    assert _cover_calls(cover, "close_cover") == []


# ---------------------------------------------------------------------------
# H. Completion persists my_position.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_h_completion_persists_my_position(make_cover, _mock_position_store):
    """completion persists my_position (PositionStore / current_cover_position)."""
    cover = _make_my(make_cover, my=90, at=30)

    await cover.async_stop_cover()
    await _drive_to_target(cover, 90)

    assert cover.current_cover_position == 90
    assert cover._my_move_active is False
    # The settled my_position was written to the store on completion.
    assert _mock_position_store.async_save.call_args is not None
    saved = _mock_position_store.async_save.call_args.args[1]
    assert saved.get("position") == 90
    # Exactly the one teardown stop (the "my" trigger); nothing at completion.
    assert len(_cover_calls(cover, "stop_cover")) == 1
    assert _cover_calls(cover, "open_cover") == []
    assert _cover_calls(cover, "close_cover") == []


# ---------------------------------------------------------------------------
# I. Pulse mode + dedicated stop relay: the idle stop's relay pulse IS the "my"
#    trigger; the tracker animates to my and nothing pulses again on arrival.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_i_pulse_idle_stop_pulses_stop_relay_once_and_tracks_to_my(make_cover):
    """pulse + dedicated stop relay, my=80, believed idle at 30: an HA idle
    stop pulses the stop relay exactly once (async_stop_cover's base
    _send_stop, sent BEFORE _maybe_start_my_move — that pulse IS the hardware
    "my" trigger for real Somfy-style pulse hardware), the tracker then
    animates 30->80, and NO further stop pulse fires when it arrives (the
    device self-stops at "my"; _motor_stops_itself honours _my_move_active
    the same way it does for the wrapped cases)."""
    cover = _make_my_pulse(make_cover, my=80, at=30)

    await cover.async_stop_cover()

    assert cover._my_move_active is True
    assert cover.travel_calc.is_traveling() is True
    assert cover.travel_calc._travel_to_position == 80
    assert len(_relay_turn_on(cover, "switch.stop")) == 1, "the 'my' trigger pulse"

    # The tracker reaches my and self-settles: no second stop pulse.
    await _drive_to_target(cover, 80)

    assert cover.current_cover_position == 80
    assert cover._my_move_active is False
    assert cover.travel_calc.is_traveling() is False
    assert len(_relay_turn_on(cover, "switch.stop")) == 1, "no completion pulse"

    await _cancel_tasks(cover)


# ---------------------------------------------------------------------------
# J. Pulse mode WITHOUT a dedicated stop relay: known footgun — the tracker
#    still animates to my even though no "my" trigger physically fired.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j_pulse_without_stop_relay_still_tracks_to_my(make_cover):
    """pulse WITHOUT a dedicated stop relay, my=80, believed idle at 30:
    CURRENT (footgun) behaviour per the feature spec (#251) — the tracking
    mechanic (_maybe_start_my_move) has no way to know whether a real "my"
    trigger reached the hardware; it only looks at my_position /
    travel_was_moving / supersede / _triggered_externally, so it animates the
    tracker to 80 regardless. The card helper (a later task) is expected to
    warn that a dedicated stop switch is required for my_position to mean
    anything on pulse hardware; this pins that the software layer itself does
    not guard against the misconfiguration.

    NOTE: a stop-switch-less pulse cover is already "not configured" for ANY
    stop — PulseModeCover._get_missing_configuration requires a stop switch
    unconditionally (pre-existing, unrelated to my_position; verified by
    running this scenario through the real async_stop_cover() first, which
    raises HomeAssistantError("...missing stop switch...") before ever
    reaching _maybe_start_my_move). So in practice this exact misconfigured
    cover can't even process a plain HA stop, let alone a my-tracking one.
    We patch out that unrelated precondition so the my-tracking mechanic can
    be exercised and pinned in isolation, as the spec's footgun is about.
    """
    cover = _make_my_pulse(make_cover, my=80, at=30, stop_switch=None)
    assert cover._stop_switch_entity_id is None

    with patch.object(cover, "_require_configured"):
        await cover.async_stop_cover()

    # No stop relay exists, so _send_stop's relay branch never pulses anything
    # — yet the tracker still starts animating toward my_position regardless.
    assert _relay_turn_on(cover, "switch.stop") == []
    assert cover._my_move_active is True
    assert cover.travel_calc.is_traveling() is True
    assert cover.travel_calc._travel_to_position == 80

    await _drive_to_target(cover, 80)

    assert cover.current_cover_position == 80
    assert cover._my_move_active is False

    await _cancel_tasks(cover)


# ---------------------------------------------------------------------------
# Completion mechanic — _motor_stops_itself honours the flag in BOTH layers.
#
# The wrapped tests above exercise the wrapped override; these pin the flag in
# each _motor_stops_itself directly (omitting the wrapped override would let a
# wrapped cover re-forward a stop at completion and re-trigger "my").
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_motor_stops_itself_honours_flag(make_cover):
    """A relay-driven (switch) cover normally must be told to stop, but during a
    my-move (_my_move_active) it self-stops at "my" — so the flag flips it."""
    cover = make_cover()  # switch mode, base _motor_stops_itself
    assert cover._motor_stops_itself() is False
    cover._my_move_active = True
    assert cover._motor_stops_itself() is True


@pytest.mark.asyncio
async def test_wrapped_motor_stops_itself_honours_flag(make_cover):
    """The wrapped override must honour the flag too — otherwise a timed wrapped
    cover re-forwards stop_cover at completion, re-triggering "my"."""
    cover = _make_my(make_cover, my=90, at=30)
    assert cover._motor_stops_itself() is False  # timed underlying, no flag
    cover._my_move_active = True
    assert cover._motor_stops_itself() is True


@pytest.mark.asyncio
async def test_supersede_clears_my_move(make_cover):
    """A superseding command mid-tracking-move ends the my-move (the flag is
    cleared in _supersede_movement), so a later real move isn't mistaken for a
    device that self-stops."""
    cover = _make_my(make_cover, my=90, at=30)
    await cover.async_stop_cover()
    assert cover._my_move_active is True

    cover._supersede_movement()
    assert cover._my_move_active is False
