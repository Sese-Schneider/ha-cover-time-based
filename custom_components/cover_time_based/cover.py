"""Cover time based"""

import asyncio
import logging
from asyncio import sleep
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_CURRENT_TILT_POSITION,
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    PLATFORM_SCHEMA,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.const import (
    CONF_NAME,
    ATTR_ENTITY_ID,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.event import (
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
from xknx.devices import TravelStatus, TravelCalculator

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

CONF_COVER_ENTITY_ID = "cover_entity_id"

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

        cover_entity_id = (
            config.pop(CONF_COVER_ENTITY_ID) if CONF_COVER_ENTITY_ID in config else None
        )

        device = CoverTimeBased(
            device_id,
            name,
            travel_moves_with_tilt,
            travel_time_down,
            travel_time_up,
            tilt_time_down,
            tilt_time_up,
            travel_delay_at_end,
            min_movement_time,
            travel_startup_delay,
            tilt_startup_delay,
            open_switch_entity_id,
            close_switch_entity_id,
            stop_switch_entity_id,
            is_button,
            cover_entity_id,
        )
        devices.append(device)
    return devices


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the cover platform."""
    async_add_entities(devices_from_config(config))

    platform = entity_platform.current_platform.get()

    platform.async_register_entity_service(
        SERVICE_SET_KNOWN_POSITION, POSITION_SCHEMA, "set_known_position"
    )
    platform.async_register_entity_service(
        SERVICE_SET_KNOWN_TILT_POSITION, TILT_POSITION_SCHEMA, "set_known_tilt_position"
    )


class CoverTimeBased(CoverEntity, RestoreEntity):
    def __init__(
        self,
        device_id,
        name,
        travel_moves_with_tilt,
        travel_time_down,
        travel_time_up,
        tilt_time_down,
        tilt_time_up,
        travel_delay_at_end,
        min_movement_time,
        travel_startup_delay,
        tilt_startup_delay,
        open_switch_entity_id,
        close_switch_entity_id,
        stop_switch_entity_id,
        is_button,
        cover_entity_id,
    ):
        """Initialize the cover."""
        self._unique_id = device_id

        self._travel_moves_with_tilt = travel_moves_with_tilt
        self._travel_time_down = travel_time_down
        self._travel_time_up = travel_time_up
        self._tilting_time_down = tilt_time_down
        self._tilting_time_up = tilt_time_up
        self._travel_delay_at_end = travel_delay_at_end
        self._min_movement_time = min_movement_time
        self._travel_startup_delay = travel_startup_delay
        self._tilt_startup_delay = tilt_startup_delay

        self._open_switch_entity_id = open_switch_entity_id
        self._close_switch_entity_id = close_switch_entity_id
        self._stop_switch_entity_id = stop_switch_entity_id
        self._is_button = is_button

        self._cover_entity_id = cover_entity_id

        if name:
            self._name = name
        else:
            self._name = device_id

        self._unsubscribe_auto_updater = None
        self._delay_task = None
        self._startup_delay_task = None
        self._last_command = None

        self.travel_calc = TravelCalculator(
            self._travel_time_down,
            self._travel_time_up,
        )
        if self._has_tilt_support():
            self.tilt_calc = TravelCalculator(
                self._tilting_time_down,
                self._tilting_time_up,
            )

    async def async_added_to_hass(self):
        """Only cover's position and tilt matters."""
        old_state = await self.async_get_last_state()
        _LOGGER.debug("async_added_to_hass :: oldState %s", old_state)
        if (
            old_state is not None
            and self.travel_calc is not None
            and old_state.attributes.get(ATTR_CURRENT_POSITION) is not None
        ):
            self.travel_calc.set_position(
                100 - int(old_state.attributes.get(ATTR_CURRENT_POSITION))
            )

            if (
                self._has_tilt_support()
                and old_state.attributes.get(ATTR_CURRENT_TILT_POSITION) is not None
            ):
                self.tilt_calc.set_position(
                    100 - int(old_state.attributes.get(ATTR_CURRENT_TILT_POSITION))
                )

    def _handle_stop(self):
        """Handle stop"""
        if self.travel_calc.is_traveling():
            _LOGGER.debug("_handle_stop :: button stops cover movement")
            self.travel_calc.stop()
            self.stop_auto_updater()

        if self._has_tilt_support() and self.tilt_calc.is_traveling():
            _LOGGER.debug("_handle_stop :: button stops tilt movement")
            self.tilt_calc.stop()
            self.stop_auto_updater()

    def _stop_travel_if_traveling(self):
        """Stop cover movement if it's currently traveling."""
        if self.travel_calc.is_traveling():
            _LOGGER.debug("_stop_travel_if_traveling :: stopping cover movement")
            self.travel_calc.stop()
            if self._has_tilt_support() and self.tilt_calc.is_traveling():
                _LOGGER.debug("_stop_travel_if_traveling :: also stopping tilt")
                self.tilt_calc.stop()
    
    def _cancel_delay_task(self):
        """Cancel any active delay task."""
        if self._delay_task is not None and not self._delay_task.done():
            _LOGGER.debug("_cancel_delay_task :: cancelling active delay task")
            self._delay_task.cancel()
            self._delay_task = None
            return True
        return False
    
    def _cancel_startup_delay_task(self):
        """Cancel any active startup delay task."""
        if self._startup_delay_task is not None and not self._startup_delay_task.done():
            _LOGGER.debug("_cancel_startup_delay_task :: cancelling active startup delay task")
            self._startup_delay_task.cancel()
            self._startup_delay_task = None
    
    async def _execute_with_startup_delay(self, startup_delay, start_callback):
        """
        Execute movement with startup delay.
        
        This method handles the motor inertia by:
        1. Turning relay ON immediately
        2. Waiting for startup_delay (motor "wakes up")
        3. Starting TravelCalculator (position starts changing in HA)
        
        Args:
            startup_delay: Time in seconds to wait before starting position tracking
            start_callback: Callback to execute after delay (starts TravelCalculator)
        """
        # Motor inertia handling: relay ON → wait → start position tracking
        _LOGGER.debug("_execute_with_startup_delay :: waiting %fs before starting position tracking", startup_delay)
        try:
            await sleep(startup_delay)
            _LOGGER.debug("_execute_with_startup_delay :: startup delay complete, starting position tracking")
            start_callback()
            self._startup_delay_task = None
        except asyncio.CancelledError:
            _LOGGER.debug("_execute_with_startup_delay :: startup delay cancelled")
            self._startup_delay_task = None
            raise

    @property
    def name(self):
        """Return the name of the cover."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique id."""
        return "cover_timebased_uuid_" + self._unique_id

    @property
    def device_class(self):
        """Return the device class of the cover."""
        return None

    @property
    def extra_state_attributes(self):
        """Return the device state attributes."""
        attr = {}
        if self._travel_moves_with_tilt is not None:
            attr[CONF_TRAVEL_MOVES_WITH_TILT] = self._travel_moves_with_tilt
        if self._travel_time_down is not None:
            attr[CONF_TRAVELLING_TIME_DOWN] = self._travel_time_down
        if self._travel_time_up is not None:
            attr[CONF_TRAVELLING_TIME_UP] = self._travel_time_up
        if self._tilting_time_down is not None:
            attr[CONF_TILTING_TIME_DOWN] = self._tilting_time_down
        if self._tilting_time_up is not None:
            attr[CONF_TILTING_TIME_UP] = self._tilting_time_up
        if self._travel_delay_at_end is not None:
            attr[CONF_TRAVEL_DELAY_AT_END] = self._travel_delay_at_end
        if self._min_movement_time is not None:
            attr[CONF_MIN_MOVEMENT_TIME] = self._min_movement_time
        if self._travel_startup_delay is not None:
            attr[CONF_TRAVEL_STARTUP_DELAY] = self._travel_startup_delay
        if self._tilt_startup_delay is not None:
            attr[CONF_TILT_STARTUP_DELAY] = self._tilt_startup_delay
        return attr

    @property
    def current_cover_position(self) -> int | None:
        """Return the current position of the cover."""
        current_position = self.travel_calc.current_position()
        return 100 - current_position if current_position is not None else None

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return the current tilt of the cover."""
        if self._has_tilt_support():
            current_position = self.tilt_calc.current_position()
            return 100 - current_position if current_position is not None else None
        return None

    @property
    def is_opening(self):
        """Return if the cover is opening or not."""
        return (
            self.travel_calc.is_traveling()
            and self.travel_calc.travel_direction == TravelStatus.DIRECTION_UP
        ) or (
            self._has_tilt_support()
            and self.tilt_calc.is_traveling()
            and self.tilt_calc.travel_direction == TravelStatus.DIRECTION_UP
        )

    @property
    def is_closing(self):
        """Return if the cover is closing or not."""
        return (
            self.travel_calc.is_traveling()
            and self.travel_calc.travel_direction == TravelStatus.DIRECTION_DOWN
        ) or (
            self._has_tilt_support()
            and self.tilt_calc.is_traveling()
            and self.tilt_calc.travel_direction == TravelStatus.DIRECTION_DOWN
        )

    @property
    def is_closed(self):
        """Return if the cover is closed."""
        if not self._has_tilt_support():
            return self.travel_calc.is_closed()
        
        return self.travel_calc.is_closed() and self.tilt_calc.is_closed()

    @property
    def assumed_state(self):
        """Return True because covers can be stopped midway."""
        return True

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Flag supported features."""
        supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )
        if self.current_cover_position is not None:
            supported_features |= CoverEntityFeature.SET_POSITION

        if self._has_tilt_support():
            supported_features |= (
                CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.STOP_TILT
            )
            if self.current_cover_tilt_position is not None:
                supported_features |= CoverEntityFeature.SET_TILT_POSITION

        return supported_features

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        if ATTR_POSITION in kwargs:
            position = kwargs[ATTR_POSITION]
            _LOGGER.debug("async_set_cover_position: %d", position)
            await self.set_position(position)

    async def async_set_cover_tilt_position(self, **kwargs):
        """Move the cover tilt to a specific position."""
        if ATTR_TILT_POSITION in kwargs:
            position = kwargs[ATTR_TILT_POSITION]
            _LOGGER.debug("async_set_cover_tilt_position: %d", position)
            await self.set_tilt_position(position)

    async def async_close_cover(self, **kwargs):
        """Turn the device close."""
        _LOGGER.debug("async_close_cover")
        
        current_travel_position = self.travel_calc.current_position()
        if current_travel_position is None or current_travel_position < 100:
            if self._startup_delay_task and not self._startup_delay_task.done():
                if self._last_command == SERVICE_OPEN_COVER:
                    _LOGGER.debug("async_close_cover :: direction change, cancelling startup delay")
                    self._cancel_startup_delay_task()
                    await self._async_handle_command(SERVICE_STOP_COVER)
                else:
                    # EDGE CASE: Tilt→travel switch during startup delay - ignore startup_delay difference
                    _LOGGER.debug("async_close_cover :: startup delay already active, not restarting")
                    return
            
            relay_was_on = self._cancel_delay_task()
            if relay_was_on:
                await self._async_handle_command(SERVICE_STOP_COVER)
            
            travel_distance = 100 - (current_travel_position if current_travel_position is not None else 0)
            movement_time = (travel_distance / 100.0) * self._travel_time_down
            
            _LOGGER.debug(
                "async_close_cover :: travel_distance=%f%%, movement_time=%fs",
                travel_distance, movement_time
            )
            
            self._last_command = SERVICE_CLOSE_COVER
            
            tilt_target = None
            if self._has_tilt_support():
                tilt_distance = (movement_time / self._tilting_time_down) * 100.0
                current_tilt_position = self.tilt_calc.current_position()
                tilt_target = min(100, current_tilt_position + tilt_distance)
                _LOGGER.debug(
                    "async_close_cover :: tilt_distance=%f%%, new_tilt_pos=%f",
                    tilt_distance, tilt_target
                )
            
            await self._async_handle_command(SERVICE_CLOSE_COVER)
            
            if self._travel_startup_delay and self._travel_startup_delay > 0:
                def start_movement():
                    self.travel_calc.start_travel_down()
                    if tilt_target is not None:
                        self.tilt_calc.start_travel(int(tilt_target))
                    self.start_auto_updater()
                
                self._startup_delay_task = self.hass.async_create_task(
                    self._execute_with_startup_delay(self._travel_startup_delay, start_movement)
                )
            else:
                self.travel_calc.start_travel_down()
                if tilt_target is not None:
                    self.tilt_calc.start_travel(int(tilt_target))
                self.start_auto_updater()

    async def async_open_cover(self, **kwargs):
        """Turn the device open."""
        _LOGGER.debug("async_open_cover")
        
        current_travel_position = self.travel_calc.current_position()
        if current_travel_position is None or current_travel_position > 0:
            if self._startup_delay_task and not self._startup_delay_task.done():
                if self._last_command == SERVICE_CLOSE_COVER:
                    _LOGGER.debug("async_open_cover :: direction change, cancelling startup delay")
                    self._cancel_startup_delay_task()
                    await self._async_handle_command(SERVICE_STOP_COVER)
                else:
                    # EDGE CASE: Tilt→travel switch during startup delay - ignore startup_delay difference
                    _LOGGER.debug("async_open_cover :: startup delay already active, not restarting")
                    return
            
            relay_was_on = self._cancel_delay_task()
            if relay_was_on:
                await self._async_handle_command(SERVICE_STOP_COVER)
            
            travel_distance = (current_travel_position if current_travel_position is not None else 100)
            movement_time = (travel_distance / 100.0) * self._travel_time_up
            
            _LOGGER.debug(
                "async_open_cover :: travel_distance=%f%%, movement_time=%fs",
                travel_distance, movement_time
            )
            
            self._last_command = SERVICE_OPEN_COVER
            
            tilt_target = None
            if self._has_tilt_support():
                tilt_distance = (movement_time / self._tilting_time_up) * 100.0
                current_tilt_position = self.tilt_calc.current_position()
                tilt_target = max(0, current_tilt_position - tilt_distance)
                _LOGGER.debug(
                    "async_open_cover :: tilt_distance=%f%%, new_tilt_pos=%f",
                    tilt_distance, tilt_target
                )
            
            await self._async_handle_command(SERVICE_OPEN_COVER)
            
            if self._travel_startup_delay and self._travel_startup_delay > 0:
                def start_movement():
                    self.travel_calc.start_travel_up()
                    if tilt_target is not None:
                        self.tilt_calc.start_travel(int(tilt_target))
                    self.start_auto_updater()
                
                self._startup_delay_task = self.hass.async_create_task(
                    self._execute_with_startup_delay(self._travel_startup_delay, start_movement)
                )
            else:
                self.travel_calc.start_travel_up()
                if tilt_target is not None:
                    self.tilt_calc.start_travel(int(tilt_target))
                self.start_auto_updater()

    async def async_close_cover_tilt(self, **kwargs):
        """Turn the device close."""
        _LOGGER.debug("async_close_cover_tilt")
        
        if self._startup_delay_task and not self._startup_delay_task.done():
            if self._last_command == SERVICE_OPEN_COVER:
                _LOGGER.debug("async_close_cover_tilt :: direction change, cancelling startup delay")
                self._cancel_startup_delay_task()
                await self._async_handle_command(SERVICE_STOP_COVER)
            else:
                # EDGE CASE: Travel→tilt switch during startup delay - ignore startup_delay difference
                _LOGGER.debug("async_close_cover_tilt :: startup delay already active, not restarting")
                return
        
        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)
        
        self._stop_travel_if_traveling()
        
        current_tilt_position = self.tilt_calc.current_position()
        if current_tilt_position is None or current_tilt_position < 100:
            tilt_distance = 100 - (current_tilt_position if current_tilt_position is not None else 0)
            movement_time = (tilt_distance / 100.0) * self._tilting_time_down
            
            travel_target = None
            if self._travel_moves_with_tilt:
                travel_distance = (movement_time / self._travel_time_down) * 100.0
                current_travel_position = self.travel_calc.current_position()
                travel_target = min(100, current_travel_position + travel_distance)
            
            _LOGGER.debug(
                "async_close_cover_tilt :: tilt_distance=%f%%, movement_time=%fs, travel_distance=%f%%, new_travel_pos=%s",
                tilt_distance, movement_time, 
                (movement_time / self._travel_time_down) * 100.0 if self._travel_moves_with_tilt else 0,
                travel_target if travel_target is not None else "N/A"
            )
            
            self._last_command = SERVICE_CLOSE_COVER
            
            await self._async_handle_command(SERVICE_CLOSE_COVER)
            
            if self._tilt_startup_delay and self._tilt_startup_delay > 0:
                def start_movement():
                    self.tilt_calc.start_travel_down()
                    if travel_target is not None:
                        self.travel_calc.start_travel(int(travel_target))
                    self.start_auto_updater()
                
                self._startup_delay_task = self.hass.async_create_task(
                    self._execute_with_startup_delay(self._tilt_startup_delay, start_movement)
                )
            else:
                self.tilt_calc.start_travel_down()
                if travel_target is not None:
                    self.travel_calc.start_travel(int(travel_target))
                self.start_auto_updater()

    async def async_open_cover_tilt(self, **kwargs):
        """Turn the device open."""
        _LOGGER.debug("async_open_cover_tilt")
        
        if self._startup_delay_task and not self._startup_delay_task.done():
            if self._last_command == SERVICE_CLOSE_COVER:
                _LOGGER.debug("async_open_cover_tilt :: direction change, cancelling startup delay")
                self._cancel_startup_delay_task()
                await self._async_handle_command(SERVICE_STOP_COVER)
            else:
                # EDGE CASE: Travel→tilt switch during startup delay - ignore startup_delay difference
                _LOGGER.debug("async_open_cover_tilt :: startup delay already active, not restarting")
                return
        
        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)
        
        self._stop_travel_if_traveling()
        
        current_tilt_position = self.tilt_calc.current_position()
        if current_tilt_position is None or current_tilt_position > 0:
            tilt_distance = (current_tilt_position if current_tilt_position is not None else 100)
            movement_time = (tilt_distance / 100.0) * self._tilting_time_up
            
            travel_target = None
            if self._travel_moves_with_tilt:
                travel_distance = (movement_time / self._travel_time_up) * 100.0
                current_travel_position = self.travel_calc.current_position()
                travel_target = max(0, current_travel_position - travel_distance)
            
            _LOGGER.debug(
                "async_open_cover_tilt :: tilt_distance=%f%%, movement_time=%fs, travel_distance=%f%%, new_travel_pos=%s",
                tilt_distance, movement_time,
                (movement_time / self._travel_time_up) * 100.0 if self._travel_moves_with_tilt else 0,
                travel_target if travel_target is not None else "N/A"
            )
            
            self._last_command = SERVICE_OPEN_COVER
            
            await self._async_handle_command(SERVICE_OPEN_COVER)
            
            if self._tilt_startup_delay and self._tilt_startup_delay > 0:
                def start_movement():
                    self.tilt_calc.start_travel_up()
                    if travel_target is not None:
                        self.travel_calc.start_travel(int(travel_target))
                    self.start_auto_updater()
                
                self._startup_delay_task = self.hass.async_create_task(
                    self._execute_with_startup_delay(self._tilt_startup_delay, start_movement)
                )
            else:
                self.tilt_calc.start_travel_up()
                if travel_target is not None:
                    self.travel_calc.start_travel(int(travel_target))
                self.start_auto_updater()

    async def async_stop_cover(self, **kwargs):
        """Turn the device stop."""
        _LOGGER.debug("async_stop_cover")
        
        self._cancel_startup_delay_task()
        self._cancel_delay_task()
        self._handle_stop()
        self._enforce_tilt_constraints()
        self._last_command = None
        
        await self._async_handle_command(SERVICE_STOP_COVER)

    async def set_position(self, position):
        """Move cover to a designated position."""
        _LOGGER.debug("set_position")
        
        current_travel_position = self.travel_calc.current_position()
        new_travel_position = 100 - position
        _LOGGER.debug(
            "set_position :: current_position: %d, new_position: %d",
            current_travel_position,
            position,
        )
        command = None
        if current_travel_position is None or new_travel_position > current_travel_position:
            command = SERVICE_CLOSE_COVER
            travel_time = self._travel_time_down
            tilt_time = self._tilting_time_down if self._has_tilt_support() else None
            startup_delay = self._travel_startup_delay
        elif new_travel_position < current_travel_position:
            command = SERVICE_OPEN_COVER
            travel_time = self._travel_time_up
            tilt_time = self._tilting_time_up if self._has_tilt_support() else None
            startup_delay = self._travel_startup_delay
        else:
            return
            
        if command is not None:
            is_direction_change = False
            
            if self._last_command is not None and self._last_command != command:
                is_direction_change = True
                _LOGGER.debug("set_position :: direction change detected (%s → %s)", self._last_command, command)
            
            # EDGE CASE: User adjusts target position during startup (e.g., 50%→60%)
            # We don't restart the delay since motor is already starting up
            if (self._startup_delay_task and not self._startup_delay_task.done() 
                and not is_direction_change):
                _LOGGER.debug("set_position :: startup delay already active for same direction, not restarting")
                return
            
            if is_direction_change and self._startup_delay_task and not self._startup_delay_task.done():
                self._cancel_startup_delay_task()
                await self._async_handle_command(SERVICE_STOP_COVER)
            
            if is_direction_change and self.travel_calc.is_traveling():
                _LOGGER.debug("set_position :: stopping active travel movement")
                self.travel_calc.stop()
                self.stop_auto_updater()
                if self._has_tilt_support() and self.tilt_calc.is_traveling():
                    self.tilt_calc.stop()
                await self._async_handle_command(SERVICE_STOP_COVER)
                
                current_travel_position = self.travel_calc.current_position()
                _LOGGER.debug("set_position :: position after stop: %d", 100 - current_travel_position)
                
                if new_travel_position == current_travel_position:
                    _LOGGER.debug("set_position :: already at target after stop, no movement needed")
                    return
            
            relay_was_on = self._cancel_delay_task()
            if relay_was_on:
                await self._async_handle_command(SERVICE_STOP_COVER)
            
            travel_distance = abs(new_travel_position - current_travel_position)
            movement_time = (travel_distance / 100.0) * travel_time
            
            is_to_endpoint = (new_travel_position == 0 or new_travel_position == 100)
            if (
                self._min_movement_time is not None
                and self._min_movement_time > 0
                and not is_to_endpoint
                and movement_time < self._min_movement_time
            ):
                _LOGGER.info(
                    "set_position :: movement too short (%fs < %fs), ignoring - from %d%% to %d%%",
                    movement_time,
                    self._min_movement_time,
                    100 - current_travel_position,
                    position,
                )
                self.async_write_ha_state()
                return
            
            _LOGGER.debug(
                "set_position :: travel_distance=%f%%, movement_time=%fs",
                travel_distance, movement_time
            )
            
            self._last_command = command
            
            tilt_target = None
            if self._has_tilt_support():
                tilt_distance = (movement_time / tilt_time) * 100.0
                current_tilt_position = self.tilt_calc.current_position()
                if command == SERVICE_CLOSE_COVER:
                    tilt_target = min(100, current_tilt_position + tilt_distance)
                else:
                    tilt_target = max(0, current_tilt_position - tilt_distance)
                
                _LOGGER.debug(
                    "set_position :: tilt_distance=%f%%, new_tilt_pos=%f",
                    tilt_distance, tilt_target
                )
            
            await self._async_handle_command(command)
            
            if startup_delay and startup_delay > 0:
                def start_movement():
                    self.travel_calc.start_travel(new_travel_position)
                    if tilt_target is not None:
                        self.tilt_calc.start_travel(int(tilt_target))
                    self.start_auto_updater()
                
                self._startup_delay_task = self.hass.async_create_task(
                    self._execute_with_startup_delay(startup_delay, start_movement)
                )
            else:
                self.travel_calc.start_travel(new_travel_position)
                if tilt_target is not None:
                    self.tilt_calc.start_travel(int(tilt_target))
                self.start_auto_updater()
        return

    async def set_tilt_position(self, position):
        """Move cover tilt to a designated position."""
        _LOGGER.debug("set_tilt_position")
        
        current_tilt_position = self.tilt_calc.current_position()
        new_tilt_position = 100 - position
        _LOGGER.debug(
            "set_tilt_position :: current_position: %d, new_position: %d",
            current_tilt_position,
            new_tilt_position,
        )
        command = None
        if current_tilt_position is None or new_tilt_position > current_tilt_position:
            command = SERVICE_CLOSE_COVER
            tilt_time = self._tilting_time_down
            travel_time = self._travel_time_down
            startup_delay = self._tilt_startup_delay
        elif new_tilt_position < current_tilt_position:
            command = SERVICE_OPEN_COVER
            tilt_time = self._tilting_time_up
            travel_time = self._travel_time_up
            startup_delay = self._tilt_startup_delay
        else:
            return
            
        if command is not None:
            is_direction_change = False
            
            if self._last_command is not None and self._last_command != command:
                is_direction_change = True
                _LOGGER.debug("set_tilt_position :: direction change detected (%s → %s)", self._last_command, command)
            
            # EDGE CASE: User adjusts tilt target during startup (e.g., 50%→60% tilt)
            # We don't restart the delay since motor is already starting up
            if (self._startup_delay_task and not self._startup_delay_task.done() 
                and not is_direction_change):
                _LOGGER.debug("set_tilt_position :: startup delay already active for same direction, not restarting")
                return
            
            if is_direction_change and self._startup_delay_task and not self._startup_delay_task.done():
                self._cancel_startup_delay_task()
                await self._async_handle_command(SERVICE_STOP_COVER)
            
            if is_direction_change:
                if self.tilt_calc.is_traveling():
                    _LOGGER.debug("set_tilt_position :: stopping active tilt movement")
                    self.tilt_calc.stop()
                if self.travel_calc.is_traveling():
                    self.travel_calc.stop()
                self.stop_auto_updater()
                await self._async_handle_command(SERVICE_STOP_COVER)
                
                current_tilt_position = self.tilt_calc.current_position()
                _LOGGER.debug("set_tilt_position :: tilt position after stop: %d", 100 - current_tilt_position)
                
                if new_tilt_position == current_tilt_position:
                    _LOGGER.debug("set_tilt_position :: already at target after stop, no movement needed")
                    return
            
            relay_was_on = self._cancel_delay_task()
            if relay_was_on:
                await self._async_handle_command(SERVICE_STOP_COVER)
            
            if not is_direction_change:
                self._stop_travel_if_traveling()
            
            tilt_distance = abs(new_tilt_position - current_tilt_position)
            movement_time = (tilt_distance / 100.0) * tilt_time
            
            travel_target = None
            if self._travel_moves_with_tilt:
                travel_distance = (movement_time / travel_time) * 100.0
                current_travel_position = self.travel_calc.current_position()
                if command == SERVICE_CLOSE_COVER:
                    travel_target = min(100, current_travel_position + travel_distance)
                else:
                    travel_target = max(0, current_travel_position - travel_distance)
            
            is_to_endpoint = (new_tilt_position == 0 or new_tilt_position == 100)
            if (
                self._min_movement_time is not None
                and self._min_movement_time > 0
                and not is_to_endpoint
                and movement_time < self._min_movement_time
            ):
                _LOGGER.info(
                    "set_tilt_position :: movement too short (%fs < %fs), ignoring - from %d%% to %d%%",
                    movement_time,
                    self._min_movement_time,
                    100 - current_tilt_position,
                    position,
                )
                self.async_write_ha_state()
                return
            
            self._last_command = command
            
            _LOGGER.debug(
                "set_tilt_position :: tilt_distance=%f%%, movement_time=%fs, travel_distance=%f%%, new_travel_pos=%s",
                tilt_distance, movement_time,
                (movement_time / travel_time) * 100.0 if self._travel_moves_with_tilt else 0,
                travel_target if travel_target is not None else "N/A"
            )
            
            await self._async_handle_command(command)
            
            if startup_delay and startup_delay > 0:
                def start_movement():
                    self.tilt_calc.start_travel(new_tilt_position)
                    if travel_target is not None:
                        self.travel_calc.start_travel(int(travel_target))
                    self.start_auto_updater()
                
                self._startup_delay_task = self.hass.async_create_task(
                    self._execute_with_startup_delay(startup_delay, start_movement)
                )
            else:
                self.tilt_calc.start_travel(new_tilt_position)
                if travel_target is not None:
                    self.travel_calc.start_travel(int(travel_target))
                self.start_auto_updater()
        return

    def start_auto_updater(self):
        """Start the autoupdater to update HASS while cover is moving."""
        _LOGGER.debug("start_auto_updater")
        if self._unsubscribe_auto_updater is None:
            _LOGGER.debug("init _unsubscribe_auto_updater")
            interval = timedelta(seconds=0.1)
            self._unsubscribe_auto_updater = async_track_time_interval(
                self.hass, self.auto_updater_hook, interval
            )

    @callback
    def auto_updater_hook(self, now):
        """Call for the autoupdater."""
        _LOGGER.debug("auto_updater_hook")
        self.async_schedule_update_ha_state()
        if self.position_reached():
            _LOGGER.debug("auto_updater_hook :: position_reached")
            self.stop_auto_updater()
        self.hass.async_create_task(self.auto_stop_if_necessary())

    def stop_auto_updater(self):
        """Stop the autoupdater."""
        _LOGGER.debug("stop_auto_updater")
        if self._unsubscribe_auto_updater is not None:
            self._unsubscribe_auto_updater()
            self._unsubscribe_auto_updater = None

    def position_reached(self):
        """Return if cover has reached its final position."""
        return self.travel_calc.position_reached() and (
            not self._has_tilt_support() or self.tilt_calc.position_reached()
        )

    def _has_tilt_support(self):
        """Return if cover has tilt support."""
        return self._tilting_time_down is not None and self._tilting_time_up is not None

    def _enforce_tilt_constraints(self):
        """Enforce tilt position constraints at travel boundaries."""
        if not self._has_tilt_support():
            return

        if not self._travel_moves_with_tilt:
            return
        
        current_travel = self.travel_calc.current_position()
        current_tilt = self.tilt_calc.current_position()
        
        if current_travel == 0 and current_tilt != 0:
            _LOGGER.debug(
                "_enforce_tilt_constraints :: Travel at 0%%, forcing tilt to 0%% (was %d%%)",
                current_tilt
            )
            self.tilt_calc.set_position(0)
        
        elif current_travel == 100 and current_tilt != 100:
            _LOGGER.debug(
                "_enforce_tilt_constraints :: Travel at 100%%, forcing tilt to 100%% (was %d%%)",
                current_tilt
            )
            self.tilt_calc.set_position(100)

    async def auto_stop_if_necessary(self):
        """Do auto stop if necessary."""
        if self.position_reached():
            _LOGGER.debug("auto_stop_if_necessary :: calling stop command")
            self.travel_calc.stop()
            if self._has_tilt_support():
                self.tilt_calc.stop()
            
            self._enforce_tilt_constraints()
            
            current_travel = self.travel_calc.current_position()
            if self._travel_delay_at_end is not None and self._travel_delay_at_end > 0 and (current_travel == 0 or current_travel == 100):
                _LOGGER.debug(
                    "auto_stop_if_necessary :: at endpoint (position=%d), delaying relay stop by %fs",
                    current_travel,
                    self._travel_delay_at_end
                )
                self._delay_task = self.hass.async_create_task(
                    self._delayed_stop(self._travel_delay_at_end)
                )
            else:
                await self._async_handle_command(SERVICE_STOP_COVER)
    
    async def _delayed_stop(self, delay):
        """Stop the relay after a delay."""
        _LOGGER.debug("_delayed_stop :: waiting %fs before stopping relay", delay)
        try:
            await sleep(delay)
            _LOGGER.debug("_delayed_stop :: delay complete, stopping relay")
            await self._async_handle_command(SERVICE_STOP_COVER)
            self._delay_task = None
        except asyncio.CancelledError:
            _LOGGER.debug("_delayed_stop :: delay cancelled")
            self._delay_task = None
            raise

    async def set_known_position(self, **kwargs):
        """We want to do a few things when we get a position"""
        position = kwargs[ATTR_POSITION]
        self._handle_stop()
        await self._async_handle_command(SERVICE_STOP_COVER)
        self.travel_calc.set_position(position)
        self._enforce_tilt_constraints()

    async def set_known_tilt_position(self, **kwargs):
        """We want to do a few things when we get a position"""
        position = kwargs[ATTR_TILT_POSITION]
        await self._async_handle_command(SERVICE_STOP_COVER)
        self.tilt_calc.set_position(position)

    async def _async_handle_command(self, command, *args):
        if command == SERVICE_CLOSE_COVER:
            cmd = "DOWN"
            self._state = False
            if self._cover_entity_id is not None:
                await self.hass.services.async_call(
                    "cover",
                    "close_cover",
                    {"entity_id": self._cover_entity_id},
                    False,
                )
            else:
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_off",
                    {"entity_id": self._open_switch_entity_id},
                    False,
                )
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_on",
                    {"entity_id": self._close_switch_entity_id},
                    False,
                )
                if self._stop_switch_entity_id is not None:
                    await self.hass.services.async_call(
                        "homeassistant",
                        "turn_off",
                        {"entity_id": self._stop_switch_entity_id},
                        False,
                    )

                if self._is_button:
                    await sleep(1)

                    await self.hass.services.async_call(
                        "homeassistant",
                        "turn_off",
                        {"entity_id": self._close_switch_entity_id},
                        False,
                    )

        elif command == SERVICE_OPEN_COVER:
            cmd = "UP"
            self._state = True
            if self._cover_entity_id is not None:
                await self.hass.services.async_call(
                    "cover",
                    "open_cover",
                    {"entity_id": self._cover_entity_id},
                    False,
                )
            else:
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_off",
                    {"entity_id": self._close_switch_entity_id},
                    False,
                )
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_on",
                    {"entity_id": self._open_switch_entity_id},
                    False,
                )
                if self._stop_switch_entity_id is not None:
                    await self.hass.services.async_call(
                        "homeassistant",
                        "turn_off",
                        {"entity_id": self._stop_switch_entity_id},
                        False,
                    )
                if self._is_button:
                    await sleep(1)

                    await self.hass.services.async_call(
                        "homeassistant",
                        "turn_off",
                        {"entity_id": self._open_switch_entity_id},
                        False,
                    )

        elif command == SERVICE_STOP_COVER:
            cmd = "STOP"
            self._state = True
            if self._cover_entity_id is not None:
                await self.hass.services.async_call(
                    "cover",
                    "stop_cover",
                    {"entity_id": self._cover_entity_id},
                    False,
                )
            else:
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_off",
                    {"entity_id": self._close_switch_entity_id},
                    False,
                )
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_off",
                    {"entity_id": self._open_switch_entity_id},
                    False,
                )
                if self._stop_switch_entity_id is not None:
                    await self.hass.services.async_call(
                        "homeassistant",
                        "turn_on",
                        {"entity_id": self._stop_switch_entity_id},
                        False,
                    )

                    if self._is_button:
                        await sleep(1)

                        await self.hass.services.async_call(
                            "homeassistant",
                            "turn_off",
                            {"entity_id": self._stop_switch_entity_id},
                            False,
                        )

        _LOGGER.debug("_async_handle_command :: %s", cmd)

        self.async_write_ha_state()
