"""Config flow for Cover Time Based integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
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
    DEFAULT_TRAVEL_TIME,
    DOMAIN,
    INPUT_MODE_PULSE,
    INPUT_MODE_SWITCH,
    INPUT_MODE_TOGGLE,
)

CONF_DEVICE_TYPE = "device_type"
DEVICE_TYPE_SWITCH = "switch"
DEVICE_TYPE_COVER = "cover"

SECTION_TRAVEL_TIMING = "travel_timing"
SECTION_ADVANCED = "advanced"

TIMING_NUMBER_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=600, step=0.1, mode=NumberSelectorMode.BOX)
)


def _travel_timing_schema() -> vol.Schema:
    """Return schema for travel timing section."""
    return vol.Schema(
        {
            vol.Optional(CONF_TRAVELLING_TIME_DOWN): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_TRAVELLING_TIME_UP): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_TILTING_TIME_DOWN): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_TILTING_TIME_UP): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_TRAVEL_MOVES_WITH_TILT): BooleanSelector(),
        }
    )


def _advanced_schema() -> vol.Schema:
    """Return schema for advanced section."""
    return vol.Schema(
        {
            vol.Optional(CONF_TRAVEL_STARTUP_DELAY): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_TILT_STARTUP_DELAY): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_MIN_MOVEMENT_TIME): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_TRAVEL_DELAY_AT_END): TIMING_NUMBER_SELECTOR,
        }
    )


class CoverTimeBasedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cover Time Based."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step -- just create the entry."""
        if user_input is not None:
            return self.async_create_entry(
                title="Cover Time Based",
                data={},
                options={
                    CONF_TRAVELLING_TIME_DOWN: DEFAULT_TRAVEL_TIME,
                    CONF_TRAVELLING_TIME_UP: DEFAULT_TRAVEL_TIME,
                    CONF_TRAVEL_MOVES_WITH_TILT: False,
                },
            )

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> CoverTimeBasedOptionsFlow:
        """Get the options flow for this handler."""
        return CoverTimeBasedOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {"cover": CoverTimeBasedSubentryFlow}


class CoverTimeBasedOptionsFlow(OptionsFlow):
    """Handle options flow for editing integration defaults."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the integration defaults."""
        if user_input is not None:
            # Merge section data into flat options dict
            options: dict[str, Any] = {}
            travel = user_input.get(SECTION_TRAVEL_TIMING, {})
            advanced = user_input.get(SECTION_ADVANCED, {})
            options.update(travel)
            options.update(advanced)
            return self.async_create_entry(title="", data=options)

        # Build schema with current values as defaults
        current = dict(self.config_entry.options)

        schema = vol.Schema(
            {
                vol.Required(SECTION_TRAVEL_TIMING): section(
                    _travel_timing_schema(),
                    {"collapsed": False},
                ),
                vol.Required(SECTION_ADVANCED): section(
                    _advanced_schema(),
                    {"collapsed": True},
                ),
            }
        )

        # Build suggested values from current options
        suggested: dict[str, Any] = {
            SECTION_TRAVEL_TIMING: {
                k: current[k]
                for k in (
                    CONF_TRAVELLING_TIME_DOWN,
                    CONF_TRAVELLING_TIME_UP,
                    CONF_TILTING_TIME_DOWN,
                    CONF_TILTING_TIME_UP,
                    CONF_TRAVEL_MOVES_WITH_TILT,
                )
                if k in current
            },
            SECTION_ADVANCED: {
                k: current[k]
                for k in (
                    CONF_TRAVEL_STARTUP_DELAY,
                    CONF_TILT_STARTUP_DELAY,
                    CONF_MIN_MOVEMENT_TIME,
                    CONF_TRAVEL_DELAY_AT_END,
                )
                if k in current
            },
        }

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )


class CoverTimeBasedSubentryFlow(ConfigSubentryFlow):
    """Handle subentry flow for adding/editing a cover entity."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle adding a new cover subentry."""
        return await self._async_handle_step(user_input, is_new=True)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguring an existing cover subentry."""
        return await self._async_handle_step(user_input, is_new=False)

    async def _async_handle_step(
        self, user_input: dict[str, Any] | None, *, is_new: bool
    ) -> SubentryFlowResult:
        """Handle the cover configuration form."""
        if user_input is not None:
            return self._save(user_input, is_new=is_new)

        # Build schema
        schema = self._build_schema()

        # Get suggested values for reconfigure
        suggested: dict[str, Any] = {}
        if not is_new:
            suggested = self._get_suggested_values()

        step_id = "user" if is_new else "reconfigure"
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )

    def _build_schema(self) -> vol.Schema:
        """Build the cover configuration schema."""
        fields: dict[vol.Marker, Any] = {}

        # Name
        fields[vol.Required("name")] = TextSelector()

        # Device type selector
        fields[vol.Required(CONF_DEVICE_TYPE, default=DEVICE_TYPE_SWITCH)] = (
            SelectSelector(
                SelectSelectorConfig(
                    options=[DEVICE_TYPE_SWITCH, DEVICE_TYPE_COVER],
                    translation_key="device_type",
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        )

        # Switch entity IDs
        switch_selector = EntitySelector(
            EntitySelectorConfig(domain=["switch", "input_boolean"])
        )
        fields[vol.Optional(CONF_OPEN_SWITCH_ENTITY_ID)] = switch_selector
        fields[vol.Optional(CONF_CLOSE_SWITCH_ENTITY_ID)] = switch_selector
        fields[vol.Optional(CONF_STOP_SWITCH_ENTITY_ID)] = switch_selector

        # Cover entity ID
        fields[vol.Optional(CONF_COVER_ENTITY_ID)] = EntitySelector(
            EntitySelectorConfig(domain="cover")
        )

        # Input mode
        fields[vol.Optional(CONF_INPUT_MODE, default=INPUT_MODE_SWITCH)] = (
            SelectSelector(
                SelectSelectorConfig(
                    options=[INPUT_MODE_SWITCH, INPUT_MODE_PULSE, INPUT_MODE_TOGGLE],
                    translation_key="input_mode",
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        )

        # Pulse time
        fields[vol.Optional(CONF_PULSE_TIME)] = NumberSelector(
            NumberSelectorConfig(
                min=0.1, max=10, step=0.1, mode=NumberSelectorMode.BOX
            )
        )

        # Travel timing section (collapsed)
        fields[vol.Required(SECTION_TRAVEL_TIMING)] = section(
            _travel_timing_schema(),
            {"collapsed": True},
        )

        # Advanced section (collapsed)
        fields[vol.Required(SECTION_ADVANCED)] = section(
            _advanced_schema(),
            {"collapsed": True},
        )

        return vol.Schema(fields)

    def _get_suggested_values(self) -> dict[str, Any]:
        """Get suggested values from existing subentry data."""
        data = dict(self._get_reconfigure_subentry().data)
        suggested: dict[str, Any] = {}

        # Top-level fields
        for key in (
            "name",
            CONF_DEVICE_TYPE,
            CONF_OPEN_SWITCH_ENTITY_ID,
            CONF_CLOSE_SWITCH_ENTITY_ID,
            CONF_STOP_SWITCH_ENTITY_ID,
            CONF_COVER_ENTITY_ID,
            CONF_INPUT_MODE,
            CONF_PULSE_TIME,
        ):
            if key in data:
                suggested[key] = data[key]

        # Section fields
        travel_keys = (
            CONF_TRAVELLING_TIME_DOWN,
            CONF_TRAVELLING_TIME_UP,
            CONF_TILTING_TIME_DOWN,
            CONF_TILTING_TIME_UP,
            CONF_TRAVEL_MOVES_WITH_TILT,
        )
        advanced_keys = (
            CONF_TRAVEL_STARTUP_DELAY,
            CONF_TILT_STARTUP_DELAY,
            CONF_MIN_MOVEMENT_TIME,
            CONF_TRAVEL_DELAY_AT_END,
        )
        suggested[SECTION_TRAVEL_TIMING] = {
            k: data[k] for k in travel_keys if k in data
        }
        suggested[SECTION_ADVANCED] = {
            k: data[k] for k in advanced_keys if k in data
        }

        return suggested

    def _save(
        self, user_input: dict[str, Any], *, is_new: bool
    ) -> SubentryFlowResult:
        """Save the subentry data."""
        # Flatten sections into top-level data
        data: dict[str, Any] = {}
        for key, value in user_input.items():
            if key in (SECTION_TRAVEL_TIMING, SECTION_ADVANCED):
                if isinstance(value, dict):
                    data.update(value)
            else:
                data[key] = value

        name = data.pop("name")

        if is_new:
            return self.async_create_entry(title=name, data=data)

        return self.async_update_reload_and_abort(
            self._get_entry(),
            self._get_reconfigure_subentry(),
            title=name,
            data=data,
        )
