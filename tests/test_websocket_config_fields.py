"""Golden characterization tests for the websocket config-field wiring.

5.2 collapses three hand-maintained parallel structures in ``websocket_api``
(``_FIELD_MAP``, the ``get_config`` response, the ``update_config`` schema)
into one derived table. These tests pin the *exact* observable behaviour of
all three so the derivation cannot silently change what a card sees or what a
save persists. They must stay green across the refactor.
"""

from unittest.mock import patch

import pytest
import voluptuous as vol

from custom_components.cover_time_based import websocket_api
from custom_components.cover_time_based.cover import (
    CONF_ASSUMED_STATE,
    CONF_CLOSE_INCLUDES_TILT,
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_CONTROL_MODE,
    CONF_COVER_ENTITY_ID,
    CONF_DIRECTION_CHANGE_DELAY,
    CONF_ENDPOINT_RUNON_TIME,
    CONF_FORCE_ENDPOINT_REDRIVE,
    CONF_FORCE_TIME_BASED_POSITION,
    CONF_IGNORE_ALL_REPORTS,
    CONF_IGNORE_ENDPOINT_STATES,
    CONF_IGNORE_REPORTED_POSITION,
    CONF_INVERT,
    CONF_MAX_TILT_ALLOWED_POSITION,
    CONF_MIN_MOVEMENT_TIME,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_RECALIBRATE_BEFORE_POSITION,
    CONF_RELAY_REPORTS_OFF,
    CONF_REPORTS_COMMAND_NOT_ENDPOINT,
    CONF_SAFE_TILT_POSITION,
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
    CONF_WAIT_FOR_RELAY_FEEDBACK,
)
from tests.test_websocket_api import (
    ENTITY_ID,
    ENTRY_ID,
    _make_connection,
    _make_hass,
    _ws_get_config,
    _ws_update_config,
)

# The complete get_config response for a config entry with empty options —
# every default, spelled out. entry_id is dynamic and checked separately.
EXPECTED_DEFAULT_CONFIG = {
    "control_mode": "switch",
    "pulse_time": 1.0,
    "relay_reports_off": True,
    "send_endpoint_stop": True,
    "open_switch_entity_id": None,
    "close_switch_entity_id": None,
    "stop_switch_entity_id": None,
    "cover_entity_id": None,
    "ignore_reported_position": False,
    "force_time_based_position": False,
    "reports_command_not_endpoint": False,
    "ignore_endpoint_states": False,
    "ignore_all_reports": False,
    "invert": False,
    "tilt_mode": "none",
    "travel_time_close": None,
    "travel_time_open": None,
    "tilt_time_close": None,
    "tilt_time_open": None,
    "travel_startup_delay": None,
    "tilt_startup_delay": None,
    "endpoint_runon_time": 2.0,
    "min_movement_time": None,
    "safe_tilt_position": 100,
    "max_tilt_allowed_position": None,
    "tilt_open_switch": None,
    "tilt_close_switch": None,
    "tilt_stop_switch": None,
    "close_includes_tilt": True,
    "assumed_state": True,
    "force_endpoint_redrive": False,
    "wait_for_relay_feedback": False,
    "recalibrate_before_position": False,
}

# The exact ws_key -> conf_key mapping every persisted field goes through.
EXPECTED_FIELD_MAP = {
    "control_mode": CONF_CONTROL_MODE,
    "pulse_time": CONF_PULSE_TIME,
    "relay_reports_off": CONF_RELAY_REPORTS_OFF,
    "send_endpoint_stop": CONF_SEND_ENDPOINT_STOP,
    "force_endpoint_redrive": CONF_FORCE_ENDPOINT_REDRIVE,
    "wait_for_relay_feedback": CONF_WAIT_FOR_RELAY_FEEDBACK,
    "recalibrate_before_position": CONF_RECALIBRATE_BEFORE_POSITION,
    "open_switch_entity_id": CONF_OPEN_SWITCH_ENTITY_ID,
    "close_switch_entity_id": CONF_CLOSE_SWITCH_ENTITY_ID,
    "stop_switch_entity_id": CONF_STOP_SWITCH_ENTITY_ID,
    "cover_entity_id": CONF_COVER_ENTITY_ID,
    "ignore_reported_position": CONF_IGNORE_REPORTED_POSITION,
    "force_time_based_position": CONF_FORCE_TIME_BASED_POSITION,
    "reports_command_not_endpoint": CONF_REPORTS_COMMAND_NOT_ENDPOINT,
    "ignore_endpoint_states": CONF_IGNORE_ENDPOINT_STATES,
    "ignore_all_reports": CONF_IGNORE_ALL_REPORTS,
    "invert": CONF_INVERT,
    "tilt_mode": CONF_TILT_MODE,
    "travel_time_close": CONF_TRAVEL_TIME_CLOSE,
    "travel_time_open": CONF_TRAVEL_TIME_OPEN,
    "tilt_time_close": CONF_TILT_TIME_CLOSE,
    "tilt_time_open": CONF_TILT_TIME_OPEN,
    "travel_startup_delay": CONF_TRAVEL_STARTUP_DELAY,
    "tilt_startup_delay": CONF_TILT_STARTUP_DELAY,
    "endpoint_runon_time": CONF_ENDPOINT_RUNON_TIME,
    "min_movement_time": CONF_MIN_MOVEMENT_TIME,
    "safe_tilt_position": CONF_SAFE_TILT_POSITION,
    "max_tilt_allowed_position": CONF_MAX_TILT_ALLOWED_POSITION,
    "tilt_open_switch": CONF_TILT_OPEN_SWITCH,
    "tilt_close_switch": CONF_TILT_CLOSE_SWITCH,
    "tilt_stop_switch": CONF_TILT_STOP_SWITCH,
    "close_includes_tilt": CONF_CLOSE_INCLUDES_TILT,
    "assumed_state": CONF_ASSUMED_STATE,
}

# The complete set of keys the update_config schema declares: the fixed frame
# (``id`` is injected by @websocket_command), every persisted field, and the
# one accepted-but-ignored legacy knob a cached card may still send.
EXPECTED_SCHEMA_KEYS = (
    {"id", "type", "entity_id"} | set(EXPECTED_FIELD_MAP) | {"direction_change_delay"}
)


def _schema_keys():
    schema = websocket_api.ws_update_config._ws_schema
    return {getattr(marker, "schema", marker) for marker in schema.schema}


async def _get_config(options):
    hass, _, entity_reg = _make_hass(options=options)
    conn = _make_connection()
    with patch(
        "custom_components.cover_time_based.websocket_api.er.async_get",
        return_value=entity_reg,
    ):
        await _ws_get_config(
            hass,
            conn,
            {"id": 1, "type": "cover_time_based/get_config", "entity_id": ENTITY_ID},
        )
    return conn.send_result.call_args[0][1]


def _frame(**fields):
    return {
        "id": 1,
        "type": "cover_time_based/update_config",
        "entity_id": ENTITY_ID,
        **fields,
    }


async def _update(msg_fields):
    hass, _, entity_reg = _make_hass(options=msg_fields.pop("_options", {}))
    conn = _make_connection()
    with (
        patch(
            "custom_components.cover_time_based.websocket_api.er.async_get",
            return_value=entity_reg,
        ),
        patch(
            "custom_components.cover_time_based.websocket_api.resolve_entity_or_none",
            return_value=None,
        ),
    ):
        await _ws_update_config(hass, conn, _frame(**msg_fields))
    return hass.config_entries.async_update_entry.call_args.kwargs["options"]


class TestFieldMap:
    """_FIELD_MAP is derived from the table but must stay ws_key -> conf_key."""

    def test_field_map_is_exact(self):
        assert websocket_api._FIELD_MAP == EXPECTED_FIELD_MAP


class TestGetConfigResponse:
    """get_config returns every field's stored value or its default."""

    @pytest.mark.asyncio
    async def test_default_output_is_exact(self):
        result = await _get_config({})
        assert result.pop("entry_id") == ENTRY_ID
        assert result == EXPECTED_DEFAULT_CONFIG

    @pytest.mark.asyncio
    async def test_echoes_every_stored_value(self):
        # A non-default value for every persisted field, so a dropped or
        # mis-keyed field in the derived response shows up here.
        stored = {
            conf_key: f"stored::{ws_key}"
            for ws_key, conf_key in EXPECTED_FIELD_MAP.items()
        }
        result = await _get_config(stored)
        result.pop("entry_id")
        for ws_key, conf_key in EXPECTED_FIELD_MAP.items():
            assert result[ws_key] == stored[conf_key], ws_key

    @pytest.mark.asyncio
    async def test_normalizes_legacy_sequential_tilt_mode_on_read(self):
        result = await _get_config({CONF_TILT_MODE: "sequential"})
        assert result["tilt_mode"] == "sequential_close"


class TestUpdateSchema:
    """The update_config voluptuous schema accepts exactly the wired fields."""

    def test_declares_exactly_the_expected_keys(self):
        assert _schema_keys() == EXPECTED_SCHEMA_KEYS

    def test_rejects_pulse_time_above_ten(self):
        schema = websocket_api.ws_update_config._ws_schema
        schema(_frame(pulse_time=5))
        with pytest.raises(vol.Invalid):
            schema(_frame(pulse_time=11))

    def test_rejects_travel_time_above_six_hundred(self):
        schema = websocket_api.ws_update_config._ws_schema
        schema(_frame(travel_time_open=600))
        with pytest.raises(vol.Invalid):
            schema(_frame(travel_time_open=601))

    def test_accepts_but_never_persists_direction_change_delay(self):
        # In the schema (a cached old card still sends it) but absent from
        # _FIELD_MAP, so it is validated and dropped, never written.
        assert "direction_change_delay" in _schema_keys()
        assert CONF_DIRECTION_CHANGE_DELAY not in websocket_api._FIELD_MAP.values()


class TestUpdatePersistence:
    """update_config writes mapped fields and honours the None/legacy rules."""

    @pytest.mark.asyncio
    async def test_persists_mapped_fields_and_drops_direction_change_delay(self):
        saved = await _update(
            {"travel_time_open": 12.5, "invert": True, "direction_change_delay": 3.0}
        )
        assert saved[CONF_TRAVEL_TIME_OPEN] == 12.5
        assert saved[CONF_INVERT] is True
        assert CONF_DIRECTION_CHANGE_DELAY not in saved

    @pytest.mark.asyncio
    async def test_normalizes_legacy_sequential_tilt_mode_on_write(self):
        saved = await _update({"tilt_mode": "sequential"})
        assert saved[CONF_TILT_MODE] == "sequential_close"

    @pytest.mark.asyncio
    async def test_removes_a_field_set_to_none(self):
        saved = await _update({"_options": {CONF_INVERT: True}, "invert": None})
        assert CONF_INVERT not in saved
