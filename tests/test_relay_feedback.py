"""Tests for the opt-in ``wait_for_relay_feedback`` behaviour (issue #231).

When enabled (every relay-driven mode — switch, toggle, toggle-opposite, pulse
and single button), the travel/tilt timer starts when the relay confirms it switched — the
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
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from custom_components.cover_time_based import cover_base, travel_calculator
from custom_components.cover_time_based.calibration import CalibrationState
from custom_components.cover_time_based.cover import CONTROL_MODE_SINGLE_BUTTON
from custom_components.cover_time_based.single_button_cycle import Phase
from tests.helpers import FakeClock, single_button_sleep_patch, stub_switches

# A fixed, timezone-aware moment used as the relay echo's ``last_changed``.
FIXED_ECHO = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


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


def _expected_anchor(echo_time, clock=time) -> float:
    """The monotonic anchor a wall-clock echo at ``echo_time`` converts to.

    Only for an echo stamped AFTER the command that produced it (the age is
    then inside the wait's own interval, so production applies no clamp).
    """
    return clock.monotonic() - (clock.time() - echo_time.timestamp())


def _ha(service, entity_id):
    """Shorthand for a homeassistant.turn_on / turn_off call."""
    return call("homeassistant", service, {"entity_id": entity_id}, False)


def _taps(cover, entity_id):
    """The taps (``turn_on``) sent to ``entity_id`` on the mock service bus."""
    tap = _ha("turn_on", entity_id)
    return [c for c in cover.hass.services.async_call.call_args_list if c == tap]


def _parked(cover, entity_id):
    """Whether a feedback wait on ``entity_id`` is still unresolved."""
    future = cover._feedback_wait_future
    return (
        cover._feedback_wait_entity == entity_id
        and future is not None
        and not future.done()
    )


async def _turns(n=5):
    """Give the loop ``n`` turns, so parked tasks and callbacks get to run."""
    for _ in range(n):
        await asyncio.sleep(0)


def _make_dual_motor(make_cover, **kwargs):
    """A feedback-gated cover with a separate tilt motor on its own relays."""
    return make_cover(
        wait_for_relay_feedback=True,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        **{"tilt_time_open": 3, "tilt_time_close": 3, **kwargs},
    )


def _make_single_button(make_cover, **kwargs):
    """A feedback-gated single-button cover driven through ``switch.button``."""
    return make_cover(
        control_mode=CONTROL_MODE_SINGLE_BUTTON,
        open_switch="switch.button",
        close_switch=None,
        wait_for_relay_feedback=True,
        **kwargs,
    )


def _stub(cover):
    """Deterministic relays and no state writes, for the whole test."""
    stub_switches(cover)
    cover.async_write_ha_state = MagicMock()
    return cover


def _make_stubbed(make_cover, **kwargs):
    """A feedback-gated cover with deterministic relays and no state writes."""
    return _stub(make_cover(wait_for_relay_feedback=True, **kwargs))


async def _park_open(make_cover, control_mode="toggle", position=0, **kwargs):
    """A cover parked on the open relay's not-yet-arrived ON echo.

    The service mock is reset on return, so ``_taps`` sees only what follows.
    """
    cover = _make_stubbed(make_cover, control_mode=control_mode, **kwargs)
    cover.travel_calc.set_position(position)
    await cover.async_open_cover()
    await asyncio.sleep(0)
    assert cover._feedback_wait_entity == "switch.open"
    cover.hass.services.async_call.reset_mock()
    return cover


@pytest.fixture
def feedback_clock():
    """Drive command, echo and tracking time together without patching the loop."""
    clock = FakeClock(wall=1_700_000_000.0, mono=5_000.0)
    with (
        patch.object(cover_base, "time", clock),
        patch.object(travel_calculator, "time", clock),
    ):
        yield clock


class TestRelayFeedbackStart:
    """The travel timer starts on the relay echo, not the queued command."""

    @pytest.mark.asyncio
    async def test_move_parks_until_relay_echo_then_tracks_from_last_changed(
        self, make_cover
    ):
        cover = make_cover(
            wait_for_relay_feedback=True, travel_time_open=30, travel_time_close=30
        )
        stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)  # let the feedback task reach its await

            # Command fired, but tracking is parked: position frozen at start.
            assert cover.travel_calc.is_traveling() is False
            assert cover.travel_calc.current_position() == 0
            assert cover._startup_delay_task is not None
            assert cover._feedback_wait_entity == "switch.open"

            # The relay confirms it switched on.
            echo_time = datetime.now(UTC)
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)  # let the feedback task resume

        assert cover.travel_calc.is_traveling() is True
        # Travel is timestamped from the echo's last_changed.
        assert cover.travel_calc._last_known_position_timestamp == pytest.approx(
            _expected_anchor(echo_time), abs=0.05
        )
        assert cover._feedback_wait_entity is None

    @pytest.mark.asyncio
    async def test_echo_anchor_is_converted_to_monotonic(
        self, make_cover, feedback_clock
    ):
        """A 3 s old echo anchors tracking 3 s ago on the monotonic clock."""
        cover = make_cover(wait_for_relay_feedback=True)
        stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)
            feedback_clock.advance(3.1)  # the wait must be older than the echo
            echo_time = datetime.fromtimestamp(feedback_clock.time() - 3, UTC)
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.travel_calc._last_known_position_timestamp == pytest.approx(
            _expected_anchor(echo_time, feedback_clock), abs=0.05
        )

    @pytest.mark.asyncio
    async def test_echo_from_the_future_anchors_now(self, make_cover):
        """A device clock ahead of ours cannot push the anchor into the future."""
        cover = make_cover(wait_for_relay_feedback=True)
        stub_switches(cover)
        cover.travel_calc.set_position(0)
        echo_time = datetime.now(UTC) + timedelta(seconds=30)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)
            before = time.monotonic()
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        anchor = cover.travel_calc._last_known_position_timestamp
        assert before <= anchor <= time.monotonic()

    @pytest.mark.asyncio
    async def test_wall_clock_step_before_the_echo_cannot_backdate_past_the_command(
        self, make_cover
    ):
        """An echo stamped an hour ago (the wall clock jumped forward) anchors at the command."""
        cover = make_cover(wait_for_relay_feedback=True)
        stub_switches(cover)
        cover.travel_calc.set_position(0)
        echo_time = datetime.now(UTC) - timedelta(hours=1)

        with patch.object(cover, "async_write_ha_state"):
            commanded = time.monotonic()
            await cover.async_open_cover()
            await asyncio.sleep(0)
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        anchor = cover.travel_calc._last_known_position_timestamp
        assert anchor == pytest.approx(commanded, abs=0.05)

    @pytest.mark.asyncio
    async def test_command_to_echo_gap_is_not_counted_as_travel(
        self, make_cover, feedback_clock
    ):
        """The variable Zigbee round-trip falls outside tracked travel."""
        clock = feedback_clock
        cover = make_cover(wait_for_relay_feedback=True)
        stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()  # commanded at mono 5000
            await asyncio.sleep(0)
            clock.advance(3)  # the round trip
            echo_time = datetime.fromtimestamp(clock.time(), UTC)
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)
            # None of the 3 s command->echo gap has been counted.
            assert cover.travel_calc.current_position() == 0
            # 6 s later, only travel since the echo counts: 6/30 = 20%.
            clock.advance(6)
            assert cover.travel_calc.current_position() == 20

    @pytest.mark.asyncio
    async def test_partial_move_parks_until_relay_echo(self, make_cover):
        """A mid-position move gates on the echo through the same seam."""
        cover = make_cover(
            wait_for_relay_feedback=True, travel_time_open=30, travel_time_close=30
        )
        stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_set_cover_position(position=60)
            await asyncio.sleep(0)
            assert cover.travel_calc.is_traveling() is False
            assert cover._feedback_wait_entity == "switch.open"

            echo_time = datetime.now(UTC)
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover.travel_calc._travel_to_position == 60
        assert cover.travel_calc._last_known_position_timestamp == pytest.approx(
            _expected_anchor(echo_time), abs=0.05
        )

    @pytest.mark.asyncio
    async def test_disabled_starts_tracking_immediately(self, make_cover):
        """With the option off, behaviour is unchanged: tracking starts inline."""
        cover = make_cover(
            wait_for_relay_feedback=False, travel_time_open=30, travel_time_close=30
        )
        stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover._feedback_wait_entity is None
        assert cover._startup_delay_task is None


class TestRelayFeedbackTilt:
    """Dual-motor tilt moves gate on the tilt relay's echo, same mechanism."""

    @pytest.mark.asyncio
    async def test_tilt_move_parks_until_tilt_relay_echo(self, make_cover):
        cover = _make_dual_motor(make_cover)
        stub_switches(cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover_tilt()
            await asyncio.sleep(0)

            # Parked on the tilt relay, not travel.
            assert cover.tilt_calc.is_traveling() is False
            assert cover._feedback_wait_entity == "switch.tilt_open"
            assert cover._startup_delay_task is not None

            echo_time = datetime.now(UTC)
            await cover._async_switch_state_changed(
                _echo_event("switch.tilt_open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.tilt_calc.is_traveling() is True
        assert cover.tilt_calc._last_known_position_timestamp == pytest.approx(
            _expected_anchor(echo_time), abs=0.05
        )


class TestRelayFeedbackCalibration:
    """Calibration measures from the relay echo too, so a calibrated travel
    time is not inflated by the Zigbee round-trip it excludes at runtime."""

    @pytest.mark.asyncio
    async def test_travel_time_calibration_excludes_command_to_echo_gap(
        self, make_cover
    ):
        cover = make_cover(wait_for_relay_feedback=True)
        stub_switches(cover)
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
        stub_switches(cover)
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
        stub_switches(cover)
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


class TestRelayFeedbackCalibrationUnmarkedEdge:
    """A calibration drive's mark can be spent by a late self-release OFF just
    like a movement's, so an unmarked rising edge on the awaited relay confirms
    it too — ahead of the guard that otherwise drops relay events during a
    calibration."""

    @pytest.mark.asyncio
    async def test_unmarked_rising_edge_confirms_a_calibration_wait(self, make_cover):
        cover = make_cover(control_mode="toggle", wait_for_relay_feedback=True)
        stub_switches(cover)
        cover._calibration = CalibrationState(attribute="travel_time_open", timeout=600)
        wait = asyncio.ensure_future(cover._wait_for_relay_echo("switch.open", 5))
        await asyncio.sleep(0)
        assert _parked(cover, "switch.open")
        assert cover._pending_switch.get("switch.open", 0) == 0

        echo_time = datetime.now(UTC)
        await cover._async_switch_state_changed(
            _echo_event("switch.open", "off", "on", echo_time)
        )
        assert await asyncio.wait_for(wait, 1.0) == pytest.approx(
            _expected_anchor(echo_time), abs=0.05
        )


class TestRelayFeedbackCoupled:
    """The mechanical startup delay applies to both calcs in the feedback path,
    as it did when it was a plain sleep wrapping the whole start."""

    @pytest.mark.asyncio
    async def test_coupled_calc_also_waits_startup_delay(self, make_cover):
        cover = make_cover(
            wait_for_relay_feedback=True, tilt_time_open=10, tilt_time_close=10
        )
        stub_switches(cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)

        # Arm and mark pending as a real _send_open would.
        cover._feedback_armed_entity = "switch.open"
        cover._mark_switch_pending("switch.open", 1)

        with patch.object(cover, "async_write_ha_state"):
            cover._begin_movement(100, 50, cover.travel_calc, cover.tilt_calc, 2.0, 0.0)
            await asyncio.sleep(0)
            echo_time = datetime.now(UTC)
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        # Both anchors are the echo plus the mechanical spin-up, so the coupled
        # tilt tracker doesn't run ahead of the travel it is coupled to.
        expected = pytest.approx(_expected_anchor(echo_time) + 2.0, abs=0.05)
        assert cover.travel_calc._last_known_position_timestamp == expected
        assert cover.tilt_calc._last_known_position_timestamp == expected


class TestRelayFeedbackGuards:
    """Every guard degrades to today's inline command-fire start."""

    @pytest.mark.asyncio
    async def test_silent_relay_times_out_to_a_command_anchored_start(self, make_cover):
        cover = make_cover(wait_for_relay_feedback=True)
        stub_switches(cover)
        cover.travel_calc.set_position(0)

        with (
            patch.object(cover_base, "RELAY_FEEDBACK_TIMEOUT", 0.2),
            patch.object(cover, "async_write_ha_state"),
        ):
            t0 = time.monotonic()
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
        # command. The tolerance only has to stay well inside the patched 0.2s
        # timeout that separates the two anchors, so it is loose enough to
        # survive a loaded CI runner.
        assert cover.travel_calc._last_known_position_timestamp == pytest.approx(
            t0, abs=0.05
        )

    @pytest.mark.asyncio
    async def test_optimistic_switch_starts_inline(self, make_cover):
        cover = make_cover(wait_for_relay_feedback=True)
        stub_switches(cover, optimistic=("switch.open",))
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
        stub_switches(cover)
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
    async def test_travel_leg_after_tilt_pre_step_does_not_inherit_tilt_arm(
        self, make_cover
    ):
        """A dual-motor tilt-to-safe pre-step arms the tilt relay's feedback wait
        then starts tilt_calc directly, never reaching _begin_movement, so the
        arm is stranded on the tilt relay. When the deferred travel leg begins
        with its own relay already energised — so its _send_* re-arms nothing —
        the travel move must start inline, not inherit the stranded tilt arm and
        park on the tilt relay's ON echo (a wait its already-latched travel relay
        would never satisfy). Same movement epoch as the pre-step throughout."""
        cover = _make_dual_motor(make_cover, safe_tilt_position=0)
        stub_switches(cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(80)  # open; tilt-to-safe (→0) pre-step first
            await _turns()
            # The pre-step armed the tilt-close relay and stranded it.
            assert cover._pending_travel_target == 80
            assert cover._feedback_armed_entity == "switch.tilt_close"

            # The travel (open) relay is already energised when the pre-step
            # completes, so the travel _send_open flips nothing and re-arms nothing.
            stub_switches(cover, on=("switch.open",))
            await cover._start_pending_travel()
            await _turns()

        # Travel already running: no ON echo is coming, so it starts inline. The
        # move must NOT be parked on the stranded tilt relay's echo.
        assert cover._feedback_wait_entity != "switch.tilt_close"
        assert cover.travel_calc.is_traveling() is True

    @pytest.mark.asyncio
    async def test_direction_relay_already_on_starts_inline(self, make_cover):
        cover = make_cover(wait_for_relay_feedback=True)
        stub_switches(cover, on=("switch.open",))
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
        stub_switches(cover)
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
        stub_switches(cover)
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
        stub_switches(cover)
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
        stub_switches(cover)
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
        stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

            # Pulse fired, but tracking is parked on the relay's ON edge.
            assert cover.travel_calc.is_traveling() is False
            assert cover.travel_calc.current_position() == 0
            assert cover._feedback_wait_entity == "switch.open"

            echo_time = datetime.now(UTC)
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover.travel_calc._last_known_position_timestamp == pytest.approx(
            _expected_anchor(echo_time), abs=0.05
        )
        assert cover._feedback_wait_entity is None

    @pytest.mark.asyncio
    async def test_disabled_starts_tracking_immediately(self, make_cover):
        cover = make_cover(
            control_mode="toggle",
            wait_for_relay_feedback=False,
            travel_time_open=30,
            travel_time_close=30,
        )
        stub_switches(cover)
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
        stub_switches(cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover_tilt()
            await asyncio.sleep(0)

            assert cover.tilt_calc.is_traveling() is False
            assert cover._feedback_wait_entity == "switch.tilt_open"

            echo_time = datetime.now(UTC)
            await cover._async_switch_state_changed(
                _echo_event("switch.tilt_open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.tilt_calc.is_traveling() is True
        assert cover.tilt_calc._last_known_position_timestamp == pytest.approx(
            _expected_anchor(echo_time), abs=0.05
        )

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
        stub_switches(cover, on=("switch.open",))
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
        stub_switches(cover, on=("switch.open",))
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

            assert cover.travel_calc.is_traveling() is False
            assert cover._feedback_wait_entity == "switch.open"

            # The release echo (on->off) is not the confirmation.
            echo_time = datetime.now(UTC)
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
        assert cover.travel_calc._last_known_position_timestamp == pytest.approx(
            _expected_anchor(echo_time), abs=0.05
        )

    @pytest.mark.asyncio
    async def test_armed_relay_gets_extended_pending_window(self, make_cover):
        cover = make_cover(control_mode="toggle", wait_for_relay_feedback=True)
        stub_switches(cover)
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
        """A toggle cover parked on the open relay's not-yet-arrived ON echo,
        with the service mock reset so ``_taps`` sees only the stop."""
        return await _park_open(make_cover)

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

        stub_switches(cover, on=("switch.open",))
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
        stub_switches(cover)
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
    async def test_the_stop_resumes_behind_the_start_it_waited_for(
        self, parked_toggle_cover
    ):
        """The confirmation wakes the parked start and the waiting stop alike,
        so the stop must resume behind the start rather than merely alongside
        it: it reads ``was_active`` off the tracker, and an idle tracker means
        no tap, leaving the motor running untracked."""
        cover = parked_toggle_cover
        traveling_at_cancel = []
        real_cancel = cover._cancel_startup_delay_task

        def _spy():
            # _neutralize_tracked_movement's first act, so this samples the
            # tracker at the instant the stop decided what to tear down.
            traveling_at_cancel.append(cover.travel_calc.is_traveling())
            return real_cancel()

        with patch.object(cover, "_cancel_startup_delay_task", _spy):
            stop = asyncio.ensure_future(cover.async_stop_cover())
            await asyncio.sleep(0)
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", datetime.now(UTC))
            )
            await stop

        assert traveling_at_cancel == [True]
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
            await asyncio.wait_for(cover._await_confirmation_before_stop(), 1.0)

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
        stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

            assert cover.travel_calc.is_traveling() is False
            assert cover._feedback_wait_entity == "switch.open"

            echo_time = datetime.now(UTC)
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover.travel_calc._last_known_position_timestamp == pytest.approx(
            _expected_anchor(echo_time), abs=0.05
        )


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
        stub_switches(cover)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()
            await asyncio.sleep(0)

            assert cover.travel_calc.is_traveling() is False
            assert cover.travel_calc.current_position() == 0
            assert cover._feedback_wait_entity == "switch.open"

            echo_time = datetime.now(UTC)
            await cover._async_switch_state_changed(
                _echo_event("switch.open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.travel_calc.is_traveling() is True
        assert cover.travel_calc._last_known_position_timestamp == pytest.approx(
            _expected_anchor(echo_time), abs=0.05
        )
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
        stub_switches(cover)
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
        stub_switches(cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover_tilt()
            await asyncio.sleep(0)

            assert cover.tilt_calc.is_traveling() is False
            assert cover._feedback_wait_entity == "switch.tilt_open"

            echo_time = datetime.now(UTC)
            await cover._async_switch_state_changed(
                _echo_event("switch.tilt_open", "off", "on", echo_time)
            )
            await asyncio.sleep(0)

        assert cover.tilt_calc.is_traveling() is True
        assert cover.tilt_calc._last_known_position_timestamp == pytest.approx(
            _expected_anchor(echo_time), abs=0.05
        )

    @pytest.mark.asyncio
    async def test_driving_relay_already_on_starts_inline(self, make_cover):
        """A re-pulse on an already-ON relay flips no state on turn_on, so there
        is no ON echo to wait for — start inline."""
        cover = make_cover(
            control_mode="pulse",
            stop_switch="switch.stop",
            wait_for_relay_feedback=True,
        )
        stub_switches(cover, on=("switch.open",))
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
        stub_switches(cover)
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
        stub_switches(cover)
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
        stub_switches(cover)
        delays = []

        def fake_call_later(hass, delay, action):
            delays.append(delay)
            return MagicMock()

        with patch.object(cover_base, "async_call_later", fake_call_later):
            yield cover, delays

    @pytest.mark.asyncio
    async def test_short_remark_keeps_the_longer_remaining_window(self, marked_cover):
        """The timer already armed ends the longer window; the shorter re-mark
        neither truncates the deadline nor arms a timer of its own."""
        cover, delays = marked_cover
        clock = {"t": 1000.0}
        fake_time = MagicMock()
        fake_time.monotonic = lambda: clock["t"]

        with patch.object(cover_base, "time", fake_time):
            cover._mark_switch_pending("switch.open", 1, timeout=12.0)
            cover._mark_switch_pending("switch.open", 1, timeout=5.0)

        assert delays == [12.0]
        assert cover._pending_switch_deadlines["switch.open"] == 1012.0
        assert cover._pending_switch["switch.open"] == 2

    @pytest.mark.asyncio
    async def test_remaining_window_is_the_original_deadline(self, marked_cover):
        """4s into a 12s window a 5s re-mark would end at 9s: inside the window
        already armed, so the original deadline stands untouched."""
        cover, delays = marked_cover
        clock = {"t": 1000.0}
        fake_time = MagicMock()
        fake_time.monotonic = lambda: clock["t"]

        with patch.object(cover_base, "time", fake_time):
            cover._mark_switch_pending("switch.open", 1, timeout=12.0)
            clock["t"] += 4.0
            cover._mark_switch_pending("switch.open", 1, timeout=5.0)

        assert delays == [12.0]
        assert cover._pending_switch_deadlines["switch.open"] == 1012.0

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
        stub_switches(cover)
        first = asyncio.ensure_future(cover._wait_for_relay_echo("switch.open", 5))
        await asyncio.sleep(0)  # first registers its slot
        first.cancel()
        second = asyncio.ensure_future(cover._wait_for_relay_echo("switch.close", 5))
        await asyncio.sleep(0)  # second registers; first's finally runs
        await asyncio.sleep(0)
        assert _parked(cover, "switch.close")
        second.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await second

    @pytest.mark.asyncio
    async def test_cancelled_deferred_start_does_not_null_the_new_task(
        self, make_cover
    ):
        cover = make_cover(wait_for_relay_feedback=True)
        stub_switches(cover)

        def _park(entity_id):
            return cover.hass.async_create_task(
                cover._run_deferred_start(
                    lambda: cover._await_relay_confirmation(
                        entity_id, time.monotonic()
                    ),
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
        stub_switches(cover)
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


class TestSingleButtonFeedback:
    """The parked start resolves on the button's pre-counted ON echo."""

    @pytest.mark.asyncio
    async def test_open_parks_until_the_button_confirms(self, make_cover):
        cover = _make_single_button(
            make_cover, travel_time_open=30, travel_time_close=30
        )
        stub_switches(cover)
        cover.travel_calc.set_position(0)
        echo_time = datetime.now(UTC)
        with (
            patch.object(cover, "async_write_ha_state"),
            single_button_sleep_patch(),
        ):
            await cover.async_open_cover()
            await asyncio.sleep(0)  # press lands; feedback wait parked
            assert not cover.travel_calc.is_traveling()
            assert cover._pending_switch.get("switch.button", 0) == 2
            await cover._async_switch_state_changed(
                _echo_event("switch.button", "off", "on", echo_time)
            )
            await asyncio.sleep(0)
        assert cover.travel_calc.is_traveling()
        assert cover._pending_switch.get("switch.button", 0) == 1

    @pytest.mark.asyncio
    async def test_stop_during_the_wait_is_deferred_until_the_button_confirms(
        self, make_cover, feedback_clock
    ):
        """A stop is a press, and the run it ends started at the press before
        it: stopping while the start is still parked must wait out the
        confirmation, or the motor runs between the two presses untracked."""
        cover = _make_single_button(
            make_cover, travel_time_open=30, travel_time_close=30
        )
        stub_switches(cover)
        cover.travel_calc.set_position(0)
        # The relay switched three seconds before its echo reached us, so a
        # tracker anchored on the confirmation is visibly off 0% — evidence the
        # run between the two presses was counted.
        with (
            patch.object(cover, "async_write_ha_state"),
            single_button_sleep_patch(),
        ):
            await cover.async_open_cover()
            await asyncio.sleep(0)  # press lands; feedback wait parked
            assert cover._feedback_wait_entity == "switch.button"

            stop = asyncio.ensure_future(cover.async_stop_cover())
            await _turns()
            # Parked: neither the stop nor its press has gone anywhere while
            # the button is unconfirmed.
            assert not stop.done()
            assert len(_taps(cover, "switch.button")) == 1

            feedback_clock.advance(1)  # the relay switches after the command
            echo_time = datetime.fromtimestamp(feedback_clock.time(), UTC)
            feedback_clock.advance(3)  # the echo arrives three seconds later
            await cover._async_switch_state_changed(
                _echo_event("switch.button", "off", "on", echo_time)
            )
            await asyncio.wait_for(stop, 1.0)
            await asyncio.sleep(0)  # the stop press sequence runs

        assert len(_taps(cover, "switch.button")) == 2
        assert cover.travel_calc.current_position() > 0


class TestRelayFeedbackToggleReversal:
    """A reversal sent while the driving relay is unconfirmed (issue #268).

    The stop a reversal issues is a tap on toggle hardware and a press on a
    single button, so it is held back until the relay confirms — the deferral a
    plain stop already gets — and only then is the parked move torn down and
    tapped out. The run between the confirmation and the tap is counted, not
    lost.
    """

    @staticmethod
    async def _park_open_midway(make_cover, control_mode="toggle"):
        return await _park_open(
            make_cover,
            control_mode,
            position=50,
            travel_time_open=10,
            travel_time_close=10,
        )

    @pytest.mark.asyncio
    async def test_set_position_reversal_holds_the_stop_tap_until_the_echo(
        self, make_cover, feedback_clock
    ):
        cover = await self._park_open_midway(make_cover)
        with patch.object(cover, "_direction_change_delay", new_callable=AsyncMock):
            reversal = asyncio.ensure_future(cover.set_position(20))
            await _turns()
            # Nothing tapped while the open relay is unconfirmed.
            assert cover.hass.services.async_call.await_count == 0
            assert not reversal.done()

            feedback_clock.advance(1)  # the relay switches after the command
            echo_time = datetime.fromtimestamp(feedback_clock.time(), UTC)
            feedback_clock.advance(3)  # the echo arrives three seconds later
            await cover._async_switch_state_changed(
                _echo_event(
                    "switch.open",
                    "off",
                    "on",
                    echo_time,
                )
            )
            await asyncio.wait_for(reversal, 1.0)

        # The stop tap on the confirmed relay, then the close drive (which
        # releases the open relay before pulsing close, as every drive does).
        assert cover.hass.services.async_call.call_args_list == [
            _ha("turn_on", "switch.open"),
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]
        # The three seconds the motor ran between the confirmation and the
        # stop were counted: the close starts from there, not from 50.
        assert cover.travel_calc.current_position() > 50
        assert cover._last_command == SERVICE_CLOSE_COVER
        assert cover._feedback_wait_entity == "switch.close"

    @pytest.mark.asyncio
    async def test_opposite_button_reversal_holds_the_stop_tap_until_the_echo(
        self, make_cover, feedback_clock
    ):
        cover = await self._park_open_midway(make_cover, "toggle_opposite")
        with patch.object(cover, "_direction_change_delay", new_callable=AsyncMock):
            reversal = asyncio.ensure_future(cover.set_position(20))
            await _turns()
            assert cover.hass.services.async_call.await_count == 0

            feedback_clock.advance(1)  # the relay switches after the command
            echo_time = datetime.fromtimestamp(feedback_clock.time(), UTC)
            feedback_clock.advance(3)  # the echo arrives three seconds later
            await cover._async_switch_state_changed(
                _echo_event(
                    "switch.open",
                    "off",
                    "on",
                    echo_time,
                )
            )
            await _turns()
            # The stop is a tap on the opposite (close) relay.
            assert _taps(cover, "switch.close")
            await cover._async_switch_state_changed(
                _echo_event(
                    "switch.close",
                    "off",
                    "on",
                    datetime.fromtimestamp(feedback_clock.time(), UTC),
                )
            )
            await asyncio.wait_for(reversal, 1.0)

        assert cover.hass.services.async_call.call_args_list == [
            _ha("turn_on", "switch.close"),
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]
        assert cover.travel_calc.current_position() > 50

    @pytest.mark.asyncio
    async def test_close_during_the_wait_holds_the_stop_tap_until_the_echo(
        self, make_cover, feedback_clock
    ):
        """An endpoint command the other way stops the parked move (a second
        press then drives it) — and that stop is deferred like any other."""
        cover = await self._park_open_midway(make_cover)
        reversal = asyncio.ensure_future(cover.async_close_cover())
        await _turns()
        assert cover.hass.services.async_call.await_count == 0
        assert not reversal.done()

        feedback_clock.advance(1)  # the relay switches after the command
        echo_time = datetime.fromtimestamp(feedback_clock.time(), UTC)
        feedback_clock.advance(3)  # the echo arrives three seconds later
        await cover._async_switch_state_changed(
            _echo_event("switch.open", "off", "on", echo_time)
        )
        await asyncio.wait_for(reversal, 1.0)

        assert cover.hass.services.async_call.call_args_list == [
            _ha("turn_on", "switch.open")
        ]
        assert cover.travel_calc.is_traveling() is False
        assert cover.travel_calc.current_position() > 50
        assert cover._last_command is None
        assert cover._startup_delay_task is None
        assert cover._feedback_wait_entity is None

    @pytest.mark.asyncio
    async def test_tilt_reversal_holds_the_tilt_stop_tap_until_the_echo(
        self, make_cover, feedback_clock
    ):
        cover = _stub(
            _make_dual_motor(
                make_cover, control_mode="toggle", tilt_time_open=10, tilt_time_close=10
            )
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)
        await cover.async_open_cover_tilt()
        await asyncio.sleep(0)
        assert cover._feedback_wait_entity == "switch.tilt_open"
        cover.hass.services.async_call.reset_mock()

        reversal = asyncio.ensure_future(cover.async_close_cover_tilt())
        await _turns()
        assert cover.hass.services.async_call.await_count == 0
        assert not reversal.done()

        feedback_clock.advance(1)  # the relay switches after the command
        echo_time = datetime.fromtimestamp(feedback_clock.time(), UTC)
        feedback_clock.advance(3)  # the echo arrives three seconds later
        await cover._async_switch_state_changed(
            _echo_event(
                "switch.tilt_open",
                "off",
                "on",
                echo_time,
            )
        )
        await asyncio.wait_for(reversal, 1.0)

        # The tilt stop is a tap on the tilt relay that was driving.
        assert cover.hass.services.async_call.call_args_list == [
            _ha("turn_on", "switch.tilt_open")
        ]
        assert cover.tilt_calc.is_traveling() is False
        assert cover.tilt_calc.current_position() > 50
        assert cover._startup_delay_task is None

    @pytest.mark.asyncio
    async def test_external_reversal_does_not_wait_for_the_echo(self, make_cover):
        """A wall-switch reversal sends no tap of ours, so there is nothing to
        hold back; the handler must not park for the feedback timeout."""
        cover = await self._park_open_midway(make_cover, "toggle_opposite")
        cover._triggered_externally = True
        try:
            await asyncio.wait_for(cover.async_close_cover(), 0.5)
        finally:
            cover._triggered_externally = False

        assert cover.hass.services.async_call.await_count == 0
        assert cover._startup_delay_task is None

    @pytest.mark.asyncio
    async def test_reversal_proceeds_after_the_timeout(self, make_cover):
        """A silent relay must not hold the reversal for ever: the move's own
        timeout fallback runs, and the reversal proceeds behind it."""
        cover = _make_stubbed(
            make_cover, control_mode="toggle", travel_time_open=10, travel_time_close=10
        )
        cover.travel_calc.set_position(50)
        with (
            patch.object(cover_base, "RELAY_FEEDBACK_TIMEOUT", 0.05),
            patch.object(cover, "_direction_change_delay", new_callable=AsyncMock),
        ):
            await cover.async_open_cover()
            await asyncio.sleep(0)
            cover.hass.services.async_call.reset_mock()
            await asyncio.wait_for(cover.set_position(20), 1.0)

        assert cover.hass.services.async_call.call_args_list == [
            _ha("turn_on", "switch.open"),
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]
        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_single_button_reversal_holds_the_stop_press_until_the_echo(
        self, make_cover, feedback_clock
    ):
        cover = _stub(
            _make_single_button(make_cover, travel_time_open=10, travel_time_close=10)
        )
        cover.travel_calc.set_position(50)
        with (
            single_button_sleep_patch(),
            patch.object(cover, "_direction_change_delay", new_callable=AsyncMock),
        ):
            await cover.async_open_cover()
            await _turns()
            assert cover._feedback_wait_entity == "switch.button"
            cover.hass.services.async_call.reset_mock()

            reversal = asyncio.ensure_future(cover.set_position(20))
            await _turns()
            # No press while the button is unconfirmed.
            assert _taps(cover, "switch.button") == []
            assert not reversal.done()

            feedback_clock.advance(1)  # the relay switches after the command
            echo_time = datetime.fromtimestamp(feedback_clock.time(), UTC)
            feedback_clock.advance(3)  # the echo arrives three seconds later
            await cover._async_switch_state_changed(
                _echo_event(
                    "switch.button",
                    "off",
                    "on",
                    echo_time,
                )
            )
            await asyncio.wait_for(reversal, 1.0)
            await _turns()

        # A stop press, then the press that drives the other way.
        assert len(_taps(cover, "switch.button")) == 2
        assert cover.travel_calc.current_position() > 50


class TestRelayFeedbackSameRelayEchoes:
    """The confirmation is the drive's own ON echo, not an earlier tap's.

    A reversal on opposite-button hardware taps the same relay twice — the
    stop, then the drive — and a single button is pressed for both; on a mesh
    slower than the settle gap the earlier tap's echoes land after the drive
    has armed its wait. Its ON must not be read as the drive's confirmation,
    and its self-release OFF must not cost the drive its confirmation either
    (issue #268).
    """

    async def _reverse_opposite(self, make_cover, clock=time):
        cover = await _park_open(
            make_cover,
            "toggle_opposite",
            position=50,
            travel_time_open=10,
            travel_time_close=10,
        )
        reversal = asyncio.ensure_future(cover.set_position(20))
        await _turns()
        await cover._async_switch_state_changed(
            _echo_event(
                "switch.open", "off", "on", datetime.fromtimestamp(clock.time(), UTC)
            )
        )
        return cover, reversal

    @pytest.mark.asyncio
    async def test_a_late_stop_tap_echo_does_not_confirm_the_drive(
        self, make_cover, feedback_clock
    ):
        clock = feedback_clock
        with patch.object(cover_base, "DIRECTION_CHANGE_DELAY", 0.0):
            cover, reversal = await self._reverse_opposite(make_cover, clock)
            await asyncio.wait_for(reversal, 1.0)
        # Stop tap, release of the open relay, drive tap: the drive is parked
        # on the close relay's confirmation.
        assert len(_taps(cover, "switch.close")) == 2
        assert cover._feedback_wait_entity == "switch.close"

        # The stop tap's ON and self-release OFF arrive only now.
        stop_echo = datetime.fromtimestamp(clock.time() - 3, UTC)
        await cover._async_switch_state_changed(
            _echo_event("switch.close", "off", "on", stop_echo)
        )
        await asyncio.sleep(0)
        assert _parked(cover, "switch.close")
        assert cover.travel_calc.is_traveling() is False
        await cover._async_switch_state_changed(
            _echo_event("switch.close", "on", "off", stop_echo)
        )
        await asyncio.sleep(0)
        assert _parked(cover, "switch.close")

        # The drive's own ON is the confirmation, and anchors tracking.
        clock.advance(1)
        drive_echo = datetime.fromtimestamp(clock.time(), UTC)
        drive_anchor = clock.monotonic()
        clock.advance(1)  # delivery one second after the drive echo was stamped
        await cover._async_switch_state_changed(
            _echo_event("switch.close", "off", "on", drive_echo)
        )
        await asyncio.sleep(0)
        assert cover.travel_calc.is_traveling() is True
        assert cover.travel_calc._last_known_position_timestamp == drive_anchor

    @pytest.mark.asyncio
    async def test_a_prompt_stop_tap_echo_is_filtered_and_the_drive_confirms(
        self, make_cover
    ):
        """The fast-mesh ordering: the stop tap's echoes land inside the settle
        gap, before the drive taps, and the drive's own echo then confirms."""
        with patch.object(cover_base, "DIRECTION_CHANGE_DELAY", 0.05):
            cover, reversal = await self._reverse_opposite(make_cover)
            await _turns()
            assert len(_taps(cover, "switch.close")) == 1
            stop_echo = datetime.now(UTC)
            await cover._async_switch_state_changed(
                _echo_event("switch.close", "off", "on", stop_echo)
            )
            await cover._async_switch_state_changed(
                _echo_event("switch.close", "on", "off", stop_echo)
            )
            await asyncio.wait_for(reversal, 1.0)
        assert len(_taps(cover, "switch.close")) == 2
        assert _parked(cover, "switch.close")
        assert cover.travel_calc.is_traveling() is False

        drive_echo = datetime.now(UTC)
        await cover._async_switch_state_changed(
            _echo_event("switch.close", "off", "on", drive_echo)
        )
        await asyncio.sleep(0)
        assert cover.travel_calc.is_traveling() is True
        assert cover.travel_calc._last_known_position_timestamp == pytest.approx(
            _expected_anchor(drive_echo), abs=0.05
        )

    @pytest.mark.asyncio
    async def test_single_button_confirms_on_the_last_press_not_a_late_nudge(
        self, make_cover, feedback_clock
    ):
        """A reversal needs a stop press and a drive press on the one button;
        the stop press's late echoes must not anchor tracking."""
        clock = feedback_clock
        cover = _stub(
            _make_single_button(make_cover, travel_time_open=10, travel_time_close=10)
        )
        cover.travel_calc.set_position(50)
        cover._phase = Phase.MOVING_UP
        with single_button_sleep_patch():
            await cover.async_close_cover()
            await _turns()
        # Both presses are out; the move is parked on the button's confirmation.
        assert len(_taps(cover, "switch.button")) == 2
        assert cover._feedback_wait_entity == "switch.button"

        # The stop press's echoes arrive late, after the drive press.
        stop_echo = datetime.fromtimestamp(clock.time() - 3, UTC)
        await cover._async_switch_state_changed(
            _echo_event("switch.button", "off", "on", stop_echo)
        )
        await asyncio.sleep(0)
        assert _parked(cover, "switch.button")
        await cover._async_switch_state_changed(
            _echo_event("switch.button", "on", "off", stop_echo)
        )
        await asyncio.sleep(0)
        assert _parked(cover, "switch.button")
        assert cover.travel_calc.is_traveling() is False

        clock.advance(1)
        drive_echo = datetime.fromtimestamp(clock.time(), UTC)
        drive_anchor = clock.monotonic()
        clock.advance(1)  # delivery one second after the drive echo was stamped
        await cover._async_switch_state_changed(
            _echo_event("switch.button", "off", "on", drive_echo)
        )
        await asyncio.sleep(0)
        assert cover.travel_calc.is_traveling() is True
        assert cover.travel_calc._last_known_position_timestamp == drive_anchor

    @pytest.mark.asyncio
    async def test_single_button_that_never_reports_off_stays_parked(self, make_cover):
        """The count is exact, by design: a button reporting its ON but never
        its OFF leaves a mark per press outstanding, so a multi-press plan's
        confirming ON is not taken and the move starts on the timeout fallback.
        A single press still confirms (its ON leaves only its own OFF)."""
        cover = _stub(
            _make_single_button(make_cover, travel_time_open=10, travel_time_close=10)
        )
        cover.travel_calc.set_position(50)
        cover._phase = Phase.MOVING_UP
        with single_button_sleep_patch():
            await cover.async_close_cover()
            await _turns()
        assert len(_taps(cover, "switch.button")) == 2

        for _ in range(2):
            await cover._async_switch_state_changed(
                _echo_event("switch.button", "off", "on", datetime.now(UTC))
            )
            await asyncio.sleep(0)
        assert _parked(cover, "switch.button")
        assert cover._pending_switch["switch.button"] == 2


class TestRelayFeedbackWallClockSteps:
    """An NTP step anywhere across the feedback path must not move the position.

    The echo's ``last_changed`` is wall-clock, so the feedback path is the one
    place tracking crosses from the steppable clock to the monotonic one. A
    step on either side of that conversion has to leave the travel untouched.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "stage",
        [
            "before_command",
            "before_echo",
            "between_echo_and_resume",
            "after_start",
            "after_update",
        ],
    )
    @pytest.mark.parametrize("step", [-3600, 3600])
    async def test_wall_steps_each_feedback_stage(self, make_cover, step, stage):
        clock = FakeClock(wall=1_700_000_000, mono=5_000)
        cover = make_cover(wait_for_relay_feedback=True)
        stub_switches(cover)
        with (
            patch.object(cover_base, "time", clock),
            patch.object(travel_calculator, "time", clock),
            patch.object(cover, "async_write_ha_state"),
        ):
            cover.travel_calc.set_position(0)
            if stage == "before_command":
                clock.step_wall(step)
            await cover.async_open_cover()
            await asyncio.sleep(0)
            clock.advance(3)
            if stage == "before_echo":
                clock.step_wall(step)
            stamp = datetime.fromtimestamp(clock.time(), UTC)
            cover._resolve_relay_feedback(
                "switch.open", "on", type("Echo", (), {"last_changed": stamp})()
            )
            if stage == "between_echo_and_resume":
                clock.step_wall(step)
            await asyncio.sleep(0)

            anchor = cover.travel_calc._last_known_position_timestamp
            assert 5000 <= anchor <= 5003
            if stage == "after_start":
                clock.step_wall(step)
            clock.advance(3)
            pos = cover.travel_calc.current_position()
            if stage == "after_update":
                cover.travel_calc.update_position(pos)
                clock.step_wall(step)
            assert cover.travel_calc.current_position() == pos
            assert 10 <= pos <= 20
            clock.advance(40)
            assert cover.travel_calc.position_reached()
            await cover.async_will_remove_from_hass()

    @pytest.mark.asyncio
    async def test_feedback_wait_replacement_owns_cleanup(self, make_cover):
        """Two waits alive at once: cancelling the older leaves the slot alone.

        The mirror of test_cancelled_wait_does_not_clear_the_new_wait, which
        cancels before the replacement registers. Resolving the survivor is
        what clears the slot.
        """
        cover = make_cover()
        first = asyncio.create_task(cover._wait_for_relay_echo("switch.open", 5))
        await asyncio.sleep(0)
        second = asyncio.create_task(cover._wait_for_relay_echo("switch.close", 5))
        await asyncio.sleep(0)
        second_future = cover._feedback_wait_future

        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert cover._feedback_wait_future is second_future

        second_future.set_result(None)
        assert await second is None
        assert cover._feedback_wait_future is None
