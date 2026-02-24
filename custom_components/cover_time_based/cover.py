"""Cover time based"""

import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    PLATFORM_SCHEMA,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_NAME,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue

from .calibration import (
    CALIBRATABLE_ATTRIBUTES,
    SERVICE_START_CALIBRATION,
    SERVICE_STOP_CALIBRATION,
)
from .const import (
    CONF_ENDPOINT_RUNON_TIME,
    CONF_MIN_MOVEMENT_TIME,
    CONF_TILT_MODE,
    CONF_TILT_STARTUP_DELAY,
    CONF_TILT_TIME_CLOSE,
    CONF_TILT_TIME_OPEN,
    CONF_TRAVEL_STARTUP_DELAY,
    CONF_TRAVEL_TIME_CLOSE,
    CONF_TRAVEL_TIME_OPEN,
    DEFAULT_ENDPOINT_RUNON_TIME,
)
from .cover_base import CoverTimeBased  # noqa: F401
from .helpers import resolve_entity

_LOGGER = logging.getLogger(__name__)

DOMAIN = "cover_time_based"

# ---------------------------------------------------------------------------
# YAML config constants (deprecated + current)
# ---------------------------------------------------------------------------

CONF_DEVICES = "devices"
CONF_DEFAULTS = "defaults"

# Deprecated YAML key names (renamed)
CONF_TRAVEL_MOVES_WITH_TILT = "travel_moves_with_tilt"
CONF_TRAVELLING_TIME_DOWN = "travelling_time_down"
CONF_TRAVELLING_TIME_UP = "travelling_time_up"
CONF_TILTING_TIME_DOWN = "tilting_time_down"
CONF_TILTING_TIME_UP = "tilting_time_up"
CONF_TRAVEL_DELAY_AT_END = "travel_delay_at_end"
CONF_IS_BUTTON = "is_button"

CONF_OPEN_SWITCH_ENTITY_ID = "open_switch_entity_id"
CONF_CLOSE_SWITCH_ENTITY_ID = "close_switch_entity_id"
CONF_STOP_SWITCH_ENTITY_ID = "stop_switch_entity_id"
CONF_SAFE_TILT_POSITION = "safe_tilt_position"
CONF_MAX_TILT_ALLOWED_POSITION = "max_tilt_allowed_position"
CONF_TILT_OPEN_SWITCH = "tilt_open_switch"
CONF_TILT_CLOSE_SWITCH = "tilt_close_switch"
CONF_TILT_STOP_SWITCH = "tilt_stop_switch"
CONF_COVER_ENTITY_ID = "cover_entity_id"

# ---------------------------------------------------------------------------
# Control mode constants
# ---------------------------------------------------------------------------

CONF_CONTROL_MODE = "control_mode"
CONTROL_MODE_WRAPPED = "wrapped"
CONTROL_MODE_SWITCH = "switch"
CONTROL_MODE_PULSE = "pulse"
CONTROL_MODE_TOGGLE = "toggle"

CONF_PULSE_TIME = "pulse_time"
DEFAULT_PULSE_TIME = 1.0

SERVICE_SET_KNOWN_POSITION = "set_known_position"
SERVICE_SET_KNOWN_TILT_POSITION = "set_known_tilt_position"

# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

BASE_DEVICE_SCHEMA = {
    vol.Required(CONF_NAME): cv.string,
}

TRAVEL_TIME_SCHEMA = {
    vol.Optional(CONF_TRAVEL_MOVES_WITH_TILT): cv.boolean,
    vol.Optional(CONF_TRAVELLING_TIME_DOWN): cv.positive_float,
    vol.Optional(CONF_TRAVELLING_TIME_UP): cv.positive_float,
    vol.Optional(CONF_TILTING_TIME_DOWN): cv.positive_float,
    vol.Optional(CONF_TILTING_TIME_UP): cv.positive_float,
    vol.Optional(CONF_TRAVEL_STARTUP_DELAY): cv.positive_float,
    vol.Optional(CONF_TILT_STARTUP_DELAY): cv.positive_float,
    vol.Optional(CONF_ENDPOINT_RUNON_TIME): cv.positive_float,
    vol.Optional(CONF_TRAVEL_DELAY_AT_END): cv.positive_float,
    vol.Optional(CONF_MIN_MOVEMENT_TIME): cv.positive_float,
}

SWITCH_COVER_SCHEMA = {
    **BASE_DEVICE_SCHEMA,
    vol.Required(CONF_OPEN_SWITCH_ENTITY_ID): cv.entity_id,
    vol.Required(CONF_CLOSE_SWITCH_ENTITY_ID): cv.entity_id,
    vol.Optional(CONF_STOP_SWITCH_ENTITY_ID, default=None): vol.Any(cv.entity_id, None),
    vol.Optional(CONF_IS_BUTTON, default=False): cv.boolean,
    vol.Optional(CONF_PULSE_TIME): cv.positive_float,
    **TRAVEL_TIME_SCHEMA,
}

ENTITY_COVER_SCHEMA = {
    **BASE_DEVICE_SCHEMA,
    vol.Required(CONF_COVER_ENTITY_ID): cv.entity_id,
    **TRAVEL_TIME_SCHEMA,
}

DEFAULTS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_TRAVEL_MOVES_WITH_TILT, default=False): cv.boolean,
        vol.Optional(CONF_TRAVELLING_TIME_DOWN, default=None): vol.Any(
            cv.positive_float, None
        ),
        vol.Optional(CONF_TRAVELLING_TIME_UP, default=None): vol.Any(
            cv.positive_float, None
        ),
        vol.Optional(CONF_TILTING_TIME_DOWN, default=None): vol.Any(
            cv.positive_float, None
        ),
        vol.Optional(CONF_TILTING_TIME_UP, default=None): vol.Any(
            cv.positive_float, None
        ),
        vol.Optional(CONF_TRAVEL_STARTUP_DELAY, default=None): vol.Any(
            cv.positive_float, None
        ),
        vol.Optional(CONF_TILT_STARTUP_DELAY, default=None): vol.Any(
            cv.positive_float, None
        ),
        vol.Optional(
            CONF_ENDPOINT_RUNON_TIME, default=DEFAULT_ENDPOINT_RUNON_TIME
        ): vol.Any(cv.positive_float, None),
        vol.Optional(CONF_TRAVEL_DELAY_AT_END): cv.positive_float,
        vol.Optional(CONF_MIN_MOVEMENT_TIME, default=None): vol.Any(
            cv.positive_float, None
        ),
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_DEFAULTS, default={}): DEFAULTS_SCHEMA,
        vol.Optional(CONF_DEVICES, default={}): vol.Schema(
            {cv.string: vol.Schema(vol.Any(SWITCH_COVER_SCHEMA, ENTITY_COVER_SCHEMA))}
        ),
    }
)

POSITION_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_POSITION): cv.positive_int,
    }
)
TILT_POSITION_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_TILT_POSITION): cv.positive_int,
    }
)

# ---------------------------------------------------------------------------
# YAML migration helpers
# ---------------------------------------------------------------------------

_YAML_KEY_RENAMES = {
    CONF_TRAVEL_DELAY_AT_END: CONF_ENDPOINT_RUNON_TIME,
    CONF_TRAVELLING_TIME_DOWN: CONF_TRAVEL_TIME_CLOSE,
    CONF_TRAVELLING_TIME_UP: CONF_TRAVEL_TIME_OPEN,
    CONF_TILTING_TIME_DOWN: CONF_TILT_TIME_CLOSE,
    CONF_TILTING_TIME_UP: CONF_TILT_TIME_OPEN,
}


def _migrate_yaml_keys(config):
    """Migrate deprecated YAML key names to current names."""
    for old_key, new_key in _YAML_KEY_RENAMES.items():
        if old_key in config:
            if new_key not in config:
                config[new_key] = config[old_key]
            config.pop(old_key)


_TIMING_DEFAULTS = {
    CONF_TILT_MODE: "none",
    CONF_TRAVEL_TIME_CLOSE: None,
    CONF_TRAVEL_TIME_OPEN: None,
    CONF_TILT_TIME_CLOSE: None,
    CONF_TILT_TIME_OPEN: None,
    CONF_TRAVEL_STARTUP_DELAY: None,
    CONF_TILT_STARTUP_DELAY: None,
    CONF_ENDPOINT_RUNON_TIME: DEFAULT_ENDPOINT_RUNON_TIME,
    CONF_MIN_MOVEMENT_TIME: None,
}


def _get_value(key, device_config, defaults_config, schema_default=None):
    """Get config value with priority: device config > defaults > schema default."""
    if key in device_config:
        return device_config[key]
    if key in defaults_config:
        return defaults_config[key]
    return schema_default


def _resolve_control_mode(config, defaults, has_cover_entity):
    """Resolve control mode from config, handling legacy keys."""
    if has_cover_entity:
        config.pop(CONF_IS_BUTTON, None)
        return CONTROL_MODE_WRAPPED

    # Explicit input_mode takes precedence
    explicit = config.pop("input_mode", None) or defaults.get("input_mode")
    if explicit:
        config.pop(CONF_IS_BUTTON, None)
        return explicit

    # Legacy is_button → pulse mode
    is_button = config.pop(CONF_IS_BUTTON, False)
    if is_button:
        return CONTROL_MODE_PULSE

    return CONTROL_MODE_SWITCH


# ---------------------------------------------------------------------------
# Entity factory
# ---------------------------------------------------------------------------


def _resolve_tilt_strategy(tilt_mode_str, tilt_time_close, tilt_time_open, **kwargs):
    """Map tilt_mode config string to a TiltStrategy instance (or None)."""
    from .tilt_strategies import DualMotorTilt, InlineTilt, SequentialTilt

    if tilt_mode_str == "none":
        return None

    has_tilt_times = tilt_time_close is not None and tilt_time_open is not None
    if not has_tilt_times:
        return None

    if tilt_mode_str == "dual_motor":
        return DualMotorTilt(
            safe_tilt_position=kwargs.get("safe_tilt_position") or 100,
            max_tilt_allowed_position=kwargs.get("max_tilt_allowed_position"),
        )
    if tilt_mode_str == "inline":
        return InlineTilt()
    # "sequential" or any other value with tilt times → sequential
    return SequentialTilt()


def _create_cover_from_options(options, device_id="", name=""):
    """Create the appropriate cover subclass based on options."""
    from .cover_wrapped import WrappedCoverTimeBased
    from .cover_switch_mode import SwitchModeCover
    from .cover_pulse_mode import PulseModeCover
    from .cover_toggle_mode import ToggleModeCover

    control_mode = options.get(CONF_CONTROL_MODE, CONTROL_MODE_SWITCH)

    tilt_mode_str = options.get(CONF_TILT_MODE, "none")
    tilt_strategy = _resolve_tilt_strategy(
        tilt_mode_str,
        options.get(CONF_TILT_TIME_CLOSE),
        options.get(CONF_TILT_TIME_OPEN),
        safe_tilt_position=options.get(CONF_SAFE_TILT_POSITION, 100),
        max_tilt_allowed_position=options.get(CONF_MAX_TILT_ALLOWED_POSITION),
    )

    # Common params for all subclasses
    common = dict(
        device_id=device_id,
        name=name,
        tilt_strategy=tilt_strategy,
        travel_time_close=options.get(CONF_TRAVEL_TIME_CLOSE),
        travel_time_open=options.get(CONF_TRAVEL_TIME_OPEN),
        tilt_time_close=options.get(CONF_TILT_TIME_CLOSE),
        tilt_time_open=options.get(CONF_TILT_TIME_OPEN),
        travel_startup_delay=options.get(CONF_TRAVEL_STARTUP_DELAY),
        tilt_startup_delay=options.get(CONF_TILT_STARTUP_DELAY),
        endpoint_runon_time=options.get(
            CONF_ENDPOINT_RUNON_TIME, DEFAULT_ENDPOINT_RUNON_TIME
        ),
        min_movement_time=options.get(CONF_MIN_MOVEMENT_TIME),
        tilt_open_switch=options.get(CONF_TILT_OPEN_SWITCH),
        tilt_close_switch=options.get(CONF_TILT_CLOSE_SWITCH),
        tilt_stop_switch=options.get(CONF_TILT_STOP_SWITCH),
    )

    if control_mode == CONTROL_MODE_WRAPPED:
        return WrappedCoverTimeBased(
            cover_entity_id=options.get(CONF_COVER_ENTITY_ID, ""),
            **common,
        )

    switch_args = dict(
        open_switch_entity_id=options.get(CONF_OPEN_SWITCH_ENTITY_ID, ""),
        close_switch_entity_id=options.get(CONF_CLOSE_SWITCH_ENTITY_ID, ""),
        stop_switch_entity_id=options.get(CONF_STOP_SWITCH_ENTITY_ID),
        **common,
    )

    pulse_time = options.get(CONF_PULSE_TIME, DEFAULT_PULSE_TIME)

    if control_mode == CONTROL_MODE_PULSE:
        return PulseModeCover(pulse_time=pulse_time, **switch_args)
    elif control_mode == CONTROL_MODE_TOGGLE:
        return ToggleModeCover(pulse_time=pulse_time, **switch_args)
    else:
        return SwitchModeCover(**switch_args)


def devices_from_config(domain_config):
    """Parse configuration and add cover devices."""
    devices = []
    defaults = domain_config.get(CONF_DEFAULTS, {})

    _migrate_yaml_keys(defaults)

    for device_id, config in domain_config[CONF_DEVICES].items():
        name = config.pop(CONF_NAME)

        _migrate_yaml_keys(config)

        # Extract timing values with defaults, then remove from config
        options = {}
        for key, schema_default in _TIMING_DEFAULTS.items():
            options[key] = _get_value(key, config, defaults, schema_default)
            config.pop(key, None)

        # Legacy travel_moves_with_tilt → inline tilt mode
        travel_moves = _get_value(CONF_TRAVEL_MOVES_WITH_TILT, config, defaults, False)
        config.pop(CONF_TRAVEL_MOVES_WITH_TILT, None)
        if travel_moves and options.get(CONF_TILT_MODE) == "none":
            options[CONF_TILT_MODE] = "inline"

        # Entity IDs
        open_switch = config.pop(CONF_OPEN_SWITCH_ENTITY_ID, None)
        close_switch = config.pop(CONF_CLOSE_SWITCH_ENTITY_ID, None)
        stop_switch = config.pop(CONF_STOP_SWITCH_ENTITY_ID, None)
        cover_entity_id = config.pop(CONF_COVER_ENTITY_ID, None)

        # Control mode (handles is_button deprecation)
        control_mode = _resolve_control_mode(config, defaults, bool(cover_entity_id))
        pulse_time = _get_value(CONF_PULSE_TIME, config, defaults, DEFAULT_PULSE_TIME)
        config.pop(CONF_PULSE_TIME, None)

        options[CONF_CONTROL_MODE] = control_mode
        options[CONF_PULSE_TIME] = pulse_time

        if open_switch:
            options[CONF_OPEN_SWITCH_ENTITY_ID] = open_switch
            options[CONF_CLOSE_SWITCH_ENTITY_ID] = close_switch
            options[CONF_STOP_SWITCH_ENTITY_ID] = stop_switch
        if cover_entity_id:
            options[CONF_COVER_ENTITY_ID] = cover_entity_id

        devices.append(
            _create_cover_from_options(options, device_id=device_id, name=name)
        )
    return devices


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the cover platform."""
    _LOGGER.warning(
        "Configuration of Cover Time Based via YAML is deprecated and "
        "will be removed in a future version. Please use the UI to "
        "configure your covers (Settings > Devices & Services > Helpers)"
    )
    async_create_issue(
        hass,
        DOMAIN,
        "deprecated_yaml",
        is_fixable=False,
        severity=IssueSeverity.WARNING,
        translation_key="deprecated_yaml",
    )
    async_add_entities(devices_from_config(config))

    platform = entity_platform.current_platform.get()
    _register_services(platform)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a single cover entity from a config entry."""
    entity = _create_cover_from_options(
        config_entry.options,
        device_id=config_entry.entry_id,
        name=config_entry.title,
    )
    entity._config_entry_id = config_entry.entry_id
    async_add_entities([entity])

    platform = entity_platform.current_platform.get()
    _register_services(platform)


def _register_services(platform):
    """Register entity services on the given platform."""
    platform.async_register_entity_service(
        SERVICE_SET_KNOWN_POSITION, POSITION_SCHEMA, "set_known_position"
    )
    platform.async_register_entity_service(
        SERVICE_SET_KNOWN_TILT_POSITION, TILT_POSITION_SCHEMA, "set_known_tilt_position"
    )

    hass = platform.hass

    if not hass.services.has_service(DOMAIN, SERVICE_START_CALIBRATION):

        async def _handle_start_calibration(call):
            entity_id = call.data["entity_id"]
            entity = resolve_entity(hass, entity_id)
            data = {k: v for k, v in call.data.items() if k != "entity_id"}
            await entity.start_calibration(**data)

        hass.services.async_register(
            DOMAIN,
            SERVICE_START_CALIBRATION,
            _handle_start_calibration,
            schema=vol.Schema(
                {
                    vol.Required("entity_id"): cv.entity_id,
                    vol.Required("attribute"): vol.In(CALIBRATABLE_ATTRIBUTES),
                    vol.Required("timeout"): vol.All(
                        vol.Coerce(float), vol.Range(min=1)
                    ),
                    vol.Optional("direction"): vol.In(["open", "close"]),
                }
            ),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_STOP_CALIBRATION):

        async def _handle_stop_calibration(call):
            entity_id = call.data["entity_id"]
            entity = resolve_entity(hass, entity_id)
            data = {k: v for k, v in call.data.items() if k != "entity_id"}
            return await entity.stop_calibration(**data)

        hass.services.async_register(
            DOMAIN,
            SERVICE_STOP_CALIBRATION,
            _handle_stop_calibration,
            schema=vol.Schema(
                {
                    vol.Required("entity_id"): cv.entity_id,
                    vol.Optional("cancel", default=False): cv.boolean,
                }
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )
