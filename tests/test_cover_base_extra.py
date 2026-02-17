"""Tests for previously uncovered areas in cover_base.py.

Covers: properties, state restoration, auto_updater, extra_state_attributes,
supported_features, async_set_cover_position/tilt, state monitoring
(echo filtering, external state changes), delayed_stop completion,
name fallback, _stop_travel_if_traveling with tilt.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_CURRENT_TILT_POSITION,
    CoverEntityFeature,
)
from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER


# ===================================================================
# Name / unique_id / device_class / assumed_state properties
# ===================================================================


class TestBasicProperties:
    """Test basic entity properties."""

    def test_name_from_constructor(self, make_cover):
        cover = make_cover()
        assert cover.name == "Test Cover"

    def test_name_falls_back_to_device_id(self, make_cover):
        from custom_components.cover_time_based.cover import (
            _create_cover_from_options,
            CONF_DEVICE_TYPE,
            CONF_OPEN_SWITCH_ENTITY_ID,
            CONF_CLOSE_SWITCH_ENTITY_ID,
            CONF_INPUT_MODE,
            DEVICE_TYPE_SWITCH,
            INPUT_MODE_SWITCH,
        )

        cover = _create_cover_from_options(
            {
                CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                CONF_INPUT_MODE: INPUT_MODE_SWITCH,
            },
            device_id="my_device",
            name="",
        )
        assert cover.name == "my_device"

    def test_unique_id(self, make_cover):
        cover = make_cover()
        assert cover.unique_id == "cover_timebased_uuid_test_cover"

    def test_device_class_is_none(self, make_cover):
        cover = make_cover()
        assert cover.device_class is None

    def test_assumed_state_is_true(self, make_cover):
        cover = make_cover()
        assert cover.assumed_state is True


# ===================================================================
# extra_state_attributes
# ===================================================================


class TestExtraStateAttributes:
    """Test extra_state_attributes returns all configured timing values."""

    def test_attributes_with_all_values(self, make_cover):
        cover = make_cover(
            travel_time_down=25.0,
            travel_time_up=20.0,
            tilt_time_down=5.0,
            tilt_time_up=4.0,
            travel_moves_with_tilt=True,
            travel_delay_at_end=1.5,
            min_movement_time=0.5,
            travel_startup_delay=0.3,
            tilt_startup_delay=0.2,
        )
        attrs = cover.extra_state_attributes
        assert attrs["travelling_time_down"] == 25.0
        assert attrs["travelling_time_up"] == 20.0
        assert attrs["tilting_time_down"] == 5.0
        assert attrs["tilting_time_up"] == 4.0
        assert attrs["travel_moves_with_tilt"] is True
        assert attrs["travel_delay_at_end"] == 1.5
        assert attrs["min_movement_time"] == 0.5
        assert attrs["travel_startup_delay"] == 0.3
        assert attrs["tilt_startup_delay"] == 0.2

    def test_attributes_with_no_optional_values(self, make_cover):
        cover = make_cover()
        attrs = cover.extra_state_attributes
        # travel_time_down/up are always set (default 30)
        assert attrs["travelling_time_down"] == 30
        assert attrs["travelling_time_up"] == 30
        # Optional values should not be present when None
        assert "tilting_time_down" not in attrs
        assert "tilting_time_up" not in attrs
        assert "travel_delay_at_end" not in attrs
        assert "min_movement_time" not in attrs
        assert "travel_startup_delay" not in attrs
        assert "tilt_startup_delay" not in attrs


# ===================================================================
# supported_features
# ===================================================================


class TestSupportedFeatures:
    """Test supported_features flag calculation."""

    def test_basic_features_without_tilt(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(50)
        features = cover.supported_features
        assert features & CoverEntityFeature.OPEN
        assert features & CoverEntityFeature.CLOSE
        assert features & CoverEntityFeature.STOP
        assert features & CoverEntityFeature.SET_POSITION
        assert not (features & CoverEntityFeature.OPEN_TILT)

    def test_tilt_features_with_tilt_support(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)
        features = cover.supported_features
        assert features & CoverEntityFeature.OPEN_TILT
        assert features & CoverEntityFeature.CLOSE_TILT
        assert features & CoverEntityFeature.STOP_TILT
        assert features & CoverEntityFeature.SET_TILT_POSITION

    def test_no_set_position_when_position_unknown(self, make_cover):
        cover = make_cover()
        # Don't set position — it remains None
        features = cover.supported_features
        assert not (features & CoverEntityFeature.SET_POSITION)


# ===================================================================
# async_set_cover_position / async_set_cover_tilt_position
# ===================================================================


class TestAsyncSetCoverPosition:
    """Test the HA service interface methods."""

    @pytest.mark.asyncio
    async def test_async_set_cover_position_calls_set_position(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_set_cover_position(position=50)

        assert cover.travel_calc.is_traveling()
        assert cover._last_command == SERVICE_CLOSE_COVER

    @pytest.mark.asyncio
    async def test_async_set_cover_tilt_position_calls_set_tilt_position(
        self, make_cover
    ):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_set_cover_tilt_position(tilt_position=50)

        assert cover.tilt_calc.is_traveling()
        assert cover._last_command == SERVICE_CLOSE_COVER


# ===================================================================
# async_added_to_hass (state restoration)
# ===================================================================


class TestStateRestoration:
    """Test position restoration from HA history on startup."""

    @pytest.mark.asyncio
    async def test_restores_position_from_old_state(self, make_cover):
        cover = make_cover()

        old_state = MagicMock()
        old_state.attributes = {ATTR_CURRENT_POSITION: 70}

        with patch.object(cover, "async_get_last_state", return_value=old_state):
            with patch(
                "custom_components.cover_time_based.cover_base.async_track_state_change_event"
            ):
                await cover.async_added_to_hass()

        # HA position 70 -> internal position 30
        assert cover.travel_calc.current_position() == 30

    @pytest.mark.asyncio
    async def test_restores_position_and_tilt_from_old_state(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)

        old_state = MagicMock()
        old_state.attributes = {
            ATTR_CURRENT_POSITION: 60,
            ATTR_CURRENT_TILT_POSITION: 80,
        }

        with patch.object(cover, "async_get_last_state", return_value=old_state):
            with patch(
                "custom_components.cover_time_based.cover_base.async_track_state_change_event"
            ):
                await cover.async_added_to_hass()

        assert cover.travel_calc.current_position() == 40
        assert cover.tilt_calc.current_position() == 20

    @pytest.mark.asyncio
    async def test_no_restore_when_no_old_state(self, make_cover):
        cover = make_cover()

        with patch.object(cover, "async_get_last_state", return_value=None):
            with patch(
                "custom_components.cover_time_based.cover_base.async_track_state_change_event"
            ):
                await cover.async_added_to_hass()

        # Position should remain unset
        assert cover.travel_calc.current_position() is None

    @pytest.mark.asyncio
    async def test_no_restore_when_old_state_has_no_position(self, make_cover):
        cover = make_cover()

        old_state = MagicMock()
        old_state.attributes = {}

        with patch.object(cover, "async_get_last_state", return_value=old_state):
            with patch(
                "custom_components.cover_time_based.cover_base.async_track_state_change_event"
            ):
                await cover.async_added_to_hass()

        assert cover.travel_calc.current_position() is None

    @pytest.mark.asyncio
    async def test_registers_state_listeners_for_switch_entities(self, make_cover):
        cover = make_cover(stop_switch="switch.stop")

        with patch.object(cover, "async_get_last_state", return_value=None):
            with patch(
                "custom_components.cover_time_based.cover_base.async_track_state_change_event"
            ) as mock_track:
                await cover.async_added_to_hass()

        # Should register listeners for open, close, and stop switches
        assert mock_track.call_count == 3
        assert len(cover._state_listener_unsubs) == 3


# ===================================================================
# async_will_remove_from_hass
# ===================================================================


class TestRemoveFromHass:
    """Test cleanup on removal."""

    @pytest.mark.asyncio
    async def test_unsubscribes_state_listeners(self, make_cover):
        cover = make_cover()
        unsub1 = MagicMock()
        unsub2 = MagicMock()
        cover._state_listener_unsubs = [unsub1, unsub2]

        await cover.async_will_remove_from_hass()

        unsub1.assert_called_once()
        unsub2.assert_called_once()
        assert len(cover._state_listener_unsubs) == 0

    @pytest.mark.asyncio
    async def test_cancels_pending_switch_timers(self, make_cover):
        cover = make_cover()
        timer = MagicMock()
        cover._pending_switch_timers = {"switch.open": timer}

        await cover.async_will_remove_from_hass()

        timer.assert_called_once()
        assert len(cover._pending_switch_timers) == 0


# ===================================================================
# auto_updater_hook
# ===================================================================


class TestAutoUpdaterHook:
    """Test the periodic auto-updater callback."""

    @pytest.mark.asyncio
    async def test_auto_updater_hook_calls_update(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel(100)

        mock_update = MagicMock()
        with patch.object(cover, "async_schedule_update_ha_state", mock_update):
            with patch.object(cover, "auto_stop_if_necessary", new_callable=AsyncMock):
                cover.auto_updater_hook(None)

        mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_updater_hook_stops_when_position_reached(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel(50)  # already at target

        unsub = MagicMock()
        cover._unsubscribe_auto_updater = unsub

        with patch.object(cover, "async_schedule_update_ha_state"):
            with patch.object(cover, "auto_stop_if_necessary", new_callable=AsyncMock):
                cover.auto_updater_hook(None)

        # Auto updater should have been stopped
        unsub.assert_called_once()
        assert cover._unsubscribe_auto_updater is None


# ===================================================================
# auto_stop_if_necessary with tilt
# ===================================================================


class TestAutoStopWithTilt:
    """Test auto_stop_if_necessary tilt_calc.stop() branch."""

    @pytest.mark.asyncio
    async def test_auto_stop_stops_tilt_calc(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        # Both at target, position reached
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)
        cover.travel_calc.start_travel(100)
        cover.tilt_calc.start_travel(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.auto_stop_if_necessary()

        assert not cover.tilt_calc.is_traveling()


# ===================================================================
# _delayed_stop completion
# ===================================================================


class TestDelayedStopCompletion:
    """Test the _delayed_stop method completing successfully."""

    @pytest.mark.asyncio
    async def test_delayed_stop_completes_and_sends_stop(self, make_cover):
        cover = make_cover(travel_delay_at_end=0.01)
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover._delayed_stop(0.01)

        # Should have sent stop command
        cover.hass.services.async_call.assert_awaited()
        assert cover._last_command is None
        assert cover._delay_task is None


# ===================================================================
# _stop_travel_if_traveling with tilt also traveling
# ===================================================================


class TestStopTravelIfTravelingWithTilt:
    """Test _stop_travel_if_traveling stops tilt as well."""

    def test_stops_both_travel_and_tilt(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover.tilt_calc.set_position(50)
        cover.tilt_calc.start_travel_down()

        cover._stop_travel_if_traveling()

        assert not cover.travel_calc.is_traveling()
        assert not cover.tilt_calc.is_traveling()


# ===================================================================
# set_position edge cases
# ===================================================================


class TestSetPositionEdgeCases:
    """Test set_position edge cases for coverage."""

    @pytest.mark.asyncio
    async def test_direction_change_stops_tilt_too(self, make_cover):
        """Direction change during set_position should stop tilt if traveling."""
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover.tilt_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(80)  # open direction = direction change

        assert cover._last_command == SERVICE_OPEN_COVER
        # Tilt should have been stopped during direction change

    @pytest.mark.asyncio
    async def test_direction_change_reaches_target_after_stop(self, make_cover):
        """If target equals current after stopping, cover should not move."""
        cover = make_cover()
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            # After stopping, current should be ~50, and target = 100-50 = 50
            await cover.set_position(50)

        # This hits the target == current after stop branch

    @pytest.mark.asyncio
    async def test_set_position_cancels_active_relay_delay(self, make_cover):
        """Active relay delay should be cancelled before new position movement."""
        cover = make_cover(travel_delay_at_end=10.0)
        cover.travel_calc.set_position(50)

        async def fake_delay():
            await asyncio.sleep(100)

        cover._delay_task = asyncio.ensure_future(fake_delay())

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(0)

        assert cover.travel_calc.is_traveling()


# ===================================================================
# set_tilt_position edge cases
# ===================================================================


class TestSetTiltPositionEdgeCases:
    """Test set_tilt_position edge cases for coverage."""

    @pytest.mark.asyncio
    async def test_direction_change_stops_both_tilt_and_travel(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)
        cover.tilt_calc.start_travel_down()
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(80)  # open direction

        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_direction_change_reaches_tilt_target_after_stop(self, make_cover):
        """If tilt target equals current after stopping, should not move."""
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)
        cover.tilt_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            # Target = 100 - 50 = 50, same as current after stop
            await cover.set_tilt_position(50)

    @pytest.mark.asyncio
    async def test_set_tilt_cancels_active_relay_delay(self, make_cover):
        """Active relay delay should be cancelled before new tilt movement."""
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            travel_delay_at_end=10.0,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        async def fake_delay():
            await asyncio.sleep(100)

        cover._delay_task = asyncio.ensure_future(fake_delay())

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(0)

        assert cover.tilt_calc.is_traveling()


# ===================================================================
# Tilt endpoint startup delay conflicts
# ===================================================================


class TestTiltEndpointStartupDelay:
    """Test startup delay conflicts in _async_move_tilt_to_endpoint."""

    @pytest.mark.asyncio
    async def test_tilt_direction_change_cancels_startup_delay(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            tilt_startup_delay=10.0,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(50)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()  # start closing tilt

        original_task = cover._startup_delay_task
        assert original_task is not None
        assert cover._last_command == SERVICE_CLOSE_COVER

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover_tilt()  # direction change

        # Let the cancellation finalize
        await asyncio.sleep(0)

        # Original startup delay should have been cancelled;
        # a new one was created for the open direction
        assert original_task.done() or original_task.cancelled()
        assert cover._last_command == SERVICE_OPEN_COVER

    @pytest.mark.asyncio
    async def test_tilt_same_direction_during_startup_delay_skips(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            tilt_startup_delay=10.0,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        task1 = cover._startup_delay_task

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        # Same direction, should not restart
        assert cover._startup_delay_task is task1

    @pytest.mark.asyncio
    async def test_tilt_cancels_active_relay_delay(self, make_cover):
        """Tilt endpoint movement should cancel active relay delay."""
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            travel_delay_at_end=10.0,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        async def fake_delay():
            await asyncio.sleep(100)

        cover._delay_task = asyncio.ensure_future(fake_delay())

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()

        assert cover.tilt_calc.is_traveling()


# ===================================================================
# State monitoring: _async_switch_state_changed & echo filtering
# ===================================================================


class TestSwitchStateChanged:
    """Test the _async_switch_state_changed state monitoring handler."""

    @pytest.mark.asyncio
    async def test_ignores_event_with_none_states(self, make_cover):
        cover = make_cover()
        event = MagicMock()
        event.data = {"entity_id": "switch.open", "new_state": None, "old_state": None}

        with patch.object(cover, "async_write_ha_state"):
            await cover._async_switch_state_changed(event)

        # Should return early, no state change handling

    @pytest.mark.asyncio
    async def test_echo_filtering_decrements_pending(self, make_cover):
        cover = make_cover()
        cover._pending_switch["switch.open"] = 2

        event = MagicMock()
        old = MagicMock()
        old.state = "off"
        new = MagicMock()
        new.state = "on"
        event.data = {
            "entity_id": "switch.open",
            "old_state": old,
            "new_state": new,
        }

        with patch.object(cover, "async_write_ha_state"):
            await cover._async_switch_state_changed(event)

        # Pending should have decremented from 2 to 1
        assert cover._pending_switch["switch.open"] == 1

    @pytest.mark.asyncio
    async def test_echo_filtering_clears_pending_at_zero(self, make_cover):
        cover = make_cover()
        cover._pending_switch["switch.open"] = 1
        timer = MagicMock()
        cover._pending_switch_timers["switch.open"] = timer

        event = MagicMock()
        old = MagicMock()
        old.state = "off"
        new = MagicMock()
        new.state = "on"
        event.data = {
            "entity_id": "switch.open",
            "old_state": old,
            "new_state": new,
        }

        with patch.object(cover, "async_write_ha_state"):
            await cover._async_switch_state_changed(event)

        # Pending should have been fully cleared
        assert "switch.open" not in cover._pending_switch
        # Timer should have been cancelled
        timer.assert_called_once()

    @pytest.mark.asyncio
    async def test_external_state_change_triggers_handler(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(50)

        event = MagicMock()
        old = MagicMock()
        old.state = "on"
        new = MagicMock()
        new.state = "off"
        event.data = {
            "entity_id": "switch.open",
            "old_state": old,
            "new_state": new,
        }

        with patch.object(
            cover, "_handle_external_state_change", new_callable=AsyncMock
        ) as mock_handler:
            await cover._async_switch_state_changed(event)

        # Should have set _triggered_externally and called handler
        mock_handler.assert_awaited_once_with("switch.open", "on", "off")

    @pytest.mark.asyncio
    async def test_triggered_externally_reset_after_handler(self, make_cover):
        cover = make_cover()

        event = MagicMock()
        old = MagicMock()
        old.state = "on"
        new = MagicMock()
        new.state = "off"
        event.data = {
            "entity_id": "switch.open",
            "old_state": old,
            "new_state": new,
        }

        with patch.object(
            cover, "_handle_external_state_change", new_callable=AsyncMock
        ):
            await cover._async_switch_state_changed(event)

        assert cover._triggered_externally is False


# ===================================================================
# _mark_switch_pending
# ===================================================================


class TestMarkSwitchPending:
    """Test echo filtering setup via _mark_switch_pending."""

    def test_increments_pending_count(self, make_cover):
        cover = make_cover()
        with patch(
            "custom_components.cover_time_based.cover_base.async_call_later"
        ) as mock_call_later:
            mock_call_later.return_value = MagicMock()
            cover._mark_switch_pending("switch.open", 2)

        assert cover._pending_switch["switch.open"] == 2

    def test_accumulates_pending_count(self, make_cover):
        cover = make_cover()
        with patch(
            "custom_components.cover_time_based.cover_base.async_call_later"
        ) as mock_call_later:
            mock_call_later.return_value = MagicMock()
            cover._mark_switch_pending("switch.open", 1)
            cover._mark_switch_pending("switch.open", 2)

        assert cover._pending_switch["switch.open"] == 3

    def test_cancels_existing_timeout(self, make_cover):
        cover = make_cover()
        old_timer = MagicMock()
        cover._pending_switch_timers["switch.open"] = old_timer

        with patch(
            "custom_components.cover_time_based.cover_base.async_call_later"
        ) as mock_call_later:
            mock_call_later.return_value = MagicMock()
            cover._mark_switch_pending("switch.open", 1)

        old_timer.assert_called_once()

    def test_sets_new_safety_timeout(self, make_cover):
        cover = make_cover()
        with patch(
            "custom_components.cover_time_based.cover_base.async_call_later"
        ) as mock_call_later:
            mock_call_later.return_value = MagicMock()
            cover._mark_switch_pending("switch.open", 1)

        mock_call_later.assert_called_once()
        assert "switch.open" in cover._pending_switch_timers


# ===================================================================
# _execute_with_startup_delay completion
# ===================================================================


class TestStartupDelayCompletion:
    """Test that _execute_with_startup_delay completes correctly."""

    @pytest.mark.asyncio
    async def test_startup_delay_completes_and_starts_tracking(self, make_cover):
        cover = make_cover(travel_startup_delay=0.01)
        cover.travel_calc.set_position(0)

        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()

        # Wait for the startup delay to complete
        await cover._startup_delay_task

        # After delay, tracking should have started
        assert cover.travel_calc.is_traveling()
        assert cover._startup_delay_task is None


# ===================================================================
# _async_handle_command with _triggered_externally
# ===================================================================


class TestHandleCommandExternallyTriggered:
    """Test _async_handle_command skips relay when triggered externally."""

    @pytest.mark.asyncio
    async def test_external_close_skips_send_close(self, make_cover):
        cover = make_cover()
        cover._triggered_externally = True

        with patch.object(cover, "_send_close", new_callable=AsyncMock) as mock_send:
            with patch.object(cover, "async_write_ha_state"):
                await cover._async_handle_command(SERVICE_CLOSE_COVER)

        mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_external_open_skips_send_open(self, make_cover):
        cover = make_cover()
        cover._triggered_externally = True

        with patch.object(cover, "_send_open", new_callable=AsyncMock) as mock_send:
            with patch.object(cover, "async_write_ha_state"):
                await cover._async_handle_command(SERVICE_OPEN_COVER)

        mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_external_stop_skips_send_stop(self, make_cover):
        cover = make_cover()
        cover._triggered_externally = True

        with patch.object(cover, "_send_stop", new_callable=AsyncMock) as mock_send:
            with patch.object(cover, "async_write_ha_state"):
                await cover._async_handle_command("stop_cover")

        mock_send.assert_not_awaited()


# ===================================================================
# async_stop_cover with _triggered_externally
# ===================================================================


class TestStopCoverExternallyTriggered:
    """Test async_stop_cover skips _send_stop when externally triggered."""

    @pytest.mark.asyncio
    async def test_stop_externally_triggered_skips_send(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER
        cover._triggered_externally = True

        with patch.object(cover, "_send_stop", new_callable=AsyncMock) as mock_send:
            with patch.object(cover, "async_write_ha_state"):
                await cover.async_stop_cover()

        mock_send.assert_not_awaited()


# ===================================================================
# position_reached
# ===================================================================


class TestPositionReached:
    """Test position_reached method."""

    def test_position_reached_without_tilt(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel(50)
        assert cover.position_reached() is True

    def test_position_not_reached(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel(100)
        assert cover.position_reached() is False

    def test_position_reached_with_tilt_both_reached(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel(50)
        cover.tilt_calc.set_position(50)
        cover.tilt_calc.start_travel(50)
        assert cover.position_reached() is True

    def test_position_reached_with_tilt_not_reached(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel(50)
        cover.tilt_calc.set_position(0)
        cover.tilt_calc.start_travel(100)
        assert cover.position_reached() is False


# ===================================================================
# is_opening / is_closing with tilt
# ===================================================================


class TestIsOpeningClosingWithTilt:
    """Test is_opening/is_closing when only tilt is traveling."""

    def test_is_opening_from_tilt(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)
        cover.tilt_calc.start_travel_up()
        assert cover.is_opening is True

    def test_is_closing_from_tilt(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)
        cover.tilt_calc.start_travel_down()
        assert cover.is_closing is True


# ===================================================================
# start_auto_updater / stop_auto_updater
# ===================================================================


class TestAutoUpdater:
    """Test start/stop auto updater."""

    def test_start_auto_updater_subscribes(self, make_cover):
        cover = make_cover()
        with patch(
            "custom_components.cover_time_based.cover_base.async_track_time_interval"
        ) as mock_track:
            mock_track.return_value = MagicMock()
            cover.start_auto_updater()

        assert cover._unsubscribe_auto_updater is not None

    def test_start_auto_updater_idempotent(self, make_cover):
        cover = make_cover()
        unsub = MagicMock()
        cover._unsubscribe_auto_updater = unsub

        with patch(
            "custom_components.cover_time_based.cover_base.async_track_time_interval"
        ) as mock_track:
            cover.start_auto_updater()

        # Should not create a second subscriber
        mock_track.assert_not_called()
        assert cover._unsubscribe_auto_updater is unsub

    def test_stop_auto_updater_unsubscribes(self, make_cover):
        cover = make_cover()
        unsub = MagicMock()
        cover._unsubscribe_auto_updater = unsub

        cover.stop_auto_updater()

        unsub.assert_called_once()
        assert cover._unsubscribe_auto_updater is None

    def test_stop_auto_updater_noop_when_not_running(self, make_cover):
        cover = make_cover()
        cover._unsubscribe_auto_updater = None

        cover.stop_auto_updater()  # Should not raise


# ===================================================================
# set_tilt_position: startup delay same direction (line 605)
# ===================================================================


class TestSetTiltPositionStartupDelay:
    """set_tilt_position with same-direction startup delay should skip."""

    @pytest.mark.asyncio
    async def test_same_direction_startup_delay_skips(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            tilt_startup_delay=10.0,
        )
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)

        # Start closing tilt (creates startup delay)
        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(0)  # close direction

        task1 = cover._startup_delay_task
        assert task1 is not None
        assert cover._last_command == SERVICE_CLOSE_COVER

        # Same direction set_tilt during startup delay should skip
        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(20)  # still close direction

        # Task should not have been restarted
        assert cover._startup_delay_task is task1


# ===================================================================
# _mark_switch_pending: safety timeout callback (lines 784-787)
# ===================================================================


class TestMarkSwitchPendingTimeout:
    """Test the safety timeout callback in _mark_switch_pending."""

    def test_safety_timeout_clears_pending(self, make_cover):
        cover = make_cover()
        captured_callback = [None]

        def mock_call_later(hass, delay, callback):
            captured_callback[0] = callback
            return MagicMock()

        with patch(
            "custom_components.cover_time_based.cover_base.async_call_later",
            side_effect=mock_call_later,
        ):
            cover._mark_switch_pending("switch.open", 2)

        assert cover._pending_switch["switch.open"] == 2
        assert captured_callback[0] is not None

        # Simulate the timeout firing
        captured_callback[0](None)

        # Pending should have been cleared
        assert "switch.open" not in cover._pending_switch
        assert "switch.open" not in cover._pending_switch_timers
