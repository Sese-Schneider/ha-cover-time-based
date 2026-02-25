"""Tests for external state change handling in all cover modes.

Covers the _handle_external_state_change methods in:
- cover_switch.py (SwitchCoverTimeBased base for pulse/toggle)
- cover_switch_mode.py (SwitchModeCover override for latching)
- cover_wrapped.py (WrappedCoverTimeBased for wrapped cover entities)

External state changes only start tracking movement — they never auto-stop,
since we can't reliably know when the motor stopped from switch state alone.
"""

import pytest
from unittest.mock import MagicMock, patch

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from custom_components.cover_time_based.cover import (
    CONTROL_MODE_PULSE,
    CONTROL_MODE_TOGGLE,
)


def _make_state_event(entity_id, old_state, new_state):
    """Create a mock state change event like HA fires."""
    old = MagicMock()
    old.state = old_state
    new = MagicMock()
    new.state = new_state
    event = MagicMock()
    event.data = {
        "entity_id": entity_id,
        "old_state": old,
        "new_state": new,
    }
    return event


# ===================================================================
# SwitchCoverTimeBased._handle_external_state_change (pulse/toggle base)
# ===================================================================


class TestPulseModeExternalStateChange:
    """Test external state changes in pulse mode (base SwitchCoverTimeBased behavior)."""

    @pytest.mark.asyncio
    async def test_open_pulse_triggers_open(self, make_cover):
        """ON->OFF transition on open switch triggers async_open_cover."""
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.open", "on", "off")

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_close_pulse_triggers_close(self, make_cover):
        """ON->OFF transition on close switch triggers async_close_cover."""
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.close", "on", "off")

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_stop_pulse_stops_tracker(self, make_cover):
        """ON->OFF transition on stop switch stops the tracker."""
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.stop", "on", "off")
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_off_to_on_ignored(self, make_cover):
        """OFF->ON transitions should be ignored in pulse mode."""
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.open", "off", "on")

        # No movement should have started
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_unknown_entity_ignored(self, make_cover):
        """Transitions on unknown entities should be ignored."""
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
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
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.open", "off", "on")

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_open_switch_off_stops_tracker(self, make_cover):
        """Open switch turning OFF while opening stops the tracker."""
        cover = make_cover()
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.open", "on", "off")
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_open_switch_off_when_idle_is_noop(self, make_cover):
        """Open switch turning OFF when not moving is a no-op."""
        cover = make_cover()
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.open", "on", "off")
            finally:
                cover._triggered_externally = False

        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_close_switch_on_triggers_close(self, make_cover):
        """Close switch turning ON triggers close."""
        cover = make_cover()
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.close", "off", "on")

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_close_switch_off_stops_tracker(self, make_cover):
        """Close switch turning OFF while closing stops the tracker."""
        cover = make_cover()
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.close", "on", "off")
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_close_switch_off_when_idle_is_noop(self, make_cover):
        """Close switch turning OFF when not moving is a no-op."""
        cover = make_cover()
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.close", "on", "off")
            finally:
                cover._triggered_externally = False

        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_stop_switch_ignored(self, make_cover):
        """Stop switch turning ON is ignored (no auto-stop)."""
        cover = make_cover(stop_switch="switch.stop")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.stop", "off", "on")

        # Should still be closing — stop is ignored externally
        assert cover._last_command == SERVICE_CLOSE_COVER


# ===================================================================
# Toggle mode external state changes
# ===================================================================


class TestToggleModeExternalStateChange:
    """Test external state changes in toggle mode.

    Toggle mode reacts to BOTH OFF->ON and ON->OFF transitions,
    unlike pulse mode which only reacts to ON->OFF. This handles
    latching switches that alternate between ON/OFF on each click.

    A debounce (using pulse_time) prevents double-triggering for
    momentary switches that produce OFF->ON->OFF in rapid succession.
    """

    @pytest.mark.asyncio
    async def test_on_to_off_triggers_open(self, make_cover):
        """ON->OFF on open switch starts opening."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.open", "on", "off")
            finally:
                cover._triggered_externally = False

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_on_to_off_triggers_close(self, make_cover):
        """ON->OFF on close switch starts closing."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.close", "on", "off")
            finally:
                cover._triggered_externally = False

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_off_to_on_triggers_open(self, make_cover):
        """OFF->ON on open switch starts opening (latching switch)."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.open", "off", "on")
            finally:
                cover._triggered_externally = False

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_off_to_on_triggers_close(self, make_cover):
        """OFF->ON on close switch starts closing (latching switch)."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.close", "off", "on")
            finally:
                cover._triggered_externally = False

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_on_to_off_while_opening_stops(self, make_cover):
        """ON->OFF on open switch while opening should stop."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.open", "on", "off")
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_off_to_on_while_opening_stops(self, make_cover):
        """OFF->ON on open switch while opening should stop (latching switch)."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.open", "off", "on")
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_on_to_off_while_closing_stops(self, make_cover):
        """ON->OFF on close switch while closing should stop."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.close", "on", "off")
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_off_to_on_while_closing_stops(self, make_cover):
        """OFF->ON on close switch while closing should stop (latching switch)."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.close", "off", "on")
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_momentary_debounce(self, make_cover):
        """Momentary switch (OFF->ON->OFF) should only trigger once due to debounce."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                # First transition: OFF->ON — starts tracker
                await cover._handle_external_state_change("switch.open", "off", "on")
                assert cover._last_command == SERVICE_OPEN_COVER
                assert cover.is_opening

                # Second transition: ON->OFF within pulse_time — debounced
                # (Without debounce, this would call async_open_cover,
                # see is_opening=True, and stop the tracker)
                await cover._handle_external_state_change("switch.open", "on", "off")
                # Tracker should still be running (debounced)
                assert cover._last_command == SERVICE_OPEN_COVER
                assert cover.is_opening
            finally:
                cover._triggered_externally = False

    @pytest.mark.asyncio
    async def test_latching_full_cycle(self, make_cover):
        """Latching switch: click 1 starts, click 2 stops (transitions > pulse_time apart)."""
        import time as time_module

        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                # Click 1: ON->OFF starts opening
                await cover._handle_external_state_change("switch.open", "on", "off")
                assert cover._last_command == SERVICE_OPEN_COVER
                assert cover.is_opening

                # Simulate time passing (beyond debounce window = pulse_time + 0.5)
                cover._last_external_toggle_time["switch.open"] = (
                    time_module.monotonic() - cover._pulse_time - 0.5 - 0.1
                )

                # Click 2: OFF->ON stops (is_opening -> async_stop_cover)
                await cover._handle_external_state_change("switch.open", "off", "on")
                assert cover._last_command is None
                assert not cover.is_opening
            finally:
                cover._triggered_externally = False

    @pytest.mark.asyncio
    async def test_external_close_while_opening_stops(self, make_cover):
        """External close toggle while opening should stop, not reverse."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.close", "off", "on")
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_external_open_while_closing_stops(self, make_cover):
        """External open toggle while closing should stop, not reverse."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.open", "off", "on")
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_ha_ui_close_while_opening_reverses(self, make_cover):
        """HA UI close while opening should reverse direction (not just stop)."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            # _triggered_externally is False (HA UI trigger)
            await cover.async_close_cover()

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_ha_ui_open_while_closing_reverses(self, make_cover):
        """HA UI open while closing should reverse direction (not just stop)."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            # _triggered_externally is False (HA UI trigger)
            await cover.async_open_cover()

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_unknown_entity_ignored(self, make_cover):
        """Transitions on unknown entities should be ignored."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.unknown", "on", "off")
            finally:
                cover._triggered_externally = False

        assert not cover.travel_calc.is_traveling()


# ===================================================================
# WrappedCoverTimeBased._handle_external_state_change
# ===================================================================


class TestWrappedCoverExternalStateChange:
    """Test external state changes for wrapped cover entities."""

    @pytest.mark.asyncio
    async def test_opening_triggers_open(self, make_cover):
        """Wrapped cover transitioning to 'opening' triggers position tracking."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change(
                "cover.inner", "closed", "opening"
            )

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_closing_triggers_close(self, make_cover):
        """Wrapped cover transitioning to 'closing' triggers position tracking."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("cover.inner", "open", "closing")

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_stop_from_opening_stops_tracker(self, make_cover):
        """Wrapped cover stopping should stop the position tracker."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("cover.inner", "opening", "open")

        assert cover._last_command is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_stop_from_closing_stops_tracker(self, make_cover):
        """Wrapped cover stopping should stop the position tracker."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change(
                "cover.inner", "closing", "closed"
            )

        assert cover._last_command is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_direction_change_opening_to_closing(self, make_cover):
        """Opening→closing should switch tracker to closing."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change(
                "cover.inner", "opening", "closing"
            )

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_direction_change_closing_to_opening(self, make_cover):
        """Closing→opening should switch tracker to opening."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change(
                "cover.inner", "closing", "opening"
            )

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_non_moving_transition_ignored(self, make_cover):
        """Transitions between non-moving states should be ignored."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("cover.inner", "open", "closed")

        assert not cover.travel_calc.is_traveling()


# ===================================================================
# End-to-end tests through _async_switch_state_changed
# (simulates the full HA event pipeline including echo filtering,
# _triggered_externally, and debounce)
# ===================================================================


class TestToggleE2EThroughStateListener:
    """End-to-end tests for toggle mode through the full state listener pipeline.

    With the new behavior, external state changes (via _async_switch_state_changed)
    call _handle_stop() and travel_calc.clear_position(), making position Unknown.
    The mode-specific _handle_external_state_change is no longer called.
    """

    @pytest.mark.asyncio
    async def test_latching_open_clears_position(self, make_cover):
        """Latching switch: click (ON->OFF) clears travel position."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "on", "off")
            )

        # Position should be cleared (Unknown)
        assert cover.travel_calc.current_position() is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_latching_open_reversed_initial_clears_position(self, make_cover):
        """Latching switch: click (OFF->ON) clears travel position."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "off", "on")
            )

        assert cover.travel_calc.current_position() is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_momentary_both_transitions_clear_position(self, make_cover):
        """Momentary switch: OFF->ON clears position, ON->OFF also clears position."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            # Momentary press: OFF->ON
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "off", "on")
            )
            assert cover.travel_calc.current_position() is None

            # Momentary auto-reset: ON->OFF — position stays None
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "on", "off")
            )
            assert cover.travel_calc.current_position() is None

    @pytest.mark.asyncio
    async def test_second_click_keeps_position_none(self, make_cover):
        """Second external click also clears position (stays None)."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            # Click 1: OFF->ON clears position
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "off", "on")
            )

        assert cover.travel_calc.current_position() is None

        with patch.object(cover, "async_write_ha_state"):
            # Click 2: ON->OFF — position stays None
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "on", "off")
            )

        assert cover.travel_calc.current_position() is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_no_echo_filtering_for_external_clicks(self, make_cover):
        """External clicks should NOT be echo-filtered (no pending echoes)."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        # Verify no pending echoes
        assert cover._pending_switch.get("switch.open", 0) == 0

        with patch.object(cover, "async_write_ha_state"):
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "on", "off")
            )

        # Handler should have cleared position (not echo-filtered)
        assert cover.travel_calc.current_position() is None


# ===================================================================
# External tilt state changes (pulse mode — base class handler)
# Covers cover_base.py lines 1664-1688
# ===================================================================


class TestExternalTiltPulseMode:
    """Test _handle_external_tilt_state_change in pulse mode (base class).

    Pulse mode: ON→OFF = command complete (pulse finished).
    Only reacts to ON→OFF transitions; OFF→ON is ignored.
    """

    def _make_tilt_cover(self, make_cover):
        return make_cover(
            control_mode=CONTROL_MODE_PULSE,
            stop_switch="switch.stop",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )

    @pytest.mark.asyncio
    async def test_tilt_open_pulse_on_to_off(self, make_cover):
        """ON→OFF on tilt open switch triggers async_open_cover_tilt."""
        cover = self._make_tilt_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_open", "on", "off"
                )
            finally:
                cover._triggered_externally = False

        assert cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_close_pulse_on_to_off(self, make_cover):
        """ON→OFF on tilt close switch triggers async_close_cover_tilt."""
        cover = self._make_tilt_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_close", "on", "off"
                )
            finally:
                cover._triggered_externally = False

        assert cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_stop_pulse_on_to_off(self, make_cover):
        """ON→OFF on tilt stop switch triggers async_stop_cover."""
        cover = self._make_tilt_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)
        cover.tilt_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_stop", "on", "off"
                )
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None
        assert not cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_non_pulse_ignored(self, make_cover):
        """OFF→ON transitions on tilt switches are ignored in pulse mode."""
        cover = self._make_tilt_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_open", "off", "on"
                )
            finally:
                cover._triggered_externally = False

        assert not cover.tilt_calc.is_traveling()


# ===================================================================
# External tilt state changes (switch/latching mode)
# Covers cover_switch_mode.py lines 50-77
# ===================================================================


class TestExternalTiltSwitchMode:
    """Test _handle_external_tilt_state_change in switch (latching) mode.

    ON = relay is driving the motor → start tracking.
    OFF = relay released → stop tracking.
    """

    def _make_tilt_cover(self, make_cover):
        # control_mode defaults to CONTROL_MODE_SWITCH in make_cover
        return make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )

    @pytest.mark.asyncio
    async def test_tilt_open_on(self, make_cover):
        """Tilt open switch ON triggers async_open_cover_tilt."""
        cover = self._make_tilt_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_open", "off", "on"
                )
            finally:
                cover._triggered_externally = False

        assert cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_open_off_stops(self, make_cover):
        """Tilt open switch OFF stops the tilt tracker."""
        cover = self._make_tilt_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)
        cover.tilt_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_open", "on", "off"
                )
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_tilt_close_on(self, make_cover):
        """Tilt close switch ON triggers async_close_cover_tilt."""
        cover = self._make_tilt_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_close", "off", "on"
                )
            finally:
                cover._triggered_externally = False

        assert cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_close_off_stops(self, make_cover):
        """Tilt close switch OFF stops the tilt tracker."""
        cover = self._make_tilt_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)
        cover.tilt_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_close", "on", "off"
                )
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_tilt_stop_on(self, make_cover):
        """Tilt stop switch ON triggers async_stop_cover."""
        cover = self._make_tilt_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)
        cover.tilt_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_stop", "off", "on"
                )
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None


# ===================================================================
# External tilt state changes (toggle mode)
# Covers cover_toggle_mode.py lines 128-166
# ===================================================================


class TestExternalTiltToggleMode:
    """Test _handle_external_tilt_state_change in toggle mode.

    Uses debounce + toggle logic. If tilt is already traveling,
    any toggle is treated as stop. If idle, dispatches open/close.
    """

    def _make_tilt_cover(self, make_cover):
        return make_cover(
            control_mode=CONTROL_MODE_TOGGLE,
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )

    @pytest.mark.asyncio
    async def test_tilt_open_toggle_when_idle(self, make_cover):
        """Toggle tilt open switch when idle → opens tilt."""
        cover = self._make_tilt_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_open", "off", "on"
                )
            finally:
                cover._triggered_externally = False

        assert cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_open_toggle_while_traveling_stops(self, make_cover):
        """Toggle tilt open switch while tilt is traveling → stops."""
        cover = self._make_tilt_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)
        cover.tilt_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_open", "on", "off"
                )
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_tilt_close_toggle_when_idle(self, make_cover):
        """Toggle tilt close switch when idle → closes tilt."""
        cover = self._make_tilt_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_close", "off", "on"
                )
            finally:
                cover._triggered_externally = False

        assert cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_toggle_debounced(self, make_cover):
        """Second toggle within debounce window is ignored."""
        cover = self._make_tilt_cover(make_cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                # First toggle: starts opening tilt
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_open", "off", "on"
                )
                assert cover.tilt_calc.is_traveling()

                # Second toggle within debounce window: ignored
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_open", "on", "off"
                )
                # Should still be traveling (debounced, not stopped)
                assert cover.tilt_calc.is_traveling()
            finally:
                cover._triggered_externally = False


# ===================================================================
# Same-state (attribute-only) transitions
# ===================================================================


class TestSameStateTransitionsIgnored:
    """Attribute-only state changes (e.g. position updates) should not
    trigger external state handling."""

    @pytest.mark.asyncio
    async def test_wrapped_closing_to_closing_ignored(self, make_cover):
        """Wrapped cover 'closing → closing' should not call async_close_cover."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "async_close_cover") as mock_close,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "closing", "closing")
            )
            mock_close.assert_not_called()

    @pytest.mark.asyncio
    async def test_wrapped_opening_to_opening_ignored(self, make_cover):
        """Wrapped cover 'opening → opening' should not call async_open_cover."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(0)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "async_open_cover") as mock_open,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "opening", "opening")
            )
            mock_open.assert_not_called()

    @pytest.mark.asyncio
    async def test_switch_on_to_on_ignored(self, make_cover):
        """Switch 'on → on' attribute update should not trigger external handling."""
        cover = make_cover()
        cover.travel_calc.set_position(0)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "_handle_external_state_change") as mock_handler,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "on", "on")
            )
            mock_handler.assert_not_called()


# ===================================================================
# Calibration suppresses external state handling
# ===================================================================


class TestCalibrationSuppressesExternalState:
    """During calibration, external state changes must not trigger
    movement lifecycle — calibration drives the motors directly."""

    @pytest.mark.asyncio
    async def test_wrapped_state_change_ignored_during_calibration(self, make_cover):
        """Wrapped cover state changes should be skipped while calibrating."""
        from custom_components.cover_time_based.calibration import CalibrationState

        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover._calibration = CalibrationState(attribute="travel_time_close", timeout=60)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "async_close_cover") as mock_close,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "open", "closing")
            )
            mock_close.assert_not_called()

    @pytest.mark.asyncio
    async def test_switch_state_change_ignored_during_calibration(self, make_cover):
        """Switch state changes should be skipped while calibrating."""
        from custom_components.cover_time_based.calibration import CalibrationState

        cover = make_cover()
        cover.travel_calc.set_position(0)
        cover._calibration = CalibrationState(attribute="travel_time_open", timeout=60)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "_handle_external_state_change") as mock_handler,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "on", "off")
            )
            mock_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_state_change_works_after_calibration_ends(self, make_cover):
        """After calibration is cleared, external state changes work again."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(100)
        cover._calibration = None  # No calibration active

        with patch.object(cover, "async_write_ha_state"):
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "open", "closing")
            )

        # Position should be cleared (external state change clears position)
        assert cover.travel_calc.current_position() is None
        assert not cover.travel_calc.is_traveling()
