"""External events on an unconfigured cover: only the move is refused, quietly.

A wall-switch press or the wrapped device moving on its own arrives as a state
event, not a service call, so a refusal raised there has no caller to report to
and would land in Home Assistant's log as an error. The event itself is still
handled: the switch-mode relay interlock and a wrapped cover's position resync
run as usual, and only the move they lead to is refused, in the debug log.
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import STATE_CLOSED, STATE_OPEN, STATE_OPENING
from homeassistant.exceptions import HomeAssistantError

from custom_components.cover_time_based.cover import (
    CONTROL_MODE_PULSE,
    CONTROL_MODE_SWITCH,
    CONTROL_MODE_TOGGLE,
    CONTROL_MODE_TOGGLE_OPPOSITE,
)
from tests.helpers import relay_calls, stub_switches

UNCONFIGURED_TIMES = pytest.mark.parametrize(
    ("travel_time_close", "travel_time_open"),
    [(None, None), (5.0, None), (None, 5.0)],
    ids=["no-times", "close-only", "open-only"],
)

CONTROL_MODES = pytest.mark.parametrize(
    "control_mode",
    [
        CONTROL_MODE_SWITCH,
        CONTROL_MODE_TOGGLE,
        CONTROL_MODE_TOGGLE_OPPOSITE,
        CONTROL_MODE_PULSE,
    ],
)

_CALL_LATER = "custom_components.cover_time_based.cover_echo_filter.async_call_later"
_LOGGER_NAME = "custom_components.cover_time_based.cover_base"


def _state(value, attributes=None):
    return SimpleNamespace(state=value, attributes=attributes or {})


def _state_event(entity_id, old_state, new_state, new_attributes=None):
    event = MagicMock()
    event.data = {
        "entity_id": entity_id,
        "old_state": _state(old_state),
        "new_state": _state(new_state, new_attributes),
    }
    return event


def _assert_move_refused(caplog):
    assert any(
        "move refused — cover not configured" in m and "missing travel times" in m
        for m in caplog.messages
    ), caplog.messages


@CONTROL_MODES
@UNCONFIGURED_TIMES
@pytest.mark.asyncio
async def test_wall_switch_press_is_refused_quietly(
    caplog, make_cover, control_mode, travel_time_close, travel_time_open
):
    kwargs = {}
    if control_mode == CONTROL_MODE_PULSE:
        kwargs["stop_switch"] = "switch.stop"
    cover = make_cover(
        control_mode=control_mode,
        travel_time_close=travel_time_close,
        travel_time_open=travel_time_open,
        **kwargs,
    )
    assert cover._get_missing_configuration() == ["travel times"]
    # All relays read off: switch mode's interlock has nothing to turn off, so
    # no mode sends anything to the hardware for this press.
    stub_switches(cover)

    with (
        caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME),
        patch.object(cover, "async_write_ha_state"),
    ):
        await cover._async_switch_state_changed(
            _state_event("switch.close", "off", "on")
        )

    _assert_move_refused(caplog)
    assert not cover.travel_calc.is_traveling()
    assert relay_calls(cover) == []


@UNCONFIGURED_TIMES
@pytest.mark.asyncio
async def test_wrapped_cover_moving_is_refused_quietly(
    caplog, make_cover, travel_time_close, travel_time_open
):
    cover = make_cover(
        cover_entity_id="cover.inner",
        travel_time_close=travel_time_close,
        travel_time_open=travel_time_open,
    )
    assert cover._get_missing_configuration() == ["travel times"]

    with (
        caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME),
        patch.object(cover, "async_write_ha_state"),
    ):
        await cover._async_switch_state_changed(
            _state_event("cover.inner", STATE_CLOSED, STATE_OPENING)
        )

    _assert_move_refused(caplog)
    assert not cover.travel_calc.is_traveling()
    assert relay_calls(cover) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("pressed", "opposite"),
    [
        ("switch.open", "switch.close"),
        ("switch.close", "switch.open"),
        ("switch.tilt_open", "switch.tilt_close"),
        ("switch.tilt_close", "switch.tilt_open"),
    ],
)
async def test_switch_mode_interlock_still_runs(caplog, make_cover, pressed, opposite):
    """A latched relay turned ON by hand must still turn its opposite OFF, so
    both directions are never energized at once, before the move itself is
    refused."""
    cover = make_cover(
        travel_time_close=None,
        travel_time_open=None,
        tilt_mode="dual_motor",
        tilt_time_open=2,
        tilt_time_close=2,
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
    )
    assert cover._get_missing_configuration() == ["travel times"]
    stub_switches(cover, on=(pressed, opposite))

    with (
        caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME),
        patch(_CALL_LATER, return_value=MagicMock()),
        patch.object(cover, "async_write_ha_state"),
    ):
        await cover._async_switch_state_changed(_state_event(pressed, "off", "on"))

    assert relay_calls(cover) == [("turn_off", opposite)]
    _assert_move_refused(caplog)
    assert not cover.travel_calc.is_traveling()
    assert not cover.tilt_calc.is_traveling()


@pytest.mark.asyncio
async def test_wrapped_cover_settling_still_resyncs_position(make_cover):
    """The wrapped cover reporting where it stopped re-anchors the tracker even
    before the cover is configured."""
    cover = make_cover(
        cover_entity_id="cover.inner", travel_time_close=None, travel_time_open=None
    )
    cover.travel_calc.set_position(50)
    event = _state_event(
        "cover.inner", STATE_OPENING, STATE_OPEN, {"current_position": 75}
    )
    cover.hass.states.get.return_value = event.data["new_state"]

    with patch.object(cover, "async_write_ha_state"):
        await cover._async_switch_state_changed(event)

    assert cover.travel_calc.current_position() == 75


@pytest.mark.asyncio
async def test_own_echo_is_still_counted_off(make_cover):
    """Calibration runs on an unconfigured cover and marks its own relay echoes;
    those must still be consumed, or a stale count would swallow a real press
    once the cover is configured."""
    cover = make_cover(
        control_mode=CONTROL_MODE_PULSE,
        stop_switch="switch.stop",
        travel_time_close=None,
        travel_time_open=None,
    )
    cover._pending_switch["switch.open"] = 1

    with patch.object(cover, "async_write_ha_state"):
        await cover._async_switch_state_changed(
            _state_event("switch.open", "off", "on")
        )

    assert cover._pending_switch.get("switch.open", 0) == 0


@pytest.mark.asyncio
async def test_service_call_still_raises_the_refusal(make_cover):
    """Only the event path is quiet; a service call still gets the refusal."""
    cover = make_cover(travel_time_close=None, travel_time_open=None)

    with pytest.raises(
        HomeAssistantError,
        match=(
            r"^Cover not configured: missing travel times\. Please configure"
            r" using the Cover Time Based card\.$"
        ),
    ):
        await cover.async_open_cover()
