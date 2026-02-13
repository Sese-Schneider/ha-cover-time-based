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
    DOMAIN,
    INPUT_MODE_PULSE,
    INPUT_MODE_SWITCH,
    INPUT_MODE_TOGGLE,
)

CONF_DEVICE_TYPE = "device_type"
DEVICE_TYPE_SWITCH = "switch"
DEVICE_TYPE_COVER = "cover"

SECTION_ADVANCED = "advanced"

TIMING_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=600, step=0.1, mode=NumberSelectorMode.BOX)
)

SWITCH_ENTITY_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain=["switch", "input_boolean"])
)

COVER_ENTITY_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain="cover")
)


def _build_schema(
    defaults: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build the cover configuration schema."""
    d = defaults or {}

    fields: dict[vol.Marker, Any] = {}

    # Main fields
    fields[vol.Required("name", default=d.get("name", ""))] = TextSelector()
    fields[
        vol.Required(CONF_DEVICE_TYPE, default=d.get(CONF_DEVICE_TYPE, DEVICE_TYPE_SWITCH))
    ] = SelectSelector(
        SelectSelectorConfig(
            options=[DEVICE_TYPE_SWITCH, DEVICE_TYPE_COVER],
            translation_key="device_type",
            mode=SelectSelectorMode.DROPDOWN,
        )
    )

    # Switch entities
    fields[vol.Optional(
        CONF_OPEN_SWITCH_ENTITY_ID,
        description={"suggested_value": d.get(CONF_OPEN_SWITCH_ENTITY_ID)},
    )] = SWITCH_ENTITY_SELECTOR
    fields[vol.Optional(
        CONF_CLOSE_SWITCH_ENTITY_ID,
        description={"suggested_value": d.get(CONF_CLOSE_SWITCH_ENTITY_ID)},
    )] = SWITCH_ENTITY_SELECTOR
    fields[vol.Optional(
        CONF_STOP_SWITCH_ENTITY_ID,
        description={"suggested_value": d.get(CONF_STOP_SWITCH_ENTITY_ID)},
    )] = SWITCH_ENTITY_SELECTOR

    # Cover entity
    fields[vol.Optional(
        CONF_COVER_ENTITY_ID,
        description={"suggested_value": d.get(CONF_COVER_ENTITY_ID)},
    )] = COVER_ENTITY_SELECTOR

    # Input mode
    fields[
        vol.Optional(CONF_INPUT_MODE, default=d.get(CONF_INPUT_MODE, INPUT_MODE_SWITCH))
    ] = SelectSelector(
        SelectSelectorConfig(
            options=[INPUT_MODE_SWITCH, INPUT_MODE_PULSE, INPUT_MODE_TOGGLE],
            translation_key="input_mode",
            mode=SelectSelectorMode.DROPDOWN,
        )
    )

    # Pulse time
    fields[vol.Optional(
        CONF_PULSE_TIME,
        description={"suggested_value": d.get(CONF_PULSE_TIME)},
    )] = NumberSelector(
        NumberSelectorConfig(min=0.1, max=10, step=0.1, mode=NumberSelectorMode.BOX)
    )

    # Travel timing fields
    fields[vol.Optional(
        CONF_TRAVELLING_TIME_DOWN,
        description={"suggested_value": d.get(CONF_TRAVELLING_TIME_DOWN)},
    )] = TIMING_SELECTOR
    fields[vol.Optional(
        CONF_TRAVELLING_TIME_UP,
        description={"suggested_value": d.get(CONF_TRAVELLING_TIME_UP)},
    )] = TIMING_SELECTOR
    fields[vol.Optional(
        CONF_TILTING_TIME_DOWN,
        description={"suggested_value": d.get(CONF_TILTING_TIME_DOWN)},
    )] = TIMING_SELECTOR
    fields[vol.Optional(
        CONF_TILTING_TIME_UP,
        description={"suggested_value": d.get(CONF_TILTING_TIME_UP)},
    )] = TIMING_SELECTOR
    fields[vol.Optional(
        CONF_TRAVEL_MOVES_WITH_TILT,
        default=d.get(CONF_TRAVEL_MOVES_WITH_TILT, False),
    )] = BooleanSelector()

    # Advanced section (collapsed)
    advanced_defaults = {
        k: d[k] for k in (
            CONF_TRAVEL_STARTUP_DELAY,
            CONF_TILT_STARTUP_DELAY,
            CONF_MIN_MOVEMENT_TIME,
            CONF_TRAVEL_DELAY_AT_END,
        ) if k in d
    }
    fields[vol.Optional(SECTION_ADVANCED)] = section(
        vol.Schema(
            {
                vol.Optional(
                    CONF_TRAVEL_STARTUP_DELAY,
                    description={
                        "suggested_value": advanced_defaults.get(CONF_TRAVEL_STARTUP_DELAY)
                    },
                ): TIMING_SELECTOR,
                vol.Optional(
                    CONF_TILT_STARTUP_DELAY,
                    description={
                        "suggested_value": advanced_defaults.get(CONF_TILT_STARTUP_DELAY)
                    },
                ): TIMING_SELECTOR,
                vol.Optional(
                    CONF_MIN_MOVEMENT_TIME,
                    description={
                        "suggested_value": advanced_defaults.get(CONF_MIN_MOVEMENT_TIME)
                    },
                ): TIMING_SELECTOR,
                vol.Optional(
                    CONF_TRAVEL_DELAY_AT_END,
                    description={
                        "suggested_value": advanced_defaults.get(CONF_TRAVEL_DELAY_AT_END)
                    },
                ): TIMING_SELECTOR,
            }
        ),
        {"collapsed": True},
    )

    return vol.Schema(fields)


def _flatten_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Flatten section data into a single dict."""
    data: dict[str, Any] = {}
    for key, value in user_input.items():
        if key == SECTION_ADVANCED and isinstance(value, dict):
            data.update(value)
        else:
            data[key] = value
    return data


class CoverTimeBasedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cover Time Based."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            data = _flatten_input(user_input)
            name = data.pop("name")
            return self.async_create_entry(
                title=name,
                data={},
                options=data,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(),
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

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the options step."""
        if user_input is not None:
            data = _flatten_input(user_input)
            name = data.pop("name")
            self.hass.config_entries.async_update_entry(
                self.config_entry, title=name
            )
            return self.async_create_entry(title="", data=data)

        # Pre-populate with current values
        current = dict(self.config_entry.options)
        current["name"] = self.config_entry.title

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(defaults=current),
        )
