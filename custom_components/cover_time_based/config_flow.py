"""Config flow for Cover Time Based integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.helpers.selector import TextSelector

from .cover import DOMAIN


class CoverTimeBasedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cover Time Based."""

    VERSION = 3

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a new time-based cover helper."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={},
                options={},
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): TextSelector(),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)
