"""Tests for external state change handling in all cover modes.

Covers the _handle_external_state_change methods in:
- cover_switch.py (SwitchCoverTimeBased base for pulse/toggle)
- cover_switch_mode.py (SwitchModeCover override for latching)
- cover_wrapped.py (WrappedCoverTimeBased for wrapped cover entities)
"""

import pytest
from unittest.mock import patch

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from custom_components.cover_time_based.cover import INPUT_MODE_PULSE, INPUT_MODE_TOGGLE


# ===================================================================
# SwitchCoverTimeBased._handle_external_state_change (pulse/toggle base)
# ===================================================================


class TestPulseModeExternalStateChange:
    """Test external state changes in pulse mode (base SwitchCoverTimeBased behavior)."""

    @pytest.mark.asyncio
    async def test_open_pulse_triggers_open(self, make_cover):
        """ON->OFF transition on open switch triggers async_open_cover."""
        cover = make_cover(input_mode=INPUT_MODE_PULSE)
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.open", "on", "off")

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_close_pulse_triggers_close(self, make_cover):
        """ON->OFF transition on close switch triggers async_close_cover."""
        cover = make_cover(input_mode=INPUT_MODE_PULSE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.close", "on", "off")

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_stop_pulse_triggers_stop(self, make_cover):
        """ON->OFF transition on stop switch triggers async_stop_cover."""
        cover = make_cover(input_mode=INPUT_MODE_PULSE, stop_switch="switch.stop")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.stop", "on", "off")

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_off_to_on_ignored(self, make_cover):
        """OFF->ON transitions should be ignored in pulse mode."""
        cover = make_cover(input_mode=INPUT_MODE_PULSE)
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.open", "off", "on")

        # No movement should have started
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_unknown_entity_ignored(self, make_cover):
        """Transitions on unknown entities should be ignored."""
        cover = make_cover(input_mode=INPUT_MODE_PULSE)
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.unknown", "on", "off")

        assert not cover.travel_calc.is_traveling()


# ===================================================================
# SwitchModeCover._handle_external_state_change (latching relay mode)
# ===================================================================


class TestSwitchModeExternalStateChange:
    """Test external state changes in switch (latching) mode."""

    @pytest.mark.asyncio
    async def test_open_switch_on_triggers_open(self, make_cover):
        """Open switch turning ON triggers open."""
        cover = make_cover()
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.open", "off", "on")

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_open_switch_off_triggers_stop(self, make_cover):
        """Open switch turning OFF triggers stop."""
        cover = make_cover()
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.open", "on", "off")

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_close_switch_on_triggers_close(self, make_cover):
        """Close switch turning ON triggers close."""
        cover = make_cover()
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.close", "off", "on")

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_close_switch_off_triggers_stop(self, make_cover):
        """Close switch turning OFF triggers stop."""
        cover = make_cover()
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.close", "on", "off")

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_stop_switch_on_triggers_stop(self, make_cover):
        """Stop switch turning ON triggers stop."""
        cover = make_cover(stop_switch="switch.stop")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.stop", "off", "on")

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_stop_switch_off_ignored(self, make_cover):
        """Stop switch turning OFF should be ignored."""
        cover = make_cover(stop_switch="switch.stop")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.stop", "on", "off")

        # Should still be closing since stop OFF is ignored
        assert cover._last_command == SERVICE_CLOSE_COVER


# ===================================================================
# Toggle mode external state changes
# ===================================================================


class TestToggleModeExternalStateChange:
    """Test external state changes in toggle mode (inherits pulse behavior)."""

    @pytest.mark.asyncio
    async def test_open_pulse_triggers_open(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.open", "on", "off")

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_close_pulse_triggers_close(self, make_cover):
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.close", "on", "off")

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_open_while_opening_stops(self, make_cover):
        """In toggle mode, open while already opening should stop."""
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.open", "on", "off")

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_close_while_closing_stops(self, make_cover):
        """In toggle mode, close while already closing should stop."""
        cover = make_cover(input_mode=INPUT_MODE_TOGGLE)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.close", "on", "off")

        assert cover._last_command is None


# ===================================================================
# WrappedCoverTimeBased._handle_external_state_change
# ===================================================================


class TestWrappedCoverExternalStateChange:
    """Test external state changes for wrapped cover entities."""

    @pytest.mark.asyncio
    async def test_opening_triggers_open(self, make_cover):
        """Wrapped cover transitioning to 'opening' triggers position tracking."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change(
                "cover.inner", "closed", "opening"
            )

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_closing_triggers_close(self, make_cover):
        """Wrapped cover transitioning to 'closing' triggers position tracking."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change(
                "cover.inner", "open", "closing"
            )

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_stop_from_opening(self, make_cover):
        """Wrapped cover stopping after opening triggers stop."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change(
                "cover.inner", "opening", "open"
            )

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_stop_from_closing(self, make_cover):
        """Wrapped cover stopping after closing triggers stop."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change(
                "cover.inner", "closing", "closed"
            )

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_non_moving_transition_ignored(self, make_cover):
        """Transitions between non-moving states should be ignored."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change(
                "cover.inner", "open", "closed"
            )

        assert not cover.travel_calc.is_traveling()
