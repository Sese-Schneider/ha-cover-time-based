"""WebSocket API for cover_time_based configuration card."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .cover import (
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
    "travel_moves_with_tilt": CONF_TRAVEL_MOVES_WITH_TILT,
    "travelling_time_down": CONF_TRAVELLING_TIME_DOWN,
    "travelling_time_up": CONF_TRAVELLING_TIME_UP,
    "tilting_time_down": CONF_TILTING_TIME_DOWN,
    "tilting_time_up": CONF_TILTING_TIME_UP,
    "travel_motor_overhead": CONF_TRAVEL_MOTOR_OVERHEAD,
    "tilt_motor_overhead": CONF_TILT_MOTOR_OVERHEAD,
    "min_movement_time": CONF_MIN_MOVEMENT_TIME,
}


def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register WebSocket API commands."""
    websocket_api.async_register_command(hass, ws_get_config)
    websocket_api.async_register_command(hass, ws_update_config)


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
            "travel_moves_with_tilt": options.get(CONF_TRAVEL_MOVES_WITH_TILT, False),
            "travelling_time_down": options.get(
                CONF_TRAVELLING_TIME_DOWN, DEFAULT_TRAVEL_TIME
            ),
            "travelling_time_up": options.get(
                CONF_TRAVELLING_TIME_UP, DEFAULT_TRAVEL_TIME
            ),
            "tilting_time_down": options.get(CONF_TILTING_TIME_DOWN),
            "tilting_time_up": options.get(CONF_TILTING_TIME_UP),
            "travel_motor_overhead": options.get(CONF_TRAVEL_MOTOR_OVERHEAD),
            "tilt_motor_overhead": options.get(CONF_TILT_MOTOR_OVERHEAD),
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
        vol.Optional("travel_moves_with_tilt"): bool,
        vol.Optional("travelling_time_down"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("travelling_time_up"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("tilting_time_down"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("tilting_time_up"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("travel_motor_overhead"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("tilt_motor_overhead"): vol.Any(
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
