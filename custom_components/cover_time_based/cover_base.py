"""Base class for time-based cover entities."""

import asyncio
import logging
import time
from abc import abstractmethod
from asyncio import sleep
from datetime import timedelta

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_CURRENT_TILT_POSITION,
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
from xknx.devices import TravelCalculator, TravelStatus

from .calibration import CalibrationState

_LOGGER = logging.getLogger(__name__)

# Configuration constants used by extra_state_attributes.
# These are also defined in cover.py for YAML/UI config schemas,
# but we define them here to avoid circular imports.
CONF_TRAVEL_MOVES_WITH_TILT = "travel_moves_with_tilt"
CONF_TRAVELLING_TIME_DOWN = "travelling_time_down"
CONF_TRAVELLING_TIME_UP = "travelling_time_up"
CONF_TILTING_TIME_DOWN = "tilting_time_down"
CONF_TILTING_TIME_UP = "tilting_time_up"
CONF_TRAVEL_MOTOR_OVERHEAD = "travel_motor_overhead"
CONF_TILT_MOTOR_OVERHEAD = "tilt_motor_overhead"
CONF_MIN_MOVEMENT_TIME = "min_movement_time"


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
        travel_motor_overhead,
        tilt_motor_overhead,
        min_movement_time,
    ):
        """Initialize the cover."""
        self._unique_id = device_id

        self._travel_moves_with_tilt = travel_moves_with_tilt
        self._travel_time_down = travel_time_down
        self._travel_time_up = travel_time_up
        self._tilting_time_down = tilt_time_down
        self._tilting_time_up = tilt_time_up
        self._travel_motor_overhead = travel_motor_overhead
        self._tilt_motor_overhead = tilt_motor_overhead
        self._min_movement_time = min_movement_time

        # Derive internal delay values by splitting overhead 50/50
        self._travel_startup_delay = (
            travel_motor_overhead / 2 if travel_motor_overhead else None
        )
        self._travel_delay_at_end = (
            travel_motor_overhead / 2 if travel_motor_overhead else None
        )
        self._tilt_startup_delay = (
            tilt_motor_overhead / 2 if tilt_motor_overhead else None
        )

        if name:
            self._name = name
        else:
            self._name = device_id

        self._config_entry_id = None
        self._calibration = None
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

    async def async_will_remove_from_hass(self):
        """Clean up when entity is removed."""
        if self._calibration is not None:
            if (
                self._calibration.timeout_task
                and not self._calibration.timeout_task.done()
            ):
                self._calibration.timeout_task.cancel()
            if (
                self._calibration.automation_task
                and not self._calibration.automation_task.done()
            ):
                self._calibration.automation_task.cancel()
            self._calibration = None

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
            _LOGGER.debug(
                "_cancel_startup_delay_task :: cancelling active startup delay task"
            )
            self._startup_delay_task.cancel()
            self._startup_delay_task = None

    def _calc_coupled_target(
        self, movement_time, closing, coupled_calc, coupled_time_down, coupled_time_up
    ):
        """Calculate target position for a coupled calculator based on primary movement time.

        When travel moves, tilt moves proportionally (and vice versa when
        travel_moves_with_tilt is enabled). This computes how far the coupled
        calculator should move given the primary movement duration.
        """
        coupled_time = coupled_time_down if closing else coupled_time_up
        coupled_distance = (movement_time / coupled_time) * 100.0
        current = coupled_calc.current_position()
        if closing:
            return min(100, current + coupled_distance)
        return max(0, current - coupled_distance)

    def _begin_movement(
        self, target, coupled_target, primary_calc, coupled_calc, startup_delay
    ):
        """Start position tracking on primary and optionally coupled calculator.

        Begins travel on the primary calculator toward `target`, and if a
        coupled_target is provided, also starts the coupled calculator.
        Then starts the auto updater. Honors motor startup delay if configured.
        """

        def start():
            primary_calc.start_travel(target)
            if coupled_target is not None:
                coupled_calc.start_travel(int(coupled_target))
            self.start_auto_updater()

        self._start_movement(startup_delay, start)

    def _start_movement(self, startup_delay, start_callback):
        """Start position tracking, optionally after a motor startup delay.

        If startup_delay is set, the relay is already ON but the motor hasn't
        started moving yet. We wait for the delay, then begin tracking.
        Otherwise we start tracking immediately.
        """
        if startup_delay and startup_delay > 0:
            self._startup_delay_task = self.hass.async_create_task(
                self._execute_with_startup_delay(startup_delay, start_callback)
            )
        else:
            start_callback()

    async def _execute_with_startup_delay(self, startup_delay, start_callback):
        """Wait for motor startup delay, then start position tracking."""
        _LOGGER.debug(
            "_execute_with_startup_delay :: waiting %fs before starting position tracking",
            startup_delay,
        )
        try:
            await sleep(startup_delay)
            _LOGGER.debug(
                "_execute_with_startup_delay :: startup delay complete, starting position tracking"
            )
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
        if self._travel_motor_overhead is not None:
            attr[CONF_TRAVEL_MOTOR_OVERHEAD] = self._travel_motor_overhead
        if self._tilt_motor_overhead is not None:
            attr[CONF_TILT_MOTOR_OVERHEAD] = self._tilt_motor_overhead
        if self._min_movement_time is not None:
            attr[CONF_MIN_MOVEMENT_TIME] = self._min_movement_time
        if self._calibration is not None:
            attr["calibration_active"] = True
            attr["calibration_attribute"] = self._calibration.attribute
            if self._calibration.step_count > 0:
                attr["calibration_step"] = self._calibration.step_count
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
        """Close the cover fully."""
        _LOGGER.debug("async_close_cover")
        if self.is_opening:
            _LOGGER.debug("async_close_cover :: currently opening, stopping first")
            await self.async_stop_cover()
        await self._async_move_to_endpoint(target=100)

    async def async_open_cover(self, **kwargs):
        """Open the cover fully."""
        _LOGGER.debug("async_open_cover")
        if self.is_closing:
            _LOGGER.debug("async_open_cover :: currently closing, stopping first")
            await self.async_stop_cover()
        await self._async_move_to_endpoint(target=0)

    async def _async_move_to_endpoint(self, target):
        """Move cover to an endpoint (0=fully open, 100=fully closed in travel_calc coords)."""
        closing = target == 100
        command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
        opposite_command = SERVICE_OPEN_COVER if closing else SERVICE_CLOSE_COVER

        # Check startup delay conflicts BEFORE position check, since during
        # startup delay the position hasn't started changing yet.
        if self._startup_delay_task and not self._startup_delay_task.done():
            if self._last_command == opposite_command:
                _LOGGER.debug(
                    "_async_move_to_endpoint :: direction change, cancelling startup delay"
                )
                self._cancel_startup_delay_task()
                await self._async_handle_command(SERVICE_STOP_COVER)
                self._last_command = None
                return
            else:
                _LOGGER.debug(
                    "_async_move_to_endpoint :: startup delay already active, not restarting"
                )
                return

        current = self.travel_calc.current_position()
        if current is not None and current == target:
            return

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)

        # Distance assumes full travel when position is unknown
        default_pos = 0 if closing else 100
        travel_distance = abs(
            target - (current if current is not None else default_pos)
        )
        travel_time = self._travel_time_down if closing else self._travel_time_up
        movement_time = (travel_distance / 100.0) * travel_time

        _LOGGER.debug(
            "_async_move_to_endpoint :: target=%d, travel_distance=%f%%, movement_time=%fs",
            target,
            travel_distance,
            movement_time,
        )

        self._last_command = command

        tilt_target = None
        if self._has_tilt_support():
            tilt_target = self._calc_coupled_target(
                movement_time,
                closing,
                self.tilt_calc,
                self._tilting_time_down,
                self._tilting_time_up,
            )

        await self._async_handle_command(command)
        coupled_calc = self.tilt_calc if tilt_target is not None else None
        self._begin_movement(
            target,
            tilt_target,
            self.travel_calc,
            coupled_calc,
            self._travel_startup_delay,
        )

    async def async_close_cover_tilt(self, **kwargs):
        """Tilt the cover fully closed."""
        _LOGGER.debug("async_close_cover_tilt")
        await self._async_move_tilt_to_endpoint(target=100)

    async def async_open_cover_tilt(self, **kwargs):
        """Tilt the cover fully open."""
        _LOGGER.debug("async_open_cover_tilt")
        await self._async_move_tilt_to_endpoint(target=0)

    async def _async_move_tilt_to_endpoint(self, target):
        """Move tilt to an endpoint (0=fully open, 100=fully closed in tilt_calc coords)."""
        closing = target == 100
        command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
        opposite_command = SERVICE_OPEN_COVER if closing else SERVICE_CLOSE_COVER

        if self._startup_delay_task and not self._startup_delay_task.done():
            if self._last_command == opposite_command:
                _LOGGER.debug(
                    "_async_move_tilt_to_endpoint :: direction change, cancelling startup delay"
                )
                self._cancel_startup_delay_task()
                await self._async_handle_command(SERVICE_STOP_COVER)
            else:
                _LOGGER.debug(
                    "_async_move_tilt_to_endpoint :: startup delay already active, not restarting"
                )
                return

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)

        self._stop_travel_if_traveling()

        current_tilt = self.tilt_calc.current_position()
        if current_tilt is not None and current_tilt == target:
            return

        default_pos = 0 if closing else 100
        tilt_distance = abs(
            target - (current_tilt if current_tilt is not None else default_pos)
        )
        tilt_time = self._tilting_time_down if closing else self._tilting_time_up
        movement_time = (tilt_distance / 100.0) * tilt_time

        travel_target = None
        if self._travel_moves_with_tilt:
            travel_target = self._calc_coupled_target(
                movement_time,
                closing,
                self.travel_calc,
                self._travel_time_down,
                self._travel_time_up,
            )

        _LOGGER.debug(
            "_async_move_tilt_to_endpoint :: target=%d, tilt_distance=%f%%, movement_time=%fs, travel_pos=%s",
            target,
            tilt_distance,
            movement_time,
            travel_target if travel_target is not None else "N/A",
        )

        self._last_command = command
        await self._async_handle_command(command)
        self._begin_movement(
            target,
            travel_target,
            self.tilt_calc,
            self.travel_calc,
            self._tilt_startup_delay,
        )

    async def async_stop_cover(self, **kwargs):
        """Turn the device stop."""
        _LOGGER.debug("async_stop_cover")
        self._cancel_startup_delay_task()
        self._cancel_delay_task()
        self._handle_stop()
        self._enforce_tilt_constraints()
        await self._send_stop()
        self.async_write_ha_state()
        self._last_command = None

    async def _handle_pre_movement_checks(self, command):
        """Handle startup delay conflicts and relay delay before a movement.

        Returns (should_proceed, is_direction_change).
        """
        is_direction_change = (
            self._last_command is not None and self._last_command != command
        )

        # If startup delay active for same direction, don't restart
        if self._startup_delay_task and not self._startup_delay_task.done():
            if not is_direction_change:
                _LOGGER.debug(
                    "_handle_pre_movement_checks :: startup delay active, skipping"
                )
                return False, is_direction_change
            _LOGGER.debug(
                "_handle_pre_movement_checks :: direction change, cancelling startup delay"
            )
            self._cancel_startup_delay_task()
            await self._async_handle_command(SERVICE_STOP_COVER)

        return True, is_direction_change

    def _is_movement_too_short(self, movement_time, target, current, label):
        """Check if movement time is below minimum. Returns True if movement should be skipped."""
        is_to_endpoint = target in (0, 100)
        if (
            self._min_movement_time is not None
            and self._min_movement_time > 0
            and not is_to_endpoint
            and movement_time < self._min_movement_time
        ):
            _LOGGER.info(
                "%s :: movement too short (%fs < %fs), ignoring - from %d%% to %d%%",
                label,
                movement_time,
                self._min_movement_time,
                100 - current,
                100 - target,
            )
            self.async_write_ha_state()
            return True
        return False

    async def set_position(self, position):
        """Move cover to a designated position."""
        current = self.travel_calc.current_position()
        target = 100 - position
        _LOGGER.debug("set_position :: current: %d, target: %d", current, position)

        if current is None or target > current:
            command = SERVICE_CLOSE_COVER
        elif target < current:
            command = SERVICE_OPEN_COVER
        else:
            return

        closing = command == SERVICE_CLOSE_COVER

        should_proceed, is_direction_change = await self._handle_pre_movement_checks(
            command
        )
        if not should_proceed:
            return

        if is_direction_change and self.travel_calc.is_traveling():
            _LOGGER.debug("set_position :: stopping active travel movement")
            self.travel_calc.stop()
            self.stop_auto_updater()
            if self._has_tilt_support() and self.tilt_calc.is_traveling():
                self.tilt_calc.stop()
            await self._async_handle_command(SERVICE_STOP_COVER)
            current = self.travel_calc.current_position()
            if target == current:
                return

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)

        travel_time = self._travel_time_down if closing else self._travel_time_up
        movement_time = (abs(target - current) / 100.0) * travel_time

        if self._is_movement_too_short(movement_time, target, current, "set_position"):
            return

        self._last_command = command

        tilt_target = None
        if self._has_tilt_support():
            tilt_target = self._calc_coupled_target(
                movement_time,
                closing,
                self.tilt_calc,
                self._tilting_time_down,
                self._tilting_time_up,
            )

        await self._async_handle_command(command)
        coupled_calc = self.tilt_calc if tilt_target is not None else None
        self._begin_movement(
            target,
            tilt_target,
            self.travel_calc,
            coupled_calc,
            self._travel_startup_delay,
        )

    async def set_tilt_position(self, position):
        """Move cover tilt to a designated position."""
        current = self.tilt_calc.current_position()
        target = 100 - position
        _LOGGER.debug("set_tilt_position :: current: %d, target: %d", current, target)

        if current is None or target > current:
            command = SERVICE_CLOSE_COVER
        elif target < current:
            command = SERVICE_OPEN_COVER
        else:
            return

        closing = command == SERVICE_CLOSE_COVER

        should_proceed, is_direction_change = await self._handle_pre_movement_checks(
            command
        )
        if not should_proceed:
            return

        if is_direction_change:
            if self.tilt_calc.is_traveling():
                self.tilt_calc.stop()
            if self.travel_calc.is_traveling():
                self.travel_calc.stop()
            self.stop_auto_updater()
            await self._async_handle_command(SERVICE_STOP_COVER)
            current = self.tilt_calc.current_position()
            if target == current:
                return

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)

        if not is_direction_change:
            self._stop_travel_if_traveling()

        tilt_time = self._tilting_time_down if closing else self._tilting_time_up
        movement_time = (abs(target - current) / 100.0) * tilt_time

        travel_target = None
        if self._travel_moves_with_tilt:
            travel_target = self._calc_coupled_target(
                movement_time,
                closing,
                self.travel_calc,
                self._travel_time_down,
                self._travel_time_up,
            )

        if self._is_movement_too_short(
            movement_time, target, current, "set_tilt_position"
        ):
            return

        self._last_command = command

        await self._async_handle_command(command)
        self._begin_movement(
            target,
            travel_target,
            self.tilt_calc,
            self.travel_calc,
            self._tilt_startup_delay,
        )

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
                current_tilt,
            )
            self.tilt_calc.set_position(0)

        elif current_travel == 100 and current_tilt != 100:
            _LOGGER.debug(
                "_enforce_tilt_constraints :: Travel at 100%%, forcing tilt to 100%% (was %d%%)",
                current_tilt,
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
            if (
                self._travel_delay_at_end is not None
                and self._travel_delay_at_end > 0
                and (current_travel == 0 or current_travel == 100)
            ):
                _LOGGER.debug(
                    "auto_stop_if_necessary :: at endpoint (position=%d), delaying relay stop by %fs",
                    current_travel,
                    self._travel_delay_at_end,
                )
                self._delay_task = self.hass.async_create_task(
                    self._delayed_stop(self._travel_delay_at_end)
                )
            else:
                await self._async_handle_command(SERVICE_STOP_COVER)
            self._last_command = None

    async def _delayed_stop(self, delay):
        """Stop the relay after a delay."""
        _LOGGER.debug("_delayed_stop :: waiting %fs before stopping relay", delay)
        try:
            await sleep(delay)
            _LOGGER.debug("_delayed_stop :: delay complete, stopping relay")
            await self._async_handle_command(SERVICE_STOP_COVER)
            self._last_command = None
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
        self._last_command = None

    async def set_known_tilt_position(self, **kwargs):
        """We want to do a few things when we get a position"""
        position = kwargs[ATTR_TILT_POSITION]
        await self._async_handle_command(SERVICE_STOP_COVER)
        self.tilt_calc.set_position(position)
        self._last_command = None

    async def start_calibration(self, **kwargs):
        """Start a calibration test for the given attribute."""
        attribute = kwargs["attribute"]
        timeout = kwargs["timeout"]
        direction = kwargs.get("direction")  # "open", "close", or None (auto)

        if self._calibration is not None:
            raise HomeAssistantError("Calibration already in progress")

        # Validate BEFORE creating state
        if attribute in ("tilt_time_close", "tilt_time_open"):
            if self._travel_moves_with_tilt:
                raise HomeAssistantError(
                    "Tilt time calibration not available when travel_moves_with_tilt is enabled"
                )

        if attribute == "travel_motor_overhead":
            if not (self._travel_time_down or self._travel_time_up):
                raise HomeAssistantError(
                    "Travel time must be configured before calibrating motor overhead"
                )

        if attribute == "tilt_motor_overhead":
            if not (self._tilting_time_down or self._tilting_time_up):
                raise HomeAssistantError(
                    "Tilt time must be configured before calibrating motor overhead"
                )

        # Create state only after validation passes
        self._calibration = CalibrationState(attribute=attribute, timeout=timeout)
        self._calibration.timeout_task = self.hass.async_create_task(
            self._calibration_timeout()
        )

        # Dispatch to appropriate test type
        if attribute in (
            "travel_time_close",
            "travel_time_open",
            "tilt_time_close",
            "tilt_time_open",
        ):
            await self._start_simple_time_test(attribute, direction)
        elif attribute in ("travel_motor_overhead", "tilt_motor_overhead"):
            await self._start_overhead_test(attribute, direction)
        elif attribute == "min_movement_time":
            self._calibration.move_command = self._resolve_direction(
                direction, self.current_cover_position
            )
            self._calibration.automation_task = self.hass.async_create_task(
                self._run_min_movement_pulses()
            )

        self.async_write_ha_state()

    @staticmethod
    def _resolve_direction(direction, position):
        """Resolve move command from explicit direction or current position."""
        if direction == "close":
            return SERVICE_CLOSE_COVER
        if direction == "open":
            return SERVICE_OPEN_COVER
        # Auto-detect from position
        if position is not None and position < 50:
            return SERVICE_OPEN_COVER
        return SERVICE_CLOSE_COVER

    async def _start_simple_time_test(self, attribute, direction):
        """Start a simple travel/tilt time test by moving the cover."""
        if direction:
            self._calibration.move_command = self._resolve_direction(
                direction, None
            )
        elif "close" in attribute:
            self._calibration.move_command = SERVICE_CLOSE_COVER
        else:
            self._calibration.move_command = SERVICE_OPEN_COVER
        await self._async_handle_command(self._calibration.move_command)

    async def _start_overhead_test(self, attribute, direction):
        """Start automated step test for motor overhead."""
        from .calibration import CALIBRATION_OVERHEAD_STEPS

        if attribute == "travel_motor_overhead":
            position = self.current_cover_position
            move_command = self._resolve_direction(direction, position)
            if move_command == SERVICE_OPEN_COVER:
                travel_time = self._travel_time_up or self._travel_time_down
            else:
                travel_time = self._travel_time_down or self._travel_time_up
        else:
            position = self.current_cover_tilt_position
            move_command = self._resolve_direction(direction, position)
            if move_command == SERVICE_OPEN_COVER:
                travel_time = self._tilting_time_up or self._tilting_time_down
            else:
                travel_time = self._tilting_time_down or self._tilting_time_up

        _LOGGER.debug(
            "overhead test: position=%s, direction=%s, travel_time=%.2f",
            position,
            move_command,
            travel_time,
        )

        # Each step is 1/10th of total travel time, but we only do 8 steps
        step_duration = travel_time / 10
        self._calibration.step_duration = step_duration
        self._calibration.move_command = move_command

        self._calibration.automation_task = self.hass.async_create_task(
            self._run_overhead_steps(step_duration, CALIBRATION_OVERHEAD_STEPS)
        )

    async def _run_overhead_steps(self, step_duration, num_steps):
        """Execute stepped moves then one continuous move for overhead test.

        Phase 1: num_steps stepped moves of step_duration each (with pauses).
        Phase 2: Continuous move for the remaining distance.
        The user calls stop_calibration when the cover reaches the endpoint.
        """
        from .calibration import CALIBRATION_STEP_PAUSE

        move_command = self._calibration.move_command

        try:
            # Phase 1: Stepped moves
            for i in range(num_steps):
                _LOGGER.debug(
                    "overhead step %d/%d: moving for %.2fs",
                    i + 1,
                    num_steps,
                    step_duration,
                )
                await self._async_handle_command(move_command)
                await sleep(step_duration)
                await self._send_stop()
                self._calibration.step_count += 1
                self.async_write_ha_state()
                if i < num_steps - 1:
                    await sleep(CALIBRATION_STEP_PAUSE)

            # Pause before continuous phase
            await sleep(CALIBRATION_STEP_PAUSE)

            # Phase 2: Continuous move for remaining distance
            _LOGGER.debug(
                "overhead test: starting continuous phase for remaining distance"
            )
            self._calibration.continuous_start = time.monotonic()
            await self._async_handle_command(move_command)

            # Wait indefinitely until user calls stop_calibration
            while True:
                await sleep(1.0)
        except asyncio.CancelledError:
            pass

    async def _run_min_movement_pulses(self):
        """Send increasingly longer pulses until user sees movement."""
        from .calibration import (
            CALIBRATION_MIN_MOVEMENT_START,
            CALIBRATION_MIN_MOVEMENT_INCREMENT,
            CALIBRATION_STEP_PAUSE,
        )

        pulse_duration = CALIBRATION_MIN_MOVEMENT_START

        try:
            while True:
                self._calibration.last_pulse_duration = pulse_duration
                self._calibration.step_count += 1

                await self._async_handle_command(self._calibration.move_command)
                await sleep(pulse_duration)
                await self._send_stop()
                self.async_write_ha_state()

                await sleep(CALIBRATION_STEP_PAUSE)
                pulse_duration += CALIBRATION_MIN_MOVEMENT_INCREMENT
        except asyncio.CancelledError:
            pass

    async def _calibration_timeout(self):
        """Handle calibration timeout."""
        try:
            await sleep(self._calibration.timeout)
            _LOGGER.warning(
                "Calibration timed out after %fs for attribute '%s'",
                self._calibration.timeout,
                self._calibration.attribute,
            )
            # Cancel automation task if running
            if (
                self._calibration.automation_task is not None
                and not self._calibration.automation_task.done()
            ):
                self._calibration.automation_task.cancel()
            await self._send_stop()
            self._calibration = None
            self.async_write_ha_state()
        except asyncio.CancelledError:
            _LOGGER.debug("_calibration_timeout :: cancelled")

    async def stop_calibration(self, **kwargs):
        """Stop an in-progress calibration test."""
        if self._calibration is None:
            raise HomeAssistantError("No calibration in progress")

        cancel = kwargs.get("cancel", False)

        # Cancel timeout task
        if (
            self._calibration.timeout_task is not None
            and not self._calibration.timeout_task.done()
        ):
            self._calibration.timeout_task.cancel()

        # Cancel automation task
        if (
            self._calibration.automation_task is not None
            and not self._calibration.automation_task.done()
        ):
            self._calibration.automation_task.cancel()

        # Stop the motor
        await self._send_stop()

        result = {}
        if not cancel:
            value = self._calculate_calibration_result()
            result["attribute"] = self._calibration.attribute
            result["value"] = value
            self._save_calibration_result(self._calibration.attribute, value)

        self._calibration = None
        self.async_write_ha_state()
        return result

    def _calculate_calibration_result(self):
        """Calculate the calibration result based on attribute type."""
        attribute = self._calibration.attribute

        if "travel_time" in attribute or "tilt_time" in attribute:
            elapsed = time.monotonic() - self._calibration.started_at
            return round(elapsed, 1)

        if attribute in ("travel_motor_overhead", "tilt_motor_overhead"):
            if attribute == "travel_motor_overhead":
                total_time = self._travel_time_down or self._travel_time_up
            else:
                total_time = self._tilting_time_down or self._tilting_time_up

            step_count = self._calibration.step_count
            continuous_start = self._calibration.continuous_start
            if continuous_start is None:
                _LOGGER.warning(
                    "Overhead calibration stopped before continuous phase started"
                )
                return 0.0
            continuous_time = time.monotonic() - continuous_start
            # 8 steps cover 8/10 of travel; remaining is 2/10 = 0.2 * total_time
            expected_remaining = 0.2 * total_time
            overhead = (continuous_time - expected_remaining) / step_count
            _LOGGER.debug(
                "overhead calculation: total_time=%.2f, step_count=%d, "
                "continuous_time=%.2f, expected_remaining=%.2f, overhead=%.4f",
                total_time,
                step_count,
                continuous_time,
                expected_remaining,
                overhead,
            )
            return round(max(0, overhead), 2)

        if attribute == "min_movement_time":
            return round(self._calibration.last_pulse_duration, 2)

        raise ValueError(f"Unexpected calibration attribute: {attribute}")

    def _save_calibration_result(self, attribute, value):
        """Save the calibration result to the config entry options."""
        attribute_to_conf = {
            "travel_time_close": CONF_TRAVELLING_TIME_DOWN,
            "travel_time_open": CONF_TRAVELLING_TIME_UP,
            "tilt_time_close": CONF_TILTING_TIME_DOWN,
            "tilt_time_open": CONF_TILTING_TIME_UP,
            "travel_motor_overhead": CONF_TRAVEL_MOTOR_OVERHEAD,
            "tilt_motor_overhead": CONF_TILT_MOTOR_OVERHEAD,
            "min_movement_time": CONF_MIN_MOVEMENT_TIME,
        }
        conf_key = attribute_to_conf.get(attribute)
        if conf_key is None:
            _LOGGER.error("Unknown calibration attribute: %s", attribute)
            return

        entry = self.hass.config_entries.async_get_entry(self._config_entry_id)
        if entry is None:
            _LOGGER.error(
                "Config entry %s not found, cannot save calibration result",
                self._config_entry_id,
            )
            return

        new_options = {**entry.options, conf_key: value}
        self.hass.config_entries.async_update_entry(entry, options=new_options)

    async def _async_handle_command(self, command, *args):
        if command == SERVICE_CLOSE_COVER:
            cmd = "DOWN"
            self._state = False
            await self._send_close()
        elif command == SERVICE_OPEN_COVER:
            cmd = "UP"
            self._state = True
            await self._send_open()
        elif command == SERVICE_STOP_COVER:
            cmd = "STOP"
            self._state = True
            await self._send_stop()

        _LOGGER.debug("_async_handle_command :: %s", cmd)
        self.async_write_ha_state()

    @abstractmethod
    async def _send_open(self) -> None:
        """Send the open command to the underlying device."""

    @abstractmethod
    async def _send_close(self) -> None:
        """Send the close command to the underlying device."""

    @abstractmethod
    async def _send_stop(self) -> None:
        """Send the stop command to the underlying device."""
