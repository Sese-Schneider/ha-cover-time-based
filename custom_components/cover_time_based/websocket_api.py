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
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_COVER_ENTITY_ID,
    CONF_DEVICE_TYPE,
    CONF_INPUT_MODE,
    CONF_MIN_MOVEMENT_TIME,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_ENDPOINT_RUNON_TIME,
    CONF_TILT_MODE,
    CONF_TILT_STARTUP_DELAY,
    CONF_TILT_TIME_CLOSE,
    CONF_TILT_TIME_OPEN,
    CONF_TRAVEL_STARTUP_DELAY,
    CONF_TRAVEL_TIME_CLOSE,
    CONF_TRAVEL_TIME_OPEN,
    DEFAULT_ENDPOINT_RUNON_TIME,
    DEFAULT_PULSE_TIME,
    DEVICE_TYPE_COVER,
    DEVICE_TYPE_SWITCH,
    INPUT_MODE_PULSE,
    INPUT_MODE_SWITCH,
    INPUT_MODE_TOGGLE,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "cover_time_based"

# Map from WS field names to config entry option keys
_FIELD_MAP = {
    "device_type": CONF_DEVICE_TYPE,
    "input_mode": CONF_INPUT_MODE,
    "pulse_time": CONF_PULSE_TIME,
    "open_switch_entity_id": CONF_OPEN_SWITCH_ENTITY_ID,
    "close_switch_entity_id": CONF_CLOSE_SWITCH_ENTITY_ID,
    "stop_switch_entity_id": CONF_STOP_SWITCH_ENTITY_ID,
    "cover_entity_id": CONF_COVER_ENTITY_ID,
    "tilt_mode": CONF_TILT_MODE,
    "travel_time_close": CONF_TRAVEL_TIME_CLOSE,
    "travel_time_open": CONF_TRAVEL_TIME_OPEN,
    "tilt_time_close": CONF_TILT_TIME_CLOSE,
    "tilt_time_open": CONF_TILT_TIME_OPEN,
    "travel_startup_delay": CONF_TRAVEL_STARTUP_DELAY,
    "tilt_startup_delay": CONF_TILT_STARTUP_DELAY,
    "endpoint_runon_time": CONF_ENDPOINT_RUNON_TIME,
    "min_movement_time": CONF_MIN_MOVEMENT_TIME,
}


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
    if error:
        connection.send_error(msg["id"], "not_found", error)
        return

    options = config_entry.options
    connection.send_result(
        msg["id"],
        {
            "entry_id": config_entry.entry_id,
            "device_type": options.get(CONF_DEVICE_TYPE, DEVICE_TYPE_SWITCH),
            "input_mode": options.get(CONF_INPUT_MODE, INPUT_MODE_SWITCH),
            "pulse_time": options.get(CONF_PULSE_TIME, DEFAULT_PULSE_TIME),
            "open_switch_entity_id": options.get(CONF_OPEN_SWITCH_ENTITY_ID),
            "close_switch_entity_id": options.get(CONF_CLOSE_SWITCH_ENTITY_ID),
            "stop_switch_entity_id": options.get(CONF_STOP_SWITCH_ENTITY_ID),
            "cover_entity_id": options.get(CONF_COVER_ENTITY_ID),
            "tilt_mode": options.get(CONF_TILT_MODE, "none"),
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
        },
    )


@websocket_api.websocket_command(
    {
        "type": "cover_time_based/update_config",
        vol.Required("entity_id"): str,
        vol.Optional("device_type"): vol.In([DEVICE_TYPE_SWITCH, DEVICE_TYPE_COVER]),
        vol.Optional("input_mode"): vol.In(
            [INPUT_MODE_SWITCH, INPUT_MODE_PULSE, INPUT_MODE_TOGGLE]
        ),
        vol.Optional("pulse_time"): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=10)
        ),
        vol.Optional("open_switch_entity_id"): vol.Any(str, None),
        vol.Optional("close_switch_entity_id"): vol.Any(str, None),
        vol.Optional("stop_switch_entity_id"): vol.Any(str, None),
        vol.Optional("cover_entity_id"): vol.Any(str, None),
        vol.Optional("tilt_mode"): vol.In(["none", "before_after", "during"]),
        vol.Optional("travel_time_close"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("travel_time_open"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("tilt_time_close"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("tilt_time_open"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
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
    if error:
        connection.send_error(msg["id"], "not_found", error)
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
                new_options[conf_key] = value

    hass.config_entries.async_update_entry(config_entry, options=new_options)

    connection.send_result(msg["id"], {"success": True})


def _resolve_entity(hass: HomeAssistant, entity_id: str):
    """Resolve an entity_id to a CoverTimeBased entity instance."""
    from .cover import CoverTimeBased

    component = hass.data.get("entity_components", {}).get("cover")
    if component is None:
        return None
    entity = component.get_entity(entity_id)
    if entity is None or not isinstance(entity, CoverTimeBased):
        return None
    return entity


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
    entity = _resolve_entity(hass, msg["entity_id"])
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
    entity = _resolve_entity(hass, msg["entity_id"])
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
        vol.Required("command"): vol.In(["open", "close", "stop"]),
    }
)
@websocket_api.async_response
async def ws_raw_command(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send open/close/stop directly to the underlying device, bypassing the position tracker."""
    entity = _resolve_entity(hass, msg["entity_id"])
    if entity is None:
        connection.send_error(msg["id"], "not_found", "Entity not found")
        return

    try:
        command = msg["command"]
        if command == "open":
            await entity._send_open()
        elif command == "close":
            await entity._send_close()
        elif command == "stop":
            await entity._send_stop()
    except Exception as exc:  # noqa: BLE001
        connection.send_error(msg["id"], "failed", str(exc))
        return

    connection.send_result(msg["id"], {"success": True})
