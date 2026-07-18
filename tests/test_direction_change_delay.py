"""Tests for the configurable direction-change (stop->reverse settle) delay.

Reversing a moving cover means stop, settle, then drive the new direction. The
settle gap must outlast the motor's stop-settle time, or the reverse command is
ignored while the position tracker keeps advancing (issue #153 follow-up: the
blind stays put, the entity ticks on to the target). Motors differ, so the gap
is configurable; it defaults to the historical 1.0s.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
)

from custom_components.cover_time_based.const import CONF_DIRECTION_CHANGE_DELAY
from custom_components.cover_time_based.cover import (
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_CONTROL_MODE,
    CONF_DEFAULTS,
    CONF_DEVICES,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONTROL_MODE_SWITCH,
    CONTROL_MODE_TOGGLE_OPPOSITE,
    _create_cover_from_options,
    devices_from_config,
)

SLEEP = "custom_components.cover_time_based.cover_base.sleep"


def _switch_options(**extra):
    return {
        CONF_CONTROL_MODE: CONTROL_MODE_SWITCH,
        CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
        CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
        **extra,
    }


@pytest.mark.asyncio
async def test_direction_change_delay_uses_configured_value(make_cover):
    """A configured settle gap is what the reversal waits for."""
    cover = make_cover(direction_change_delay=2.5)
    with patch(SLEEP, new_callable=AsyncMock) as slept:
        await cover._direction_change_delay()
    slept.assert_awaited_once_with(2.5)


@pytest.mark.asyncio
async def test_direction_change_delay_defaults_to_one_second(make_cover):
    """Unset keeps the historical 1.0s, so existing covers are unaffected."""
    cover = make_cover()
    with patch(SLEEP, new_callable=AsyncMock) as slept:
        await cover._direction_change_delay()
    slept.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_explicit_none_in_options_falls_back_to_the_default():
    """An explicit None must not reach sleep().

    ``options.get(key, default)`` only substitutes the default for a *missing*
    key, so a present-but-None value is handed straight through. Resolving it
    at the boundary alone is therefore not enough; without the entity-side
    fallback this raises TypeError from sleep(None) on every reversal.
    """
    cover = _create_cover_from_options(
        _switch_options(**{CONF_DIRECTION_CHANGE_DELAY: None}),
        device_id="test",
        name="Test",
    )
    with patch(SLEEP, new_callable=AsyncMock) as slept:
        await cover._direction_change_delay()
    slept.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_yaml_defaults_block_may_null_the_delay():
    """The live route by which an explicit None reaches the entity.

    The YAML ``defaults:`` block accepts null, and ``_get_value`` returns it
    verbatim into options. (The card cannot produce this — ws_update_config
    pops the key on null — so this is the path that keeps the entity-side
    fallback load-bearing.)
    """
    config = {
        CONF_DEFAULTS: {CONF_DIRECTION_CHANGE_DELAY: None},
        CONF_DEVICES: {
            "blind1": {
                "name": "Living Room",
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
            },
        },
    }
    cover = devices_from_config(config)[0]
    with patch(SLEEP, new_callable=AsyncMock) as slept:
        await cover._direction_change_delay()
    slept.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_zero_is_preserved_as_no_settle_gap():
    """0 is a legitimate value and must not be coerced to the default."""
    cover = _create_cover_from_options(
        _switch_options(**{CONF_DIRECTION_CHANGE_DELAY: 0}),
        device_id="test",
        name="Test",
    )
    with patch(SLEEP, new_callable=AsyncMock) as slept:
        await cover._direction_change_delay()
    slept.assert_awaited_once_with(0)


@pytest.mark.asyncio
async def test_set_position_reversal_settles_for_the_configured_gap(make_cover):
    """Regression guard for issue #153.

    Reversing mid-travel via set_position (opening, then a lower target) must
    wait the configured settle gap between the stop and the reverse command.
    With the old hardcoded 1.0s the reverse landed while the motor was still
    coming to rest, so the cover stayed put while the tracker ran on.
    """
    cover = make_cover(
        control_mode=CONTROL_MODE_TOGGLE_OPPOSITE, direction_change_delay=2.5
    )
    cover.hass.states.get = MagicMock(
        side_effect=lambda eid: SimpleNamespace(state="off")
    )

    cover.travel_calc.set_position(40)
    cover.travel_calc.start_travel_up()
    cover._last_command = SERVICE_OPEN_COVER

    # Record commands and sleeps on one timeline: the gap has to land *between*
    # the stop and the reverse. Asserting only that sleep(2.5) happened would
    # still pass if the settle were awaited after the reverse was already sent,
    # which is exactly the ordering the fix depends on.
    events = []
    real_handle = cover._async_handle_command

    async def record_command(command, *args):
        events.append(command)
        return await real_handle(command, *args)

    async def record_sleep(seconds):
        events.append(f"sleep:{seconds}")

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", side_effect=record_command),
        patch(SLEEP, side_effect=record_sleep),
    ):
        await cover.set_position(20)

    assert (
        events.index(SERVICE_STOP_COVER)
        < events.index("sleep:2.5")
        < events.index(SERVICE_CLOSE_COVER)
    )


def test_configured_delay_is_wired_through_from_options():
    """The option reaches the cover built by the factory."""
    cover = _create_cover_from_options(
        _switch_options(**{CONF_DIRECTION_CHANGE_DELAY: 3.0}),
        device_id="test",
        name="Test",
    )
    assert cover._direction_change_delay_time == 3.0


def test_yaml_device_config_accepts_the_delay():
    """YAML parity with the other timing options."""
    config = {
        CONF_DEFAULTS: {},
        CONF_DEVICES: {
            "blind1": {
                "name": "Living Room",
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                CONF_DIRECTION_CHANGE_DELAY: 4.0,
            },
        },
    }
    devices = devices_from_config(config)
    assert devices[0]._direction_change_delay_time == 4.0


def test_omitted_option_leaves_the_default():
    """An unset option falls back to the historical 1.0s."""
    cover = _create_cover_from_options(_switch_options(), device_id="test", name="Test")
    assert cover._direction_change_delay_time == 1.0
