import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.cover_time_based.cover_single_button_mode import (
    SingleButtonModeCover,
)
from custom_components.cover_time_based.single_button_cycle import Action, Phase


def _make_sb_cover(button="switch.button", pulse_time=1.0, travel=30):
    cover = SingleButtonModeCover(
        device_id="test_sb",
        name="Test SB",
        tilt_strategy=None,
        travel_time_close=travel,
        travel_time_open=travel,
        tilt_time_close=None,
        tilt_time_open=None,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        endpoint_runon_time=None,
        min_movement_time=None,
        open_switch_entity_id=button,
        close_switch_entity_id=None,
        stop_switch_entity_id=None,
        pulse_time=pulse_time,
    )
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    created = []

    def create_task(coro):
        task = asyncio.ensure_future(coro)
        created.append(task)
        return task

    hass.async_create_task = create_task
    cover.hass = hass
    cover._test_tasks = created
    return cover


async def _drain(cover):
    # Drain repeatedly: sequences schedule further pulse tasks.
    while cover._test_tasks:
        task = cover._test_tasks.pop(0)
        await task


def test_supports_tilt_false():
    assert SingleButtonModeCover.supports_tilt is False


def test_only_button_required():
    cover = _make_sb_cover()
    assert cover._are_entities_configured() is True
    cover._open_switch_entity_id = None
    assert cover._are_entities_configured() is False


def test_self_stops_at_endpoints():
    assert _make_sb_cover()._self_stops_at_endpoints() is True


def test_initial_phase_is_at_closed():
    assert _make_sb_cover()._phase is Phase.AT_CLOSED


def test_external_state_change_ignored():
    cover = _make_sb_cover()
    # Must not raise and must not call any service.
    cover._handle_external_state_change("switch.button", None, MagicMock())
    cover.hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_pulse_button_turns_on_then_off():
    cover = _make_sb_cover(pulse_time=1.0)
    with patch(
        "custom_components.cover_time_based.cover_single_button_mode.sleep",
        new_callable=AsyncMock,
    ):
        await cover._pulse_button()
        await _drain(cover)
    assert cover.hass.services.async_call.call_args_list == [
        call("homeassistant", "turn_on", {"entity_id": "switch.button"}, False),
        call("homeassistant", "turn_off", {"entity_id": "switch.button"}, False),
    ]
