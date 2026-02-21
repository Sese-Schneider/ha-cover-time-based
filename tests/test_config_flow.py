"""Tests for CoverTimeBasedConfigFlow."""

import pytest
from unittest.mock import MagicMock

from homeassistant.const import CONF_NAME

from custom_components.cover_time_based.config_flow import CoverTimeBasedConfigFlow


class TestCoverTimeBasedConfigFlow:
    """Test the config flow."""

    @pytest.mark.asyncio
    async def test_step_user_shows_form_when_no_input(self):
        """async_step_user with no input shows the name form."""
        flow = CoverTimeBasedConfigFlow()
        flow.hass = MagicMock()

        result = await flow.async_step_user(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert CONF_NAME in result["data_schema"].schema

    @pytest.mark.asyncio
    async def test_step_user_creates_entry_with_name(self):
        """async_step_user with valid input creates a config entry."""
        flow = CoverTimeBasedConfigFlow()
        flow.hass = MagicMock()

        result = await flow.async_step_user(user_input={CONF_NAME: "Living Room"})

        assert result["type"] == "create_entry"
        assert result["title"] == "Living Room"
        assert result["data"] == {}
        assert result["options"] == {}
