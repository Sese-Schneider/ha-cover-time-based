"""Unit tests for the position-store persistence contract across control modes.

CoverTimeBased.async_stop_cover (the base) always persists the position it
stops at, via _async_persist_position, because the PositionStore is
authoritative on restore and beats RestoreEntity when both exist (see
cover_base.py). Any override of async_stop_cover that skips that call leaves
a stale position in the Store: on restart the cover snaps back to whatever
was last persisted (e.g. a prior full-open) instead of where it actually
stopped.
"""

import asyncio
from unittest.mock import patch

import pytest

from custom_components.cover_time_based.cover import (
    CONTROL_MODE_SWITCH,
    CONTROL_MODE_TOGGLE,
)


@pytest.mark.asyncio
async def test_toggle_mode_stop_persists_mid_travel_position(
    make_cover, _mock_position_store
):
    """A toggle-mode stop mid-travel must persist the position it stopped at.

    Regression for: open fully (persists 100) -> close -> stop at a mid
    position. Without the persist call, the Store still says 100 and a
    restart restores the wrong (fully-open) position instead of the actual
    stop position.
    """
    cover = make_cover(
        control_mode=CONTROL_MODE_TOGGLE, travel_time_close=5.0, travel_time_open=5.0
    )
    cover.travel_calc.set_position(100)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()
        assert cover.travel_calc.is_traveling()
        await asyncio.sleep(0.1)
        await cover.async_stop_cover()

    assert not cover.travel_calc.is_traveling()
    assert _mock_position_store.async_save.await_count >= 1

    stopped_position = cover.travel_calc.current_position()
    saved_data = _mock_position_store.async_save.await_args.args[1]
    assert saved_data["position"] == int(stopped_position)


@pytest.mark.asyncio
async def test_switch_mode_stop_persists_position_contrast(
    make_cover, _mock_position_store
):
    """Contrast: switch mode already persists on stop (unaffected by the fix)."""
    cover = make_cover(
        control_mode=CONTROL_MODE_SWITCH, travel_time_close=5.0, travel_time_open=5.0
    )
    cover.travel_calc.set_position(100)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()
        await asyncio.sleep(0.1)
        await cover.async_stop_cover()

    assert _mock_position_store.async_save.await_count >= 1


@pytest.mark.asyncio
async def test_tilt_restore_no_op_branch_persists(make_cover, _mock_position_store):
    """The tilt-restore-no-op branch of auto_stop_if_necessary is a terminal
    completion, so it must persist like the other two.

    A dual-motor travel move to an endpoint runs a tilt-to-safe pre-step, then
    travel, then a "restore" phase whose target is the endpoint itself. With
    the default safe_tilt_position (100) an open lands tilt exactly on that
    restore target, so _start_tilt_restore takes its synchronous no-op
    shortcut: no motor is driven and the auto-updater is never re-armed, which
    makes that return the end of the move. Without the persist here the Store
    keeps whatever the last write said while the cover sits at a new position
    — on restart it snaps back. Nothing to do with
    recalibrate_before_position (deliberately off here): this branch is
    reached by any dual-motor cover.
    """
    cover = make_cover(
        tilt_mode="dual_motor",
        tilt_time_open=2.0,
        tilt_time_close=2.0,
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        tilt_stop_switch="switch.tilt_stop",
    )
    cover.travel_calc.set_position(75)
    cover.tilt_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(100)
        # Tilt pre-step reaches the safe position (100).
        cover.tilt_calc.set_position(100)
        await cover.auto_stop_if_necessary()
        # Travel reaches 100. Tilt already sits on the restore target (100).
        cover.travel_calc.set_position(100)
        _mock_position_store.async_save.reset_mock()
        await cover.auto_stop_if_necessary()

    assert not cover._tilt_restore_active, "the restore must be the no-op shortcut"
    assert _mock_position_store.async_save.await_count == 1, (
        "the terminal no-op restore must persist the position it finished at"
    )
