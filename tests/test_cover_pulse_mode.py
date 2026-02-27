"""Tests for PulseModeCover._send_open/close/stop.

Each test verifies the exact sequence of homeassistant.turn_on/turn_off
service calls for the momentary pulse mode.

Pulse completion (sleep + turn_off) now runs in background tasks. Tests
await those tasks to verify the full call sequence.
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
    tilt_open_switch=None,
    tilt_close_switch=None,
    tilt_stop_switch=None,
):
    """Create a PulseModeCover wired to a mock hass."""
    cover = PulseModeCover(
        device_id="test_pulse",
        name="Test Pulse",
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
        tilt_open_switch=tilt_open_switch,
        tilt_close_switch=tilt_close_switch,
        tilt_stop_switch=tilt_stop_switch,
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


async def _drain_tasks(cover):
    """Await all background tasks created during a send call."""
    for task in cover._test_tasks:
        await task
    cover._test_tasks.clear()


async def _cancel_tasks(cover):
    """Cancel all pending background tasks (for tests that don't drain)."""
    for task in cover._test_tasks:
        if not task.done():
            task.cancel()
    if cover._test_tasks:
        await asyncio.gather(*cover._test_tasks, return_exceptions=True)
    cover._test_tasks.clear()


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
            await _drain_tasks(cover)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
            # pulse completion (background)
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
            await _drain_tasks(cover)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
            _ha("turn_off", "switch.stop"),
            # pulse completion (background)
            _ha("turn_off", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_open_returns_before_pulse_completion(self):
        """Verify _send_open returns immediately after the ON edge."""
        cover = _make_pulse_cover()
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_open()

        # Only synchronous calls made — turn_off (pulse cleanup) is background
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]
        await _cancel_tasks(cover)


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
            await _drain_tasks(cover)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
            # pulse completion (background)
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
            await _drain_tasks(cover)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
            _ha("turn_off", "switch.stop"),
            # pulse completion (background)
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
            await _drain_tasks(cover)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.stop"),
            # pulse completion (background)
            _ha("turn_off", "switch.stop"),
        ]

    @pytest.mark.asyncio
    async def test_stop_returns_before_pulse_completion(self):
        """Verify _send_stop returns immediately after the stop ON edge."""
        cover = _make_pulse_cover(stop_switch="switch.stop")
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_stop()

        # Only synchronous calls — stop pulse cleanup is background
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.stop"),
        ]
        await _cancel_tasks(cover)


# ---------------------------------------------------------------------------
# _send_tilt_open / _send_tilt_close / _send_tilt_stop
# ---------------------------------------------------------------------------


class TestPulseModeSendTiltOpen:
    @pytest.mark.asyncio
    async def test_tilt_open_pulses_tilt_open_switch(self):
        cover = _make_pulse_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_tilt_open()
            await _drain_tasks(cover)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.tilt_close"),
            _ha("turn_on", "switch.tilt_open"),
            # pulse completion (background)
            _ha("turn_off", "switch.tilt_open"),
        ]


class TestPulseModeSendTiltClose:
    @pytest.mark.asyncio
    async def test_tilt_close_pulses_tilt_close_switch(self):
        cover = _make_pulse_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_tilt_close()
            await _drain_tasks(cover)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.tilt_open"),
            _ha("turn_on", "switch.tilt_close"),
            # pulse completion (background)
            _ha("turn_off", "switch.tilt_close"),
        ]


class TestPulseModeSendTiltStop:
    @pytest.mark.asyncio
    async def test_tilt_stop_without_stop_switch(self):
        cover = _make_pulse_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        await cover._send_tilt_stop()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.tilt_open"),
            _ha("turn_off", "switch.tilt_close"),
        ]

    @pytest.mark.asyncio
    async def test_tilt_stop_with_stop_switch(self):
        cover = _make_pulse_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_tilt_stop()
            await _drain_tasks(cover)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.tilt_open"),
            _ha("turn_off", "switch.tilt_close"),
            _ha("turn_on", "switch.tilt_stop"),
            # pulse completion (background)
            _ha("turn_off", "switch.tilt_stop"),
        ]
