"""Tests for SwitchModeCover._send_open/close/stop.

Each test verifies the exact sequence of homeassistant.turn_on/turn_off
service calls for the latching relay (switch) mode.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, call

from custom_components.cover_time_based.cover_switch_mode import SwitchModeCover


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _make_switch_cover(
    open_switch="switch.open",
    close_switch="switch.close",
    stop_switch=None,
):
    """Create a SwitchModeCover wired to a mock hass."""
    cover = SwitchModeCover(
        device_id="test_switch",
        name="Test Switch",
        tilt_mode="none",
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


class TestSwitchModeSendOpen:
    @pytest.mark.asyncio
    async def test_open_without_stop_switch(self):
        cover = _make_switch_cover()
        await cover._send_open()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_open_with_stop_switch(self):
        cover = _make_switch_cover(stop_switch="switch.stop")
        await cover._send_open()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
            _ha("turn_off", "switch.stop"),
        ]


# ---------------------------------------------------------------------------
# _send_close
# ---------------------------------------------------------------------------


class TestSwitchModeSendClose:
    @pytest.mark.asyncio
    async def test_close_without_stop_switch(self):
        cover = _make_switch_cover()
        await cover._send_close()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_close_with_stop_switch(self):
        cover = _make_switch_cover(stop_switch="switch.stop")
        await cover._send_close()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
            _ha("turn_off", "switch.stop"),
        ]


# ---------------------------------------------------------------------------
# _send_stop
# ---------------------------------------------------------------------------


class TestSwitchModeSendStop:
    @pytest.mark.asyncio
    async def test_stop_without_stop_switch(self):
        cover = _make_switch_cover()
        await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_with_stop_switch(self):
        cover = _make_switch_cover(stop_switch="switch.stop")
        await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.stop"),
        ]
