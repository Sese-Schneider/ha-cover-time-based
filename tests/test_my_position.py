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

from unittest.mock import MagicMock

import pytest
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import ATTR_SUPPORTED_FEATURES


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
