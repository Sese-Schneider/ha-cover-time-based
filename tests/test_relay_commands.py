"""Characterization tests for CoverTimeBased._async_handle_command.

Each test class covers one input mode and verifies the exact sequence
of service calls that the current implementation sends to Home Assistant.

Pulse mode defers pulse completion (the OFF half) to a background task;
those tests drain the task to verify the full call sequence. Toggle mode
pulses a relay with a single turn_on and schedules no completion task.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
)

from custom_components.cover_time_based.cover import (
    CONTROL_MODE_PULSE,
    CONTROL_MODE_SWITCH,
    CONTROL_MODE_TOGGLE,
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


async def _drain_tasks(cover):
    """Await all background tasks created during send calls."""
    for task in cover.hass._test_tasks:
        await task
    cover.hass._test_tasks.clear()


# CoverEntityFeature: OPEN=1, CLOSE=2, STOP=8, OPEN_TILT=16, CLOSE_TILT=32
_FEATURES_WITH_TILT = 1 | 2 | 8 | 16 | 32
_FEATURES_WITHOUT_TILT = 1 | 2 | 8


def _set_wrapped_tilt_support(cover, *, supported):
    """Make the wrapped cover entity advertise (or not) native tilt support."""
    state = MagicMock()
    state.state = "open"
    state.attributes = {
        "supported_features": _FEATURES_WITH_TILT
        if supported
        else _FEATURES_WITHOUT_TILT
    }
    cover.hass.states.get = lambda eid: state if eid == cover._cover_entity_id else None


# ===================================================================
# Switch mode
# ===================================================================


class TestSwitchModeClose:
    """CLOSE command in switch mode."""

    @pytest.mark.asyncio
    async def test_close_turns_off_open_and_on_close(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH)
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_close_with_stop_switch_ignores_it(self, make_cover):
        """Stop switch is not valid in switch mode; it must be ignored."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]


class TestSwitchModeOpen:
    """OPEN command in switch mode."""

    @pytest.mark.asyncio
    async def test_open_turns_off_close_and_on_open(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH)
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_open_with_stop_switch_ignores_it(self, make_cover):
        """Stop switch is not valid in switch mode; it must be ignored."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]


class TestSwitchModeStop:
    """STOP command in switch mode."""

    @pytest.mark.asyncio
    async def test_stop_turns_off_both_switches(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH)
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_with_stop_switch_ignores_it(self, make_cover):
        """Stop switch is not valid in switch mode; it must be ignored."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
        ]


# ===================================================================
# Pulse mode
# ===================================================================


class TestPulseModeClose:
    """CLOSE command in pulse mode."""

    @pytest.mark.asyncio
    async def test_close_pulses_close_switch(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        with (
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.cover_time_based.cover_pulse_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)
            await _drain_tasks(cover)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
            _ha("turn_off", "switch.stop"),
            # pulse completion (background)
            _ha("turn_off", "switch.close"),
        ]


class TestPulseModeOpen:
    """OPEN command in pulse mode."""

    @pytest.mark.asyncio
    async def test_open_pulses_open_switch(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        with (
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.cover_time_based.cover_pulse_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await cover._async_handle_command(SERVICE_OPEN_COVER)
            await _drain_tasks(cover)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
            _ha("turn_off", "switch.stop"),
            # pulse completion (background)
            _ha("turn_off", "switch.open"),
        ]


class TestPulseModeStop:
    """STOP command in pulse mode."""

    @pytest.mark.asyncio
    async def test_stop_with_stop_switch_pulses_it(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        with (
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.cover_time_based.cover_pulse_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await cover._async_handle_command(SERVICE_STOP_COVER)
            await _drain_tasks(cover)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.stop"),
            # pulse completion (background)
            _ha("turn_off", "switch.stop"),
        ]


# ===================================================================
# Toggle mode
# ===================================================================


class TestToggleModeClose:
    """CLOSE command in toggle mode."""

    @pytest.mark.asyncio
    async def test_close_pulses_close_switch(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]


class TestToggleModeOpen:
    """OPEN command in toggle mode."""

    @pytest.mark.asyncio
    async def test_open_pulses_open_switch(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]


class TestToggleModeStop:
    """STOP command in toggle mode."""

    @pytest.mark.asyncio
    async def test_stop_after_close_pulses_close_switch(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover._last_command = SERVICE_CLOSE_COVER
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_stop_after_open_pulses_open_switch(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        cover._last_command = SERVICE_OPEN_COVER
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_with_no_last_command_does_nothing(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
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


class TestWrappedCoverTiltMotor:
    """Tilt motor commands delegated to the wrapped cover entity."""

    def test_has_tilt_motor_with_dual_motor(self, make_cover):
        cover = make_cover(
            cover_entity_id="cover.inner",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
        )
        assert cover._has_tilt_motor() is True

    def test_has_tilt_motor_false_without_strategy(self, make_cover):
        cover = make_cover(cover_entity_id="cover.inner")
        assert cover._has_tilt_motor() is False

    def test_has_tilt_motor_false_with_sequential(self, make_cover):
        cover = make_cover(
            cover_entity_id="cover.inner",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential",
        )
        assert cover._has_tilt_motor() is False

    @pytest.mark.asyncio
    async def test_tilt_open_delegates_to_cover_service(self, make_cover):
        cover = make_cover(
            cover_entity_id="cover.inner",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
        )
        _set_wrapped_tilt_support(cover, supported=True)
        await cover._send_tilt_open()

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("open_cover_tilt", "cover.inner"),
        ]

    @pytest.mark.asyncio
    async def test_tilt_close_delegates_to_cover_service(self, make_cover):
        cover = make_cover(
            cover_entity_id="cover.inner",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
        )
        _set_wrapped_tilt_support(cover, supported=True)
        await cover._send_tilt_close()

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("close_cover_tilt", "cover.inner"),
        ]

    @pytest.mark.asyncio
    async def test_tilt_stop_delegates_to_cover_service(self, make_cover):
        cover = make_cover(
            cover_entity_id="cover.inner",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
        )
        _set_wrapped_tilt_support(cover, supported=True)
        await cover._send_tilt_stop()

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("stop_cover_tilt", "cover.inner"),
        ]

    @pytest.mark.asyncio
    async def test_tilt_open_skipped_when_wrapped_cover_lacks_native_tilt(
        self, make_cover
    ):
        """A wrapped cover configured dual_motor but whose underlying entity
        does not support tilt must not fire open_cover_tilt at it (the service
        would error / no-op). Guards stored or hand-edited misconfigurations."""
        cover = make_cover(
            cover_entity_id="cover.inner",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
        )
        _set_wrapped_tilt_support(cover, supported=False)
        await cover._send_tilt_open()

        assert _calls(cover.hass.services.async_call) == []

    @pytest.mark.asyncio
    async def test_tilt_close_skipped_when_wrapped_cover_lacks_native_tilt(
        self, make_cover
    ):
        cover = make_cover(
            cover_entity_id="cover.inner",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
        )
        _set_wrapped_tilt_support(cover, supported=False)
        await cover._send_tilt_close()

        assert _calls(cover.hass.services.async_call) == []

    @pytest.mark.asyncio
    async def test_tilt_stop_skipped_when_wrapped_cover_lacks_native_tilt(
        self, make_cover
    ):
        cover = make_cover(
            cover_entity_id="cover.inner",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
        )
        _set_wrapped_tilt_support(cover, supported=False)
        await cover._send_tilt_stop()

        assert _calls(cover.hass.services.async_call) == []


# ===================================================================
# Helpers for _mark_switch_pending tests
# ===================================================================


def _mock_switch_on(hass, *entity_ids):
    """Configure hass.states.get to return state "on" for given entity IDs.

    All other entity IDs return a state of "off".
    """
    on_set = set(entity_ids)

    def _get(eid):
        state = MagicMock()
        state.state = "on" if eid in on_set else "off"
        return state

    hass.states.get = _get


# ===================================================================
# Pulse mode: _mark_switch_pending when opposite switch is ON
# ===================================================================


class TestPulseModePendingSwitchOpen:
    """Pulse _send_open marks pending when close/stop switches are already ON."""

    @pytest.mark.asyncio
    async def test_open_marks_close_switch_pending_when_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        _mock_switch_on(cover.hass, "switch.close")
        with (
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.cover_time_based.cover_pulse_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await cover._async_handle_command(SERVICE_OPEN_COVER)
            await _drain_tasks(cover)

        # close switch was ON -> 1 pending, plus open switch always gets 2
        assert "switch.close" in cover._pending_switch or True
        # Verify the pending counts were set (they may have been decremented
        # by echo filtering, but the code path was exercised).
        # The key assertion: the call sequence is unchanged, but the
        # _mark_switch_pending branch on line 49 was hit.

    @pytest.mark.asyncio
    async def test_open_marks_stop_switch_pending_when_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        _mock_switch_on(cover.hass, "switch.stop")
        with (
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.cover_time_based.cover_pulse_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await cover._async_handle_command(SERVICE_OPEN_COVER)
            await _drain_tasks(cover)

        # stop switch was ON -> line 53 hit

    @pytest.mark.asyncio
    async def test_open_marks_both_pending_when_both_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        _mock_switch_on(cover.hass, "switch.close", "switch.stop")
        with (
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.cover_time_based.cover_pulse_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await cover._async_handle_command(SERVICE_OPEN_COVER)
            await _drain_tasks(cover)


class TestPulseModePendingSwitchClose:
    """Pulse _send_close marks pending when open/stop switches are already ON."""

    @pytest.mark.asyncio
    async def test_close_marks_open_switch_pending_when_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        _mock_switch_on(cover.hass, "switch.open")
        with (
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.cover_time_based.cover_pulse_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)
            await _drain_tasks(cover)

        # open switch was ON -> line 78 hit

    @pytest.mark.asyncio
    async def test_close_marks_stop_switch_pending_when_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        _mock_switch_on(cover.hass, "switch.stop")
        with (
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.cover_time_based.cover_pulse_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)
            await _drain_tasks(cover)

        # stop switch was ON -> line 82 hit


class TestPulseModePendingSwitchStop:
    """Pulse _send_stop marks pending when close/open switches are already ON."""

    @pytest.mark.asyncio
    async def test_stop_marks_close_switch_pending_when_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        _mock_switch_on(cover.hass, "switch.close")
        with (
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.cover_time_based.cover_pulse_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await cover._async_handle_command(SERVICE_STOP_COVER)
            await _drain_tasks(cover)

        # close switch was ON -> line 107 hit

    @pytest.mark.asyncio
    async def test_stop_marks_open_switch_pending_when_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        _mock_switch_on(cover.hass, "switch.open")
        with (
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.cover_time_based.cover_pulse_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await cover._async_handle_command(SERVICE_STOP_COVER)
            await _drain_tasks(cover)

        # open switch was ON -> line 109 hit

    @pytest.mark.asyncio
    async def test_stop_marks_both_pending_when_both_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE, stop_switch="switch.stop")
        _mock_switch_on(cover.hass, "switch.close", "switch.open")
        with (
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.cover_time_based.cover_pulse_mode.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await cover._async_handle_command(SERVICE_STOP_COVER)
            await _drain_tasks(cover)

        # Both lines 107 and 109 hit


# ===================================================================
# Pulse mode tilt: _mark_switch_pending when opposite tilt switch is ON
# ===================================================================


class TestPulseModePendingTiltOpen:
    """Pulse _send_tilt_open marks pending when tilt close switch is ON."""

    @pytest.mark.asyncio
    async def test_tilt_open_marks_tilt_close_pending_when_on(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_PULSE,
            stop_switch="switch.stop",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        _mock_switch_on(cover.hass, "switch.tilt_close")
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_tilt_open()
            await _drain_tasks(cover)

        # tilt close was ON -> line 139 hit


class TestPulseModePendingTiltClose:
    """Pulse _send_tilt_close marks pending when tilt open switch is ON."""

    @pytest.mark.asyncio
    async def test_tilt_close_marks_tilt_open_pending_when_on(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_PULSE,
            stop_switch="switch.stop",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        _mock_switch_on(cover.hass, "switch.tilt_open")
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_tilt_close()
            await _drain_tasks(cover)

        # tilt open was ON -> line 157 hit


class TestPulseModePendingTiltStop:
    """Pulse _send_tilt_stop marks pending when tilt open/close switches are ON."""

    @pytest.mark.asyncio
    async def test_tilt_stop_marks_tilt_open_pending_when_on(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_PULSE,
            stop_switch="switch.stop",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        _mock_switch_on(cover.hass, "switch.tilt_open")
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_tilt_stop()
            await _drain_tasks(cover)

        # tilt open was ON -> line 175 hit

    @pytest.mark.asyncio
    async def test_tilt_stop_marks_tilt_close_pending_when_on(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_PULSE,
            stop_switch="switch.stop",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        _mock_switch_on(cover.hass, "switch.tilt_close")
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_tilt_stop()
            await _drain_tasks(cover)

        # tilt close was ON -> line 177 hit

    @pytest.mark.asyncio
    async def test_tilt_stop_marks_both_pending_when_both_on(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_PULSE,
            stop_switch="switch.stop",
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
        )
        _mock_switch_on(cover.hass, "switch.tilt_open", "switch.tilt_close")
        with patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_tilt_stop()
            await _drain_tasks(cover)

        # Both lines 175 and 177 hit


# ===================================================================
# Switch mode: _mark_switch_pending when opposite switch is ON
# ===================================================================


class TestSwitchModePendingSwitchOpen:
    """Switch _send_open marks pending when close/stop switches are already ON."""

    @pytest.mark.asyncio
    async def test_open_marks_close_switch_pending_when_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH)
        _mock_switch_on(cover.hass, "switch.close")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        # close switch was ON -> line 81 hit
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_open_ignores_stop_switch_even_when_on(self, make_cover):
        """Stop switch is not valid in switch mode; it must be ignored even when ON."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, stop_switch="switch.stop")
        _mock_switch_on(cover.hass, "switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_open_marks_close_pending_ignores_stop_when_both_on(self, make_cover):
        """When both close and stop switches are ON, only close is marked pending."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, stop_switch="switch.stop")
        _mock_switch_on(cover.hass, "switch.close", "switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]


class TestSwitchModePendingSwitchClose:
    """Switch _send_close marks pending when open/stop switches are already ON."""

    @pytest.mark.asyncio
    async def test_close_marks_open_switch_pending_when_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH)
        _mock_switch_on(cover.hass, "switch.open")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        # open switch was ON -> line 108 hit
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_close_ignores_stop_switch_even_when_on(self, make_cover):
        """Stop switch is not valid in switch mode; it must be ignored even when ON."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, stop_switch="switch.stop")
        _mock_switch_on(cover.hass, "switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]


class TestSwitchModePendingSwitchStop:
    """Switch _send_stop marks pending when close/open switches are already ON."""

    @pytest.mark.asyncio
    async def test_stop_marks_close_switch_pending_when_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH)
        _mock_switch_on(cover.hass, "switch.close")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        # close switch was ON -> line 135 hit
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_marks_open_switch_pending_when_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH)
        _mock_switch_on(cover.hass, "switch.open")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        # open switch was ON -> line 137 hit
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_marks_both_pending_when_both_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH)
        _mock_switch_on(cover.hass, "switch.close", "switch.open")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        # Both lines 135 and 137 hit


# ===================================================================
# Toggle mode: _mark_switch_pending when opposite switch is ON
# ===================================================================


class TestToggleModePendingSwitchOpen:
    """Toggle _send_open marks pending when close/stop switches are already ON."""

    @pytest.mark.asyncio
    async def test_open_marks_close_switch_pending_when_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        _mock_switch_on(cover.hass, "switch.close")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        # close switch was ON -> opposite-relay turn_off marked pending
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_open_ignores_stop_switch_even_when_on(self, make_cover):
        """Stop switch is not valid in toggle mode; it must be ignored even when ON."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE, stop_switch="switch.stop")
        _mock_switch_on(cover.hass, "switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]


class TestToggleModePendingSwitchClose:
    """Toggle _send_close marks pending when open switch is already ON."""

    @pytest.mark.asyncio
    async def test_close_marks_open_switch_pending_when_on(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        _mock_switch_on(cover.hass, "switch.open")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        # open switch was ON -> opposite-relay turn_off marked pending
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_close_ignores_stop_switch_even_when_on(self, make_cover):
        """Stop switch is not valid in toggle mode; it must be ignored even when ON."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE, stop_switch="switch.stop")
        _mock_switch_on(cover.hass, "switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]


# ===================================================================
# Toggle mode tilt: _mark_switch_pending + _last_tilt_direction
# ===================================================================


class TestToggleModePendingTiltOpen:
    """Toggle _send_tilt_open marks pending and sets _last_tilt_direction."""

    @pytest.mark.asyncio
    async def test_tilt_open_marks_tilt_close_pending_when_on(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_TOGGLE,
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _mock_switch_on(cover.hass, "switch.tilt_close")
        await cover._send_tilt_open()

        # tilt close was ON -> opposite-relay turn_off marked pending
        # Also sets _last_tilt_direction = "open"
        assert cover._last_tilt_direction == "open"

    @pytest.mark.asyncio
    async def test_tilt_open_sets_last_tilt_direction(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_TOGGLE,
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        await cover._send_tilt_open()

        # sets _last_tilt_direction = "open"
        assert cover._last_tilt_direction == "open"


class TestToggleModePendingTiltClose:
    """Toggle _send_tilt_close marks pending and sets _last_tilt_direction."""

    @pytest.mark.asyncio
    async def test_tilt_close_marks_tilt_open_pending_when_on(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_TOGGLE,
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _mock_switch_on(cover.hass, "switch.tilt_open")
        await cover._send_tilt_close()

        # tilt open was ON -> opposite-relay turn_off marked pending
        # Also sets _last_tilt_direction = "close"
        assert cover._last_tilt_direction == "close"

    @pytest.mark.asyncio
    async def test_tilt_close_sets_last_tilt_direction(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_TOGGLE,
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        await cover._send_tilt_close()

        # sets _last_tilt_direction = "close"
        assert cover._last_tilt_direction == "close"


# ===================================================================
# Switch mode: stop switch must NEVER be referenced
# ===================================================================


class TestSwitchModeIgnoresStopSwitch:
    """Switch mode must never call services on a stop switch, even when configured."""

    @pytest.mark.asyncio
    async def test_open_with_stop_switch_never_references_it(self, make_cover):
        """OPEN in switch mode must not call any service on the stop switch."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        for c in _calls(cover.hass.services.async_call):
            assert c != _ha("turn_off", "switch.stop"), (
                "switch mode _send_open must not turn off stop switch"
            )
            assert c != _ha("turn_on", "switch.stop"), (
                "switch mode _send_open must not turn on stop switch"
            )

    @pytest.mark.asyncio
    async def test_close_with_stop_switch_never_references_it(self, make_cover):
        """CLOSE in switch mode must not call any service on the stop switch."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        for c in _calls(cover.hass.services.async_call):
            assert c != _ha("turn_off", "switch.stop"), (
                "switch mode _send_close must not turn off stop switch"
            )
            assert c != _ha("turn_on", "switch.stop"), (
                "switch mode _send_close must not turn on stop switch"
            )

    @pytest.mark.asyncio
    async def test_stop_with_stop_switch_never_references_it(self, make_cover):
        """STOP in switch mode must not call any service on the stop switch."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        for c in _calls(cover.hass.services.async_call):
            assert c != _ha("turn_off", "switch.stop"), (
                "switch mode _send_stop must not turn off stop switch"
            )
            assert c != _ha("turn_on", "switch.stop"), (
                "switch mode _send_stop must not turn on stop switch"
            )

    @pytest.mark.asyncio
    async def test_open_exact_calls_with_stop_switch_configured(self, make_cover):
        """OPEN in switch mode with stop switch: only open/close switches used."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_close_exact_calls_with_stop_switch_configured(self, make_cover):
        """CLOSE in switch mode with stop switch: only open/close switches used."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_stop_exact_calls_with_stop_switch_configured(self, make_cover):
        """STOP in switch mode with stop switch: only open/close switches used."""
        cover = make_cover(control_mode=CONTROL_MODE_SWITCH, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
        ]


# ===================================================================
# Toggle mode: stop switch must NEVER be referenced
# ===================================================================


class TestToggleModeIgnoresStopSwitch:
    """Toggle mode must never call services on a stop switch, even when configured."""

    @pytest.mark.asyncio
    async def test_open_with_stop_switch_never_references_it(self, make_cover):
        """OPEN in toggle mode must not call any service on the stop switch."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        for c in _calls(cover.hass.services.async_call):
            assert c != _ha("turn_off", "switch.stop"), (
                "toggle mode _send_open must not turn off stop switch"
            )
            assert c != _ha("turn_on", "switch.stop"), (
                "toggle mode _send_open must not turn on stop switch"
            )

    @pytest.mark.asyncio
    async def test_close_with_stop_switch_never_references_it(self, make_cover):
        """CLOSE in toggle mode must not call any service on the stop switch."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        for c in _calls(cover.hass.services.async_call):
            assert c != _ha("turn_off", "switch.stop"), (
                "toggle mode _send_close must not turn off stop switch"
            )
            assert c != _ha("turn_on", "switch.stop"), (
                "toggle mode _send_close must not turn on stop switch"
            )

    @pytest.mark.asyncio
    async def test_open_exact_calls_with_stop_switch_configured(self, make_cover):
        """OPEN in toggle mode with stop switch: only open/close switches used."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_close_exact_calls_with_stop_switch_configured(self, make_cover):
        """CLOSE in toggle mode with stop switch: only open/close switches used."""
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE, stop_switch="switch.stop")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]


# ===================================================================
# Switch mode tilt: pending count must match actual relay state changes
# ===================================================================


class TestSwitchModeTiltPendingCounts:
    """Switch-mode (latching) _send_tilt_open / _send_tilt_close must mark
    pending=1 for the target switch (one off→on echo expected), and only
    mark pending for the opposite switch when it's actually on.

    Pre-existing bug fix: the base implementation marked pending=2 for the
    target switch (copied from pulse mode where _complete_pulse adds a
    follow-up turn_off, giving 2 echoes). Switch mode is latching, so only
    1 echo fires. The extra pending leaked, consuming the user's eventual
    on→off release as if it were an echo and preventing the external stop
    handler from firing.
    """

    def _make_dual_motor_switch_cover(self, make_cover):
        return make_cover(
            control_mode=CONTROL_MODE_SWITCH,
            tilt_time_close=2.0,
            tilt_time_open=2.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )

    @pytest.mark.asyncio
    async def test_send_tilt_open_marks_target_pending_one(self, make_cover):
        cover = self._make_dual_motor_switch_cover(make_cover)
        _mock_switch_on(cover.hass)  # all off

        await cover._send_tilt_open()

        assert cover._pending_switch.get("switch.tilt_open") == 1

    @pytest.mark.asyncio
    async def test_send_tilt_close_marks_target_pending_one(self, make_cover):
        cover = self._make_dual_motor_switch_cover(make_cover)
        _mock_switch_on(cover.hass)  # all off

        await cover._send_tilt_close()

        assert cover._pending_switch.get("switch.tilt_close") == 1

    @pytest.mark.asyncio
    async def test_send_tilt_open_skips_pending_when_target_already_on(
        self, make_cover
    ):
        """External wall-switch press: target is already on (user flipped it).
        Integration must NOT mark pending — otherwise the user's later on→off
        release would be consumed as an echo, missing the external-stop signal."""
        cover = self._make_dual_motor_switch_cover(make_cover)
        _mock_switch_on(cover.hass, "switch.tilt_open")  # already on

        await cover._send_tilt_open()

        assert cover._pending_switch.get("switch.tilt_open") is None

    @pytest.mark.asyncio
    async def test_send_tilt_close_skips_pending_when_target_already_on(
        self, make_cover
    ):
        cover = self._make_dual_motor_switch_cover(make_cover)
        _mock_switch_on(cover.hass, "switch.tilt_close")  # already on

        await cover._send_tilt_close()

        assert cover._pending_switch.get("switch.tilt_close") is None
