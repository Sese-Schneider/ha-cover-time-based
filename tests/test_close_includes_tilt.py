"""Tests for close_includes_tilt option and the related changes to
async_close_cover (resync-skip when settled at 0).

These tests use mocked _async_move_to_endpoint and _async_move_tilt_to_endpoint
to assert orchestration rather than running real motor timing.
"""

import pytest
from unittest.mock import AsyncMock, patch

from custom_components.cover_time_based.travel_calculator import TravelStatus


class TestSkipResyncAtZero:
    """async_close_cover should not call _async_move_to_endpoint(0) when
    travel is already settled at 0. This avoids the resync motor pulse
    HA-convention violation."""

    @pytest.mark.asyncio
    async def test_skips_endpoint_call_when_settled_at_zero(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)
        # set_position() leaves direction at STOPPED, which is what we want
        assert cover.travel_calc.travel_direction == TravelStatus.STOPPED

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_move,
        ):
            await cover.async_close_cover()

        mock_move.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_calls_endpoint_when_not_at_zero(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_move,
        ):
            await cover.async_close_cover()

        mock_move.assert_awaited_once_with(target=0)

    @pytest.mark.asyncio
    async def test_calls_endpoint_when_at_zero_but_still_moving(self, make_cover):
        """In the final 1% of a close, current_position() can read 0 while
        the motor is still finishing. travel_direction is the clean signal."""
        cover = make_cover()
        cover.travel_calc.set_position(100)
        cover.travel_calc.start_travel_down()
        # Force the calculator into a state where current is 0 but direction
        # is still DOWN (mid-finish).
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel_down()
        assert cover.travel_calc.travel_direction == TravelStatus.DIRECTION_DOWN

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_move,
        ):
            await cover.async_close_cover()

        mock_move.assert_awaited_once_with(target=0)


class TestTrailingTiltClose:
    """When close_includes_tilt=True, async_close_cover follows the travel
    move with a tilt-close if tilt is not already at 0."""

    @pytest.mark.asyncio
    async def test_sequential_close_option_true_from_fully_open(self, make_cover):
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_close",
            close_includes_tilt=True,
        )
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_travel,
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_travel.assert_awaited_once_with(target=0)
        # Travel is in flight: restore target is set for the auto-updater to chain.
        assert cover._tilt_restore_target == 0

    @pytest.mark.asyncio
    async def test_sequential_close_option_true_from_articulated(self, make_cover):
        """Settled at (0, 100): travel skipped, tilt-close fires."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_close",
            close_includes_tilt=True,
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_travel,
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_travel.assert_not_awaited()
        mock_tilt.assert_awaited_once_with(target=0)

    @pytest.mark.asyncio
    async def test_sequential_close_option_false_from_fully_open(self, make_cover):
        """Option off: travel only, no tilt-close."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_close",
            close_includes_tilt=False,
        )
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_travel,
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_travel.assert_awaited_once_with(target=0)
        mock_tilt.assert_not_awaited()
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_sequential_close_option_false_from_articulated(self, make_cover):
        """Option off + already at 0 + tilt open: total no-op."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_close",
            close_includes_tilt=False,
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_travel,
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_travel.assert_not_awaited()
        mock_tilt.assert_not_awaited()
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_no_trailing_tilt_when_tilt_already_zero(self, make_cover):
        """Even with option=true, skip the tilt-close when tilt is already 0."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_close",
            close_includes_tilt=True,
        )
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(0)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ),
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_tilt.assert_not_awaited()
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_no_trailing_tilt_when_no_tilt_support(self, make_cover):
        """No tilt support → no trailing tilt-close, period."""
        cover = make_cover(close_includes_tilt=True)  # no tilt times
        cover.travel_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ),
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        assert cover._tilt_restore_target is None
        mock_tilt.assert_not_awaited()


class TestDualMotor:
    """The async_close_cover implementation is strategy-agnostic. Confirm
    dual_motor behaves identically to sequential_close for the trailing
    tilt-close decision (via _tilt_restore_target)."""

    @pytest.mark.asyncio
    async def test_dual_motor_option_true_closes_tilt_after_travel(self, make_cover):
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            safe_tilt_position=100,
            close_includes_tilt=True,
        )
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)  # parked at safe

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_travel,
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_travel.assert_awaited_once_with(target=0)
        mock_tilt.assert_not_awaited()
        assert cover._tilt_restore_target == 0

    @pytest.mark.asyncio
    async def test_dual_motor_option_false_leaves_tilt_at_safe(self, make_cover):
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            safe_tilt_position=100,
            close_includes_tilt=False,
        )
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_travel,
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_travel.assert_awaited_once_with(target=0)
        mock_tilt.assert_not_awaited()
        assert cover._tilt_restore_target is None
