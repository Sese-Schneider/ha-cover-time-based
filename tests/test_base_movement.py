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
        cover.travel_calc.set_position(0)  # fully open

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        assert cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_CLOSE_COVER
        cover.hass.services.async_call.assert_awaited()

    @pytest.mark.asyncio
    async def test_close_when_already_closed_does_nothing(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(100)  # fully closed

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        assert not cover.travel_calc.is_traveling()
        cover.hass.services.async_call.assert_not_awaited()


class TestOpenFromClosed:
    """Opening from fully closed should send open command and start travel."""

    @pytest.mark.asyncio
    async def test_open_sends_command_and_starts_travel(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(100)  # fully closed

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()

        assert cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_OPEN_COVER
        cover.hass.services.async_call.assert_awaited()

    @pytest.mark.asyncio
    async def test_open_when_already_open_does_nothing(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)  # fully open

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
    """Closing with tilt support should also move tilt toward closed."""

    @pytest.mark.asyncio
    async def test_close_also_starts_tilt_travel(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        assert cover.travel_calc.is_traveling()
        assert cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_open_also_starts_tilt_travel(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

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
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        assert cover.tilt_calc.is_traveling()
        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_close_tilt_when_already_closed_does_nothing(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        assert not cover.tilt_calc.is_traveling()
        cover.hass.services.async_call.assert_not_awaited()


class TestOpenTilt:
    """Tilt open should move tilt to fully open."""

    @pytest.mark.asyncio
    async def test_open_tilt_sends_command_and_starts_tilt(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover_tilt()

        assert cover.tilt_calc.is_traveling()
        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_open_tilt_when_already_open_does_nothing(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover_tilt()

        assert not cover.tilt_calc.is_traveling()
        cover.hass.services.async_call.assert_not_awaited()


class TestTiltStopsTravelFirst:
    """Tilt movement should stop any active travel first."""

    @pytest.mark.asyncio
    async def test_close_tilt_stops_active_travel(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        # Travel should have been stopped
        assert not cover.travel_calc.is_traveling()
        # Tilt should be traveling
        assert cover.tilt_calc.is_traveling()


class TestTiltWithTravelCoupling:
    """Tilt with travel_moves_with_tilt should also move travel."""

    @pytest.mark.asyncio
    async def test_close_tilt_also_moves_travel_when_coupled(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            travel_moves_with_tilt=True,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        assert cover.tilt_calc.is_traveling()
        assert cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_open_tilt_also_moves_travel_when_coupled(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            travel_moves_with_tilt=True,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover_tilt()

        assert cover.tilt_calc.is_traveling()
        assert cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_close_tilt_without_coupling_does_not_move_travel(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            travel_moves_with_tilt=False,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

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
        cover.travel_calc.set_position(0)  # currently open

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(50)  # HA position 50 = travel_calc 50

        assert cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_set_position_open_direction(self, make_cover):
        """Setting position above current should open (move up)."""
        cover = make_cover()
        cover.travel_calc.set_position(100)  # currently closed

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
        """Setting position to 0 (HA) = travel_calc 100."""
        cover = make_cover()
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(0)

        assert cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_set_position_to_fully_open(self, make_cover):
        """Setting position to 100 (HA) = travel_calc 0."""
        cover = make_cover()
        cover.travel_calc.set_position(100)

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
    async def test_set_position_also_moves_tilt(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)

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
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(50)

        assert cover.tilt_calc.is_traveling()
        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_set_tilt_open_direction(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(50)

        assert cover.tilt_calc.is_traveling()
        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_set_tilt_already_at_target(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(50)

        assert not cover.tilt_calc.is_traveling()
        cover.hass.services.async_call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_set_tilt_stops_active_travel(self, make_cover):
        """set_tilt_position should stop any active travel (not a direction change)."""
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(50)

        # Travel should be stopped, tilt should be moving
        assert not cover.travel_calc.is_traveling()
        assert cover.tilt_calc.is_traveling()


class TestSetTiltWithTravelCoupling:
    """set_tilt_position with travel_moves_with_tilt should also move travel."""

    @pytest.mark.asyncio
    async def test_set_tilt_moves_travel_when_coupled(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            travel_moves_with_tilt=True,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(0)  # close tilt fully

        assert cover.tilt_calc.is_traveling()
        assert cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_set_tilt_does_not_move_travel_when_uncoupled(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            travel_moves_with_tilt=False,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

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
            travel_time_down=30,
            travel_time_up=30,
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
            travel_time_down=30,
            travel_time_up=30,
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
            travel_time_down=30,
            travel_time_up=30,
            min_movement_time=100.0,  # very high threshold
        )
        cover.travel_calc.set_position(99)  # almost closed

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(0)  # close fully (endpoint)

        assert cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_short_movement_ignored(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
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
        cover = make_cover(travel_startup_delay=0.5)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Startup delay task should have been created
        assert cover._startup_delay_task is not None

    @pytest.mark.asyncio
    async def test_close_without_startup_delay_starts_immediately(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # No startup delay, so tracking starts immediately
        assert cover._startup_delay_task is None
        assert cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_with_startup_delay_creates_task(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            tilt_startup_delay=0.5,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        assert cover._startup_delay_task is not None


class TestStartupDelayConflict:
    """Direction change during startup delay should cancel and stop."""

    @pytest.mark.asyncio
    async def test_close_during_open_startup_delay_cancels(self, make_cover):
        cover = make_cover(travel_startup_delay=10.0)
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()

        # Startup delay task should be running
        assert cover._startup_delay_task is not None
        assert cover._last_command == SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Should have cancelled the open startup and sent stop
        # Cover is already at position 100 (closed), so no close movement needed
        assert cover._last_command is None
        assert cover._startup_delay_task is None or cover._startup_delay_task.done()

    @pytest.mark.asyncio
    async def test_same_direction_during_startup_delay_is_ignored(self, make_cover):
        cover = make_cover(travel_startup_delay=10.0)
        cover.travel_calc.set_position(100)

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
        cover = make_cover(travel_startup_delay=10.0)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(0)  # close (target=100 internal)

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
        cover = make_cover(travel_startup_delay=10.0)
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
    """travel_delay_at_end should delay the stop command at endpoints."""

    @pytest.mark.asyncio
    async def test_auto_stop_at_endpoint_creates_delay_task(self, make_cover):
        cover = make_cover(travel_delay_at_end=2.0)
        cover.travel_calc.set_position(0)
        # Simulate the cover reaching position 100 (endpoint)
        cover.travel_calc.start_travel(100)
        # Force position reached by setting position directly
        cover.travel_calc.set_position(100)
        cover.travel_calc.stop()
        cover.travel_calc.start_travel(100)
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.auto_stop_if_necessary()

        # Should have created a delay task instead of stopping immediately
        assert cover._delay_task is not None
        cover._delay_task.cancel()

    @pytest.mark.asyncio
    async def test_auto_stop_at_midpoint_stops_immediately(self, make_cover):
        cover = make_cover(travel_delay_at_end=2.0)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover.auto_stop_if_necessary()

        # At midpoint, should stop immediately (no delay)
        assert cover._delay_task is None

    @pytest.mark.asyncio
    async def test_close_cancels_active_relay_delay(self, make_cover):
        """Starting a new movement should cancel an active relay delay."""
        cover = make_cover(travel_delay_at_end=10.0)
        cover.travel_calc.set_position(0)  # at open endpoint

        # Simulate an active delay task
        async def fake_delay():
            await asyncio.sleep(100)

        cover._delay_task = asyncio.ensure_future(fake_delay())

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Delay should have been cancelled, new movement started
        assert cover.travel_calc.is_traveling()


# ===================================================================
# Stop cover
# ===================================================================


class TestStopCover:
    """async_stop_cover should stop all movement."""

    @pytest.mark.asyncio
    async def test_stop_while_closing(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        assert cover.travel_calc.is_traveling()

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()

        assert not cover.travel_calc.is_traveling()
        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_stop_clears_startup_delay(self, make_cover):
        cover = make_cover(travel_startup_delay=10.0)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        assert cover._startup_delay_task is not None

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()

        assert cover._startup_delay_task is None
        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_stop_with_tilt(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

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
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
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
        cover.travel_calc.set_position(100)
        cover.travel_calc.start_travel_up()
        assert cover.is_opening is True
        assert cover.is_closing is False

    def test_is_closing(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel_down()
        assert cover.is_closing is True
        assert cover.is_opening is False

    def test_is_closed(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(100)
        assert cover.is_closed is True

    def test_is_not_closed(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(50)
        assert cover.is_closed is False

    def test_is_closed_with_tilt(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)
        assert cover.is_closed is True

    def test_is_not_closed_when_tilt_open(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(0)
        assert cover.is_closed is False

    def test_current_position(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(30)
        # HA position is inverted: 100 - 30 = 70
        assert cover.current_cover_position == 70

    def test_current_tilt_position(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.tilt_calc.set_position(25)
        assert cover.current_cover_tilt_position == 75

    def test_no_tilt_position_without_support(self, make_cover):
        cover = make_cover()
        assert cover.current_cover_tilt_position is None

    def test_has_tilt_support(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        assert cover._has_tilt_support() is True

    def test_no_tilt_support(self, make_cover):
        cover = make_cover()
        assert cover._has_tilt_support() is False


# ===================================================================
# Tilt constraints
# ===================================================================


class TestTiltConstraints:
    """_enforce_tilt_constraints should sync tilt at travel boundaries."""

    def test_tilt_forced_open_when_travel_fully_open(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            travel_moves_with_tilt=True,
        )
        cover.travel_calc.set_position(0)  # fully open
        cover.tilt_calc.set_position(50)

        cover._enforce_tilt_constraints()

        assert cover.tilt_calc.current_position() == 0

    def test_tilt_forced_closed_when_travel_fully_closed(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            travel_moves_with_tilt=True,
        )
        cover.travel_calc.set_position(100)  # fully closed
        cover.tilt_calc.set_position(50)

        cover._enforce_tilt_constraints()

        assert cover.tilt_calc.current_position() == 100

    def test_no_constraint_without_coupling(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            travel_moves_with_tilt=False,
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(50)

        cover._enforce_tilt_constraints()

        assert cover.tilt_calc.current_position() == 50  # unchanged

    def test_no_constraint_at_midpoint(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            travel_moves_with_tilt=True,
        )
        cover.travel_calc.set_position(50)  # midpoint
        cover.tilt_calc.set_position(30)

        cover._enforce_tilt_constraints()

        assert cover.tilt_calc.current_position() == 30  # unchanged
