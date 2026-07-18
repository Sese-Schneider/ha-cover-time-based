"""WebSocket API for cover_time_based configuration card."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .calibration import CALIBRATABLE_ATTRIBUTES
from .cover import (
    CONF_ASSUMED_STATE,
    CONF_CLOSE_INCLUDES_TILT,
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_CONTROL_MODE,
    CONF_COVER_ENTITY_ID,
    CONF_FORCE_ENDPOINT_REDRIVE,
    CONF_FORCE_TIME_BASED_POSITION,
    CONF_IGNORE_REPORTED_POSITION,
    CONF_INVERT,
    CONF_MIN_MOVEMENT_TIME,
    CONF_MAX_TILT_ALLOWED_POSITION,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_RELAY_REPORTS_OFF,
    CONF_REPORTS_COMMAND_NOT_ENDPOINT,
    CONF_SAFE_TILT_POSITION,
    CONF_SEND_ENDPOINT_STOP,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_ENDPOINT_RUNON_TIME,
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
    DEFAULT_ASSUMED_STATE,
    DEFAULT_CLOSE_INCLUDES_TILT,
    DEFAULT_ENDPOINT_RUNON_TIME,
    DEFAULT_FORCE_ENDPOINT_REDRIVE,
    DEFAULT_FORCE_TIME_BASED_POSITION,
    DEFAULT_IGNORE_REPORTED_POSITION,
    DEFAULT_INVERT,
    DEFAULT_PULSE_TIME,
    DEFAULT_RELAY_REPORTS_OFF,
    DEFAULT_REPORTS_COMMAND_NOT_ENDPOINT,
    DEFAULT_SEND_ENDPOINT_STOP,
)
from .const import DOMAIN
from .helpers import resolve_entity_or_none

_LOGGER = logging.getLogger(__name__)

# Map from WS field names to config entry option keys
_FIELD_MAP = {
    "control_mode": CONF_CONTROL_MODE,
    "pulse_time": CONF_PULSE_TIME,
    "relay_reports_off": CONF_RELAY_REPORTS_OFF,
    "send_endpoint_stop": CONF_SEND_ENDPOINT_STOP,
    "force_endpoint_redrive": CONF_FORCE_ENDPOINT_REDRIVE,
    "open_switch_entity_id": CONF_OPEN_SWITCH_ENTITY_ID,
    "close_switch_entity_id": CONF_CLOSE_SWITCH_ENTITY_ID,
    "stop_switch_entity_id": CONF_STOP_SWITCH_ENTITY_ID,
    "cover_entity_id": CONF_COVER_ENTITY_ID,
    "ignore_reported_position": CONF_IGNORE_REPORTED_POSITION,
    "force_time_based_position": CONF_FORCE_TIME_BASED_POSITION,
    "reports_command_not_endpoint": CONF_REPORTS_COMMAND_NOT_ENDPOINT,
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


# Entity-id slots that must not hold a `script.` entity outside pulse mode.
_SWITCH_ENTITY_CONF_KEYS = (
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_TILT_OPEN_SWITCH,
    CONF_TILT_CLOSE_SWITCH,
    CONF_TILT_STOP_SWITCH,
)


def _script_in_non_pulse_mode(control_mode, options):
    """Return the first script entity_id configured outside pulse mode, else None.

    Scripts are only supported in pulse mode (they auto-return to 'off',
    which switch/toggle modes misread as a stop). Every other mode rejects
    them, keeping the rule simple and unequivocal. Wrapped mode never carries
    switch-slot entities via the UI — the card clears them when the mode
    changes (see _onControlModeChange) — so this rejection only fires on raw
    API/YAML misuse. `options` is the merged config that would be persisted.
    """
    if control_mode == CONTROL_MODE_PULSE:
        return None
    for key in _SWITCH_ENTITY_CONF_KEYS:
        value = options.get(key)
        if isinstance(value, str) and value.startswith("script."):
            return value
    return None


def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register WebSocket API commands."""
    websocket_api.async_register_command(hass, ws_get_config)
    websocket_api.async_register_command(hass, ws_update_config)
    websocket_api.async_register_command(hass, ws_start_calibration)
    websocket_api.async_register_command(hass, ws_stop_calibration)
    websocket_api.async_register_command(hass, ws_raw_command)


def _resolve_config_entry(hass: HomeAssistant, entity_id: str):
    """Resolve an entity_id to its config entry.

    Returns (config_entry, error_msg) tuple.
    """
    entity_reg = er.async_get(hass)
    entry = entity_reg.async_get(entity_id)
    if not entry or not entry.config_entry_id:
        return None, "Entity not found or not a config entry entity"

    config_entry = hass.config_entries.async_get_entry(entry.config_entry_id)
    if not config_entry or config_entry.domain != DOMAIN:
        return None, "Entity does not belong to cover_time_based"

    return config_entry, None


@websocket_api.websocket_command(
    {
        "type": "cover_time_based/get_config",
        vol.Required("entity_id"): str,
    }
)
@websocket_api.async_response
async def ws_get_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get_config WebSocket command."""
    config_entry, error = _resolve_config_entry(hass, msg["entity_id"])
    if error or config_entry is None:
        connection.send_error(msg["id"], "not_found", error or "Config entry not found")
        return

    options = config_entry.options
    # Normalize the legacy "sequential" string in the GET response so the
    # frontend always sees the current canonical name. The migration and
    # resolver alias handle behavior; this guard keeps the UI consistent
    # for any entry that somehow escapes migration.
    tilt_mode = options.get(CONF_TILT_MODE, "none")
    if tilt_mode == "sequential":
        tilt_mode = "sequential_close"
    connection.send_result(
        msg["id"],
        {
            "entry_id": config_entry.entry_id,
            "control_mode": options.get(CONF_CONTROL_MODE, CONTROL_MODE_SWITCH),
            "pulse_time": options.get(CONF_PULSE_TIME, DEFAULT_PULSE_TIME),
            "relay_reports_off": options.get(
                CONF_RELAY_REPORTS_OFF, DEFAULT_RELAY_REPORTS_OFF
            ),
            "send_endpoint_stop": options.get(
                CONF_SEND_ENDPOINT_STOP, DEFAULT_SEND_ENDPOINT_STOP
            ),
            "open_switch_entity_id": options.get(CONF_OPEN_SWITCH_ENTITY_ID),
            "close_switch_entity_id": options.get(CONF_CLOSE_SWITCH_ENTITY_ID),
            "stop_switch_entity_id": options.get(CONF_STOP_SWITCH_ENTITY_ID),
            "cover_entity_id": options.get(CONF_COVER_ENTITY_ID),
            "ignore_reported_position": options.get(
                CONF_IGNORE_REPORTED_POSITION, DEFAULT_IGNORE_REPORTED_POSITION
            ),
            "force_time_based_position": options.get(
                CONF_FORCE_TIME_BASED_POSITION, DEFAULT_FORCE_TIME_BASED_POSITION
            ),
            "reports_command_not_endpoint": options.get(
                CONF_REPORTS_COMMAND_NOT_ENDPOINT,
                DEFAULT_REPORTS_COMMAND_NOT_ENDPOINT,
            ),
            "invert": options.get(CONF_INVERT, DEFAULT_INVERT),
            "tilt_mode": tilt_mode,
            "travel_time_close": options.get(CONF_TRAVEL_TIME_CLOSE),
            "travel_time_open": options.get(CONF_TRAVEL_TIME_OPEN),
            "tilt_time_close": options.get(CONF_TILT_TIME_CLOSE),
            "tilt_time_open": options.get(CONF_TILT_TIME_OPEN),
            "travel_startup_delay": options.get(CONF_TRAVEL_STARTUP_DELAY),
            "tilt_startup_delay": options.get(CONF_TILT_STARTUP_DELAY),
            "endpoint_runon_time": options.get(
                CONF_ENDPOINT_RUNON_TIME, DEFAULT_ENDPOINT_RUNON_TIME
            ),
            "min_movement_time": options.get(CONF_MIN_MOVEMENT_TIME),
            "safe_tilt_position": options.get(CONF_SAFE_TILT_POSITION, 100),
            "max_tilt_allowed_position": options.get(CONF_MAX_TILT_ALLOWED_POSITION),
            "tilt_open_switch": options.get(CONF_TILT_OPEN_SWITCH),
            "tilt_close_switch": options.get(CONF_TILT_CLOSE_SWITCH),
            "tilt_stop_switch": options.get(CONF_TILT_STOP_SWITCH),
            "close_includes_tilt": options.get(
                CONF_CLOSE_INCLUDES_TILT, DEFAULT_CLOSE_INCLUDES_TILT
            ),
            "assumed_state": options.get(CONF_ASSUMED_STATE, DEFAULT_ASSUMED_STATE),
            "force_endpoint_redrive": options.get(
                CONF_FORCE_ENDPOINT_REDRIVE, DEFAULT_FORCE_ENDPOINT_REDRIVE
            ),
        },
    )


@websocket_api.websocket_command(
    {
        "type": "cover_time_based/update_config",
        vol.Required("entity_id"): str,
        vol.Optional("control_mode"): vol.In(
            [
                CONTROL_MODE_WRAPPED,
                CONTROL_MODE_SWITCH,
                CONTROL_MODE_PULSE,
                CONTROL_MODE_TOGGLE,
                CONTROL_MODE_TOGGLE_OPPOSITE,
            ]
        ),
        vol.Optional("pulse_time"): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=10)
        ),
        vol.Optional("relay_reports_off"): vol.Any(None, bool),
        vol.Optional("send_endpoint_stop"): vol.Any(None, bool),
        vol.Optional("force_endpoint_redrive"): vol.Any(None, bool),
        vol.Optional("open_switch_entity_id"): vol.Any(str, None),
        vol.Optional("close_switch_entity_id"): vol.Any(str, None),
        vol.Optional("stop_switch_entity_id"): vol.Any(str, None),
        vol.Optional("cover_entity_id"): vol.Any(str, None),
        vol.Optional("ignore_reported_position"): vol.Any(None, bool),
        vol.Optional("force_time_based_position"): vol.Any(None, bool),
        vol.Optional("reports_command_not_endpoint"): vol.Any(None, bool),
        vol.Optional("invert"): vol.Any(None, bool),
        vol.Optional("assumed_state"): vol.Any(None, bool),
        vol.Optional("tilt_mode"): vol.In(
            [
                "none",
                "sequential_close",
                "sequential_open",
                "sequential",
                "dual_motor",
                "inline",
            ]
        ),
        vol.Optional("travel_time_close"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0.1, max=600))
        ),
        vol.Optional("travel_time_open"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0.1, max=600))
        ),
        vol.Optional("tilt_time_close"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0.1, max=600))
        ),
        vol.Optional("tilt_time_open"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0.1, max=600))
        ),
        vol.Optional("travel_startup_delay"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("tilt_startup_delay"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("endpoint_runon_time"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("min_movement_time"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("safe_tilt_position"): vol.Any(
            None, vol.All(int, vol.Range(min=0, max=100))
        ),
        vol.Optional("max_tilt_allowed_position"): vol.Any(
            None, vol.All(int, vol.Range(min=0, max=100))
        ),
        vol.Optional("tilt_open_switch"): vol.Any(str, None),
        vol.Optional("tilt_close_switch"): vol.Any(str, None),
        vol.Optional("tilt_stop_switch"): vol.Any(str, None),
        vol.Optional("close_includes_tilt"): vol.Any(None, bool),
    }
)
@websocket_api.async_response
async def ws_update_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle update_config WebSocket command."""
    config_entry, error = _resolve_config_entry(hass, msg["entity_id"])
    if error or config_entry is None:
        connection.send_error(msg["id"], "not_found", error or "Config entry not found")
        return

    # Reject wrapping another cover_time_based entity
    cover_entity_id = msg.get("cover_entity_id")
    if cover_entity_id:
        entity_reg = er.async_get(hass)
        target = entity_reg.async_get(cover_entity_id)
        if target and target.platform == DOMAIN:
            connection.send_error(
                msg["id"],
                "invalid_entity",
                "Cannot wrap another Cover Time Based entity",
            )
            return

    new_options = dict(config_entry.options)

    for ws_key, conf_key in _FIELD_MAP.items():
        if ws_key in msg:
            value = msg[ws_key]
            if value is None:
                new_options.pop(conf_key, None)
            else:
                # Normalize the legacy "sequential" string on write so
                # persisted options never carry it — the frontend no longer
                # has dropdown/hint keys for it.
                if conf_key == CONF_TILT_MODE and value == "sequential":
                    value = "sequential_close"
                new_options[conf_key] = value

    # Reject script entities outside pulse mode (they auto-return to 'off',
    # which switch/toggle modes misread as a stop). Validate the merged result
    # so switching an existing script-configured cover into switch/toggle is
    # caught too.
    offending = _script_in_non_pulse_mode(
        new_options.get(CONF_CONTROL_MODE), new_options
    )
    if offending is not None:
        connection.send_error(
            msg["id"],
            "invalid_entity",
            f"Script entities are only supported in pulse mode (got {offending})",
        )
        return

    hass.config_entries.async_update_entry(config_entry, options=new_options)

    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        "type": "cover_time_based/start_calibration",
        vol.Required("entity_id"): str,
        vol.Required("attribute"): vol.In(CALIBRATABLE_ATTRIBUTES),
        vol.Required("timeout"): vol.All(vol.Coerce(float), vol.Range(min=1)),
        vol.Optional("direction"): vol.In(["open", "close"]),
    }
)
@websocket_api.async_response
async def ws_start_calibration(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle start_calibration WebSocket command."""
    entity = resolve_entity_or_none(hass, msg["entity_id"])
    if entity is None:
        connection.send_error(msg["id"], "not_found", "Entity not found")
        return

    try:
        kwargs = {"attribute": msg["attribute"], "timeout": msg["timeout"]}
        if "direction" in msg:
            kwargs["direction"] = msg["direction"]
        await entity.start_calibration(**kwargs)
    except Exception as exc:  # noqa: BLE001
        connection.send_error(msg["id"], "failed", str(exc))
        return

    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        "type": "cover_time_based/stop_calibration",
        vol.Required("entity_id"): str,
        vol.Optional("cancel", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_stop_calibration(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle stop_calibration WebSocket command."""
    entity = resolve_entity_or_none(hass, msg["entity_id"])
    if entity is None:
        connection.send_error(msg["id"], "not_found", "Entity not found")
        return

    try:
        result = await entity.stop_calibration(cancel=msg["cancel"])
    except Exception as exc:  # noqa: BLE001
        connection.send_error(msg["id"], "failed", str(exc))
        return

    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        "type": "cover_time_based/raw_command",
        vol.Required("entity_id"): str,
        vol.Required("command"): vol.In(
            ["open", "close", "stop", "tilt_open", "tilt_close", "tilt_stop"]
        ),
    }
)
@websocket_api.async_response
async def ws_raw_command(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send open/close/stop directly to the underlying device, bypassing the position tracker."""
    entity = resolve_entity_or_none(hass, msg["entity_id"])
    if entity is None:
        connection.send_error(msg["id"], "not_found", "Entity not found")
        return

    command = msg["command"]

    # Validate tilt motor for tilt commands early
    if command.startswith("tilt_") and not entity._has_tilt_motor():
        connection.send_error(msg["id"], "not_supported", "Tilt motor not configured")
        return

    try:
        # Stop active lifecycle tracking (calibration manages its own state)
        if entity._calibration is None:
            entity._cancel_startup_delay_task()
            entity._cancel_delay_task()
            entity._handle_stop()

        await entity._raw_direction_command(command)

        # Clear tracked position (outside of calibration)
        if entity._calibration is None:
            if command.startswith("tilt_"):
                if entity._has_tilt_support():
                    entity.tilt_calc.clear_position()
            else:
                entity.travel_calc.clear_position()
            entity.async_write_ha_state()
    except Exception as exc:  # noqa: BLE001
        connection.send_error(msg["id"], "failed", str(exc))
        return

    connection.send_result(msg["id"], {"success": True})
