"""Task (#245 review, Fix 2): calibration's tilt-motor path must be gated by
supports_tilt.

_calibration_uses_tilt_motor's dual_motor fallback branch (used before a
TiltStrategy is resolved -- see TestDualMotorTiltCalibrationDrivesTiltMotor
in test_calibration.py) checked only ``_tilt_mode_str`` and
``_has_dual_motor_tilt_route()``, not ``supports_tilt``. A raw-YAML/API
misconfig (control_mode: single_button + tilt_mode: dual_motor + tilt
switches) could therefore still route calibration to the tilt relays on a
mode that structurally has no tilt (single-button covers set
supports_tilt = False and have no direction to choose). This closes that
one remaining unguarded tilt path (spec 7: supports_tilt must zero every
tilt code path).
"""

from custom_components.cover_time_based.cover_single_button_mode import (
    SingleButtonModeCover,
)


def _make_misconfigured_sb_cover():
    """A single_button cover with a raw-YAML/API dual_motor tilt misconfig:
    tilt_mode forced to "dual_motor" with tilt switches wired up, as if
    calibration should drive a tilt motor this mode cannot have.
    """
    cover = SingleButtonModeCover(
        device_id="test_sb",
        name="Test SB",
        tilt_strategy=None,
        travel_time_close=30,
        travel_time_open=30,
        tilt_time_close=None,
        tilt_time_open=None,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        endpoint_runon_time=None,
        min_movement_time=None,
        open_switch_entity_id="switch.button",
        close_switch_entity_id=None,
        stop_switch_entity_id=None,
        pulse_time=1.0,
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        tilt_mode_str="dual_motor",
    )
    return cover


def test_calibration_uses_tilt_motor_false_for_single_button_even_with_dual_motor_misconfig():
    cover = _make_misconfigured_sb_cover()
    # Preconditions: absent the supports_tilt guard, this exact combination
    # is what the dual_motor fallback branch reads to return True.
    assert cover.supports_tilt is False
    assert cover._tilt_strategy is None
    assert cover._tilt_mode_str == "dual_motor"
    assert cover._has_dual_motor_tilt_route() is True

    assert cover._calibration_uses_tilt_motor("tilt_time_close") is False
