"""Tests for WrappedCoverTimeBased._send_open/close/stop.

Each test verifies that the correct cover.* service call is made.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from custom_components.cover_time_based.cover_wrapped import WrappedCoverTimeBased


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _make_wrapped_cover(cover_entity_id="cover.inner"):
    """Create a WrappedCoverTimeBased wired to a mock hass."""
    cover = WrappedCoverTimeBased(
        device_id="test_wrapped",
        name="Test Wrapped",
        travel_moves_with_tilt=False,
        travel_time_down=30,
        travel_time_up=30,
        tilt_time_down=None,
        tilt_time_up=None,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        endpoint_runon_time=None,
        min_movement_time=None,
        cover_entity_id=cover_entity_id,
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
    """Return the list of calls made on hass.services.async_call."""
    return mock.call_args_list


def _cover_svc(service, entity_id):
    """Shorthand for a cover domain service call."""
    return call("cover", service, {"entity_id": entity_id}, False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWrappedSendOpen:
    """_send_open delegates to cover.open_cover."""

    @pytest.mark.asyncio
    async def test_send_open(self):
        cover = _make_wrapped_cover()
        await cover._send_open()

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("open_cover", "cover.inner"),
        ]


class TestWrappedSendClose:
    """_send_close delegates to cover.close_cover."""

    @pytest.mark.asyncio
    async def test_send_close(self):
        cover = _make_wrapped_cover()
        await cover._send_close()

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("close_cover", "cover.inner"),
        ]


class TestWrappedSendStop:
    """_send_stop delegates to cover.stop_cover."""

    @pytest.mark.asyncio
    async def test_send_stop(self):
        cover = _make_wrapped_cover()
        await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("stop_cover", "cover.inner"),
        ]


class TestWrappedViaHandleCommand:
    """Integration test: _async_handle_command routes through _send_* correctly."""

    @pytest.mark.asyncio
    async def test_handle_command_open(self):
        from homeassistant.const import SERVICE_OPEN_COVER

        cover = _make_wrapped_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("open_cover", "cover.inner"),
        ]

    @pytest.mark.asyncio
    async def test_handle_command_close(self):
        from homeassistant.const import SERVICE_CLOSE_COVER

        cover = _make_wrapped_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("close_cover", "cover.inner"),
        ]

    @pytest.mark.asyncio
    async def test_handle_command_stop(self):
        from homeassistant.const import SERVICE_STOP_COVER

        cover = _make_wrapped_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("stop_cover", "cover.inner"),
        ]
