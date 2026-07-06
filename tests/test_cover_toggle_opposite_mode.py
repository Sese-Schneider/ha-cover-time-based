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
from custom_components.cover_time_based.tilt_strategies.inline import InlineTilt


def _make_opposite_cover(
    open_switch="switch.open",
    close_switch="switch.close",
    stop_switch=None,
    tilt_open_switch=None,
    tilt_close_switch=None,
    tilt_stop_switch=None,
    relay_reports_off=True,
):
    # Set tilt times and strategy if tilt switches are provided
    tilt_time_close = 30 if tilt_open_switch or tilt_close_switch else None
    tilt_time_open = 30 if tilt_open_switch or tilt_close_switch else None
    tilt_strategy = InlineTilt() if tilt_open_switch or tilt_close_switch else None

    cover = ToggleOppositeModeCover(
        device_id="test_toggle_opposite",
        name="Test Toggle Opposite",
        tilt_strategy=tilt_strategy,
        travel_time_close=30,
        travel_time_open=30,
        tilt_time_close=tilt_time_close,
        tilt_time_open=tilt_time_open,
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


class TestOppositeExternalTravel:
    """Opposite press while moving stops; same-direction press continues."""

    @pytest.mark.asyncio
    async def test_external_close_while_opening_stops(self):
        cover = _make_opposite_cover()
        _all_relays_off(cover)
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER
        assert cover.travel_calc.is_traveling()

        cover._triggered_externally = True
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._handle_external_state_change("switch.close", "off", "on")
        finally:
            cover._triggered_externally = False

        # Motor already stopped physically; the integration only stops tracking
        # and fires NO relay of its own.
        assert not cover.travel_calc.is_traveling()
        assert cover.hass.services.async_call.await_count == 0
        await _cancel_tasks(cover)

    @pytest.mark.asyncio
    async def test_external_open_while_closing_stops(self):
        cover = _make_opposite_cover()
        _all_relays_off(cover)
        cover.travel_calc.set_position(100)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER
        assert cover.travel_calc.is_traveling()

        cover._triggered_externally = True
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._handle_external_state_change("switch.open", "off", "on")
        finally:
            cover._triggered_externally = False

        assert not cover.travel_calc.is_traveling()
        assert cover.hass.services.async_call.await_count == 0
        await _cancel_tasks(cover)

    @pytest.mark.asyncio
    async def test_external_open_while_opening_continues(self):
        """Same-direction press while moving is a no-op continuation."""
        cover = _make_opposite_cover()
        _all_relays_off(cover)
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        cover._triggered_externally = True
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._handle_external_state_change("switch.open", "off", "on")
        finally:
            cover._triggered_externally = False

        # Still opening; no relay fired.
        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._travel_to_position == 100
        assert cover.hass.services.async_call.await_count == 0
        await _cancel_tasks(cover)

    @pytest.mark.asyncio
    async def test_external_open_when_idle_starts_opening(self):
        cover = _make_opposite_cover()
        _all_relays_off(cover)
        cover.travel_calc.set_position(0)
        assert not cover.travel_calc.is_traveling()

        cover._triggered_externally = True
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._handle_external_state_change("switch.open", "off", "on")
        finally:
            cover._triggered_externally = False

        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._travel_to_position == 100
        await _cancel_tasks(cover)


class TestOppositeExternalTilt:
    @pytest.mark.asyncio
    async def test_external_tilt_close_while_tilt_opening_stops(self):
        cover = _make_opposite_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _all_relays_off(cover)
        cover.tilt_calc.set_position(0)
        cover.tilt_calc.start_travel(100)  # tilt opening (UP)
        assert cover.tilt_calc.is_opening()

        cover._triggered_externally = True
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_close", "off", "on"
                )
        finally:
            cover._triggered_externally = False

        assert not cover.tilt_calc.is_traveling()
        assert cover.hass.services.async_call.await_count == 0
        await _cancel_tasks(cover)

    @pytest.mark.asyncio
    async def test_external_tilt_open_while_tilt_opening_continues(self):
        cover = _make_opposite_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _all_relays_off(cover)
        cover.tilt_calc.set_position(0)
        cover.tilt_calc.start_travel(100)  # tilt opening (UP)
        assert cover.tilt_calc.is_opening()

        cover._triggered_externally = True
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_open", "off", "on"
                )
        finally:
            cover._triggered_externally = False

        assert cover.tilt_calc.is_traveling()
        assert cover.hass.services.async_call.await_count == 0
        await _cancel_tasks(cover)
