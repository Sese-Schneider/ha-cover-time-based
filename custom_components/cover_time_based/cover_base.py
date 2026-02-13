"""Base class for time-based cover entities."""

import asyncio
import logging
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
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
from xknx.devices import TravelCalculator, TravelStatus

_LOGGER = logging.getLogger(__name__)

# Configuration constants used by extra_state_attributes.
# These are also defined in cover.py for YAML/UI config schemas,
# but we define them here to avoid circular imports.
CONF_TRAVEL_MOVES_WITH_TILT = "travel_moves_with_tilt"
CONF_TRAVELLING_TIME_DOWN = "travelling_time_down"
CONF_TRAVELLING_TIME_UP = "travelling_time_up"
CONF_TILTING_TIME_DOWN = "tilting_time_down"
CONF_TILTING_TIME_UP = "tilting_time_up"
CONF_TRAVEL_DELAY_AT_END = "travel_delay_at_end"
CONF_MIN_MOVEMENT_TIME = "min_movement_time"
CONF_TRAVEL_STARTUP_DELAY = "travel_startup_delay"
CONF_TILT_STARTUP_DELAY = "tilt_startup_delay"


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

        if name:
            self._name = name
        else:
            self._name = device_id

        self._unsubscribe_auto_updater = None
        self._delay_task = None
        self._startup_delay_task = None
        self._last_command = None
        self._triggered_externally = False
        self._pending_switch = {}
        self._pending_switch_timers = {}
        self._state_listener_unsubs = []

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

        # Register state change listeners for switch entities
        for attr in ('_open_switch_entity_id', '_close_switch_entity_id', '_stop_switch_entity_id'):
            entity_id = getattr(self, attr, None)
            if entity_id:
                self._state_listener_unsubs.append(
                    async_track_state_change_event(
                        self.hass,
                        [entity_id],
                        self._async_switch_state_changed,
                    )
                )

    async def async_will_remove_from_hass(self):
        """Clean up state listeners."""
        for unsub in self._state_listener_unsubs:
            unsub()
        self._state_listener_unsubs.clear()
        for timer in self._pending_switch_timers.values():
            timer()
        self._pending_switch_timers.clear()

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
        if not self._triggered_externally:
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

    def _mark_switch_pending(self, entity_id, expected_transitions):
        """Mark a switch as having pending echo transitions to ignore."""
        self._pending_switch[entity_id] = self._pending_switch.get(entity_id, 0) + expected_transitions
        _LOGGER.debug("_mark_switch_pending :: %s pending=%d", entity_id, self._pending_switch[entity_id])

        # Cancel any existing timeout for this switch
        if entity_id in self._pending_switch_timers:
            self._pending_switch_timers[entity_id]()

        # Safety timeout: clear pending after 5 seconds
        @callback
        def _clear_pending(_now):
            if entity_id in self._pending_switch:
                _LOGGER.debug("_mark_switch_pending :: timeout clearing %s", entity_id)
                del self._pending_switch[entity_id]
            self._pending_switch_timers.pop(entity_id, None)

        self._pending_switch_timers[entity_id] = async_call_later(
            self.hass, 5, _clear_pending
        )

    async def _async_switch_state_changed(self, event):
        """Handle state changes on monitored switch entities."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if new_state is None or old_state is None:
            return

        new_val = new_state.state
        old_val = old_state.state

        _LOGGER.debug(
            "_async_switch_state_changed :: %s: %s -> %s (pending=%s)",
            entity_id, old_val, new_val,
            self._pending_switch.get(entity_id, 0),
        )

        # Echo filtering: if this switch has pending echoes, decrement and skip
        if self._pending_switch.get(entity_id, 0) > 0:
            self._pending_switch[entity_id] -= 1
            if self._pending_switch[entity_id] <= 0:
                del self._pending_switch[entity_id]
                # Cancel the safety timeout
                timer = self._pending_switch_timers.pop(entity_id, None)
                if timer:
                    timer()
            _LOGGER.debug(
                "_async_switch_state_changed :: echo filtered, remaining=%s",
                self._pending_switch.get(entity_id, 0),
            )
            return

        # External state change detected — handle per mode
        self._triggered_externally = True
        try:
            await self._handle_external_state_change(entity_id, old_val, new_val)
        finally:
            self._triggered_externally = False

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle external state change. Override in subclasses for mode-specific behavior."""

    async def _async_handle_command(self, command, *args):
        if command == SERVICE_CLOSE_COVER:
            cmd = "DOWN"
            self._state = False
            if not self._triggered_externally:
                await self._send_close()
        elif command == SERVICE_OPEN_COVER:
            cmd = "UP"
            self._state = True
            if not self._triggered_externally:
                await self._send_open()
        elif command == SERVICE_STOP_COVER:
            cmd = "STOP"
            self._state = True
            if not self._triggered_externally:
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
