"""Force endpoint re-drive (issue #167).

Covers with no position feedback can be moved by an external remote HA never
sees, so HA keeps believing the cover is at an endpoint. With
force_endpoint_redrive on, an open/close commanded at that believed endpoint is
re-driven for the full travel time (modeled from the opposite endpoint) instead
of being skipped as a no-op / short resync pulse.
"""

import pytest
from unittest.mock import patch

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from custom_components.cover_time_based.cover import (
    CONTROL_MODE_PULSE,
    CONTROL_MODE_SWITCH,
    CONTROL_MODE_TOGGLE,
)


@pytest.mark.asyncio
async def test_force_close_at_closed_redrives_full_travel(make_cover):
    """Switch cover believed fully closed: force-close starts a real full
    journey (is_traveling), not the skip no-op."""
    cover = make_cover(force_endpoint_redrive=True)  # switch mode
    cover.travel_calc.set_position(0)  # believed fully closed

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()

    assert cover.travel_calc.is_traveling(), "force-close must start a full journey"
    assert cover._last_command == SERVICE_CLOSE_COVER
    cover.hass.services.async_call.assert_awaited()


@pytest.mark.asyncio
async def test_force_open_at_open_redrives_full_travel(make_cover):
    """Switch cover believed fully open: force-open starts a real full journey,
    not the short resync (which does not travel)."""
    cover = make_cover(force_endpoint_redrive=True)  # switch mode
    cover.travel_calc.set_position(100)  # believed fully open

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()

    assert cover.travel_calc.is_traveling(), "force-open must start a full journey"
    assert cover._last_command == SERVICE_OPEN_COVER
    cover.hass.services.async_call.assert_awaited()


@pytest.mark.asyncio
async def test_option_off_close_at_closed_is_noop(make_cover):
    """Regression guard: with the flag off, close at believed-0 is still the
    existing no-op (nothing sent)."""
    cover = make_cover()  # switch mode, flag off by default
    assert cover._force_endpoint_redrive is False
    cover.travel_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()

    assert not cover.travel_calc.is_traveling()
    cover.hass.services.async_call.assert_not_awaited()
    assert cover._last_command is None


@pytest.mark.asyncio
async def test_config_sets_force_endpoint_redrive(make_cover):
    """The option flows from config into the entity attribute."""
    assert make_cover(force_endpoint_redrive=True)._force_endpoint_redrive is True
    assert make_cover()._force_endpoint_redrive is False


@pytest.mark.asyncio
async def test_force_endpoint_redrive_in_state_attributes(make_cover):
    """The flag is exposed in extra_state_attributes for diagnostics."""
    assert (
        make_cover(force_endpoint_redrive=True).extra_state_attributes[
            "force_endpoint_redrive"
        ]
        is True
    )
    assert (
        make_cover().extra_state_attributes["force_endpoint_redrive"] is False
    )


@pytest.mark.asyncio
async def test_force_close_command_echo_wrapped_redrives(make_cover):
    """The reporter's mode: a command-echo wrapped cover believed closed
    re-drives a full close and forwards the command."""
    cover = make_cover(
        cover_entity_id="cover.inner",
        reports_command_not_endpoint=True,
        force_endpoint_redrive=True,
    )
    cover.travel_calc.set_position(0)  # believed fully closed
    cover.hass.services.async_call.reset_mock()

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()

    assert cover.travel_calc.is_traveling()
    assert cover._last_command == SERVICE_CLOSE_COVER
    cover.hass.services.async_call.assert_awaited()


@pytest.mark.asyncio
async def test_force_open_command_echo_wrapped_overrides_152_skip(make_cover):
    """Force-open overrides the command-echo open-at-100 skip (#152)."""
    cover = make_cover(
        cover_entity_id="cover.inner",
        reports_command_not_endpoint=True,
        force_endpoint_redrive=True,
    )
    cover.travel_calc.set_position(100)  # believed fully open
    cover.hass.services.async_call.reset_mock()

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()

    assert cover.travel_calc.is_traveling()
    assert cover._last_command == SERVICE_OPEN_COVER
    cover.hass.services.async_call.assert_awaited()


@pytest.mark.asyncio
async def test_command_echo_wrapped_open_still_skips_when_off(make_cover):
    """Regression guard: with the flag off, the #152 open-at-100 skip stands."""
    cover = make_cover(
        cover_entity_id="cover.inner", reports_command_not_endpoint=True
    )
    assert cover._force_endpoint_redrive is False
    cover.travel_calc.set_position(100)
    cover.hass.services.async_call.reset_mock()

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()

    assert not cover.travel_calc.is_traveling()
    cover.hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_force_redrive_command_echo_keeps_endpoint_stop_active(make_cover):
    """The #152-override is safe because the endpoint stop still fires: a
    command-echo wrapped cover does not self-stop at endpoints, so the forced
    full-travel branch's auto-stop de-energizes the motor rather than leaving
    the endstop-less motor stalled against its limit."""
    cover = make_cover(
        cover_entity_id="cover.inner",
        reports_command_not_endpoint=True,
        force_endpoint_redrive=True,
    )
    assert cover._self_stops_at_endpoints() is False


@pytest.mark.asyncio
async def test_force_close_pulse_redrives(make_cover):
    cover = make_cover(
        control_mode=CONTROL_MODE_PULSE,
        stop_switch="switch.stop",
        force_endpoint_redrive=True,
    )
    cover.travel_calc.set_position(0)
    cover.hass.services.async_call.reset_mock()

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()

    assert cover.travel_calc.is_traveling()
    assert cover._last_command == SERVICE_CLOSE_COVER
    cover.hass.services.async_call.assert_awaited()


@pytest.mark.asyncio
async def test_force_close_toggle_redrives(make_cover):
    cover = make_cover(
        control_mode=CONTROL_MODE_TOGGLE, force_endpoint_redrive=True
    )
    cover.travel_calc.set_position(0)
    cover.hass.services.async_call.reset_mock()

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()

    assert cover.travel_calc.is_traveling()
    assert cover._last_command == SERVICE_CLOSE_COVER
    cover.hass.services.async_call.assert_awaited()


@pytest.mark.asyncio
async def test_force_close_dual_motor_runs_safe_pre_step(make_cover):
    """Dual-motor: force-close runs the safe-tilt pre-step (slats to safe=100 =
    tilt_open) BEFORE travel, then queues the travel — the safety guarantee."""
    cover = make_cover(
        control_mode=CONTROL_MODE_SWITCH,
        tilt_time_close=2.0,
        tilt_time_open=2.0,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        tilt_stop_switch="switch.tilt_stop",
        safe_tilt_position=100,
        force_endpoint_redrive=True,
    )
    cover.travel_calc.set_position(0)  # believed fully closed
    cover.tilt_calc.set_position(0)    # slats NOT at safe (100)
    cover.hass.services.async_call.reset_mock()

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()

    tilt_open_on = [
        c
        for c in cover.hass.services.async_call.call_args_list
        if c.args[0] == "homeassistant"
        and c.args[1] == "turn_on"
        and c.args[2].get("entity_id") == "switch.tilt_open"
    ]
    assert tilt_open_on, "dual-motor force-close must run the safe-tilt pre-step first"
    assert cover._pending_travel_target == 0
    assert cover._pending_travel_command == SERVICE_CLOSE_COVER
