"""Cover time based"""

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
CONF_TRAVELLING_TIME_DOWN = "travelling_time_down"
CONF_TRAVELLING_TIME_UP = "travelling_time_up"
CONF_TILTING_TIME_DOWN = "tilting_time_down"
CONF_TILTING_TIME_UP = "tilting_time_up"
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
    vol.Optional(
        CONF_TRAVELLING_TIME_DOWN, default=DEFAULT_TRAVEL_TIME
    ): cv.positive_int,
    vol.Optional(CONF_TRAVELLING_TIME_UP, default=DEFAULT_TRAVEL_TIME): cv.positive_int,
    vol.Optional(CONF_TILTING_TIME_DOWN, default=None): vol.Any(
        cv.positive_float, None
    ),
    vol.Optional(CONF_TILTING_TIME_UP, default=None): vol.Any(cv.positive_float, None),
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

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
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
    for device_id, config in domain_config[CONF_DEVICES].items():
        name = config.pop(CONF_NAME)

        travel_time_down = config.pop(CONF_TRAVELLING_TIME_DOWN)
        travel_time_up = config.pop(CONF_TRAVELLING_TIME_UP)
        tilt_time_down = config.pop(CONF_TILTING_TIME_DOWN)
        tilt_time_up = config.pop(CONF_TILTING_TIME_UP)

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
            travel_time_down,
            travel_time_up,
            tilt_time_down,
            tilt_time_up,
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
        travel_time_down,
        travel_time_up,
        tilt_time_down,
        tilt_time_up,
        open_switch_entity_id,
        close_switch_entity_id,
        stop_switch_entity_id,
        is_button,
        cover_entity_id,
    ):
        """Initialize the cover."""
        self._unique_id = device_id

        self._travel_time_down = travel_time_down
        self._travel_time_up = travel_time_up
        self._tilting_time_down = tilt_time_down
        self._tilting_time_up = tilt_time_up

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
        if self._travel_time_down is not None:
            attr[CONF_TRAVELLING_TIME_DOWN] = self._travel_time_down
        if self._travel_time_up is not None:
            attr[CONF_TRAVELLING_TIME_UP] = self._travel_time_up
        if self._tilting_time_down is not None:
            attr[CONF_TILTING_TIME_DOWN] = self._tilting_time_down
        if self._tilting_time_up is not None:
            attr[CONF_TILTING_TIME_UP] = self._tilting_time_up
        return attr

    @property
    def current_cover_position(self) -> int | None:
        """Return the current position of the cover."""
        current_position = self.travel_calc.current_position()
        # HA has an inverted position logic compared to XKNX
        return 100 - current_position if current_position is not None else None

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return the current tilt of the cover."""
        if self._has_tilt_support():
            current_position = self.tilt_calc.current_position()
            # HA has an inverted position logic compared to XKNX
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
        return self.travel_calc.is_closed()

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
        current_position = self.travel_calc.current_position()
        if current_position is None or current_position < 100:
            self.travel_calc.start_travel_down()
            self.start_auto_updater()
            self._update_tilt_before_travel(SERVICE_CLOSE_COVER)
            await self._async_handle_command(SERVICE_CLOSE_COVER)

    async def async_open_cover(self, **kwargs):
        """Turn the device open."""
        _LOGGER.debug("async_open_cover")
        current_position = self.travel_calc.current_position()
        if current_position is None or current_position > 0:
            self.travel_calc.start_travel_up()
            self.start_auto_updater()
            self._update_tilt_before_travel(SERVICE_OPEN_COVER)
            await self._async_handle_command(SERVICE_OPEN_COVER)

    async def async_close_cover_tilt(self, **kwargs):
        """Turn the device close."""
        _LOGGER.debug("async_close_cover_tilt")
        current_position = self.tilt_calc.current_position()
        if current_position is None or current_position < 100:
            self.tilt_calc.start_travel_down()
            self.start_auto_updater()
            await self._async_handle_command(SERVICE_CLOSE_COVER)

    async def async_open_cover_tilt(self, **kwargs):
        """Turn the device open."""
        _LOGGER.debug("async_open_cover_tilt")
        current_position = self.tilt_calc.current_position()
        if current_position is None or current_position > 0:
            self.tilt_calc.start_travel_up()
            self.start_auto_updater()
            await self._async_handle_command(SERVICE_OPEN_COVER)

    async def async_stop_cover(self, **kwargs):
        """Turn the device stop."""
        _LOGGER.debug("async_stop_cover")
        self._handle_stop()
        await self._async_handle_command(SERVICE_STOP_COVER)

    async def set_position(self, position):
        """Move cover to a designated position."""
        _LOGGER.debug("set_position")
        current_position = self.travel_calc.current_position()
        # HA has an inverted position logic compared to XKNX
        new_position = 100 - position
        _LOGGER.debug(
            "set_position :: current_position: %d, new_position: %d",
            current_position,
            position,
        )
        command = None
        if current_position is None or new_position > current_position:
            command = SERVICE_CLOSE_COVER
        elif new_position < current_position:
            command = SERVICE_OPEN_COVER
        if command is not None:
            self.start_auto_updater()
            self.travel_calc.start_travel(new_position)
            _LOGGER.debug("set_position :: command %s", command)
            self._update_tilt_before_travel(command)
            await self._async_handle_command(command)
        return

    async def set_tilt_position(self, position):
        """Move cover tilt to a designated position."""
        _LOGGER.debug("set_tilt_position")
        current_position = self.tilt_calc.current_position()
        # HA has an inverted position logic compared to XKNX
        new_position = 100 - position
        _LOGGER.debug(
            "set_tilt_position :: current_position: %d, new_position: %d",
            current_position,
            new_position,
        )
        command = None
        if current_position is None or new_position > current_position:
            command = SERVICE_CLOSE_COVER
        elif new_position < current_position:
            command = SERVICE_OPEN_COVER
        if command is not None:
            self.start_auto_updater()
            self.tilt_calc.start_travel(new_position)
            _LOGGER.debug("set_tilt_position :: command %s", command)
            await self._async_handle_command(command)
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

    def _update_tilt_before_travel(self, command):
        """Updating tilt before travel."""
        if self._has_tilt_support():
            _LOGGER.debug("_update_tilt_before_travel :: command %s", command)
            if command == SERVICE_OPEN_COVER:
                self.tilt_calc.set_position(0)
            elif command == SERVICE_CLOSE_COVER:
                self.tilt_calc.set_position(100)

    async def auto_stop_if_necessary(self):
        """Do auto stop if necessary."""
        if self.position_reached():
            # Calculation of the current position (reversed because Home Assistant uses 100=open)
            current_position = 100 - self.travel_calc.current_position()

            # If the position is at 0% or 100%, we do NOT make a STOP.
            if current_position in (0, 100):
                _LOGGER.debug(
                    "auto_stop_if_necessary :: end reached (%d%%), skip STOP",
                    current_position,
                )
                # We only stop internal calculations.
                self.travel_calc.stop()
                if self._has_tilt_support():
                    self.tilt_calc.stop()
                # On stop l’auto-updater manuellement
                self.stop_auto_updater()
                return

            # Otherwise, we perform the classic stop.
            _LOGGER.debug("auto_stop_if_necessary :: calling stop command")
            self.travel_calc.stop()
            if self._has_tilt_support():
                self.tilt_calc.stop()
            await self._async_handle_command(SERVICE_STOP_COVER)


    async def set_known_position(self, **kwargs):
        """We want to do a few things when we get a position"""
        position = kwargs[ATTR_POSITION]
        self._handle_stop()
        await self._async_handle_command(SERVICE_STOP_COVER)
        self.travel_calc.set_position(position)

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
                    # The close_switch_entity_id should be turned off one second after being turned on
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
                    # The open_switch_entity_id should be turned off one second after being turned on
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
                        # The stop_switch_entity_id should be turned off one second after being turned on
                        await sleep(1)

                        await self.hass.services.async_call(
                            "homeassistant",
                            "turn_off",
                            {"entity_id": self._stop_switch_entity_id},
                            False,
                        )

        _LOGGER.debug("_async_handle_command :: %s", cmd)

        # Update state of entity
        self.async_write_ha_state()

