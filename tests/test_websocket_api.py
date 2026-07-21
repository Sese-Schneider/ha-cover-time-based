"""Tests for the WebSocket API module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.cover_time_based.cover import (
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_CONTROL_MODE,
    CONF_COVER_ENTITY_ID,
    CONF_DIRECTION_CHANGE_DELAY,
    CONF_FORCE_ENDPOINT_REDRIVE,
    CONF_IGNORE_REPORTED_POSITION,
    CONF_INVERT,
    CONF_MIN_MOVEMENT_TIME,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_RELAY_REPORTS_OFF,
    CONF_REPORTS_COMMAND_NOT_ENDPOINT,
    CONF_SEND_ENDPOINT_STOP,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_TILT_CLOSE_SWITCH,
    CONF_TILT_MODE,
    CONF_TILT_OPEN_SWITCH,
    CONF_TILT_STARTUP_DELAY,
    CONF_TILT_STOP_SWITCH,
    CONF_TILT_TIME_CLOSE,
    CONF_TILT_TIME_OPEN,
    CONF_TRAVEL_STARTUP_DELAY,
    CONF_TRAVEL_TIME_CLOSE,
    CONF_TRAVEL_TIME_OPEN,
    CONTROL_MODE_PULSE,
    CONTROL_MODE_SWITCH,
    CONTROL_MODE_TOGGLE,
    CONTROL_MODE_TOGGLE_OPPOSITE,
    CONTROL_MODE_WRAPPED,
    DEFAULT_PULSE_TIME,
)
from custom_components.cover_time_based.websocket_api import (
    _resolve_config_entry,
    _script_in_non_pulse_mode,
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
        assert result["control_mode"] == CONTROL_MODE_SWITCH
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
            CONF_CONTROL_MODE: CONTROL_MODE_WRAPPED,
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
        assert result["control_mode"] == CONTROL_MODE_WRAPPED
        assert result["pulse_time"] == 2.5
        assert result["cover_entity_id"] == "cover.inner"
        assert result["travel_time_close"] == 45
        assert result["travel_time_open"] == 50
        assert result["tilt_time_close"] == 3.0
        assert result["tilt_time_open"] == 3.5
        # Legacy "sequential" is normalized to "sequential_close" in the
        # GET response so the frontend (which no longer has dropdown/hint
        # keys for the legacy string) always sees the canonical name.
        assert result["tilt_mode"] == "sequential_close"
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


class TestIgnoreReportedPositionRoundTrip:
    """ignore_reported_position is returned in get_config and saved in update_config."""

    @pytest.mark.asyncio
    async def test_get_config_defaults_to_false(self):
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

        result = conn.send_result.call_args[0][1]
        assert result["ignore_reported_position"] is False

    @pytest.mark.asyncio
    async def test_get_config_returns_stored_true(self):
        hass, _, entity_reg = _make_hass(
            options={
                CONF_CONTROL_MODE: CONTROL_MODE_WRAPPED,
                CONF_COVER_ENTITY_ID: "cover.inner",
                CONF_IGNORE_REPORTED_POSITION: True,
            }
        )
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
        assert result["ignore_reported_position"] is True

    @pytest.mark.asyncio
    async def test_update_config_saves_true(self):
        hass, _, entity_reg = _make_hass(
            options={CONF_CONTROL_MODE: CONTROL_MODE_WRAPPED}
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
                    "ignore_reported_position": True,
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_options[CONF_IGNORE_REPORTED_POSITION] is True


class TestForceTimeBasedPositionRoundTrip:
    """force_time_based_position is returned in get_config and saved in update_config."""

    @pytest.mark.asyncio
    async def test_get_config_defaults_to_false(self):
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

        result = conn.send_result.call_args[0][1]
        assert result["force_time_based_position"] is False

    @pytest.mark.asyncio
    async def test_get_config_returns_stored_true(self):
        from custom_components.cover_time_based.const import (
            CONF_FORCE_TIME_BASED_POSITION,
        )

        hass, _, entity_reg = _make_hass(
            options={
                CONF_CONTROL_MODE: CONTROL_MODE_WRAPPED,
                CONF_COVER_ENTITY_ID: "cover.inner",
                CONF_FORCE_TIME_BASED_POSITION: True,
            }
        )
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
        assert result["force_time_based_position"] is True

    @pytest.mark.asyncio
    async def test_update_config_saves_true(self):
        from custom_components.cover_time_based.const import (
            CONF_FORCE_TIME_BASED_POSITION,
        )

        hass, _, entity_reg = _make_hass(
            options={CONF_CONTROL_MODE: CONTROL_MODE_WRAPPED}
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
                    "force_time_based_position": True,
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_options[CONF_FORCE_TIME_BASED_POSITION] is True


class TestRelayReportsOffRoundTrip:
    """relay_reports_off is returned in get_config and saved in update_config."""

    @pytest.mark.asyncio
    async def test_get_config_defaults_to_true(self):
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

        result = conn.send_result.call_args[0][1]
        assert result["relay_reports_off"] is True

    @pytest.mark.asyncio
    async def test_get_config_returns_stored_false(self):
        hass, _, entity_reg = _make_hass(
            options={
                CONF_CONTROL_MODE: CONTROL_MODE_TOGGLE,
                CONF_RELAY_REPORTS_OFF: False,
            }
        )
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
        assert result["relay_reports_off"] is False

    @pytest.mark.asyncio
    async def test_update_config_saves_false(self):
        hass, _, entity_reg = _make_hass(
            options={CONF_CONTROL_MODE: CONTROL_MODE_TOGGLE}
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
                    "relay_reports_off": False,
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_options[CONF_RELAY_REPORTS_OFF] is False


class TestSendEndpointStopRoundTrip:
    """send_endpoint_stop is returned in get_config and saved in update_config."""

    @pytest.mark.asyncio
    async def test_get_config_defaults_to_true(self):
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

        result = conn.send_result.call_args[0][1]
        assert result["send_endpoint_stop"] is True

    @pytest.mark.asyncio
    async def test_get_config_returns_stored_false(self):
        hass, _, entity_reg = _make_hass(
            options={
                CONF_CONTROL_MODE: CONTROL_MODE_PULSE,
                CONF_SEND_ENDPOINT_STOP: False,
            }
        )
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
        assert result["send_endpoint_stop"] is False

    @pytest.mark.asyncio
    async def test_update_config_saves_false(self):
        hass, _, entity_reg = _make_hass(
            options={CONF_CONTROL_MODE: CONTROL_MODE_PULSE}
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
                    "send_endpoint_stop": False,
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_options[CONF_SEND_ENDPOINT_STOP] is False


class TestAssumedStateRoundTrip:
    """assumed_state is returned in get_config and saved in update_config."""

    @pytest.mark.asyncio
    async def test_get_config_defaults_to_true(self):
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

        result = conn.send_result.call_args[0][1]
        assert result["assumed_state"] is True

    @pytest.mark.asyncio
    async def test_get_config_returns_stored_false(self):
        from custom_components.cover_time_based.const import CONF_ASSUMED_STATE

        hass, _, entity_reg = _make_hass(
            options={
                CONF_CONTROL_MODE: CONTROL_MODE_SWITCH,
                CONF_ASSUMED_STATE: False,
            }
        )
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
        assert result["assumed_state"] is False

    @pytest.mark.asyncio
    async def test_update_config_saves_false(self):
        from custom_components.cover_time_based.const import CONF_ASSUMED_STATE

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
                    "assumed_state": False,
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_options[CONF_ASSUMED_STATE] is False


class TestDualMotorFieldRoundTrip:
    """Test that dual-motor fields are returned in get_config and saved in update_config."""

    @pytest.fixture
    def config_entry_with_dual_motor(self):
        """Config entry with dual_motor options set."""
        entry = MagicMock()
        entry.entry_id = ENTRY_ID
        entry.domain = DOMAIN
        entry.options = {
            "control_mode": "switch",
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

    @pytest.mark.asyncio
    async def test_update_config_normalizes_legacy_sequential(self):
        """Writing tilt_mode='sequential' rewrites to 'sequential_close' on
        persist — the frontend no longer has dropdown/hint keys for the
        legacy string."""
        hass = MagicMock()
        connection = MagicMock()
        config_entry = MagicMock()
        config_entry.options = {}
        config_entry.domain = DOMAIN

        msg = {
            "id": 4,
            "type": "cover_time_based/update_config",
            "entity_id": ENTITY_ID,
            "tilt_mode": "sequential",
        }

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry, None),
        ):
            handler = _unwrap(ws_update_config)
            await handler(hass, connection, msg)

        new_opts = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_opts["tilt_mode"] == "sequential_close"

    @pytest.mark.asyncio
    async def test_get_config_normalizes_legacy_sequential(self):
        """Stored legacy 'sequential' (from an entry that somehow escaped
        migration) is surfaced to the UI as 'sequential_close'."""
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
        assert result["tilt_mode"] == "sequential_close"


# ---------------------------------------------------------------------------
# ws_update_config
# ---------------------------------------------------------------------------


class TestWsUpdateConfig:
    """Tests for ws_update_config WebSocket handler."""

    @pytest.mark.asyncio
    async def test_update_single_field(self):
        hass, config_entry, entity_reg = _make_hass(
            options={CONF_CONTROL_MODE: CONTROL_MODE_SWITCH}
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
                    "control_mode": CONTROL_MODE_WRAPPED,
                },
            )

        conn.send_result.assert_called_once_with(1, {"success": True})
        call_kwargs = hass.config_entries.async_update_entry.call_args
        new_options = call_kwargs[1]["options"]
        assert new_options[CONF_CONTROL_MODE] == CONTROL_MODE_WRAPPED

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
                    "control_mode": CONTROL_MODE_TOGGLE,
                    "open_switch_entity_id": "switch.up",
                    "close_switch_entity_id": "switch.down",
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_options[CONF_CONTROL_MODE] == CONTROL_MODE_TOGGLE
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
                CONF_CONTROL_MODE: CONTROL_MODE_SWITCH,
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                CONF_STOP_SWITCH_ENTITY_ID: "switch.stop",
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
                    "control_mode": CONTROL_MODE_PULSE,
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        # Original options preserved
        assert new_options[CONF_OPEN_SWITCH_ENTITY_ID] == "switch.open"
        assert new_options[CONF_CLOSE_SWITCH_ENTITY_ID] == "switch.close"
        assert new_options[CONF_STOP_SWITCH_ENTITY_ID] == "switch.stop"
        # New option added
        assert new_options[CONF_CONTROL_MODE] == CONTROL_MODE_PULSE

    @pytest.mark.asyncio
    async def test_pulse_mode_accepted_with_stop_switch(self):
        """Pulse mode with a stop switch should be accepted."""
        hass, _, entity_reg = _make_hass(
            options={
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                CONF_STOP_SWITCH_ENTITY_ID: "switch.stop",
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
                    "control_mode": CONTROL_MODE_PULSE,
                },
            )

        conn.send_result.assert_called_once()
        hass.config_entries.async_update_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_switch_mode_does_not_require_stop_switch(self):
        """Switch mode without a stop switch should be accepted."""
        hass, _, entity_reg = _make_hass(
            options={
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
                    "control_mode": CONTROL_MODE_SWITCH,
                },
            )

        conn.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_toggle_mode_does_not_require_stop_switch(self):
        """Toggle mode without a stop switch should be accepted."""
        hass, _, entity_reg = _make_hass(
            options={
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
                    "control_mode": CONTROL_MODE_TOGGLE,
                },
            )

        conn.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_pulse_mode_accepted_with_tilt_stop_switch(self):
        """Pulse mode with dual_motor tilt and tilt stop switch should be accepted."""
        hass, _, entity_reg = _make_hass(
            options={
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                CONF_STOP_SWITCH_ENTITY_ID: "switch.stop",
                CONF_CONTROL_MODE: CONTROL_MODE_PULSE,
                CONF_TILT_MODE: "dual_motor",
                CONF_TILT_OPEN_SWITCH: "switch.tilt_open",
                CONF_TILT_CLOSE_SWITCH: "switch.tilt_close",
                CONF_TILT_STOP_SWITCH: "switch.tilt_stop",
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
                },
            )

        conn.send_result.assert_called_once()
        hass.config_entries.async_update_entry.assert_called_once()

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
                    "control_mode": CONTROL_MODE_WRAPPED,
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
                    "tilt_mode": "sequential_close",
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_options[CONF_TILT_TIME_CLOSE] == 5.0
        assert new_options[CONF_TILT_TIME_OPEN] == 5.5
        assert new_options[CONF_TILT_MODE] == "sequential_close"

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
# ws_update_config — tilt_mode schema validation
# ---------------------------------------------------------------------------


class TestTiltModeSchemaValidation:
    """Verify the update_config schema accepts all tilt_mode variants the UI emits."""

    @pytest.mark.parametrize(
        "tilt_mode",
        [
            "none",
            "sequential_close",
            "sequential_open",
            "sequential",  # legacy alias retained as defense in depth
            "dual_motor",
            "inline",
        ],
    )
    def test_valid_tilt_modes_accepted(self, tilt_mode):
        """Each valid tilt_mode string must pass schema validation."""
        schema = ws_update_config._ws_schema
        result = schema(
            {
                "id": 1,
                "type": "cover_time_based/update_config",
                "entity_id": ENTITY_ID,
                "tilt_mode": tilt_mode,
            }
        )
        assert result["tilt_mode"] == tilt_mode

    def test_invalid_tilt_mode_rejected(self):
        """Unknown tilt_mode strings must fail schema validation."""
        import voluptuous as vol

        schema = ws_update_config._ws_schema
        with pytest.raises(vol.Invalid):
            schema(
                {
                    "id": 1,
                    "type": "cover_time_based/update_config",
                    "entity_id": ENTITY_ID,
                    "tilt_mode": "bogus_mode",
                }
            )


class TestControlModeSchemaValidation:
    """Verify the update_config schema accepts the toggle_opposite control mode."""

    def test_toggle_opposite_accepted(self):
        """toggle_opposite must pass schema validation for control_mode."""
        schema = ws_update_config._ws_schema
        result = schema(
            {
                "id": 1,
                "type": "cover_time_based/update_config",
                "entity_id": ENTITY_ID,
                "control_mode": CONTROL_MODE_TOGGLE_OPPOSITE,
            }
        )
        assert result["control_mode"] == CONTROL_MODE_TOGGLE_OPPOSITE


# ---------------------------------------------------------------------------
# ws_update_config — timing field validation
# ---------------------------------------------------------------------------


class TestTimingFieldValidation:
    """Verify that travel/tilt time fields reject 0 (min 0.1) while delay fields allow it."""

    @pytest.mark.parametrize(
        "field",
        ["travel_time_close", "travel_time_open", "tilt_time_close", "tilt_time_open"],
    )
    def test_zero_rejected_for_travel_tilt_times(self, field):
        """travel_time_* and tilt_time_* require >= 0.1."""
        import voluptuous as vol

        validator = vol.All(vol.Coerce(float), vol.Range(min=0.1, max=600))
        with pytest.raises(vol.Invalid):
            validator(0)
        # 0.1 must be accepted
        assert validator(0.1) == pytest.approx(0.1)

    @pytest.mark.parametrize(
        "field",
        [
            "travel_startup_delay",
            "tilt_startup_delay",
            "endpoint_runon_time",
            "min_movement_time",
        ],
    )
    def test_zero_accepted_for_delay_fields(self, field):
        """Delay and auxiliary timing fields allow 0."""
        import voluptuous as vol

        validator = vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        assert validator(0) == pytest.approx(0)


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
                    "control_mode": CONTROL_MODE_SWITCH,
                },
            )

        conn.send_result.assert_called_once()


class TestWsUpdateConfigCalibrationGuard:
    """ws_update_config must reject saves while a calibration is running.

    A card save reloads the config entry (async_update_entry triggers a
    reload), and a reload mid-calibration destroys the session. Reject the
    save instead.
    """

    @pytest.mark.asyncio
    async def test_rejects_when_calibration_active(self):
        hass, config_entry, _ = _make_hass(
            options={CONF_CONTROL_MODE: CONTROL_MODE_SWITCH}
        )
        conn = _make_connection()
        entity = MagicMock()
        entity._calibration = MagicMock()  # not None — calibration active

        with (
            patch(
                "custom_components.cover_time_based.websocket_api._resolve_config_entry",
                return_value=(config_entry, None),
            ),
            patch(
                "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
                return_value=entity,
            ),
        ):
            await _ws_update_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/update_config",
                    "entity_id": ENTITY_ID,
                    "control_mode": CONTROL_MODE_WRAPPED,
                },
            )

        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "calibration_active"
        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_when_no_calibration_active(self):
        hass, config_entry, _ = _make_hass(
            options={CONF_CONTROL_MODE: CONTROL_MODE_SWITCH}
        )
        conn = _make_connection()
        entity = MagicMock()
        entity._calibration = None

        with (
            patch(
                "custom_components.cover_time_based.websocket_api._resolve_config_entry",
                return_value=(config_entry, None),
            ),
            patch(
                "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
                return_value=entity,
            ),
        ):
            await _ws_update_config(
                hass,
                conn,
                {
                    "id": 1,
                    "type": "cover_time_based/update_config",
                    "entity_id": ENTITY_ID,
                    "control_mode": CONTROL_MODE_WRAPPED,
                },
            )

        conn.send_result.assert_called_once_with(1, {"success": True})
        hass.config_entries.async_update_entry.assert_called_once()


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

    def _make_entity(self, *, has_tilt_motor=False, has_tilt_support=False):
        entity = MagicMock()
        entity._raw_direction_command = AsyncMock()
        entity._has_tilt_motor = MagicMock(return_value=has_tilt_motor)
        entity._has_tilt_support = MagicMock(return_value=has_tilt_support)
        entity._calibration = None
        entity._cancel_startup_delay_task = MagicMock()
        entity._cancel_delay_task = MagicMock()
        entity._handle_stop = MagicMock()
        entity.travel_calc = MagicMock()
        entity.tilt_calc = MagicMock()
        entity.async_write_ha_state = MagicMock()
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
        entity._raw_direction_command.assert_awaited_once_with("open")
        entity.travel_calc.clear_position.assert_called_once()
        entity.async_write_ha_state.assert_called_once()
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
        entity._raw_direction_command.assert_awaited_once_with("close")
        entity.travel_calc.clear_position.assert_called_once()
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
        entity._raw_direction_command.assert_awaited_once_with("stop")
        entity.travel_calc.clear_position.assert_called_once()
        conn.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_tilt_open(self):
        entity = self._make_entity(has_tilt_motor=True, has_tilt_support=True)
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("tilt_open"))
        entity._raw_direction_command.assert_awaited_once_with("tilt_open")
        entity.tilt_calc.clear_position.assert_called_once()
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
        entity = self._make_entity(has_tilt_motor=True, has_tilt_support=True)
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("tilt_close"))
        entity._raw_direction_command.assert_awaited_once_with("tilt_close")
        entity.tilt_calc.clear_position.assert_called_once()
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
        entity = self._make_entity(has_tilt_motor=True, has_tilt_support=True)
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("tilt_stop"))
        entity._raw_direction_command.assert_awaited_once_with("tilt_stop")
        entity.tilt_calc.clear_position.assert_called_once()
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
    async def test_lifecycle_stop_called(self):
        entity = self._make_entity()
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("open"))
        entity._cancel_startup_delay_task.assert_called_once()
        entity._cancel_delay_task.assert_called_once()
        entity._handle_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_calibration_skips_lifecycle_and_clear(self):
        entity = self._make_entity()
        entity._calibration = MagicMock()  # not None — calibration active
        conn = _make_connection()
        with patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=entity,
        ):
            await _ws_raw_command(MagicMock(), conn, self._msg("open"))
        # Command still dispatched
        entity._raw_direction_command.assert_awaited_once_with("open")
        # But lifecycle stop and position clear are skipped
        entity._cancel_startup_delay_task.assert_not_called()
        entity._cancel_delay_task.assert_not_called()
        entity._handle_stop.assert_not_called()
        entity.travel_calc.clear_position.assert_not_called()
        entity.async_write_ha_state.assert_not_called()
        conn.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception(self):
        entity = self._make_entity()
        entity._raw_direction_command = AsyncMock(side_effect=Exception("hw error"))
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
                "control_mode": "switch",
                "open_switch_entity_id": "switch.open",
                "close_switch_entity_id": "switch.close",
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


# ---------------------------------------------------------------------------
# close_includes_tilt field round-tripping
# ---------------------------------------------------------------------------


class TestCloseIncludesTiltFieldRoundTrip:
    """get_config returns the value (defaulting to True); update_config persists it."""

    @pytest.mark.asyncio
    async def test_get_config_returns_default_true_when_unset(self):
        hass = MagicMock()
        connection = MagicMock()
        entry = MagicMock()
        entry.entry_id = ENTRY_ID
        entry.domain = DOMAIN
        entry.options = {"tilt_mode": "sequential_close"}
        msg = {"id": 1, "type": "cover_time_based/get_config", "entity_id": ENTITY_ID}

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(entry, None),
        ):
            handler = _unwrap(ws_get_config)
            await handler(hass, connection, msg)

        result = connection.send_result.call_args[0][1]
        assert result["close_includes_tilt"] is True

    @pytest.mark.asyncio
    async def test_get_config_returns_stored_false(self):
        hass = MagicMock()
        connection = MagicMock()
        entry = MagicMock()
        entry.entry_id = ENTRY_ID
        entry.domain = DOMAIN
        entry.options = {
            "tilt_mode": "sequential_close",
            "close_includes_tilt": False,
        }
        msg = {"id": 1, "type": "cover_time_based/get_config", "entity_id": ENTITY_ID}

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(entry, None),
        ):
            handler = _unwrap(ws_get_config)
            await handler(hass, connection, msg)

        result = connection.send_result.call_args[0][1]
        assert result["close_includes_tilt"] is False

    @pytest.mark.asyncio
    async def test_update_config_persists_close_includes_tilt(self):
        hass = MagicMock()
        connection = MagicMock()
        config_entry = MagicMock()
        config_entry.options = {"tilt_mode": "dual_motor"}
        config_entry.domain = DOMAIN

        msg = {
            "id": 2,
            "type": "cover_time_based/update_config",
            "entity_id": ENTITY_ID,
            "close_includes_tilt": False,
        }

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry, None),
        ):
            handler = _unwrap(ws_update_config)
            await handler(hass, connection, msg)

        new_opts = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_opts["close_includes_tilt"] is False

    @pytest.mark.asyncio
    async def test_update_config_accepts_null_to_clear(self):
        """Frontend sends close_includes_tilt=null when switching tilt_mode
        away from sequential_close/dual_motor. Schema must accept None and
        the handler must drop the stored option."""
        hass = MagicMock()
        connection = MagicMock()
        config_entry = MagicMock()
        config_entry.options = {
            "tilt_mode": "sequential_close",
            "close_includes_tilt": False,
        }
        config_entry.domain = DOMAIN

        msg = {
            "id": 3,
            "type": "cover_time_based/update_config",
            "entity_id": ENTITY_ID,
            "close_includes_tilt": None,
        }

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry, None),
        ):
            handler = _unwrap(ws_update_config)
            await handler(hass, connection, msg)

        # send_error must NOT have been called (the bug was schema rejection)
        connection.send_error.assert_not_called()
        new_opts = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert "close_includes_tilt" not in new_opts


# ---------------------------------------------------------------------------
# _script_in_non_pulse_mode helper
# ---------------------------------------------------------------------------


class TestScriptGuardHelper:
    """Tests for _script_in_non_pulse_mode (pure validation helper)."""

    def test_allows_scripts_in_pulse_mode(self):
        options = {
            CONF_CONTROL_MODE: CONTROL_MODE_PULSE,
            CONF_OPEN_SWITCH_ENTITY_ID: "script.open_blind",
            CONF_CLOSE_SWITCH_ENTITY_ID: "script.close_blind",
            CONF_STOP_SWITCH_ENTITY_ID: "script.stop_blind",
        }
        assert _script_in_non_pulse_mode(CONTROL_MODE_PULSE, options) is None

    def test_rejects_script_in_switch_mode(self):
        options = {
            CONF_CONTROL_MODE: CONTROL_MODE_SWITCH,
            CONF_OPEN_SWITCH_ENTITY_ID: "script.open_blind",
            CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close_relay",
        }
        assert (
            _script_in_non_pulse_mode(CONTROL_MODE_SWITCH, options)
            == "script.open_blind"
        )

    def test_rejects_script_tilt_entity_in_toggle_mode(self):
        options = {
            CONF_CONTROL_MODE: CONTROL_MODE_TOGGLE,
            CONF_TILT_OPEN_SWITCH: "script.tilt_open",
        }
        assert (
            _script_in_non_pulse_mode(CONTROL_MODE_TOGGLE, options)
            == "script.tilt_open"
        )

    def test_allows_plain_switches_in_switch_mode(self):
        options = {
            CONF_OPEN_SWITCH_ENTITY_ID: "switch.open_relay",
            CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close_relay",
        }
        assert _script_in_non_pulse_mode(CONTROL_MODE_SWITCH, options) is None

    def test_rejects_script_in_wrapped_mode(self):
        # Only pulse mode supports scripts. Wrapped never carries switch-slot
        # scripts via the UI (the card clears them on mode switch), so this
        # only guards against raw API/YAML misuse — the rule stays simple:
        # scripts are valid in pulse mode, rejected everywhere else.
        options = {
            CONF_CONTROL_MODE: CONTROL_MODE_WRAPPED,
            CONF_OPEN_SWITCH_ENTITY_ID: "script.open_blind",
        }
        assert (
            _script_in_non_pulse_mode(CONTROL_MODE_WRAPPED, options)
            == "script.open_blind"
        )

    def test_rejects_script_when_control_mode_absent(self):
        # No explicit mode → runtime defaults to switch → scripts must be rejected.
        options = {CONF_OPEN_SWITCH_ENTITY_ID: "script.open_blind"}
        assert _script_in_non_pulse_mode(None, options) == "script.open_blind"


# ---------------------------------------------------------------------------
# ws_update_config — script entity guard
# ---------------------------------------------------------------------------


class TestScriptGuardInUpdateConfig:
    """ws_update_config rejects script entities outside pulse mode."""

    @pytest.mark.asyncio
    async def test_rejects_setting_script_in_switch_mode(self):
        config_entry = MagicMock()
        config_entry.domain = DOMAIN
        config_entry.options = {CONF_CONTROL_MODE: CONTROL_MODE_SWITCH}
        hass = MagicMock()
        conn = _make_connection()
        msg = {
            "id": 1,
            "type": "cover_time_based/update_config",
            "entity_id": ENTITY_ID,
            "open_switch_entity_id": "script.open_blind",
        }

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry, None),
        ):
            await _ws_update_config(hass, conn, msg)

        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "invalid_entity"
        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_switching_existing_script_into_switch_mode(self):
        config_entry = MagicMock()
        config_entry.domain = DOMAIN
        config_entry.options = {
            CONF_CONTROL_MODE: CONTROL_MODE_PULSE,
            CONF_OPEN_SWITCH_ENTITY_ID: "script.open_blind",
        }
        hass = MagicMock()
        conn = _make_connection()
        msg = {
            "id": 1,
            "type": "cover_time_based/update_config",
            "entity_id": ENTITY_ID,
            "control_mode": CONTROL_MODE_SWITCH,
        }

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry, None),
        ):
            await _ws_update_config(hass, conn, msg)

        conn.send_error.assert_called_once()
        assert conn.send_error.call_args[0][1] == "invalid_entity"
        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_script_in_pulse_mode(self):
        config_entry = MagicMock()
        config_entry.domain = DOMAIN
        config_entry.options = {CONF_CONTROL_MODE: CONTROL_MODE_PULSE}
        hass = MagicMock()
        conn = _make_connection()
        msg = {
            "id": 1,
            "type": "cover_time_based/update_config",
            "entity_id": ENTITY_ID,
            "open_switch_entity_id": "script.open_blind",
        }

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry, None),
        ):
            await _ws_update_config(hass, conn, msg)

        conn.send_error.assert_not_called()
        new_opts = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_opts[CONF_OPEN_SWITCH_ENTITY_ID] == "script.open_blind"


class TestReportsCommandNotEndpointRoundTrip:
    """reports_command_not_endpoint is returned in get_config and saved in update_config."""

    @pytest.mark.asyncio
    async def test_get_config_defaults_to_false(self):
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

        result = conn.send_result.call_args[0][1]
        assert result["reports_command_not_endpoint"] is False

    @pytest.mark.asyncio
    async def test_get_config_returns_stored_true(self):
        hass, _, entity_reg = _make_hass(
            options={
                CONF_CONTROL_MODE: CONTROL_MODE_WRAPPED,
                CONF_COVER_ENTITY_ID: "cover.inner",
                CONF_REPORTS_COMMAND_NOT_ENDPOINT: True,
            }
        )
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
        assert result["reports_command_not_endpoint"] is True

    @pytest.mark.asyncio
    async def test_update_config_saves_true(self):
        hass, _, entity_reg = _make_hass(
            options={CONF_CONTROL_MODE: CONTROL_MODE_WRAPPED}
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
                    "reports_command_not_endpoint": True,
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_options[CONF_REPORTS_COMMAND_NOT_ENDPOINT] is True


# ---------------------------------------------------------------------------
# invert
# ---------------------------------------------------------------------------


class TestInvertRoundTrip:
    """invert is returned in get_config and saved in update_config."""

    @pytest.mark.asyncio
    async def test_get_config_defaults_to_false(self):
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

        result = conn.send_result.call_args[0][1]
        assert result["invert"] is False

    @pytest.mark.asyncio
    async def test_get_config_returns_stored_true(self):
        hass, _, entity_reg = _make_hass(
            options={
                CONF_CONTROL_MODE: CONTROL_MODE_WRAPPED,
                CONF_COVER_ENTITY_ID: "cover.inner",
                CONF_INVERT: True,
            }
        )
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
        assert result["invert"] is True

    @pytest.mark.asyncio
    async def test_update_config_saves_true(self):
        hass, _, entity_reg = _make_hass(
            options={CONF_CONTROL_MODE: CONTROL_MODE_WRAPPED}
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
                    "invert": True,
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_options[CONF_INVERT] is True

    def test_field_map_contains_invert(self):
        from custom_components.cover_time_based.websocket_api import _FIELD_MAP

        assert _FIELD_MAP["invert"] == CONF_INVERT

    def test_update_schema_accepts_invert(self):
        # Guards the schema/_FIELD_MAP pair: a real websocket update_config
        # carrying `invert` must validate, else persistence is silently rejected.
        schema = ws_update_config._ws_schema
        validated = schema(
            {
                "id": 1,
                "type": "cover_time_based/update_config",
                "entity_id": "cover.x",
                "invert": True,
            }
        )
        assert validated["invert"] is True


class TestForceEndpointRedriveRoundTrip:
    """force_endpoint_redrive is returned in get_config and saved in update_config."""

    @pytest.mark.asyncio
    async def test_get_config_defaults_to_false(self):
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

        result = conn.send_result.call_args[0][1]
        assert result["force_endpoint_redrive"] is False

    @pytest.mark.asyncio
    async def test_get_config_returns_stored_true(self):
        hass, _, entity_reg = _make_hass(options={CONF_FORCE_ENDPOINT_REDRIVE: True})
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
        assert result["force_endpoint_redrive"] is True

    @pytest.mark.asyncio
    async def test_update_config_saves_true(self):
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
                    "force_endpoint_redrive": True,
                },
            )

        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_options[CONF_FORCE_ENDPOINT_REDRIVE] is True

    def test_field_map_contains_force_endpoint_redrive(self):
        from custom_components.cover_time_based.websocket_api import _FIELD_MAP

        assert _FIELD_MAP["force_endpoint_redrive"] == CONF_FORCE_ENDPOINT_REDRIVE

    def test_update_schema_accepts_force_endpoint_redrive(self):
        # Guards the schema/_FIELD_MAP pair: a real websocket update_config
        # carrying `force_endpoint_redrive` must validate, else persistence
        # is silently rejected.
        schema = ws_update_config._ws_schema
        validated = schema(
            {
                "id": 1,
                "type": "cover_time_based/update_config",
                "entity_id": "cover.x",
                "force_endpoint_redrive": True,
            }
        )
        assert validated["force_endpoint_redrive"] is True


class TestDirectionChangeDelayRemoved:
    """The settle gap is fixed at 1.0s and is no longer configurable.

    The websocket key is still *accepted* so a browser holding a cached copy
    of the old card does not get an error on save -- it is simply not mapped
    to an option, so nothing is persisted.
    """

    @pytest.mark.asyncio
    async def test_a_stale_card_sending_the_key_is_accepted_and_ignored(self):
        hass, _, entity_reg = _make_hass(
            options={CONF_CONTROL_MODE: CONTROL_MODE_WRAPPED}
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
                    "direction_change_delay": 2.5,
                },
            )

        conn.send_error.assert_not_called()
        new_options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert CONF_DIRECTION_CHANGE_DELAY not in new_options

    def test_update_schema_still_accepts_the_key(self):
        # The stale-card guarantee lives in the schema, and the handler test
        # above calls the unwrapped coroutine, which bypasses it. Without this
        # a schema tidy-up would make real websocket traffic from a cached
        # card fail validation while every other test stayed green.
        schema = ws_update_config._ws_schema
        validated = schema(
            {
                "id": 1,
                "type": "cover_time_based/update_config",
                "entity_id": "cover.x",
                "direction_change_delay": 2.5,
            }
        )
        assert validated["direction_change_delay"] == 2.5

    def test_field_map_no_longer_contains_the_key(self):
        from custom_components.cover_time_based.websocket_api import _FIELD_MAP

        assert "direction_change_delay" not in _FIELD_MAP

    @pytest.mark.asyncio
    async def test_get_config_no_longer_offers_the_key(self):
        hass, _, entity_reg = _make_hass(
            options={CONF_CONTROL_MODE: CONTROL_MODE_WRAPPED}
        )
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
        assert "direction_change_delay" not in result
