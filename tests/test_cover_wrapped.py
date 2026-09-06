"""Tests for WrappedCoverTimeBased._send_open/close/stop.

Each test verifies that the correct cover.* service call is made.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.components.cover import ATTR_CURRENT_POSITION
from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    STATE_CLOSED,
    STATE_UNAVAILABLE,
)

from custom_components.cover_time_based.cover_wrapped import WrappedCoverTimeBased

# CoverEntityFeature bit values (OPEN=1, CLOSE=2, SET_POSITION=4, STOP=8,
# SET_TILT_POSITION=128).
_F_OPEN = 1
_F_CLOSE = 2
_F_SET_POSITION = 4
_F_STOP = 8
_F_SET_TILT = 128


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _make_wrapped_cover(
    cover_entity_id="cover.inner",
    force_time_based_position=False,
    reports_command_not_endpoint=False,
    ignore_endpoint_states=False,
    ignore_all_reports=False,
    invert=False,
    tilt_time_close=None,
    tilt_time_open=None,
    tilt_mode="none",
    travel_startup_delay=None,
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
        travel_startup_delay=travel_startup_delay,
        tilt_startup_delay=None,
        endpoint_runon_time=None,
        min_movement_time=None,
        cover_entity_id=cover_entity_id,
        force_time_based_position=force_time_based_position,
        reports_command_not_endpoint=reports_command_not_endpoint,
        ignore_endpoint_states=ignore_endpoint_states,
        ignore_all_reports=ignore_all_reports,
        invert=invert,
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


def _stub_updates(cover):
    """Keep mock HA from scheduling an auto-updater or publishing state."""
    cover.start_auto_updater = MagicMock()
    cover.async_write_ha_state = MagicMock()
    cover.async_schedule_update_ha_state = MagicMock()


def _services(cover):
    """Return the service names called on hass.services.async_call, in order."""
    return [c.args[1] for c in _calls(cover.hass.services.async_call)]


def _attr_event(entity_id, state):
    """An attribute-change event carrying `state` as the entity's new state."""
    event = MagicMock()
    event.data = {"entity_id": entity_id, "new_state": state}
    return event


def _state_event(entity_id, old_val, new_val, *, position=None):
    """A state-change event as HA fires it, with fake old/new State objects."""
    old_s = MagicMock()
    old_s.state = old_val
    old_s.attributes = {}
    new_s = MagicMock()
    new_s.state = new_val
    new_s.attributes = {} if position is None else {ATTR_CURRENT_POSITION: position}
    event = MagicMock()
    event.data = {"entity_id": entity_id, "old_state": old_s, "new_state": new_s}
    return event


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
        _stub_updates(cover)
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

    @pytest.mark.asyncio
    async def test_forwards_set_cover_position_directly(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)  # OPEN|CLOSE|SET_POSITION, no STOP
        _stub_updates(cover)
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
        _stub_updates(cover)
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
        _stub_updates(cover)
        cover.travel_calc.set_position(100)

        await cover.set_position(60)

        services = _services(cover)
        assert "set_cover_position" not in services
        assert "close_cover" in services

    @pytest.mark.asyncio
    async def test_no_native_support_uses_legacy_path(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP)
        _stub_updates(cover)
        cover.travel_calc.set_position(100)

        await cover.set_position(60)

        services = _services(cover)
        assert "set_cover_position" not in services
        assert "close_cover" in services


class TestInvertOutboundSetPosition:
    """Inverted covers forward set_cover_position(100 - p) to the underlying."""

    @pytest.mark.asyncio
    async def test_native_set_position_is_inverted(self):
        cover = _make_wrapped_cover(invert=True)
        _set_wrapped_features(cover, 7)  # OPEN|CLOSE|SET_POSITION
        _stub_updates(cover)
        cover.travel_calc.set_position(100)

        await cover.set_position(30)  # user target 30

        assert _calls(cover.hass.services.async_call) == [
            call(
                "cover",
                "set_cover_position",
                {"entity_id": "cover.inner", "position": 70},
                False,
            ),
        ]
        # Internal tracker stays in user frame.
        assert cover.travel_calc._travel_to_position == 30

    @pytest.mark.asyncio
    async def test_stop_freeze_is_inverted(self):
        cover = _make_wrapped_cover(invert=True)
        _set_wrapped_features(
            cover, 7
        )  # SET_POSITION, no STOP → freeze via set_position
        cover.travel_calc.set_position(43)  # user frame

        await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == [
            call(
                "cover",
                "set_cover_position",
                {"entity_id": "cover.inner", "position": 57},
                False,
            ),
        ]

    @pytest.mark.asyncio
    async def test_native_set_position_unchanged_when_invert_off(self):
        cover = _make_wrapped_cover(invert=False)
        _set_wrapped_features(cover, 7)
        _stub_updates(cover)
        cover.travel_calc.set_position(100)

        await cover.set_position(30)

        assert _calls(cover.hass.services.async_call) == [
            call(
                "cover",
                "set_cover_position",
                {"entity_id": "cover.inner", "position": 30},
                False,
            ),
        ]


class TestInvertOutboundOpenClose:
    """Inverted user-open drives the underlying close_cover, and vice versa."""

    @pytest.mark.asyncio
    async def test_send_open_drives_underlying_close(self):
        cover = _make_wrapped_cover(invert=True)
        await cover._send_open()
        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("close_cover", "cover.inner"),
        ]

    @pytest.mark.asyncio
    async def test_send_close_drives_underlying_open(self):
        cover = _make_wrapped_cover(invert=True)
        await cover._send_close()
        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("open_cover", "cover.inner"),
        ]

    @pytest.mark.asyncio
    async def test_send_open_unchanged_when_invert_off(self):
        cover = _make_wrapped_cover(invert=False)
        await cover._send_open()
        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("open_cover", "cover.inner"),
        ]


class TestInvertInboundReportedPosition:
    """Inverted covers report 100 - underlying position; closed → 100."""

    def test_reported_attr_position_is_inverted(self):
        cover = _make_wrapped_cover(invert=True)
        _set_wrapped_features(cover, 7, state="open", current_position=70)
        assert cover._wrapped_reported_position() == 30

    def test_reported_closed_maps_to_100(self):
        cover = _make_wrapped_cover(invert=True)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE, state="closed")
        assert cover._wrapped_reported_position() == 100

    def test_reported_attr_unchanged_when_invert_off(self):
        cover = _make_wrapped_cover(invert=False)
        _set_wrapped_features(cover, 7, state="open", current_position=70)
        assert cover._wrapped_reported_position() == 70

    def test_reported_closed_maps_to_0_when_invert_off(self):
        cover = _make_wrapped_cover(invert=False)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE, state="closed")
        assert cover._wrapped_reported_position() == 0


class TestInvertInboundStateChange:
    """Inverted: underlying opening → we close; underlying closing → we open."""

    @pytest.mark.asyncio
    async def test_underlying_opening_drives_our_close(self):
        cover = _make_wrapped_cover(invert=True)
        cover.travel_calc.set_position(50)  # idle
        cover._last_self_command_time = None
        with (
            patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock,
            patch.object(cover, "async_close_cover", new=AsyncMock()) as close_mock,
        ):
            await cover._handle_external_state_change(
                "cover.inner", "closed", "opening"
            )
        close_mock.assert_awaited_once()
        open_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_underlying_closing_drives_our_open(self):
        cover = _make_wrapped_cover(invert=True)
        cover.travel_calc.set_position(50)
        cover._last_self_command_time = None
        with (
            patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock,
            patch.object(cover, "async_close_cover", new=AsyncMock()) as close_mock,
        ):
            await cover._handle_external_state_change("cover.inner", "open", "closing")
        open_mock.assert_awaited_once()
        close_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_opening_drives_our_open_when_invert_off(self):
        cover = _make_wrapped_cover(invert=False)
        cover.travel_calc.set_position(50)
        cover._last_self_command_time = None
        with patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock:
            await cover._handle_external_state_change(
                "cover.inner", "closed", "opening"
            )
        open_mock.assert_awaited_once()


class TestInvertCommandEcho:
    """Inverted command-echo: open-echo → our close; close-echo → our open."""

    @pytest.mark.asyncio
    async def test_open_echo_drives_our_close(self):
        cover = _make_wrapped_cover(invert=True, reports_command_not_endpoint=True)
        with (
            patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock,
            patch.object(cover, "async_close_cover", new=AsyncMock()) as close_mock,
        ):
            await cover._handle_external_state_change("cover.inner", "unknown", "open")
        close_mock.assert_awaited_once()
        open_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_closed_echo_drives_our_open(self):
        cover = _make_wrapped_cover(invert=True, reports_command_not_endpoint=True)
        with (
            patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock,
            patch.object(cover, "async_close_cover", new=AsyncMock()) as close_mock,
        ):
            await cover._handle_external_state_change("cover.inner", "open", "closed")
        open_mock.assert_awaited_once()
        close_mock.assert_not_awaited()


class TestIgnoreAllReports:
    """ignore_all_reports (issue #248): the underlying is a dumb relay — its
    every state/position/transition report is ignored and position is tracked
    purely by time. Reproduces the DiO ZB-ERSM-01 ghost paths from the log."""

    @pytest.mark.asyncio
    async def test_closed_with_position_attr_does_not_snap(self):
        # The exact debug-log event: idle at 100%, the device reports
        # opening -> closed carrying current_position=0. No real endpoints
        # snaps here (trusts the attr); ignore_all_reports must not.
        cover = _make_wrapped_cover(ignore_all_reports=True)
        cover.travel_calc.set_position(100)
        cover._last_self_command_time = None
        _set_wrapped_features(cover, 0, state="closed", current_position=0)
        with (
            patch.object(cover, "set_known_position", new=AsyncMock()) as snap,
            patch.object(cover, "async_stop_cover", new=AsyncMock()) as stop,
        ):
            await cover._handle_external_state_change(
                "cover.inner", "opening", "closed"
            )
        snap.assert_not_awaited()
        stop.assert_not_awaited()
        assert cover.travel_calc.current_position() == 100

    @pytest.mark.asyncio
    async def test_spurious_opening_does_not_start_travel(self):
        cover = _make_wrapped_cover(ignore_all_reports=True)
        cover.travel_calc.set_position(0)
        cover._last_self_command_time = None
        with (
            patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock,
            patch.object(cover, "async_close_cover", new=AsyncMock()) as close_mock,
        ):
            await cover._handle_external_state_change(
                "cover.inner", "closed", "opening"
            )
        open_mock.assert_not_awaited()
        close_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_spurious_closing_does_not_start_travel(self):
        cover = _make_wrapped_cover(ignore_all_reports=True)
        cover.travel_calc.set_position(100)
        cover._last_self_command_time = None
        with (
            patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock,
            patch.object(cover, "async_close_cover", new=AsyncMock()) as close_mock,
        ):
            await cover._handle_external_state_change("cover.inner", "open", "closing")
        open_mock.assert_not_awaited()
        close_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_attribute_only_position_report_is_ignored(self):
        # A bare current_position attribute update (state unchanged) must not
        # snap either — the other channel the device desyncs through.
        cover = _make_wrapped_cover(ignore_all_reports=True)
        cover.travel_calc.set_position(100)
        cover._last_self_command_time = None
        st = _set_wrapped_features(cover, 0, state="closed", current_position=0)
        event = MagicMock()
        event.data = {"entity_id": "cover.inner", "new_state": st}
        with patch.object(cover, "set_known_position", new=AsyncMock()) as snap:
            await cover._handle_external_attribute_change(event)
        snap.assert_not_awaited()
        assert cover.travel_calc.current_position() == 100

    @pytest.mark.asyncio
    async def test_commands_still_forward_to_the_underlying(self):
        # Ignoring the device's reports must not stop us driving it.
        cover = _make_wrapped_cover(ignore_all_reports=True)
        await cover._send_close()
        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("close_cover", "cover.inner"),
        ]

    def test_reported_position_is_none_even_with_attribute(self):
        # Source of truth for the startup live-sync and every other consumer:
        # a device we never trust reports no usable position.
        cover = _make_wrapped_cover(ignore_all_reports=True)
        _set_wrapped_features(cover, 0, state="closed", current_position=0)
        assert cover._wrapped_reported_position() is None

    @pytest.mark.asyncio
    async def test_unknown_is_still_stop_when_inverted(self):
        cover = _make_wrapped_cover(invert=True, reports_command_not_endpoint=True)
        with patch.object(cover, "async_stop_cover", new=AsyncMock()) as stop_mock:
            await cover._handle_external_state_change(
                "cover.inner", "closed", "unknown"
            )
        stop_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_open_echo_drives_our_open_when_invert_off(self):
        cover = _make_wrapped_cover(invert=False, reports_command_not_endpoint=True)
        with patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock:
            await cover._handle_external_state_change("cover.inner", "unknown", "open")
        open_mock.assert_awaited_once()


class TestIgnoreAllReportsTimedPath:
    """ignore_all_reports keeps both axes on the timed path even when the
    underlying advertises SET_POSITION / SET_TILT_POSITION.

    A native target is expressed in the device's own position scale — the very
    scale this profile declares untrustworthy — and with both report channels
    ignored no settle-snap is left to reconcile the result.
    """

    def test_use_native_set_position_is_disabled(self):
        cover = _make_wrapped_cover(ignore_all_reports=True)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_STOP)
        assert cover._use_native_set_position() is False

    def test_position_driver_is_timed(self):
        from custom_components.cover_time_based.drivers import TimedPositionDriver

        cover = _make_wrapped_cover(ignore_all_reports=True)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_STOP)
        assert isinstance(cover._position_driver(), TimedPositionDriver)

    def test_motor_does_not_stop_itself(self):
        # stops_itself=True would mean the auto-updater sends no stop: the
        # tracker parks at the target and the relay is never told anything.
        cover = _make_wrapped_cover(ignore_all_reports=True)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_STOP)
        assert cover._motor_stops_itself() is False

    @pytest.mark.asyncio
    async def test_set_position_uses_timed_open_not_native_forward(self):
        cover = _make_wrapped_cover(ignore_all_reports=True)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_STOP)
        _stub_updates(cover)
        cover.travel_calc.set_position(0)

        await cover.async_set_cover_position(position=50)

        services = _services(cover)
        assert "set_cover_position" not in services, services
        assert "open_cover" in services

    @pytest.mark.asyncio
    async def test_force_time_based_control_takes_the_timed_path(self):
        # Control: the sibling option on the identical underlying.
        cover = _make_wrapped_cover(force_time_based_position=True)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_STOP)
        _stub_updates(cover)
        cover.travel_calc.set_position(0)

        await cover.async_set_cover_position(position=50)

        services = _services(cover)
        assert "set_cover_position" not in services
        assert "open_cover" in services

    @pytest.mark.asyncio
    async def test_we_stop_the_move_ourselves_and_reports_never_correct_it(self):
        # End to end: the move is a timed open that we stop when our own
        # tracker arrives, and whatever the device reports along the way
        # changes nothing.
        cover = _make_wrapped_cover(ignore_all_reports=True)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_STOP)
        _stub_updates(cover)
        cover.travel_calc.set_position(0)

        await cover.async_set_cover_position(position=50)

        assert _calls(cover.hass.services.async_call) == [
            _cover_svc("open_cover", "cover.inner"),
        ]
        assert cover._motor_stops_itself() is False

        # The device reports settling somewhere else entirely (its position
        # scale is the lie this profile exists for). Both channels drop it.
        st = _set_wrapped_features(
            cover,
            _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_STOP,
            state="open",
            current_position=17,
        )
        cover._last_self_command_time = None
        with patch.object(cover, "set_known_position", new=AsyncMock()) as snap:
            await cover._handle_external_state_change("cover.inner", "opening", "open")
            await cover._handle_external_attribute_change(
                _attr_event("cover.inner", st)
            )
        snap.assert_not_awaited()
        assert cover.travel_calc._travel_to_position == 50
        assert cover._wrapped_reported_position() is None

        # Our own timer arriving is what halts the motor.
        cover.travel_calc.set_position(50)
        await cover.auto_stop_if_necessary()
        assert _services(cover) == ["open_cover", "stop_cover"]

    def test_use_native_tilt_is_disabled(self):
        cover = _make_wrapped_cover(
            ignore_all_reports=True,
            tilt_time_close=5,
            tilt_time_open=5,
            tilt_mode="inline",
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_TILT)
        assert cover._use_native_tilt() is False

    @pytest.mark.asyncio
    async def test_set_tilt_position_uses_timed_path(self):
        cover = _make_wrapped_cover(
            ignore_all_reports=True,
            tilt_time_close=5,
            tilt_time_open=5,
            tilt_mode="inline",
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_TILT)
        _stub_updates(cover)
        cover.tilt_calc.set_position(0)

        await cover.async_set_cover_tilt_position(tilt_position=50)

        assert _services(cover) == ["open_cover"]

    def test_reported_tilt_is_not_trusted(self):
        cover = _make_wrapped_cover(
            ignore_all_reports=True,
            tilt_time_close=5,
            tilt_time_open=5,
            tilt_mode="inline",
        )
        st = _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_TILT)
        st.attributes["current_tilt_position"] = 30
        assert cover._wrapped_reported_tilt_position() is None

    @pytest.mark.asyncio
    async def test_tilt_snap_never_runs_under_ignore_all(self):
        # _maybe_snap_to_reported_tilt is only reachable from the two report
        # handlers, and both early-return on ignore_all_reports.
        cover = _make_wrapped_cover(
            ignore_all_reports=True,
            tilt_time_close=5,
            tilt_time_open=5,
            tilt_mode="inline",
        )
        st = _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_TILT)
        st.attributes["current_tilt_position"] = 30
        cover.tilt_calc.set_position(80)
        cover._last_self_command_time = None
        with patch.object(
            cover, "_maybe_snap_to_reported_tilt", new=AsyncMock()
        ) as snap:
            await cover._handle_external_state_change("cover.inner", "opening", "open")
            await cover._handle_external_attribute_change(
                _attr_event("cover.inner", st)
            )
        snap.assert_not_awaited()
        assert cover.tilt_calc.current_position() == 80

    @pytest.mark.asyncio
    async def test_freeze_reissues_tracked_position_natively(self):
        # With STOP unsupported, re-issuing our tracked position is the only
        # halt command that exists — untrusted scale and all.
        cover = _make_wrapped_cover(ignore_all_reports=True)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION)  # no STOP
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
    async def test_native_stop_is_used_when_supported(self):
        cover = _make_wrapped_cover(ignore_all_reports=True)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_STOP)

        await cover._send_stop()

        assert _services(cover) == ["stop_cover"]


class TestInvertEndToEndOpenClose:
    """End-to-end: driving the public async_open_cover/async_close_cover
    entry points on an inverted cover (no native features, so the timed
    path is used) drives the underlying's opposite command, while the
    internal tracker still travels toward the user-frame target.
    """

    def _prep(self, cover):
        _stub_updates(cover)
        # No native SET_POSITION -> open/close use the timed _send_open/
        # _send_close path (see TestInvertOutboundOpenClose), while the
        # target stays "available" so movement isn't rejected.
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP)

    @pytest.mark.asyncio
    async def test_open_cover_drives_underlying_close_and_travels_to_user_open(self):
        cover = _make_wrapped_cover(invert=True)
        self._prep(cover)
        cover.travel_calc.set_position(0)  # user-frame closed

        await cover.async_open_cover()

        assert _cover_svc("close_cover", "cover.inner") in _calls(
            cover.hass.services.async_call
        )
        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._travel_to_position == 100

    @pytest.mark.asyncio
    async def test_close_cover_drives_underlying_open_and_travels_to_user_close(self):
        cover = _make_wrapped_cover(invert=True)
        self._prep(cover)
        cover.travel_calc.set_position(100)  # user-frame open

        await cover.async_close_cover()

        assert _cover_svc("open_cover", "cover.inner") in _calls(
            cover.hass.services.async_call
        )
        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._travel_to_position == 0


class TestWrappedNativeMoveNoHijack:
    """While the tracker animates a native set_position move, the wrapped
    cover's own opening/closing state (a side effect of our forwarded
    command) must not hijack the move into a full open/close. Once the
    tracker is idle, a genuine external opening/closing is honored again.
    """

    @pytest.mark.asyncio
    async def test_opening_during_native_move_is_not_hijacked(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)
        _stub_updates(cover)
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
        _stub_updates(cover)
        cover.travel_calc.set_position(0)  # idle, not travelling
        cover._last_self_command_time = None

        with patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock:
            await cover._handle_external_state_change(
                "cover.inner", "closed", "opening"
            )

        open_mock.assert_awaited_once()


class TestWrappedTimedMoveNoHijack:
    """A time-based wrapped cover (Force time-based, or no native
    set_position) forwards open_cover/close_cover to reach a partial target,
    then the wrapped cover reports its own opening/closing as a side effect of
    that command. When that report lands after the bounce grace window -- e.g.
    a template cover driven by a physical binary sensor that lags the relay by
    >0.5s (issue #165) -- it must not be reinterpreted as a fresh full
    open/close that hijacks the in-flight partial move.

    Only the SAME-direction echo of our own move is suppressed. An
    opposite-direction report is a genuine external reversal (e.g. the wall
    switch pressed the other way) and is still honored. When the tracker is
    idle it is honored too (an external press).
    """

    @pytest.mark.asyncio
    async def test_opening_during_timed_partial_move_is_not_hijacked(self):
        cover = _make_wrapped_cover(force_time_based_position=True)
        _set_wrapped_features(cover, 15, state="closed")
        _stub_updates(cover)
        cover.travel_calc.set_position(0)
        await cover.set_position(4)  # timed; tracker now travelling up to 4%
        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._travel_to_position == 4

        # The up binary sensor flips ~1.5s later, past the bounce grace window.
        cover._last_self_command_time = None
        with patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock:
            await cover._handle_external_state_change("cover.inner", "open", "opening")

        open_mock.assert_not_awaited()
        assert cover.travel_calc._travel_to_position == 4

    @pytest.mark.asyncio
    async def test_closing_reversal_during_timed_move_is_honored(self):
        cover = _make_wrapped_cover(force_time_based_position=True)
        _set_wrapped_features(cover, 15, state="closed")
        _stub_updates(cover)
        cover.travel_calc.set_position(0)
        await cover.set_position(60)  # timed; travelling up
        assert cover.travel_calc.is_opening()

        cover._last_self_command_time = None
        # Opposite direction: the wall switch was pressed down mid-move.
        with patch.object(cover, "async_close_cover", new=AsyncMock()) as close_mock:
            await cover._handle_external_state_change(
                "cover.inner", "opening", "closing"
            )

        close_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_closing_during_timed_partial_move_is_not_hijacked(self):
        # Same-direction echo on a downward move (the mirror of test 1):
        # forwarding close_cover to reach a partial target makes the underlying
        # report "closing"; that echo must not hijack the move to 0%.
        cover = _make_wrapped_cover(force_time_based_position=True)
        _set_wrapped_features(cover, 15, state="open")
        _stub_updates(cover)
        cover.travel_calc.set_position(100)
        await cover.set_position(96)  # timed; tracker now travelling down to 96%
        assert cover.travel_calc.is_closing()
        assert cover.travel_calc._travel_to_position == 96

        cover._last_self_command_time = None
        with patch.object(cover, "async_close_cover", new=AsyncMock()) as close_mock:
            await cover._handle_external_state_change("cover.inner", "open", "closing")

        close_mock.assert_not_awaited()
        assert cover.travel_calc._travel_to_position == 96

    @pytest.mark.asyncio
    async def test_opening_when_idle_timed_is_honored(self):
        cover = _make_wrapped_cover(force_time_based_position=True)
        _set_wrapped_features(cover, 15, state="closed")
        _stub_updates(cover)
        cover.travel_calc.set_position(0)  # idle, not travelling
        cover._last_self_command_time = None

        with patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock:
            await cover._handle_external_state_change(
                "cover.inner", "closed", "opening"
            )

        open_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_inverted_echo_during_timed_partial_move_is_not_hijacked(self):
        # Inverted: our up-move forwards close_cover to the underlying, which
        # then reports "closing" -- our-frame open. That same-direction echo
        # must be suppressed, not drive us to the open endpoint.
        cover = _make_wrapped_cover(force_time_based_position=True, invert=True)
        _set_wrapped_features(cover, 15, state="open")
        _stub_updates(cover)
        cover.travel_calc.set_position(0)
        await cover.set_position(4)  # our-frame up; underlying driven closed
        assert cover.travel_calc.is_opening()

        cover._last_self_command_time = None
        with patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock:
            await cover._handle_external_state_change("cover.inner", "open", "closing")

        open_mock.assert_not_awaited()
        assert cover.travel_calc._travel_to_position == 4


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

    @pytest.mark.asyncio
    async def test_min_movement_time_suppresses_tiny_native_move(self):
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7)
        _stub_updates(cover)
        cover._min_movement_time = 2.0
        cover.travel_calc.set_position(100)

        await cover.set_position(99)  # 1% * 30s = 0.3s < 2s → suppressed

        services = _services(cover)
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

        services = _services(cover)
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
        _stub_updates(cover)
        cover.travel_calc.set_position(100)
        await cover.set_position(60)  # one set_cover_position so far
        # Tracker arrives at target; auto-stop must not re-command the device.
        cover.travel_calc.set_position(60)
        await cover.auto_stop_if_necessary()

        services = _services(cover)
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


class TestWrappedIgnoreEndpointStates:
    """ignore_endpoint_states: a wrapped cover with no position feedback that
    reports open/closed when the motor merely stops mid-travel (not only at the
    physical endpoints). With the flag on, a reported `closed` is no longer
    trusted as the 0% endpoint — the tracker stops where it is instead of
    snapping to 0. Unlike command-echo mode, opening/closing are still honored
    as real movement. Issue #238.
    """

    @pytest.mark.asyncio
    async def test_default_flag_is_false(self):
        cover = _make_wrapped_cover()
        assert cover._ignore_endpoint_states is False

    def test_closed_reported_position_is_none_when_flag_on(self):
        cover = _make_wrapped_cover(ignore_endpoint_states=True)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP, state="closed")
        assert cover._wrapped_reported_position() is None

    def test_closed_reported_position_is_none_when_flag_on_inverted(self):
        # Inverted, the closed fallback would be 100; the flag must drop it too.
        cover = _make_wrapped_cover(ignore_endpoint_states=True, invert=True)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP, state="closed")
        assert cover._wrapped_reported_position() is None

    def test_closed_still_maps_to_zero_when_flag_off(self):
        # Regression: the default still trusts closed as the 0% endpoint.
        cover = _make_wrapped_cover(ignore_endpoint_states=False)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP, state="closed")
        assert cover._wrapped_reported_position() == 0

    @pytest.mark.asyncio
    async def test_external_closing_to_closed_stops_at_tracked_position(self):
        # The headline #238 case: a wall-switch close that stops mid-travel
        # reports closing -> closed. With the flag on we stop the tracker where
        # it is, never snapping to 0.
        cover = _make_wrapped_cover(ignore_endpoint_states=True)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP, state="closed")
        with (
            patch.object(cover, "async_stop_cover", new=AsyncMock()) as stop_mock,
            patch.object(cover, "_snap_to_position", new=AsyncMock()) as snap_mock,
        ):
            await cover._handle_external_state_change(
                "cover.inner", "closing", "closed"
            )
        stop_mock.assert_awaited_once()
        snap_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_external_closing_to_closed_snaps_to_zero_when_flag_off(self):
        # Regression: with the flag off, closing -> closed still snaps to 0.
        cover = _make_wrapped_cover(ignore_endpoint_states=False)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_STOP, state="closed")
        with patch.object(cover, "_snap_to_position", new=AsyncMock()) as snap_mock:
            await cover._handle_external_state_change(
                "cover.inner", "closing", "closed"
            )
        snap_mock.assert_awaited_once_with(0)

    def test_option_flows_through_cover_factory(self, make_cover):
        # The real options -> cover.py -> constructor path wires the flag.
        cover = make_cover(cover_entity_id="cover.inner", ignore_endpoint_states=True)
        assert cover._ignore_endpoint_states is True

    def test_option_defaults_false_through_cover_factory(self, make_cover):
        cover = make_cover(cover_entity_id="cover.inner")
        assert cover._ignore_endpoint_states is False


class TestUseNativeTilt:
    """_use_native_tilt() requires InlineTilt + wrapped SET_TILT_POSITION,
    and is off for command-echo covers and non-inline strategies."""

    def test_native_tilt_when_inline_and_set_tilt_supported(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_TILT)
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
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_TILT)
        assert cover._use_native_tilt() is False

    def test_not_native_for_command_echo(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5,
            tilt_time_open=5,
            tilt_mode="inline",
            reports_command_not_endpoint=True,
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_TILT)
        assert cover._use_native_tilt() is False

    def test_not_native_without_tilt_configured(self):
        cover = _make_wrapped_cover()  # no tilt times → no tilt strategy
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_TILT)
        assert cover._use_native_tilt() is False


class TestNativeTiltForwarding:
    """Native tilt covers forward set_cover_tilt_position and animate tilt_calc,
    and the auto-updater issues no relay stop when the tilt move completes."""

    def _native_tilt_cover(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_TILT)
        _stub_updates(cover)
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

        services = _services(cover)
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

        services = _services(cover)
        assert "stop_cover" not in services
        assert "close_cover" not in services


class TestTiltSettleSnap:
    """On settle, a native-tilt cover snaps tilt_calc to the device's reported
    current_tilt_position; non-native strategies do not."""

    @pytest.mark.asyncio
    async def test_snaps_tilt_to_reported_on_settle(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        st = _set_wrapped_features(
            cover, _F_OPEN | _F_CLOSE | _F_SET_TILT, state="open"
        )
        st.attributes["current_position"] = 100
        st.attributes["current_tilt_position"] = 45
        _stub_updates(cover)
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
            cover, _F_OPEN | _F_CLOSE | _F_SET_TILT, state="open"
        )
        st.attributes["current_position"] = 100
        st.attributes["current_tilt_position"] = 45
        _stub_updates(cover)
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
            cover, _F_OPEN | _F_CLOSE | _F_SET_TILT, state="open"
        )
        st.attributes["current_position"] = 100
        st.attributes["current_tilt_position"] = 0
        _stub_updates(cover)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(50)

        await cover._handle_external_state_change("cover.inner", "opening", "open")

        assert cover.tilt_calc.current_position() == 0


class TestNativeCouplingNeutralized:
    """A position move on a native-tilt cover schedules no main-motor tilt
    restore — the device manages its own slats."""

    @pytest.mark.asyncio
    async def test_no_tilt_restore_scheduled_for_native(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_TILT)
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

    @pytest.mark.asyncio
    async def test_move_to_rejects_unavailable_target(self):
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.cover_time_based.drivers import NativeTiltDriver

        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(
            cover, _F_OPEN | _F_CLOSE | _F_SET_TILT, state="unavailable"
        )
        cover.tilt_calc.set_position(80)
        cover._triggered_externally = False

        with pytest.raises(HomeAssistantError):
            await NativeTiltDriver(cover).move_to(30)


class TestNativePositionWithNativeTilt:
    """A native-both-inline cover drives position natively too (symmetry);
    timed-tilt strategies keep the timed position path."""

    def test_native_position_enabled_for_native_both_inline(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_SET_TILT)
        assert cover._use_native_set_position() is True

    def test_timed_position_kept_for_sequential_even_with_set_position(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="sequential_close"
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_SET_TILT)
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
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_SET_TILT)
        _stub_updates(cover)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(50)

        await cover.set_position(60)

        services = _services(cover)
        assert "set_cover_position" in services
        assert "close_cover" not in services and "open_cover" not in services


class TestNativeTiltSweep:
    """During a position travel, a native cover's tilt display sweeps to the
    direction endpoint (0 closing, 100 opening); no physical tilt command."""

    def _native_cover(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_SET_TILT)
        _stub_updates(cover)
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
        services = _services(cover)
        assert "set_cover_tilt_position" not in services
        assert "close_cover_tilt" not in services
        assert "open_cover_tilt" not in services

    @pytest.mark.asyncio
    async def test_native_both_position_move_settles_both_axes(self):
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        st = _set_wrapped_features(
            cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_SET_TILT
        )
        _stub_updates(cover)
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(80)

        await cover.set_position(30)  # native position forward; tilt sweeps toward 0

        # Device settles and reports its real position + slat angle.
        cover._last_self_command_time = None  # bypass the bounce grace window
        st.state = "open"
        st.attributes["current_position"] = 30
        st.attributes["current_tilt_position"] = 25

        await cover._handle_external_state_change("cover.inner", "closing", "open")

        assert cover.travel_calc.current_position() == 30
        assert cover.tilt_calc.current_position() == 25


# ===================================================================
# Invert option
# ===================================================================


class TestInvertOption:
    """The invert option: constructor field, default, and the involution helper."""

    def test_default_invert_is_false(self):
        cover = _make_wrapped_cover()
        assert cover._invert is False

    def test_invert_stored_when_true(self):
        cover = _make_wrapped_cover(invert=True)
        assert cover._invert is True

    def test_invert_position_is_noop_when_off(self):
        cover = _make_wrapped_cover(invert=False)
        assert cover._invert_position(0) == 0
        assert cover._invert_position(30) == 30
        assert cover._invert_position(100) == 100

    def test_invert_position_flips_when_on(self):
        cover = _make_wrapped_cover(invert=True)
        assert cover._invert_position(0) == 100
        assert cover._invert_position(30) == 70
        assert cover._invert_position(100) == 0


class TestWrappedStaleReappearance:
    """A wrapped entity coming back from unavailable/unknown is re-announcing
    itself, not reporting an endpoint. Issue #160 follow-up: an inverted awning
    whose no-feedback entity dropped out and returned reporting 'closed' was
    snapped to _invert_position(0) == 100, flipping a closed cover to open in
    the same second. Only a reported current_position is trusted on the way
    back; the closed-state fallback is not.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("old_val", [STATE_UNAVAILABLE, "unknown"])
    @pytest.mark.parametrize("invert", [True, False])
    async def test_reappearing_closed_does_not_snap(self, old_val, invert):
        cover = _make_wrapped_cover(invert=invert)
        _set_wrapped_features(cover, _F_OPEN | _F_CLOSE, state="closed")
        with patch.object(cover, "_snap_to_position", new=AsyncMock()) as snap_mock:
            await cover._handle_external_state_change("cover.inner", old_val, "closed")
        snap_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reappearing_with_position_attribute_still_snaps(self):
        # A device that reports where it actually is is trusted on the way back.
        cover = _make_wrapped_cover()
        _set_wrapped_features(cover, 7, state="open", current_position=70)
        with patch.object(cover, "_snap_to_position", new=AsyncMock()) as snap_mock:
            await cover._handle_external_state_change(
                "cover.inner", STATE_UNAVAILABLE, "open"
            )
        snap_mock.assert_awaited_once_with(70)

    @pytest.mark.asyncio
    async def test_reappearing_moving_still_starts_movement(self):
        # opening/closing on the way back is a real report, not a stale endpoint.
        cover = _make_wrapped_cover()
        cover.travel_calc.set_position(50)
        cover._last_self_command_time = None
        with patch.object(cover, "async_open_cover", new=AsyncMock()) as open_mock:
            await cover._handle_external_state_change(
                "cover.inner", STATE_UNAVAILABLE, "opening"
            )
        open_mock.assert_awaited_once()

    def test_command_echo_retained_travel_state_is_vetoed(self):
        # The dispatcher's stale-reappearance hook takes the command-echo half:
        # a retained open/closed resurfacing must not be replayed as a command.
        cover = _make_wrapped_cover(reports_command_not_endpoint=True)
        assert cover._is_stale_reappearance(STATE_UNAVAILABLE, "closed") is True
        assert cover._is_stale_reappearance(STATE_UNAVAILABLE, "opening") is True

    def test_command_echo_stop_on_reconnect_is_still_honoured(self):
        # `unknown` is this mode's stop command, and freezing the tracker on
        # reconnect is the behaviour we want to keep.
        cover = _make_wrapped_cover(reports_command_not_endpoint=True)
        assert cover._is_stale_reappearance(STATE_UNAVAILABLE, "unknown") is False

    def test_command_echo_two_step_reconnect_is_vetoed_throughout(self):
        # unavailable -> unknown -> <retained value> is one reconnect, not a
        # stop followed by a command: the veto has to survive the stop hop.
        cover = _make_wrapped_cover(reports_command_not_endpoint=True)
        assert cover._is_stale_reappearance(STATE_UNAVAILABLE, "unknown") is False
        assert cover._is_stale_reappearance("unknown", "closed") is True

    def test_command_echo_ordinary_stop_then_close_is_a_real_command(self):
        # The same unknown -> closed pair, with no dropout before it, is a
        # genuine stop-then-close and must still be obeyed.
        cover = _make_wrapped_cover(reports_command_not_endpoint=True)
        assert cover._is_stale_reappearance("open", "unknown") is False
        assert cover._is_stale_reappearance("unknown", "closed") is False

    def test_endpoint_covers_are_not_vetoed_by_the_hook(self):
        # They are guarded in the handler instead, so the transition must still
        # reach it — a returning entity may carry a trustworthy position.
        cover = _make_wrapped_cover()
        assert cover._is_stale_reappearance(STATE_UNAVAILABLE, "closed") is False


class TestStartupDelayEchoDoesNotHijackTimedMove:
    """A lagged same-direction echo landing during the travel_startup_delay
    window (travel_calc not yet traveling) must not hijack a self-initiated
    timed move.

    The #166 echo guard only matched while travel_calc.is_traveling(), so an
    echo arriving in the startup-delay window slipped through to
    async_open_cover -> _async_move_to_endpoint, whose flag assignment flipped
    _self_initiated_movement to False. The in-flight move then read as external:
    auto-stop skipped the relay stop and the underlying ran to its endpoint.

    The fix recognises the echo during the startup-delay window too (guard) and
    commits the move's own bookkeeping only once it starts acting (flag move).
    """

    @pytest.mark.asyncio
    async def test_echo_during_startup_delay_keeps_flag_and_sends_stop(self):
        # features = 15 == OPEN|CLOSE|SET_POSITION|STOP; force_time_based keeps
        # the timed path (open_cover forwarded, tracker-driven auto-stop).
        cover = _make_wrapped_cover(
            force_time_based_position=True, travel_startup_delay=0.05
        )
        _set_wrapped_features(cover, 15, state="closed")
        _stub_updates(cover)
        cover.travel_calc.set_position(0)

        await cover.set_position(50)  # timed partial move, startup delay pending
        assert cover._startup_delay_task is not None
        assert not cover._startup_delay_task.done()
        assert cover._self_initiated_movement is True
        assert not cover.travel_calc.is_traveling()  # not started yet

        # A lagged echo of our own open_cover arrives inside the delay window,
        # past the bounce grace window and dispatched with _triggered_externally.
        cover._last_self_command_time = None
        cover._triggered_externally = True
        try:
            await cover._handle_external_state_change("cover.inner", "open", "opening")
        finally:
            cover._triggered_externally = False

        # The in-flight move stays self-initiated (echo recognised, not obeyed).
        assert cover._self_initiated_movement is True

        # Let the startup delay complete and the move run to its target.
        await asyncio.sleep(0.1)
        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._travel_to_position == 50

        # Tracker arrives: a self-initiated move sends the relay stop, so the
        # underlying is halted at 50 rather than running on to the endpoint.
        cover.travel_calc.update_position(50)
        await cover.auto_stop_if_necessary()
        services = _services(cover)
        assert "stop_cover" in services

    @pytest.mark.asyncio
    async def test_control_no_echo_stop_is_sent(self):
        """Control arm: the same move with no echo does send stop_cover."""
        cover = _make_wrapped_cover(
            force_time_based_position=True, travel_startup_delay=0.05
        )
        _set_wrapped_features(cover, 15, state="closed")
        _stub_updates(cover)
        cover.travel_calc.set_position(0)

        await cover.set_position(50)
        await asyncio.sleep(0.1)
        assert cover.travel_calc.is_traveling()

        cover.travel_calc.update_position(50)
        await cover.auto_stop_if_necessary()
        services = _services(cover)
        assert "stop_cover" in services

    @pytest.mark.asyncio
    async def test_control_external_opposite_report_still_tracked(self):
        """Control arm: a genuine external move in the opposite direction during
        the startup-delay window is not suppressed — it reaches the handler and
        reverses (cancelling the pending same-direction startup delay).

        Only the same-direction echo of our own command is swallowed; an
        opposite-direction report is a real external reversal.
        """
        cover = _make_wrapped_cover(
            force_time_based_position=True, travel_startup_delay=0.05
        )
        _set_wrapped_features(cover, 15, state="closed")
        _stub_updates(cover)
        cover.travel_calc.set_position(0)

        await cover.set_position(50)  # self-initiated open, startup delay pending
        assert cover._startup_delay_task is not None
        assert not cover._startup_delay_task.done()

        # An external CLOSING report (opposite to our pending open) arrives in
        # the window. It must fall through and be handled as a reversal.
        cover._last_self_command_time = None
        cover._triggered_externally = True
        try:
            await cover._handle_external_state_change("cover.inner", "open", "closing")
        finally:
            cover._triggered_externally = False

        # The reversal cancelled the pending open's startup delay: the report
        # was tracked, not swallowed.
        assert cover._startup_delay_task is None or cover._startup_delay_task.done()


class TestRedundantReportDuringStartupDelay:
    """A redundant position report inside the travel_startup_delay window must
    not clear the pending move's bookkeeping.

    Snapping runs set_known_position -> _handle_stop and drops _last_command,
    which is the only record of the pending move's direction while the tracker
    is still parked. Without it a reversal issued in the window no longer
    reads as a direction change: async_close_cover sees the tracker settled at
    0 with nothing to cancel, skips the re-drive, and the delay fires on the
    original target — the cover runs on instead of stopping.
    """

    @pytest.mark.asyncio
    async def test_reversal_survives_redundant_report_in_startup_window(self):
        # features = 15 == OPEN|CLOSE|SET_POSITION|STOP; force_time_based keeps
        # the timed path so the move waits out travel_startup_delay.
        cover = _make_wrapped_cover(
            force_time_based_position=True, travel_startup_delay=1.5
        )
        st = _set_wrapped_features(cover, 15, state="closed", current_position=0)
        _stub_updates(cover)
        cover.travel_calc.set_position(0)

        await cover.async_set_cover_position(position=40)
        assert cover._startup_delay_task is not None
        assert not cover._startup_delay_task.done()
        assert not cover.travel_calc.is_traveling()  # parked in the window

        # The underlying re-reports the position it already had, past the
        # bounce grace window and while the delay is still pending.
        cover._last_self_command_time = None
        await cover._handle_external_attribute_change(_attr_event("cover.inner", st))

        cover.hass.services.async_call.reset_mock()
        await cover.async_close_cover()

        services = _services(cover)
        assert "stop_cover" in services
        assert cover._startup_delay_task is None or cover._startup_delay_task.done()


class TestWrappedSyncsToLivePositionAtStartup:
    """B12: on restart the tracker restores from the PositionStore, but the
    underlying may have been moved (app/remote) while HA was down. Trust a
    live reported position over the stored snapshot at startup — but not a
    bare `closed` (the untrustworthy reappearance shape #160 guards against),
    an unavailable underlying, or a cover whose reported position is not a
    measurement (ignore_reported_position, or a command-echo cover).
    """

    @staticmethod
    def _set_underlying_state(cover, *, state="open", current_position=None):
        st = MagicMock()
        st.state = state
        attrs = {}
        if current_position is not None:
            attrs[ATTR_CURRENT_POSITION] = current_position
        st.attributes = attrs
        cover.hass.states.get = lambda eid: (
            st if eid == cover._cover_entity_id else None
        )
        return st

    @staticmethod
    async def _added_to_hass(cover):
        with patch(
            "custom_components.cover_time_based.cover_wrapped.async_track_state_change_event",
            return_value=MagicMock(),
        ):
            await cover.async_added_to_hass()

    @pytest.mark.asyncio
    async def test_syncs_to_live_position_on_restart(
        self, make_cover, _mock_position_store
    ):
        _mock_position_store.async_get = AsyncMock(return_value={"position": 30})
        cover = make_cover(cover_entity_id="cover.inner")
        self._set_underlying_state(cover, state="open", current_position=70)

        await self._added_to_hass(cover)

        assert cover.travel_calc.current_position() == 70
        # The corrected live position must be persisted too — otherwise a
        # second restart with the underlying unavailable would restore the
        # stale stored value (30) all over again.
        _mock_position_store.async_save.assert_awaited_once()
        entry_id, data = _mock_position_store.async_save.await_args.args
        assert entry_id == cover._config_entry_id
        assert data["position"] == 70

    @pytest.mark.asyncio
    async def test_ignore_reported_position_keeps_stored_value(
        self, make_cover, _mock_position_store
    ):
        _mock_position_store.async_get = AsyncMock(return_value={"position": 30})
        cover = make_cover(cover_entity_id="cover.inner", ignore_reported_position=True)
        self._set_underlying_state(cover, state="open", current_position=70)

        await self._added_to_hass(cover)

        assert cover.travel_calc.current_position() == 30
        # No divergence detected, so no spurious persist at startup.
        _mock_position_store.async_save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_command_echo_keeps_stored_value(
        self, make_cover, _mock_position_store
    ):
        """A command-echo cover never trusts a reported position, at startup
        included: both live report channels already ignore it, so a number
        echoed back from the last command must not move the tracker either.
        """
        _mock_position_store.async_get = AsyncMock(return_value={"position": 30})
        cover = make_cover(
            cover_entity_id="cover.inner",
            reports_command_not_endpoint=True,
            ignore_reported_position=False,
        )
        self._set_underlying_state(cover, state="open", current_position=70)

        await self._added_to_hass(cover)

        assert cover.travel_calc.current_position() == 30
        _mock_position_store.async_save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unavailable_underlying_keeps_stored_value(
        self, make_cover, _mock_position_store
    ):
        _mock_position_store.async_get = AsyncMock(return_value={"position": 30})
        cover = make_cover(cover_entity_id="cover.inner")
        self._set_underlying_state(
            cover, state=STATE_UNAVAILABLE, current_position=None
        )

        await self._added_to_hass(cover)

        assert cover.travel_calc.current_position() == 30
        _mock_position_store.async_save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bare_closed_at_startup_keeps_stored_value(
        self, make_cover, _mock_position_store
    ):
        # A bare `closed` with no position attribute is exactly the
        # untrustworthy reappearance shape #160 guards against — trust_closed
        # must stay False at startup too.
        _mock_position_store.async_get = AsyncMock(return_value={"position": 30})
        cover = make_cover(cover_entity_id="cover.inner")
        self._set_underlying_state(cover, state=STATE_CLOSED, current_position=None)

        await self._added_to_hass(cover)

        assert cover.travel_calc.current_position() == 30
        _mock_position_store.async_save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_live_position_matches_stored_value_no_spurious_persist(
        self, make_cover, _mock_position_store
    ):
        # live == stored: no divergence, so the sync branch never runs and the
        # extra persist must not fire at startup.
        _mock_position_store.async_get = AsyncMock(return_value={"position": 30})
        cover = make_cover(cover_entity_id="cover.inner")
        self._set_underlying_state(cover, state="open", current_position=30)

        await self._added_to_hass(cover)

        assert cover.travel_calc.current_position() == 30
        _mock_position_store.async_save.assert_not_awaited()


class TestWrappedDecisionCost:
    """The wrapped decision helpers read the underlying's state once, and an
    attribute report that changes nothing does no work.
    """

    def test_position_driver_reads_state_once(self):
        # Native-both inline cover: the longest decision chain
        # (_position_driver -> _use_native_set_position -> _use_native_tilt
        # -> _wrapped_supports_set_tilt_position, then
        # _wrapped_supports_set_position).
        cover = _make_wrapped_cover(
            tilt_time_close=5, tilt_time_open=5, tilt_mode="inline"
        )
        st = _set_wrapped_features(
            cover, _F_OPEN | _F_CLOSE | _F_SET_POSITION | _F_SET_TILT
        )
        cover.hass.states.get = MagicMock(return_value=st)
        assert cover._position_driver() is cover._native_position_driver
        assert cover.hass.states.get.call_count == 1

    @pytest.mark.asyncio
    async def test_attribute_event_with_same_position_and_no_updater_does_not_snap(
        self,
    ):
        cover = _make_wrapped_cover()
        cover.travel_calc.set_position(40)
        st = _set_wrapped_features(cover, 0, state="open", current_position=40)
        with patch.object(cover, "set_known_position", new=AsyncMock()) as snap:
            await cover._handle_external_attribute_change(
                _attr_event("cover.inner", st)
            )
        snap.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_attribute_event_with_same_position_but_running_updater_still_snaps(
        self,
    ):
        cover = _make_wrapped_cover()
        cover.travel_calc.set_position(40)
        cover._unsubscribe_auto_updater = MagicMock()
        st = _set_wrapped_features(cover, 0, state="open", current_position=40)
        with patch.object(cover, "set_known_position", new=AsyncMock()) as snap:
            await cover._handle_external_attribute_change(
                _attr_event("cover.inner", st)
            )
        snap.assert_awaited_once()
        cover._unsubscribe_auto_updater = None

    @pytest.mark.asyncio
    async def test_attribute_event_reads_position_from_the_event(self):
        cover = _make_wrapped_cover()
        cover.travel_calc.set_position(40)
        event_state = _set_wrapped_features(cover, 0, state="open", current_position=55)
        # A different value in the state machine: reading it would give 99.
        _set_wrapped_features(cover, 0, state="open", current_position=99)
        with patch.object(cover, "set_known_position", new=AsyncMock()) as snap:
            await cover._handle_external_attribute_change(
                _attr_event("cover.inner", event_state)
            )
        snap.assert_awaited_once_with(position=55, supersede=False)


# ---------------------------------------------------------------------------
# Reversal echo counting
# ---------------------------------------------------------------------------


def _make_reversing_cover():
    """A plain wrapped cover with a mid-close underlying, ready to reverse.

    Features are OPEN|CLOSE|STOP but NOT SET_POSITION, so the timed driver
    (and therefore _send_underlying_open/close) drives the move.
    """
    cover = _make_wrapped_cover()
    _stub_updates(cover)
    st = _set_wrapped_features(
        cover, _F_OPEN | _F_CLOSE | _F_STOP, state="closing", current_position=60
    )
    return cover, st


async def _open_while_underlying_closing(cover):
    """Issue our open command while the underlying still reports `closing`."""
    cover.travel_calc.set_position(60)
    await cover.async_open_cover()
    assert cover._last_command == SERVICE_OPEN_COVER
    assert cover.travel_calc.is_traveling() is True
    return cover._pending_switch.get("cover.inner", 0)


class TestReversalPendingCount:
    """What `_send_underlying_open` pre-counts, and how long it lives."""

    @pytest.mark.asyncio
    async def test_open_while_underlying_closing_marks_two_pending(self):
        cover, _ = _make_reversing_cover()

        assert await _open_while_underlying_closing(cover) == 2

    @pytest.mark.asyncio
    async def test_pending_safety_window_is_five_seconds(self):
        cover, _ = _make_reversing_cover()

        before = time.monotonic()
        await _open_while_underlying_closing(cover)
        deadline = cover._pending_switch_deadlines["cover.inner"]

        assert 4.9 <= deadline - before <= 5.1


class TestSingleTransitionReversal:
    """An underlying that reports `closing -> opening` directly (one event).

    The pre-count assumes the reversal arrives as two transitions. A device
    with its own motor controller (Shelly 2.5 in cover mode, KNX, anything
    that updates is_opening/is_closing atomically) delivers one, so the
    surplus count must be dropped at the terminal moving state instead of
    swallowing the next genuine report.
    """

    @pytest.mark.asyncio
    async def test_single_transition_reversal_leaves_no_orphan_pending_count(self):
        cover, st = _make_reversing_cover()

        await _open_while_underlying_closing(cover)

        st.state = "opening"
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "closing", "opening", position=60)
        )

        orphan = cover._pending_switch.get("cover.inner", 0)
        assert orphan == 0, f"orphaned pending echo count left over: {orphan}"

    @pytest.mark.asyncio
    async def test_wall_stop_after_single_transition_reversal_is_honoured(self):
        """The genuine wall stop must snap the tracker to the reported 37%."""
        cover, st = _make_reversing_cover()

        await _open_while_underlying_closing(cover)

        st.state = "opening"
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "closing", "opening", position=60)
        )

        # ~1s later the user hits the wall STOP. Past the 0.5s bounce grace
        # window, so this is a report the cover is supposed to honour.
        cover._last_self_command_time = time.monotonic() - 1.0
        st.state = "open"
        st.attributes[ATTR_CURRENT_POSITION] = 37
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "opening", "open", position=37)
        )

        assert cover.travel_calc.is_traveling() is False, (
            "wall stop swallowed as an echo: tracker still running toward "
            f"{cover.travel_calc._travel_to_position}"
        )
        assert cover.travel_calc.current_position() == 37

    @pytest.mark.asyncio
    async def test_wall_stop_honoured_late_in_the_five_second_window(self):
        """The old loss window ran to the pending deadline, not the bounce one."""
        cover, st = _make_reversing_cover()

        await _open_while_underlying_closing(cover)

        st.state = "opening"
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "closing", "opening", position=60)
        )

        # 4.9s after the command — still inside ECHO_PENDING_WINDOW.
        cover._last_self_command_time = time.monotonic() - 4.9
        st.state = "open"
        st.attributes[ATTR_CURRENT_POSITION] = 37
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "opening", "open", position=37)
        )

        assert cover.travel_calc.current_position() == 37


class TestTwoTransitionReversal:
    """The device the pre-count was written for still drains exactly."""

    @pytest.mark.asyncio
    async def test_two_transition_reversal_leaves_no_orphan(self):
        cover, st = _make_reversing_cover()

        await _open_while_underlying_closing(cover)

        # closing -> open ...
        st.state = "open"
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "closing", "open", position=60)
        )
        # ... then open -> opening.
        st.state = "opening"
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "open", "opening", position=60)
        )

        assert cover._pending_switch.get("cover.inner", 0) == 0

        # The wall stop that follows is honoured.
        cover._last_self_command_time = time.monotonic() - 1.0
        st.state = "open"
        st.attributes[ATTR_CURRENT_POSITION] = 37
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "opening", "open", position=37)
        )

        assert cover.travel_calc.current_position() == 37
        assert cover.travel_calc.is_traveling() is False


class TestBounceGraceWindowInterplay:
    """Inside the 0.5s bounce window the report is dropped anyway."""

    @pytest.mark.asyncio
    async def test_report_inside_bounce_window_is_dropped_even_without_orphan(self):
        cover, st = _make_reversing_cover()

        await _open_while_underlying_closing(cover)

        # Drain the pending count entirely, isolating the bounce window.
        cover._clear_pending_switch("cover.inner")

        st.state = "open"
        st.attributes[ATTR_CURRENT_POSITION] = 37
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "opening", "open", position=37)
        )

        # Still traveling: the bounce grace window (0.5s) discarded it.
        assert cover.travel_calc.is_traveling() is True


class TestReversalViaSetPosition:
    """The stop-then-reverse path over-counts even on a two-transition device.

    `set_position` across the direction sends `stop_cover` (marks 1) and then,
    after the settle gap, `open_cover` — whose `_send_underlying_open` re-reads
    a wrapped state still stuck on `closing` and marks 2 more. Three pending
    against the two transitions the device actually emits.
    """

    @pytest.mark.asyncio
    async def test_stop_then_reverse_leaves_no_orphan_with_two_transitions(self):
        cover, st = _make_reversing_cover()
        cover.travel_calc.set_position(60)
        cover.travel_calc.start_travel(0)
        cover._last_command = SERVICE_CLOSE_COVER
        cover._self_initiated_movement = True

        with patch(
            "custom_components.cover_time_based.cover_base.sleep",
            new_callable=AsyncMock,
        ):
            await cover.set_position(90)

        assert _services(cover) == ["stop_cover", "open_cover"]

        # The device does exactly what the `expected = 2` prediction describes.
        st.state = "open"
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "closing", "open", position=60)
        )
        st.state = "opening"
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "open", "opening", position=60)
        )

        orphan = cover._pending_switch.get("cover.inner", 0)
        assert orphan == 0, f"orphaned pending echo count left over: {orphan}"


class TestNoAttributeChannelRescue:
    """A following attribute-only report cannot undo a swallowed stop.

    `_handle_external_attribute_change` ignores position reports arriving
    mid-timed-move, so if the state event were eaten nothing would correct the
    tracker until it reached its own target — the stop has to be honoured on
    the state channel.
    """

    @pytest.mark.asyncio
    async def test_stop_stands_without_help_from_the_attribute_channel(self):
        cover, st = _make_reversing_cover()

        await _open_while_underlying_closing(cover)

        st.state = "opening"
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "closing", "opening", position=60)
        )

        cover._last_self_command_time = time.monotonic() - 1.0
        st.state = "open"
        st.attributes[ATTR_CURRENT_POSITION] = 37
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "opening", "open", position=37)
        )
        # The device re-reports 37% as an attribute-only update (same state).
        await cover._async_switch_state_changed(
            _state_event("cover.inner", "open", "open", position=37)
        )

        assert cover.travel_calc.current_position() == 37
