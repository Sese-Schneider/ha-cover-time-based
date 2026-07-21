"""Stopping tilt-motor movements — audit findings core-C1a/C1b."""
import pytest
from unittest.mock import patch


def _tilt_switch_calls(cover, start=0):
    calls = cover.hass.services.async_call.call_args_list[start:]
    return [
        (c[0][1], c[0][2].get("entity_id"))
        for c in calls
        if c[0][2].get("entity_id") in ("switch.tilt_open", "switch.tilt_close")
    ]


DUAL = dict(
    tilt_time_close=5.0, tilt_time_open=5.0, tilt_mode="dual_motor",
    tilt_open_switch="switch.tilt_open", tilt_close_switch="switch.tilt_close",
)


@pytest.mark.asyncio
async def test_stop_cover_releases_plain_tilt_motor_move(make_cover):
    """A user stop during a plain dual-motor tilt move must turn the tilt relay off."""
    cover = make_cover(**DUAL)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(30)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(80)
        assert cover.tilt_calc.is_traveling() and cover._moving_tilt_motor
        n = len(cover.hass.services.async_call.call_args_list)
        await cover.async_stop_cover()
    offs = [c for c in _tilt_switch_calls(cover, n) if c[0] == "turn_off"]
    assert offs, "stop must de-energize the running tilt relay"


@pytest.mark.asyncio
async def test_stop_cover_tilt_stops_tilt_move(make_cover):
    """cover.stop_cover_tilt must actually stop tilt (STOP_TILT is advertised)."""
    cover = make_cover(**DUAL)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(30)
    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(80)
        n = len(cover.hass.services.async_call.call_args_list)
        await cover.async_stop_cover_tilt()
    assert not cover.tilt_calc.is_traveling()
    offs = [c for c in _tilt_switch_calls(cover, n) if c[0] == "turn_off"]
    assert offs
