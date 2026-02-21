"""Tests for base class movement orchestration in CoverTimeBased.

These tests exercise the movement coordination logic in cover_base.py:
- _async_move_to_endpoint (close/open travel)
- _async_move_tilt_to_endpoint (close/open tilt)
- set_position / set_tilt_position
- _start_movement (startup delay helper)
- _handle_pre_movement_checks
- _is_movement_too_short
- auto_stop_if_necessary / _delayed_stop
"""

import asyncio

import pytest
from unittest.mock import patch

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER


# ===================================================================
# Travel endpoint movement (async_close_cover / async_open_cover)
# ===================================================================


class TestCloseFromOpen:
    """Closing from fully open should send close command and start travel."""

    @pytest.mark.asyncio
    async def test_close_sends_command_and_starts_travel(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(100)  # fully open

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        assert cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_CLOSE_COVER
        cover.hass.services.async_call.assert_awaited()

    @pytest.mark.asyncio
    async def test_close_when_already_closed_does_nothing(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)  # fully closed

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        assert not cover.travel_calc.is_traveling()
        cover.hass.services.async_call.assert_not_awaited()


class TestOpenFromClosed:
    """Opening from fully closed should send open command and start travel."""

    @pytest.mark.asyncio
    async def test_open_sends_command_and_starts_travel(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)  # fully closed

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()

        assert cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_OPEN_COVER
        cover.hass.services.async_call.assert_awaited()

    @pytest.mark.asyncio
    async def test_open_when_already_open_does_nothing(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(100)  # fully open

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()

        assert not cover.travel_calc.is_traveling()
        cover.hass.services.async_call.assert_not_awaited()


class TestCloseStopsOppositeDirection:
    """Closing while opening should stop first, then close."""

    @pytest.mark.asyncio
    async def test_close_while_opening_stops_then_closes(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Should now be traveling down (closing)
        assert cover._last_command == SERVICE_CLOSE_COVER


class TestOpenStopsOppositeDirection:
    """Opening while closing should stop first, then open."""

    @pytest.mark.asyncio
    async def test_open_while_closing_stops_then_opens(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()

        assert cover._last_command == SERVICE_OPEN_COVER


# ===================================================================
# Travel endpoint with tilt coupling
# ===================================================================


class TestCloseWithTiltCoupling:
    """Closing with tilt support should also move tilt when plan calls for it."""

    @pytest.mark.asyncio
    async def test_close_no_tilt_when_already_flat_sequential(self, make_cover):
        """Sequential: closing with tilt already flat does not move tilt."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        assert cover.travel_calc.is_traveling()
        assert not cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_close_also_starts_tilt_travel_when_tilted(self, make_cover):
        """Sequential: closing with tilt not flat should flatten tilt first."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        assert cover.travel_calc.is_traveling()
        assert cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_open_also_starts_tilt_travel(self, make_cover):
        """Sequential: opening with tilt at 0 should flatten tilt."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()

        assert cover.travel_calc.is_traveling()
        assert cover.tilt_calc.is_traveling()


# ===================================================================
# Tilt endpoint movement (async_close_cover_tilt / async_open_cover_tilt)
# ===================================================================


class TestCloseTilt:
    """Tilt close should move tilt to fully closed."""

    @pytest.mark.asyncio
    async def test_close_tilt_sends_command_and_starts_tilt(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        assert cover.tilt_calc.is_traveling()
        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_close_tilt_when_already_closed_does_nothing(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        assert not cover.tilt_calc.is_traveling()
        cover.hass.services.async_call.assert_not_awaited()


class TestOpenTilt:
    """Tilt open should move tilt to fully open."""

    @pytest.mark.asyncio
    async def test_open_tilt_sends_command_and_starts_tilt(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover_tilt()

        assert cover.tilt_calc.is_traveling()
        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_open_tilt_when_already_open_does_nothing(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover_tilt()

        assert not cover.tilt_calc.is_traveling()
        cover.hass.services.async_call.assert_not_awaited()


class TestTiltStopsTravelFirst:
    """Tilt movement should stop any active travel first, then restart if plan requires it."""

    @pytest.mark.asyncio
    async def test_close_tilt_restarts_travel_when_plan_requires(self, make_cover):
        """Sequential: tilt close from pos 50 needs travel to 0 first."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        # Sequential plan_move_tilt requires travel to 0 before tilting,
        # so travel restarts toward 0 as a coupled target
        assert cover.travel_calc.is_traveling()
        # Tilt should be traveling
        assert cover.tilt_calc.is_traveling()


class TestTiltWithTravelCoupling:
    """Tilt endpoint commands with different tilt modes."""

    @pytest.mark.asyncio
    async def test_close_tilt_sequential_moves_travel_to_closed_first(self, make_cover):
        """Sequential: tilting from pos 50 requires travel to 0 first."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential",
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        assert cover.tilt_calc.is_traveling()
        # Sequential plan requires travel to 0 before tilting
        assert cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_close_tilt_sequential_no_travel_when_already_closed(
        self, make_cover
    ):
        """Sequential: tilting when already at closed position does not move travel."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential",
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        assert cover.tilt_calc.is_traveling()
        assert not cover.travel_calc.is_traveling()


# ===================================================================
# set_position
# ===================================================================


class TestSetPosition:
    """set_position should move cover to the target position."""

    @pytest.mark.asyncio
    async def test_set_position_close_direction(self, make_cover):
        """Setting position below current should close (move down)."""
        cover = make_cover()
        cover.travel_calc.set_position(100)  # currently open

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(50)

        assert cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_set_position_open_direction(self, make_cover):
        """Setting position above current should open (move up)."""
        cover = make_cover()
        cover.travel_calc.set_position(0)  # currently closed

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(50)

        assert cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_set_position_already_at_target(self, make_cover):
        """Setting position equal to current should do nothing."""
        cover = make_cover()
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(50)

        assert not cover.travel_calc.is_traveling()
        cover.hass.services.async_call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_set_position_to_fully_closed(self, make_cover):
        """Setting position to 0 (HA closed)."""
        cover = make_cover()
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(0)

        assert cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_set_position_to_fully_open(self, make_cover):
        """Setting position to 100 (HA open)."""
        cover = make_cover()
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(100)

        assert cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_OPEN_COVER


class TestSetPositionDirectionChange:
    """set_position should handle direction changes properly."""

    @pytest.mark.asyncio
    async def test_direction_change_stops_active_travel(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()  # closing
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(80)  # open direction

        # Should have stopped and restarted in open direction
        assert cover._last_command == SERVICE_OPEN_COVER


class TestSetPositionWithTilt:
    """set_position with tilt support should also calculate tilt target."""

    @pytest.mark.asyncio
    async def test_set_position_no_tilt_when_already_flat_sequential(self, make_cover):
        """Sequential: closing with tilt already flat does not move tilt."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(0)  # close fully

        assert cover.travel_calc.is_traveling()
        assert not cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_set_position_also_moves_tilt_when_tilted(self, make_cover):
        """Sequential: closing with non-flat tilt should flatten tilt."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(0)  # close fully

        assert cover.travel_calc.is_traveling()
        assert cover.tilt_calc.is_traveling()


# ===================================================================
# set_tilt_position
# ===================================================================


class TestSetTiltPosition:
    """set_tilt_position should move tilt to the target position."""

    @pytest.mark.asyncio
    async def test_set_tilt_close_direction(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(50)

        assert cover.tilt_calc.is_traveling()
        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_set_tilt_open_direction(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(50)

        assert cover.tilt_calc.is_traveling()
        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_set_tilt_already_at_target(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(50)

        assert not cover.tilt_calc.is_traveling()
        cover.hass.services.async_call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_set_tilt_restarts_travel_when_plan_requires(self, make_cover):
        """Sequential: set_tilt_position stops active travel, then restarts to 0."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(50)

        # Sequential plan requires travel to 0 before tilting,
        # so travel restarts toward 0 as a coupled target
        assert cover.travel_calc.is_traveling()
        assert cover.tilt_calc.is_traveling()


class TestSetTiltWithTravelCoupling:
    """set_tilt_position with different tilt modes."""

    @pytest.mark.asyncio
    async def test_set_tilt_sequential_moves_travel_to_closed_first(self, make_cover):
        """Sequential: set_tilt from pos 50 requires travel to 0 first."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential",
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(0)

        assert cover.tilt_calc.is_traveling()
        # Sequential plan requires travel to 0 before tilting
        assert cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_set_tilt_sequential_no_travel_when_already_closed(self, make_cover):
        """Sequential: set_tilt from pos 0 does not move travel."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential",
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(0)

        assert cover.tilt_calc.is_traveling()
        assert not cover.travel_calc.is_traveling()


# ===================================================================
# Minimum movement time
# ===================================================================


class TestMinMovementTime:
    """Movements shorter than min_movement_time should be ignored."""

    @pytest.mark.asyncio
    async def test_short_movement_ignored(self, make_cover):
        cover = make_cover(
            travel_time_close=30,
            travel_time_open=30,
            min_movement_time=2.0,
        )
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            # 1% movement = 0.3s, which is < 2.0s
            await cover.set_position(49)

        assert not cover.travel_calc.is_traveling()
        cover.hass.services.async_call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_long_enough_movement_proceeds(self, make_cover):
        cover = make_cover(
            travel_time_close=30,
            travel_time_open=30,
            min_movement_time=2.0,
        )
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            # 20% movement = 6s, which is > 2.0s
            await cover.set_position(30)

        assert cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_endpoint_movement_always_allowed(self, make_cover):
        """Movements to endpoints (0 or 100) bypass min_movement_time."""
        cover = make_cover(
            travel_time_close=30,
            travel_time_open=30,
            min_movement_time=100.0,  # very high threshold
        )
        cover.travel_calc.set_position(99)  # almost open

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(100)  # open fully (endpoint)

        assert cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_short_movement_ignored(self, make_cover):
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            min_movement_time=1.0,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            # 1% tilt = 0.05s, which is < 1.0s
            await cover.set_tilt_position(49)

        assert not cover.tilt_calc.is_traveling()
        cover.hass.services.async_call.assert_not_awaited()


# ===================================================================
# Startup delay
# ===================================================================


class TestStartupDelay:
    """Travel startup delay should defer position tracking."""

    @pytest.mark.asyncio
    async def test_close_with_startup_delay_creates_task(self, make_cover):
        cover = make_cover(travel_startup_delay=1.0)
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Startup delay task should have been created
        assert cover._startup_delay_task is not None

    @pytest.mark.asyncio
    async def test_close_without_startup_delay_starts_immediately(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # No startup delay, so tracking starts immediately
        assert cover._startup_delay_task is None
        assert cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_with_startup_delay_creates_task(self, make_cover):
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_startup_delay=1.0,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        assert cover._startup_delay_task is not None


class TestStartupDelayConflict:
    """Direction change during startup delay should cancel and stop."""

    @pytest.mark.asyncio
    async def test_close_during_open_startup_delay_cancels(self, make_cover):
        cover = make_cover(travel_startup_delay=20.0)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()

        # Startup delay task should be running
        assert cover._startup_delay_task is not None
        assert cover._last_command == SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Should have cancelled the open startup and sent stop
        # Cover is already at position 0 (closed), so no close movement needed
        assert cover._last_command is None
        assert cover._startup_delay_task is None or cover._startup_delay_task.done()

    @pytest.mark.asyncio
    async def test_same_direction_during_startup_delay_is_ignored(self, make_cover):
        cover = make_cover(travel_startup_delay=20.0)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()

        task1 = cover._startup_delay_task

        with patch.object(cover, "async_write_ha_state"):
            # Open again during startup delay - should be ignored
            await cover.async_open_cover()

        # Task should not have been restarted
        assert cover._startup_delay_task is task1

    @pytest.mark.asyncio
    async def test_set_position_during_startup_delay_same_direction_skips(
        self, make_cover
    ):
        cover = make_cover(travel_startup_delay=20.0)
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(0)  # close (target=0)

        task1 = cover._startup_delay_task
        assert task1 is not None

        with patch.object(cover, "async_write_ha_state"):
            # Another close-direction position during startup delay
            await cover.set_position(30)

        # Should not have restarted delay
        assert cover._startup_delay_task is task1

    @pytest.mark.asyncio
    async def test_set_position_during_startup_delay_direction_change_cancels(
        self, make_cover
    ):
        cover = make_cover(travel_startup_delay=20.0)
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(0)  # close direction

        assert cover._startup_delay_task is not None
        assert cover._last_command == SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(100)  # open direction = direction change

        assert cover._last_command == SERVICE_OPEN_COVER


# ===================================================================
# Relay delay at endpoints
# ===================================================================


class TestRelayDelayAtEnd:
    """endpoint_runon_time should cause a delay at endpoints."""

    @pytest.mark.asyncio
    async def test_auto_stop_at_endpoint_creates_delay_task(self, make_cover):
        cover = make_cover(endpoint_runon_time=4.0)
        cover.travel_calc.set_position(100)
        # Simulate the cover reaching position 0 (closed endpoint)
        cover.travel_calc.start_travel(0)
        # Force position reached by setting position directly
        cover.travel_calc.set_position(0)
        cover.travel_calc.stop()
        cover.travel_calc.start_travel(0)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.auto_stop_if_necessary()

        # Should have created a delay task instead of stopping immediately
        assert cover._delay_task is not None
        cover._delay_task.cancel()

    @pytest.mark.asyncio
    async def test_auto_stop_at_midpoint_stops_immediately(self, make_cover):
        cover = make_cover(endpoint_runon_time=4.0)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover.auto_stop_if_necessary()

        # At midpoint, should stop immediately (no delay)
        assert cover._delay_task is None

    @pytest.mark.asyncio
    async def test_close_cancels_active_relay_delay(self, make_cover):
        """Starting a new movement should cancel an active relay delay."""
        cover = make_cover(endpoint_runon_time=4.0)
        cover.travel_calc.set_position(100)  # at open endpoint

        # Simulate an active delay task
        async def fake_delay():
            await asyncio.sleep(100)

        cover._delay_task = asyncio.ensure_future(fake_delay())

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Delay should have been cancelled, new movement initiated
        # (movement starts after startup delay, so check that the
        # startup delay task was created rather than is_traveling)
        assert cover._startup_delay_task is not None or cover.travel_calc.is_traveling()


# ===================================================================
# Stop cover
# ===================================================================


class TestStopCover:
    """async_stop_cover should stop all movement."""

    @pytest.mark.asyncio
    async def test_stop_while_closing(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        assert cover.travel_calc.is_traveling()

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()

        assert not cover.travel_calc.is_traveling()
        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_stop_clears_startup_delay(self, make_cover):
        cover = make_cover(travel_startup_delay=20.0)
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        assert cover._startup_delay_task is not None

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()

        assert cover._startup_delay_task is None
        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_stop_with_tilt(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        assert cover.tilt_calc.is_traveling()

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()

        assert not cover.tilt_calc.is_traveling()


# ===================================================================
# set_known_position / set_known_tilt_position
# ===================================================================


class TestSetKnownPosition:
    """set_known_position should update position without movement."""

    @pytest.mark.asyncio
    async def test_set_known_position(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_known_position(position=50)

        assert cover.travel_calc.current_position() == 50
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_set_known_tilt_position(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_known_tilt_position(tilt_position=75)

        assert cover.tilt_calc.current_position() == 75


# ===================================================================
# Properties
# ===================================================================


class TestProperties:
    """Test cover entity properties."""

    def test_is_opening(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel_up()
        assert cover.is_opening is True
        assert cover.is_closing is False

    def test_is_closing(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(100)
        cover.travel_calc.start_travel_down()
        assert cover.is_closing is True
        assert cover.is_opening is False

    def test_is_closed(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)
        assert cover.is_closed is True

    def test_is_not_closed(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(50)
        assert cover.is_closed is False

    def test_is_closed_with_tilt(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)
        assert cover.is_closed is True

    def test_is_not_closed_when_tilt_open(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(100)
        assert cover.is_closed is False

    def test_current_position(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(70)
        assert cover.current_cover_position == 70

    def test_current_tilt_position(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.tilt_calc.set_position(75)
        assert cover.current_cover_tilt_position == 75

    def test_no_tilt_position_without_support(self, make_cover):
        cover = make_cover()
        assert cover.current_cover_tilt_position is None

    def test_has_tilt_support(self, make_cover):
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        assert cover._has_tilt_support() is True

    def test_no_tilt_support(self, make_cover):
        cover = make_cover()
        assert cover._has_tilt_support() is False


# ===================================================================
# Tilt constraints
# ===================================================================


class TestTiltConstraints:
    """snap_trackers_to_physical should sync tilt at travel boundaries."""

    def test_sequential_forces_tilt_flat_when_not_closed(self, make_cover):
        """Sequential: tilt is forced to 100 when travel is not at closed (0)."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential",
        )
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(50)

        cover._tilt_strategy.snap_trackers_to_physical(
            cover.travel_calc, cover.tilt_calc
        )

        assert cover.tilt_calc.current_position() == 100  # forced flat

    def test_sequential_no_constraint_when_closed(self, make_cover):
        """Sequential: tilt unchanged when travel is at closed (0)."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential",
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(50)

        cover._tilt_strategy.snap_trackers_to_physical(
            cover.travel_calc, cover.tilt_calc
        )

        assert cover.tilt_calc.current_position() == 50  # unchanged


# ===================================================================
# Sequential pre-step delay (tilt before travel, travel before tilt)
# ===================================================================


class TestSequentialPreStepDelay:
    """In sequential mode, movement steps execute one after another.

    When opening from closed+tilted, the tilt must fully open before
    travel begins. The travel calculator's start is delayed by the
    tilt duration so its position stays put during the tilt phase.
    """

    @pytest.mark.asyncio
    async def test_open_from_closed_tilted_delays_travel(self, make_cover):
        """Opening from pos=0, tilt=0: travel should be delayed by tilt time."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential",
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)

        import time

        before = time.time()
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()

        # Tilt should be traveling immediately (0→100)
        assert cover.tilt_calc.is_traveling()
        # Travel calc is tracking (target differs from position) but
        # its timestamp is offset into the future by tilt_time_open
        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._last_known_position_timestamp >= before + 4.9

        # Travel position should still be at 0 (delay hasn't elapsed)
        assert cover.travel_calc.current_position() == 0

    @pytest.mark.asyncio
    async def test_no_delay_when_tilt_already_flat(self, make_cover):
        """Opening from pos=0, tilt=100: no pre-step needed, no delay."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential",
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(100)

        import time

        before = time.time()
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()

        assert cover.travel_calc.is_traveling()
        # No delay — timestamp should be approximately now
        assert cover.travel_calc._last_known_position_timestamp < before + 1.0

    @pytest.mark.asyncio
    async def test_set_position_delays_travel_for_tilt_prestep(self, make_cover):
        """set_position from closed+tilted: travel delayed by tilt time."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential",
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)

        import time

        before = time.time()
        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(10)

        assert cover.tilt_calc.is_traveling()
        assert cover.travel_calc.is_traveling()
        # Travel delayed by full tilt_time_open (tilt 0→100 = 5.0s)
        assert cover.travel_calc._last_known_position_timestamp >= before + 4.9
        assert cover.travel_calc.current_position() == 0

    @pytest.mark.asyncio
    async def test_tilt_endpoint_delays_tilt_for_travel_prestep(self, make_cover):
        """Closing tilt from pos=50: travel must close first, then tilt."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential",
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        import time

        before = time.time()
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        # Travel (coupled) should be tracking immediately (50→0)
        assert cover.travel_calc.is_traveling()
        # Tilt (primary) should be delayed by travel time (50→0 = 15s for 30s full)
        assert cover.tilt_calc._last_known_position_timestamp >= before + 14.0
        assert cover.tilt_calc.current_position() == 100  # not started yet


# ===================================================================
# Dual-motor tilt pre-step and restore after travel
# ===================================================================


class TestDualMotorTiltPreStep:
    """Dual-motor covers should tilt to safe before travel, then restore."""

    def _make_dual_motor_cover(self, make_cover):
        return make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )

    # -- Pre-step phase --

    @pytest.mark.asyncio
    async def test_pre_step_starts_tilt_motor_not_travel(self, make_cover):
        """Moving position should start tilt motor first, not travel motor."""
        cover = self._make_dual_motor_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(30)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Tilt motor should be opening (30 → 100 = safe)
        assert cover.tilt_calc.is_traveling()
        assert cover.tilt_calc._travel_to_position == 100

        # Travel should NOT have started yet
        assert not cover.travel_calc.is_traveling()

        # Pending travel is queued
        assert cover._pending_travel_target == 0
        assert cover._pending_travel_command == SERVICE_CLOSE_COVER
        assert cover._tilt_restore_target == 30

    @pytest.mark.asyncio
    async def test_pre_step_sends_tilt_open_command(self, make_cover):
        """Tilt motor open switch should be activated for opening tilt."""
        cover = self._make_dual_motor_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(30)  # needs to open to 100

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        calls = cover.hass.services.async_call.call_args_list
        # Should turn on tilt_open switch
        tilt_open_calls = [
            c
            for c in calls
            if c[0][1] == "turn_on" and c[0][2].get("entity_id") == "switch.tilt_open"
        ]
        assert len(tilt_open_calls) == 1

        # Should NOT send the travel command (open/close via _async_handle_command)
        stop_calls = [
            c
            for c in calls
            if c[0][1] == "turn_on"
            and c[0][2].get("entity_id") in ("switch.open", "switch.close")
        ]
        assert len(stop_calls) == 0

    @pytest.mark.asyncio
    async def test_set_position_starts_pre_step(self, make_cover):
        """set_position should also start tilt pre-step."""
        cover = self._make_dual_motor_cover(make_cover)
        cover.travel_calc.set_position(80)
        cover.tilt_calc.set_position(40)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(20)

        assert cover.tilt_calc.is_traveling()
        assert not cover.travel_calc.is_traveling()
        assert cover._pending_travel_target == 20
        assert cover._tilt_restore_target == 40

    @pytest.mark.asyncio
    async def test_no_pre_step_when_tilt_already_safe(self, make_cover):
        """No pre-step needed when tilt is already at safe position."""
        cover = self._make_dual_motor_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)  # already safe

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Travel should start immediately (no pre-step)
        assert cover.travel_calc.is_traveling()
        assert cover._pending_travel_target is None
        assert cover._tilt_restore_target is None

    # -- Pre-step completion → travel starts --

    @pytest.mark.asyncio
    async def test_pre_step_complete_starts_travel(self, make_cover):
        """When tilt reaches safe position, travel should start."""
        cover = self._make_dual_motor_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(30)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Simulate tilt reaching safe position
        cover.tilt_calc.set_position(100)

        cover.hass.services.async_call.reset_mock()
        with patch.object(cover, "async_write_ha_state"):
            await cover.auto_stop_if_necessary()

        # Travel should now be running
        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._travel_to_position == 0
        assert cover._pending_travel_target is None

        # Tilt stop should have been called
        calls = cover.hass.services.async_call.call_args_list
        tilt_stop_calls = [
            c
            for c in calls
            if c[0][1] == "turn_off"
            and c[0][2].get("entity_id") in ("switch.tilt_open", "switch.tilt_close")
        ]
        assert len(tilt_stop_calls) == 2

    # -- Full lifecycle: pre-step → travel → restore --

    @pytest.mark.asyncio
    async def test_full_lifecycle_pre_step_travel_restore(self, make_cover):
        """Full dual_motor lifecycle: tilt safe → travel → tilt restore."""
        cover = self._make_dual_motor_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(30)

        with patch.object(cover, "async_write_ha_state"):
            # Phase 1: Start → tilt pre-step
            await cover.async_close_cover()
            assert cover.tilt_calc.is_traveling()
            assert not cover.travel_calc.is_traveling()

            # Phase 2: Tilt reaches safe → travel starts
            cover.tilt_calc.set_position(100)
            await cover.auto_stop_if_necessary()
            assert cover.travel_calc.is_traveling()
            assert cover._tilt_restore_target == 30

            # Phase 3: Travel completes → tilt restore starts
            cover.travel_calc.set_position(0)
            await cover.auto_stop_if_necessary()
            assert cover._tilt_restore_active is True
            assert cover.tilt_calc.is_traveling()
            assert cover.tilt_calc._travel_to_position == 30

            # Phase 4: Tilt restore completes → all done
            cover.tilt_calc.set_position(30)
            await cover.auto_stop_if_necessary()
            assert cover._tilt_restore_active is False
            assert not cover.tilt_calc.is_traveling()

    # -- Stop during phases --

    @pytest.mark.asyncio
    async def test_stop_during_tilt_pre_step(self, make_cover):
        """Stopping during tilt pre-step should clear all pending state."""
        cover = self._make_dual_motor_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(30)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        assert cover._pending_travel_target == 0

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()

        assert cover._pending_travel_target is None
        assert cover._pending_travel_command is None
        assert cover._tilt_restore_target is None
        assert not cover.tilt_calc.is_traveling()

        # Tilt motor should have been stopped
        calls = cover.hass.services.async_call.call_args_list
        tilt_stop_calls = [
            c
            for c in calls
            if c[0][1] == "turn_off"
            and c[0][2].get("entity_id") in ("switch.tilt_open", "switch.tilt_close")
        ]
        assert len(tilt_stop_calls) >= 2

    @pytest.mark.asyncio
    async def test_stop_during_travel_phase(self, make_cover):
        """Stopping during travel phase should clear restore target."""
        cover = self._make_dual_motor_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(30)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

            # Complete pre-step
            cover.tilt_calc.set_position(100)
            await cover.auto_stop_if_necessary()

        assert cover.travel_calc.is_traveling()
        assert cover._tilt_restore_target == 30

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()

        assert cover._tilt_restore_target is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_stop_during_tilt_restore(self, make_cover):
        """Stopping during tilt restore should stop tilt motor and clear state."""
        cover = self._make_dual_motor_cover(make_cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(30)
        cover.tilt_calc.start_travel(50)
        cover._tilt_restore_active = True

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()

        assert cover._tilt_restore_active is False
        assert cover._tilt_restore_target is None
        assert not cover.tilt_calc.is_traveling()

    # -- Edge cases --

    @pytest.mark.asyncio
    async def test_sequential_no_pre_step(self, make_cover):
        """Sequential mode should NOT use tilt pre-step (shared motor)."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential",
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(30)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Travel should start immediately (with pre_step_delay, not tilt motor)
        assert cover.travel_calc.is_traveling()
        assert cover._pending_travel_target is None
        assert cover._tilt_restore_target is None


# ===================================================================
# Inline tilt: tilt restore after travel via main motor reversal
# ===================================================================


class TestInlineTiltRestore:
    """Inline tilt: tilt restores after travel via main motor reversal."""

    def _make_inline_cover(self, make_cover):
        return make_cover(
            tilt_time_close=2.0,
            tilt_time_open=2.0,
            tilt_mode="inline",
        )

    @pytest.mark.asyncio
    async def test_close_to_mid_sets_restore_target(self, make_cover):
        """Closing to mid-position saves tilt for restore."""
        cover = self._make_inline_cover(make_cover)
        cover.travel_calc.set_position(80)
        cover.tilt_calc.set_position(100)  # tilt open

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(30)

        # Pre-step delay is used (not tilt motor pre-step)
        assert cover.travel_calc.is_traveling()
        assert cover._pending_travel_target is None  # no dual_motor pre-step
        assert cover._tilt_restore_target == 100

    @pytest.mark.asyncio
    async def test_no_restore_at_endpoint_zero(self, make_cover):
        """Closing to 0%: no restore (endpoint forces tilt=0)."""
        cover = self._make_inline_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover._async_move_to_endpoint(target=0)

        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_no_restore_at_endpoint_hundred(self, make_cover):
        """Opening to 100%: no restore (endpoint forces tilt=100)."""
        cover = self._make_inline_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover._async_move_to_endpoint(target=100)

        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_no_restore_when_tilt_already_at_direction_endpoint(self, make_cover):
        """No restore when tilt is already at direction's endpoint."""
        cover = self._make_inline_cover(make_cover)
        cover.travel_calc.set_position(80)
        cover.tilt_calc.set_position(0)  # already closed

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(30)  # closing — tilt endpoint is 0

        # No tilt pre-step needed, so no restore
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_restore_reverses_main_motor(self, make_cover):
        """After travel, restore sends opposite main motor command."""
        cover = self._make_inline_cover(make_cover)
        cover.travel_calc.set_position(80)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(30)

            # Simulate travel completing (tilt is now 0 after closing)
            cover.travel_calc.set_position(30)
            cover.tilt_calc.set_position(0)
            cover.hass.services.async_call.reset_mock()
            await cover.auto_stop_if_necessary()

        # Restore should be active
        assert cover._tilt_restore_active is True
        assert cover.tilt_calc.is_traveling()
        assert cover.tilt_calc._travel_to_position == 100

        # Main motor open command should have been sent (to restore tilt 0->100)
        calls = cover.hass.services.async_call.call_args_list
        open_calls = [
            c
            for c in calls
            if c[0][1] == "turn_on" and c[0][2].get("entity_id") == "switch.open"
        ]
        assert len(open_calls) == 1

    @pytest.mark.asyncio
    async def test_restore_complete_stops_main_motor(self, make_cover):
        """When restore finishes, main motor is stopped."""
        cover = self._make_inline_cover(make_cover)
        cover.travel_calc.set_position(80)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(30)

            # Complete travel
            cover.travel_calc.set_position(30)
            cover.tilt_calc.set_position(0)
            await cover.auto_stop_if_necessary()

            # Complete restore
            cover.tilt_calc.set_position(100)
            cover.hass.services.async_call.reset_mock()
            await cover.auto_stop_if_necessary()

        assert cover._tilt_restore_active is False
        assert not cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, make_cover):
        """Full inline lifecycle: pre-step delay -> travel -> restore."""
        cover = self._make_inline_cover(make_cover)
        cover.travel_calc.set_position(80)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            # Start: closing to 30
            await cover.set_position(30)
            assert cover.travel_calc.is_traveling()
            assert cover._tilt_restore_target == 100

            # Travel completes -> restore starts
            cover.travel_calc.set_position(30)
            cover.tilt_calc.set_position(0)
            await cover.auto_stop_if_necessary()
            assert cover._tilt_restore_active is True

            # Restore completes -> done
            cover.tilt_calc.set_position(100)
            await cover.auto_stop_if_necessary()
            assert cover._tilt_restore_active is False

    @pytest.mark.asyncio
    async def test_stop_during_restore(self, make_cover):
        """Stopping during restore clears state and stops motor."""
        cover = self._make_inline_cover(make_cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(30)
        cover.tilt_calc.start_travel(50)
        cover._tilt_restore_active = True

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()

        assert cover._tilt_restore_active is False
        assert not cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_endpoint_move_uses_pre_step_delay(self, make_cover):
        """Endpoint move with inline: uses pre_step_delay, no restore."""
        cover = self._make_inline_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)  # open tilt

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Travel started (with pre_step_delay for tilt phase)
        assert cover.travel_calc.is_traveling()
        # No restore at endpoint
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_set_position_endpoint_also_no_restore(self, make_cover):
        """set_position(0) should not set restore target."""
        cover = self._make_inline_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(0)

        assert cover._tilt_restore_target is None
