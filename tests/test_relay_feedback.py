"""Tests for the opt-in ``wait_for_relay_feedback`` behaviour (issue #231).

When enabled (every relay-driven mode — switch, toggle, toggle-opposite and
pulse), the travel/tilt timer starts when the relay confirms it switched — the
state-change echo — instead of the instant the non-blocking command is queued.
The variable Zigbee round-trip then falls outside the tracked travel, so the
calculated position no longer drifts ahead of the physical cover on a slow/cold
mesh.

These tests drive real state-change events through ``_async_switch_state_changed``
with an injected command->echo gap, rather than forcing internal flags — the
way past regressions in this echo-handling area slipped past CI.
"""

import asyncio
import contextlib
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, call, patch

import pytest
from homeassistant.const import SERVICE_OPEN_COVER

from custom_components.cover_time_based import cover_base
from custom_components.cover_time_based.calibration import CalibrationState

# A fixed, timezone-aware moment used as the relay echo's ``last_changed``.
FIXED_ECHO = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _stub_switches(cover, *, on=(), optimistic=()):
    """Make ``hass.states.get`` deterministic for the feedback guards.

    Without this the conftest MagicMock hass returns a truthy MagicMock for
    ``attributes.get("assumed_state")``, which would read every relay as
    optimistic. Listed entities are ON and/or optimistic; everything else is a
    plain OFF, non-optimistic switch.
    """

    def _get(entity_id):
        st = MagicMock()
        st.state = "on" if entity_id in on else "off"
        st.attributes = {"assumed_state": True} if entity_id in optimistic else {}
        return st

    cover.hass.states.get = _get


def _echo_event(entity_id, old, new, last_changed=FIXED_ECHO):
    """Build a switch state-change event like HA fires, with a real datetime."""
    old_s = MagicMock()
    old_s.state = old
    old_s.attributes = {}
    new_s = MagicMock()
    new_s.state = new
    new_s.attributes = {}
    new_s.last_changed = last_changed
    event = MagicMock()
    event.data = {"entity_id": entity_id, "old_state": old_s, "new_state": new_s}
    return event


def _ha(service, entity_id):
    """Shorthand for a homeassistant.turn_on / turn_off call."""
    return call("homeassistant", service, {"entity_id": entity_id}, False)


def _taps(cover, entity_id):
    """The taps (``turn_on``) sent to ``entity_id`` on the mock service bus."""
    tap = _ha("turn_on", entity_id)
    return [c for c in cover.hass.services.async_call.call_args_list if c == tap]


class TestRelayFeedbackStart:
    """The travel timer starts on the relay echo, not the queued command."""

    @pytest.mark.asyncio
    async def test_move_parks_until_relay_echo_then_tracks_from_last_changed(
        self, make_cover
    ):
        cover = make_cover(
            wait_for_relay_feedback=True, travel_time_open=30, travel_time_close=30
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)
        echo_time = datetime.now(UTC)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)  # let the feedback task reach its await

            # Command fired, but tracking is parked: position frozen at start.
            assert cover.travel_calc.is_traveling() is False
            assert cover.travel_calc.current_position() == 0
            assert cover._startup_delay_task is not None
            assert cover._feedback_wait_entity == "switch.open"

            # The relay confirms it switched on.
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)  # let the feedback task resume

        assert cover.travel_calc.is_traveling() is True
        # Travel is timestamped from the echo's last_changed.
        assert cover.travel_calc._last_known_position_timestamp == echo_time.timestamp()
        assert cover._feedback_wait_entity is None

    @pytest.mark.asyncio
    async def test_command_to_echo_gap_is_not_counted_as_travel(self, make_cover):
        """The variable Zigbee round-trip falls outside tracked travel.

        A command fired at T0 whose relay only confirms at T0+3s must track as
        if the move began at T0+3s: at the moment of confirmation the position
        is still at the start, not 10% (3s of a 30s travel) along.
        """
        cover = make_cover(
            wait_for_relay_feedback=True, travel_time_open=30, travel_time_close=30
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)

        # Relay confirmed 3s after the command was queued.
        echo_ts = 10_000.0
        echo_time = datetime.fromtimestamp(echo_ts, UTC)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        # Evaluate position exactly at the confirmation instant.
        with patch(
            "custom_components.cover_time_based.travel_calculator.time"
        ) as mock_time:
            mock_time.time.return_value = echo_ts
            # None of the 3s command->echo gap has been counted.
            assert cover.travel_calc.current_position() == 0
            # 6s later, only travel since the echo counts: 6/30 = 20%.
            mock_time.time.return_value = echo_ts + 6
            assert cover.travel_calc.current_position() == 20

    @pytest.mark.asyncio
    async def test_partial_move_parks_until_relay_echo(self, make_cover):
        """A mid-position move gates on the echo through the same seam."""
        cover = make_cover(
            wait_for_relay_feedback=True, travel_time_open=30, travel_time_close=30
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)
        echo_time = datetime.now(UTC)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_set_cover_position(position=60)
            await asyncio.sleep(0)
            assert cover.travel_calc.is_traveling() is False
            assert cover._feedback_wait_entity == "switch.open"

            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover.travel_calc._travel_to_position == 60
        assert cover.travel_calc._last_known_position_timestamp == echo_time.timestamp()

    @pytest.mark.asyncio
    async def test_disabled_starts_tracking_immediately(self, make_cover):
        """With the option off, behaviour is unchanged: tracking starts inline."""
        cover = make_cover(
            wait_for_relay_feedback=False, travel_time_open=30, travel_time_close=30
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover._feedback_wait_entity is None
        assert cover._startup_delay_task is None


class TestRelayFeedbackTilt:
    """Dual-motor tilt moves gate on the tilt relay's echo, same mechanism."""

    def _make_dual_motor(self, make_cover):
        return make_cover(
            wait_for_relay_feedback=True,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_time_open=3,
            tilt_time_close=3,
        )

    @pytest.mark.asyncio
    async def test_tilt_move_parks_until_tilt_relay_echo(self, make_cover):
        cover = self._make_dual_motor(make_cover)
        _stub_switches(cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)
        echo_time = datetime.now(UTC)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover_tilt()
            await asyncio.sleep(0)

            # Parked on the tilt relay, not travel.
            assert cover.tilt_calc.is_traveling() is False
            assert cover._feedback_wait_entity == "switch.tilt_open"
            assert cover._startup_delay_task is not None

            await cover._async_switch_state_changed(
                _echo_event("switch.tilt_open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.tilt_calc.is_traveling() is True
        assert cover.tilt_calc._last_known_position_timestamp == echo_time.timestamp()


class TestRelayFeedbackCalibration:
    """Calibration measures from the relay echo too, so a calibrated travel
    time is not inflated by the Zigbee round-trip it excludes at runtime."""

    @pytest.mark.asyncio
    async def test_travel_time_calibration_excludes_command_to_echo_gap(
        self, make_cover
    ):
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover)
        cover.travel_calc.set_position(100)  # open; calibrate the close travel

        clock = {"t": 1000.0}
        fake_time = MagicMock()
        fake_time.monotonic = lambda: clock["t"]
        with (
            patch(
                "custom_components.cover_time_based.cover_calibration.time", fake_time
            ),
            patch.object(cover, "async_write_ha_state"),
        ):
            await cover.start_calibration(
                attribute="travel_time_close", timeout=600, direction="close"
            )
            await asyncio.sleep(0)  # let the feedback wait arm
            # Normalise the construction baseline to "now".
            cover._calibration.started_at = clock["t"]
            assert cover._feedback_wait_entity == "switch.close"

            # Relay only confirms 3s later (cold mesh).
            clock["t"] = 1003.0
            await cover._async_switch_state_changed(
                _echo_event("switch.close", "off", "on")
            )
            await asyncio.sleep(0)
            # The timer is re-baselined to the confirmation, dropping the 3s gap.
            assert cover._calibration.started_at == 1003.0

            # 20s of real travel, then the user stops at the endpoint.
            clock["t"] = 1023.0
            result = await cover.stop_calibration()

        assert result["value"] == 20.0

    @pytest.mark.asyncio
    async def test_time_calibration_unaffected_when_option_off(self, make_cover):
        """With the option off, calibration times from the command as before."""
        cover = make_cover(wait_for_relay_feedback=False)
        _stub_switches(cover)
        cover.travel_calc.set_position(100)

        clock = {"t": 1000.0}
        fake_time = MagicMock()
        fake_time.monotonic = lambda: clock["t"]
        with (
            patch(
                "custom_components.cover_time_based.cover_calibration.time", fake_time
            ),
            patch.object(cover, "async_write_ha_state"),
        ):
            await cover.start_calibration(
                attribute="travel_time_close", timeout=600, direction="close"
            )
            await asyncio.sleep(0)
            cover._calibration.started_at = clock["t"]
            # No feedback wait is armed.
            assert cover._feedback_wait_entity is None

            clock["t"] = 1003.0
            await cover._async_switch_state_changed(
                _echo_event("switch.close", "off", "on")
            )
            await asyncio.sleep(0)
            # Baseline unchanged — the whole elapsed time is counted.
            assert cover._calibration.started_at == 1000.0

            clock["t"] = 1023.0
            result = await cover.stop_calibration()

        assert result["value"] == 23.0

    @pytest.mark.asyncio
    async def test_overhead_continuous_phase_rebaselines_on_echo(self, make_cover):
        """The startup-delay (overhead) test times its continuous phase from the
        relay echo too, so the Zigbee gap is not measured as motor overhead."""
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover)
        cover._calibration = CalibrationState(
            attribute="travel_startup_delay", timeout=600
        )
        cover._calibration.continuous_start = 500.0  # command-fire baseline
        cover._calibration.move_command = SERVICE_OPEN_COVER

        clock = {"t": 1000.0}
        fake_time = MagicMock()
        fake_time.monotonic = lambda: clock["t"]
        try:
            with (
                patch(
                    "custom_components.cover_time_based.cover_calibration.time",
                    fake_time,
                ),
                patch.object(cover, "async_write_ha_state"),
            ):
                # The continuous-phase drive fires the relay and arms the timing.
                await cover._calibration_drive(SERVICE_OPEN_COVER)
                cover._arm_calibration_feedback_timing("continuous_start")
                await asyncio.sleep(0)
                assert cover._feedback_wait_entity == "switch.open"

                clock["t"] = 1002.0
                await cover._async_switch_state_changed(
                    _echo_event("switch.open", "off", "on")
                )
                await asyncio.sleep(0)

            assert cover._calibration.continuous_start == 1002.0
        finally:
            cover._calibration = None


class TestRelayFeedbackCoupled:
    """The mechanical startup delay applies to both calcs in the feedback path,
    as it did when it was a plain sleep wrapping the whole start."""

    @pytest.mark.asyncio
    async def test_coupled_calc_also_waits_startup_delay(self, make_cover):
        cover = make_cover(
            wait_for_relay_feedback=True, tilt_time_open=10, tilt_time_close=10
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)
        echo_time = datetime.now(UTC)

        # Arm and mark pending as a real _send_open would.
        cover._feedback_armed_entity = "switch.open"
        cover._mark_switch_pending("switch.open", 1)

        with patch.object(cover, "async_write_ha_state"):
            cover._begin_movement(100, 50, cover.travel_calc, cover.tilt_calc, 2.0, 0.0)
            await asyncio.sleep(0)
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        # Both anchors are the echo plus the mechanical spin-up, so the coupled
        # tilt tracker doesn't run ahead of the travel it is coupled to.
        expected = echo_time.timestamp() + 2.0
        assert cover.travel_calc._last_known_position_timestamp == expected
        assert cover.tilt_calc._last_known_position_timestamp == expected


class TestRelayFeedbackGuards:
    """Every guard degrades to today's inline command-fire start."""

    @pytest.mark.asyncio
    async def test_silent_relay_times_out_to_a_command_anchored_start(self, make_cover):
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover)
        cover.travel_calc.set_position(0)

        with (
            patch.object(cover_base, "RELAY_FEEDBACK_TIMEOUT", 0.2),
            patch.object(cover, "async_write_ha_state"),
        ):
            t0 = time.time()
            await cover.async_open_cover()
            await asyncio.sleep(0)
            assert cover.travel_calc.is_traveling() is False  # parked
            # No echo ever arrives; the wait times out and tracking starts,
            # backdated to the command.
            await asyncio.sleep(0.25)

        assert cover.travel_calc.is_traveling() is True
        assert cover._feedback_wait_entity is None
        assert cover._startup_delay_task is None
        # The fallback anchors on the command, not on the moment the wait gave
        # up: a relay whose ON report was dropped has been running since the
        # command.
        assert cover.travel_calc._last_known_position_timestamp == pytest.approx(
            t0, abs=0.01
        )

    @pytest.mark.asyncio
    async def test_optimistic_switch_starts_inline(self, make_cover):
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover, optimistic=("switch.open",))
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

        # Optimistic switch confirms nothing — do not wait on its echo.
        assert cover.travel_calc.is_traveling() is True
        assert cover._feedback_wait_entity is None

    @pytest.mark.asyncio
    async def test_suppress_redrive_ignores_stale_feedback_arm(self, make_cover):
        """A move that reaches _begin_movement without a _send_* (a forced
        redrive) must not inherit an arm left by an earlier resync."""
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover)
        cover.travel_calc.set_position(0)
        # Leftover arm as an endpoint resync would strand it.
        cover._feedback_armed_entity = "switch.open"

        with patch.object(cover, "async_write_ha_state"):
            await cover._async_move_to_endpoint(100, suppress_start_command=True)
            await asyncio.sleep(0)

        # Cleared at funnel entry; the redrive tracks inline, not parked.
        assert cover.travel_calc.is_traveling() is True
        assert cover._feedback_wait_entity is None

    @pytest.mark.asyncio
    async def test_direction_relay_already_on_starts_inline(self, make_cover):
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover, on=("switch.open",))
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

        # Relay already energized: the motor is already running, so waiting for
        # an ON echo that will never come would be wrong.
        assert cover.travel_calc.is_traveling() is True
        assert cover._feedback_wait_entity is None

    @pytest.mark.asyncio
    async def test_external_press_starts_inline(self, make_cover):
        """An external press already switched the relay — nothing to wait for."""
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            # Genuine external open (no pending self-echo) through the listener.
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on")
            )
            await asyncio.sleep(0)

        assert cover._last_command is not None
        assert cover.travel_calc.is_traveling() is True
        assert cover._feedback_wait_entity is None

    @pytest.mark.asyncio
    async def test_reverse_during_wait_cancels_wait_and_stops(self, make_cover):
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover)
        cover.travel_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)
            assert cover._startup_delay_task is not None  # parked, waiting

            cover.hass.services.async_call.reset_mock()
            await cover.async_close_cover()  # reverse before the echo lands
            await asyncio.sleep(0)

        # The parked open is abandoned and the motor stopped; no tracking begins.
        assert cover._feedback_wait_entity is None
        assert cover.travel_calc.is_traveling() is False
        assert cover._last_command is None
        # A STOP (turn_off both relays) was sent for the reversal.
        sent = [c.args for c in cover.hass.services.async_call.call_args_list]
        assert (
            "homeassistant",
            "turn_off",
            {"entity_id": "switch.open"},
            False,
        ) in sent

    @pytest.mark.asyncio
    async def test_stop_during_wait_cancels_wait(self, make_cover):
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)
            assert cover._startup_delay_task is not None

            await cover.async_stop_cover()
            await asyncio.sleep(0)

        assert cover._startup_delay_task is None
        assert cover._feedback_wait_entity is None
        assert cover.travel_calc.is_traveling() is False

    @pytest.mark.asyncio
    async def test_armed_relay_gets_extended_pending_window(self, make_cover):
        """The awaited relay's echo stays classifiable as our own for the whole
        feedback wait — so its pending window is the longer feedback timeout."""
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover)
        cover.travel_calc.set_position(0)

        with (
            patch.object(
                cover, "_mark_switch_pending", wraps=cover._mark_switch_pending
            ) as spy,
            patch.object(cover, "async_write_ha_state"),
        ):
            await cover.async_open_cover()
            await asyncio.sleep(0)

        open_calls = [c for c in spy.call_args_list if c.args[0] == "switch.open"]
        assert open_calls, "open relay should have been marked pending"
        assert (
            open_calls[0].kwargs.get("timeout")
            == cover_base.RELAY_FEEDBACK_PENDING_TIMEOUT
        )
        assert (
            cover_base.RELAY_FEEDBACK_PENDING_TIMEOUT
            > cover_base.RELAY_FEEDBACK_TIMEOUT
        )


class TestRelayFeedbackToggleMode:
    """Toggle (momentary) mode gates on the pulse relay's OFF->ON rising edge.

    The relay pulses ON then self-releases, but the ON edge is still the "motor
    energized" signal — the same seam switch mode uses, reached through
    ToggleBaseCover._pulse_relay instead of a latched turn_on.
    """

    @pytest.mark.asyncio
    async def test_move_parks_until_relay_echo_then_tracks_from_last_changed(
        self, make_cover
    ):
        cover = make_cover(
            control_mode="toggle",
            wait_for_relay_feedback=True,
            travel_time_open=30,
            travel_time_close=30,
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)
        echo_time = datetime.now(UTC)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

            # Pulse fired, but tracking is parked on the relay's ON edge.
            assert cover.travel_calc.is_traveling() is False
            assert cover.travel_calc.current_position() == 0
            assert cover._feedback_wait_entity == "switch.open"

            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover.travel_calc._last_known_position_timestamp == echo_time.timestamp()
        assert cover._feedback_wait_entity is None

    @pytest.mark.asyncio
    async def test_disabled_starts_tracking_immediately(self, make_cover):
        cover = make_cover(
            control_mode="toggle",
            wait_for_relay_feedback=False,
            travel_time_open=30,
            travel_time_close=30,
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover._feedback_wait_entity is None
        assert cover._startup_delay_task is None

    @pytest.mark.asyncio
    async def test_tilt_move_parks_until_tilt_relay_echo(self, make_cover):
        cover = make_cover(
            control_mode="toggle",
            wait_for_relay_feedback=True,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_time_open=3,
            tilt_time_close=3,
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)
        echo_time = datetime.now(UTC)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover_tilt()
            await asyncio.sleep(0)

            assert cover.tilt_calc.is_traveling() is False
            assert cover._feedback_wait_entity == "switch.tilt_open"

            await cover._async_switch_state_changed(
                _echo_event("switch.tilt_open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.tilt_calc.is_traveling() is True
        assert cover.tilt_calc._last_known_position_timestamp == echo_time.timestamp()

    @pytest.mark.asyncio
    async def test_no_rising_edge_relay_starts_inline(self, make_cover):
        """A relay that never reports its OFF (relay_reports_off disabled) and is
        stale-ON produces no rising edge on turn_on — there is no echo to wait
        for, so tracking must start inline rather than block on a phantom echo."""
        cover = make_cover(
            control_mode="toggle",
            wait_for_relay_feedback=True,
            relay_reports_off=False,
        )
        _stub_switches(cover, on=("switch.open",))
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover._feedback_wait_entity is None
        assert cover._startup_delay_task is None

    @pytest.mark.asyncio
    async def test_relay_reporting_on_is_released_then_pulsed_and_still_waits(
        self, make_cover
    ):
        """Unlike switch mode's "already on -> inline" shortcut, a toggle relay
        reporting ON (with relay_reports_off on) is released then re-pulsed, so a
        genuine OFF->ON edge is produced — tracking still gates on that ON echo,
        which arrives as the second of the two echoes."""
        cover = make_cover(control_mode="toggle", wait_for_relay_feedback=True)
        _stub_switches(cover, on=("switch.open",))
        cover.travel_calc.set_position(0)
        echo_time = datetime.now(UTC)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

            assert cover.travel_calc.is_traveling() is False
            assert cover._feedback_wait_entity == "switch.open"

            # The release echo (on->off) is not the confirmation.
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "on", "off")
            )
            await asyncio.sleep(0)
            assert cover.travel_calc.is_traveling() is False

            # The re-pulse echo (off->on) is.
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover.travel_calc._last_known_position_timestamp == echo_time.timestamp()

    @pytest.mark.asyncio
    async def test_armed_relay_gets_extended_pending_window(self, make_cover):
        cover = make_cover(control_mode="toggle", wait_for_relay_feedback=True)
        _stub_switches(cover)
        cover.travel_calc.set_position(0)

        with (
            patch.object(
                cover, "_mark_switch_pending", wraps=cover._mark_switch_pending
            ) as spy,
            patch.object(cover, "async_write_ha_state"),
        ):
            await cover.async_open_cover()
            await asyncio.sleep(0)

        open_calls = [c for c in spy.call_args_list if c.args[0] == "switch.open"]
        assert open_calls, "open relay should have been marked pending"
        assert (
            open_calls[0].kwargs.get("timeout")
            == cover_base.RELAY_FEEDBACK_PENDING_TIMEOUT
        )


class TestRelayFeedbackToggleStop:
    """A toggle stop is a tap on the driving relay; tapped before the relay's
    ON echo lands it can be swallowed, leaving the motor running untracked."""

    @pytest.fixture
    async def parked_toggle_cover(self, make_cover):
        """A toggle cover parked on the open relay's not-yet-arrived ON echo.

        ``async_write_ha_state`` stays patched for the whole test, and the
        service mock is reset at the yield so ``_taps`` sees only the stop.
        """
        cover = make_cover(control_mode="toggle", wait_for_relay_feedback=True)
        _stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)
            assert cover._feedback_wait_entity == "switch.open"
            cover.hass.services.async_call.reset_mock()
            yield cover

    @pytest.mark.asyncio
    async def test_stop_during_wait_is_deferred_until_the_echo(
        self, parked_toggle_cover
    ):
        cover = parked_toggle_cover
        stop = asyncio.ensure_future(cover.async_stop_cover())
        await asyncio.sleep(0)
        # No tap yet: the relay has not confirmed.
        assert cover.hass.services.async_call.await_count == 0

        await cover._async_switch_state_changed(
            _echo_event("switch.open", "off", "on", datetime.now(UTC))
        )
        await stop

        # Exactly one tap, after the confirmation.
        assert len(_taps(cover, "switch.open")) == 1
        assert cover.travel_calc.is_traveling() is False

    @pytest.mark.asyncio
    async def test_deferred_stop_releases_a_relay_reporting_on_first(
        self, parked_toggle_cover
    ):
        """The deferred tap is still a real pulse: with the relay reporting ON
        by the time the echo lands, the stop releases it first so its turn_on
        carries the rising edge the motor acts on."""
        cover = parked_toggle_cover
        stop = asyncio.ensure_future(cover.async_stop_cover())
        await asyncio.sleep(0)

        _stub_switches(cover, on=("switch.open",))
        await cover._async_switch_state_changed(
            _echo_event("switch.open", "off", "on", datetime.now(UTC))
        )
        await stop

        assert cover.hass.services.async_call.call_args_list == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_gives_up_waiting_after_the_timeout(self, make_cover):
        """Opts out of the parked fixture: the shortened timeout has to bound
        the move's own wait too, so its fallback start runs before the stop."""
        cover = make_cover(
            control_mode="toggle",
            wait_for_relay_feedback=True,
            travel_time_open=1,
            travel_time_close=1,
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)

        with (
            patch.object(cover_base, "RELAY_FEEDBACK_TIMEOUT", 0.05),
            patch.object(cover, "async_write_ha_state"),
        ):
            await cover.async_open_cover()
            await asyncio.sleep(0)
            cover.hass.services.async_call.reset_mock()
            await cover.async_stop_cover()

        assert len(_taps(cover, "switch.open")) == 1
        # The silent relay's wait was not merely abandoned: its command-fire
        # fallback started tracking, so the stop lands on a tracked move.
        assert cover._startup_delay_task is None
        assert cover.travel_calc.current_position() > 0

    @pytest.mark.asyncio
    async def test_external_stop_does_not_wait_for_the_echo(self, parked_toggle_cover):
        """An external press drives the motor itself and suppresses our relay
        command, so a stop reached that way sends no tap to protect — waiting
        would park the wall switch for the whole feedback timeout."""
        cover = parked_toggle_cover
        cover._triggered_externally = True
        try:
            await asyncio.wait_for(cover.async_stop_cover(supersede=False), 0.5)
        finally:
            cover._triggered_externally = False

        assert _taps(cover, "switch.open") == []

    @pytest.mark.asyncio
    async def test_stop_with_no_pending_wait_taps_immediately(
        self, parked_toggle_cover
    ):
        """The deferral is confined to a live wait: with the option on but the
        relay already confirmed, the stop still goes out inline."""
        cover = parked_toggle_cover
        await cover._async_switch_state_changed(
            _echo_event("switch.open", "off", "on", datetime.now(UTC))
        )
        await asyncio.sleep(0)
        assert cover._feedback_wait_future is None

        stop = asyncio.ensure_future(cover.async_stop_cover())
        await asyncio.sleep(0)
        assert _taps(cover, "switch.open")
        await stop

        assert len(_taps(cover, "switch.open")) == 1

    @pytest.mark.asyncio
    async def test_an_orphaned_wait_is_released_by_the_backstop(self, make_cover):
        """A future with no owner has nobody to time it out, so the deferral's
        own timeout has to end the wait rather than block the stop forever."""
        cover = make_cover(control_mode="toggle", wait_for_relay_feedback=True)
        cover._feedback_wait_entity = "switch.open"
        orphan = asyncio.get_running_loop().create_future()
        cover._feedback_wait_future = orphan

        with patch.object(cover_base, "RELAY_FEEDBACK_TIMEOUT", 0.05):
            await asyncio.wait_for(cover._await_pending_relay_confirmation(), 1.0)

        # Passive: the wait gives up on the future, it does not cancel it.
        assert not orphan.done()


class TestRelayFeedbackToggleOppositeMode:
    """Toggle-opposite shares ToggleBaseCover's send path, so the same arming
    applies — one smoke test proves the inheritance rather than re-covering it."""

    @pytest.mark.asyncio
    async def test_move_parks_until_relay_echo(self, make_cover):
        cover = make_cover(
            control_mode="toggle_opposite",
            wait_for_relay_feedback=True,
            travel_time_open=30,
            travel_time_close=30,
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)
        echo_time = datetime.now(UTC)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

            assert cover.travel_calc.is_traveling() is False
            assert cover._feedback_wait_entity == "switch.open"

            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover.travel_calc._last_known_position_timestamp == echo_time.timestamp()


class TestRelayFeedbackPulseMode:
    """Pulse mode gates on the driving relay's ON edge (turn_on), before the
    deferred turn_off that completes the pulse."""

    @pytest.mark.asyncio
    async def test_move_parks_until_relay_echo_then_tracks_from_last_changed(
        self, make_cover
    ):
        cover = make_cover(
            control_mode="pulse",
            stop_switch="switch.stop",
            wait_for_relay_feedback=True,
            travel_time_open=30,
            travel_time_close=30,
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)
        echo_time = datetime.now(UTC)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

            assert cover.travel_calc.is_traveling() is False
            assert cover.travel_calc.current_position() == 0
            assert cover._feedback_wait_entity == "switch.open"

            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover.travel_calc._last_known_position_timestamp == echo_time.timestamp()
        assert cover._feedback_wait_entity is None

    @pytest.mark.asyncio
    async def test_disabled_starts_tracking_immediately(self, make_cover):
        cover = make_cover(
            control_mode="pulse",
            stop_switch="switch.stop",
            wait_for_relay_feedback=False,
            travel_time_open=30,
            travel_time_close=30,
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover._feedback_wait_entity is None
        assert cover._startup_delay_task is None

    @pytest.mark.asyncio
    async def test_tilt_move_parks_until_tilt_relay_echo(self, make_cover):
        cover = make_cover(
            control_mode="pulse",
            stop_switch="switch.stop",
            wait_for_relay_feedback=True,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
            tilt_time_open=3,
            tilt_time_close=3,
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)
        echo_time = datetime.now(UTC)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover_tilt()
            await asyncio.sleep(0)

            assert cover.tilt_calc.is_traveling() is False
            assert cover._feedback_wait_entity == "switch.tilt_open"

            await cover._async_switch_state_changed(
                _echo_event("switch.tilt_open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.tilt_calc.is_traveling() is True
        assert cover.tilt_calc._last_known_position_timestamp == echo_time.timestamp()

    @pytest.mark.asyncio
    async def test_driving_relay_already_on_starts_inline(self, make_cover):
        """A re-pulse on an already-ON relay flips no state on turn_on, so there
        is no ON echo to wait for — start inline."""
        cover = make_cover(
            control_mode="pulse",
            stop_switch="switch.stop",
            wait_for_relay_feedback=True,
        )
        _stub_switches(cover, on=("switch.open",))
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover._feedback_wait_entity is None

    @pytest.mark.asyncio
    async def test_armed_relay_gets_extended_pending_window(self, make_cover):
        cover = make_cover(
            control_mode="pulse",
            stop_switch="switch.stop",
            wait_for_relay_feedback=True,
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)

        with (
            patch.object(
                cover, "_mark_switch_pending", wraps=cover._mark_switch_pending
            ) as spy,
            patch.object(cover, "async_write_ha_state"),
        ):
            await cover.async_open_cover()
            await asyncio.sleep(0)

        open_calls = [c for c in spy.call_args_list if c.args[0] == "switch.open"]
        assert open_calls, "open relay should have been marked pending"
        assert (
            open_calls[0].kwargs.get("timeout")
            == cover_base.RELAY_FEEDBACK_PENDING_TIMEOUT
        )

    @pytest.mark.asyncio
    async def test_long_pulse_pending_window_outlasts_the_pulse(self, make_cover):
        """The deferred completion OFF echo fires ~pulse_time after the pulse, so
        the pending window must outlast the pulse. A pulse_time above the 5s
        default would otherwise clear the count early and misread the pulse's own
        OFF echo as an external change. Independent of relay feedback (option
        off here), since the completion OFF exists regardless."""
        cover = make_cover(
            control_mode="pulse",
            stop_switch="switch.stop",
            pulse_time=8,
            wait_for_relay_feedback=False,
        )
        _stub_switches(cover)
        cover.travel_calc.set_position(0)

        with (
            patch.object(
                cover, "_mark_switch_pending", wraps=cover._mark_switch_pending
            ) as spy,
            patch.object(cover, "async_write_ha_state"),
        ):
            await cover.async_open_cover()
            await asyncio.sleep(0)

        open_calls = [c for c in spy.call_args_list if c.args[0] == "switch.open"]
        assert open_calls, "open relay should have been marked pending"
        assert open_calls[0].kwargs.get("timeout") >= 8, (
            "pending window must cover the 8s pulse so the completion OFF echo "
            "is still filtered as our own"
        )


class TestRelayFeedbackPendingWindow:
    """A later, shorter mark (a stop's default window) must not truncate the
    long window a feedback-gated move armed while its echo is outstanding."""

    @pytest.fixture
    def marked_cover(self, make_cover):
        """Yield ``(cover, delays)`` with the safety timers recorded, not armed.

        ``delays`` collects the window each ``_mark_switch_pending`` schedules,
        in call order.
        """
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover)
        delays = []

        def fake_call_later(hass, delay, action):
            delays.append(delay)
            return MagicMock()

        with patch.object(cover_base, "async_call_later", fake_call_later):
            yield cover, delays

    @pytest.mark.asyncio
    async def test_short_remark_keeps_the_longer_remaining_window(self, marked_cover):
        cover, delays = marked_cover
        cover._mark_switch_pending("switch.open", 1, timeout=12.0)
        cover._mark_switch_pending("switch.open", 1, timeout=5.0)
        assert delays[0] == 12.0
        assert delays[1] == pytest.approx(12.0, abs=0.05)

    @pytest.mark.asyncio
    async def test_remaining_window_shrinks_by_the_time_already_elapsed(
        self, marked_cover
    ):
        """The re-mark preserves the original deadline, not the original
        duration: 4s into a 12s window the timer is re-armed for the 8s left."""
        cover, delays = marked_cover
        clock = {"t": 1000.0}
        fake_time = MagicMock()
        fake_time.monotonic = lambda: clock["t"]

        with patch.object(cover_base, "time", fake_time):
            cover._mark_switch_pending("switch.open", 1, timeout=12.0)
            clock["t"] += 4.0
            cover._mark_switch_pending("switch.open", 1, timeout=5.0)

        assert delays[-1] == pytest.approx(8.0)

    @pytest.mark.asyncio
    async def test_longer_remark_extends(self, marked_cover):
        cover, delays = marked_cover
        cover._mark_switch_pending("switch.open", 1, timeout=5.0)
        cover._mark_switch_pending("switch.open", 1, timeout=12.0)
        assert delays[1] == 12.0

    @pytest.mark.asyncio
    async def test_deadline_is_dropped_once_the_echo_is_consumed(self, marked_cover):
        """A fresh mark after the count clears starts from its own timeout —
        a stale deadline must not keep extending later, unrelated windows."""
        cover, delays = marked_cover
        cover._mark_switch_pending("switch.open", 1, timeout=12.0)
        await cover._async_switch_state_changed(_echo_event("switch.open", "off", "on"))
        assert "switch.open" not in cover._pending_switch
        cover._mark_switch_pending("switch.open", 1, timeout=5.0)
        assert delays[-1] == 5.0

    @pytest.mark.asyncio
    async def test_unmark_drops_the_deadline(self, marked_cover):
        cover, delays = marked_cover
        cover._mark_switch_pending("switch.open", 1, timeout=12.0)
        cover._unmark_switch_pending("switch.open", 1)
        cover._mark_switch_pending("switch.open", 1, timeout=5.0)
        assert delays[-1] == 5.0


class TestRelayFeedbackWaitSlot:
    """A cancelled wait's cleanup must not clear a replacement wait that
    registered before the cancelled task's `finally` ran (HA creates tasks
    eagerly, so that ordering is the normal one)."""

    @pytest.fixture(autouse=True)
    async def _eager_tasks(self):
        """Start tasks eagerly, the way ``hass.async_create_task`` does.

        Under eager start a replacement task registers its slot synchronously,
        before the cancelled task's cleanup gets to run — the ordering that
        unconditional cleanup clobbers.
        """
        loop = asyncio.get_running_loop()
        previous = loop.get_task_factory()
        loop.set_task_factory(asyncio.eager_task_factory)
        yield
        loop.set_task_factory(previous)

    @pytest.mark.asyncio
    async def test_cancelled_wait_does_not_clear_the_new_wait(self, make_cover):
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover)
        first = asyncio.ensure_future(cover._wait_for_relay_echo("switch.open", 5))
        await asyncio.sleep(0)  # first registers its slot
        first.cancel()
        second = asyncio.ensure_future(cover._wait_for_relay_echo("switch.close", 5))
        await asyncio.sleep(0)  # second registers; first's finally runs
        await asyncio.sleep(0)
        assert cover._feedback_wait_entity == "switch.close"
        assert (
            cover._feedback_wait_future is not None
            and not cover._feedback_wait_future.done()
        )
        second.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await second

    @pytest.mark.asyncio
    async def test_cancelled_deferred_start_does_not_null_the_new_task(
        self, make_cover
    ):
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover)

        def _park(entity_id):
            return cover.hass.async_create_task(
                cover._run_deferred_start(
                    lambda: cover._await_relay_confirmation(entity_id, time.time()),
                    MagicMock(),
                    startup_delay=0.0,
                )
            )

        cover._startup_delay_task = old = _park("switch.open")
        old.cancel()
        # A replacement move registers its own task before old's handler runs.
        cover._startup_delay_task = new = _park("switch.close")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert cover._startup_delay_task is new
        cover._cancel_startup_delay_task()

    @pytest.mark.asyncio
    async def test_second_calibration_arm_cancels_the_first(self, make_cover):
        """An overwritten calibration wait must not stay parked: it would
        re-stamp a later phase's baseline off the wrong relay confirmation."""
        cover = make_cover(wait_for_relay_feedback=True)
        _stub_switches(cover)
        cover._calibration = CalibrationState(
            attribute="travel_startup_delay", timeout=600
        )
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._calibration_drive(SERVICE_OPEN_COVER)
                cover._arm_calibration_feedback_timing("started_at")
                first = cover._calibration.feedback_task
                assert first is not None
                await cover._calibration_drive(SERVICE_OPEN_COVER)
                cover._arm_calibration_feedback_timing("continuous_start")
                await asyncio.sleep(0)
                await asyncio.sleep(0)
            assert first.cancelled()
            second = cover._calibration.feedback_task
            assert second is not first and not second.done()
            assert cover._feedback_wait_entity == "switch.open"
            second.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await second
        finally:
            cover._calibration = None
