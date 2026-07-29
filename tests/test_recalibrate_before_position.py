"""Fully open before moving to a position (issue #179).

A cover with no position feedback that an unseen remote can also move drifts:
Home Assistant keeps tracking from its last known position while the real cover
is somewhere else. With recalibrate_before_position on, a set_position command
first drives the cover fully open — a true datum, since the motor stalls at its
limit — and only then moves to the requested position.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
)
from homeassistant.exceptions import HomeAssistantError


@pytest.mark.asyncio
async def test_option_exposed_as_state_attribute(make_cover):
    cover = make_cover(recalibrate_before_position=True)
    assert cover.extra_state_attributes["recalibrate_before_position"] is True


@pytest.mark.asyncio
async def test_option_off_moves_directly(make_cover):
    """Regression guard: with the option off nothing changes."""
    cover = make_cover()
    cover.travel_calc.set_position(75)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(25)

    assert cover.travel_calc.is_closing(), "must head straight for the target"
    assert cover.travel_calc._travel_to_position == 25
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_leg_a_drives_full_open_and_arms_leg_b(make_cover):
    """Believed 75, asked for 25: leg A is a full-travel open, leg B is armed."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(25)

    assert cover.travel_calc.is_opening(), "leg A must open, not close"
    assert cover.travel_calc._travel_to_position == 100
    assert cover._last_command == SERVICE_OPEN_COVER
    assert cover._pending_recalibrated_target == 25
    assert cover._pending_recalibrated_axis == "travel"
    assert cover._recalibration_epoch == cover._movement_epoch


@pytest.mark.asyncio
async def test_leg_b_runs_after_leg_a_completes(make_cover):
    """Leg A reaching 100 chains into the requested move from a true 100."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_position(25)
        cover.travel_calc.set_position(100)  # leg A arrives
        await cover.auto_stop_if_necessary()

    assert cover._pending_recalibrated_target is None
    assert cover.travel_calc.is_closing(), "leg B must head down to the target"
    assert cover.travel_calc._travel_to_position == 25
    assert cover._last_command == SERVICE_CLOSE_COVER


@pytest.mark.asyncio
async def test_leg_b_awaits_the_settle_gap(make_cover):
    """auto_stop_if_necessary clears _last_command, so leg B would not read
    itself as a direction change. Without an explicit settle it reverses the
    motor with no rest — the exact hazard DIRECTION_CHANGE_DELAY exists for."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)
    settle = AsyncMock()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=settle),
    ):
        await cover.set_position(25)
        cover.travel_calc.set_position(100)
        await cover.auto_stop_if_necessary()

    settle.assert_awaited_once()


@pytest.mark.asyncio
async def test_target_100_is_a_single_forced_open(make_cover):
    """An endpoint target IS the recalibration — no pointless extra leg.

    Finding 3 (fix round 1): that is only true if the single drive is
    actually a *forced* full-travel open modelled from the opposite
    endpoint (0), not an ordinary timed move computed from the believed
    position (30) -- the value this whole feature exists to distrust. Default
    control_mode is switch, which does not self-stop at its endpoints (its
    latched relay is cut by an explicit stop after the computed duration), so
    an ordinary timed move here would strand the cover under drift.
    """
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(30)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(100)

    assert cover.travel_calc.is_opening()
    assert cover.travel_calc._travel_to_position == 100
    assert cover.travel_calc._last_known_position == 0, (
        "must be modelled as a full-travel open starting from the opposite"
        " endpoint (0), not an ordinary move from the believed 30"
    )
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_target_0_has_no_open_leg(make_cover):
    """Going fully closed must not drive fully open first.

    Finding 3 (fix round 1) companion to the above: the single drive to 0
    must be a forced full-travel close modelled from the opposite endpoint
    (100), not an ordinary timed move from the believed position (30).
    """
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(30)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(0)

    assert cover.travel_calc.is_closing(), "must close, not open first"
    assert cover.travel_calc._travel_to_position == 0
    assert cover.travel_calc._last_known_position == 100, (
        "must be modelled as a full-travel close starting from the opposite"
        " endpoint (100), not an ordinary move from the believed 30"
    )
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_option_off_endpoint_targets_unchanged(make_cover):
    """Finding 3 (fix round 1) regression guard: with the option off, an
    endpoint target is an ordinary timed move from the believed position,
    exactly as before the fix -- the forced-redrive path must not fire when
    the feature itself is off."""
    cover = make_cover()
    cover.travel_calc.set_position(30)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(0)

    assert cover.travel_calc.is_closing()
    assert cover.travel_calc._travel_to_position == 0
    assert cover.travel_calc._last_known_position == 30, (
        "option off: must be an ordinary timed move from the believed"
        " position (30), not a forced full redrive from the opposite endpoint"
    )


@pytest.mark.asyncio
async def test_endpoint_redrive_rolls_back_when_not_started(make_cover):
    """Finding 3 (fix round 1): mirrors test_rollback_when_leg_a_does_not_start
    for the endpoint-target path. When the forced full redrive silently does
    not start (_movement_started reports False), the tracker must roll back
    to the believed position rather than being left seeded at the fabricated
    opposite endpoint, and the fallback plain move must be planned from that
    restored position."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(30)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_movement_started", return_value=False),
    ):
        await cover.set_position(0)

    assert cover._pending_recalibrated_target is None
    assert cover.travel_calc._travel_to_position == 0
    assert cover.travel_calc._last_known_position == 30, (
        "tracker must be rolled back to the believed position (30), not left"
        " seeded at the fabricated opposite endpoint (100)"
    )
    assert cover.travel_calc.is_closing(), "fallback plain move: 30 -> 0 is a close"


@pytest.mark.asyncio
async def test_recalibrate_false_endpoint_target_not_forced(make_cover):
    """Finding 3 (fix round 1) guard: ``recalibrate=False`` must also skip
    the forced-redrive path, not just leg-arming -- a caller that explicitly
    opts out (as the internal leg-B re-entry does) must never trigger a
    forced endpoint redrive."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(30)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(0, recalibrate=False)

    assert cover.travel_calc.is_closing()
    assert cover.travel_calc._last_known_position == 30, (
        "recalibrate=False must move directly from the believed position,"
        " not force a full redrive from the opposite endpoint"
    )


@pytest.mark.asyncio
async def test_external_trigger_never_forces_endpoint_redrive(make_cover):
    """Finding 3 (fix round 1) guard: a physical press landing on an
    endpoint target must never be intercepted into a forced full redrive --
    external moves only track what the hardware already did."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(30)

    with patch.object(cover, "async_write_ha_state"):
        cover._triggered_externally = True
        try:
            await cover.set_position(0)
        finally:
            cover._triggered_externally = False

    assert cover.travel_calc.is_closing()
    assert cover.travel_calc._last_known_position == 30, (
        "external trigger must move directly from the believed position,"
        " not force a full redrive from the opposite endpoint"
    )


@pytest.mark.asyncio
async def test_external_trigger_never_recalibrates(make_cover):
    """A physical press must never cause a surprise full-open."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    with patch.object(cover, "async_write_ha_state"):
        cover._triggered_externally = True
        try:
            await cover.set_position(25)
        finally:
            cover._triggered_externally = False

    assert cover.travel_calc.is_closing()
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_leg_b_does_not_arm_a_third_leg(make_cover):
    """Leg B re-enters with recalibrate=False, so the chain terminates."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_position(25)
        cover.travel_calc.set_position(100)
        await cover.auto_stop_if_necessary()
        cover.travel_calc.set_position(25)  # leg B arrives
        await cover.auto_stop_if_necessary()

    assert cover._pending_recalibrated_target is None
    assert not cover.travel_calc.is_traveling(), "no third leg"


@pytest.mark.asyncio
async def test_min_movement_time_does_not_strand_leg_b(make_cover):
    """Fix round 1, IMPORTANT 1: min_movement_time must not silently drop leg
    B after leg A has already moved the cover. Believed 75, asked for 95, with
    min_movement_time=2: leg A drives fully open (a real, full-length motor
    run), then leg B's pulse back down to 95 computes to 0.5s -- under the 2s
    floor. min_movement_time exists to skip pointless motor pulses for
    imperceptible moves; once leg A has already run the motor a full travel,
    that rationale is gone -- the second pulse is the entire point of the
    operation, and dropping it would strand the cover fully open instead of
    at the 95% the user asked for."""
    cover = make_cover(recalibrate_before_position=True, min_movement_time=2)
    cover.travel_calc.set_position(75)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_position(95)
        cover.travel_calc.set_position(100)  # leg A arrives
        await cover.auto_stop_if_necessary()

    assert cover._pending_recalibrated_target is None
    assert cover.travel_calc.is_closing(), (
        "leg B must still run despite being 'too short'"
    )
    assert cover.travel_calc._travel_to_position == 95


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"control_mode": "pulse", "stop_switch": "switch.stop"},
        {"control_mode": "toggle", "close_switch": "switch.open"},
        {"control_mode": "toggle_opposite"},
        {"cover_entity_id": "cover.real"},
    ],
    ids=["switch", "pulse", "toggle", "toggle_opposite", "wrapped"],
)
async def test_recalibration_leg_runs_in_every_mode(make_cover, kwargs):
    cover = make_cover(recalibrate_before_position=True, **kwargs)
    cover.travel_calc.set_position(75)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(25)

    assert cover.travel_calc.is_opening()
    assert cover._pending_recalibrated_target == 25


# ===================================================================
# Fix round 1 — dual_motor stranding (CRITICAL 1)
# ===================================================================


def _make_dual_motor(make_cover, **kwargs):
    return make_cover(
        recalibrate_before_position=True,
        tilt_time_close=2.0,
        tilt_time_open=2.0,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        tilt_stop_switch="switch.tilt_stop",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_leg_b_runs_after_dual_motor_default_safe_position_restore(make_cover):
    """CRITICAL 1 regression: leg A's travel target (100) coincides with the
    default safe_tilt_position (100), so the dual-motor tilt-to-safe pre-step
    already parks tilt exactly where the post-travel "restore" phase would
    put it. _start_tilt_restore therefore takes its synchronous "no restore
    needed" shortcut: no new movement is started and the auto-updater is
    never re-armed, so this shortcut return IS the terminal completion of
    leg A. Before the fix, nothing on this path consumed the armed
    recalibration leg, stranding the cover at 100% forever with no error and
    no log."""
    cover = _make_dual_motor(make_cover)
    cover.travel_calc.set_position(75)
    cover.tilt_calc.set_position(0)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_position(25)
        assert cover._pending_recalibrated_target == 25

        # Tilt pre-step (to the safe position, 100 by default) completes.
        cover.tilt_calc.set_position(100)
        await cover.auto_stop_if_necessary()

        # Travel (leg A) reaches the fully-open datum. Tilt is already at the
        # restore target (100), so _start_tilt_restore's shortcut fires.
        cover.travel_calc.set_position(100)
        await cover.auto_stop_if_necessary()

    assert not cover._tilt_restore_active, "the restore must have been a no-op shortcut"
    assert cover._pending_recalibrated_target is None, "leg B must not be stranded"
    assert cover.travel_calc.is_traveling(), "leg B must actually start"
    assert cover.travel_calc._travel_to_position == 25


@pytest.mark.asyncio
async def test_leg_b_runs_after_dual_motor_genuine_tilt_restore(make_cover):
    """Companion to the above, for the non-default configuration where a
    tilt restore is genuinely needed (safe_tilt_position != leg A's target).
    _start_tilt_restore claims a real restore (drives the tilt motor)
    instead of taking the synchronous shortcut, and its completion is
    handled by the `_tilt_restore_active` branch. Pins that leg B still runs
    there, and is not double-fired by the shortcut-path fix exercised
    above."""
    cover = _make_dual_motor(make_cover, safe_tilt_position=50)
    cover.travel_calc.set_position(75)
    cover.tilt_calc.set_position(0)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_position(25)

        # Tilt pre-step (to the safe position, 50) completes.
        cover.tilt_calc.set_position(50)
        await cover.auto_stop_if_necessary()

        # Travel (leg A) reaches the fully-open datum. Tilt (50) now differs
        # from the restore target (100), so a real restore is claimed.
        cover.travel_calc.set_position(100)
        await cover.auto_stop_if_necessary()
        assert cover._tilt_restore_active, "a genuine restore must be claimed here"
        assert cover._pending_recalibrated_target == 25, "not consumed until it settles"

        # The tilt restore itself completes.
        cover.tilt_calc.set_position(100)
        await cover.auto_stop_if_necessary()

    assert cover._pending_recalibrated_target is None, "leg B must not be stranded"


# ===================================================================
# Fix round 1 — _movement_started false-positive (IMPORTANT 2 / 3)
# ===================================================================


@pytest.mark.asyncio
async def test_movement_started_ignores_preexisting_startup_delay(make_cover):
    """IMPORTANT 2 regression: a startup delay left over from an earlier,
    unrelated move must not read as leg A having started. Before the fix,
    _movement_started() treated ANY live startup-delay task as proof of
    movement, including one armed by a prior command that _force_full_redrive
    itself never touched (its own attempt hit "startup delay already active,
    not restarting" and returned without doing anything) -- reporting false
    success, skipping the snapshot rollback, and leaving the tracker seeded
    at the fabricated opposite endpoint (0) with leg B wrongly armed against
    a movement that was never actually driving to 100."""
    cover = make_cover(recalibrate_before_position=True, travel_startup_delay=2.0)
    cover.travel_calc.set_position(30)

    with patch.object(cover, "async_write_ha_state"):
        # An ordinary move to 100 is issued and is still inside its startup
        # delay: the relay is on, but travel_calc hasn't started animating.
        await cover.async_open_cover()
        assert cover._startup_delay_task is not None
        assert not cover._startup_delay_task.done()
        assert not cover.travel_calc.is_traveling()

        # A recalibrated set_position arrives while that unrelated delay is
        # still pending.
        await cover.set_position(25)

    assert cover._pending_recalibrated_target is None, (
        "leg B must not be armed against a leg A that never started"
    )
    assert cover.travel_calc.current_position() != 0, (
        "tracker must not be left corrupted at the fabricated opposite endpoint"
    )


@pytest.mark.asyncio
async def test_rollback_when_leg_a_does_not_start(make_cover):
    """IMPORTANT 3: pins _start_recalibration_drive's snapshot/rollback in
    isolation. A prior review deleted that method's entire body (snapshot,
    guard, rollback) and all of Task 2's tests still passed. Force
    _movement_started to report that leg A never actually got going --
    whatever the cause -- and confirm the fabricated opposite-endpoint seed
    is rolled back to the believed position rather than left standing, that
    nothing is armed, and that the fallback plain move heads toward the
    requested target from the believed (restored) position."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_movement_started", return_value=False),
    ):
        await cover.set_position(25)

    assert cover._pending_recalibrated_target is None, "nothing must be armed"
    assert cover.travel_calc._travel_to_position == 25, (
        "the fallback move must head to the originally requested target"
    )
    assert cover.travel_calc.is_closing(), (
        "planned from the restored believed position (75), 25 is a close"
    )


# ===================================================================
# Fix round 1 — stale pending state on epoch mismatch (MINOR 4)
# ===================================================================


@pytest.mark.asyncio
async def test_maybe_start_recalibrated_leg_clears_pending_state_on_epoch_mismatch(
    make_cover,
):
    """MINOR 4 (fix round 1) / Task 3 finding (a): a superseded leg B must not
    linger forever. Originally regression-tested only via the epoch-mismatch
    early return in _maybe_start_recalibrated_leg, which still clears
    unconditionally on a mismatch as belt-and-braces. Task 3 closes the gap
    further upstream: _clear_multiphase_tilt_state (invoked by every
    supersede, via _handle_stop) now knows about these three fields too, so
    the supersede itself clears them immediately -- nothing is left stale
    even before _maybe_start_recalibrated_leg ever runs again."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(25)
        assert cover._pending_recalibrated_target == 25
        armed_epoch = cover._recalibration_epoch

        # A newer command supersedes the movement (bumps _movement_epoch)
        # before leg A ever completes.
        await cover.async_stop_cover()
        assert cover._movement_epoch != armed_epoch
        assert cover._pending_recalibrated_target is None, (
            "cleared immediately by the supersede, not left stale"
        )

        # A stray/leftover completion call is now a pure no-op (target is
        # already None), and must still leave everything cleared.
        await cover._maybe_start_recalibrated_leg()

    assert cover._pending_recalibrated_target is None
    assert cover._pending_recalibrated_axis is None
    assert cover._recalibration_epoch is None


# ===================================================================
# Fix round 1 — recalibration pre-empts the already-at-target no-op (MINOR 5)
# ===================================================================


@pytest.mark.asyncio
async def test_recalibration_overrides_already_at_target_noop(make_cover):
    """Recalibration is decided before set_position's normal "already at
    target" no-op. Asking for the position the tracker already believes it
    holds still triggers a full-open-then-return rather than doing nothing --
    intended, since the whole premise of the feature is that the tracker is
    not trustworthy. Pinned here as a decision, not an accident."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(25)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(25)

    assert cover.travel_calc.is_opening(), "must still drive leg A, not no-op"
    assert cover.travel_calc._travel_to_position == 100
    assert cover._pending_recalibrated_target == 25


# ===================================================================
# Task 3 — cancellation and error handling
# ===================================================================


@pytest.mark.asyncio
async def test_stop_during_leg_a_cancels_leg_b(make_cover):
    """A stop mid-recalibration must not be followed by a surprise move."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(25)
        await cover.async_stop_cover()

    assert cover._pending_recalibrated_target is None

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.auto_stop_if_necessary()

    assert not cover.travel_calc.is_traveling(), "no leg B after a stop"


@pytest.mark.asyncio
async def test_new_command_during_leg_a_supersedes(make_cover):
    """A fresh set_position replaces the pending leg rather than queueing."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(25)
        await cover.set_position(60, recalibrate=False)

    assert cover._pending_recalibrated_target is None
    assert cover.travel_calc._travel_to_position == 60


@pytest.mark.asyncio
async def test_stop_inside_the_settle_gap_aborts_leg_b(make_cover):
    """_settle_before_reversing re-checks the epoch; a stop landing in the gap
    must win, not be overridden the moment the settle finishes."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    async def stop_during_settle():
        cover._supersede_movement()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", side_effect=stop_during_settle),
    ):
        await cover.set_position(25)
        cover.travel_calc.set_position(100)
        await cover.auto_stop_if_necessary()

    assert not cover.travel_calc.is_traveling(), "leg B must abort"


@pytest.mark.asyncio
async def test_leg_b_waits_for_the_endpoint_runon(make_cover):
    """The run-on relay must be de-energised before the settle gap starts,
    or the 'rest' happens while the motor is still powered."""
    cover = make_cover(recalibrate_before_position=True, endpoint_runon_time=2.0)
    cover.travel_calc.set_position(75)
    order = []

    async def fake_runon(_delay):
        order.append("runon")

    async def fake_settle():
        order.append("settle")

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_delayed_stop", side_effect=fake_runon),
        patch.object(cover, "_direction_change_delay", side_effect=fake_settle),
    ):
        await cover.set_position(25)
        cover.travel_calc.set_position(100)
        await cover.auto_stop_if_necessary()

    assert order == ["runon", "settle"], f"run-on must precede the settle: {order}"


@pytest.mark.asyncio
async def test_leg_b_failure_does_not_escape(make_cover):
    """Leg B runs on a fresh per-tick task (hass.async_create_task, not
    literally "the auto-updater" -- stop_auto_updater() has already run by
    this point). An escaping HomeAssistantError would still surface only as a
    noisy unhandled-task-exception log and, worse, silently abandon the move
    the user asked for. The cover is parked at a true endpoint, so stopping
    there is safe and correctly tracked; warn instead of losing it."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_position(25)
        cover.travel_calc.set_position(100)
        with patch.object(
            cover,
            "set_position",
            side_effect=HomeAssistantError("switch unavailable"),
        ):
            await cover.auto_stop_if_necessary()

    assert cover.travel_calc.current_position() == 100


@pytest.mark.asyncio
async def test_maybe_start_recalibrated_leg_propagates_own_cancellation(make_cover):
    """Cancelling the task that is running _maybe_start_recalibrated_leg (a
    fresh per-tick task from hass.async_create_task -- e.g. torn down on
    entity removal or HA shutdown) must propagate as a real cancellation of
    that task.

    A bare `await delay_task` (or contextlib.suppress(CancelledError) around
    one) cannot tell "the run-on task I'm waiting on was cancelled by a
    supersede" apart from "I myself was cancelled" -- both surface as
    CancelledError at the same await point, and a bare await would also
    propagate MY cancellation down into delay_task, killing the pending
    relay de-energisation. asyncio.wait keeps the two independent: the inner
    task's own cancellation is absorbed (checked below by
    test_..._absorbs_delay_task_cancellation) while an outer cancellation of
    this task still propagates out through the await, without touching
    delay_task at all.
    """
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(100)
    cover._pending_recalibrated_target = 25
    cover._pending_recalibrated_axis = "travel"
    cover._recalibration_epoch = cover._movement_epoch
    cover._delay_task = asyncio.ensure_future(asyncio.sleep(10))
    settle = AsyncMock()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=settle),
    ):
        task = asyncio.ensure_future(cover._maybe_start_recalibrated_leg())
        await asyncio.sleep(0)  # let it reach `await delay_task`
        assert not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert not cover._delay_task.cancelled(), (
        "our own cancellation must not propagate into delay_task and kill"
        " the pending relay de-energisation (MINOR 5)"
    )
    settle.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_start_recalibrated_leg_absorbs_delay_task_cancellation(make_cover):
    """The complementary case: cancelling only the run-on task directly
    (_cancel_delay_task, as async_stop_cover/_abandon_active_lifecycle do)
    while leg B's own task is left running -- with nothing superseding the
    movement itself -- must not kill leg B's task. Leg B still proceeds past
    the run-on wait to the settle gap; the epoch re-checks (both the one
    immediately after the run-on wait and _settle_before_reversing's own) are
    what would actually stop it on a genuine supersede -- see
    test_stop_during_the_runon_wait_prevents_leg_b and
    test_stop_inside_the_settle_gap_aborts_leg_b."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(100)
    cover._pending_recalibrated_target = 25
    cover._pending_recalibrated_axis = "travel"
    cover._recalibration_epoch = cover._movement_epoch
    cover._delay_task = asyncio.ensure_future(asyncio.sleep(10))
    settle = AsyncMock()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=settle),
    ):
        task = asyncio.ensure_future(cover._maybe_start_recalibrated_leg())
        await asyncio.sleep(0)  # let it reach `await delay_task`
        assert not task.done()
        cover._delay_task.cancel()
        await task  # must not raise

    settle.assert_awaited_once()


# ===================================================================
# Task 3 fix round 2 — Critical 1 / Important 2
# ===================================================================


@pytest.mark.asyncio
async def test_stop_during_the_runon_wait_prevents_leg_b(make_cover):
    """CRITICAL 1: the epoch is captured once, before the run-on await, and
    was never re-checked afterward. _settle_before_reversing's own re-check
    does NOT cover this window -- it captures self._movement_epoch on entry
    and compares it to itself after its own sleep, so it only ever catches a
    supersede landing during ITS OWN wait, never one that already landed
    during the run-on wait before settle even started. Reproduces the
    review's Critical 1: a STOP arriving while leg B is parked on the
    endpoint run-on must not be followed by leg B driving off anyway."""
    cover = make_cover(recalibrate_before_position=True, endpoint_runon_time=2.0)
    cover.travel_calc.set_position(75)
    runon_started = asyncio.Event()
    runon_release = asyncio.Event()

    async def fake_runon(_delay):
        runon_started.set()
        await runon_release.wait()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_delayed_stop", side_effect=fake_runon),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_position(25)
        cover.travel_calc.set_position(100)  # leg A arrives

        task = asyncio.ensure_future(cover.auto_stop_if_necessary())
        await asyncio.wait_for(runon_started.wait(), timeout=5)
        assert not task.done(), "leg B must still be parked on the run-on wait"

        await cover.async_stop_cover()  # user presses STOP mid run-on
        runon_release.set()
        await asyncio.wait_for(task, timeout=5)

    assert not cover.travel_calc.is_traveling(), "leg B must not run after a stop"
    assert cover.travel_calc.current_position() == 100, (
        "must stay where the stop left it, not drive off to the old target"
    )


@pytest.mark.asyncio
async def test_new_command_during_the_runon_wait_supersedes(make_cover):
    """CRITICAL 1b, the other supersede path in the same window: a fresh
    set_position landing while leg B is parked on the run-on wait must win --
    the stale leg B, resuming afterward, must not clobber it back to the old
    target."""
    cover = make_cover(recalibrate_before_position=True, endpoint_runon_time=2.0)
    cover.travel_calc.set_position(75)
    runon_started = asyncio.Event()
    runon_release = asyncio.Event()

    async def fake_runon(_delay):
        runon_started.set()
        await runon_release.wait()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_delayed_stop", side_effect=fake_runon),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_position(25)
        cover.travel_calc.set_position(100)  # leg A arrives

        task = asyncio.ensure_future(cover.auto_stop_if_necessary())
        await asyncio.wait_for(runon_started.wait(), timeout=5)
        assert not task.done(), "leg B must still be parked on the run-on wait"

        await cover.set_position(60, recalibrate=False)
        runon_release.set()
        await asyncio.wait_for(task, timeout=5)

    assert cover.travel_calc._travel_to_position == 60, (
        "must keep heading for the fresh target, not be clobbered back to 25"
    )


@pytest.mark.asyncio
async def test_maybe_start_recalibrated_leg_epoch_mismatch_still_clears(make_cover):
    """IMPORTANT 2: the epoch-mismatch branch inside
    _maybe_start_recalibrated_leg must itself clear the three pending fields,
    independent of the upstream clear finding (a) added to
    _clear_multiphase_tilt_state. _supersede_movement bumps the epoch without
    going through _clear_multiphase_tilt_state, so arming directly and
    superseding this way is the one route that still reaches the
    epoch-mismatch branch with a non-None target -- pinning the "clear before
    the epoch check" ordering fix round 1 introduced. Moving the three clears
    to after the epoch check leaves every other test in this file green."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(100)

    cover._arm_recalibrated_leg(25, "travel")
    cover._supersede_movement()
    await cover._maybe_start_recalibrated_leg()

    assert cover._pending_recalibrated_target is None
    assert cover._pending_recalibrated_axis is None
    assert cover._recalibration_epoch is None
    assert not cover.travel_calc.is_traveling(), "epoch mismatch must not run leg B"


# ===================================================================
# Fix round 2 — a reversing recalibration drive must stop and settle first
# ===================================================================
#
# _start_recalibration_drive funnels a travel-axis drive through
# _force_full_redrive -> _async_move_to_endpoint, which has no in-motion-
# reversal handling of its own (unlike its tilt counterpart,
# _async_move_tilt_to_endpoint). Both recalibration-drive callers in
# set_position -- leg A of a mid-position move (always drives OPEN) and a
# forced endpoint redrive (drives OPEN or CLOSE) -- can be asked to reverse
# an in-flight movement, and previously did so by issuing the new direction
# command straight at the running motor with no stop and no settle. On
# Toggle (opposite button) hardware an opposite-direction pulse while moving
# IS a stop, not a reversal, so this desynced the tracker from a physically
# halted motor.


@pytest.mark.asyncio
async def test_toggle_opposite_endpoint_redrive_reversal_stops_and_settles(
    make_cover, command_spy
):
    """Requirement 1: Toggle-opposite, opening toward 80, option on,
    set_position(0) must stop and await the settle gap before the close
    drive -- not issue close_cover straight at the still-opening motor.
    Asserted at the command level (the sequence _async_handle_command
    receives), which is where the bug showed: the tracker still moved
    either way, only the missing STOP/settle distinguished the fix from the
    bug (see the coordinator's own relay-level trace)."""
    cover = make_cover(control_mode="toggle_opposite", recalibrate_before_position=True)
    cover.travel_calc.set_position(20)
    cover.travel_calc.start_travel(80)
    cover._last_command = SERVICE_OPEN_COVER
    assert cover.travel_calc.is_opening()

    calls, spy = command_spy(cover)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", side_effect=spy),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.set_position(0)

    assert calls == [SERVICE_STOP_COVER, SERVICE_CLOSE_COVER], (
        f"must stop before reversing to close, in that order: {calls}"
    )
    settle.assert_awaited_once()
    assert cover._pending_recalibrated_target is None, "endpoint target arms no leg"


@pytest.mark.asyncio
async def test_mid_range_leg_a_reversal_stops_and_settles(make_cover, command_spy):
    """Requirement 2: closing toward 20, option on, set_position(50) — leg
    A always drives OPEN, so this reverses the in-flight close. The open
    drive must stop and settle first."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(60)
    cover.travel_calc.start_travel(20)
    cover._last_command = SERVICE_CLOSE_COVER
    assert cover.travel_calc.is_closing()

    calls, spy = command_spy(cover)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", side_effect=spy),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.set_position(50)

    assert calls == [SERVICE_STOP_COVER, SERVICE_OPEN_COVER], (
        f"leg A's open drive must stop and reverse cleanly, in that order: {calls}"
    )
    settle.assert_awaited_once()
    assert cover._pending_recalibrated_target == 50, "leg B must still be armed"


@pytest.mark.asyncio
async def test_same_direction_recalibration_drive_no_spurious_stop(
    make_cover, command_spy
):
    """Requirement 3 (regression guard): already opening, option on,
    set_position(100) drives OPEN again — same direction as what is already
    running, so no reversal is needed and no extra stop/settle must be
    inserted."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(20)
    cover.travel_calc.start_travel(100)
    cover._last_command = SERVICE_OPEN_COVER
    assert cover.travel_calc.is_opening()

    calls, spy = command_spy(cover)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", side_effect=spy),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.set_position(100)

    assert SERVICE_STOP_COVER not in calls, f"no spurious stop: {calls}"
    settle.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_during_reversal_settle_aborts_recalibration_drive(make_cover):
    """Requirement 4: a stop (or any new command) landing inside the
    pre-drive settle gap must win. The recalibration drive must not proceed
    once the settle finishes, and set_position must not fall back to a
    plain move either -- something else has already claimed the movement."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(20)
    cover.travel_calc.start_travel(80)
    cover._last_command = SERVICE_OPEN_COVER

    async def stop_during_settle():
        cover._supersede_movement()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", side_effect=stop_during_settle),
    ):
        await cover.set_position(0)

    assert not cover.travel_calc.is_traveling(), (
        "no recalibration drive, and no fallback plain move, after a stop mid-settle"
    )
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target",
    [0, 10],
    ids=["endpoint", "mid-range"],
)
async def test_option_off_reversal_unaffected_by_recalibration_guard(
    make_cover, command_spy, target
):
    """Requirement 5: with the option off, an ordinary reversing
    set_position still goes through the pre-existing plain-path
    stop-then-settle, exactly as before fix round 2 -- the new
    pre-recalibration-drive guard never fires when the option is off.
    Opening toward 80 from a believed 20, both an endpoint target (0) and a
    mid-range target below the current position (10) reverse the in-flight
    open into a close."""
    cover = make_cover(control_mode="toggle_opposite")
    cover.travel_calc.set_position(20)
    cover.travel_calc.start_travel(80)
    cover._last_command = SERVICE_OPEN_COVER

    calls, spy = command_spy(cover)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", side_effect=spy),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.set_position(target)

    assert calls == [SERVICE_STOP_COVER, SERVICE_CLOSE_COVER], (
        f"option off: unchanged stop-then-reverse sequence: {calls}"
    )
    settle.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_known_position_stale_last_command_no_spurious_stop(
    make_cover, command_spy
):
    """Final-review fix (item 1): ``is_direction_change`` alone is not enough
    to gate the pre-drive stop in
    ``_stop_and_settle_before_recalibration_drive`` -- it must also require
    something to actually be moving. ``set_known_position`` -> ``_handle_stop``
    halts ``travel_calc`` but never touches ``_last_command``, so a stale
    command can outlive the movement it described. A following
    ``set_position`` then sees a "direction change" against nothing moving;
    without the "is anything moving" conjunct this pulses an extra stop at an
    idle motor -- on toggle-opposite hardware a movement command that runs
    the cover to its endpoint (#153-class hazard)."""
    cover = make_cover(control_mode="toggle_opposite", recalibrate_before_position=True)
    cover.travel_calc.set_position(80)
    cover.travel_calc.start_travel(20)
    cover._last_command = SERVICE_CLOSE_COVER

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_known_position(position=80)

    assert not cover.travel_calc.is_traveling(), (
        "must be halted by the known-position reset"
    )
    assert cover._last_command == SERVICE_CLOSE_COVER, (
        "set_known_position/_handle_stop must not touch _last_command -- that's the setup"
    )

    calls, spy = command_spy(cover)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", side_effect=spy),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.set_position(50)

    assert calls == [SERVICE_OPEN_COVER], (
        f"no stop pulse at an idle motor, just leg A's open drive: {calls}"
    )
    settle.assert_not_awaited()


# ===================================================================
# Fix round 3 — same-direction re-pulse on toggle hardware (CRITICAL)
#
# _stop_and_settle_before_recalibration_drive handles the *reversing* case.
# The mirror image — the recalibration drive heading the SAME way as the
# movement already under way — had no handling at all: the drive reached
# _async_move_to_endpoint and re-issued the direction command. On toggle
# (same button) hardware a second rising edge on the relay that is currently
# driving STOPS the motor, while _force_full_redrive's seed makes the tracker
# animate a fabricated full travel over a motor that is standing still.
# The plain (non-recalibrated) path has guarded against exactly this since
# forever via `already_moving_same_dir`; these pin the same guard on the
# recalibration path.
# ===================================================================


def _relay_ops(cover):
    """The (service, entity_id) pairs actually sent to the hardware."""
    return [
        (c.args[1], c.args[2]["entity_id"])
        for c in cover.hass.services.async_call.call_args_list
    ]


@pytest.mark.asyncio
async def test_toggle_same_direction_leg_a_does_not_repulse(make_cover):
    """CRITICAL: toggle, really opening from 20%, set_position(50).

    Leg A drives OPEN — the direction already running. Re-pulsing the open
    relay is a same-button toggle: the MOTOR STOPS, while the tracker (seeded
    to 0 by _force_full_redrive) animates a fabricated 0→100 over the full
    travel time. Leg B then runs from a fabricated 100 against a real 20% and
    drives the shutter into the bottom — the obstruction-crush outcome this
    whole feature exists to prevent.
    """
    cover = make_cover(control_mode="toggle", recalibrate_before_position=True)
    cover.travel_calc.set_position(20)
    cover.travel_calc.start_travel(80)
    cover._last_command = SERVICE_OPEN_COVER
    assert cover.travel_calc.is_opening()
    cover.hass.services.async_call.reset_mock()

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(50)

    assert _relay_ops(cover) == [], (
        "the motor is already driving toward the datum and will stall there:"
        f" leg A must not touch a relay at all, got {_relay_ops(cover)}"
    )
    assert cover.travel_calc.is_opening(), "the tracker must still animate leg A"
    assert cover.travel_calc._travel_to_position == 100
    assert cover.travel_calc._last_known_position == 0, (
        "still modelled as a full-travel open from the opposite endpoint"
    )
    assert cover._pending_recalibrated_target == 50, "leg B must still be armed"


@pytest.mark.asyncio
async def test_toggle_same_direction_forced_endpoint_does_not_repulse(make_cover):
    """CRITICAL, FORCED_ENDPOINT shape: toggle, really opening, set_position(100).

    Same hazard by the other branch of set_position — a forced endpoint
    re-drive to 100 while already opening.
    """
    cover = make_cover(control_mode="toggle", recalibrate_before_position=True)
    cover.travel_calc.set_position(20)
    cover.travel_calc.start_travel(80)
    cover._last_command = SERVICE_OPEN_COVER
    cover.hass.services.async_call.reset_mock()

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(100)

    assert _relay_ops(cover) == [], (
        f"no second rising edge on the open relay: {_relay_ops(cover)}"
    )
    assert cover.travel_calc.is_opening()
    assert cover.travel_calc._travel_to_position == 100
    assert cover.travel_calc._last_known_position == 0
    assert cover._pending_recalibrated_target is None, "endpoint target arms no leg"


@pytest.mark.asyncio
async def test_toggle_same_direction_forced_close_does_not_repulse(make_cover):
    """CRITICAL, closing mirror: toggle, really closing, set_position(0)."""
    cover = make_cover(control_mode="toggle", recalibrate_before_position=True)
    cover.travel_calc.set_position(80)
    cover.travel_calc.start_travel(20)
    cover._last_command = SERVICE_CLOSE_COVER
    assert cover.travel_calc.is_closing()
    cover.hass.services.async_call.reset_mock()

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(0)

    assert _relay_ops(cover) == [], (
        f"no second rising edge on the close relay: {_relay_ops(cover)}"
    )
    assert cover.travel_calc.is_closing()
    assert cover.travel_calc._travel_to_position == 0
    assert cover.travel_calc._last_known_position == 100


@pytest.mark.asyncio
async def test_toggle_genuine_reversal_still_stops_and_settles(make_cover, command_spy):
    """Regression guard for the suppression: it must key off *direction*, not
    simply "something is moving". A genuine reversal still gets the stop and
    the settle gap, and the new direction still gets its command."""
    cover = make_cover(control_mode="toggle", recalibrate_before_position=True)
    cover.travel_calc.set_position(20)
    cover.travel_calc.start_travel(80)
    cover._last_command = SERVICE_OPEN_COVER

    calls, spy = command_spy(cover)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", side_effect=spy),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.set_position(0)

    assert calls == [SERVICE_STOP_COVER, SERVICE_CLOSE_COVER], (
        f"a reversal must still stop, settle, then drive the other way: {calls}"
    )
    settle.assert_awaited_once()


@pytest.mark.asyncio
async def test_switch_same_direction_leg_a_leaves_the_latch_alone(make_cover):
    """Switch mode takes the same suppression, and it is a no-op there.

    A latching relay that is already driving open stays driving open whether
    we re-send the command or not — the only difference is relay churn — so
    the guard is applied uniformly rather than per-mode, exactly as the plain
    path's `already_moving_same_dir` is. What must not change is that the
    latch keeps driving and the recalibration leg still runs.
    """
    cover = make_cover(recalibrate_before_position=True)  # switch is the default
    cover.travel_calc.set_position(20)
    cover.travel_calc.start_travel(80)
    cover._last_command = SERVICE_OPEN_COVER
    # Reflect reality: in switch mode the open relay is latched ON for the
    # whole travel, so a re-send would be writing to an already-on relay.
    open_state = MagicMock()
    open_state.state = "on"
    cover.hass.states.get = lambda eid: open_state if eid == "switch.open" else None
    cover.hass.services.async_call.reset_mock()

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(50)

    ops = _relay_ops(cover)
    assert ("turn_off", "switch.open") not in ops, "must never break the latch"
    assert ops == [], f"nothing to write to an already-latched relay: {ops}"
    assert cover.travel_calc.is_opening(), "the tracker must still animate leg A"
    assert cover.travel_calc._travel_to_position == 100
    assert cover._pending_recalibrated_target == 50, "leg B must still be armed"
