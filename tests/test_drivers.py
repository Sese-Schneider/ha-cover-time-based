"""Unit tests for the wrapped-cover actuation drivers."""

import pytest
from unittest.mock import AsyncMock, MagicMock

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

    driver = NativePositionDriver(cover)
    await driver.command_move(59.6, "open", False)

    cover._require_movement_target_available.assert_called_once_with("cover.inner")
    cover._call_set_cover_position.assert_awaited_once_with(60)


@pytest.mark.asyncio
async def test_timed_command_move_delegates_to_base():
    # The timed driver runs the base CoverTimeBased._command_position_move
    # against the cover. We assert it calls through to that exact unbound
    # method with the same args (full behaviour is covered by the existing
    # wrapped-cover integration tests).
    from custom_components.cover_time_based import drivers as drivers_mod

    cover = MagicMock()
    called = {}

    async def fake_base(self, target, command, already):
        called["args"] = (self, target, command, already)

    drivers_mod.CoverTimeBased._command_position_move = fake_base
    try:
        driver = TimedPositionDriver(cover)
        await driver.command_move(40, "close", True)
    finally:
        del drivers_mod.CoverTimeBased._command_position_move

    assert called["args"] == (cover, 40, "close", True)
