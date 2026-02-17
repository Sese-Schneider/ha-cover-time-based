"""Tests for PulseModeCover._send_open/close/stop.

Each test verifies the exact sequence of homeassistant.turn_on/turn_off
service calls for the momentary pulse mode, including the pulse sleep.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from custom_components.cover_time_based.cover_pulse_mode import PulseModeCover


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _make_pulse_cover(
    open_switch="switch.open",
    close_switch="switch.close",
    stop_switch=None,
    pulse_time=1.0,
):
    """Create a PulseModeCover wired to a mock hass."""
    cover = PulseModeCover(
        device_id="test_pulse",
        name="Test Pulse",
        travel_moves_with_tilt=False,
        travel_time_down=30,
        travel_time_up=30,
        tilt_time_down=None,
        tilt_time_up=None,
        travel_motor_overhead=None,
        tilt_motor_overhead=None,
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


# ---------------------------------------------------------------------------
# _send_open
# ---------------------------------------------------------------------------


class TestPulseModeSendOpen:
    @pytest.mark.asyncio
    async def test_open_without_stop_switch(self):
        cover = _make_pulse_cover()
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
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
        cover = _make_pulse_cover(stop_switch="switch.stop")
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
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


# ---------------------------------------------------------------------------
# _send_close
# ---------------------------------------------------------------------------


class TestPulseModeSendClose:
    @pytest.mark.asyncio
    async def test_close_without_stop_switch(self):
        cover = _make_pulse_cover()
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
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
        cover = _make_pulse_cover(stop_switch="switch.stop")
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
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


# ---------------------------------------------------------------------------
# _send_stop
# ---------------------------------------------------------------------------


class TestPulseModeSendStop:
    @pytest.mark.asyncio
    async def test_stop_without_stop_switch(self):
        cover = _make_pulse_cover()
        await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_with_stop_switch_pulses_it(self):
        cover = _make_pulse_cover(stop_switch="switch.stop")
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.stop"),
            # after pulse sleep
            _ha("turn_off", "switch.stop"),
        ]
