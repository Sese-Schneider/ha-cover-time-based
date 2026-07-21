"""Tests for close_includes_tilt option and the related changes to
async_close_cover (resync-skip when settled at 0).

Most tests here mock _async_move_to_endpoint and _async_move_tilt_to_endpoint
to assert orchestration rather than running real motor timing. The dual-motor
tests that exercise the tilt pre-step planner (TestDualMotor) run for real —
mocking _async_move_to_endpoint would bypass _plan_tilt_for_travel entirely
and hide bugs in how it honors close_includes_tilt.
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
        # Direct tilt call is not made; the auto-updater chain mechanism is used.
        mock_tilt.assert_not_awaited()
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
            patch.object(cover, "_async_move_to_endpoint", new_callable=AsyncMock),
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
            patch.object(cover, "_async_move_to_endpoint", new_callable=AsyncMock),
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
        """Tilt already at safe: real planner runs (no mocked
        _async_move_to_endpoint) — travel proceeds directly, no tilt motor
        pre-step is needed (nothing to move), and no trailing restore is
        scheduled since close_includes_tilt is off."""
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
        cover.tilt_calc.set_position(100)  # already at safe

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Travel started for real (no pre-step needed: tilt is already safe).
        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._travel_to_position == 0
        # Tilt motor never engaged.
        assert not cover.tilt_calc.is_traveling()
        assert cover.tilt_calc.current_position() == 100
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_option_false_close_from_unsafe_tilt_restores_to_safe(
        self, make_cover
    ):
        """The buggy case: tilt is NOT at safe when the close starts, so the
        dual-motor pre-step drives it to safe first. With close_includes_tilt
        off, the close must travel only — the slats stay at the safe position
        the pre-step put them at, not get driven on to 0."""
        cover = make_cover(
            travel_time_close=5.0,
            travel_time_open=5.0,
            tilt_time_close=1.0,
            tilt_time_open=1.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            safe_tilt_position=100,
            close_includes_tilt=False,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(30)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        assert cover._pending_travel_target == 0  # tilt-to-safe pre-step running
        assert cover._tilt_restore_target == 100  # stays at safe, NOT driven to 0


class TestUnaffectedStrategies:
    """inline and sequential_open already land tilt at 0 after close_cover,
    so the trailing tilt-close should be a no-op regardless of option value.
    These tests pin that behavior."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("option", [True, False])
    async def test_inline_no_trailing_tilt_close(self, make_cover, option):
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="inline",
            close_includes_tilt=option,
        )
        cover.travel_calc.set_position(100)
        # Simulate the post-_async_move_to_endpoint(0) state for inline:
        # tilt ends at 0 because plan_move_position pre-steps TiltTo(0).
        # Since we mock _async_move_to_endpoint, we set tilt manually.
        cover.tilt_calc.set_position(0)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "_async_move_to_endpoint", new_callable=AsyncMock),
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_tilt.assert_not_awaited()
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("option", [True, False])
    async def test_sequential_open_no_trailing_tilt_close(self, make_cover, option):
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_open",
            close_includes_tilt=option,
        )
        cover.travel_calc.set_position(100)
        # For sequential_open, implicit_tilt_during_travel=0, so tilt sits at 0.
        cover.tilt_calc.set_position(0)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "_async_move_to_endpoint", new_callable=AsyncMock),
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_tilt.assert_not_awaited()
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_inline_with_endpoint_runon_does_not_set_restore_target(
        self, make_cover
    ):
        """Regression: inline cover with endpoint_runon_time must not have
        close_cover set _tilt_restore_target, because that would short-circuit
        the endpoint runon block in auto_stop_if_necessary. Inline already
        drives tilt to 0 as a pre-step during close travel, so the trailing
        restore would be a redundant no-op that disables runon."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="inline",
            endpoint_runon_time=2.0,
            close_includes_tilt=True,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)  # mid-tilt — would match the guard

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "_async_move_to_endpoint", new_callable=AsyncMock),
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_tilt.assert_not_awaited()
        assert cover._tilt_restore_target is None


class TestStopOnInMotionClick:
    """Clicking close_cover or open_cover while the cover is moving (in any
    direction) should stop the cover and return — not re-issue the command
    and not chain a direction-change reversal. Reversing requires a second
    click, or use set_cover_position which keeps its existing
    stop-then-reverse behavior."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "start_pos,start_dir,method",
        [
            (100, "down", "async_close_cover"),
            (0, "up", "async_close_cover"),
            (0, "up", "async_open_cover"),
            (100, "down", "async_open_cover"),
        ],
    )
    async def test_in_motion_click_stops(
        self, make_cover, start_pos, start_dir, method
    ):
        cover = make_cover()
        cover.travel_calc.set_position(start_pos)
        if start_dir == "down":
            cover.travel_calc.start_travel_down()
        else:
            cover.travel_calc.start_travel_up()

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "async_stop_cover", new_callable=AsyncMock
            ) as mock_stop,
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_move,
        ):
            await getattr(cover, method)()

        mock_stop.assert_awaited_once()
        mock_move.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "start_pos,method,expected_target",
        [
            (100, "async_close_cover", 0),
            (0, "async_open_cover", 100),
        ],
    )
    async def test_idle_click_proceeds_normally(
        self, make_cover, start_pos, method, expected_target
    ):
        """Sanity: when idle, close_cover/open_cover proceeds normally."""
        cover = make_cover()
        cover.travel_calc.set_position(start_pos)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "async_stop_cover", new_callable=AsyncMock
            ) as mock_stop,
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_move,
        ):
            await getattr(cover, method)()

        mock_stop.assert_not_awaited()
        mock_move.assert_awaited_once_with(target=expected_target)
