"""Tests for WrappedCoverTimeBased._send_open/close/stop.

Each test verifies that the correct cover.* service call is made.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from homeassistant.const import STATE_UNAVAILABLE

from custom_components.cover_time_based.cover_wrapped import WrappedCoverTimeBased


# CoverEntityFeature bit values (OPEN=1, CLOSE=2, SET_POSITION=4, STOP=8).
_F_OPEN = 1
_F_CLOSE = 2
_F_SET_POSITION = 4
_F_STOP = 8


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _make_wrapped_cover(
    cover_entity_id="cover.inner",
    force_time_based_position=False,
    reports_command_not_endpoint=False,
    tilt_time_close=None,
    tilt_time_open=None,
    tilt_mode="none",
):
    """Create a WrappedCoverTimeBased wired to a mock hass."""
    tilt_strategy = None
    if tilt_time_close is not None and tilt_time_open is not None:
        # Map tilt_mode to strategy
        from custom_components.cover_time_based.tilt_strategies import (
            InlineTilt,
            SequentialCloseTilt,
        )

        if tilt_mode == "inline":
            tilt_strategy = InlineTilt()
        elif tilt_mode in ("sequential_close", "sequential"):
            tilt_strategy = SequentialCloseTilt()

    cover = WrappedCoverTimeBased(
        device_id="test_wrapped",
        name="Test Wrapped",
        tilt_strategy=tilt_strategy,
        travel_time_close=30,
        travel_time_open=30,
        tilt_time_close=tilt_time_close,
        tilt_time_open=tilt_time_open,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        endpoint_runon_time=None,
        min_movement_time=None,
        cover_entity_id=cover_entity_id,
        force_time_based_position=force_time_based_position,
        reports_command_not_endpoint=reports_command_not_endpoint,
    )
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.async_create_task = lambda coro: asyncio.ensure_future(coro)
    cover.hass = hass
    return cover


def _set_wrapped_features(cover, features, *, state="open", current_position=None):
    """Make the wrapped cover entity advertise the given supported_features."""
    st = MagicMock()
    st.state = state
    attrs = {"supported_features": features}
    if current_position is not None:
        attrs["current_position"] = current_position
    st.attributes = attrs
    cover.hass.states.get = lambda eid: st if eid == cover._cover_entity_id else None
    return st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _calls(mock: AsyncMock):
    """Return the list of calls made on hass.services.async_call."""
    return mock.call_args_list


def _cover_svc(service, entity_id):
    """Shorthand for a cover domain service call."""
    return call("cover", service, {"entity_id": entity_id}, False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWrappedSendOpen:
    """_send_open delegates to cover.open_cover."""

    @pytest.mark.asyncio
    async def test_send_open(self):
        cover = _make_wrapped_cover()
        await cover._send_open()

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("open_cover", "cover.inner"),
        ]


class TestWrappedSendClose:
    """_send_close delegates to cover.close_cover."""

    @pytest.mark.asyncio
    async def test_send_close(self):
        cover = _make_wrapped_cover()
        await cover._send_close()

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("close_cover", "cover.inner"),
        ]


class TestWrappedSendStop:
    """_send_stop delegates to cover.stop_cover."""

    @pytest.mark.asyncio
    async def test_send_stop(self):
        cover = _make_wrapped_cover()
        await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("stop_cover", "cover.inner"),
        ]


class TestWrappedViaHandleCommand:
    """Integration test: _async_handle_command routes through _send_* correctly."""

    @pytest.mark.asyncio
    async def test_handle_command_open(self):
        from homeassistant.const import SERVICE_OPEN_COVER

        cover = _make_wrapped_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_OPEN_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("open_cover", "cover.inner"),
        ]

    @pytest.mark.asyncio
    async def test_handle_command_close(self):
        from homeassistant.const import SERVICE_CLOSE_COVER

        cover = _make_wrapped_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_CLOSE_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("close_cover", "cover.inner"),
        ]

    @pytest.mark.asyncio
    async def test_handle_command_stop(self):
        from homeassistant.const import SERVICE_STOP_COVER

        cover = _make_wrapped_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_handle_command(SERVICE_STOP_COVER)

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("stop_cover", "cover.inner"),
        ]


# ---------------------------------------------------------------------------
# async_added_to_hass — state listener registration
# ---------------------------------------------------------------------------


class TestWrappedAsyncAddedToHass:
    """Test that async_added_to_hass registers a state listener."""

    @pytest.mark.asyncio
    async def test_registers_cover_listener(self):
        cover = _make_wrapped_cover(cover_entity_id="cover.inner")
        unsub = MagicMock()

        with (
            patch.object(cover, "async_get_last_state", return_value=None),
            patch(
                "custom_components.cover_time_based.cover_wrapped.async_track_state_change_event",
                return_value=unsub,
            ) as mock_track,
        ):
            await cover.async_added_to_hass()

        mock_track.assert_called_once()
        # Verify the entity list includes the wrapped cover
        assert mock_track.call_args[0][1] == ["cover.inner"]
        assert unsub in cover._state_listener_unsubs


class TestWrappedSameDirectionRetarget:
    """Same-direction retarget must not re-issue the directional command.

    Wrapped mode never had the toggle-mode runaway (it delegates STOP to the
    underlying cover's real stop_cover), but the shared set_position fix
    should still skip the redundant close_cover call when the cover is
    already travelling the right way.
    """

    @pytest.mark.asyncio
    async def test_retarget_same_direction_does_not_reissue_command(self):
        cover = _make_wrapped_cover(cover_entity_id="cover.inner")
        # Avoid scheduling a real auto-updater / writing state on the mock hass.
        cover.start_auto_updater = MagicMock()
        cover.async_write_ha_state = MagicMock()
        cover.async_schedule_update_ha_state = MagicMock()
        cover.travel_calc.set_position(100)  # fully open

        with patch.object(cover, "_send_close", wraps=cover._send_close) as send_close:
            await cover.set_position(60)
            assert cover.travel_calc.is_traveling()
            assert send_close.call_count == 1

            # Same direction (still closing), lower target.
            await cover.set_position(30)
            assert send_close.call_count == 1
            assert cover.travel_calc._travel_to_position == 30


class TestWrappedCapabilityDetection:
    """Detect the wrapped entity's SET_POSITION / STOP support from
    supported_features, treating unavailable/unknown as 'no support'.
    """

    def test_supports_set_position_true(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION)
        assert cover._wrapped_supports_set_position() is True

    def test_supports_set_position_false_when_absent(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP)
        assert cover._wrapped_supports_set_position() is False

    def test_supports_stop_true(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP)
        assert cover._wrapped_supports_stop() is True

    def test_issue93_features_7_means_set_position_no_stop(self):
        # supported_features = 7 == OPEN|CLOSE|SET_POSITION, no STOP (bit 8).
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)
        assert cover._wrapped_supports_set_position() is True
        assert cover._wrapped_supports_stop() is False

    def test_detection_false_when_unavailable(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7, state=STATE_UNAVAILABLE)
        assert cover._wrapped_supports_set_position() is False
        assert cover._wrapped_supports_stop() is False

    def test_detection_false_when_state_missing(self):
        cover = _make_wrapped_cover()
        cover.hass.states.get = lambda eid: None
        assert cover._wrapped_supports_set_position() is False
        assert cover._wrapped_supports_stop() is False


class TestUseNativeSetPosition:
    """_use_native_set_position auto-detects SET_POSITION support, but the
    force_time_based_position override forces the legacy time-based path.
    """

    def test_native_when_set_position_supported(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)
        assert cover._use_native_set_position() is True

    def test_legacy_when_force_time_based(self):
        cover = _make_wrapped_cover(force_time_based_position=True)
        _set_wrapped_features(cover, 7)
        assert cover._use_native_set_position() is False

    def test_legacy_when_set_position_unsupported(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP)
        assert cover._use_native_set_position() is False

    def test_legacy_when_reports_command_not_endpoint(self):
        # Command-echo mode tracks purely by time, so native set_position must
        # never be forwarded even if the (misconfigured) wrapped cover advertises
        # SET_POSITION — otherwise a self-driven native move could be
        # reinterpreted as an open/close command by _handle_command_state.
        cover = _make_wrapped_cover(reports_command_not_endpoint=True)
        _set_wrapped_features(cover, 7)  # SET_POSITION supported
        assert cover._use_native_set_position() is False


class TestWrappedNativeSetPosition:
    """When the wrapped entity supports SET_POSITION, set_position forwards
    cover.set_cover_position directly (the device stops itself), while the
    time-based tracker still animates so the integration reports live motion.
    """

    def _prep(self, cover):
        # Avoid scheduling a real auto-updater / writing state on the mock hass.
        cover.start_auto_updater = MagicMock()
        cover.async_write_ha_state = MagicMock()
        cover.async_schedule_update_ha_state = MagicMock()

    @pytest.mark.asyncio
    async def test_forwards_set_cover_position_directly(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)  # OPEN|CLOSE|SET_POSITION, no STOP
        self._prep(cover)
        cover.travel_calc.set_position(100)

        await cover.set_position(60)

        assert _calls(cover.hass.services.async_call) == [
            call(
                "cover",
                "set_cover_position",
                {"entity_id": "cover.inner", "position": 60},
                False,
            ),
        ]
        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._travel_to_position == 60

    @pytest.mark.asyncio
    async def test_does_not_call_open_close_or_stop(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)
        self._prep(cover)
        cover.travel_calc.set_position(0)

        with (
            patch.object(cover, "_send_open", wraps=cover._send_open) as so,
            patch.object(cover, "_send_close", wraps=cover._send_close) as sc,
            patch.object(cover, "_send_stop", wraps=cover._send_stop) as ss,
        ):
            await cover.set_position(40)

        so.assert_not_called()
        sc.assert_not_called()
        ss.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_time_based_uses_legacy_path(self):
        cover = _make_wrapped_cover(force_time_based_position=True)
        _set_wrapped_features(cover, 7)
        self._prep(cover)
        cover.travel_calc.set_position(100)

        await cover.set_position(60)

        services = [c.args[1] for c in _calls(cover.hass.services.async_call)]
        assert "set_cover_position" not in services
        assert "close_cover" in services

    @pytest.mark.asyncio
    async def test_no_native_support_uses_legacy_path(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP)
        self._prep(cover)
        cover.travel_calc.set_position(100)

        await cover.set_position(60)

        services = [c.args[1] for c in _calls(cover.hass.services.async_call)]
        assert "set_cover_position" not in services
        assert "close_cover" in services


class TestWrappedNativeMoveNoHijack:
    """While the tracker animates a native set_position move, the wrapped
    cover's own opening/closing state (a side effect of our forwarded
    command) must not hijack the move into a full open/close. Once the
    tracker is idle, a genuine external opening/closing is honored again.
    """

    def _prep(self, cover):
        cover.start_auto_updater = MagicMock()
        cover.async_write_ha_state = MagicMock()
        cover.async_schedule_update_ha_state = MagicMock()

    @pytest.mark.asyncio
    async def test_opening_during_native_move_is_not_hijacked(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)
        self._prep(cover)
        cover.travel_calc.set_position(0)
        await cover.set_position(60)  # native; tracker now travelling up
        assert cover.travel_calc.is_traveling()

        # Disable the bounce grace window so we exercise the is_traveling guard.
        cover._last_self_command_time = None
        with patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock:
            await cover._handle_external_state_change(
                "cover.inner", "closed", "opening"
            )

        open_mock.assert_not_awaited()
        assert cover.travel_calc._travel_to_position == 60

    @pytest.mark.asyncio
    async def test_opening_when_idle_is_honored(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)
        self._prep(cover)
        cover.travel_calc.set_position(0)  # idle, not travelling
        cover._last_self_command_time = None

        with patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock:
            await cover._handle_external_state_change(
                "cover.inner", "closed", "opening"
            )

        open_mock.assert_awaited_once()


class TestWrappedSendStopCapabilityAware:
    """_send_stop adapts to the wrapped cover's capabilities:
    - native STOP supported            -> cover.stop_cover
    - no STOP but SET_POSITION         -> freeze via set_cover_position(calc)
    - capabilities unknown / neither   -> legacy cover.stop_cover fallback
    """

    @pytest.mark.asyncio
    async def test_uses_native_stop_when_supported(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP)
        await cover._send_stop()

        assert _cover_svc("stop_cover", "cover.inner") in _calls(
            cover.hass.services.async_call
        )

    @pytest.mark.asyncio
    async def test_freezes_via_set_position_when_no_native_stop(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)  # SET_POSITION, no STOP
        cover.travel_calc.set_position(43)

        await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == [
            call(
                "cover",
                "set_cover_position",
                {"entity_id": "cover.inner", "position": 43},
                False,
            ),
        ]

    @pytest.mark.asyncio
    async def test_falls_back_to_stop_cover_when_features_unknown(self):
        cover = _make_wrapped_cover()
        cover.hass.states.get = lambda eid: None  # unknown capabilities
        await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("stop_cover", "cover.inner"),
        ]

    @pytest.mark.asyncio
    async def test_async_stop_cover_midmove_freezes_at_calculated_position(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)
        cover.start_auto_updater = MagicMock()
        cover.async_write_ha_state = MagicMock()
        cover.async_schedule_update_ha_state = MagicMock()
        cover.travel_calc.set_position(55)  # frozen estimate

        await cover.async_stop_cover()

        assert call(
            "cover",
            "set_cover_position",
            {"entity_id": "cover.inner", "position": 55},
            False,
        ) in _calls(cover.hass.services.async_call)


class TestWrappedNativeInheritsBaseCeremony:
    """Native forwarding now runs through the base set_position, so it inherits
    min_movement_time suppression, startup-delay conflict handling, and the
    self-stopping auto-stop guard. It is also gated to travel-only covers (no
    tilt strategy) so tilt covers keep the full tilt-aware time-based path.
    """

    def _prep(self, cover):
        cover.start_auto_updater = MagicMock()
        cover.async_write_ha_state = MagicMock()
        cover.async_schedule_update_ha_state = MagicMock()

    @pytest.mark.asyncio
    async def test_min_movement_time_suppresses_tiny_native_move(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)
        self._prep(cover)
        cover._min_movement_time = 2.0
        cover.travel_calc.set_position(100)

        await cover.set_position(99)  # 1% * 30s = 0.3s < 2s → suppressed

        services = [c.args[1] for c in _calls(cover.hass.services.async_call)]
        assert "set_cover_position" not in services
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_startup_delay_pending_does_not_double_forward(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)
        cover.async_write_ha_state = MagicMock()
        cover.async_schedule_update_ha_state = MagicMock()
        cover._travel_startup_delay = 2.0
        cover.travel_calc.set_position(100)

        await cover.set_position(60)  # forwards once, startup-delay task pending
        await cover.set_position(60)  # same dir while pending → base skips

        services = [c.args[1] for c in _calls(cover.hass.services.async_call)]
        assert services.count("set_cover_position") == 1
        cover._cancel_startup_delay_task()

    def test_native_disabled_when_tilt_strategy_present(self):
        cover = _make_wrapped_cover()
        cover._tilt_strategy = object()  # any configured tilt strategy
        _set_wrapped_features(cover, 7 | 16 | 32)
        assert cover._use_native_set_position() is False

    def test_motor_stops_itself_true_for_native(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)
        assert cover._motor_stops_itself() is True

    def test_motor_stops_itself_false_for_legacy(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP)
        assert cover._motor_stops_itself() is False

    @pytest.mark.asyncio
    async def test_position_driver_selection_matches_native_flag(self):
        from custom_components.cover_time_based.drivers import (
            NativePositionDriver,
            TimedPositionDriver,
        )

        cover = _make_wrapped_cover()

        _set_wrapped_features(cover, 7)  # OPEN|CLOSE|SET_POSITION -> native
        assert isinstance(cover._position_driver(), NativePositionDriver)
        assert cover._motor_stops_itself() is True

        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP)  # no SET_POSITION
        assert isinstance(cover._position_driver(), TimedPositionDriver)
        assert cover._motor_stops_itself() is False

    @pytest.mark.asyncio
    async def test_auto_stop_sends_no_relay_stop_for_native(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)
        self._prep(cover)
        cover.travel_calc.set_position(100)
        await cover.set_position(60)  # one set_cover_position so far
        # Tracker arrives at target; auto-stop must not re-command the device.
        cover.travel_calc.set_position(60)
        await cover.auto_stop_if_necessary()

        services = [c.args[1] for c in _calls(cover.hass.services.async_call)]
        assert services == ["set_cover_position"]  # no extra stop_cover / re-set


class TestWrappedCommandEchoMode:
    """reports_command_not_endpoint: the wrapped entity's state is a command
    echo (open/close/stop), not an endpoint. Each state maps straight to a
    time-based command; we never snap to an endpoint. Issue #137.
    """

    @pytest.mark.asyncio
    async def test_default_flag_is_false(self):
        cover = _make_wrapped_cover()
        assert cover._reports_command_not_endpoint is False

    @pytest.mark.asyncio
    async def test_closed_is_close_command_not_snap(self):
        # The headline bug: open -> closed must start a timed close, not snap to 0.
        cover = _make_wrapped_cover(reports_command_not_endpoint=True)
        with (
            patch.object(cover, "async_close_cover", new=AsyncMock()) as close_mock,
            patch.object(cover, "_snap_to_position", new=AsyncMock()) as snap_mock,
        ):
            await cover._handle_external_state_change("cover.inner", "open", "closed")
        close_mock.assert_awaited_once()
        snap_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_is_stop_command(self):
        cover = _make_wrapped_cover(reports_command_not_endpoint=True)
        with patch.object(cover, "async_stop_cover", new=AsyncMock()) as stop_mock:
            await cover._handle_external_state_change(
                "cover.inner", "closed", "unknown"
            )
        stop_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_open_is_open_command(self):
        cover = _make_wrapped_cover(reports_command_not_endpoint=True)
        with patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock:
            await cover._handle_external_state_change("cover.inner", "unknown", "open")
        open_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_settle_guard_closing_to_closed_is_command(self):
        # No old_val inspection: closing -> closed is still a close command,
        # never a snap-to-0.
        cover = _make_wrapped_cover(reports_command_not_endpoint=True)
        with (
            patch.object(cover, "async_close_cover", new=AsyncMock()) as close_mock,
            patch.object(cover, "_snap_to_position", new=AsyncMock()) as snap_mock,
        ):
            await cover._handle_external_state_change(
                "cover.inner", "closing", "closed"
            )
        close_mock.assert_awaited_once()
        snap_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unavailable_is_noop(self):
        cover = _make_wrapped_cover(reports_command_not_endpoint=True)
        with (
            patch.object(cover, "async_open_cover", new=AsyncMock()) as o,
            patch.object(cover, "async_close_cover", new=AsyncMock()) as c,
            patch.object(cover, "async_stop_cover", new=AsyncMock()) as s,
        ):
            await cover._handle_external_state_change(
                "cover.inner", "closed", "unavailable"
            )
        o.assert_not_awaited()
        c.assert_not_awaited()
        s.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_opening_is_open_command(self):
        cover = _make_wrapped_cover(reports_command_not_endpoint=True)
        with patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock:
            await cover._handle_external_state_change(
                "cover.inner", "closed", "opening"
            )
        open_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_closing_is_close_command(self):
        cover = _make_wrapped_cover(reports_command_not_endpoint=True)
        with patch.object(cover, "async_close_cover", new=AsyncMock()) as close_mock:
            await cover._handle_external_state_change("cover.inner", "open", "closing")
        close_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flag_off_closed_still_snaps_to_zero(self):
        # Regression: with the flag off, closed is still the 0% endpoint.
        cover = _make_wrapped_cover()  # flag defaults off
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP, state="closed")
        with patch.object(cover, "_snap_to_position", new=AsyncMock()) as snap_mock:
            await cover._handle_external_state_change("cover.inner", "open", "closed")
        snap_mock.assert_awaited_once_with(0)


class TestUseNativeTilt:
    """_use_native_tilt() requires InlineTilt + wrapped SET_TILT_POSITION,
    and is off for command-echo covers and non-inline strategies."""

    _F_SET_TILT = 128  # CoverEntityFeature.SET_TILT_POSITION

    def test_native_tilt_when_inline_and_set_tilt_supported(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | self._F_SET_TILT)
        assert cover._use_native_tilt() is True

    def test_not_native_without_set_tilt_position(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE)  # no SET_TILT_POSITION
        assert cover._use_native_tilt() is False

    def test_not_native_for_non_inline_strategy(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="sequential_close"
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | self._F_SET_TILT)
        assert cover._use_native_tilt() is False

    def test_not_native_for_command_echo(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5,
            tilt_time_open=5,
            tilt_mode="inline",
            reports_command_not_endpoint=True,
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | self._F_SET_TILT)
        assert cover._use_native_tilt() is False

    def test_not_native_without_tilt_configured(self):
        cover = _make_wrapped_cover()  # no tilt times → no tilt strategy
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | self._F_SET_TILT)
        assert cover._use_native_tilt() is False


class TestNativeTiltForwarding:
    """Native tilt covers forward set_cover_tilt_position and animate tilt_calc,
    and the auto-updater issues no relay stop when the tilt move completes."""

    _F_SET_TILT = 128

    def _prep(self, cover):
        cover.start_auto_updater = MagicMock()
        cover.async_write_ha_state = MagicMock()
        cover.async_schedule_update_ha_state = MagicMock()

    def _native_tilt_cover(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | self._F_SET_TILT)
        self._prep(cover)
        return cover

    @pytest.mark.asyncio
    async def test_set_tilt_position_forwards_natively(self):
        cover = self._native_tilt_cover()
        cover.tilt_calc.set_position(100)

        await cover.async_set_cover_tilt_position(tilt_position=30)

        services = [
            (c.args[1], c.args[2]) for c in _calls(cover.hass.services.async_call)
        ]
        assert (
            "set_cover_tilt_position",
            {"entity_id": "cover.inner", "tilt_position": 30},
        ) in services
        assert all(svc != "close_cover" and svc != "open_cover" for svc, _ in services)
        assert cover.tilt_calc.is_traveling()
        assert cover.tilt_calc._travel_to_position == 30

    @pytest.mark.asyncio
    async def test_open_close_tilt_forward_natively(self):
        cover = self._native_tilt_cover()
        cover.tilt_calc.set_position(0)

        await cover.async_open_cover_tilt()

        services = [c.args[1] for c in _calls(cover.hass.services.async_call)]
        assert "set_cover_tilt_position" in services
        assert "open_cover_tilt" not in services  # not the dual-motor relay path

        tilt_call = next(
            c
            for c in _calls(cover.hass.services.async_call)
            if c.args[1] == "set_cover_tilt_position"
        )
        assert tilt_call.args[2] == {"entity_id": "cover.inner", "tilt_position": 100}

    @pytest.mark.asyncio
    async def test_tilt_already_at_target_is_noop(self):
        cover = self._native_tilt_cover()
        cover.tilt_calc.set_position(30)

        await cover.async_set_cover_tilt_position(tilt_position=30)

        assert _calls(cover.hass.services.async_call) == []

    @pytest.mark.asyncio
    async def test_auto_stop_sends_no_relay_stop_for_native_tilt(self):
        cover = self._native_tilt_cover()
        cover.tilt_calc.set_position(100)
        await cover.async_set_cover_tilt_position(tilt_position=30)
        cover.hass.services.async_call.reset_mock()

        # Simulate the tilt animation having reached the target, then let the
        # auto-updater's stop check run: a native tilt device holds itself.
        cover.tilt_calc.set_position(30)
        await cover.auto_stop_if_necessary()

        services = [c.args[1] for c in _calls(cover.hass.services.async_call)]
        assert "stop_cover" not in services
        assert "close_cover" not in services


class TestTiltSettleSnap:
    """On settle, a native-tilt cover snaps tilt_calc to the device's reported
    current_tilt_position; non-native strategies do not."""

    _F_SET_TILT = 128

    def _prep(self, cover):
        cover.start_auto_updater = MagicMock()
        cover.async_write_ha_state = MagicMock()
        cover.async_schedule_update_ha_state = MagicMock()

    @pytest.mark.asyncio
    async def test_snaps_tilt_to_reported_on_settle(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        st = _set_wrapped_features(
            cover, _F_OPEN | _F_CLOSE | self._F_SET_TILT, state="open"
        )
        st.attributes["current_position"] = 100
        st.attributes["current_tilt_position"] = 45
        self._prep(cover)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(60)  # optimistic/stale

        await cover._handle_external_state_change("cover.inner", "opening", "open")

        assert cover.tilt_calc.current_position() == 45

    @pytest.mark.asyncio
    async def test_no_tilt_snap_for_non_native_strategy(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="sequential_close"
        )
        st = _set_wrapped_features(
            cover, _F_OPEN | _F_CLOSE | self._F_SET_TILT, state="open"
        )
        st.attributes["current_position"] = 100
        st.attributes["current_tilt_position"] = 45
        self._prep(cover)
        cover.travel_calc.set_position(100)
        # SequentialCloseTilt's own (pre-existing, unrelated) snap_trackers_to_
        # physical forces tilt to 100 whenever travel is not at 0 — set tilt to
        # 100 up front so that mechanism is a no-op here, isolating the
        # assertion to whether _maybe_snap_to_reported_tilt (this task) pulls
        # tilt from the wrapped device's reported current_tilt_position (45).
        cover.tilt_calc.set_position(100)

        await cover._handle_external_state_change("cover.inner", "opening", "open")

        assert cover.tilt_calc.current_position() == 100  # unchanged; not native

    @pytest.mark.asyncio
    async def test_snaps_tilt_to_zero_on_settle(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        st = _set_wrapped_features(
            cover, _F_OPEN | _F_CLOSE | self._F_SET_TILT, state="open"
        )
        st.attributes["current_position"] = 100
        st.attributes["current_tilt_position"] = 0
        self._prep(cover)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(50)

        await cover._handle_external_state_change("cover.inner", "opening", "open")

        assert cover.tilt_calc.current_position() == 0


class TestNativeCouplingNeutralized:
    """A position move on a native-tilt cover schedules no main-motor tilt
    restore — the device manages its own slats."""

    _F_SET_TILT = 128

    @pytest.mark.asyncio
    async def test_no_tilt_restore_scheduled_for_native(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | self._F_SET_TILT)
        cover._tilt_restore_target = 77  # pretend something set it

        tilt_target, pre_step_delay, started = await cover._plan_tilt_for_travel(
            50, "close", current_pos=100, current_tilt=60
        )

        assert (tilt_target, pre_step_delay, started) == (0, 0.0, False)
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_coupling_preserved_for_non_native(self):
        # A non-native inline cover (no SET_TILT_POSITION) keeps the base plan,
        # which for an inline mid-position move schedules a tilt restore.
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE)  # no SET_TILT_POSITION
        cover.tilt_calc.set_position(60)

        _, _, started = await cover._plan_tilt_for_travel(
            50, "close", current_pos=100, current_tilt=60
        )

        assert started is False
        assert cover._tilt_restore_target == 60  # base scheduled a restore


class TestNativePositionWithNativeTilt:
    """A native-both-inline cover drives position natively too (symmetry);
    timed-tilt strategies keep the timed position path."""

    _F_SET_TILT = 128

    def _prep(self, cover):
        cover.start_auto_updater = MagicMock()
        cover.async_write_ha_state = MagicMock()
        cover.async_schedule_update_ha_state = MagicMock()

    def test_native_position_enabled_for_native_both_inline(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(
            cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | self._F_SET_TILT
        )
        assert cover._use_native_set_position() is True

    def test_timed_position_kept_for_sequential_even_with_set_position(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="sequential_close"
        )
        _set_wrapped_features(
            cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | self._F_SET_TILT
        )
        assert cover._use_native_set_position() is False

    def test_timed_position_kept_for_inline_without_set_tilt(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(
            cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION
        )  # no SET_TILT
        assert cover._use_native_set_position() is False

    @pytest.mark.asyncio
    async def test_position_move_forwards_natively_for_native_both(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(
            cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | self._F_SET_TILT
        )
        self._prep(cover)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(50)

        await cover.set_position(60)

        services = [c.args[1] for c in _calls(cover.hass.services.async_call)]
        assert "set_cover_position" in services
        assert "close_cover" not in services and "open_cover" not in services


class TestNativeTiltSweep:
    """During a position travel, a native cover's tilt display sweeps to the
    direction endpoint (0 closing, 100 opening); no physical tilt command."""

    _F_SET_TILT = 128

    def _prep(self, cover):
        cover.start_auto_updater = MagicMock()
        cover.async_write_ha_state = MagicMock()
        cover.async_schedule_update_ha_state = MagicMock()

    def _native_cover(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(
            cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | self._F_SET_TILT
        )
        self._prep(cover)
        return cover

    @pytest.mark.asyncio
    async def test_plan_returns_zero_endpoint_when_closing(self):
        cover = self._native_cover()
        tilt_target, pre_step_delay, started = await cover._plan_tilt_for_travel(
            30, "close", current_pos=100, current_tilt=80
        )
        assert (tilt_target, pre_step_delay, started) == (0, 0.0, False)
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_plan_returns_100_endpoint_when_opening(self):
        cover = self._native_cover()
        tilt_target, _, started = await cover._plan_tilt_for_travel(
            90, "open", current_pos=20, current_tilt=10
        )
        assert tilt_target == 100
        assert started is False

    @pytest.mark.asyncio
    async def test_plan_returns_none_when_position_unknown(self):
        cover = self._native_cover()
        result = await cover._plan_tilt_for_travel(
            50, "open", current_pos=None, current_tilt=40
        )
        assert result == (None, 0.0, False)

    @pytest.mark.asyncio
    async def test_position_move_sweeps_tilt_display_no_tilt_command(self):
        cover = self._native_cover()
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(80)

        await cover.set_position(30)  # closing

        # Tilt display is animating toward the closed endpoint (0)...
        assert cover.tilt_calc.is_traveling()
        assert cover.tilt_calc._travel_to_position == 0
        # ...and no physical tilt command was sent (device owns its slats).
        services = [c.args[1] for c in _calls(cover.hass.services.async_call)]
        assert "set_cover_tilt_position" not in services
        assert "close_cover_tilt" not in services
        assert "open_cover_tilt" not in services
