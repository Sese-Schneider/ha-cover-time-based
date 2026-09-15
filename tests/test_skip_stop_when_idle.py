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

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.cover_time_based.cover import (
    CONTROL_MODE_PULSE,
    CONTROL_MODE_SWITCH,
)


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
