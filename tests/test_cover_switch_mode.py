"""Tests for SwitchModeCover._send_open/close/stop.

Each test verifies the exact sequence of homeassistant.turn_on/turn_off
service calls for the latching relay (switch) mode.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.cover_time_based.cover import (
    CONTROL_MODE_PULSE,
    CONTROL_MODE_TOGGLE,
)
from custom_components.cover_time_based.cover_switch_mode import SwitchModeCover

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _make_switch_cover(
    open_switch="switch.open",
    close_switch="switch.close",
    stop_switch=None,
    tilt_open_switch=None,
    tilt_close_switch=None,
    tilt_stop_switch=None,
):
    """Create a SwitchModeCover wired to a mock hass."""
    cover = SwitchModeCover(
        device_id="test_switch",
        name="Test Switch",
        tilt_strategy=None,
        travel_time_close=30,
        travel_time_open=30,
        tilt_time_close=None,
        tilt_time_open=None,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        endpoint_runon_time=None,
        min_movement_time=None,
        open_switch_entity_id=open_switch,
        close_switch_entity_id=close_switch,
        stop_switch_entity_id=stop_switch,
        tilt_open_switch=tilt_open_switch,
        tilt_close_switch=tilt_close_switch,
        tilt_stop_switch=tilt_stop_switch,
    )
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.async_create_task = lambda coro: asyncio.ensure_future(coro)
    cover.hass = hass
    return cover


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _calls(mock: AsyncMock):
    return mock.call_args_list


def _ha(service, entity_id):
    return call("homeassistant", service, {"entity_id": entity_id}, False)


# ---------------------------------------------------------------------------
# _send_open
# ---------------------------------------------------------------------------


class TestSwitchModeSendOpen:
    @pytest.mark.asyncio
    async def test_open_without_stop_switch(self):
        cover = _make_switch_cover()
        await cover._send_open()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_open_with_stop_switch(self):
        """Stop switch is not valid in switch mode; it must be ignored."""
        cover = _make_switch_cover(stop_switch="switch.stop")
        await cover._send_open()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_on", "switch.open"),
        ]


# ---------------------------------------------------------------------------
# _send_close
# ---------------------------------------------------------------------------


class TestSwitchModeSendClose:
    @pytest.mark.asyncio
    async def test_close_without_stop_switch(self):
        cover = _make_switch_cover()
        await cover._send_close()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_close_with_stop_switch(self):
        """Stop switch is not valid in switch mode; it must be ignored."""
        cover = _make_switch_cover(stop_switch="switch.stop")
        await cover._send_close()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.open"),
            _ha("turn_on", "switch.close"),
        ]


# ---------------------------------------------------------------------------
# _send_stop
# ---------------------------------------------------------------------------


class TestSwitchModeSendStop:
    @pytest.mark.asyncio
    async def test_stop_without_stop_switch(self):
        cover = _make_switch_cover()
        await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_with_stop_switch(self):
        """Stop switch is not valid in switch mode; it must be ignored."""
        cover = _make_switch_cover(stop_switch="switch.stop")
        await cover._send_stop()

        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_off", "switch.close"),
            _ha("turn_off", "switch.open"),
        ]


# ---------------------------------------------------------------------------
# Observe-path up/down software interlock (issue #99)
# ---------------------------------------------------------------------------

# Where _mark_switch_pending schedules its safety timeout — patched to a no-op
# so tests don't schedule real timers.
_CALL_LATER = "custom_components.cover_time_based.cover_base.async_call_later"


def _set_switch_states(cover, states):
    """Wire cover.hass.states.get(entity_id) to return the given on/off states.

    `states` maps entity_id -> "on"/"off"; anything absent reports as None.
    """

    def _get(entity_id):
        value = states.get(entity_id)
        if value is None:
            return None
        st = MagicMock()
        st.state = value
        return st

    cover.hass.states.get = MagicMock(side_effect=_get)


class TestSwitchModeObserveInterlock:
    """When a direction relay is observed turning ON externally, the opposite
    relay must be turned OFF (software interlock) without cancelling the move."""

    @pytest.mark.asyncio
    async def test_external_open_turns_close_off_and_still_tracks(self):
        cover = _make_switch_cover()
        _set_switch_states(cover, {"switch.close": "on"})

        with (
            patch(_CALL_LATER, return_value=MagicMock()),
            patch.object(cover, "async_open_cover", new_callable=AsyncMock) as track,
        ):
            await cover._handle_external_state_change("switch.open", "off", "on")

        assert _ha("turn_off", "switch.close") in _calls(cover.hass.services.async_call)
        track.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_external_open_marks_close_echo_pending(self):
        """The interlock's own turn_off is marked pending so the echo isn't
        misread as a user releasing the close switch (which would stop us)."""
        cover = _make_switch_cover()
        _set_switch_states(cover, {"switch.close": "on"})

        with (
            patch(_CALL_LATER, return_value=MagicMock()),
            patch.object(cover, "async_open_cover", new_callable=AsyncMock),
        ):
            await cover._handle_external_state_change("switch.open", "off", "on")

        assert cover._pending_switch.get("switch.close") == 1

    @pytest.mark.asyncio
    async def test_external_close_turns_open_off_and_still_tracks(self):
        cover = _make_switch_cover()
        _set_switch_states(cover, {"switch.open": "on"})

        with (
            patch(_CALL_LATER, return_value=MagicMock()),
            patch.object(cover, "async_close_cover", new_callable=AsyncMock) as track,
        ):
            await cover._handle_external_state_change("switch.close", "off", "on")

        assert _ha("turn_off", "switch.open") in _calls(cover.hass.services.async_call)
        assert cover._pending_switch.get("switch.open") == 1
        track.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_interlock_write_when_opposite_already_off(self):
        """If the opposite relay is already OFF there is nothing to interlock,
        so no relay write (and no spurious echo) is produced."""
        cover = _make_switch_cover()
        _set_switch_states(cover, {"switch.close": "off"})

        with (
            patch(_CALL_LATER, return_value=MagicMock()),
            patch.object(cover, "async_open_cover", new_callable=AsyncMock) as track,
        ):
            await cover._handle_external_state_change("switch.open", "off", "on")

        assert cover.hass.services.async_call.call_count == 0
        assert "switch.close" not in cover._pending_switch
        track.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_external_off_stops_without_interlock_write(self):
        """The OFF (relay released) path is unchanged: stop, no relay write."""
        cover = _make_switch_cover()
        _set_switch_states(cover, {})

        with patch.object(cover, "async_stop_cover", new_callable=AsyncMock) as stop:
            await cover._handle_external_state_change("switch.open", "on", "off")

        stop.assert_awaited_once()
        assert cover.hass.services.async_call.call_count == 0

    @pytest.mark.asyncio
    async def test_interlock_off_echo_does_not_trigger_stop(self):
        """End-to-end: the interlock's turn_off event, when it arrives back via
        _async_switch_state_changed, is echo-filtered and does NOT stop us."""
        cover = _make_switch_cover()
        _set_switch_states(cover, {"switch.close": "on"})

        with (
            patch(_CALL_LATER, return_value=MagicMock()),
            patch.object(cover, "async_open_cover", new_callable=AsyncMock),
            patch.object(cover, "async_stop_cover", new_callable=AsyncMock) as stop,
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "_entity_unavailable", return_value=False),
        ):
            # 1. open relay observed ON externally → interlock turns close OFF
            await cover._handle_external_state_change("switch.open", "off", "on")
            assert cover._pending_switch.get("switch.close") == 1

            # 2. the close relay's resulting OFF event arrives
            event = MagicMock()
            old = MagicMock()
            old.state = "on"
            new = MagicMock()
            new.state = "off"
            event.data = {
                "entity_id": "switch.close",
                "old_state": old,
                "new_state": new,
            }
            await cover._async_switch_state_changed(event)

        assert "switch.close" not in cover._pending_switch
        stop.assert_not_awaited()


class TestSwitchModeTiltObserveInterlock:
    """Dual-motor tilt relays also latch in switch mode, so observing one tilt
    direction turn ON externally must turn the opposite tilt relay OFF — the
    same interlock as travel (the tilt driver path already does this)."""

    @pytest.mark.asyncio
    async def test_external_tilt_open_turns_tilt_close_off_and_still_tracks(self):
        cover = _make_switch_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _set_switch_states(cover, {"switch.tilt_close": "on"})

        with (
            patch(_CALL_LATER, return_value=MagicMock()),
            patch.object(
                cover, "async_open_cover_tilt", new_callable=AsyncMock
            ) as track,
        ):
            await cover._handle_external_tilt_state_change(
                "switch.tilt_open", "off", "on"
            )

        assert _ha("turn_off", "switch.tilt_close") in _calls(
            cover.hass.services.async_call
        )
        assert cover._pending_switch.get("switch.tilt_close") == 1
        track.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_external_tilt_close_turns_tilt_open_off_and_still_tracks(self):
        cover = _make_switch_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _set_switch_states(cover, {"switch.tilt_open": "on"})

        with (
            patch(_CALL_LATER, return_value=MagicMock()),
            patch.object(
                cover, "async_close_cover_tilt", new_callable=AsyncMock
            ) as track,
        ):
            await cover._handle_external_tilt_state_change(
                "switch.tilt_close", "off", "on"
            )

        assert _ha("turn_off", "switch.tilt_open") in _calls(
            cover.hass.services.async_call
        )
        assert cover._pending_switch.get("switch.tilt_open") == 1
        track.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_tilt_interlock_write_when_opposite_already_off(self):
        cover = _make_switch_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _set_switch_states(cover, {"switch.tilt_close": "off"})

        with (
            patch(_CALL_LATER, return_value=MagicMock()),
            patch.object(
                cover, "async_open_cover_tilt", new_callable=AsyncMock
            ) as track,
        ):
            await cover._handle_external_tilt_state_change(
                "switch.tilt_open", "off", "on"
            )

        assert cover.hass.services.async_call.call_count == 0
        assert "switch.tilt_close" not in cover._pending_switch
        track.assert_awaited_once()


class TestNonSwitchModesHaveNoInterlock:
    """Toggle and pulse modes don't latch a direction relay, so their observe
    path must not write to the relays (no interlock)."""

    @pytest.mark.asyncio
    async def test_pulse_observe_open_writes_no_relay(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_PULSE)
        _set_switch_states(cover, {"switch.close": "on"})

        with patch.object(cover, "async_open_cover", new_callable=AsyncMock):
            await cover._handle_external_state_change("switch.open", "off", "on")

        assert cover.hass.services.async_call.call_count == 0

    @pytest.mark.asyncio
    async def test_toggle_observe_open_writes_no_relay(self, make_cover):
        cover = make_cover(control_mode=CONTROL_MODE_TOGGLE)
        _set_switch_states(cover, {"switch.close": "on"})

        with patch.object(cover, "async_open_cover", new_callable=AsyncMock):
            await cover._handle_external_state_change("switch.open", "off", "on")

        assert cover.hass.services.async_call.call_count == 0
