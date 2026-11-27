"""Unit tests for the wrapped-cover actuation drivers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.cover_time_based.drivers import (
    NativePositionDriver,
    TimedPositionDriver,
)


def test_holds_itself_flags():
    assert NativePositionDriver(MagicMock()).holds_itself is True
    assert TimedPositionDriver(MagicMock()).holds_itself is False


@pytest.mark.asyncio
async def test_native_command_move_forwards_rounded_set_position():
    cover = MagicMock()
    cover._cover_entity_id = "cover.inner"
    cover._call_set_cover_position = AsyncMock()
    cover._require_movement_target_available = MagicMock()
    cover._triggered_externally = False

    driver = NativePositionDriver(cover)
    await driver.command_move(59.6, "open", False)

    cover._require_movement_target_available.assert_called_once_with("cover.inner")
    cover._call_set_cover_position.assert_awaited_once_with(60)


@pytest.mark.asyncio
async def test_native_command_move_forwards_nothing_on_a_tracked_move():
    """The device is already moving by itself; only the tracker follows."""
    cover = MagicMock()
    cover._cover_entity_id = "cover.inner"
    cover._call_set_cover_position = AsyncMock()
    cover._triggered_externally = True

    driver = NativePositionDriver(cover)
    await driver.command_move(40, "close", False)

    cover._call_set_cover_position.assert_not_awaited()
    cover._note_travel_motor_driven.assert_called_once_with("close")
