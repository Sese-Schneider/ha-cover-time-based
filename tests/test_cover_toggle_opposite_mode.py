"""Tests for ToggleOppositeModeCover.

Opposite-button hardware halts a moving cover with a pulse on the OPPOSITE
direction relay (not the same one), and treats a same-direction press while
moving as a continuation. Stop therefore pulses the opposite of the last-used
direction.
"""

import asyncio
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from custom_components.cover_time_based.cover_toggle_opposite_mode import (
    ToggleOppositeModeCover,
)


def _make_opposite_cover(
    open_switch="switch.open",
    close_switch="switch.close",
    stop_switch=None,
    tilt_open_switch=None,
    tilt_close_switch=None,
    tilt_stop_switch=None,
    relay_reports_off=True,
):
    cover = ToggleOppositeModeCover(
        device_id="test_toggle_opposite",
        name="Test Toggle Opposite",
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
        tilt_open_switch=tilt_open_switch,
        tilt_close_switch=tilt_close_switch,
        tilt_stop_switch=tilt_stop_switch,
        relay_reports_off=relay_reports_off,
    )
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    created_tasks = []

    def create_task(coro):
        task = asyncio.ensure_future(coro)
        created_tasks.append(task)
        return task

    hass.async_create_task = create_task
    cover.hass = hass
    cover._test_tasks = created_tasks
    return cover


async def _cancel_tasks(cover):
    for task in cover._test_tasks:
        if not task.done():
            task.cancel()
    if cover._test_tasks:
        await asyncio.gather(*cover._test_tasks, return_exceptions=True)
    cover._test_tasks.clear()


def _calls(mock):
    return mock.call_args_list


def _ha(service, entity_id):
    return call("homeassistant", service, {"entity_id": entity_id}, False)


def _all_relays_off(cover):
    cover.hass.states.get = MagicMock(
        side_effect=lambda eid: SimpleNamespace(state="off")
    )


class TestOppositeSendStop:
    @pytest.mark.asyncio
    async def test_stop_after_open_pulses_close_switch(self):
        cover = _make_opposite_cover()
        _all_relays_off(cover)
        cover._last_command = SERVICE_OPEN_COVER
        await cover._send_stop()
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_stop_after_close_pulses_open_switch(self):
        cover = _make_opposite_cover()
        _all_relays_off(cover)
        cover._last_command = SERVICE_CLOSE_COVER
        await cover._send_stop()
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_with_no_last_command_does_nothing(self):
        cover = _make_opposite_cover()
        cover._last_command = None
        await cover._send_stop()
        assert _calls(cover.hass.services.async_call) == []


class TestOppositeSendTiltStop:
    @pytest.mark.asyncio
    async def test_tilt_stop_after_open_pulses_tilt_close(self):
        cover = _make_opposite_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _all_relays_off(cover)
        cover._last_tilt_direction = "open"
        await cover._send_tilt_stop()
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.tilt_close"),
        ]
        assert cover._last_tilt_direction is None

    @pytest.mark.asyncio
    async def test_tilt_stop_after_close_pulses_tilt_open(self):
        cover = _make_opposite_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _all_relays_off(cover)
        cover._last_tilt_direction = "close"
        await cover._send_tilt_stop()
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.tilt_open"),
        ]
        assert cover._last_tilt_direction is None

    @pytest.mark.asyncio
    async def test_tilt_stop_no_last_direction_does_nothing(self):
        cover = _make_opposite_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        cover._last_tilt_direction = None
        await cover._send_tilt_stop()
        assert _calls(cover.hass.services.async_call) == []
        assert cover._last_tilt_direction is None
