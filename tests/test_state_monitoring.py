"""Tests for external state change handling in all cover modes.

Covers the _handle_external_state_change methods in:
- cover_switch.py (SwitchCoverTimeBased base for pulse/toggle)
- cover_switch_mode.py (SwitchModeCover override for latching)
- cover_wrapped.py (WrappedCoverTimeBased for wrapped cover entities)

External state changes only start tracking movement — they never auto-stop,
since we can't reliably know when the motor stopped from switch state alone.
"""

import contextlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.cover import ATTR_CURRENT_POSITION
from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from custom_components.cover_time_based.cover import (
    CONTROL_MODE_PULSE,
    CONTROL_MODE_TOGGLE,
)


def _make_state_event(entity_id, old_state, new_state, *, new_attributes=None):
    """Create a mock state change event like HA fires."""
    old = MagicMock()
    old.state = old_state
    old.attributes = {}
    new = MagicMock()
    new.state = new_state
    new.attributes = new_attributes if new_attributes is not None else {}
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
        """OFF->ON (rising edge) on open switch triggers async_open_cover."""
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.open", "off", "on")

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_close_pulse_triggers_close(self, make_cover):
        """OFF->ON (rising edge) on close switch triggers async_close_cover."""
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.close", "off", "on")

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_stop_pulse_stops_tracker(self, make_cover):
        """OFF->ON (rising edge) on stop switch stops the tracker."""
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.stop", "off", "on")
            finally:
                cover._triggered_externally = False

        assert cover._last_command is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_on_to_off_ignored(self, make_cover):
        """ON->OFF (falling edge / button release) should be ignored in pulse mode."""
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("switch.open", "on", "off")

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

    Toggle mode reacts only to OFF->ON (rising edge). ON->OFF (falling
    edge / relay release) is ignored.

    A debounce (using pulse_time) prevents double-triggering.
    """

    @pytest.mark.asyncio
    async def test_on_to_off_ignored_open(self, make_cover):
        """ON->OFF on open switch is ignored (falling edge)."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.open", "on", "off")
            finally:
                cover._triggered_externally = False

        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_on_to_off_ignored_close(self, make_cover):
        """ON->OFF on close switch is ignored (falling edge)."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change("switch.close", "on", "off")
            finally:
                cover._triggered_externally = False

        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_off_to_on_triggers_open(self, make_cover):
        """OFF->ON on open switch starts opening (rising edge)."""
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
        """OFF->ON on close switch starts closing (rising edge)."""
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
    async def test_off_to_on_while_opening_stops(self, make_cover):
        """OFF->ON on open switch while opening stops the motor.

        Toggle motor controllers latch OFF on a second same-direction pulse.
        The integration mirrors that: a same-direction external toggle during
        travel stops instead of re-issuing the direction.
        """
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

        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_off_to_on_while_closing_stops(self, make_cover):
        """OFF->ON on close switch while closing stops the motor (same-direction toggle)."""
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

        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_debounce_ignores_rapid_second_pulse(self, make_cover):
        """Second OFF->ON within debounce window is ignored (contact bounce)."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                # First rising edge starts tracker
                await cover._handle_external_state_change("switch.open", "off", "on")
                assert cover._last_command == SERVICE_OPEN_COVER
                assert cover.is_opening

                # Second rising edge within debounce window — ignored
                await cover._handle_external_state_change("switch.open", "off", "on")
                assert cover._last_command == SERVICE_OPEN_COVER
                assert cover.is_opening
            finally:
                cover._triggered_externally = False

    @pytest.mark.asyncio
    async def test_debounce_allows_second_click_after_1_second(self, make_cover):
        """Second click ~1s after the first is a legitimate toggle, not a bounce.

        Regression: an earlier debounce window of pulse_time + 0.5 (1.5s with
        default pulse_time=1.0) swallowed deliberate clicks up to 1.5s apart,
        so a "start then stop" cadence got stuck on the start.
        """
        import time as time_module

        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                # Click 1 starts opening
                await cover._handle_external_state_change("switch.open", "off", "on")
                assert cover.is_opening

                # Backdate the recorded click so "now - last" == 1 second
                cover._last_external_toggle_time["switch.open"] = (
                    time_module.monotonic() - 1.0
                )

                # Click 2 at +1s should NOT be debounced → same-direction
                # while opening → stops the motor.
                await cover._handle_external_state_change("switch.open", "off", "on")
                assert not cover.travel_calc.is_traveling()
            finally:
                cover._triggered_externally = False

    @pytest.mark.asyncio
    async def test_full_cycle_same_direction_stops(self, make_cover):
        """Click 1 starts, click 2 (same direction after debounce) stops."""
        import time as time_module

        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                # Click 1: OFF->ON starts opening
                await cover._handle_external_state_change("switch.open", "off", "on")
                assert cover._last_command == SERVICE_OPEN_COVER
                assert cover.is_opening

                # Simulate time passing (well beyond the debounce window)
                cover._last_external_toggle_time["switch.open"] = (
                    time_module.monotonic() - 2.0
                )

                # Click 2: same direction stops the motor (matches toggle
                # hardware where a second same-direction pulse latches OFF).
                await cover._handle_external_state_change("switch.open", "off", "on")
                assert not cover.travel_calc.is_traveling()
            finally:
                cover._triggered_externally = False

    @pytest.mark.asyncio
    async def test_external_close_while_opening_reverses(self, make_cover):
        """External close toggle while opening reverses direction."""
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

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_external_open_while_closing_reverses(self, make_cover):
        """External open toggle while closing reverses direction."""
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

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_ha_ui_close_while_opening_stops(self, make_cover):
        """HA UI close while opening just stops — does NOT reverse. Reversing
        now requires a second click, or use set_cover_position which keeps
        the legacy stop-then-reverse flow."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            # _triggered_externally is False (HA UI trigger)
            await cover.async_close_cover()

        # Stopped, not reversed.
        assert cover._last_command is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_ha_ui_open_while_closing_stops(self, make_cover):
        """HA UI open while closing just stops — does NOT reverse."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            # _triggered_externally is False (HA UI trigger)
            await cover.async_open_cover()

        assert cover._last_command is None
        assert not cover.travel_calc.is_traveling()

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
        """Opening→closing should switch tracker to closing.

        Sets _triggered_externally to mirror how the real listener wraps
        _handle_external_state_change — external triggers preserve the
        legacy stop-then-reverse behavior."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change(
                    "cover.inner", "opening", "closing"
                )
            finally:
                cover._triggered_externally = False

        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_direction_change_closing_to_opening(self, make_cover):
        """Closing→opening should switch tracker to opening."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            cover._triggered_externally = True
            try:
                await cover._handle_external_state_change(
                    "cover.inner", "closing", "opening"
                )
            finally:
                cover._triggered_externally = False

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_non_moving_transition_ignored(self, make_cover):
        """Transitions between non-moving states should be ignored."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("cover.inner", "open", "closed")

        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_opening_to_unknown_does_not_stop(self, make_cover):
        """Stateless covers transition to 'unknown' while still moving.

        opening->unknown must NOT be treated as an external stop, because
        'unknown' means 'no state feedback', not 'stopped'.
        """
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change(
                "cover.inner", "opening", "unknown"
            )

        # Tracker should still be running — not stopped
        assert cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_closing_to_unavailable_does_not_stop(self, make_cover):
        """closing->unavailable must NOT be treated as an external stop."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change(
                "cover.inner", "closing", "unavailable"
            )

        assert cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_CLOSE_COVER


class TestWrappedCoverBounceGraceWindow:
    """Bounce-back suppression for misbehaving wrapped covers (e.g. Tuya TS130F).

    Some wrapped cover entities briefly emit a spurious "moving → stopped"
    state transition shortly after acknowledging a movement command — the
    cover bounces back to its pre-command state for a fraction of a second
    before eventually settling. Without protection, our handler interprets
    this as an external stop and aborts position tracking, leaving the
    time-based entity stuck while the physical cover keeps moving.

    After issuing any command to the wrapped cover (open/close/stop) we
    enter a short "grace window" during which external state changes are
    ignored — we trust our own time-based position calculation.
    """

    @pytest.mark.parametrize(
        "start_pos,start_direction,send,old_val,new_val,last_command",
        [
            # Closed (0%) → opening, bounces back to "closed"
            (0, "up", "_send_open", "opening", "closed", SERVICE_OPEN_COVER),
            # 50% (state "open") → opening, bounces back to "open"
            # (direction-consistent bounce — still must be suppressed)
            (50, "up", "_send_open", "opening", "open", SERVICE_OPEN_COVER),
            # 50% (state "open") → closing, bounces back to "open"
            (50, "down", "_send_close", "closing", "open", SERVICE_CLOSE_COVER),
        ],
    )
    @pytest.mark.asyncio
    async def test_bounce_back_within_grace_window_is_suppressed(
        self,
        make_cover,
        start_pos,
        start_direction,
        send,
        old_val,
        new_val,
        last_command,
    ):
        """A wrapped-cover bounce-back arriving within the grace window
        must not stop our position tracker."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(start_pos)
        if start_direction == "up":
            cover.travel_calc.start_travel_up()
        else:
            cover.travel_calc.start_travel_down()
        cover._last_command = last_command

        with patch.object(cover, "async_write_ha_state"):
            await getattr(cover, send)()
            await cover._handle_external_state_change("cover.inner", old_val, new_val)

        assert cover.travel_calc.is_traveling()
        assert cover._last_command == last_command

    @pytest.mark.asyncio
    async def test_external_stop_honored_after_grace_window_expires(self, make_cover):
        """A real external stop occurring outside the grace window is honored."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        # Place the last command timestamp well in the past.
        cover._last_self_command_time = time.monotonic() - 5.0

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("cover.inner", "opening", "open")

        assert cover._last_command is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_no_command_no_grace_window(self, make_cover):
        """With no preceding self-initiated command, external stops are honored.

        Covers the externally-initiated movement path (e.g. another
        integration commanding the wrapped cover): we never sent a
        command, so there is no grace window to suppress anything.
        """
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("cover.inner", "opening", "open")

        assert cover._last_command is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_stop_command_also_starts_grace_window(self, make_cover):
        """_send_stop also opens a grace window for post-stop bounce-back.

        After we issue STOP, the wrapped cover may briefly flip state
        through opening/closing on its way back to a stopped state.
        These should be ignored within the grace window.
        """
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._send_stop()
            # Suppose the wrapped cover briefly re-reports "opening" then
            # settles to "open" within the grace window. Both should be ignored.
            await cover._handle_external_state_change("cover.inner", "opening", "open")

        # Tracker remains as it was — _send_stop itself does not stop tracking
        # (the caller does); we only verify the bounce was not interpreted as
        # a fresh external event.
        assert cover._last_command == SERVICE_OPEN_COVER


class TestWrappedCoverStopThenLateSettle:
    """When the user clicks STOP via the tile card, the wrapped cover may take
    several seconds to settle back to a stopped state (reported behaviour:
    state remains `opening`/`closing` for a few seconds before going to
    `open`/`closed`). Verify our combined grace-window + pending-echo
    protection handles the full timeline correctly.
    """

    @pytest.mark.asyncio
    async def test_late_stop_echo_consumed_by_pending_counter(self, make_cover):
        """The wrapped cover's late settling echo (after grace window has
        expired) must be consumed by the pending counter, not interpreted
        as a fresh external event."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            # User clicks stop on the tile card. _send_stop marks pending=1
            # and opens the bounce grace window.
            await cover._send_stop()
            # Caller (async_stop_cover) freezes the tracker at the calculated
            # position. Simulate that here:
            cover.travel_calc.stop()
            cover._last_command = None

            # Advance time past the grace window — the late echo arrives
            # several seconds after the stop command.
            cover._last_self_command_time = time.monotonic() - 5.0
            assert cover._pending_switch.get("cover.inner") == 1

            # Wrapped cover finally settles: opening → open
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "opening", "open")
            )

        # Echo consumed; tracker still frozen at the calculated position
        assert cover._pending_switch.get("cover.inner") is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_bounce_during_stop_grace_window_does_not_restart_tracker(
        self, make_cover
    ):
        """If the wrapped cover emits a spurious state change within the
        grace window after stop (e.g. opening→closing flip), grace-window
        suppression prevents it from restarting position tracking."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._send_stop()
            cover.travel_calc.stop()
            cover._last_command = None

            # Spurious mid-stop bounce within grace window
            await cover._handle_external_state_change(
                "cover.inner", "opening", "closing"
            )

        # Grace window suppressed; tracker remains frozen
        assert not cover.travel_calc.is_traveling()
        assert cover._last_command is None


def _set_wrapped_state(cover, state, current_position=None):
    """Make cover.hass.states.get return a state with optional current_position."""
    fake_state = MagicMock()
    fake_state.state = state
    attrs = {}
    if current_position is not None:
        attrs[ATTR_CURRENT_POSITION] = current_position
    fake_state.attributes = attrs
    cover.hass.states.get = lambda eid: fake_state if eid == "cover.inner" else None
    return fake_state


def _make_attribute_event(entity_id, state, current_position):
    """Attribute-only state-change event (state unchanged, attribute changed)."""
    return _make_state_event(
        entity_id,
        state,
        state,
        new_attributes={ATTR_CURRENT_POSITION: current_position},
    )


class TestWrappedCoverSnapToReportedPosition:
    """When the wrapped cover transitions to a stopped state, trust the
    position it reports and snap our tracker to match. Handles physical
    switch operation (where state may or may not change) and HA-initiated
    movement that eventually settles to a different position than our
    time-based calc predicted.
    """

    @pytest.mark.parametrize(
        "starting_pos,old_val,new_val,reported_pos,expected_pos",
        [
            # Physical close: state changes open→closed, position reports 0
            (52, "open", "closed", 0, 0),
            # HA-initiated close eventually settles: open→closed, attr=0
            (50, "open", "closed", 0, 0),
            # Physical close where wrapped reports no attribute → state fallback
            (52, "open", "closed", None, 0),
            # Physical open from fully closed: closed→open, attr=100
            (0, "closed", "open", 100, 100),
            # External mid-travel stop: closing→open, attr=30
            (50, "closing", "open", 30, 30),
            # Well-behaved cover endpoint: closing→closed
            (50, "closing", "closed", 0, 0),
        ],
    )
    @pytest.mark.asyncio
    async def test_state_change_to_stopped_snaps_to_reported_position(
        self,
        make_cover,
        starting_pos,
        old_val,
        new_val,
        reported_pos,
        expected_pos,
    ):
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(starting_pos)
        cover._last_command = SERVICE_OPEN_COVER
        _set_wrapped_state(cover, new_val, reported_pos)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("cover.inner", old_val, new_val)

        assert cover.travel_calc.current_position() == expected_pos
        assert cover._last_command is None

    @pytest.mark.asyncio
    async def test_state_open_without_attribute_does_not_snap(self, make_cover):
        """state=open with no position attribute is ambiguous; tracker stops
        but position is not changed (existing fallback preserved)."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER
        _set_wrapped_state(cover, "open", current_position=None)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("cover.inner", "opening", "open")

        assert cover.travel_calc.current_position() == 50
        assert cover._last_command is None
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_attribute_only_update_in_stopped_state_snaps(self, make_cover):
        """Physical-switch open from 52%: wrapped state stays 'open' but
        current_position updates to 100 via attribute change."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(52)
        cover._last_command = None
        _set_wrapped_state(cover, "open", current_position=100)

        event = _make_attribute_event("cover.inner", "open", 100)
        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_attribute_change(event)

        assert cover.travel_calc.current_position() == 100

    @pytest.mark.asyncio
    async def test_attribute_only_update_while_wrapped_moving_ignored(self, make_cover):
        """If wrapped state is opening/closing, position attribute changes
        are mid-travel and we don't trust them."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover._last_command = SERVICE_OPEN_COVER

        event = _make_attribute_event("cover.inner", "opening", 60)
        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_attribute_change(event)

        assert cover.travel_calc.current_position() == 50

    @pytest.mark.asyncio
    async def test_attribute_update_for_unrelated_entity_ignored(self, make_cover):
        """Attribute events for non-wrapped entities (e.g. switches) are ignored."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        _set_wrapped_state(cover, "open", current_position=100)

        event = _make_attribute_event("switch.other", "open", 100)
        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_attribute_change(event)

        # Position unchanged
        assert cover.travel_calc.current_position() == 50

    @pytest.mark.asyncio
    async def test_attribute_update_within_grace_window_ignored(self, make_cover):
        """Bounce grace window applies to attribute updates too."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        _set_wrapped_state(cover, "open", current_position=100)

        event = _make_attribute_event("cover.inner", "open", 100)
        with patch.object(cover, "async_write_ha_state"):
            await cover._send_open()  # opens grace window
            await cover._handle_external_attribute_change(event)

        # Position unchanged — grace window suppressed the snap
        assert cover.travel_calc.current_position() == 50

    @pytest.mark.asyncio
    async def test_snap_while_traveling_with_matching_calc_position_stops_tracker(
        self, make_cover
    ):
        """If the wrapped cover reports a position that happens to equal our
        calculated position at this instant *while* our tracker is still
        traveling, we must still stop the tracker — otherwise the auto-updater
        keeps advancing past the physical cover's actual position."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER
        # Wrapped cover reports the same position our calc currently has.
        _set_wrapped_state(cover, "open", current_position=50)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("cover.inner", "opening", "open")

        assert not cover.travel_calc.is_traveling()
        assert cover._last_command is None


class TestAttributeOnlyReportDuringTimedMove:
    """An underlying that reports current_position mid-travel but never
    opening/closing (e.g. an MQTT cover with a position topic only) stays in
    a stopped state ("open") the whole time it is physically moving. A
    timed (force_time_based_position) move forwards open_cover/close_cover
    and relies on the pending auto-stop (a timed stop_cover) to halt the
    underlying — there is no native endpoint to hold it. A mid-move
    attribute-only position report from such a device must not be read as
    "the cover has settled": snapping to it would stop the tracker
    (set_known_position -> _handle_stop -> stop_auto_updater) and silently
    cancel the pending stop_cover, running the underlying to its endpoint.
    """

    @pytest.mark.asyncio
    async def test_mid_move_attr_report_does_not_kill_pending_auto_stop(
        self, make_cover
    ):
        cover = make_cover(
            cover_entity_id="cover.inner", force_time_based_position=True
        )
        cover.travel_calc.set_position(0)
        _set_wrapped_state(cover, "open", current_position=0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(50)  # timed: open_cover forwarded, stop planned

        assert cover.travel_calc.is_traveling()
        assert cover._self_initiated_movement is True
        sent = [c.args[1] for c in cover.hass.services.async_call.call_args_list]
        assert "open_cover" in sent

        # Device reports an intermediate, already-stale position ~partway in;
        # its state stays "open" the whole move (no opening/closing ever).
        cover._last_self_command_time = None  # past the bounce grace window
        _set_wrapped_state(cover, "open", current_position=10)
        event = _make_attribute_event("cover.inner", "open", 10)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_attribute_change(event)

        # The tracker must still be traveling — the mid-move report is
        # ignored rather than snapped, so the pending auto-stop survives.
        assert cover.travel_calc.is_traveling()

        # When the tracker reaches the target, auto-stop still sends the
        # planned stop_cover — it was never cancelled.
        cover.travel_calc.update_position(50)
        with patch.object(cover, "async_write_ha_state"):
            await cover.auto_stop_if_necessary()

        sent = [c.args[1] for c in cover.hass.services.async_call.call_args_list]
        assert "stop_cover" in sent

    @pytest.mark.asyncio
    async def test_settle_snap_with_no_move_in_flight_still_works(self, make_cover):
        """Control: with no timed move in flight, a settle report from the
        same kind of position-only underlying still snaps as before — only
        the mid-move report is now suppressed."""
        cover = make_cover(
            cover_entity_id="cover.inner", force_time_based_position=True
        )
        cover.travel_calc.set_position(52)
        _set_wrapped_state(cover, "open", current_position=100)

        event = _make_attribute_event("cover.inner", "open", 100)
        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_attribute_change(event)

        assert cover.travel_calc.current_position() == 100
        assert not cover.travel_calc.is_traveling()


class TestAttributeChangeHookDispatch:
    """The _async_switch_state_changed dispatcher must call the new
    _handle_external_attribute_change hook on attribute-only updates,
    while still skipping the echo filter (so that mid-travel attribute
    updates from a wrapped cover don't consume pending echo counts).
    """

    @pytest.mark.asyncio
    async def test_attribute_only_update_dispatches_to_attribute_hook(self, make_cover):
        cover = make_cover(cover_entity_id="cover.inner")

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover,
                "_handle_external_attribute_change",
                new_callable=AsyncMock,
            ) as attr_hook,
            patch.object(
                cover,
                "_handle_external_state_change",
                new_callable=AsyncMock,
            ) as state_hook,
        ):
            event = _make_attribute_event("cover.inner", "open", 100)
            await cover._async_switch_state_changed(event)

        attr_hook.assert_awaited_once()
        state_hook.assert_not_called()

    @pytest.mark.asyncio
    async def test_attribute_only_update_does_not_consume_pending_echo(
        self, make_cover
    ):
        """Critical: attribute-only updates must not consume pending echo
        counts, otherwise a moving wrapped cover's position updates would
        eat the echoes from our subsequent stop commands."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover._mark_switch_pending("cover.inner", 1)
        assert cover._pending_switch["cover.inner"] == 1

        with patch.object(cover, "async_write_ha_state"):
            event = _make_attribute_event("cover.inner", "opening", 50)
            await cover._async_switch_state_changed(event)

        # Pending echo count unchanged
        assert cover._pending_switch.get("cover.inner") == 1


# ===================================================================
# End-to-end tests through _async_switch_state_changed
# (simulates the full HA event pipeline including echo filtering,
# _triggered_externally, and debounce)
# ===================================================================


class TestToggleE2EThroughStateListener:
    """End-to-end tests for toggle mode through the full state listener pipeline.

    External state changes delegate to _handle_external_state_change with
    _triggered_externally=True. The toggle mode handler starts position
    tracking (not clearing).
    """

    @pytest.mark.asyncio
    async def test_latching_open_delegates_to_handler(self, make_cover):
        """Latching switch: click (ON->OFF) delegates to external handler."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_handle_external_state_change", new_callable=AsyncMock
            ) as handler,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "on", "off")
            )

        handler.assert_awaited_once_with("switch.open", "on", "off")

    @pytest.mark.asyncio
    async def test_triggered_externally_during_handler(self, make_cover):
        """_triggered_externally is True during handler, False after."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        captured_flag = None

        async def capture_flag(*_args):
            nonlocal captured_flag
            captured_flag = cover._triggered_externally

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_handle_external_state_change", side_effect=capture_flag
            ),
        ):
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "off", "on")
            )

        assert captured_flag is True
        assert cover._triggered_externally is False

    @pytest.mark.asyncio
    async def test_no_echo_filtering_for_external_clicks(self, make_cover):
        """External clicks should NOT be echo-filtered (no pending echoes)."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(0)

        # Verify no pending echoes
        assert cover._pending_switch.get("switch.open", 0) == 0

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_handle_external_state_change", new_callable=AsyncMock
            ) as handler,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "on", "off")
            )

        # Handler called (not echo-filtered)
        handler.assert_awaited_once()


# ===================================================================
# Startup / reconnect: a switch (re)appearing must not look like a press
# ===================================================================


class TestStartupReappearanceNotTreatedAsPress:
    """Toggle mode with ``relay_reports_off`` disabled.

    Such a relay (e.g. an Aqara T2 in hardware-pulse mode) pulses and releases
    itself but never reports the OFF, so its HA entity stays stuck ``on``. On a
    restart / Zigbee reconnect it reappears as ``unavailable``/``unknown`` ->
    ``on`` — the stale retained state resurfacing, NOT a genuine ``off -> on``
    press. Replaying it as a command starts a phantom movement (tracked, but
    with no relay fired because it's "external") and desyncs the tracker.

    The guard is scoped to exactly this case: relays that report their OFF (the
    default, and every other mode) come back ``off``, so there is nothing to
    guard there and their behaviour is unchanged.
    """

    @staticmethod
    def _toggle_no_off_report(make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover._relay_reports_off = False
        cover.travel_calc.set_position(25)
        return cover

    @pytest.mark.asyncio
    async def test_unavailable_to_on_does_not_trigger(self, make_cover):
        cover = self._toggle_no_off_report(make_cover)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_handle_external_state_change", new_callable=AsyncMock
            ) as handler,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "unavailable", "on")
            )

        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_to_on_does_not_trigger(self, make_cover):
        cover = self._toggle_no_off_report(make_cover)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_handle_external_state_change", new_callable=AsyncMock
            ) as handler,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "unknown", "on")
            )

        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unavailable_to_on_starts_no_movement(self, make_cover):
        """Symptom-level: the cover must not start opening on reappearance."""
        cover = self._toggle_no_off_report(make_cover)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "async_open_cover", new_callable=AsyncMock) as op,
            patch.object(cover, "async_close_cover", new_callable=AsyncMock) as cl,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "unavailable", "on")
            )

        op.assert_not_awaited()
        cl.assert_not_awaited()
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_genuine_off_to_on_still_triggers(self, make_cover):
        """Regression: a real off->on press must still reach the handler."""
        cover = self._toggle_no_off_report(make_cover)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_handle_external_state_change", new_callable=AsyncMock
            ) as handler,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "off", "on")
            )

        handler.assert_awaited_once_with("switch.open", "off", "on")

    @pytest.mark.asyncio
    async def test_dual_relay_reappearance_no_phantom_reverse(self, make_cover):
        """Canonical repro from the reporter's restart log (issue #105).

        On restart BOTH stuck-on relays reappear as ``unknown -> on`` a few ms
        apart: the close relay first (which read as an external close), then the
        open relay (an external open "while closing, reversing") — driving the
        cover to an endpoint with no relay ever fired. Neither edge may start
        movement.
        """
        cover = self._toggle_no_off_report(make_cover)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "async_open_cover", new_callable=AsyncMock) as op,
            patch.object(cover, "async_close_cover", new_callable=AsyncMock) as cl,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("switch.close", "unknown", "on")
            )
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "unknown", "on")
            )

        op.assert_not_awaited()
        cl.assert_not_awaited()
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_default_toggle_reappearance_still_dispatched(self, make_cover):
        """Scope check: a relay that DOES report its OFF (the default) is not
        guarded — its reappearance still reaches the handler unchanged."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        assert cover._relay_reports_off is True
        cover.travel_calc.set_position(25)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_handle_external_state_change", new_callable=AsyncMock
            ) as handler,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "unavailable", "on")
            )

        handler.assert_awaited_once_with("switch.open", "unavailable", "on")


# ===================================================================
# External tilt state changes (pulse mode — base class handler)
# Covers cover_base.py lines 1664-1688
# ===================================================================


class TestExternalTiltPulseMode:
    """Test _handle_external_tilt_state_change in pulse mode (base class).

    Pulse mode: OFF→ON = button press (rising edge).
    Only reacts to OFF→ON transitions; ON→OFF (release) is ignored.
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
    async def test_tilt_open_pulse_off_to_on(self, make_cover):
        """OFF→ON (rising edge) on tilt open switch triggers async_open_cover_tilt."""
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
    async def test_tilt_close_pulse_off_to_on(self, make_cover):
        """OFF→ON (rising edge) on tilt close switch triggers async_close_cover_tilt."""
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
    async def test_tilt_stop_pulse_off_to_on(self, make_cover):
        """OFF→ON (rising edge) on tilt stop switch triggers async_stop_cover."""
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
        assert not cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_on_to_off_ignored(self, make_cover):
        """ON→OFF (falling edge / release) on tilt switches is ignored in pulse mode."""
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
                    "switch.tilt_open", "off", "on"
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

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_handle_external_state_change", new_callable=AsyncMock
            ) as handler,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "open", "closing")
            )

        # Handler should be called (not suppressed by calibration)
        handler.assert_awaited_once_with("cover.inner", "open", "closing")


# ===================================================================
# Raw direction change: echo filtering for all control modes
# (Verifies that _raw_direction_command properly marks pending echoes
# so that state changes from direction reversal don't trigger external
# state handling or position tracking.)
# ===================================================================


def _mock_entity_states(cover, initial_states):
    """Set up hass.states.get to return mock states from a mutable dict.

    Returns the mutable state dict so tests can update states between steps.
    """
    states = dict(initial_states)

    def _get(entity_id):
        s = MagicMock()
        s.state = states.get(entity_id, "off")
        return s

    cover.hass.states.get = _get
    return states


async def _drain_bg_tasks(cover):
    """Wait for all background tasks (pulse completions etc.) to finish."""
    for task in cover.hass._test_tasks:
        if not task.done():
            # A background task failing is not this helper's concern — callers
            # assert on the cover's resulting state, not on task outcomes.
            with contextlib.suppress(Exception):
                await task


class TestRawDirectionChangeEchoFiltering:
    """Raw direction change via calibration buttons must not trigger
    position tracking.

    When using the calibration screen's manual open/close/stop buttons,
    _raw_direction_command sends relay commands and marks expected echoes.
    All resulting state change events must be echo-filtered so that
    _handle_external_state_change is never called.

    Bug fixed: wrapped covers produced 2 state transitions on direction
    change (e.g. closing->open->opening) but only marked 1 pending echo.
    """

    @pytest.mark.asyncio
    async def test_wrapped_close_then_open(self, make_cover):
        """Wrapped: close->open direction change filters both transitions."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        states = _mock_entity_states(cover, {"cover.inner": "open"})

        with patch.object(cover, "async_write_ha_state"):
            # Raw close: inner cover transitions open -> closing (1 echo)
            await cover._raw_direction_command("close")
            states["cover.inner"] = "closing"
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "open", "closing")
            )
            assert not cover.travel_calc.is_traveling()

            # Raw open (direction change): closing->open, then open->opening
            await cover._raw_direction_command("open")

            states["cover.inner"] = "open"
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "closing", "open")
            )
            assert not cover.travel_calc.is_traveling()

            states["cover.inner"] = "opening"
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "open", "opening")
            )
            assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_wrapped_direction_change_with_attribute_updates(self, make_cover):
        """Attribute-only updates during echo window must not consume echo counts.

        Wrapped covers emit opening->opening position updates while moving.
        If these arrive between the raw command and the actual direction change
        transitions, they must not decrement the pending echo counter.
        """
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        states = _mock_entity_states(cover, {"cover.inner": "open"})

        with patch.object(cover, "async_write_ha_state"):
            # Raw open
            await cover._raw_direction_command("open")
            states["cover.inner"] = "opening"
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "open", "opening")
            )
            assert not cover.travel_calc.is_traveling()

            # Raw close (direction change) while inner cover is opening
            await cover._raw_direction_command("close")

            # Attribute-only update arrives (position update from inner cover)
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "opening", "opening")
            )
            assert not cover.travel_calc.is_traveling()

            # Actual transitions: opening->open (stop), open->closing (start)
            states["cover.inner"] = "open"
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "opening", "open")
            )
            assert not cover.travel_calc.is_traveling()

            states["cover.inner"] = "closing"
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "open", "closing")
            )
            assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_wrapped_open_then_close(self, make_cover):
        """Wrapped: open->close direction change filters both transitions."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(50)
        states = _mock_entity_states(cover, {"cover.inner": "open"})

        with patch.object(cover, "async_write_ha_state"):
            # Raw open: inner cover transitions open -> opening (1 echo)
            await cover._raw_direction_command("open")
            states["cover.inner"] = "opening"
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "open", "opening")
            )
            assert not cover.travel_calc.is_traveling()

            # Raw close (direction change): opening->open, then open->closing
            await cover._raw_direction_command("close")

            states["cover.inner"] = "open"
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "opening", "open")
            )
            assert not cover.travel_calc.is_traveling()

            states["cover.inner"] = "closing"
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "open", "closing")
            )
            assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_switch_mode(self, make_cover):
        """Switch mode: close->open direction change filters all relay echoes."""
        cover = make_cover()
        cover.travel_calc.set_position(50)
        states = _mock_entity_states(
            cover, {"switch.open": "off", "switch.close": "off"}
        )

        with patch.object(cover, "async_write_ha_state"):
            # Raw close: turn_on(close_switch) -> 1 echo
            await cover._raw_direction_command("close")
            states["switch.close"] = "on"
            await cover._async_switch_state_changed(
                _make_state_event("switch.close", "off", "on")
            )
            assert not cover.travel_calc.is_traveling()

            # Raw open (direction change): turn_off(close) + turn_on(open)
            await cover._raw_direction_command("open")
            states["switch.close"] = "off"
            states["switch.open"] = "on"

            await cover._async_switch_state_changed(
                _make_state_event("switch.close", "on", "off")
            )
            assert not cover.travel_calc.is_traveling()

            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "off", "on")
            )
            assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_toggle_mode(self, make_cover):
        """Toggle mode: close->open direction change (stop + open) filters all echoes."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover.travel_calc.set_position(50)
        _mock_entity_states(cover, {"switch.open": "off", "switch.close": "off"})

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "_direction_change_delay", new_callable=AsyncMock),
        ):
            # Raw close: single turn_on on the close switch -> one commanded
            # echo. A self-releasing relay then reports OFF on its own (a
            # falling edge, which the toggle handler ignores).
            await cover._raw_direction_command("close")

            await cover._async_switch_state_changed(
                _make_state_event("switch.close", "off", "on")
            )
            await cover._async_switch_state_changed(
                _make_state_event("switch.close", "on", "off")
            )
            assert not cover.travel_calc.is_traveling()

            # Raw open (direction change): stop-pulse on close + open-pulse on open
            await cover._raw_direction_command("open")

            # Stop re-pulse on close: turn_on echo, then the relay self-releases
            await cover._async_switch_state_changed(
                _make_state_event("switch.close", "off", "on")
            )
            await cover._async_switch_state_changed(
                _make_state_event("switch.close", "on", "off")
            )
            assert not cover.travel_calc.is_traveling()

            # Open pulse on open: turn_on echo, then the relay self-releases
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "off", "on")
            )
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "on", "off")
            )
            assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_pulse_mode(self, make_cover):
        """Pulse mode: close->open direction change filters all pulse echoes."""
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        cover.travel_calc.set_position(50)
        _mock_entity_states(
            cover,
            {"switch.open": "off", "switch.close": "off", "switch.stop": "off"},
        )

        with (
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.cover_time_based.cover_pulse_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            # Raw close: pulse on close switch -> 2 echoes (ON + OFF)
            await cover._raw_direction_command("close")
            await _drain_bg_tasks(cover)

            await cover._async_switch_state_changed(
                _make_state_event("switch.close", "off", "on")
            )
            await cover._async_switch_state_changed(
                _make_state_event("switch.close", "on", "off")
            )
            assert not cover.travel_calc.is_traveling()

            # Raw open (direction change): pulse on open switch -> 2 echoes
            await cover._raw_direction_command("open")
            await _drain_bg_tasks(cover)

            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "off", "on")
            )
            await cover._async_switch_state_changed(
                _make_state_event("switch.open", "on", "off")
            )
            assert not cover.travel_calc.is_traveling()


class TestPulseModeScriptEntities:
    """Pulse mode works with `script` entities (issue #82).

    A script auto-returns to 'off' when it finishes. These tests pin the
    two behaviors that make scripts safe in pulse mode:
      - a manual run (off->on) is detected as the external command;
      - the auto-return (on->off) is ignored, so no spurious stop;
      - an integration-initiated run + auto-return is fully echo-filtered.
    """

    @pytest.mark.asyncio
    async def test_manual_script_run_detected_as_open(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_PULSE,
            open_switch="script.open_blind",
            close_switch="script.close_blind",
            stop_switch="script.stop_blind",
        )
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("script.open_blind", "off", "on")

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_script_auto_return_to_off_is_ignored(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_PULSE,
            open_switch="script.open_blind",
            close_switch="script.close_blind",
            stop_switch="script.stop_blind",
        )
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("script.open_blind", "on", "off")

        # OFF edge ignored in pulse mode — no movement, no stop.
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_integration_run_and_autoreturn_are_echo_filtered(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_PULSE,
            open_switch="script.open_blind",
            close_switch="script.close_blind",
            stop_switch="script.stop_blind",
        )
        # _send_open marks the open entity pending=2 (expects on + off).
        cover._pending_switch["script.open_blind"] = 2

        on_event = _make_state_event("script.open_blind", "off", "on")
        off_event = _make_state_event("script.open_blind", "on", "off")

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_handle_external_state_change", new_callable=AsyncMock
            ) as handler,
        ):
            await cover._async_switch_state_changed(on_event)
            await cover._async_switch_state_changed(off_event)

        # Both transitions consumed as echoes — external handler never fires.
        handler.assert_not_awaited()
        assert "script.open_blind" not in cover._pending_switch


class TestWrappedCoverIgnoreReportedPosition:
    """With ignore_reported_position set, the wrapper never trusts the
    underlying cover's reported current_position. It tracks position purely
    by time, behaving like a cover that reports no position at all. The
    unambiguous closed endpoint is still honored (it is a state, not a
    reported position number).
    """

    @pytest.mark.asyncio
    async def test_stopped_state_does_not_snap_to_reported_position(self, make_cover):
        cover = make_cover(cover_entity_id="cover.inner", ignore_reported_position=True)
        cover.travel_calc.set_position(52)
        cover._last_command = SERVICE_OPEN_COVER
        _set_wrapped_state(cover, "open", current_position=100)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("cover.inner", "opening", "open")

        # Reported 100 must be ignored; tracker stays where time-based calc put it.
        assert cover.travel_calc.current_position() == 52

    @pytest.mark.asyncio
    async def test_attribute_only_update_does_not_snap(self, make_cover):
        cover = make_cover(cover_entity_id="cover.inner", ignore_reported_position=True)
        cover.travel_calc.set_position(52)
        cover._last_command = None
        _set_wrapped_state(cover, "open", current_position=100)

        event = _make_attribute_event("cover.inner", "open", 100)
        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_attribute_change(event)

        assert cover.travel_calc.current_position() == 52

    @pytest.mark.asyncio
    async def test_still_snaps_to_zero_on_closed_state(self, make_cover):
        cover = make_cover(cover_entity_id="cover.inner", ignore_reported_position=True)
        cover.travel_calc.set_position(52)
        cover._last_command = SERVICE_CLOSE_COVER
        # Reported 80 is bogus, but the closed *state* is trusted.
        _set_wrapped_state(cover, "closed", current_position=80)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change(
                "cover.inner", "closing", "closed"
            )

        assert cover.travel_calc.current_position() == 0

    @pytest.mark.asyncio
    async def test_default_still_snaps_to_reported_position(self, make_cover):
        """Sanity: without the flag, the existing snap behavior is unchanged."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(52)
        cover._last_command = SERVICE_OPEN_COVER
        _set_wrapped_state(cover, "open", current_position=100)

        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_state_change("cover.inner", "opening", "open")

        assert cover.travel_calc.current_position() == 100


class TestWrappedCoverReportsCommandNotEndpoint:
    """With reports_command_not_endpoint, the wrapped entity's state is a
    command echo, never an endpoint. The attribute-only update path must be
    suppressed too — otherwise an attribute update while the device sits in
    'closed' would snap to 0% via the state==closed shortcut, the very snap
    this option exists to prevent (issue #137).
    """

    @pytest.mark.asyncio
    async def test_attribute_only_update_in_closed_state_does_not_snap(
        self, make_cover
    ):
        cover = make_cover(
            cover_entity_id="cover.inner", reports_command_not_endpoint=True
        )
        # Tracker is mid-close at 70% (a timed close started by a 'closed'
        # command echo); the device still reports its 'closed' command state.
        cover.travel_calc.set_position(70)
        _set_wrapped_state(cover, "closed", current_position=None)

        event = _make_attribute_event("cover.inner", "closed", None)
        with (
            patch.object(cover, "_snap_to_position") as snap,
            patch.object(cover, "async_write_ha_state"),
        ):
            await cover._handle_external_attribute_change(event)

        snap.assert_not_called()
        assert cover.travel_calc.current_position() == 70

    @pytest.mark.asyncio
    async def test_default_attribute_update_still_snaps(self, make_cover):
        """Sanity: without the flag, the attribute-change snap is unchanged."""
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(52)
        cover._last_command = None
        _set_wrapped_state(cover, "open", current_position=100)

        event = _make_attribute_event("cover.inner", "open", 100)
        with patch.object(cover, "async_write_ha_state"):
            await cover._handle_external_attribute_change(event)

        assert cover.travel_calc.current_position() == 100

    @pytest.mark.asyncio
    async def test_external_close_command_sends_no_service_call(self, make_cover):
        """End-to-end through the dispatcher: an external 'closed' command-echo
        starts a timed close but bounces NO cover.* service call back to the
        wrapped entity. The async_* path runs with _triggered_externally set by
        the dispatcher, so it tracks by time without re-commanding the device.
        """
        cover = make_cover(
            cover_entity_id="cover.inner", reports_command_not_endpoint=True
        )
        cover.travel_calc.set_position(100)
        cover.start_auto_updater = MagicMock()  # don't schedule real timers
        _set_wrapped_state(cover, "closed", current_position=None)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "async_schedule_update_ha_state"),
        ):
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "open", "closed")
            )

        # A timed close started...
        assert cover.travel_calc.is_closing()
        # ...and nothing was bounced back to the wrapped cover entity.
        cover.hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_reconnect_unknown_routes_to_stop(self, make_cover):
        """A reconnect surfacing through the dispatcher as 'unavailable ->
        unknown' is treated as the stop command (freeze), not ignored."""
        cover = make_cover(
            cover_entity_id="cover.inner", reports_command_not_endpoint=True
        )
        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "async_stop_cover", new=AsyncMock()) as stop_mock,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "unavailable", "unknown")
            )

        stop_mock.assert_awaited_once()


class TestWrappedCoverReappearance:
    """A wrapped entity dropping out and returning must not move the tracker.

    Issue #160: an inverted awning wrapping a no-feedback cover entity logged
    `Non disponibile -> Chiuso -> Aperto` within the same second on every
    dropout — the returning entity's bare `closed` was read as an endpoint and
    snapped through _invert_position(0) to 100.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("invert", [True, False])
    async def test_dropout_and_return_keeps_tracked_position(self, make_cover, invert):
        cover = make_cover(cover_entity_id="cover.inner", invert=invert)
        # Deliberately not an endpoint: seeded at 0 the buggy snap target and
        # the correct answer coincide when invert is off, so the assertion
        # would pass against the unfixed code.
        cover.travel_calc.set_position(40)
        _set_wrapped_state(cover, "unavailable", current_position=None)

        with patch.object(cover, "async_write_ha_state"):
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "closed", "unavailable")
            )
            # The awning integration reloads and initialises to 'closed'.
            _set_wrapped_state(cover, "closed", current_position=None)
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "unavailable", "closed")
            )

        assert cover.travel_calc.current_position() == 40

    @pytest.mark.asyncio
    async def test_returning_with_a_reported_position_is_trusted(self, make_cover):
        cover = make_cover(cover_entity_id="cover.inner")
        cover.travel_calc.set_position(0)
        _set_wrapped_state(cover, "open", current_position=60)

        with patch.object(cover, "async_write_ha_state"):
            await cover._async_switch_state_changed(
                _make_state_event(
                    "cover.inner",
                    "unavailable",
                    "open",
                    new_attributes={ATTR_CURRENT_POSITION: 60},
                )
            )

        assert cover.travel_calc.current_position() == 60

    @pytest.mark.asyncio
    async def test_command_echo_dropout_and_return_runs_no_travel(self, make_cover):
        """The command-echo half, end to end through the dispatcher: the
        retained `closed` resurfacing must not start a timed travel."""
        cover = make_cover(
            cover_entity_id="cover.inner",
            reports_command_not_endpoint=True,
            invert=True,
        )
        cover.travel_calc.set_position(0)
        _set_wrapped_state(cover, "closed", current_position=None)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock,
            patch.object(cover, "async_close_cover", new=AsyncMock()) as close_mock,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "unavailable", "closed")
            )

        open_mock.assert_not_awaited()
        close_mock.assert_not_awaited()
        assert cover.travel_calc.current_position() == 0

    @pytest.mark.asyncio
    async def test_attribute_touch_after_the_return_does_not_snap(self, make_cover):
        """A reconnect is more than one event: whatever attribute the entity
        settles next must not snap us to the endpoint we just refused."""
        cover = make_cover(cover_entity_id="cover.inner", invert=True)
        cover.travel_calc.set_position(0)
        _set_wrapped_state(cover, "closed", current_position=None)

        with patch.object(cover, "async_write_ha_state"):
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "unavailable", "closed")
            )
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "closed", "closed")
            )

        assert cover.travel_calc.current_position() == 0

    @pytest.mark.asyncio
    async def test_command_echo_two_step_reconnect_runs_no_travel(self, make_cover):
        """unavailable -> unknown -> closed is one reconnect: the stop is
        honoured, the retained `closed` behind it is not a command."""
        cover = make_cover(
            cover_entity_id="cover.inner",
            reports_command_not_endpoint=True,
            invert=True,
        )
        cover.travel_calc.set_position(0)
        _set_wrapped_state(cover, "closed", current_position=None)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock,
            patch.object(cover, "async_close_cover", new=AsyncMock()) as close_mock,
        ):
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "unavailable", "unknown")
            )
            await cover._async_switch_state_changed(
                _make_state_event("cover.inner", "unknown", "closed")
            )

        open_mock.assert_not_awaited()
        close_mock.assert_not_awaited()
        assert cover.travel_calc.current_position() == 0
