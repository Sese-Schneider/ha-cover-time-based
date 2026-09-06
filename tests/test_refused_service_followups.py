"""Refused-service-call follow-ups from #275.

#275 routed every hardware service call through one ``_call_service(..., stop=)``
funnel that DROPS a motor-starting service (``turn_on`` &c.) once the entity is
``_removed``. The funnel guards only the actual send; some callers did echo
bookkeeping or spawned follow-up tasks around that refused send, leaving them
dangling. These tests lock the side effects away after a refused send.
"""

from unittest.mock import patch

import pytest

from .helpers import stub_switches


# Echo bookkeeping runs before a refused turn_on (switch mode)
@pytest.mark.asyncio
async def test_refused_switch_drive_leaves_no_feedback_arm(make_cover):
    """A removed switch-mode cover whose ``turn_on`` the funnel refuses must not
    be left waiting for / counting an ON echo that will never come.

    ``_send_open`` marks the driving relay's pending echo AND arms the
    relay-feedback wait; on a removed entity the ``turn_on`` is refused by
    ``_call_service`` (motor-starting), so neither a pending-echo count nor a
    feedback arm may survive on the relay the refused drive never energised.
    """
    cover = make_cover(control_mode="switch", wait_for_relay_feedback=True)
    stub_switches(cover)  # every relay reports OFF, non-optimistic
    cover._removed = True

    with patch.object(cover, "async_write_ha_state"):
        await cover._send_open()

    # The driving relay was NEVER energised (turn_on refused), so nothing about
    # it should be outstanding.
    driving = cover._open_switch_entity_id
    assert cover._pending_switch.get(driving, 0) == 0, (
        f"pending-echo count left on {driving}: {cover._pending_switch}"
    )
    assert cover._feedback_armed_entity is None, (
        f"relay-feedback wait left armed on {cover._feedback_armed_entity}"
    )


# Self-stopping calibration mid-drive parks nothing at removal
@pytest.mark.asyncio
async def test_removal_mid_calibration_parks_axis_at_limit(make_cover):
    """A self-stopping cover removed mid-calibration must leave its tracker at
    the limit the drive is heading for, exactly as a normal drive's removal does.

    A calibration TIME-test drive fires the relay without starting the position
    tracker, so ``travel_calc.is_traveling()`` is False at removal.
    ``async_will_remove_from_hass`` still treats an active continuous calibration
    as driving its axis, parking the tracker at the calibration command's
    endpoint rather than leaving the stale mid-travel position.
    """
    cover = make_cover(control_mode="toggle_opposite")
    stub_switches(cover)
    # Cover sitting mid-travel; a close-time calibration will drive it to 0.
    cover.travel_calc.set_position(50)

    with patch.object(cover, "async_write_ha_state"):
        await cover.start_calibration(attribute="travel_time_close", timeout=60.0)
        # Sanity: the calibration drive set the direction but started no tracker.
        assert cover._last_command is not None
        assert not cover.travel_calc.is_traveling()

        await cover.async_will_remove_from_hass()

    # travel_time_close drove toward the closed endpoint; a self-stopping motor
    # halts there, so the tracker must be parked at 0.
    assert cover.travel_calc.current_position() == 0, (
        "removal mid-calibration left the tracker at "
        f"{cover.travel_calc.current_position()} instead of the closed limit (0)"
    )


DUAL_TILT = {
    "tilt_time_close": 5.0,
    "tilt_time_open": 5.0,
    "tilt_mode": "dual_motor",
    "tilt_open_switch": "switch.tilt_open",
    "tilt_close_switch": "switch.tilt_close",
}


# A dedicated-tilt calibration parks the tilt tracker at ITS command's endpoint
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("attribute", "endpoint"),
    [("tilt_time_close", 0), ("tilt_time_open", 100)],
)
async def test_removal_mid_tilt_calibration_parks_tilt_at_limit(
    make_cover, attribute, endpoint
):
    """A self-stopping cover removed mid tilt-calibration parks the TILT tracker
    at the endpoint the calibration command heads for.

    A dedicated tilt calibration drives the tilt motor without recording the
    travel ``_last_command``, so a ``_last_command``-derived tilt fallback parks
    at ``None`` or the opposite endpoint. The authoritative direction is the
    calibration's own ``move_command`` (reused from ``_set_position_after_calibration``).
    """
    cover = make_cover(control_mode="toggle_opposite", **DUAL_TILT)
    stub_switches(cover)
    cover.tilt_calc.set_position(50)
    # A stale opposite-endpoint travel command must not leak into the tilt park.
    cover._last_command = (
        "open_cover" if attribute == "tilt_time_close" else "close_cover"
    )

    with patch.object(cover, "async_write_ha_state"):
        await cover.start_calibration(attribute=attribute, timeout=60.0)
        assert not cover.tilt_calc.is_traveling()

        await cover.async_will_remove_from_hass()

    assert cover.tilt_calc.current_position() == endpoint, (
        f"removal mid {attribute} left tilt at "
        f"{cover.tilt_calc.current_position()} instead of {endpoint}"
    )


# Pulse release task spawned after a refused ON
@pytest.mark.asyncio
async def test_refused_pulse_spawns_no_release_task(make_cover):
    """A removed pulse-mode cover whose driving ``turn_on`` is refused must not
    spawn a deferred release (``turn_off``) task for a relay it never energised.

    ``_send_open`` ends with ``_schedule_pulse_completion(open_relay)``, now
    skipped when the drive was refused (the entity is ``_removed`` so the funnel
    dropped the ``turn_on``). The relay was never pulsed ON, so no deferred
    ``turn_off`` completion may be left dangling on a relay being removed.
    """
    cover = make_cover(control_mode="pulse", stop_switch="switch.stop")
    stub_switches(cover)  # every relay OFF
    cover._removed = True

    with (
        patch("custom_components.cover_time_based.cover_pulse_mode.sleep"),
        patch.object(cover, "async_write_ha_state"),
    ):
        await cover._send_open()

    driving = cover._open_switch_entity_id
    assert driving not in cover._pulse_tasks, (
        "a release/turn_off task was scheduled for a relay whose turn_on was "
        f"refused: {list(cover._pulse_tasks)}"
    )
