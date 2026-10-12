"""Tests for close_includes_tilt option, which applies to async_close_cover
and to set_cover_position(0), and the related changes to async_close_cover
(resync-skip when settled at 0).

Most tests here mock _async_move_to_endpoint and _async_move_tilt_to_endpoint
to assert orchestration rather than running real motor timing. The dual-motor
tests that exercise the tilt pre-step planner (TestDualMotor) run for real —
mocking _async_move_to_endpoint would bypass _plan_tilt_for_travel entirely
and hide bugs in how it honors close_includes_tilt.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import State

from custom_components.cover_time_based.travel_calculator import TravelStatus
from tests.helpers import stub_switches


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


class TestCloseButtonWhileMoving:
    """Whether the close button's slat step drives the slats now or after
    the travel depends on what is still moving when the press lands."""

    @pytest.mark.asyncio
    async def test_reverses_an_opening_tilt_motor_at_once(self, make_cover):
        """Travel settled at 0 and the dual-motor slats opening: the press
        turns the tilt motor round now rather than after it finishes opening."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            safe_tilt_position=100,
            close_includes_tilt=True,
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)

        with (
            patch(
                "custom_components.cover_time_based.travel_calculator.time"
            ) as mock_time,
            patch.object(cover, "async_write_ha_state"),
        ):
            mock_time.monotonic.return_value = 1000.0
            await cover.async_open_cover_tilt()
            mock_time.monotonic.return_value += 2  # slats part-way open
            cover.hass.services.async_call.reset_mock()
            await cover.async_close_cover()

            sent = [
                (c.args[1], c.args[2]["entity_id"])
                for c in cover.hass.services.async_call.call_args_list
            ]
            assert ("turn_on", "switch.tilt_close") in sent, sent
            assert cover.tilt_calc.is_closing()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("travel", [0, 50])
    async def test_press_that_stops_a_parked_open_does_not_move(
        self, make_cover, travel
    ):
        """A close pressed while an open waits out its startup delay only
        stops it: nothing is switched on (a second press closes)."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_close",
            close_includes_tilt=True,
            travel_startup_delay=30,
        )
        cover.travel_calc.set_position(travel)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            cover.hass.services.async_call.reset_mock()
            await cover.async_close_cover()

        turned_on = [
            c.args[2]["entity_id"]
            for c in cover.hass.services.async_call.call_args_list
            if c.args[1] == "turn_on"
        ]
        assert turned_on == []
        assert not cover.travel_calc.is_traveling()
        assert not cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_redrive_not_started_still_closes_slats_after_pending_close(
        self, make_cover
    ):
        """force_endpoint_redrive at a believed 0 that does not start because
        a close is already waiting out its startup delay: the slat close is
        chained after that pending close, which must survive the press."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_close",
            close_includes_tilt=True,
            force_endpoint_redrive=True,
            cover_entity_id="cover.inner",
            travel_startup_delay=30,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_set_cover_position(position=0)
            pending_close = cover._startup_delay_task
            cover._last_self_command_time = None
            await cover._handle_external_attribute_change(
                SimpleNamespace(
                    data={
                        "entity_id": "cover.inner",
                        "new_state": State(
                            "cover.inner", "closed", {"current_position": 0}
                        ),
                    }
                )
            )
            await cover.async_close_cover()
            await asyncio.sleep(0)

        assert cover._startup_delay_task is pending_close
        assert not pending_close.done()
        assert cover._tilt_restore_target == 0
        pending_close.cancel()


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


def _sequential_close_cover(make_cover, close_includes_tilt=True, **options):
    return make_cover(
        tilt_time_close=5.0,
        tilt_time_open=5.0,
        tilt_mode="sequential_close",
        close_includes_tilt=close_includes_tilt,
        **options,
    )


class TestSetPositionZero:
    """With close_includes_tilt on, set_cover_position(0) closes the slats too,
    like the close button — HomeKit, voice assistants and the slider send 0%,
    not close (#307)."""

    @pytest.mark.asyncio
    async def test_from_open_schedules_tilt_close_after_travel(self, make_cover):
        cover = _sequential_close_cover(make_cover)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_set_cover_position(position=0)

        assert cover.travel_calc.is_closing()
        assert cover._tilt_restore_target == 0

    @pytest.mark.asyncio
    async def test_settled_at_zero_closes_tilt_directly(self, make_cover):
        cover = _sequential_close_cover(make_cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_set_cover_position(position=0)

        mock_tilt.assert_awaited_once_with(target=0)

    @pytest.mark.asyncio
    async def test_option_off_leaves_tilt(self, make_cover):
        cover = _sequential_close_cover(make_cover, close_includes_tilt=False)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_set_cover_position(position=0)

        assert cover.travel_calc.is_closing()
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_non_zero_target_leaves_tilt(self, make_cover):
        cover = _sequential_close_cover(make_cover)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_set_cover_position(position=10)

        mock_tilt.assert_not_awaited()
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_slats_start_closing_when_travel_reaches_zero(self, make_cover):
        """End to end through the auto-updater: once the 0% travel arrives,
        the chained tilt close actually starts."""
        cover = _sequential_close_cover(make_cover)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_set_cover_position(position=0)
            # Arrive at 0 while still marked as travelling there.
            cover.travel_calc.set_position(0)
            cover.travel_calc.start_travel(0)
            await cover.auto_stop_if_necessary()

        assert cover.tilt_calc.is_traveling(), "the slats must start closing"
        assert cover.tilt_calc.is_closing()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("option", "restore_target"), [(True, 0), (False, None)])
    async def test_dual_motor(self, make_cover, option, restore_target):
        """Slats parked at safe: travel starts at once, and the slats are
        closed after it only with the option on — off, they stay at safe, as
        after the close button."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            safe_tilt_position=100,
            close_includes_tilt=option,
        )
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_set_cover_position(position=0)

        assert cover.travel_calc.is_closing()
        assert not cover.tilt_calc.is_traveling()
        assert cover.tilt_calc.current_position() == 100
        assert cover._tilt_restore_target == restore_target

    @pytest.mark.asyncio
    async def test_inline_with_endpoint_runon_does_not_set_restore_target(
        self, make_cover
    ):
        """Inline closes the slats on the way down, and a restore target would
        cut short the endpoint run-on — see the close-button test of the same
        name."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="inline",
            endpoint_runon_time=2.0,
            close_includes_tilt=True,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_set_cover_position(position=0)

        assert cover.travel_calc.is_closing()
        assert cover.tilt_calc.is_closing()
        mock_tilt.assert_not_awaited()
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_zero_just_after_an_open_leaves_adds_no_slat_close(self, make_cover):
        """An open that has only just left 0 still reads 0 on its first tick.
        A 0% then is ignored (the open carries on) and must not chain a slat
        close to the open, which would drive the close relay at the top."""
        cover = _sequential_close_cover(make_cover)
        stub_switches(cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(100)

        with (
            patch(
                "custom_components.cover_time_based.travel_calculator.time"
            ) as mock_time,
            patch.object(cover, "async_write_ha_state"),
        ):
            mock_time.monotonic.return_value = 1000.0
            await cover.async_open_cover()
            mock_time.monotonic.return_value += 0.05
            assert cover.travel_calc.current_position() == 0
            await cover.async_set_cover_position(position=0)
            assert cover.travel_calc.is_opening()
            assert cover._tilt_restore_target is None
            cover.hass.services.async_call.reset_mock()
            with patch.object(cover, "_direction_change_delay", new_callable=AsyncMock):
                for _ in range(6):
                    mock_time.monotonic.return_value += 100
                    if cover.position_reached():
                        await cover.auto_stop_if_necessary()
                    await asyncio.sleep(0)

            sent = [
                (c.args[1], c.args[2]["entity_id"])
                for c in cover.hass.services.async_call.call_args_list
            ]
            assert ("turn_on", "switch.close") not in sent, sent
            assert cover.travel_calc.current_position() == 100

    @pytest.mark.asyncio
    async def test_superseded_zero_does_not_close_tilt_after_newer_open(
        self, make_cover
    ):
        """A 0% request superseded while it waits out the reversal pause must
        not attach its slat close to the newer move that replaced it."""
        cover = _sequential_close_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def held_reversal_pause():
            entered.set()
            await release.wait()

        with (
            patch(
                "custom_components.cover_time_based.travel_calculator.time"
            ) as mock_time,
            patch.object(cover, "async_write_ha_state"),
        ):
            mock_time.monotonic.return_value = 1000.0
            await cover.async_set_cover_position(position=100)
            with patch.object(cover, "_direction_change_delay", held_reversal_pause):
                closing = asyncio.create_task(
                    cover.async_set_cover_position(position=0)
                )
                await entered.wait()
                await cover.async_set_cover_position(position=100)
                release.set()
                await closing
            cover.hass.services.async_call.reset_mock()
            for _ in range(5):
                mock_time.monotonic.return_value += 100
                if cover.position_reached():
                    await cover.auto_stop_if_necessary()

        sent = [
            (c.args[1], c.args[2]["entity_id"])
            for c in cover.hass.services.async_call.call_args_list
        ]
        assert ("turn_on", "switch.close") not in sent, sent
        assert cover._tilt_restore_target is None
        assert (
            cover.travel_calc.current_position(),
            cover.tilt_calc.current_position(),
        ) == (100, 100)


def _parked_close_cover(make_cover, kind):
    """A sequential_close cover whose next start parks — on its startup delay
    or on the relay's feedback — until the returned event is set."""
    if kind == "startup":
        cover = _sequential_close_cover(
            make_cover, travel_startup_delay=30, tilt_startup_delay=30
        )
        waiter = "_await_startup_delay"
    else:
        cover = _sequential_close_cover(make_cover, wait_for_relay_feedback=True)
        waiter = "_await_relay_confirmation"
    stub_switches(cover)
    release = asyncio.Event()

    async def held(*_args):
        await release.wait()

    return cover, release, patch.object(cover, waiter, held)


async def _run_to_rest(cover, mock_time, release):
    release.set()
    for _ in range(5):
        await asyncio.sleep(0)
    with patch.object(cover, "_direction_change_delay", new_callable=AsyncMock):
        for _ in range(6):
            mock_time.monotonic.return_value += 100
            if cover.position_reached():
                await cover.auto_stop_if_necessary()
            await asyncio.sleep(0)


class TestRepeatedZeroWhileCloseParked:
    """HomeKit and voice assistants may repeat 0% while the first close still
    waits to start. The repeat is refused (the parked close owns the motor)
    but must not drop the slat close chained to it."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["startup", "feedback"])
    @pytest.mark.parametrize("first", ["close_button", "zero"])
    async def test_repeat_keeps_slat_close(self, make_cover, kind, first):
        cover, release, hold = _parked_close_cover(make_cover, kind)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with (
            patch(
                "custom_components.cover_time_based.travel_calculator.time"
            ) as mock_time,
            patch.object(cover, "async_write_ha_state"),
            hold,
        ):
            mock_time.monotonic.return_value = 1000.0
            if first == "close_button":
                await cover.async_close_cover()
            else:
                await cover.async_set_cover_position(position=0)
            await asyncio.sleep(0)
            parked = cover._startup_delay_task
            assert parked is not None and not parked.done()
            await cover.async_set_cover_position(position=0)
            assert cover._startup_delay_task is parked
            assert cover._tilt_restore_target == 0
            await _run_to_rest(cover, mock_time, release)

            assert (
                cover.travel_calc.current_position(),
                cover.tilt_calc.current_position(),
            ) == (0, 0)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["startup", "feedback"])
    async def test_zero_while_close_to_30_parked_adds_no_slat_close(
        self, make_cover, kind
    ):
        """The refused 0% does not own the parked 30% close, so no slat close
        may be chained to it."""
        cover, release, hold = _parked_close_cover(make_cover, kind)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with (
            patch(
                "custom_components.cover_time_based.travel_calculator.time"
            ) as mock_time,
            patch.object(cover, "async_write_ha_state"),
            hold,
        ):
            mock_time.monotonic.return_value = 1000.0
            await cover.async_set_cover_position(position=30)
            await asyncio.sleep(0)
            parked = cover._startup_delay_task
            assert parked is not None and not parked.done()
            await cover.async_set_cover_position(position=0)
            assert cover._tilt_restore_target is None
            await _run_to_rest(cover, mock_time, release)

            assert (
                cover.travel_calc.current_position(),
                cover.tilt_calc.current_position(),
            ) == (30, 100)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["startup", "feedback"])
    async def test_zero_at_zero_while_open_parked_adds_no_slat_close(
        self, make_cover, kind
    ):
        """Already at 0 with an open waiting to start: the 0% is a no-op for
        travel, but the parked open is not its move, so no slat close may be
        chained to it (it would energise the close relay at the top)."""
        cover, release, hold = _parked_close_cover(make_cover, kind)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(100)

        with (
            patch(
                "custom_components.cover_time_based.travel_calculator.time"
            ) as mock_time,
            patch.object(cover, "async_write_ha_state"),
            hold,
        ):
            mock_time.monotonic.return_value = 1000.0
            await cover.async_open_cover()
            await asyncio.sleep(0)
            parked = cover._startup_delay_task
            assert parked is not None and not parked.done()
            await cover.async_set_cover_position(position=0)
            assert cover._tilt_restore_target is None
            cover.hass.services.async_call.reset_mock()
            await _run_to_rest(cover, mock_time, release)

            sent = [
                (c.args[1], c.args[2]["entity_id"])
                for c in cover.hass.services.async_call.call_args_list
            ]
            assert ("turn_on", "switch.close") not in sent, sent

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["startup", "feedback"])
    async def test_repeat_after_zero_replaced_a_parked_open(self, make_cover, kind):
        """A 0% that cancels a waiting open parks its own close; the cancelled
        open's clean-up must not forget that close's target, or a repeated 0%
        drops the slat close."""
        cover, release, hold = _parked_close_cover(make_cover, kind)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with (
            patch(
                "custom_components.cover_time_based.travel_calculator.time"
            ) as mock_time,
            patch.object(cover, "async_write_ha_state"),
            hold,
        ):
            mock_time.monotonic.return_value = 1000.0
            await cover.async_open_cover()
            await asyncio.sleep(0)
            parked_open = cover._startup_delay_task
            await cover.async_set_cover_position(position=0)
            await asyncio.sleep(0)
            parked_close = cover._startup_delay_task
            assert parked_open is not None and parked_open.done()
            assert parked_close is not None and not parked_close.done()
            await cover.async_set_cover_position(position=0)
            assert cover._tilt_restore_target == 0
            await _run_to_rest(cover, mock_time, release)

            assert (
                cover.travel_calc.current_position(),
                cover.tilt_calc.current_position(),
            ) == (0, 0)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["startup", "feedback"])
    async def test_zero_at_zero_while_tilt_open_parked_closes_slats(
        self, make_cover, kind
    ):
        """At 0 with a slat-open waiting to start: that start leaves travel at
        0, so the 0% is done and its slat close is chained after it."""
        cover, release, hold = _parked_close_cover(make_cover, kind)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(50)

        with (
            patch(
                "custom_components.cover_time_based.travel_calculator.time"
            ) as mock_time,
            patch.object(cover, "async_write_ha_state"),
            hold,
        ):
            mock_time.monotonic.return_value = 1000.0
            await cover.async_open_cover_tilt()
            await asyncio.sleep(0)
            parked = cover._startup_delay_task
            assert parked is not None and not parked.done()
            await cover.async_set_cover_position(position=0)
            assert cover._tilt_restore_target == 0
            await _run_to_rest(cover, mock_time, release)

            assert (
                cover.travel_calc.current_position(),
                cover.tilt_calc.current_position(),
            ) == (0, 0)
