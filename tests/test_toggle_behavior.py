"""Tests for toggle-specific behaviour in CoverTimeBased.

These tests exercise the higher-level async_close_cover / async_open_cover /
async_stop_cover methods and verify that toggle mode correctly stops the
cover when a same-direction command arrives while already moving, and that
the stop guard prevents relay commands when the cover is idle.
"""

import pytest
from unittest.mock import AsyncMock, patch

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
)

from custom_components.cover_time_based.cover import (
    INPUT_MODE_SWITCH,
    INPUT_MODE_TOGGLE,
)


# ===================================================================
# Toggle: close/open while already moving in the same direction
# ===================================================================


class TestToggleCloseWhileMoving:
    """Issuing close while already closing should stop (toggle behaviour)."""

    @pytest.mark.asyncio
    async def test_close_while_closing_stops(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)

        # Simulate that the cover is currently closing (position 100 = fully open)
        cover.travel_calc.set_position(100)
        cover.travel_calc.start_travel_down()

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "async_stop_cover", new_callable=AsyncMock
            ) as mock_stop,
        ):
            await cover.async_close_cover()

        mock_stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_open_while_opening_stops(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)

        # Simulate that the cover is currently opening (position 0 = fully closed)
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel_up()

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "async_stop_cover", new_callable=AsyncMock
            ) as mock_stop,
        ):
            await cover.async_open_cover()

        mock_stop.assert_awaited_once()


# ===================================================================
# Toggle stop guard: idle cover should NOT send relay commands
# ===================================================================


class TestToggleStopGuard:
    """async_stop_cover on an idle toggle cover must not send relay commands."""

    @pytest.mark.asyncio
    async def test_stop_when_idle_toggle_no_relay_command(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()

        # Toggle mode: no relay command because the cover was idle
        cover.hass.services.async_call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stop_when_idle_switch_sends_relay_command(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_SWITCH)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()

        # Switch mode: always sends the stop relay command, even when idle
        cover.hass.services.async_call.assert_awaited()


# ===================================================================
# Stop before direction change in toggle mode
# ===================================================================


class TestStopBeforeDirectionChange:
    """Closing while opening in toggle mode should stop first."""

    @pytest.mark.asyncio
    async def test_close_while_opening_stops_first(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)

        # Simulate that the cover is currently opening (position 0 = fully closed)
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "async_stop_cover", new_callable=AsyncMock
            ) as mock_stop,
        ):
            await cover.async_close_cover()

        # async_stop_cover should have been called to stop the opening movement
        mock_stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_open_while_closing_stops_first(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)

        # Simulate that the cover is currently closing (position 100 = fully open)
        cover.travel_calc.set_position(100)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "async_stop_cover", new_callable=AsyncMock
            ) as mock_stop,
        ):
            await cover.async_open_cover()

        # async_stop_cover should have been called to stop the closing movement
        mock_stop.assert_awaited_once()
