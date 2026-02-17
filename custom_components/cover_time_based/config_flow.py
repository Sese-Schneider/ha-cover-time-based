"""Config flow for Cover Time Based integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .cover import (
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

SECTION_TILT = "tilt"
SECTION_ADVANCED = "advanced"

TIMING_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=600, step=0.1, mode=NumberSelectorMode.BOX)
)

SWITCH_ENTITY_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain=["switch", "input_boolean"])
)

COVER_ENTITY_SELECTOR = EntitySelector(EntitySelectorConfig(domain="cover"))

PULSE_TIME_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0.1, max=10, step=0.1, mode=NumberSelectorMode.BOX)
)


def _build_details_schema(
    device_type: str,
    input_mode: str,
    defaults: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build the details schema based on device type and input mode."""
    d = defaults or {}
    fields: dict[vol.Marker, Any] = {}

    # Entity fields based on device type
    if device_type == DEVICE_TYPE_SWITCH:
        fields[
            vol.Required(
                CONF_OPEN_SWITCH_ENTITY_ID,
                default=d.get(CONF_OPEN_SWITCH_ENTITY_ID, vol.UNDEFINED),
            )
        ] = SWITCH_ENTITY_SELECTOR
        fields[
            vol.Required(
                CONF_CLOSE_SWITCH_ENTITY_ID,
                default=d.get(CONF_CLOSE_SWITCH_ENTITY_ID, vol.UNDEFINED),
            )
        ] = SWITCH_ENTITY_SELECTOR
        fields[
            vol.Optional(
                CONF_STOP_SWITCH_ENTITY_ID,
                description={"suggested_value": d.get(CONF_STOP_SWITCH_ENTITY_ID)},
            )
        ] = SWITCH_ENTITY_SELECTOR
    else:
        fields[
            vol.Required(
                CONF_COVER_ENTITY_ID,
                default=d.get(CONF_COVER_ENTITY_ID, vol.UNDEFINED),
            )
        ] = COVER_ENTITY_SELECTOR

    # Travel timing
    fields[
        vol.Optional(
            CONF_TRAVELLING_TIME_DOWN,
            description={"suggested_value": d.get(CONF_TRAVELLING_TIME_DOWN)},
        )
    ] = TIMING_SELECTOR
    fields[
        vol.Optional(
            CONF_TRAVELLING_TIME_UP,
            description={"suggested_value": d.get(CONF_TRAVELLING_TIME_UP)},
        )
    ] = TIMING_SELECTOR

    # Tilt section (collapsed)
    fields[vol.Optional(SECTION_TILT)] = section(
        vol.Schema(
            {
                vol.Optional(
                    CONF_TILTING_TIME_DOWN,
                    description={"suggested_value": d.get(CONF_TILTING_TIME_DOWN)},
                ): TIMING_SELECTOR,
                vol.Optional(
                    CONF_TILTING_TIME_UP,
                    description={"suggested_value": d.get(CONF_TILTING_TIME_UP)},
                ): TIMING_SELECTOR,
                vol.Optional(
                    CONF_TRAVEL_MOVES_WITH_TILT,
                    default=d.get(CONF_TRAVEL_MOVES_WITH_TILT, False),
                ): BooleanSelector(),
            }
        ),
        {"collapsed": True},
    )

    # Advanced section (collapsed)
    adv_fields: dict[vol.Marker, Any] = {}
    if input_mode in (INPUT_MODE_PULSE, INPUT_MODE_TOGGLE):
        adv_fields[
            vol.Optional(
                CONF_PULSE_TIME,
                description={"suggested_value": d.get(CONF_PULSE_TIME)},
            )
        ] = PULSE_TIME_SELECTOR
    adv_fields[
        vol.Optional(
            CONF_TRAVEL_STARTUP_DELAY,
            description={"suggested_value": d.get(CONF_TRAVEL_STARTUP_DELAY)},
        )
    ] = TIMING_SELECTOR
    adv_fields[
        vol.Optional(
            CONF_TILT_STARTUP_DELAY,
            description={"suggested_value": d.get(CONF_TILT_STARTUP_DELAY)},
        )
    ] = TIMING_SELECTOR
    adv_fields[
        vol.Optional(
            CONF_MIN_MOVEMENT_TIME,
            description={"suggested_value": d.get(CONF_MIN_MOVEMENT_TIME)},
        )
    ] = TIMING_SELECTOR
    adv_fields[
        vol.Optional(
            CONF_TRAVEL_DELAY_AT_END,
            description={"suggested_value": d.get(CONF_TRAVEL_DELAY_AT_END)},
        )
    ] = TIMING_SELECTOR
    fields[vol.Optional(SECTION_ADVANCED)] = section(
        vol.Schema(adv_fields),
        {"collapsed": True},
    )

    return vol.Schema(fields)


def _flatten_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Flatten section data into a single dict."""
    data: dict[str, Any] = {}
    for key, value in user_input.items():
        if key in (SECTION_TILT, SECTION_ADVANCED) and isinstance(value, dict):
            data.update(value)
        else:
            data[key] = value
    return data


def _validate_tilt_pair(data: dict[str, Any]) -> dict[str, str]:
    """Validate that tilt times are provided as a pair."""
    has_down = data.get(CONF_TILTING_TIME_DOWN) is not None
    has_up = data.get(CONF_TILTING_TIME_UP) is not None
    if has_down != has_up:
        missing = CONF_TILTING_TIME_UP if has_down else CONF_TILTING_TIME_DOWN
        return {missing: "tilt_time_pair_required"}
    return {}


class CoverTimeBasedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cover Time Based."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._name: str = ""
        self._device_type: str = DEVICE_TYPE_SWITCH
        self._input_mode: str = INPUT_MODE_SWITCH

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Choose name, device type and input mode."""
        if user_input is not None:
            self._name = user_input[CONF_NAME]
            self._device_type = user_input[CONF_DEVICE_TYPE]
            self._input_mode = user_input.get(CONF_INPUT_MODE, INPUT_MODE_SWITCH)
            return await self.async_step_details()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): TextSelector(),
                vol.Required(
                    CONF_DEVICE_TYPE, default=DEVICE_TYPE_SWITCH
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            DEVICE_TYPE_SWITCH,
                            DEVICE_TYPE_COVER,
                        ],
                        translation_key="device_type",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_INPUT_MODE, default=INPUT_MODE_SWITCH
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            INPUT_MODE_SWITCH,
                            INPUT_MODE_PULSE,
                            INPUT_MODE_TOGGLE,
                        ],
                        translation_key="input_mode",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Configure entities and timing."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _flatten_input(user_input)
            errors = _validate_tilt_pair(data)
            if not errors:
                data[CONF_DEVICE_TYPE] = self._device_type
                data[CONF_INPUT_MODE] = self._input_mode
                return self.async_create_entry(
                    title=self._name,
                    data={},
                    options=data,
                )

        schema = _build_details_schema(
            self._device_type,
            self._input_mode,
            defaults=_flatten_input(user_input) if user_input else None,
        )
        return self.async_show_form(
            step_id="details", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> CoverTimeBasedOptionsFlow:
        """Get the options flow for this handler."""
        return CoverTimeBasedOptionsFlow()


class CoverTimeBasedOptionsFlow(OptionsFlow):
    """Handle options flow for reconfiguring a cover."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._device_type: str = DEVICE_TYPE_SWITCH
        self._input_mode: str = INPUT_MODE_SWITCH

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Choose device type and input mode."""
        current = dict(self.config_entry.options)

        if user_input is not None:
            self._device_type = user_input[CONF_DEVICE_TYPE]
            self._input_mode = user_input.get(CONF_INPUT_MODE, INPUT_MODE_SWITCH)
            return await self.async_step_details()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEVICE_TYPE,
                    default=current.get(CONF_DEVICE_TYPE, DEVICE_TYPE_SWITCH),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            DEVICE_TYPE_SWITCH,
                            DEVICE_TYPE_COVER,
                        ],
                        translation_key="device_type",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_INPUT_MODE,
                    default=current.get(CONF_INPUT_MODE, INPUT_MODE_SWITCH),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            INPUT_MODE_SWITCH,
                            INPUT_MODE_PULSE,
                            INPUT_MODE_TOGGLE,
                        ],
                        translation_key="input_mode",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Configure entities and timing."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _flatten_input(user_input)
            errors = _validate_tilt_pair(data)
            if not errors:
                data[CONF_DEVICE_TYPE] = self._device_type
                data[CONF_INPUT_MODE] = self._input_mode
                return self.async_create_entry(title="", data=data)

        current = dict(self.config_entry.options)
        if user_input is not None:
            current.update(_flatten_input(user_input))
        schema = _build_details_schema(
            self._device_type, self._input_mode, defaults=current
        )
        return self.async_show_form(
            step_id="details", data_schema=schema, errors=errors
        )
