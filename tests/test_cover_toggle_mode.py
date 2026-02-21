"""Tests for ToggleModeCover.

Tests cover:
- _send_open / _send_close / _send_stop relay patterns
- Toggle-specific behaviour: close-while-closing, open-while-opening -> stop
- Stop guard: idle cover should not send relay commands
- Direction change: closing while opening stops first
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
)

from custom_components.cover_time_based.cover_toggle_mode import ToggleModeCover


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _make_toggle_cover(
    open_switch="switch.open",
    close_switch="switch.close",
    stop_switch=None,
    pulse_time=1.0,
):
    """Create a ToggleModeCover wired to a mock hass."""
    cover = ToggleModeCover(
        device_id="test_toggle",
        name="Test Toggle",
        tilt_strategy=None,
        travel_time_close=30,
        travel_time_open=30,
        tilt_time_close=None,
        tilt_time_open=None,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        endpoint_runon_time=None,
        min_movement_time=None,
        open_switch_entity_id=open_switch,
        close_switch_entity_id=close_switch,
        stop_switch_entity_id=stop_switch,
        pulse_time=pulse_time,
    )
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.async_create_task = lambda coro: asyncio.ensure_future(coro)
    cover.hass = hass
    return cover


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _calls(mock: AsyncMock):
    return mock.call_args_list


def _ha(service, entity_id):
    return call("homeassistant", service, {"entity_id": entity_id}, False)


# ===================================================================
# _send_open
# ===================================================================


class TestToggleModeSendOpen:
    @pytest.mark.asyncio
    async def test_open_pulses_open_switch(self):
        cover = _make_toggle_cover()
        with patch(
            "custom_components.cover_time_based.cover_toggle_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_open()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
            # after pulse sleep
            _ha("turn_off", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_open_with_stop_switch(self):
        cover = _make_toggle_cover(stop_switch="switch.stop")
        with patch(
            "custom_components.cover_time_based.cover_toggle_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_open()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
            _ha("turn_off", "switch.stop"),
            # after pulse sleep
            _ha("turn_off", "switch.open"),
        ]


# ===================================================================
# _send_close
# ===================================================================


class TestToggleModeSendClose:
    @pytest.mark.asyncio
    async def test_close_pulses_close_switch(self):
        cover = _make_toggle_cover()
        with patch(
            "custom_components.cover_time_based.cover_toggle_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_close()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
            # after pulse sleep
            _ha("turn_off", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_close_with_stop_switch(self):
        cover = _make_toggle_cover(stop_switch="switch.stop")
        with patch(
            "custom_components.cover_time_based.cover_toggle_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_close()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
            _ha("turn_off", "switch.stop"),
            # after pulse sleep
            _ha("turn_off", "switch.close"),
        ]


# ===================================================================
# _send_stop
# ===================================================================


class TestToggleModeSendStop:
    @pytest.mark.asyncio
    async def test_stop_after_close_pulses_close_switch(self):
        cover = _make_toggle_cover()
        cover._last_command = SERVICE_CLOSE_COVER
        with patch(
            "custom_components.cover_time_based.cover_toggle_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.close"),
            # after pulse sleep
            _ha("turn_off", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_stop_after_open_pulses_open_switch(self):
        cover = _make_toggle_cover()
        cover._last_command = SERVICE_OPEN_COVER
        with patch(
            "custom_components.cover_time_based.cover_toggle_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.open"),
            # after pulse sleep
            _ha("turn_off", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_with_no_last_command_does_nothing(self):
        cover = _make_toggle_cover()
        cover._last_command = None
        await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == []


# ===================================================================
# Toggle-specific: close-while-closing stops, open-while-opening stops
# ===================================================================


class TestToggleCloseWhileClosing:
    @pytest.mark.asyncio
    async def test_close_while_closing_stops(self):
        cover = _make_toggle_cover()

        # Simulate currently closing (position 100 = fully open)
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


class TestToggleOpenWhileOpening:
    @pytest.mark.asyncio
    async def test_open_while_opening_stops(self):
        cover = _make_toggle_cover()

        # Simulate currently opening (position 0 = fully closed)
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
    @pytest.mark.asyncio
    async def test_stop_when_idle_no_relay_command(self):
        cover = _make_toggle_cover()

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()

        # Idle cover: no relay command
        cover.hass.services.async_call.assert_not_awaited()


# ===================================================================
# Direction change: closing while opening stops first
# ===================================================================


class TestToggleDirectionChange:
    @pytest.mark.asyncio
    async def test_close_while_opening_stops_first(self):
        cover = _make_toggle_cover()

        # Simulate currently opening (position 0 = fully closed)
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "async_stop_cover", new_callable=AsyncMock
            ) as mock_stop,
            patch(
                "custom_components.cover_time_based.cover_toggle_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await cover.async_close_cover()

        mock_stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_open_while_closing_stops_first(self):
        cover = _make_toggle_cover()

        # Simulate currently closing (position 100 = fully open)
        cover.travel_calc.set_position(100)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "async_stop_cover", new_callable=AsyncMock
            ) as mock_stop,
            patch(
                "custom_components.cover_time_based.cover_toggle_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await cover.async_open_cover()

        mock_stop.assert_awaited_once()


# ===================================================================
# Stop with tilt: snap_trackers_to_physical
# ===================================================================


class TestToggleStopWithTilt:
    @pytest.mark.asyncio
    async def test_stop_with_tilt_snaps_trackers(self):
        """Stopping toggle cover with tilt calls snap_trackers_to_physical."""
        tilt_strategy = MagicMock()
        tilt_strategy.snap_trackers_to_physical = MagicMock()
        tilt_strategy.uses_tilt_motor = False
        tilt_strategy.restores_tilt = False

        cover = ToggleModeCover(
            device_id="test_toggle_tilt",
            name="Test Toggle Tilt",
            tilt_strategy=tilt_strategy,
            travel_time_close=30,
            travel_time_open=30,
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            travel_startup_delay=None,
            tilt_startup_delay=None,
            endpoint_runon_time=None,
            min_movement_time=None,
            open_switch_entity_id="switch.open",
            close_switch_entity_id="switch.close",
            stop_switch_entity_id=None,
            pulse_time=1.0,
        )
        hass = MagicMock()
        hass.services.async_call = AsyncMock()
        hass.async_create_task = lambda coro: asyncio.ensure_future(coro)
        cover.hass = hass

        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()

        tilt_strategy.snap_trackers_to_physical.assert_called_once_with(
            cover.travel_calc, cover.tilt_calc
        )
