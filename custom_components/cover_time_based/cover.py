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
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue

from .cover_base import CoverTimeBased  # noqa: F401

_LOGGER = logging.getLogger(__name__)

CONF_DEVICES = "devices"
CONF_DEFAULTS = "defaults"
CONF_TRAVEL_MOVES_WITH_TILT = "travel_moves_with_tilt"
CONF_TRAVELLING_TIME_DOWN = "travelling_time_down"
CONF_TRAVELLING_TIME_UP = "travelling_time_up"
CONF_TILTING_TIME_DOWN = "tilting_time_down"
CONF_TILTING_TIME_UP = "tilting_time_up"
CONF_TRAVEL_DELAY_AT_END = "travel_delay_at_end"
CONF_MIN_MOVEMENT_TIME = "min_movement_time"
CONF_TRAVEL_STARTUP_DELAY = "travel_startup_delay"
CONF_TILT_STARTUP_DELAY = "tilt_startup_delay"
DEFAULT_TRAVEL_TIME = 30

CONF_OPEN_SWITCH_ENTITY_ID = "open_switch_entity_id"
CONF_CLOSE_SWITCH_ENTITY_ID = "close_switch_entity_id"
CONF_STOP_SWITCH_ENTITY_ID = "stop_switch_entity_id"
CONF_IS_BUTTON = "is_button"
CONF_INPUT_MODE = "input_mode"
CONF_PULSE_TIME = "pulse_time"
DEFAULT_PULSE_TIME = 1.0
INPUT_MODE_SWITCH = "switch"
INPUT_MODE_PULSE = "pulse"
INPUT_MODE_TOGGLE = "toggle"

CONF_COVER_ENTITY_ID = "cover_entity_id"
CONF_DEVICE_TYPE = "device_type"
DEVICE_TYPE_SWITCH = "switch"
DEVICE_TYPE_COVER = "cover"

SERVICE_SET_KNOWN_POSITION = "set_known_position"
SERVICE_SET_KNOWN_TILT_POSITION = "set_known_tilt_position"

BASE_DEVICE_SCHEMA = {
    vol.Required(CONF_NAME): cv.string,
}

TRAVEL_TIME_SCHEMA = {
    vol.Optional(CONF_TRAVEL_MOVES_WITH_TILT): cv.boolean,
    vol.Optional(CONF_TRAVELLING_TIME_DOWN): cv.positive_float,
    vol.Optional(CONF_TRAVELLING_TIME_UP): cv.positive_float,
    vol.Optional(CONF_TILTING_TIME_DOWN): cv.positive_float,
    vol.Optional(CONF_TILTING_TIME_UP): cv.positive_float,
    vol.Optional(CONF_TRAVEL_DELAY_AT_END): cv.positive_float,
    vol.Optional(CONF_MIN_MOVEMENT_TIME): cv.positive_float,
    vol.Optional(CONF_TRAVEL_STARTUP_DELAY): cv.positive_float,
    vol.Optional(CONF_TILT_STARTUP_DELAY): cv.positive_float,
}

SWITCH_COVER_SCHEMA = {
    **BASE_DEVICE_SCHEMA,
    vol.Required(CONF_OPEN_SWITCH_ENTITY_ID): cv.entity_id,
    vol.Required(CONF_CLOSE_SWITCH_ENTITY_ID): cv.entity_id,
    vol.Optional(CONF_STOP_SWITCH_ENTITY_ID, default=None): vol.Any(cv.entity_id, None),
    vol.Optional(CONF_IS_BUTTON, default=False): cv.boolean,
    vol.Optional(CONF_INPUT_MODE, default=None): vol.Any(
        vol.In([INPUT_MODE_SWITCH, INPUT_MODE_PULSE, INPUT_MODE_TOGGLE]), None
    ),
    vol.Optional(CONF_PULSE_TIME): cv.positive_float,
    **TRAVEL_TIME_SCHEMA,
}

ENTITY_COVER_SCHEMA = {
    **BASE_DEVICE_SCHEMA,
    vol.Required(CONF_COVER_ENTITY_ID): cv.entity_id,
    **TRAVEL_TIME_SCHEMA,
}

DEFAULTS_SCHEMA = vol.Schema({
    vol.Optional(CONF_TRAVEL_MOVES_WITH_TILT, default=False): cv.boolean,
    vol.Optional(
        CONF_TRAVELLING_TIME_DOWN, default=DEFAULT_TRAVEL_TIME
    ): cv.positive_float,
    vol.Optional(CONF_TRAVELLING_TIME_UP, default=DEFAULT_TRAVEL_TIME): cv.positive_float,
    vol.Optional(CONF_TILTING_TIME_DOWN, default=None): vol.Any(
        cv.positive_float, None
    ),
    vol.Optional(CONF_TILTING_TIME_UP, default=None): vol.Any(cv.positive_float, None),
    vol.Optional(CONF_TRAVEL_DELAY_AT_END, default=None): vol.Any(
        cv.positive_float, None
    ),
    vol.Optional(CONF_MIN_MOVEMENT_TIME, default=None): vol.Any(
        cv.positive_float, None
    ),
    vol.Optional(CONF_TRAVEL_STARTUP_DELAY, default=None): vol.Any(
        cv.positive_float, None
    ),
    vol.Optional(CONF_TILT_STARTUP_DELAY, default=None): vol.Any(
        cv.positive_float, None
    ),
})

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

DOMAIN = "cover_time_based"


def _create_cover_from_options(options, device_id="", name=""):
    """Create the appropriate cover subclass based on options."""
    from .cover_wrapped import WrappedCoverTimeBased
    from .cover_switch_mode import SwitchModeCover
    from .cover_pulse_mode import PulseModeCover
    from .cover_toggle_mode import ToggleModeCover

    device_type = options.get(CONF_DEVICE_TYPE, DEVICE_TYPE_SWITCH)

    # Common params for all subclasses
    common = dict(
        device_id=device_id,
        name=name,
        travel_moves_with_tilt=options.get(CONF_TRAVEL_MOVES_WITH_TILT, False),
        travel_time_down=options.get(CONF_TRAVELLING_TIME_DOWN, DEFAULT_TRAVEL_TIME),
        travel_time_up=options.get(CONF_TRAVELLING_TIME_UP, DEFAULT_TRAVEL_TIME),
        tilt_time_down=options.get(CONF_TILTING_TIME_DOWN),
        tilt_time_up=options.get(CONF_TILTING_TIME_UP),
        travel_delay_at_end=options.get(CONF_TRAVEL_DELAY_AT_END),
        min_movement_time=options.get(CONF_MIN_MOVEMENT_TIME),
        travel_startup_delay=options.get(CONF_TRAVEL_STARTUP_DELAY),
        tilt_startup_delay=options.get(CONF_TILT_STARTUP_DELAY),
    )

    if device_type == DEVICE_TYPE_COVER:
        return WrappedCoverTimeBased(
            cover_entity_id=options[CONF_COVER_ENTITY_ID],
            **common,
        )

    switch_args = dict(
        open_switch_entity_id=options[CONF_OPEN_SWITCH_ENTITY_ID],
        close_switch_entity_id=options[CONF_CLOSE_SWITCH_ENTITY_ID],
        stop_switch_entity_id=options.get(CONF_STOP_SWITCH_ENTITY_ID),
        **common,
    )

    input_mode = options.get(CONF_INPUT_MODE, INPUT_MODE_SWITCH)
    pulse_time = options.get(CONF_PULSE_TIME, DEFAULT_PULSE_TIME)

    if input_mode == INPUT_MODE_PULSE:
        return PulseModeCover(pulse_time=pulse_time, **switch_args)
    elif input_mode == INPUT_MODE_TOGGLE:
        return ToggleModeCover(pulse_time=pulse_time, **switch_args)
    else:
        return SwitchModeCover(**switch_args)


def devices_from_config(domain_config):
    """Parse configuration and add cover devices."""
    devices = []
    defaults = domain_config.get(CONF_DEFAULTS, {})

    def get_value(key, device_config, defaults_config, schema_default=None):
        """
        Get value with priority: device config > defaults > schema default.

        If key EXISTS in device config (even if None/null), use that value.
        Otherwise, try defaults, then schema default.
        """
        # Priority: device config > defaults > schema default
        if key in device_config:
            return device_config[key]
        if key in defaults_config:
            return defaults_config[key]
        return schema_default

    for device_id, config in domain_config[CONF_DEVICES].items():
        name = config.pop(CONF_NAME)

        travel_moves_with_tilt = get_value(CONF_TRAVEL_MOVES_WITH_TILT, config, defaults, False)
        travel_time_down = get_value(CONF_TRAVELLING_TIME_DOWN, config, defaults, DEFAULT_TRAVEL_TIME)
        travel_time_up = get_value(CONF_TRAVELLING_TIME_UP, config, defaults, DEFAULT_TRAVEL_TIME)
        tilt_time_down = get_value(CONF_TILTING_TIME_DOWN, config, defaults, None)
        tilt_time_up = get_value(CONF_TILTING_TIME_UP, config, defaults, None)
        travel_delay_at_end = get_value(CONF_TRAVEL_DELAY_AT_END, config, defaults, None)
        min_movement_time = get_value(CONF_MIN_MOVEMENT_TIME, config, defaults, None)
        travel_startup_delay = get_value(CONF_TRAVEL_STARTUP_DELAY, config, defaults, None)
        tilt_startup_delay = get_value(CONF_TILT_STARTUP_DELAY, config, defaults, None)

        config.pop(CONF_TRAVEL_MOVES_WITH_TILT, None)
        config.pop(CONF_TRAVELLING_TIME_DOWN, None)
        config.pop(CONF_TRAVELLING_TIME_UP, None)
        config.pop(CONF_TILTING_TIME_DOWN, None)
        config.pop(CONF_TILTING_TIME_UP, None)
        config.pop(CONF_TRAVEL_DELAY_AT_END, None)
        config.pop(CONF_MIN_MOVEMENT_TIME, None)
        config.pop(CONF_TRAVEL_STARTUP_DELAY, None)
        config.pop(CONF_TILT_STARTUP_DELAY, None)

        open_switch_entity_id = (
            config.pop(CONF_OPEN_SWITCH_ENTITY_ID)
            if CONF_OPEN_SWITCH_ENTITY_ID in config
            else None
        )
        close_switch_entity_id = (
            config.pop(CONF_CLOSE_SWITCH_ENTITY_ID)
            if CONF_CLOSE_SWITCH_ENTITY_ID in config
            else None
        )
        stop_switch_entity_id = (
            config.pop(CONF_STOP_SWITCH_ENTITY_ID)
            if CONF_STOP_SWITCH_ENTITY_ID in config
            else None
        )
        is_button = config.pop(CONF_IS_BUTTON) if CONF_IS_BUTTON in config else False
        input_mode = (
            config.pop(CONF_INPUT_MODE, None) if CONF_INPUT_MODE in config else None
        )
        pulse_time = get_value(CONF_PULSE_TIME, config, defaults, DEFAULT_PULSE_TIME)
        config.pop(CONF_PULSE_TIME, None)

        if input_mode is not None and is_button:
            _LOGGER.warning(
                "Device '%s': both 'is_button' and 'input_mode' are set. "
                "'input_mode: %s' takes precedence. Please remove 'is_button'.",
                device_id,
                input_mode,
            )
        elif is_button:
            input_mode = INPUT_MODE_PULSE
            _LOGGER.warning(
                "Device '%s': 'is_button' is deprecated. "
                "Use 'input_mode: pulse' instead.",
                device_id,
            )
        elif input_mode is None:
            input_mode = INPUT_MODE_SWITCH

        cover_entity_id = (
            config.pop(CONF_COVER_ENTITY_ID) if CONF_COVER_ENTITY_ID in config else None
        )

        options = {
            CONF_DEVICE_TYPE: DEVICE_TYPE_COVER if cover_entity_id else DEVICE_TYPE_SWITCH,
            CONF_TRAVEL_MOVES_WITH_TILT: travel_moves_with_tilt,
            CONF_TRAVELLING_TIME_DOWN: travel_time_down,
            CONF_TRAVELLING_TIME_UP: travel_time_up,
            CONF_TILTING_TIME_DOWN: tilt_time_down,
            CONF_TILTING_TIME_UP: tilt_time_up,
            CONF_TRAVEL_DELAY_AT_END: travel_delay_at_end,
            CONF_MIN_MOVEMENT_TIME: min_movement_time,
            CONF_TRAVEL_STARTUP_DELAY: travel_startup_delay,
            CONF_TILT_STARTUP_DELAY: tilt_startup_delay,
            CONF_INPUT_MODE: input_mode,
            CONF_PULSE_TIME: pulse_time,
        }
        if open_switch_entity_id:
            options[CONF_OPEN_SWITCH_ENTITY_ID] = open_switch_entity_id
            options[CONF_CLOSE_SWITCH_ENTITY_ID] = close_switch_entity_id
            options[CONF_STOP_SWITCH_ENTITY_ID] = stop_switch_entity_id
        if cover_entity_id:
            options[CONF_COVER_ENTITY_ID] = cover_entity_id

        device = _create_cover_from_options(options, device_id=device_id, name=name)
        devices.append(device)
    return devices


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

    platform.async_register_entity_service(
        SERVICE_SET_KNOWN_POSITION, POSITION_SCHEMA, "set_known_position"
    )
    platform.async_register_entity_service(
        SERVICE_SET_KNOWN_TILT_POSITION, TILT_POSITION_SCHEMA, "set_known_tilt_position"
    )


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
    async_add_entities([entity])

    platform = entity_platform.current_platform.get()
    platform.async_register_entity_service(
        SERVICE_SET_KNOWN_POSITION, POSITION_SCHEMA, "set_known_position"
    )
    platform.async_register_entity_service(
        SERVICE_SET_KNOWN_TILT_POSITION, TILT_POSITION_SCHEMA, "set_known_tilt_position"
    )
