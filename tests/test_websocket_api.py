"""Tests for the WebSocket API module."""

import pytest
from unittest.mock import MagicMock, patch

from custom_components.cover_time_based.cover import (
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_COVER_ENTITY_ID,
    CONF_DEVICE_TYPE,
    CONF_INPUT_MODE,
    CONF_MIN_MOVEMENT_TIME,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_TILT_MOTOR_OVERHEAD,
    CONF_TILTING_TIME_DOWN,
    CONF_TILTING_TIME_UP,
    CONF_TRAVEL_MOTOR_OVERHEAD,
    CONF_TRAVEL_MOVES_WITH_TILT,
    CONF_TRAVELLING_TIME_DOWN,
    CONF_TRAVELLING_TIME_UP,
    DEFAULT_PULSE_TIME,
    DEFAULT_TRAVEL_TIME,
    DEVICE_TYPE_COVER,
    DEVICE_TYPE_SWITCH,
    INPUT_MODE_PULSE,
    INPUT_MODE_SWITCH,
    INPUT_MODE_TOGGLE,
)
from custom_components.cover_time_based.websocket_api import (
    _resolve_config_entry,
    async_register_websocket_api,
    ws_get_config,
    ws_update_config,
)

DOMAIN = "cover_time_based"
ENTITY_ID = "cover.test_blind"
ENTRY_ID = "test_entry_123"


def _unwrap(fn):
    """Get the original async function from a decorated WS handler."""
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


# Unwrapped coroutines — bypass @async_response / @websocket_command decorators
_ws_get_config = _unwrap(ws_get_config)
_ws_update_config = _unwrap(ws_update_config)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hass(options=None, *, domain=DOMAIN, entry_id=ENTRY_ID):
    """Build a mock HomeAssistant with entity registry and config entry."""
    config_entry = MagicMock()
    config_entry.entry_id = entry_id
    config_entry.domain = domain
    config_entry.options = dict(options or {})

    registry_entry = MagicMock()
    registry_entry.config_entry_id = entry_id

    entity_reg = MagicMock()
    entity_reg.async_get.return_value = registry_entry

    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = config_entry

    return hass, config_entry, entity_reg


def _make_connection():
    """Build a mock WebSocket connection."""
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


# ---------------------------------------------------------------------------
# _resolve_config_entry
# ---------------------------------------------------------------------------


class TestResolveConfigEntry:
    """Tests for _resolve_config_entry helper."""

    def test_valid_entity(self):
        hass, config_entry, entity_reg = _make_hass()
        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            result, error = _resolve_config_entry(hass, ENTITY_ID)

        assert result is config_entry
        assert error is None

    def test_entity_not_found(self):
        hass, _, entity_reg = _make_hass()
        entity_reg.async_get.return_value = None

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            result, error = _resolve_config_entry(hass, "cover.nonexistent")

        assert result is None
        assert "not found" in error.lower()

    def test_entity_without_config_entry_id(self):
        hass, _, entity_reg = _make_hass()
        entry = MagicMock()
        entry.config_entry_id = None
        entity_reg.async_get.return_value = entry

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            result, error = _resolve_config_entry(hass, ENTITY_ID)

        assert result is None
        assert error is not None

    def test_wrong_domain(self):
        hass, _, entity_reg = _make_hass(domain="other_domain")

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            result, error = _resolve_config_entry(hass, ENTITY_ID)

        assert result is None
        assert "cover_time_based" in error

    def test_config_entry_missing(self):
        hass, _, entity_reg = _make_hass()
        hass.config_entries.async_get_entry.return_value = None

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            result, error = _resolve_config_entry(hass, ENTITY_ID)

        assert result is None
        assert error is not None


# ---------------------------------------------------------------------------
# ws_get_config
# ---------------------------------------------------------------------------


class TestWsGetConfig:
    """Tests for ws_get_config WebSocket handler."""

    @pytest.mark.asyncio
    async def test_returns_defaults_when_options_empty(self):
        hass, _, entity_reg = _make_hass(options={})
        conn = _make_connection()

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            await _ws_get_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/get_config",
                    "entity_id": ENTITY_ID,
                },
            )

        conn.send_result.assert_called_once()
        result = conn.send_result.call_args[0][1]

        assert result["entry_id"] == ENTRY_ID
        assert result["device_type"] == DEVICE_TYPE_SWITCH
        assert result["input_mode"] == INPUT_MODE_SWITCH
        assert result["pulse_time"] == DEFAULT_PULSE_TIME
        assert result["travelling_time_down"] == DEFAULT_TRAVEL_TIME
        assert result["travelling_time_up"] == DEFAULT_TRAVEL_TIME
        assert result["travel_moves_with_tilt"] is False
        # Optional fields default to None
        assert result["open_switch_entity_id"] is None
        assert result["close_switch_entity_id"] is None
        assert result["stop_switch_entity_id"] is None
        assert result["cover_entity_id"] is None
        assert result["tilting_time_down"] is None
        assert result["tilting_time_up"] is None
        assert result["travel_motor_overhead"] is None
        assert result["tilt_motor_overhead"] is None
        assert result["min_movement_time"] is None

    @pytest.mark.asyncio
    async def test_returns_stored_options(self):
        options = {
            CONF_DEVICE_TYPE: DEVICE_TYPE_COVER,
            CONF_INPUT_MODE: INPUT_MODE_PULSE,
            CONF_PULSE_TIME: 2.5,
            CONF_COVER_ENTITY_ID: "cover.inner",
            CONF_TRAVELLING_TIME_DOWN: 45,
            CONF_TRAVELLING_TIME_UP: 50,
            CONF_TILTING_TIME_DOWN: 3.0,
            CONF_TILTING_TIME_UP: 3.5,
            CONF_TRAVEL_MOVES_WITH_TILT: True,
            CONF_TRAVEL_MOTOR_OVERHEAD: 1.2,
            CONF_TILT_MOTOR_OVERHEAD: 0.8,
            CONF_MIN_MOVEMENT_TIME: 0.5,
        }
        hass, _, entity_reg = _make_hass(options=options)
        conn = _make_connection()

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            await _ws_get_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/get_config",
                    "entity_id": ENTITY_ID,
                },
            )

        result = conn.send_result.call_args[0][1]
        assert result["device_type"] == DEVICE_TYPE_COVER
        assert result["input_mode"] == INPUT_MODE_PULSE
        assert result["pulse_time"] == 2.5
        assert result["cover_entity_id"] == "cover.inner"
        assert result["travelling_time_down"] == 45
        assert result["travelling_time_up"] == 50
        assert result["tilting_time_down"] == 3.0
        assert result["tilting_time_up"] == 3.5
        assert result["travel_moves_with_tilt"] is True
        assert result["travel_motor_overhead"] == 1.2
        assert result["tilt_motor_overhead"] == 0.8
        assert result["min_movement_time"] == 0.5

    @pytest.mark.asyncio
    async def test_error_when_entity_not_found(self):
        hass, _, entity_reg = _make_hass()
        entity_reg.async_get.return_value = None
        conn = _make_connection()

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            await _ws_get_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/get_config",
                    "entity_id": "cover.bad",
                },
            )

        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "not_found"
        conn.send_result.assert_not_called()


# ---------------------------------------------------------------------------
# ws_update_config
# ---------------------------------------------------------------------------


class TestWsUpdateConfig:
    """Tests for ws_update_config WebSocket handler."""

    @pytest.mark.asyncio
    async def test_update_single_field(self):
        hass, config_entry, entity_reg = _make_hass(
            options={CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH}
        )
        conn = _make_connection()

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            await _ws_update_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/update_config",
                    "entity_id": ENTITY_ID,
                    "device_type": DEVICE_TYPE_COVER,
                },
            )

        conn.send_result.assert_called_once_with(1, {"success": True})
        call_kwargs = hass.config_entries.async_update_entry.call_args
        new_options = call_kwargs[1]["options"]
        assert new_options[CONF_DEVICE_TYPE] == DEVICE_TYPE_COVER

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self):
        hass, _, entity_reg = _make_hass(options={})
        conn = _make_connection()

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            await _ws_update_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/update_config",
                    "entity_id": ENTITY_ID,
                    "device_type": DEVICE_TYPE_SWITCH,
                    "input_mode": INPUT_MODE_TOGGLE,
                    "open_switch_entity_id": "switch.up",
                    "close_switch_entity_id": "switch.down",
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_options[CONF_DEVICE_TYPE] == DEVICE_TYPE_SWITCH
        assert new_options[CONF_INPUT_MODE] == INPUT_MODE_TOGGLE
        assert new_options[CONF_OPEN_SWITCH_ENTITY_ID] == "switch.up"
        assert new_options[CONF_CLOSE_SWITCH_ENTITY_ID] == "switch.down"

    @pytest.mark.asyncio
    async def test_null_removes_option(self):
        hass, _, entity_reg = _make_hass(
            options={CONF_STOP_SWITCH_ENTITY_ID: "switch.stop"}
        )
        conn = _make_connection()

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            await _ws_update_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/update_config",
                    "entity_id": ENTITY_ID,
                    "stop_switch_entity_id": None,
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert CONF_STOP_SWITCH_ENTITY_ID not in new_options

    @pytest.mark.asyncio
    async def test_preserves_unmentioned_options(self):
        hass, _, entity_reg = _make_hass(
            options={
                CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
            }
        )
        conn = _make_connection()

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            await _ws_update_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/update_config",
                    "entity_id": ENTITY_ID,
                    "input_mode": INPUT_MODE_PULSE,
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        # Original options preserved
        assert new_options[CONF_DEVICE_TYPE] == DEVICE_TYPE_SWITCH
        assert new_options[CONF_OPEN_SWITCH_ENTITY_ID] == "switch.open"
        assert new_options[CONF_CLOSE_SWITCH_ENTITY_ID] == "switch.close"
        # New option added
        assert new_options[CONF_INPUT_MODE] == INPUT_MODE_PULSE

    @pytest.mark.asyncio
    async def test_error_when_entity_not_found(self):
        hass, _, entity_reg = _make_hass()
        entity_reg.async_get.return_value = None
        conn = _make_connection()

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            await _ws_update_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/update_config",
                    "entity_id": "cover.bad",
                    "device_type": DEVICE_TYPE_COVER,
                },
            )

        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "not_found"
        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_tilt_fields(self):
        hass, _, entity_reg = _make_hass(options={})
        conn = _make_connection()

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            await _ws_update_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/update_config",
                    "entity_id": ENTITY_ID,
                    "tilting_time_down": 5.0,
                    "tilting_time_up": 5.5,
                    "travel_moves_with_tilt": True,
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_options[CONF_TILTING_TIME_DOWN] == 5.0
        assert new_options[CONF_TILTING_TIME_UP] == 5.5
        assert new_options[CONF_TRAVEL_MOVES_WITH_TILT] is True

    @pytest.mark.asyncio
    async def test_clear_tilt_fields(self):
        hass, _, entity_reg = _make_hass(
            options={
                CONF_TILTING_TIME_DOWN: 5.0,
                CONF_TILTING_TIME_UP: 5.0,
                CONF_TRAVEL_MOVES_WITH_TILT: True,
            }
        )
        conn = _make_connection()

        with patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ):
            await _ws_update_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/update_config",
                    "entity_id": ENTITY_ID,
                    "tilting_time_down": None,
                    "tilting_time_up": None,
                    "travel_moves_with_tilt": False,
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert CONF_TILTING_TIME_DOWN not in new_options
        assert CONF_TILTING_TIME_UP not in new_options
        assert new_options[CONF_TRAVEL_MOVES_WITH_TILT] is False


# ---------------------------------------------------------------------------
# async_register_websocket_api
# ---------------------------------------------------------------------------


class TestRegistration:
    """Test that commands are registered correctly."""

    def test_registers_both_commands(self):
        hass = MagicMock()
        with patch(
            "custom_components.cover_time_based.websocket_api.websocket_api.async_register_command"
        ) as mock_register:
            async_register_websocket_api(hass)

        assert mock_register.call_count == 2
        registered_fns = {call[0][1] for call in mock_register.call_args_list}
        assert ws_get_config in registered_fns
        assert ws_update_config in registered_fns
