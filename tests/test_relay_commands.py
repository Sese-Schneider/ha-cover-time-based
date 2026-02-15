"""Characterization tests for CoverTimeBased._async_handle_command.

Each test class covers one input mode and verifies the exact sequence
of service calls that the current implementation sends to Home Assistant.
"""

import pytest
from unittest.mock import AsyncMock, call, patch

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
)

from custom_components.cover_time_based.cover import (
    INPUT_MODE_PULSE,
    INPUT_MODE_SWITCH,
    INPUT_MODE_TOGGLE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calls(mock: AsyncMock):
    """Return the list of calls made on hass.services.async_call."""
    return mock.call_args_list


def _ha(service, entity_id):
    """Shorthand for a homeassistant.turn_on / turn_off call."""
    return call("homeassistant", service, {"entity_id": entity_id}, False)


def _cover_svc(service, entity_id):
    """Shorthand for a cover domain service call."""
    return call("cover", service, {"entity_id": entity_id}, False)


# ===================================================================
# Switch mode
# ===================================================================

class TestSwitchModeClose:
    """CLOSE command in switch mode."""

    @pytest.mark.asyncio
    async def test_close_turns_off_open_and_on_close(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_SWITCH)
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_close_with_stop_switch_turns_it_off(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_SWITCH, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
            _ha("turn_off", "switch.stop"),
        ]


class TestSwitchModeOpen:
    """OPEN command in switch mode."""

    @pytest.mark.asyncio
    async def test_open_turns_off_close_and_on_open(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_SWITCH)
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_open_with_stop_switch_turns_it_off(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_SWITCH, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
            _ha("turn_off", "switch.stop"),
        ]


class TestSwitchModeStop:
    """STOP command in switch mode."""

    @pytest.mark.asyncio
    async def test_stop_turns_off_both_switches(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_SWITCH)
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_with_stop_switch_turns_it_on(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_SWITCH, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.stop"),
        ]


# ===================================================================
# Pulse mode
# ===================================================================

class TestPulseModeClose:
    """CLOSE command in pulse mode."""

    @pytest.mark.asyncio
    async def test_close_pulses_close_switch(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_PULSE)
        with patch.object(cover, "async_write_ha_state"), \
             patch("custom_components.cover_time_based.cover_pulse_mode.sleep", new_callable=AsyncMock):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
            # after pulse sleep
            _ha("turn_off", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_close_with_stop_switch(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_PULSE, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"), \
             patch("custom_components.cover_time_based.cover_pulse_mode.sleep", new_callable=AsyncMock):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
            _ha("turn_off", "switch.stop"),
            # after pulse sleep
            _ha("turn_off", "switch.close"),
        ]


class TestPulseModeOpen:
    """OPEN command in pulse mode."""

    @pytest.mark.asyncio
    async def test_open_pulses_open_switch(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_PULSE)
        with patch.object(cover, "async_write_ha_state"), \
             patch("custom_components.cover_time_based.cover_pulse_mode.sleep", new_callable=AsyncMock):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
            # after pulse sleep
            _ha("turn_off", "switch.open"),
        ]


class TestPulseModeStop:
    """STOP command in pulse mode."""

    @pytest.mark.asyncio
    async def test_stop_without_stop_switch(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_PULSE)
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_with_stop_switch_pulses_it(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_PULSE, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"), \
             patch("custom_components.cover_time_based.cover_pulse_mode.sleep", new_callable=AsyncMock):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.stop"),
            # after pulse sleep
            _ha("turn_off", "switch.stop"),
        ]


# ===================================================================
# Toggle mode
# ===================================================================

class TestToggleModeClose:
    """CLOSE command in toggle mode."""

    @pytest.mark.asyncio
    async def test_close_pulses_close_switch(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)
        with patch.object(cover, "async_write_ha_state"), \
             patch("custom_components.cover_time_based.cover_toggle_mode.sleep", new_callable=AsyncMock):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
            # after pulse sleep
            _ha("turn_off", "switch.close"),
        ]


class TestToggleModeOpen:
    """OPEN command in toggle mode."""

    @pytest.mark.asyncio
    async def test_open_pulses_open_switch(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)
        with patch.object(cover, "async_write_ha_state"), \
             patch("custom_components.cover_time_based.cover_toggle_mode.sleep", new_callable=AsyncMock):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
            # after pulse sleep
            _ha("turn_off", "switch.open"),
        ]


class TestToggleModeStop:
    """STOP command in toggle mode."""

    @pytest.mark.asyncio
    async def test_stop_after_close_pulses_close_switch(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)
        cover._last_command = SERVICE_CLOSE_COVER
        with patch.object(cover, "async_write_ha_state"), \
             patch("custom_components.cover_time_based.cover_toggle_mode.sleep", new_callable=AsyncMock):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.close"),
            # after pulse sleep
            _ha("turn_off", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_stop_after_open_pulses_open_switch(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)
        cover._last_command = SERVICE_OPEN_COVER
        with patch.object(cover, "async_write_ha_state"), \
             patch("custom_components.cover_time_based.cover_toggle_mode.sleep", new_callable=AsyncMock):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.open"),
            # after pulse sleep
            _ha("turn_off", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_with_no_last_command_does_nothing(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)
        cover._last_command = None
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        # No service calls expected - toggle mode skips stop when
        # there is no prior direction to repeat.
        assert _calls(cover.hass.services.async_call) == []


# ===================================================================
# Wrapped cover entity (delegates to cover.* services)
# ===================================================================

class TestWrappedCoverClose:
    """CLOSE command delegated to a wrapped cover entity."""

    @pytest.mark.asyncio
    async def test_close_delegates_to_cover_service(self, make_cover):
        cover = make_cover(cover_entity_id="cover.inner")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("close_cover", "cover.inner"),
        ]


class TestWrappedCoverOpen:
    """OPEN command delegated to a wrapped cover entity."""

    @pytest.mark.asyncio
    async def test_open_delegates_to_cover_service(self, make_cover):
        cover = make_cover(cover_entity_id="cover.inner")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("open_cover", "cover.inner"),
        ]


class TestWrappedCoverStop:
    """STOP command delegated to a wrapped cover entity."""

    @pytest.mark.asyncio
    async def test_stop_delegates_to_cover_service(self, make_cover):
        cover = make_cover(cover_entity_id="cover.inner")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("stop_cover", "cover.inner"),
        ]
