import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.components.cover import CoverEntityFeature

from custom_components.cover_time_based.cover_single_button_mode import (
    SingleButtonModeCover,
)
from custom_components.cover_time_based.single_button_cycle import Phase


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


def test_tilt_absent_from_supported_features_even_if_tilt_strategy_present():
    # supports_tilt=False alone must gate the tilt bits out of
    # supported_features. _make_sb_cover() already passes tilt_strategy=None,
    # which would suppress tilt independently of the flag (via
    # _has_tilt_support()'s `_tilt_strategy is not None` check) and so isn't a
    # real test of the flag itself. Force a tilt_strategy + tilt_calc onto
    # the instance -- as if tilt were somehow configured -- to prove
    # supports_tilt=False is still what blocks it.
    cover = _make_sb_cover()
    cover._tilt_strategy = object()
    cover.tilt_calc = object()
    tilt_bits = (
        CoverEntityFeature.OPEN_TILT
        | CoverEntityFeature.CLOSE_TILT
        | CoverEntityFeature.STOP_TILT
        | CoverEntityFeature.SET_TILT_POSITION
    )
    assert cover.supported_features & tilt_bits == 0
    assert cover.supported_features & CoverEntityFeature.SET_POSITION


def test_only_button_required():
    cover = _make_sb_cover()
    assert cover._are_entities_configured() is True
    cover._open_switch_entity_id = None
    assert cover._are_entities_configured() is False


def test_self_stops_at_endpoints():
    assert _make_sb_cover()._self_stops_at_endpoints() is True


def test_initial_phase_is_at_closed():
    assert _make_sb_cover()._phase is Phase.AT_CLOSED


@pytest.mark.asyncio
async def test_external_state_change_ignored():
    cover = _make_sb_cover()
    # Must not raise and must not call any service.
    await cover._handle_external_state_change("switch.button", None, MagicMock())
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


def _presses(cover):
    """Count turn_on calls on the button (one per press)."""
    return [
        c
        for c in cover.hass.services.async_call.call_args_list
        if c == call("homeassistant", "turn_on", {"entity_id": "switch.button"}, False)
    ]


class TestSendCommands:
    @pytest.mark.asyncio
    async def test_open_from_closed_is_one_press_moving_up(self):
        cover = _make_sb_cover()
        cover._phase = Phase.AT_CLOSED
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_open()
            await _drain(cover)
        assert len(_presses(cover)) == 1
        assert cover._phase is Phase.MOVING_UP

    @pytest.mark.asyncio
    async def test_open_from_stopped_after_up_is_three_press_nudge(self):
        cover = _make_sb_cover()
        cover._phase = Phase.STOPPED_AFTER_UP
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_open()
            await _drain(cover)
        assert len(_presses(cover)) == 3
        assert cover._phase is Phase.MOVING_UP

    @pytest.mark.asyncio
    async def test_open_when_already_moving_up_is_noop(self):
        cover = _make_sb_cover()
        cover._phase = Phase.MOVING_UP
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_open()
            await _drain(cover)
        assert len(_presses(cover)) == 0
        assert cover._phase is Phase.MOVING_UP

    @pytest.mark.asyncio
    async def test_stop_while_moving_up_is_one_press_stopped_after_up(self):
        cover = _make_sb_cover()
        cover._phase = Phase.MOVING_UP
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_stop()
            await _drain(cover)
        assert len(_presses(cover)) == 1
        assert cover._phase is Phase.STOPPED_AFTER_UP

    @pytest.mark.asyncio
    async def test_close_from_open_is_one_press_moving_down(self):
        cover = _make_sb_cover()
        cover._phase = Phase.AT_OPEN
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_close()
            await _drain(cover)
        assert len(_presses(cover)) == 1
        assert cover._phase is Phase.MOVING_DOWN

    @pytest.mark.asyncio
    async def test_uses_direction_change_delay_between_presses(self):
        # pulse_time deliberately != DIRECTION_CHANGE_DELAY (1.0) so the
        # inter-press gaps are distinguishable from the pulse-off sleeps.
        cover = _make_sb_cover(pulse_time=0.3)
        cover._phase = Phase.STOPPED_AFTER_UP  # 3-press nudge
        gaps = []
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new=AsyncMock(side_effect=lambda d: gaps.append(d)),
        ):
            await cover._send_open()
            await _drain(cover)
        # Two inter-press gaps of DIRECTION_CHANGE_DELAY; three pulse-off
        # sleeps of pulse_time (0.3).
        from custom_components.cover_time_based.const import DIRECTION_CHANGE_DELAY

        assert gaps.count(DIRECTION_CHANGE_DELAY) == 2
        assert gaps.count(0.3) == 3

    @pytest.mark.asyncio
    async def test_raw_open_command_presses_the_button(self):
        cover = _make_sb_cover()
        cover._phase = Phase.AT_CLOSED
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._raw_direction_command("open")
            await _drain(cover)
        assert len(_presses(cover)) == 1


class TestEndpointReanchor:
    def test_immediate_anchor_when_no_runon(self):
        cover = _make_sb_cover()
        cover._endpoint_runon_time = None
        cover._phase = Phase.MOVING_UP
        cover._on_endpoint_reached(100)
        assert cover._phase is Phase.AT_OPEN

    def test_immediate_anchor_closed(self):
        cover = _make_sb_cover()
        cover._endpoint_runon_time = 0
        cover._phase = Phase.MOVING_DOWN
        cover._on_endpoint_reached(0)
        assert cover._phase is Phase.AT_CLOSED

    @pytest.mark.asyncio
    async def test_settle_margin_defers_anchor(self):
        cover = _make_sb_cover()
        cover._endpoint_runon_time = 2.0
        cover._phase = Phase.MOVING_UP
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            cover._on_endpoint_reached(100)
            # Phase still moving until the margin elapses.
            assert cover._phase is Phase.MOVING_UP
            await _drain(cover)
        assert cover._phase is Phase.AT_OPEN


class TestResync:
    @pytest.mark.asyncio
    async def test_resync_closed(self):
        cover = _make_sb_cover()
        cover._phase = Phase.MOVING_UP
        cover.async_write_ha_state = MagicMock()
        cover._async_persist_position = AsyncMock()
        cover.travel_calc.set_position(70)
        await cover.async_resync("closed")
        assert cover._phase is Phase.AT_CLOSED
        assert cover.travel_calc.current_position() == 0
        cover._async_persist_position.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resync_open(self):
        cover = _make_sb_cover()
        cover.async_write_ha_state = MagicMock()
        cover._async_persist_position = AsyncMock()
        await cover.async_resync("open")
        assert cover._phase is Phase.AT_OPEN
        assert cover.travel_calc.current_position() == 100

    @pytest.mark.asyncio
    async def test_resync_rejects_unknown(self):
        cover = _make_sb_cover()
        with pytest.raises(ValueError):
            await cover.async_resync("halfway")
