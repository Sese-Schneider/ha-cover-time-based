"""The skip_stop_when_idle option (issue #251).

When set on a wrapped or pulse cover, a stop issued from HA while the cover is
already stopped is not forwarded to the hardware. This stops shutters with a
hardware "my"/favourite preset (Somfy RTS and similar) from drifting to that
preset every time the HA stop button is pressed on an idle cover.

The option must:
  - suppress the hardware stop only when the cover was idle (a stop while
    moving still halts the motor),
  - do nothing on modes that need the redundant stop (switch/toggle/single
    button), where a stop de-energises a latched relay or is a genuine tap,
  - be off by default (existing behaviour unchanged).
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.cover_time_based.cover import (
    CONTROL_MODE_PULSE,
    CONTROL_MODE_SWITCH,
)
from tests.helpers import stub_switches


async def _call_stop(cover):
    with patch.object(cover, "async_write_ha_state"):
        await cover.async_stop_cover()


class TestSkipStopWhenIdle:
    @pytest.mark.asyncio
    async def test_pulse_idle_flag_on_suppresses_hardware_stop(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        cover._skip_stop_when_idle = True
        cover.travel_calc.set_position(50)  # idle

        with patch.object(cover, "_send_stop", new_callable=AsyncMock) as send_stop:
            await _call_stop(cover)

        send_stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_pulse_idle_flag_off_still_sends_hardware_stop(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        cover._skip_stop_when_idle = False
        cover.travel_calc.set_position(50)  # idle

        with patch.object(cover, "_send_stop", new_callable=AsyncMock) as send_stop:
            await _call_stop(cover)

        send_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_pulse_moving_flag_on_still_sends_hardware_stop(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        cover._skip_stop_when_idle = True
        cover.travel_calc.set_position(100)
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()
        assert cover.travel_calc.is_traveling()

        with patch.object(cover, "_send_stop", new_callable=AsyncMock) as send_stop:
            await _call_stop(cover)

        send_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_wrapped_idle_flag_on_suppresses_hardware_stop(self, make_cover):
        cover = make_cover(cover_entity_id="cover.real")
        cover._skip_stop_when_idle = True
        cover.travel_calc.set_position(50)  # idle

        with patch.object(cover, "_send_stop", new_callable=AsyncMock) as send_stop:
            await _call_stop(cover)

        send_stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_switch_idle_flag_on_still_sends_hardware_stop(self, make_cover):
        """Switch mode ignores the flag: the stop de-energises a latched relay."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH)
        cover._skip_stop_when_idle = True
        cover.travel_calc.set_position(50)  # idle

        with patch.object(cover, "_send_stop", new_callable=AsyncMock) as send_stop:
            await _call_stop(cover)

        send_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_pulse_stop_in_startup_delay_still_sends_hardware_stop(
        self, make_cover
    ):
        """A stop during the startup-delay window must still halt the motor: the
        move is in flight even though travel_calc has not started ticking."""
        cover = make_cover(
            control_mode=CONTROL_MODE_PULSE,
            stop_switch="switch.stop",
            travel_startup_delay=20.0,
        )
        cover._skip_stop_when_idle = True
        cover.travel_calc.set_position(100)
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()
        assert cover._startup_delay_task is not None
        assert not cover.travel_calc.is_traveling()  # still in the delay window

        with patch.object(cover, "_send_stop", new_callable=AsyncMock) as send_stop:
            await _call_stop(cover)

        send_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_wrapped_stop_in_startup_delay_still_sends_hardware_stop(
        self, make_cover
    ):
        cover = make_cover(cover_entity_id="cover.real", travel_startup_delay=20.0)
        cover._skip_stop_when_idle = True
        cover.travel_calc.set_position(100)
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()
        assert cover._startup_delay_task is not None
        assert not cover.travel_calc.is_traveling()

        with patch.object(cover, "_send_stop", new_callable=AsyncMock) as send_stop:
            await _call_stop(cover)

        send_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_pulse_stop_after_open_at_endpoint_resync_is_suppressed(
        self, make_cover
    ):
        """An open issued while already at 100% is a silent resync: it leaves
        _last_command set on an idle, self-stopping cover without the tracker
        travelling. A following stop must still be suppressed (the cover is
        idle) — the guard keys on the in-flight signals, not _last_command."""
        cover = make_cover(
            control_mode=CONTROL_MODE_PULSE,
            stop_switch="switch.stop",
            send_endpoint_stop=False,  # self-stops at endpoints
        )
        stub_switches(cover)
        cover.async_write_ha_state = lambda: None
        cover._skip_stop_when_idle = True
        cover.travel_calc.set_position(100)  # already open
        await cover.async_open_cover()
        await asyncio.sleep(0)
        assert not cover.travel_calc.is_traveling()  # idle after the resync
        assert cover._last_command is not None  # but the command lingers

        with patch.object(cover, "_send_stop", new_callable=AsyncMock) as send_stop:
            await _call_stop(cover)

        send_stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_pulse_stop_during_relay_feedback_wait_still_sends_hardware_stop(
        self, make_cover
    ):
        """A stop while the cover is parked on a relay-feedback confirmation
        (wait_for_relay_feedback) must still halt the motor — the move is in
        flight though travel_calc has not started."""
        cover = make_cover(
            control_mode=CONTROL_MODE_PULSE,
            stop_switch="switch.stop",
            wait_for_relay_feedback=True,
            travel_time_open=30,
            travel_time_close=30,
        )
        stub_switches(cover)
        cover.async_write_ha_state = lambda: None
        cover._skip_stop_when_idle = True
        cover.travel_calc.set_position(100)
        await cover.async_close_cover()
        await asyncio.sleep(0)
        assert cover._feedback_wait_entity is not None  # parked on the echo
        assert not cover.travel_calc.is_traveling()

        with patch.object(cover, "_send_stop", new_callable=AsyncMock) as send_stop:
            await _call_stop(cover)

        send_stop.assert_called_once()
