"""Fully open before moving to a position (issue #179).

A cover with no position feedback that an unseen remote can also move drifts:
Home Assistant keeps tracking from its last known position while the real cover
is somewhere else. With recalibrate_before_position on, a set_position command
first drives the cover fully open — a true datum, since the motor stalls at its
limit — and only then moves to the requested position.
"""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER


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
    """An endpoint target IS the recalibration — no pointless extra leg."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(40)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(100)

    assert cover.travel_calc.is_opening()
    assert cover.travel_calc._travel_to_position == 100
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_target_0_has_no_open_leg(make_cover):
    """Going fully closed must not drive fully open first."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(40)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(0)

    assert cover.travel_calc.is_closing(), "must close, not open first"
    assert cover.travel_calc._travel_to_position == 0
    assert cover._pending_recalibrated_target is None


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
    """MINOR 4: a superseded leg B must not linger forever. Before the fix,
    the epoch-mismatch early return in _maybe_start_recalibrated_leg left
    _pending_recalibrated_target (and its axis/epoch siblings) set --
    _clear_multiphase_tilt_state does not know about these fields, so
    nothing else would ever clear them either."""
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
        assert cover._pending_recalibrated_target == 25, (
            "still armed and stale immediately after the supersede"
        )

        # A stray/leftover completion call must not leave it armed forever.
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
