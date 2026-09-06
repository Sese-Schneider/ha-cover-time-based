"""WebSocket API for cover_time_based configuration card."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, NamedTuple

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .calibration import CALIBRATABLE_ATTRIBUTES
from .const import DOMAIN
from .cover import (
    CONF_ASSUMED_STATE,
    CONF_CLOSE_INCLUDES_TILT,
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_CONTROL_MODE,
    CONF_COVER_ENTITY_ID,
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
    CONTROL_MODE_PULSE,
    CONTROL_MODE_SINGLE_BUTTON,
    CONTROL_MODE_SWITCH,
    CONTROL_MODE_TOGGLE,
    CONTROL_MODE_TOGGLE_OPPOSITE,
    CONTROL_MODE_WRAPPED,
    DEFAULT_ASSUMED_STATE,
    DEFAULT_CLOSE_INCLUDES_TILT,
    DEFAULT_ENDPOINT_RUNON_TIME,
    DEFAULT_FORCE_ENDPOINT_REDRIVE,
    DEFAULT_FORCE_TIME_BASED_POSITION,
    DEFAULT_IGNORE_ALL_REPORTS,
    DEFAULT_IGNORE_ENDPOINT_STATES,
    DEFAULT_IGNORE_REPORTED_POSITION,
    DEFAULT_INVERT,
    DEFAULT_PULSE_TIME,
    DEFAULT_RECALIBRATE_BEFORE_POSITION,
    DEFAULT_RELAY_REPORTS_OFF,
    DEFAULT_REPORTS_COMMAND_NOT_ENDPOINT,
    DEFAULT_SEND_ENDPOINT_STOP,
    DEFAULT_WAIT_FOR_RELAY_FEEDBACK,
    MIN_DURATION,
    PERCENT,
)
from .cover_base import RawCommandNotSupported
from .helpers import resolve_entity_or_none

_LOGGER = logging.getLogger(__name__)


# Single source of truth for every configurable field the card exchanges over
# the websocket. Each descriptor drives all three derived structures below —
# the ws-key→conf-key map (`_FIELD_MAP`), the `get_config` response defaults,
# and the `update_config` voluptuous schema — so a new option is added in one
# place, not four. Adding a row here is the whole wiring change.
class _ConfigField(NamedTuple):
    ws_key: str  # the key the card sends and receives
    conf_key: str | None  # config-entry option key; None = validated but never
    # persisted or returned (a legacy knob a cached card still sends)
    validator: Any  # voluptuous validator for the update_config schema
    default: Any = None  # get_config fallback when the option is absent
    normalize: Callable[[Any], Any] | None = None  # applied on read and write


def _normalize_tilt_mode(value: Any) -> Any:
    """Map the legacy "sequential" tilt mode to its canonical name.

    The frontend no longer has dropdown/hint keys for the bare "sequential"
    string; the migration and resolver alias handle behaviour, and this keeps
    the read and write paths consistent for any entry that escapes migration.
    """
    return "sequential_close" if value == "sequential" else value


# Validators shared across fields of the same shape. `None` is always accepted
# (a cleared field), matching HA's own optional-value convention.
_BOOL = vol.Any(None, bool)
_ENTITY = vol.Any(str, None)
_PERCENT_OR_NONE = vol.Any(None, PERCENT)
_PULSE_TIME = vol.Any(
    None, vol.All(vol.Coerce(float), vol.Range(min=MIN_DURATION, max=10))
)
_TRAVEL_TIME = vol.Any(
    None, vol.All(vol.Coerce(float), vol.Range(min=MIN_DURATION, max=600))
)
_DELAY = vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600)))

_CONFIG_FIELDS: tuple[_ConfigField, ...] = (
    _ConfigField(
        "control_mode",
        CONF_CONTROL_MODE,
        vol.In(
            [
                CONTROL_MODE_WRAPPED,
                CONTROL_MODE_SWITCH,
                CONTROL_MODE_PULSE,
                CONTROL_MODE_TOGGLE,
                CONTROL_MODE_TOGGLE_OPPOSITE,
                CONTROL_MODE_SINGLE_BUTTON,
            ]
        ),
        default=CONTROL_MODE_SWITCH,
    ),
    _ConfigField(
        "pulse_time", CONF_PULSE_TIME, _PULSE_TIME, default=DEFAULT_PULSE_TIME
    ),
    _ConfigField(
        "relay_reports_off",
        CONF_RELAY_REPORTS_OFF,
        _BOOL,
        default=DEFAULT_RELAY_REPORTS_OFF,
    ),
    _ConfigField(
        "send_endpoint_stop",
        CONF_SEND_ENDPOINT_STOP,
        _BOOL,
        default=DEFAULT_SEND_ENDPOINT_STOP,
    ),
    _ConfigField(
        "force_endpoint_redrive",
        CONF_FORCE_ENDPOINT_REDRIVE,
        _BOOL,
        default=DEFAULT_FORCE_ENDPOINT_REDRIVE,
    ),
    _ConfigField(
        "wait_for_relay_feedback",
        CONF_WAIT_FOR_RELAY_FEEDBACK,
        _BOOL,
        default=DEFAULT_WAIT_FOR_RELAY_FEEDBACK,
    ),
    _ConfigField(
        "recalibrate_before_position",
        CONF_RECALIBRATE_BEFORE_POSITION,
        _BOOL,
        default=DEFAULT_RECALIBRATE_BEFORE_POSITION,
    ),
    _ConfigField("open_switch_entity_id", CONF_OPEN_SWITCH_ENTITY_ID, _ENTITY),
    _ConfigField("close_switch_entity_id", CONF_CLOSE_SWITCH_ENTITY_ID, _ENTITY),
    _ConfigField("stop_switch_entity_id", CONF_STOP_SWITCH_ENTITY_ID, _ENTITY),
    _ConfigField("cover_entity_id", CONF_COVER_ENTITY_ID, _ENTITY),
    _ConfigField(
        "ignore_reported_position",
        CONF_IGNORE_REPORTED_POSITION,
        _BOOL,
        default=DEFAULT_IGNORE_REPORTED_POSITION,
    ),
    _ConfigField(
        "force_time_based_position",
        CONF_FORCE_TIME_BASED_POSITION,
        _BOOL,
        default=DEFAULT_FORCE_TIME_BASED_POSITION,
    ),
    _ConfigField(
        "reports_command_not_endpoint",
        CONF_REPORTS_COMMAND_NOT_ENDPOINT,
        _BOOL,
        default=DEFAULT_REPORTS_COMMAND_NOT_ENDPOINT,
    ),
    _ConfigField(
        "ignore_endpoint_states",
        CONF_IGNORE_ENDPOINT_STATES,
        _BOOL,
        default=DEFAULT_IGNORE_ENDPOINT_STATES,
    ),
    _ConfigField(
        "ignore_all_reports",
        CONF_IGNORE_ALL_REPORTS,
        _BOOL,
        default=DEFAULT_IGNORE_ALL_REPORTS,
    ),
    _ConfigField("invert", CONF_INVERT, _BOOL, default=DEFAULT_INVERT),
    _ConfigField(
        "tilt_mode",
        CONF_TILT_MODE,
        vol.In(
            [
                "none",
                "sequential_close",
                "sequential_open",
                "sequential",
                "dual_motor",
                "inline",
            ]
        ),
        default="none",
        normalize=_normalize_tilt_mode,
    ),
    _ConfigField("travel_time_close", CONF_TRAVEL_TIME_CLOSE, _TRAVEL_TIME),
    _ConfigField("travel_time_open", CONF_TRAVEL_TIME_OPEN, _TRAVEL_TIME),
    _ConfigField("tilt_time_close", CONF_TILT_TIME_CLOSE, _TRAVEL_TIME),
    _ConfigField("tilt_time_open", CONF_TILT_TIME_OPEN, _TRAVEL_TIME),
    _ConfigField("travel_startup_delay", CONF_TRAVEL_STARTUP_DELAY, _DELAY),
    _ConfigField("tilt_startup_delay", CONF_TILT_STARTUP_DELAY, _DELAY),
    _ConfigField(
        "endpoint_runon_time",
        CONF_ENDPOINT_RUNON_TIME,
        _DELAY,
        default=DEFAULT_ENDPOINT_RUNON_TIME,
    ),
    _ConfigField("min_movement_time", CONF_MIN_MOVEMENT_TIME, _DELAY),
    # Accepted and ignored (conf_key None, so never persisted or returned): a
    # browser holding a cached copy of the old card still sends it.
    _ConfigField("direction_change_delay", None, _DELAY),
    _ConfigField(
        "safe_tilt_position", CONF_SAFE_TILT_POSITION, _PERCENT_OR_NONE, default=100
    ),
    _ConfigField(
        "max_tilt_allowed_position", CONF_MAX_TILT_ALLOWED_POSITION, _PERCENT_OR_NONE
    ),
    _ConfigField("tilt_open_switch", CONF_TILT_OPEN_SWITCH, _ENTITY),
    _ConfigField("tilt_close_switch", CONF_TILT_CLOSE_SWITCH, _ENTITY),
    _ConfigField("tilt_stop_switch", CONF_TILT_STOP_SWITCH, _ENTITY),
    _ConfigField(
        "close_includes_tilt",
        CONF_CLOSE_INCLUDES_TILT,
        _BOOL,
        default=DEFAULT_CLOSE_INCLUDES_TILT,
    ),
    _ConfigField(
        "assumed_state", CONF_ASSUMED_STATE, _BOOL, default=DEFAULT_ASSUMED_STATE
    ),
)

# Map from WS field names to config entry option keys, for the fields that
# persist. Derived so it can never drift from the table above.
_FIELD_MAP = {f.ws_key: f.conf_key for f in _CONFIG_FIELDS if f.conf_key is not None}

# The update_config field validators, keyed by the WS key that carries them.
_UPDATE_CONFIG_FIELD_SCHEMA = {
    vol.Optional(f.ws_key): f.validator for f in _CONFIG_FIELDS
}


# Entity-id slots that must not hold a `script.` entity in a mode that cannot
# drive one.
_SWITCH_ENTITY_CONF_KEYS = (
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_TILT_OPEN_SWITCH,
    CONF_TILT_CLOSE_SWITCH,
    CONF_TILT_STOP_SWITCH,
)

# Modes that turn the driving entity off themselves after pulse_time, so a
# script's own auto-off is never misread as a stop.
_SCRIPT_CAPABLE_MODES = frozenset({CONTROL_MODE_PULSE, CONTROL_MODE_SINGLE_BUTTON})


def _unsupported_script_entity(control_mode, options):
    """Return the first script entity_id configured in a mode that cannot drive
    one, else None.

    Scripts auto-return to 'off', which the latching and toggle modes read as
    a stop; only the modes in _SCRIPT_CAPABLE_MODES drive the entity as a
    timed press and ignore its state. The card clears the wrapped-mode switch
    slots, and any script-valued slot left over from a script-capable mode,
    whenever the control mode changes (see _onControlModeChange /
    clearedEntitiesForMode / clearedScriptEntities in cover-time-based-card.js
    and entity-filter.js) — so this rejection is a backstop that mainly fires
    on raw API/YAML misuse. `options` is the merged config that would be
    persisted.
    """
    if control_mode in _SCRIPT_CAPABLE_MODES:
        return None
    for key in _SWITCH_ENTITY_CONF_KEYS:
        value = options.get(key)
        if isinstance(value, str) and value.startswith("script."):
            return value
    return None


def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register WebSocket API commands.

    Every command here reads or writes a cover's configuration, or drives a
    relay, so each handler carries ``@websocket_api.require_admin``
    (outermost), matching HA core's gating of config-entry writes. A new
    command must too.
    """
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


@websocket_api.require_admin
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
    # Every persisted field, read through the shared table so the response can
    # never drift from what update_config accepts. Fields carrying a normalize
    # hook (e.g. the legacy "sequential" tilt mode) are canonicalised here so
    # the card always sees the current name, whatever escaped migration.
    result: dict[str, Any] = {"entry_id": config_entry.entry_id}
    for field in _CONFIG_FIELDS:
        if field.conf_key is None:
            continue
        value = options.get(field.conf_key, field.default)
        if field.normalize is not None:
            value = field.normalize(value)
        result[field.ws_key] = value
    connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        "type": "cover_time_based/update_config",
        vol.Required("entity_id"): str,
        **_UPDATE_CONFIG_FIELD_SCHEMA,
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

    # Reject saving while a calibration is running: a save reloads the
    # config entry, and a reload mid-calibration destroys the session.
    entity = resolve_entity_or_none(hass, msg["entity_id"])
    if entity is not None and entity._calibration is not None:
        connection.send_error(
            msg["id"],
            "calibration_active",
            "Configuration cannot be saved while a calibration is running;"
            " finish or cancel it first.",
        )
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

    for field in _CONFIG_FIELDS:
        if field.conf_key is None or field.ws_key not in msg:
            continue
        value = msg[field.ws_key]
        if value is None:
            new_options.pop(field.conf_key, None)
        else:
            # A field's normalize hook (e.g. the legacy "sequential" tilt mode)
            # canonicalises the value so persisted options never carry a name
            # the frontend can no longer render.
            if field.normalize is not None:
                value = field.normalize(value)
            new_options[field.conf_key] = value

    # Reject script entities in a mode that cannot drive one (they auto-return
    # to 'off', which switch/toggle modes misread as a stop). Validate the
    # merged result so switching an existing script-configured cover into
    # switch/toggle is caught too.
    offending = _unsupported_script_entity(
        new_options.get(CONF_CONTROL_MODE), new_options
    )
    if offending is not None:
        connection.send_error(
            msg["id"],
            "invalid_entity",
            "Script entities are only supported in pulse and single-button "
            f"modes (got {offending})",
        )
        return

    hass.config_entries.async_update_entry(config_entry, options=new_options)

    connection.send_result(msg["id"], {"success": True})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        "type": "cover_time_based/start_calibration",
        vol.Required("entity_id"): str,
        vol.Required("attribute"): vol.In(CALIBRATABLE_ATTRIBUTES),
        vol.Required("timeout"): vol.All(vol.Coerce(float), vol.Range(min=1, max=600)),
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
    except Exception as exc:
        connection.send_error(msg["id"], "failed", str(exc))
        return

    connection.send_result(msg["id"], {"success": True})


@websocket_api.require_admin
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
    except Exception as exc:
        connection.send_error(msg["id"], "failed", str(exc))
        return

    connection.send_result(msg["id"], result)


@websocket_api.require_admin
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

    try:
        await entity.async_raw_command(msg["command"])
    except RawCommandNotSupported as exc:
        connection.send_error(msg["id"], "not_supported", str(exc))
        return
    except Exception as exc:
        connection.send_error(msg["id"], "failed", str(exc))
        return

    connection.send_result(msg["id"], {"success": True})
