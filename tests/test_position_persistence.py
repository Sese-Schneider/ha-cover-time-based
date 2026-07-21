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

import pytest
from unittest.mock import patch

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
