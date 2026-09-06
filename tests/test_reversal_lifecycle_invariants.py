"""Reversal / lifecycle invariants — two #273/#275 hypotheses that did NOT hold.

Two traced follow-ups (a user stop swallowed during a parked reversal; an
``_abandon_active_lifecycle`` tap firing outside the deferral gate) were probed
at HEAD and neither reproduced: ``_settle_before_reversing`` already carries the
epoch guard, and abandoning a parked pre-step sends no ungated tap. These tests
lock in the correct behaviour so a future change cannot silently break it. Each
encodes the exact hypothesised scenario and asserts what the bug would violate.

Fixtures/mocks mirror tests/test_relay_feedback.py — real code paths driven
through _async_switch_state_changed with an injected command->echo gap.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from tests.helpers import stub_switches


def _echo_event(entity_id, old, new, last_changed=None):
    """Build a switch state-change event like HA fires, with a real datetime."""
    old_s = MagicMock()
    old_s.state = old
    old_s.attributes = {}
    new_s = MagicMock()
    new_s.state = new
    new_s.attributes = {}
    new_s.last_changed = last_changed or datetime.now(UTC)
    event = MagicMock()
    event.data = {"entity_id": entity_id, "old_state": old_s, "new_state": new_s}
    return event


def _turn_on_taps(cover, entity_id):
    """Every homeassistant.turn_on sent to ``entity_id`` on the mock bus."""
    return [
        c
        for c in cover.hass.services.async_call.call_args_list
        if c.args[:2] == ("homeassistant", "turn_on")
        and c.args[2].get("entity_id") == entity_id
    ]


# ---------------------------------------------------------------------------
# ITEM 1 — user-stop absorbed during a parked reversal (#273 follow-up b)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_stop_during_parked_reversal_is_honored(make_cover):
    """VERDICT: DOES-NOT-REPRODUCE.

    Hypothesis: on a toggle cover with wait_for_relay_feedback, when a reversal
    is itself parked awaiting the driving relay's ON echo and a user
    async_stop_cover arrives during that parked window, the stop is swallowed
    and the reversal drives on with no settle gap.

    Faithful interleaving: the original open is parked on switch.open's echo; a
    reversing set_cover_position(0) is issued and parks at
    ``_handle_pre_movement_checks`` (cover_base.py:~2670, the
    ``await self._await_confirmation_before_stop()`` on a still-parked start);
    THEN a user stop arrives "during that parked window". Because the reversal
    registered its wait first, on the echo it resumes first, enters the caller's
    in-motion reversal block (set_position, cover_base.py:~2273), taps STOP and
    then awaits ``_settle_before_reversing`` (cover_base.py:1437) — which DID
    capture the epoch and, when the later user stop supersedes during the 1 s
    settle, aborts the reversal. The cover stops. The later-issued command wins.

    (The only interleaving in which the reversal drives on is when the stop is
    issued BEFORE the reversal parks — i.e. the reversal is the later command,
    where driving on is correct, not a swallowed stop.)

    Production change the hypothesis called for: add an epoch/cancellation
    re-check after the ``_await_confirmation_before_stop`` await in
    ``_handle_pre_movement_checks``. It is unnecessary: ``_settle_before_reversing``
    already carries the epoch guard for this path, and the deferral gate handles
    the re-park case, so the test passes without it.
    """
    cover = make_cover(
        control_mode="toggle",
        wait_for_relay_feedback=True,
        travel_time_open=30,
        travel_time_close=30,
    )
    stub_switches(cover)
    cover.async_write_ha_state = MagicMock()

    # Original open, parked on switch.open's not-yet-arrived ON echo.
    cover.travel_calc.set_position(50)
    await cover.async_open_cover()
    await asyncio.sleep(0)
    assert cover._feedback_wait_entity == "switch.open"
    assert cover._startup_delay_task is not None
    cover.hass.services.async_call.reset_mock()

    # Reversal to the opposite side parks at _handle_pre_movement_checks.
    reversal = asyncio.ensure_future(cover.async_set_cover_position(position=0))
    for _ in range(5):
        await asyncio.sleep(0)
    # Still parked on the same wait — the reversal has not driven anything yet.
    assert cover._feedback_wait_entity == "switch.open"

    # The user stop arrives DURING the parked window.
    stop = asyncio.ensure_future(cover.async_stop_cover())
    for _ in range(3):
        await asyncio.sleep(0)

    # The relay finally confirms the original open.
    await cover._async_switch_state_changed(_echo_event("switch.open", "off", "on"))
    await asyncio.gather(reversal, stop)
    # Allow the reversal's 1 s direction-change settle to elapse.
    await asyncio.sleep(1.05)

    # The user stop is honoured: the cover is stopped, no CLOSE was driven.
    assert _turn_on_taps(cover, "switch.close") == [], (
        "a close was driven despite the user stop — the stop was swallowed"
    )
    assert cover._last_command is None
    assert cover.travel_calc.is_traveling() is False
    assert cover.travel_calc.current_position() == 50
    assert cover._feedback_wait_entity is None


# ---------------------------------------------------------------------------
# ITEM 2 — _abandon_active_lifecycle taps outside the deferral gate (#273 c)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abandon_of_parked_pre_step_sends_no_ungated_tap(make_cover):
    """VERDICT: DOES-NOT-REPRODUCE.

    Hypothesis: on a dual-motor toggle cover with wait_for_relay_feedback,
    ``_abandon_active_lifecycle`` cancels a start parked on a relay-feedback
    wait (``_cancel_startup_delay_task``) and then taps a relay directly
    (``_stop_travel_relay_if_needed`` / ``_send_tilt_stop``) WITHOUT the
    #273/#275 deferral gate, so the tap fires before the relay's ON echo and can
    be swallowed.

    Reachability findings at HEAD:
    * The only multi-phase phase that both feedback-parks (via _begin_movement)
      AND leaves ``_pending_*`` set (so _abandon proceeds past its early return)
      is the TRAVEL pre-step (``_start_travel_pre_step``): it parks on the travel
      relay with ``_pending_tilt_target`` set. This test drives exactly that.
    * A TILT pre-step (``_start_tilt_pre_step``) never feedback-parks — it calls
      ``tilt_calc.start_travel`` directly — so the item's literal premise ("a
      tilt pre-step parked on its relay awaiting feedback") is unreachable.

    When ``_abandon_active_lifecycle`` runs on the parked travel pre-step, the
    guards prevent any ungated tap: ``travel_was_running`` is False (the tracker
    never started — it is parked), so ``_stop_travel_relay_if_needed``
    (cover_base.py:3435) skips the toggle self-stopping relay; and
    ``was_tilt_motor``/``was_tilt_traveling`` are both False, so ``_send_tilt_stop``
    is skipped too. No service call is emitted.

    Production change the hypothesis called for: route _abandon's relay taps
    through ``_await_confirmation_before_stop``. It is unnecessary here — no tap
    is sent — so the test passes without it. (Separately, that the physically
    pulsed travel motor is left with no stop is a distinct "motor left running"
    concern, not the swallowed-tap this item hypothesised.)
    """
    cover = make_cover(
        control_mode="toggle",
        wait_for_relay_feedback=True,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        tilt_time_open=3,
        tilt_time_close=3,
        max_tilt_allowed_position=50,
        travel_time_open=30,
        travel_time_close=30,
    )
    stub_switches(cover)
    cover.async_write_ha_state = MagicMock()

    # Cover above the max-allowed tilt position: a tilt-open must travel to <=50
    # first, so a TRAVEL pre-step runs and parks on the travel (close) relay.
    cover.travel_calc.set_position(100)
    cover.tilt_calc.set_position(0)

    await cover.async_open_cover_tilt()
    await asyncio.sleep(0)

    # A travel pre-step is parked on the driving relay's feedback wait.
    assert cover._feedback_wait_entity == "switch.close"
    assert cover._startup_delay_task is not None
    assert cover._pending_tilt_target == 100
    parked_relay = cover._feedback_wait_entity

    cover.hass.services.async_call.reset_mock()

    # Abandon the lifecycle while the start is parked on its relay-feedback wait.
    await cover._abandon_active_lifecycle()

    # No ungated tap: the parked start is cancelled but nothing is sent to the
    # relay it was waiting on (nor any relay) before its ON echo.
    assert _turn_on_taps(cover, parked_relay) == []
    assert cover.hass.services.async_call.await_count == 0, (
        f"_abandon sent ungated relay commands: "
        f"{cover.hass.services.async_call.call_args_list}"
    )
