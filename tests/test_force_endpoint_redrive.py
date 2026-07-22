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
from homeassistant.exceptions import HomeAssistantError

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
    assert make_cover().extra_state_attributes["force_endpoint_redrive"] is False


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
    cover = make_cover(cover_entity_id="cover.inner", reports_command_not_endpoint=True)
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
    cover = make_cover(control_mode=CONTROL_MODE_TOGGLE, force_endpoint_redrive=True)
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
    cover.tilt_calc.set_position(0)  # slats NOT at safe (100)
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


@pytest.mark.asyncio
async def test_force_redrive_failed_validation_does_not_corrupt_tracker(make_cover):
    """issue #167 follow-up: _force_full_redrive used to seed the opposite
    endpoint (travel_calc.set_position(100)) BEFORE validating that the
    movement target is available. A failed redrive from settled-0 must raise
    without leaving the tracker corrupted at the seeded opposite endpoint —
    that corrupt position would otherwise be persisted on the next state
    write, with no feedback to correct it."""
    cover = make_cover(force_endpoint_redrive=True)  # switch mode
    cover.travel_calc.set_position(0)  # settled closed
    # Make the movement target unavailable.
    cover.hass.states.get.return_value = None

    with patch.object(cover, "async_write_ha_state"):
        with pytest.raises(HomeAssistantError):
            await cover.async_close_cover()

    assert cover.travel_calc.current_position() == 0, (
        "tracker must not be corrupted to the opposite endpoint by a failed redrive"
    )


@pytest.mark.asyncio
async def test_force_redrive_validates_even_with_stale_self_initiated_flag(make_cover):
    """Guards the _self_initiated_movement refresh in _force_full_redrive.

    _require_movement_target_available only checks availability when
    _self_initiated_movement is True. That flag is not reset at the top of
    async_close_cover/async_open_cover — it's left over from whatever
    movement last ran (e.g. False, from a prior externally-triggered move
    that settled at this endpoint). If _force_full_redrive didn't refresh it
    before validating, a stale False would make the availability check a
    silent no-op, letting a failed redrive corrupt the tracker exactly like
    the bug this task fixes — just gated behind trigger-history instead of
    always. Simulate that stale precondition directly."""
    cover = make_cover(force_endpoint_redrive=True)  # switch mode
    cover.travel_calc.set_position(0)  # settled closed
    # Make the movement target unavailable.
    cover.hass.states.get.return_value = None
    # Simulate a prior externally-triggered movement leaving this flag stale.
    cover._self_initiated_movement = False

    with patch.object(cover, "async_write_ha_state"):
        with pytest.raises(HomeAssistantError):
            await cover.async_close_cover()

    assert cover.travel_calc.current_position() == 0, (
        "tracker must not be corrupted to the opposite endpoint by a failed "
        "redrive, even when _self_initiated_movement was left stale-False"
    )


@pytest.mark.asyncio
async def test_force_redrive_failing_tilt_prestep_does_not_corrupt_tracker(make_cover):
    """A dual-motor forced redrive seeds the opposite endpoint, then drives the
    tilt-to-safe pre-step BEFORE travel. Task 17 pre-validated only the TRAVEL
    target — the tilt switch is checked (and the tilt relay fired) deeper in,
    inside _start_tilt_pre_step, AFTER the seed. So a tilt-phase failure (the
    tilt service raising, or the tilt switch unavailable) left the travel
    tracker parked at the opposite endpoint with no movement started to correct
    it, and the pre-step's half-set continuation fields dangling. Snapshot the
    tracker before the seed and roll it back (plus clear the pending fields) on
    any failure."""
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
    cover.travel_calc.set_position(0)  # believed fully closed (settled)
    cover.tilt_calc.set_position(0)  # slats NOT at safe (100) -> pre-step drives tilt_open

    # The tilt-to-safe pre-step raises (e.g. the tilt service errors) AFTER the
    # seed and after the pending fields are set.
    async def _boom():
        raise HomeAssistantError("tilt relay failed")

    with patch.object(cover, "async_write_ha_state"):
        with patch.object(cover, "_send_tilt_open", side_effect=_boom):
            with pytest.raises(HomeAssistantError):
                await cover.async_close_cover()

    assert cover.travel_calc.current_position() == 0, (
        "tracker must not be left seeded at the opposite endpoint by a failed "
        "tilt pre-step during a forced redrive"
    )
    # The pre-step's continuation fields must not dangle after the rollback.
    assert cover._pending_travel_target is None, cover._pending_travel_target
    assert cover._pending_travel_command is None, cover._pending_travel_command
    assert cover._tilt_restore_target is None, cover._tilt_restore_target
