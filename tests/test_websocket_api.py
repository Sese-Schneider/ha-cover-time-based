"""Tests for the WebSocket API module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.cover_time_based.cover import (
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_COVER_ENTITY_ID,
    CONF_DEVICE_TYPE,
    CONF_INPUT_MODE,
    CONF_MIN_MOVEMENT_TIME,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_TILT_MODE,
    CONF_TILT_STARTUP_DELAY,
    CONF_TILT_TIME_CLOSE,
    CONF_TILT_TIME_OPEN,
    CONF_TRAVEL_STARTUP_DELAY,
    CONF_TRAVEL_TIME_CLOSE,
    CONF_TRAVEL_TIME_OPEN,
    DEFAULT_PULSE_TIME,
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
    ws_raw_command,
    ws_start_calibration,
    ws_stop_calibration,
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
_ws_start_calibration = _unwrap(ws_start_calibration)
_ws_stop_calibration = _unwrap(ws_stop_calibration)
_ws_raw_command = _unwrap(ws_raw_command)


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
        assert result["travel_time_close"] is None
        assert result["travel_time_open"] is None
        assert result["tilt_mode"] == "none"
        # Optional fields default to None
        assert result["open_switch_entity_id"] is None
        assert result["close_switch_entity_id"] is None
        assert result["stop_switch_entity_id"] is None
        assert result["cover_entity_id"] is None
        assert result["tilt_time_close"] is None
        assert result["tilt_time_open"] is None
        assert result["travel_startup_delay"] is None
        assert result["tilt_startup_delay"] is None
        assert result["min_movement_time"] is None

    @pytest.mark.asyncio
    async def test_returns_stored_options(self):
        options = {
            CONF_DEVICE_TYPE: DEVICE_TYPE_COVER,
            CONF_INPUT_MODE: INPUT_MODE_PULSE,
            CONF_PULSE_TIME: 2.5,
            CONF_COVER_ENTITY_ID: "cover.inner",
            CONF_TRAVEL_TIME_CLOSE: 45,
            CONF_TRAVEL_TIME_OPEN: 50,
            CONF_TILT_TIME_CLOSE: 3.0,
            CONF_TILT_TIME_OPEN: 3.5,
            CONF_TILT_MODE: "sequential",
            CONF_TRAVEL_STARTUP_DELAY: 1.2,
            CONF_TILT_STARTUP_DELAY: 0.8,
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
        assert result["travel_time_close"] == 45
        assert result["travel_time_open"] == 50
        assert result["tilt_time_close"] == 3.0
        assert result["tilt_time_open"] == 3.5
        assert result["tilt_mode"] == "sequential"
        assert result["travel_startup_delay"] == 1.2
        assert result["tilt_startup_delay"] == 0.8
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
# Dual-motor field round-tripping
# ---------------------------------------------------------------------------


class TestDualMotorFieldRoundTrip:
    """Test that dual-motor fields are returned in get_config and saved in update_config."""

    @pytest.fixture
    def config_entry_with_dual_motor(self):
        """Config entry with dual_motor options set."""
        entry = MagicMock()
        entry.entry_id = ENTRY_ID
        entry.domain = DOMAIN
        entry.options = {
            "device_type": "switch",
            "input_mode": "switch",
            "tilt_mode": "dual_motor",
            "safe_tilt_position": 10,
            "max_tilt_allowed_position": 80,
            "tilt_open_switch": "switch.tilt_open",
            "tilt_close_switch": "switch.tilt_close",
            "tilt_stop_switch": "switch.tilt_stop",
        }
        return entry

    @pytest.mark.asyncio
    async def test_get_config_returns_dual_motor_fields(
        self, config_entry_with_dual_motor
    ):
        hass = MagicMock()
        connection = MagicMock()
        msg = {"id": 1, "type": "cover_time_based/get_config", "entity_id": ENTITY_ID}

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry_with_dual_motor, None),
        ):
            handler = _unwrap(ws_get_config)
            await handler(hass, connection, msg)

        result = connection.send_result.call_args[0][1]
        assert result["safe_tilt_position"] == 10
        assert result["max_tilt_allowed_position"] == 80
        assert result["tilt_open_switch"] == "switch.tilt_open"
        assert result["tilt_close_switch"] == "switch.tilt_close"
        assert result["tilt_stop_switch"] == "switch.tilt_stop"

    @pytest.mark.asyncio
    async def test_update_config_saves_dual_motor_fields(self):
        hass = MagicMock()
        connection = MagicMock()
        config_entry = MagicMock()
        config_entry.options = {"tilt_mode": "dual_motor"}
        config_entry.domain = DOMAIN

        msg = {
            "id": 2,
            "type": "cover_time_based/update_config",
            "entity_id": ENTITY_ID,
            "safe_tilt_position": 15,
            "max_tilt_allowed_position": 90,
            "tilt_open_switch": "switch.tilt_up",
            "tilt_close_switch": "switch.tilt_down",
            "tilt_stop_switch": "switch.tilt_stop",
        }

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry, None),
        ):
            handler = _unwrap(ws_update_config)
            await handler(hass, connection, msg)

        new_opts = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_opts["safe_tilt_position"] == 15
        assert new_opts["max_tilt_allowed_position"] == 90
        assert new_opts["tilt_open_switch"] == "switch.tilt_up"
        assert new_opts["tilt_close_switch"] == "switch.tilt_down"
        assert new_opts["tilt_stop_switch"] == "switch.tilt_stop"

    @pytest.mark.asyncio
    async def test_get_config_defaults_for_missing_dual_motor_fields(self):
        """When dual_motor fields aren't in options, get_config returns sensible defaults."""
        hass = MagicMock()
        connection = MagicMock()
        config_entry = MagicMock()
        config_entry.entry_id = ENTRY_ID
        config_entry.domain = DOMAIN
        config_entry.options = {"tilt_mode": "sequential"}
        msg = {"id": 1, "type": "cover_time_based/get_config", "entity_id": ENTITY_ID}

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry, None),
        ):
            handler = _unwrap(ws_get_config)
            await handler(hass, connection, msg)

        result = connection.send_result.call_args[0][1]
        assert result["safe_tilt_position"] == 100  # HA default: fully open
        assert result["max_tilt_allowed_position"] is None
        assert result["tilt_open_switch"] is None
        assert result["tilt_close_switch"] is None
        assert result["tilt_stop_switch"] is None


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
                    "tilt_time_close": 5.0,
                    "tilt_time_open": 5.5,
                    "tilt_mode": "sequential",
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_options[CONF_TILT_TIME_CLOSE] == 5.0
        assert new_options[CONF_TILT_TIME_OPEN] == 5.5
        assert new_options[CONF_TILT_MODE] == "sequential"

    @pytest.mark.asyncio
    async def test_clear_tilt_fields(self):
        hass, _, entity_reg = _make_hass(
            options={
                CONF_TILT_TIME_CLOSE: 5.0,
                CONF_TILT_TIME_OPEN: 5.0,
                CONF_TILT_MODE: "sequential",
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
                    "tilt_time_close": None,
                    "tilt_time_open": None,
                    "tilt_mode": "none",
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert CONF_TILT_TIME_CLOSE not in new_options
        assert CONF_TILT_TIME_OPEN not in new_options
        assert new_options[CONF_TILT_MODE] == "none"


# ---------------------------------------------------------------------------
# ws_update_config — wrap-self rejection
# ---------------------------------------------------------------------------


class TestWsUpdateConfigWrappedSelf:
    """Test that ws_update_config rejects wrapping another CTB entity."""

    @pytest.mark.asyncio
    async def test_rejects_wrapping_ctb_entity(self):
        hass, config_entry, entity_reg = _make_hass(options={})
        conn = _make_connection()

        # Target entity belongs to cover_time_based
        target_entry = MagicMock()
        target_entry.platform = DOMAIN

        entity_reg_for_update = MagicMock()
        entity_reg_for_update.async_get.side_effect = lambda eid: (
            target_entry if eid == "cover.other_ctb" else entity_reg.async_get(eid)
        )

        with (
            patch(
                "custom_components.cover_time_based.websocket_api._resolve_config_entry",
                return_value=(config_entry, None),
            ),
            patch(
                "custom_components.cover_time_based.websocket_api.er.async_get",
                return_value=entity_reg_for_update,
            ),
        ):
            await _ws_update_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/update_config",
                    "entity_id": ENTITY_ID,
                    "cover_entity_id": "cover.other_ctb",
                },
            )

        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "invalid_entity"
        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_wrapping_non_ctb_entity(self):
        hass, config_entry, _ = _make_hass(options={})
        conn = _make_connection()

        target_entry = MagicMock()
        target_entry.platform = "other_integration"

        entity_reg_for_update = MagicMock()
        entity_reg_for_update.async_get.return_value = target_entry

        with (
            patch(
                "custom_components.cover_time_based.websocket_api._resolve_config_entry",
                return_value=(config_entry, None),
            ),
            patch(
                "custom_components.cover_time_based.websocket_api.er.async_get",
                return_value=entity_reg_for_update,
            ),
        ):
            await _ws_update_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/update_config",
                    "entity_id": ENTITY_ID,
                    "cover_entity_id": "cover.other",
                },
            )

        conn.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_allows_update_without_cover_entity_id(self):
        hass, config_entry, _ = _make_hass(options={})
        conn = _make_connection()

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry, None),
        ):
            await _ws_update_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/update_config",
                    "entity_id": ENTITY_ID,
                    "device_type": DEVICE_TYPE_SWITCH,
                },
            )

        conn.send_result.assert_called_once()


# ---------------------------------------------------------------------------
# ws_start_calibration
# ---------------------------------------------------------------------------


class TestWsStartCalibration:
    """Tests for ws_start_calibration handler."""

    @pytest.mark.asyncio
    async def test_entity_not_found(self):
        hass = MagicMock()
        conn = _make_connection()

        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=None,
        ):
            await _ws_start_calibration(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/start_calibration",
                    "entity_id": ENTITY_ID,
                    "attribute": "travel_time_close",
                    "timeout": 60,
                },
            )

        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "not_found"

    @pytest.mark.asyncio
    async def test_success(self):
        hass = MagicMock()
        conn = _make_connection()
        entity = MagicMock()
        entity.start_calibration = AsyncMock()

        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_start_calibration(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/start_calibration",
                    "entity_id": ENTITY_ID,
                    "attribute": "travel_time_close",
                    "timeout": 60,
                },
            )

        entity.start_calibration.assert_awaited_once_with(
            attribute="travel_time_close", timeout=60
        )
        conn.send_result.assert_called_once_with(1, {"success": True})

    @pytest.mark.asyncio
    async def test_with_direction(self):
        hass = MagicMock()
        conn = _make_connection()
        entity = MagicMock()
        entity.start_calibration = AsyncMock()

        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_start_calibration(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/start_calibration",
                    "entity_id": ENTITY_ID,
                    "attribute": "travel_time_close",
                    "timeout": 60,
                    "direction": "close",
                },
            )

        call_kwargs = entity.start_calibration.call_args[1]
        assert call_kwargs["direction"] == "close"

    @pytest.mark.asyncio
    async def test_exception(self):
        hass = MagicMock()
        conn = _make_connection()
        entity = MagicMock()
        entity.start_calibration = AsyncMock(
            side_effect=Exception("already in progress")
        )

        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_start_calibration(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/start_calibration",
                    "entity_id": ENTITY_ID,
                    "attribute": "travel_time_close",
                    "timeout": 60,
                },
            )

        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "failed"


# ---------------------------------------------------------------------------
# ws_stop_calibration
# ---------------------------------------------------------------------------


class TestWsStopCalibration:
    """Tests for ws_stop_calibration handler."""

    @pytest.mark.asyncio
    async def test_entity_not_found(self):
        hass = MagicMock()
        conn = _make_connection()

        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=None,
        ):
            await _ws_stop_calibration(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/stop_calibration",
                    "entity_id": ENTITY_ID,
                    "cancel": False,
                },
            )

        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "not_found"

    @pytest.mark.asyncio
    async def test_success(self):
        hass = MagicMock()
        conn = _make_connection()
        entity = MagicMock()
        entity.stop_calibration = AsyncMock(
            return_value={"attribute": "travel_time_close", "value": 45.0}
        )

        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_stop_calibration(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/stop_calibration",
                    "entity_id": ENTITY_ID,
                    "cancel": False,
                },
            )

        conn.send_result.assert_called_once()
        result = conn.send_result.call_args[0][1]
        assert result["attribute"] == "travel_time_close"
        assert result["value"] == 45.0

    @pytest.mark.asyncio
    async def test_exception(self):
        hass = MagicMock()
        conn = _make_connection()
        entity = MagicMock()
        entity.stop_calibration = AsyncMock(side_effect=Exception("no calibration"))

        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_stop_calibration(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/stop_calibration",
                    "entity_id": ENTITY_ID,
                    "cancel": False,
                },
            )

        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "failed"


# ---------------------------------------------------------------------------
# ws_raw_command
# ---------------------------------------------------------------------------


class TestWsRawCommand:
    """Tests for ws_raw_command handler."""

    def _make_entity(self, *, has_tilt_motor=False):
        entity = MagicMock()
        entity._send_open = AsyncMock()
        entity._send_close = AsyncMock()
        entity._send_stop = AsyncMock()
        entity._send_tilt_open = AsyncMock()
        entity._send_tilt_close = AsyncMock()
        entity._send_tilt_stop = AsyncMock()
        entity._has_tilt_motor = MagicMock(return_value=has_tilt_motor)
        return entity

    def _msg(self, command):
        return {
            "id": 1,
            "type": "cover_time_based/raw_command",
            "entity_id": ENTITY_ID,
            "command": command,
        }

    @pytest.mark.asyncio
    async def test_entity_not_found(self):
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=None,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("open"))
        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "not_found"

    @pytest.mark.asyncio
    async def test_open(self):
        entity = self._make_entity()
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("open"))
        entity._send_open.assert_awaited_once()
        conn.send_result.assert_called_once_with(1, {"success": True})

    @pytest.mark.asyncio
    async def test_close(self):
        entity = self._make_entity()
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("close"))
        entity._send_close.assert_awaited_once()
        conn.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop(self):
        entity = self._make_entity()
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("stop"))
        entity._send_stop.assert_awaited_once()
        conn.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_tilt_open(self):
        entity = self._make_entity(has_tilt_motor=True)
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("tilt_open"))
        entity._send_tilt_open.assert_awaited_once()
        conn.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_tilt_open_not_supported(self):
        entity = self._make_entity(has_tilt_motor=False)
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("tilt_open"))
        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "not_supported"

    @pytest.mark.asyncio
    async def test_tilt_close(self):
        entity = self._make_entity(has_tilt_motor=True)
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("tilt_close"))
        entity._send_tilt_close.assert_awaited_once()
        conn.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_tilt_close_not_supported(self):
        entity = self._make_entity(has_tilt_motor=False)
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("tilt_close"))
        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "not_supported"

    @pytest.mark.asyncio
    async def test_tilt_stop(self):
        entity = self._make_entity(has_tilt_motor=True)
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("tilt_stop"))
        entity._send_tilt_stop.assert_awaited_once()
        conn.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_tilt_stop_not_supported(self):
        entity = self._make_entity(has_tilt_motor=False)
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("tilt_stop"))
        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "not_supported"

    @pytest.mark.asyncio
    async def test_exception(self):
        entity = self._make_entity()
        entity._send_open = AsyncMock(side_effect=Exception("hw error"))
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("open"))
        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "failed"


# ---------------------------------------------------------------------------
# resolve_entity_or_none (from helpers, returns None on error)
# ---------------------------------------------------------------------------


class TestWsResolveEntity:
    """Test resolve_entity_or_none from helpers.py."""

    def test_returns_none_no_component(self):
        from custom_components.cover_time_based.helpers import resolve_entity_or_none

        hass = MagicMock()
        hass.data = {}
        assert resolve_entity_or_none(hass, "cover.test") is None

    def test_returns_none_entity_not_found(self):
        from custom_components.cover_time_based.helpers import resolve_entity_or_none

        component = MagicMock()
        component.get_entity.return_value = None
        hass = MagicMock()
        hass.data = {"entity_components": {"cover": component}}
        assert resolve_entity_or_none(hass, "cover.test") is None

    def test_returns_none_wrong_type(self):
        from custom_components.cover_time_based.helpers import resolve_entity_or_none

        component = MagicMock()
        component.get_entity.return_value = MagicMock()  # not CoverTimeBased
        hass = MagicMock()
        hass.data = {"entity_components": {"cover": component}}
        assert resolve_entity_or_none(hass, "cover.test") is None

    def test_returns_entity_when_valid(self):
        from custom_components.cover_time_based.helpers import resolve_entity_or_none
        from custom_components.cover_time_based.cover import _create_cover_from_options

        entity = _create_cover_from_options(
            {
                "device_type": "switch",
                "open_switch_entity_id": "switch.open",
                "close_switch_entity_id": "switch.close",
                "input_mode": "switch",
                "travel_time_close": 30,
                "travel_time_open": 30,
            },
            device_id="test",
            name="Test",
        )
        component = MagicMock()
        component.get_entity.return_value = entity
        hass = MagicMock()
        hass.data = {"entity_components": {"cover": component}}

        result = resolve_entity_or_none(hass, "cover.test")
        assert result is entity


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

        assert mock_register.call_count == 5
        registered_fns = {call[0][1] for call in mock_register.call_args_list}
        assert ws_get_config in registered_fns
        assert ws_update_config in registered_fns
        assert ws_start_calibration in registered_fns
        assert ws_stop_calibration in registered_fns
        assert ws_raw_command in registered_fns
