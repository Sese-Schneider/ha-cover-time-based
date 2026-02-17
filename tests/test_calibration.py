"""Tests for calibration services."""


class TestConfigEntryAccess:
    """Test that config entry ID is available on the entity."""

    def test_config_entry_id_stored(self, make_cover):
        """Cover should store its config entry ID."""
        cover = make_cover()
        assert cover._config_entry_id == "test_cover"


class TestCalibrationState:
    """Test the CalibrationState dataclass."""

    def test_initial_state(self):
        """CalibrationState should initialize with required fields."""
        from custom_components.cover_time_based.calibration import CalibrationState

        state = CalibrationState(
            attribute="travel_time_down",
            timeout=120.0,
        )
        assert state.attribute == "travel_time_down"
        assert state.timeout == 120.0
        assert state.started_at is not None
        assert state.step_count == 0
        assert state.step_duration is None
        assert state.last_pulse_duration is None
        assert state.timeout_task is None
        assert state.automation_task is None

    def test_constants_defined(self):
        """Calibration constants should be accessible."""
        from custom_components.cover_time_based.calibration import (
            CALIBRATION_STEP_PAUSE,
            CALIBRATION_OVERHEAD_STEPS,
            CALIBRATION_MIN_MOVEMENT_START,
            CALIBRATION_MIN_MOVEMENT_INCREMENT,
            CALIBRATABLE_ATTRIBUTES,
            SERVICE_START_CALIBRATION,
            SERVICE_STOP_CALIBRATION,
        )

        assert CALIBRATION_STEP_PAUSE == 2.0
        assert CALIBRATION_OVERHEAD_STEPS == 10
        assert CALIBRATION_MIN_MOVEMENT_START == 0.1
        assert CALIBRATION_MIN_MOVEMENT_INCREMENT == 0.1
        assert len(CALIBRATABLE_ATTRIBUTES) == 7
        assert SERVICE_START_CALIBRATION == "start_calibration"
        assert SERVICE_STOP_CALIBRATION == "stop_calibration"
