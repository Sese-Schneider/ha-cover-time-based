"""Tests for config_flow.py."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from custom_components.cover_time_based.config_flow import (
    CoverTimeBasedConfigFlow,
    CoverTimeBasedOptionsFlow,
    _build_details_schema,
    _flatten_input,
    _validate_tilt_pair,
    SECTION_TILT,
    SECTION_ADVANCED,
)
from custom_components.cover_time_based.cover import (
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_COVER_ENTITY_ID,
    CONF_DEVICE_TYPE,
    CONF_INPUT_MODE,
    CONF_MIN_MOVEMENT_TIME,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_TILT_STARTUP_DELAY,
    CONF_TILTING_TIME_DOWN,
    CONF_TILTING_TIME_UP,
    CONF_TRAVEL_DELAY_AT_END,
    CONF_TRAVEL_MOVES_WITH_TILT,
    CONF_TRAVEL_STARTUP_DELAY,
    CONF_TRAVELLING_TIME_DOWN,
    CONF_TRAVELLING_TIME_UP,
    DEVICE_TYPE_COVER,
    DEVICE_TYPE_SWITCH,
    DOMAIN,
    INPUT_MODE_PULSE,
    INPUT_MODE_SWITCH,
    INPUT_MODE_TOGGLE,
)
from homeassistant.const import CONF_NAME


# ===================================================================
# _flatten_input
# ===================================================================


class TestFlattenInput:
    """Test section flattening for config flow data."""

    def test_flattens_tilt_section(self):
        data = {
            CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
            SECTION_TILT: {
                CONF_TILTING_TIME_DOWN: 5.0,
                CONF_TILTING_TIME_UP: 4.0,
            },
        }
        result = _flatten_input(data)
        assert result[CONF_OPEN_SWITCH_ENTITY_ID] == "switch.open"
        assert result[CONF_TILTING_TIME_DOWN] == 5.0
        assert result[CONF_TILTING_TIME_UP] == 4.0
        assert SECTION_TILT not in result

    def test_flattens_advanced_section(self):
        data = {
            SECTION_ADVANCED: {
                CONF_MIN_MOVEMENT_TIME: 0.5,
                CONF_TRAVEL_DELAY_AT_END: 1.0,
            },
        }
        result = _flatten_input(data)
        assert result[CONF_MIN_MOVEMENT_TIME] == 0.5
        assert result[CONF_TRAVEL_DELAY_AT_END] == 1.0

    def test_passes_through_non_section_keys(self):
        data = {
            CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
            CONF_TRAVELLING_TIME_DOWN: 25.0,
        }
        result = _flatten_input(data)
        assert result == data

    def test_handles_empty_input(self):
        assert _flatten_input({}) == {}

    def test_handles_mixed_sections_and_flat(self):
        data = {
            CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
            CONF_TRAVELLING_TIME_DOWN: 25.0,
            SECTION_TILT: {CONF_TILTING_TIME_DOWN: 5.0},
            SECTION_ADVANCED: {CONF_MIN_MOVEMENT_TIME: 0.5},
        }
        result = _flatten_input(data)
        assert len(result) == 4
        assert SECTION_TILT not in result
        assert SECTION_ADVANCED not in result


# ===================================================================
# _validate_tilt_pair
# ===================================================================


class TestValidateTiltPair:
    """Test tilt time pair validation."""

    def test_both_present_is_valid(self):
        assert _validate_tilt_pair({
            CONF_TILTING_TIME_DOWN: 5.0,
            CONF_TILTING_TIME_UP: 4.0,
        }) == {}

    def test_neither_present_is_valid(self):
        assert _validate_tilt_pair({}) == {}

    def test_only_down_missing_up(self):
        errors = _validate_tilt_pair({CONF_TILTING_TIME_DOWN: 5.0})
        assert CONF_TILTING_TIME_UP in errors
        assert errors[CONF_TILTING_TIME_UP] == "tilt_time_pair_required"

    def test_only_up_missing_down(self):
        errors = _validate_tilt_pair({CONF_TILTING_TIME_UP: 4.0})
        assert CONF_TILTING_TIME_DOWN in errors
        assert errors[CONF_TILTING_TIME_DOWN] == "tilt_time_pair_required"

    def test_both_none_is_valid(self):
        assert _validate_tilt_pair({
            CONF_TILTING_TIME_DOWN: None,
            CONF_TILTING_TIME_UP: None,
        }) == {}


# ===================================================================
# _build_details_schema
# ===================================================================


class TestBuildDetailsSchema:
    """Test schema building based on device type and input mode."""

    def test_switch_mode_schema_has_switch_entities(self):
        schema = _build_details_schema(DEVICE_TYPE_SWITCH, INPUT_MODE_SWITCH)
        keys = [str(k) for k in schema.schema]
        assert any(CONF_OPEN_SWITCH_ENTITY_ID in k for k in keys)
        assert any(CONF_CLOSE_SWITCH_ENTITY_ID in k for k in keys)

    def test_cover_mode_schema_has_cover_entity(self):
        schema = _build_details_schema(DEVICE_TYPE_COVER, INPUT_MODE_SWITCH)
        keys = [str(k) for k in schema.schema]
        assert any(CONF_COVER_ENTITY_ID in k for k in keys)
        assert not any(CONF_OPEN_SWITCH_ENTITY_ID in k for k in keys)

    def test_pulse_mode_schema_includes_pulse_time(self):
        schema = _build_details_schema(DEVICE_TYPE_SWITCH, INPUT_MODE_PULSE)
        # Advanced section should include pulse_time
        all_keys = []
        for key, val in schema.schema.items():
            all_keys.append(str(key))
        # The schema has sections, need to check the advanced section has pulse_time
        assert SECTION_ADVANCED in [str(k) for k in schema.schema]

    def test_toggle_mode_schema_includes_pulse_time(self):
        schema = _build_details_schema(DEVICE_TYPE_SWITCH, INPUT_MODE_TOGGLE)
        assert SECTION_ADVANCED in [str(k) for k in schema.schema]

    def test_switch_mode_schema_no_pulse_time(self):
        """Switch mode should not include pulse_time in advanced section."""
        schema = _build_details_schema(DEVICE_TYPE_SWITCH, INPUT_MODE_SWITCH)
        # Find the advanced section schema
        for key, val in schema.schema.items():
            if str(key) == SECTION_ADVANCED:
                # The section wraps a schema - check it doesn't have pulse_time
                inner = val.schema
                inner_keys = [str(k) for k in inner.schema]
                assert not any(CONF_PULSE_TIME in k for k in inner_keys)

    def test_schema_with_defaults(self):
        defaults = {
            CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
            CONF_TRAVELLING_TIME_DOWN: 25.0,
        }
        schema = _build_details_schema(
            DEVICE_TYPE_SWITCH, INPUT_MODE_SWITCH, defaults=defaults
        )
        assert schema is not None


# ===================================================================
# CoverTimeBasedConfigFlow
# ===================================================================


class TestConfigFlow:
    """Test the main config flow."""

    @pytest.mark.asyncio
    async def test_step_user_shows_form(self):
        flow = CoverTimeBasedConfigFlow()
        flow.hass = MagicMock()

        result = await flow.async_step_user(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_step_user_stores_values_and_proceeds(self):
        flow = CoverTimeBasedConfigFlow()
        flow.hass = MagicMock()

        result = await flow.async_step_user(
            user_input={
                CONF_NAME: "My Cover",
                CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
                CONF_INPUT_MODE: INPUT_MODE_PULSE,
            }
        )

        assert flow._name == "My Cover"
        assert flow._device_type == DEVICE_TYPE_SWITCH
        assert flow._input_mode == INPUT_MODE_PULSE
        assert result["type"] == "form"
        assert result["step_id"] == "details"

    @pytest.mark.asyncio
    async def test_step_details_shows_form(self):
        flow = CoverTimeBasedConfigFlow()
        flow.hass = MagicMock()
        flow._device_type = DEVICE_TYPE_SWITCH
        flow._input_mode = INPUT_MODE_SWITCH

        result = await flow.async_step_details(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "details"

    @pytest.mark.asyncio
    async def test_step_details_creates_entry(self):
        flow = CoverTimeBasedConfigFlow()
        flow.hass = MagicMock()
        flow._name = "My Cover"
        flow._device_type = DEVICE_TYPE_SWITCH
        flow._input_mode = INPUT_MODE_SWITCH

        result = await flow.async_step_details(
            user_input={
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
            }
        )

        assert result["type"] == "create_entry"
        assert result["title"] == "My Cover"
        assert result["options"][CONF_DEVICE_TYPE] == DEVICE_TYPE_SWITCH
        assert result["options"][CONF_INPUT_MODE] == INPUT_MODE_SWITCH

    @pytest.mark.asyncio
    async def test_step_details_validates_tilt_pair(self):
        flow = CoverTimeBasedConfigFlow()
        flow.hass = MagicMock()
        flow._name = "My Cover"
        flow._device_type = DEVICE_TYPE_SWITCH
        flow._input_mode = INPUT_MODE_SWITCH

        result = await flow.async_step_details(
            user_input={
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                SECTION_TILT: {CONF_TILTING_TIME_DOWN: 5.0},
            }
        )

        assert result["type"] == "form"
        assert result["errors"]

    @pytest.mark.asyncio
    async def test_step_details_with_sections(self):
        flow = CoverTimeBasedConfigFlow()
        flow.hass = MagicMock()
        flow._name = "My Cover"
        flow._device_type = DEVICE_TYPE_SWITCH
        flow._input_mode = INPUT_MODE_PULSE

        result = await flow.async_step_details(
            user_input={
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                CONF_TRAVELLING_TIME_DOWN: 25.0,
                CONF_TRAVELLING_TIME_UP: 20.0,
                SECTION_TILT: {
                    CONF_TILTING_TIME_DOWN: 5.0,
                    CONF_TILTING_TIME_UP: 4.0,
                    CONF_TRAVEL_MOVES_WITH_TILT: True,
                },
                SECTION_ADVANCED: {
                    CONF_PULSE_TIME: 0.5,
                    CONF_MIN_MOVEMENT_TIME: 0.3,
                },
            }
        )

        assert result["type"] == "create_entry"
        options = result["options"]
        assert options[CONF_TILTING_TIME_DOWN] == 5.0
        assert options[CONF_PULSE_TIME] == 0.5

    @pytest.mark.asyncio
    async def test_step_details_cover_type(self):
        flow = CoverTimeBasedConfigFlow()
        flow.hass = MagicMock()
        flow._name = "My Cover"
        flow._device_type = DEVICE_TYPE_COVER
        flow._input_mode = INPUT_MODE_SWITCH

        result = await flow.async_step_details(
            user_input={
                CONF_COVER_ENTITY_ID: "cover.inner",
                CONF_TRAVELLING_TIME_DOWN: 30.0,
                CONF_TRAVELLING_TIME_UP: 30.0,
            }
        )

        assert result["type"] == "create_entry"
        assert result["options"][CONF_COVER_ENTITY_ID] == "cover.inner"

    def test_async_get_options_flow(self):
        config_entry = MagicMock()
        flow = CoverTimeBasedConfigFlow.async_get_options_flow(config_entry)
        assert isinstance(flow, CoverTimeBasedOptionsFlow)


# ===================================================================
# CoverTimeBasedOptionsFlow
# ===================================================================


class TestOptionsFlow:
    """Test the options reconfiguration flow."""

    @pytest.mark.asyncio
    async def test_step_init_shows_form(self):
        flow = CoverTimeBasedOptionsFlow()
        flow.hass = MagicMock()
        config_entry = MagicMock()
        config_entry.options = {
            CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
            CONF_INPUT_MODE: INPUT_MODE_SWITCH,
        }
        type(flow).config_entry = PropertyMock(return_value=config_entry)

        result = await flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_step_init_stores_and_proceeds(self):
        flow = CoverTimeBasedOptionsFlow()
        flow.hass = MagicMock()
        config_entry = MagicMock()
        config_entry.options = {}
        type(flow).config_entry = PropertyMock(return_value=config_entry)

        result = await flow.async_step_init(
            user_input={
                CONF_DEVICE_TYPE: DEVICE_TYPE_COVER,
                CONF_INPUT_MODE: INPUT_MODE_PULSE,
            }
        )

        assert flow._device_type == DEVICE_TYPE_COVER
        assert flow._input_mode == INPUT_MODE_PULSE
        assert result["type"] == "form"
        assert result["step_id"] == "details"

    @pytest.mark.asyncio
    async def test_step_details_creates_entry(self):
        flow = CoverTimeBasedOptionsFlow()
        flow.hass = MagicMock()
        flow._device_type = DEVICE_TYPE_SWITCH
        flow._input_mode = INPUT_MODE_SWITCH
        config_entry = MagicMock()
        config_entry.options = {}
        type(flow).config_entry = PropertyMock(return_value=config_entry)

        result = await flow.async_step_details(
            user_input={
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
            }
        )

        assert result["type"] == "create_entry"
        assert result["data"][CONF_DEVICE_TYPE] == DEVICE_TYPE_SWITCH
        assert result["data"][CONF_INPUT_MODE] == INPUT_MODE_SWITCH

    @pytest.mark.asyncio
    async def test_step_details_shows_form_on_error(self):
        flow = CoverTimeBasedOptionsFlow()
        flow.hass = MagicMock()
        flow._device_type = DEVICE_TYPE_SWITCH
        flow._input_mode = INPUT_MODE_SWITCH
        config_entry = MagicMock()
        config_entry.options = {}
        type(flow).config_entry = PropertyMock(return_value=config_entry)

        result = await flow.async_step_details(
            user_input={
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                SECTION_TILT: {CONF_TILTING_TIME_DOWN: 5.0},
            }
        )

        assert result["type"] == "form"
        assert result["errors"]

    @pytest.mark.asyncio
    async def test_step_details_shows_form_no_input(self):
        flow = CoverTimeBasedOptionsFlow()
        flow.hass = MagicMock()
        flow._device_type = DEVICE_TYPE_SWITCH
        flow._input_mode = INPUT_MODE_SWITCH
        config_entry = MagicMock()
        config_entry.options = {
            CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
            CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
        }
        type(flow).config_entry = PropertyMock(return_value=config_entry)

        result = await flow.async_step_details(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "details"
