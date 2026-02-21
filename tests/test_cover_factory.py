"""Tests for cover factory and YAML config parsing in cover.py."""

import pytest
from unittest.mock import MagicMock, patch

from custom_components.cover_time_based.cover import (
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_COVER_ENTITY_ID,
    CONF_DEFAULTS,
    CONF_DEVICE_TYPE,
    CONF_DEVICES,
    CONF_INPUT_MODE,
    CONF_IS_BUTTON,
    CONF_MIN_MOVEMENT_TIME,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_TILT_STARTUP_DELAY,
    CONF_TILTING_TIME_DOWN,
    CONF_TILTING_TIME_UP,
    CONF_TRAVEL_DELAY_AT_END,
    CONF_TRAVEL_STARTUP_DELAY,
    CONF_TRAVELLING_TIME_DOWN,
    CONF_TRAVELLING_TIME_UP,
    CONF_TRAVEL_TIME_CLOSE,
    CONF_TRAVEL_TIME_OPEN,
    CONF_TILT_TIME_CLOSE,
    CONF_TILT_TIME_OPEN,
    DEVICE_TYPE_COVER,
    DEVICE_TYPE_SWITCH,
    INPUT_MODE_PULSE,
    INPUT_MODE_SWITCH,
    INPUT_MODE_TOGGLE,
    _create_cover_from_options,
    _resolve_tilt_strategy,
    devices_from_config,
)
from custom_components.cover_time_based.cover_switch_mode import SwitchModeCover
from custom_components.cover_time_based.cover_pulse_mode import PulseModeCover
from custom_components.cover_time_based.cover_toggle_mode import ToggleModeCover
from custom_components.cover_time_based.cover_wrapped import WrappedCoverTimeBased
from custom_components.cover_time_based.tilt_strategies import (
    DualMotorTilt,
    InlineTilt,
    SequentialTilt,
)


# ===================================================================
# _create_cover_from_options
# ===================================================================


class TestCreateCoverFromOptions:
    """Test the factory function for creating cover subclasses."""

    def test_creates_switch_mode_cover(self):
        cover = _create_cover_from_options(
            {
                CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                CONF_INPUT_MODE: INPUT_MODE_SWITCH,
            },
            device_id="test",
            name="Test",
        )
        assert isinstance(cover, SwitchModeCover)

    def test_creates_pulse_mode_cover(self):
        cover = _create_cover_from_options(
            {
                CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                CONF_INPUT_MODE: INPUT_MODE_PULSE,
                CONF_PULSE_TIME: 0.5,
            },
            device_id="test",
            name="Test",
        )
        assert isinstance(cover, PulseModeCover)

    def test_creates_toggle_mode_cover(self):
        cover = _create_cover_from_options(
            {
                CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                CONF_INPUT_MODE: INPUT_MODE_TOGGLE,
                CONF_PULSE_TIME: 0.5,
            },
            device_id="test",
            name="Test",
        )
        assert isinstance(cover, ToggleModeCover)

    def test_creates_wrapped_cover(self):
        cover = _create_cover_from_options(
            {
                CONF_DEVICE_TYPE: DEVICE_TYPE_COVER,
                CONF_COVER_ENTITY_ID: "cover.inner",
            },
            device_id="test",
            name="Test",
        )
        assert isinstance(cover, WrappedCoverTimeBased)

    def test_defaults_to_switch_mode(self):
        """When input_mode is not specified, defaults to switch."""
        cover = _create_cover_from_options(
            {
                CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
            },
            device_id="test",
            name="Test",
        )
        assert isinstance(cover, SwitchModeCover)

    def test_passes_common_params(self):
        cover = _create_cover_from_options(
            {
                CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                CONF_TRAVEL_TIME_CLOSE: 25.0,
                CONF_TRAVEL_TIME_OPEN: 20.0,
                CONF_TILT_TIME_CLOSE: 5.0,
                CONF_TILT_TIME_OPEN: 4.0,
                CONF_MIN_MOVEMENT_TIME: 0.5,
            },
            device_id="myid",
            name="My Cover",
        )
        assert cover.name == "My Cover"
        assert cover._travel_time_close == 25.0
        assert cover._travel_time_open == 20.0
        assert cover._tilting_time_close == 5.0
        assert cover._tilting_time_open == 4.0
        assert cover._min_movement_time == 0.5

    def test_defaults_to_switch_device_type(self):
        """When device_type is not specified, defaults to switch."""
        cover = _create_cover_from_options(
            {
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
            },
            device_id="test",
            name="Test",
        )
        assert isinstance(cover, SwitchModeCover)


# ===================================================================
# devices_from_config
# ===================================================================


class TestDevicesFromConfig:
    """Test YAML config parsing via devices_from_config."""

    def test_creates_switch_mode_from_yaml(self):
        config = {
            CONF_DEFAULTS: {},
            CONF_DEVICES: {
                "blind1": {
                    "name": "Living Room",
                    CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                    CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                },
            },
        }
        devices = devices_from_config(config)
        assert len(devices) == 1
        assert isinstance(devices[0], SwitchModeCover)
        assert devices[0].name == "Living Room"

    def test_creates_wrapped_cover_from_yaml(self):
        config = {
            CONF_DEFAULTS: {},
            CONF_DEVICES: {
                "blind1": {
                    "name": "Bedroom",
                    CONF_COVER_ENTITY_ID: "cover.inner",
                },
            },
        }
        devices = devices_from_config(config)
        assert len(devices) == 1
        assert isinstance(devices[0], WrappedCoverTimeBased)

    def test_creates_pulse_mode_from_yaml(self):
        config = {
            CONF_DEFAULTS: {},
            CONF_DEVICES: {
                "blind1": {
                    "name": "Kitchen",
                    CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                    CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                    CONF_INPUT_MODE: INPUT_MODE_PULSE,
                },
            },
        }
        devices = devices_from_config(config)
        assert isinstance(devices[0], PulseModeCover)

    def test_creates_toggle_mode_from_yaml(self):
        config = {
            CONF_DEFAULTS: {},
            CONF_DEVICES: {
                "blind1": {
                    "name": "Kitchen",
                    CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                    CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                    CONF_INPUT_MODE: INPUT_MODE_TOGGLE,
                },
            },
        }
        devices = devices_from_config(config)
        assert isinstance(devices[0], ToggleModeCover)

    def test_defaults_applied(self):
        """Old YAML keys in defaults are migrated to new names."""
        config = {
            CONF_DEFAULTS: {
                CONF_TRAVELLING_TIME_DOWN: 15.0,
                CONF_TRAVELLING_TIME_UP: 12.0,
                CONF_TILTING_TIME_DOWN: 3.0,
                CONF_TILTING_TIME_UP: 2.5,
            },
            CONF_DEVICES: {
                "blind1": {
                    "name": "Test",
                    CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                    CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                },
            },
        }
        devices = devices_from_config(config)
        cover = devices[0]
        assert cover._travel_time_close == 15.0
        assert cover._travel_time_open == 12.0
        assert cover._tilting_time_close == 3.0
        assert cover._tilting_time_open == 2.5

    def test_device_config_overrides_defaults(self):
        config = {
            CONF_DEFAULTS: {
                CONF_TRAVELLING_TIME_DOWN: 15.0,
            },
            CONF_DEVICES: {
                "blind1": {
                    "name": "Test",
                    CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                    CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                    CONF_TRAVELLING_TIME_DOWN: 25.0,
                },
            },
        }
        devices = devices_from_config(config)
        assert devices[0]._travel_time_close == 25.0

    def test_is_button_deprecated_to_pulse_mode(self):
        config = {
            CONF_DEFAULTS: {},
            CONF_DEVICES: {
                "blind1": {
                    "name": "Test",
                    CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                    CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                    CONF_IS_BUTTON: True,
                },
            },
        }
        devices = devices_from_config(config)
        assert isinstance(devices[0], PulseModeCover)

    def test_input_mode_takes_precedence_over_is_button(self):
        config = {
            CONF_DEFAULTS: {},
            CONF_DEVICES: {
                "blind1": {
                    "name": "Test",
                    CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                    CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                    CONF_IS_BUTTON: True,
                    CONF_INPUT_MODE: INPUT_MODE_TOGGLE,
                },
            },
        }
        devices = devices_from_config(config)
        assert isinstance(devices[0], ToggleModeCover)

    def test_multiple_devices(self):
        config = {
            CONF_DEFAULTS: {},
            CONF_DEVICES: {
                "blind1": {
                    "name": "Living",
                    CONF_OPEN_SWITCH_ENTITY_ID: "switch.open1",
                    CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close1",
                },
                "blind2": {
                    "name": "Bedroom",
                    CONF_COVER_ENTITY_ID: "cover.inner",
                },
            },
        }
        devices = devices_from_config(config)
        assert len(devices) == 2

    def test_stop_switch_passed_through(self):
        config = {
            CONF_DEFAULTS: {},
            CONF_DEVICES: {
                "blind1": {
                    "name": "Test",
                    CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                    CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                    CONF_STOP_SWITCH_ENTITY_ID: "switch.stop",
                },
            },
        }
        devices = devices_from_config(config)
        assert devices[0]._stop_switch_entity_id == "switch.stop"

    def test_all_timing_params_from_defaults(self):
        config = {
            CONF_DEFAULTS: {
                CONF_TRAVEL_DELAY_AT_END: 1.0,
                CONF_MIN_MOVEMENT_TIME: 0.5,
                CONF_TRAVEL_STARTUP_DELAY: 0.3,
                CONF_TILT_STARTUP_DELAY: 0.2,
                CONF_PULSE_TIME: 0.8,
            },
            CONF_DEVICES: {
                "blind1": {
                    "name": "Test",
                    CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                    CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                    CONF_INPUT_MODE: INPUT_MODE_PULSE,
                },
            },
        }
        devices = devices_from_config(config)
        cover = devices[0]
        assert cover._endpoint_runon_time == 1.0
        assert cover._min_movement_time == 0.5
        assert cover._travel_startup_delay == 0.3
        assert cover._tilt_startup_delay == 0.2


# ===================================================================
# async_setup_platform (deprecated YAML)
# ===================================================================


class TestAsyncSetupPlatform:
    """Test the deprecated YAML setup."""

    @pytest.mark.asyncio
    async def test_setup_platform_creates_entities(self):
        from custom_components.cover_time_based.cover import async_setup_platform

        hass = MagicMock()
        added_entities = []

        config = {
            CONF_DEFAULTS: {},
            CONF_DEVICES: {
                "blind1": {
                    "name": "Test",
                    CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                    CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                },
            },
        }

        platform = MagicMock()
        with patch("custom_components.cover_time_based.cover.async_create_issue"):
            with patch(
                "custom_components.cover_time_based.cover.entity_platform.current_platform"
            ) as mock_platform:
                mock_platform.get.return_value = platform
                await async_setup_platform(
                    hass, config, lambda entities: added_entities.extend(entities)
                )

        assert len(added_entities) == 1
        assert isinstance(added_entities[0], SwitchModeCover)
        # Should register services
        assert platform.async_register_entity_service.call_count == 2


# ===================================================================
# async_setup_entry
# ===================================================================


class TestAsyncSetupEntry:
    """Test config entry setup."""

    @pytest.mark.asyncio
    async def test_setup_entry_creates_entity(self):
        from custom_components.cover_time_based.cover import async_setup_entry

        hass = MagicMock()
        added_entities = []

        config_entry = MagicMock()
        config_entry.entry_id = "test_entry"
        config_entry.title = "My Cover"
        config_entry.options = {
            CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
            CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
            CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
            CONF_INPUT_MODE: INPUT_MODE_SWITCH,
        }

        platform = MagicMock()
        with patch(
            "custom_components.cover_time_based.cover.entity_platform.current_platform"
        ) as mock_platform:
            mock_platform.get.return_value = platform
            await async_setup_entry(
                hass,
                config_entry,
                lambda entities: added_entities.extend(entities),
            )

        assert len(added_entities) == 1
        assert added_entities[0].name == "My Cover"
        assert platform.async_register_entity_service.call_count == 2


# ===================================================================
# _resolve_tilt_strategy
# ===================================================================


class TestResolveTiltStrategy:
    def test_none_when_tilt_mode_none(self):
        assert _resolve_tilt_strategy("none", 2.0, 2.0) is None

    def test_none_when_no_tilt_times(self):
        assert _resolve_tilt_strategy("sequential", None, None) is None

    def test_none_when_partial_tilt_times(self):
        assert _resolve_tilt_strategy("sequential", 2.0, None) is None

    def test_sequential(self):
        result = _resolve_tilt_strategy("sequential", 2.0, 2.0)
        assert isinstance(result, SequentialTilt)

    def test_dual_motor_defaults(self):
        result = _resolve_tilt_strategy("dual_motor", 2.0, 2.0)
        assert isinstance(result, DualMotorTilt)
        assert result._safe_tilt_position == 100
        assert result._max_tilt_allowed_position is None

    def test_dual_motor_with_options(self):
        result = _resolve_tilt_strategy(
            "dual_motor",
            2.0,
            2.0,
            safe_tilt_position=10,
            max_tilt_allowed_position=80,
        )
        assert isinstance(result, DualMotorTilt)
        assert result._safe_tilt_position == 10
        assert result._max_tilt_allowed_position == 80

    def test_inline(self):
        result = _resolve_tilt_strategy("inline", 2.0, 2.0)
        assert isinstance(result, InlineTilt)

    def test_unknown_mode_defaults_to_sequential(self):
        result = _resolve_tilt_strategy("unknown_value", 2.0, 2.0)
        assert isinstance(result, SequentialTilt)
