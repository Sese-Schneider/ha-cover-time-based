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
from .travel_calculator import TravelCalculator, TravelStatus

from .calibration import CalibrationState

_LOGGER = logging.getLogger(__name__)

# Configuration constants used by extra_state_attributes.
# These are also defined in cover.py for YAML/UI config schemas,
# but we define them here to avoid circular imports.
CONF_TILT_MODE = "tilt_mode"
CONF_TRAVEL_TIME_CLOSE = "travel_time_close"
CONF_TRAVEL_TIME_OPEN = "travel_time_open"
CONF_TILT_TIME_CLOSE = "tilt_time_close"
CONF_TILT_TIME_OPEN = "tilt_time_open"
CONF_TRAVEL_STARTUP_DELAY = "travel_startup_delay"
CONF_TILT_STARTUP_DELAY = "tilt_startup_delay"
CONF_ENDPOINT_RUNON_TIME = "endpoint_runon_time"
CONF_MIN_MOVEMENT_TIME = "min_movement_time"


class CoverTimeBased(CoverEntity, RestoreEntity):
    def __init__(
        self,
        device_id,
        name,
        tilt_strategy,
        travel_time_close,
        travel_time_open,
        tilt_time_close,
        tilt_time_open,
        travel_startup_delay,
        tilt_startup_delay,
        endpoint_runon_time,
        min_movement_time,
        tilt_open_switch=None,
        tilt_close_switch=None,
        tilt_stop_switch=None,
    ):
        """Initialize the cover."""
        self._unique_id = device_id

        self._tilt_strategy = tilt_strategy
        self._travel_time_close = travel_time_close
        self._travel_time_open = travel_time_open
        self._tilting_time_close = tilt_time_close
        self._tilting_time_open = tilt_time_open
        self._travel_startup_delay = travel_startup_delay
        self._tilt_startup_delay = tilt_startup_delay
        self._endpoint_runon_time = endpoint_runon_time
        self._min_movement_time = min_movement_time
        self._tilt_open_switch_id = tilt_open_switch
        self._tilt_close_switch_id = tilt_close_switch
        self._tilt_stop_switch_id = tilt_stop_switch

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
        self._tilt_restore_target: int | None = None
        self._tilt_restore_active: bool = False
        self._pending_travel_target: int | None = None
        self._pending_travel_command: str | None = None

        self.travel_calc = TravelCalculator(
            self._travel_time_close,
            self._travel_time_open,
        )
        if self._tilting_time_close is not None and self._tilting_time_open is not None:
            self.tilt_calc = TravelCalculator(
                self._tilting_time_close,
                self._tilting_time_open,
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
                int(old_state.attributes.get(ATTR_CURRENT_POSITION))
            )

            if (
                self._has_tilt_support()
                and old_state.attributes.get(ATTR_CURRENT_TILT_POSITION) is not None
            ):
                self.tilt_calc.set_position(
                    int(old_state.attributes.get(ATTR_CURRENT_TILT_POSITION))
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
        self._tilt_restore_target = None
        self._tilt_restore_active = False
        self._pending_travel_target = None
        self._pending_travel_command = None

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

    def _begin_movement(
        self,
        target,
        coupled_target,
        primary_calc,
        coupled_calc,
        startup_delay,
        pre_step_delay: float = 0.0,
    ):
        """Start position tracking on primary and optionally coupled calculator.

        Begins travel on the primary calculator toward `target`, and if a
        coupled_target is provided, also starts the coupled calculator.
        Then starts the auto updater. Honors motor startup delay if configured.

        If pre_step_delay > 0, the coupled calculator is a pre-step that must
        complete before the primary starts (e.g. tilt-before-travel in
        sequential mode). The primary calculator's start is offset by this
        delay so its position stays put until the pre-step finishes.
        """

        def start():
            primary_calc.start_travel(target, delay=pre_step_delay)
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

    def _are_entities_configured(self) -> bool:
        """Return True if the required input entities are configured.

        Subclasses override this to check their specific entity IDs.
        """
        return True

    def _get_missing_configuration(self) -> list[str]:
        """Return list of missing configuration items."""
        missing = []
        if not self._are_entities_configured():
            missing.append("input entities")
        if self._travel_time_close is None and self._travel_time_open is None:
            missing.append("travel times")
        return missing

    @property
    def available(self) -> bool:
        """Return True if the cover is properly configured and available."""
        return len(self._get_missing_configuration()) == 0

    def _require_configured(self) -> None:
        """Raise if the cover is not properly configured."""
        missing = self._get_missing_configuration()
        if missing:
            raise HomeAssistantError(
                f"Cover not configured: missing {', '.join(missing)}. "
                "Please configure using the Cover Time Based card."
            )

    def _require_travel_time(self, closing: bool) -> float:
        """Return travel time for the given direction, or raise if not configured."""
        travel_time = self._travel_time_close if closing else self._travel_time_open
        if travel_time is None:
            raise HomeAssistantError(
                "Travel time not configured. Please configure travel times "
                "using the Cover Time Based card."
            )
        return travel_time

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
        if self._tilt_strategy is not None:
            attr[CONF_TILT_MODE] = self._tilt_strategy.name
        if self._travel_time_close is not None:
            attr[CONF_TRAVEL_TIME_CLOSE] = self._travel_time_close
        if self._travel_time_open is not None:
            attr[CONF_TRAVEL_TIME_OPEN] = self._travel_time_open
        if self._tilting_time_close is not None:
            attr[CONF_TILT_TIME_CLOSE] = self._tilting_time_close
        if self._tilting_time_open is not None:
            attr[CONF_TILT_TIME_OPEN] = self._tilting_time_open
        if self._travel_startup_delay is not None:
            attr[CONF_TRAVEL_STARTUP_DELAY] = self._travel_startup_delay
        if self._tilt_startup_delay is not None:
            attr[CONF_TILT_STARTUP_DELAY] = self._tilt_startup_delay
        if self._endpoint_runon_time is not None:
            attr[CONF_ENDPOINT_RUNON_TIME] = self._endpoint_runon_time
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
        return self.travel_calc.current_position()

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return the current tilt of the cover."""
        if self._has_tilt_support():
            return self.tilt_calc.current_position()
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
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )

        if self._has_tilt_support():
            supported_features |= (
                CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.STOP_TILT
                | CoverEntityFeature.SET_TILT_POSITION
            )

        return supported_features

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        self._require_configured()
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
        self._require_configured()
        _LOGGER.debug("async_close_cover")
        if self.is_opening:
            _LOGGER.debug("async_close_cover :: currently opening, stopping first")
            await self.async_stop_cover()
        await self._async_move_to_endpoint(target=0)

    async def async_open_cover(self, **kwargs):
        """Open the cover fully."""
        self._require_configured()
        _LOGGER.debug("async_open_cover")
        if self.is_closing:
            _LOGGER.debug("async_open_cover :: currently closing, stopping first")
            await self.async_stop_cover()
        await self._async_move_to_endpoint(target=100)

    async def _async_move_to_endpoint(self, target):
        """Move cover to an endpoint (0=fully closed, 100=fully open)."""
        closing = target == 0
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
        default_pos = 100 if closing else 0
        travel_distance = abs(
            target - (current if current is not None else default_pos)
        )
        travel_time = self._require_travel_time(closing)
        movement_time = (travel_distance / 100.0) * travel_time

        _LOGGER.debug(
            "_async_move_to_endpoint :: target=%d, travel_distance=%f%%, movement_time=%fs",
            target,
            travel_distance,
            movement_time,
        )

        self._last_command = command

        tilt_target = None
        pre_step_delay = 0.0
        self._tilt_restore_target = None
        if self._tilt_strategy is not None:
            current_pos = self.travel_calc.current_position()
            current_tilt = self.tilt_calc.current_position()
            if current_pos is not None and current_tilt is not None:
                steps = self._tilt_strategy.plan_move_position(
                    target, current_pos, current_tilt
                )
                tilt_target = self._extract_coupled_tilt(steps)
                pre_step_delay = self._calculate_pre_step_delay(steps)

                # Dual motor: tilt to safe position first, then travel
                if (
                    tilt_target is not None
                    and self._tilt_strategy.uses_tilt_motor
                    and current_tilt != tilt_target
                ):
                    await self._start_tilt_pre_step(
                        tilt_target, target, command, current_tilt
                    )
                    return

                # Shared motor with restore: save tilt for post-travel restore
                if (
                    tilt_target is not None
                    and self._tilt_strategy.restores_tilt
                    and not self._tilt_strategy.uses_tilt_motor
                    and target not in (0, 100)
                ):
                    self._tilt_restore_target = current_tilt

        await self._async_handle_command(command)
        coupled_calc = self.tilt_calc if tilt_target is not None else None
        self._begin_movement(
            target,
            tilt_target,
            self.travel_calc,
            coupled_calc,
            self._travel_startup_delay,
            pre_step_delay,
        )

    async def async_close_cover_tilt(self, **kwargs):
        """Tilt the cover fully closed."""
        _LOGGER.debug("async_close_cover_tilt")
        await self._async_move_tilt_to_endpoint(target=0)

    async def async_open_cover_tilt(self, **kwargs):
        """Tilt the cover fully open."""
        _LOGGER.debug("async_open_cover_tilt")
        await self._async_move_tilt_to_endpoint(target=100)

    async def _async_move_tilt_to_endpoint(self, target):
        """Move tilt to an endpoint (0=fully closed, 100=fully open)."""
        closing = target == 0
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

        default_pos = 100 if closing else 0
        tilt_distance = abs(
            target - (current_tilt if current_tilt is not None else default_pos)
        )
        tilt_time = self._tilting_time_close if closing else self._tilting_time_open
        movement_time = (tilt_distance / 100.0) * tilt_time

        travel_target = None
        pre_step_delay = 0.0
        if self._tilt_strategy is not None:
            current_pos = self.travel_calc.current_position()
            current_tilt = self.tilt_calc.current_position()
            if current_pos is not None and current_tilt is not None:
                steps = self._tilt_strategy.plan_move_tilt(
                    target, current_pos, current_tilt
                )
                travel_target = self._extract_coupled_travel(steps)
                pre_step_delay = self._calculate_pre_step_delay(steps)

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
            pre_step_delay,
        )

    async def async_stop_cover(self, **kwargs):
        """Turn the device stop."""
        self._require_configured()
        _LOGGER.debug("async_stop_cover")
        tilt_restore_was_active = self._tilt_restore_active
        tilt_pre_step_was_active = self._pending_travel_target is not None
        self._cancel_startup_delay_task()
        self._cancel_delay_task()
        self._handle_stop()
        if self._has_tilt_support():
            self._tilt_strategy.snap_trackers_to_physical(
                self.travel_calc, self.tilt_calc
            )
        await self._send_stop()
        if (
            tilt_restore_was_active or tilt_pre_step_was_active
        ) and self._has_tilt_motor():
            await self._send_tilt_stop()
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
                current,
                target,
            )
            self.async_write_ha_state()
            return True
        return False

    async def set_position(self, position):
        """Move cover to a designated position."""
        current = self.travel_calc.current_position()
        target = position
        _LOGGER.debug(
            "set_position :: current: %s, target: %d",
            current if current is not None else "None",
            target,
        )

        if current is None:
            # Position unknown — assume opposite endpoint so full travel occurs
            closing = target <= 50
            command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
            current = 100 if closing else 0
        elif target < current:
            command = SERVICE_CLOSE_COVER
        elif target > current:
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

        travel_time = self._require_travel_time(closing)
        movement_time = (abs(target - current) / 100.0) * travel_time

        if self._is_movement_too_short(movement_time, target, current, "set_position"):
            return

        self._last_command = command

        tilt_target = None
        pre_step_delay = 0.0
        self._tilt_restore_target = None
        if self._tilt_strategy is not None:
            current_tilt = self.tilt_calc.current_position()
            if current is not None and current_tilt is not None:
                steps = self._tilt_strategy.plan_move_position(
                    target, current, current_tilt
                )
                tilt_target = self._extract_coupled_tilt(steps)
                pre_step_delay = self._calculate_pre_step_delay(steps)

                # Dual motor: tilt to safe position first, then travel
                if (
                    tilt_target is not None
                    and self._tilt_strategy.uses_tilt_motor
                    and current_tilt != tilt_target
                ):
                    await self._start_tilt_pre_step(
                        tilt_target, target, command, current_tilt
                    )
                    return

                # Shared motor with restore: save tilt for post-travel restore
                if (
                    tilt_target is not None
                    and self._tilt_strategy.restores_tilt
                    and not self._tilt_strategy.uses_tilt_motor
                    and target not in (0, 100)
                ):
                    self._tilt_restore_target = current_tilt

        await self._async_handle_command(command)
        coupled_calc = self.tilt_calc if tilt_target is not None else None
        self._begin_movement(
            target,
            tilt_target,
            self.travel_calc,
            coupled_calc,
            self._travel_startup_delay,
            pre_step_delay,
        )

    async def set_tilt_position(self, position):
        """Move cover tilt to a designated position."""
        current = self.tilt_calc.current_position()
        target = position
        _LOGGER.debug(
            "set_tilt_position :: current: %s, target: %d",
            current if current is not None else "None",
            target,
        )

        if current is None:
            closing = target <= 50
            command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
            current = 100 if closing else 0
        elif target < current:
            command = SERVICE_CLOSE_COVER
        elif target > current:
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

        tilt_time = self._tilting_time_close if closing else self._tilting_time_open
        movement_time = (abs(target - current) / 100.0) * tilt_time

        travel_target = None
        pre_step_delay = 0.0
        if self._tilt_strategy is not None:
            current_pos = self.travel_calc.current_position()
            if current is not None and current_pos is not None:
                steps = self._tilt_strategy.plan_move_tilt(target, current_pos, current)
                travel_target = self._extract_coupled_travel(steps)
                pre_step_delay = self._calculate_pre_step_delay(steps)

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
            pre_step_delay,
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
        return self._tilt_strategy is not None and hasattr(self, "tilt_calc")

    async def auto_stop_if_necessary(self):
        """Do auto stop if necessary."""
        if self.position_reached():
            _LOGGER.debug("auto_stop_if_necessary :: calling stop command")
            self.travel_calc.stop()
            if self._has_tilt_support():
                self.tilt_calc.stop()

            if self._tilt_restore_active:
                _LOGGER.debug("auto_stop_if_necessary :: tilt restore complete")
                self._tilt_restore_active = False
                if self._has_tilt_motor():
                    await self._send_tilt_stop()
                else:
                    await self._async_handle_command(SERVICE_STOP_COVER)
                if self._tilt_strategy is not None:
                    self._tilt_strategy.snap_trackers_to_physical(
                        self.travel_calc, self.tilt_calc
                    )
                self._last_command = None
                return

            if self._pending_travel_target is not None:
                # Tilt pre-step complete — start travel phase
                _LOGGER.debug("auto_stop_if_necessary :: tilt pre-step complete")
                await self._start_pending_travel()
                return

            if self._tilt_strategy is not None:
                self._tilt_strategy.snap_trackers_to_physical(
                    self.travel_calc, self.tilt_calc
                )

            if self._tilt_restore_target is not None:
                # Travel just completed — start tilt restore phase
                await self._start_tilt_restore()
                return

            current_travel = self.travel_calc.current_position()
            if (
                self._endpoint_runon_time is not None
                and self._endpoint_runon_time > 0
                and (current_travel == 0 or current_travel == 100)
            ):
                _LOGGER.debug(
                    "auto_stop_if_necessary :: at endpoint (position=%d), delaying relay stop by %fs",
                    current_travel,
                    self._endpoint_runon_time,
                )
                self._delay_task = self.hass.async_create_task(
                    self._delayed_stop(self._endpoint_runon_time)
                )
            else:
                await self._async_handle_command(SERVICE_STOP_COVER)
            self._last_command = None

    async def _start_tilt_pre_step(
        self, tilt_target, travel_target, travel_command, restore_target
    ):
        """Move tilt to safe position before travel (dual_motor).

        Sends the tilt motor command and starts tilt_calc. When tilt reaches
        target, auto_stop_if_necessary will call _start_pending_travel to
        begin the actual cover travel.
        """
        current_tilt = self.tilt_calc.current_position()
        _LOGGER.debug(
            "_start_tilt_pre_step :: tilt %s→%d, pending travel→%d (%s)",
            current_tilt,
            tilt_target,
            travel_target,
            travel_command,
        )
        self._pending_travel_target = travel_target
        self._pending_travel_command = travel_command
        self._tilt_restore_target = restore_target

        closing_tilt = tilt_target < current_tilt
        if closing_tilt:
            await self._send_tilt_close()
        else:
            await self._send_tilt_open()

        self.tilt_calc.start_travel(tilt_target)
        self.start_auto_updater()

    async def _start_pending_travel(self):
        """Start travel after tilt pre-step completes (dual_motor).

        Called by auto_stop_if_necessary when tilt_calc reaches the safe
        position. Stops the tilt motor, sends the travel command, and starts
        tracking with travel_calc.
        """
        target = self._pending_travel_target
        command = self._pending_travel_command
        self._pending_travel_target = None
        self._pending_travel_command = None

        _LOGGER.debug(
            "_start_pending_travel :: starting travel to %d (%s)",
            target,
            command,
        )

        # Stop tilt motor
        await self._send_tilt_stop()

        # Send travel command and start tracking
        await self._async_handle_command(command)
        self._last_command = command
        self._begin_movement(
            target,
            None,
            self.travel_calc,
            None,
            self._travel_startup_delay,
        )

    async def _start_tilt_restore(self):
        """Restore tilt to its pre-movement position.

        For dual_motor: stops travel motor, starts tilt motor.
        For shared motor (inline): reverses main motor direction.
        """
        restore_target = self._tilt_restore_target
        self._tilt_restore_target = None

        current_tilt = self.tilt_calc.current_position()
        if current_tilt is None or current_tilt == restore_target:
            _LOGGER.debug(
                "_start_tilt_restore :: no restore needed (current=%s, target=%s)",
                current_tilt,
                restore_target,
            )
            await self._async_handle_command(SERVICE_STOP_COVER)
            self._last_command = None
            return

        _LOGGER.debug(
            "_start_tilt_restore :: restoring tilt from %d%% to %d%%",
            current_tilt,
            restore_target,
        )

        closing = restore_target < current_tilt

        if self._tilt_strategy.uses_tilt_motor:
            # Dual motor: stop travel, start tilt motor
            await self._async_handle_command(SERVICE_STOP_COVER)
            if closing:
                await self._send_tilt_close()
            else:
                await self._send_tilt_open()
        else:
            # Shared motor (inline): reverse main motor direction
            command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
            await self._async_handle_command(command)

        self.tilt_calc.start_travel(restore_target)
        self._tilt_restore_active = True
        self._last_command = None
        self.start_auto_updater()

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
        """Set the cover to a known position (0=closed, 100=open)."""
        position = kwargs[ATTR_POSITION]
        self._handle_stop()
        await self._async_handle_command(SERVICE_STOP_COVER)
        self.travel_calc.set_position(position)
        if self._has_tilt_support():
            self._tilt_strategy.snap_trackers_to_physical(
                self.travel_calc, self.tilt_calc
            )
        self._last_command = None

    async def set_known_tilt_position(self, **kwargs):
        """Set the tilt to a known position (0=closed, 100=open)."""
        if not self._has_tilt_support():
            return
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
            if (
                self._tilt_strategy is not None
                and not self._tilt_strategy.can_calibrate_tilt()
            ):
                raise HomeAssistantError(
                    "Tilt time calibration not available for this tilt mode"
                )

        if attribute == "travel_startup_delay":
            if not (self._travel_time_close or self._travel_time_open):
                raise HomeAssistantError(
                    "Travel time must be configured before calibrating startup delay"
                )

        if attribute == "tilt_startup_delay":
            if not (self._tilting_time_close or self._tilting_time_open):
                raise HomeAssistantError(
                    "Tilt time must be configured before calibrating startup delay"
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
        elif attribute in ("travel_startup_delay", "tilt_startup_delay"):
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
            self._calibration.move_command = self._resolve_direction(direction, None)
        elif "close" in attribute:
            self._calibration.move_command = SERVICE_CLOSE_COVER
        else:
            self._calibration.move_command = SERVICE_OPEN_COVER
        await self._async_handle_command(self._calibration.move_command)

    async def _start_overhead_test(self, attribute, direction):
        """Start automated step test for motor overhead."""
        from .calibration import CALIBRATION_OVERHEAD_STEPS

        if attribute == "travel_startup_delay":
            position = self.current_cover_position
            move_command = self._resolve_direction(direction, position)
            if move_command == SERVICE_OPEN_COVER:
                travel_time = self._travel_time_open or self._travel_time_close
            else:
                travel_time = self._travel_time_close or self._travel_time_open
        else:
            position = self.current_cover_tilt_position
            move_command = self._resolve_direction(direction, position)
            if move_command == SERVICE_OPEN_COVER:
                travel_time = self._tilting_time_open or self._tilting_time_close
            else:
                travel_time = self._tilting_time_close or self._tilting_time_open

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
            CALIBRATION_MIN_MOVEMENT_INITIAL_PAUSE,
            CALIBRATION_STEP_PAUSE,
        )

        pulse_duration = CALIBRATION_MIN_MOVEMENT_START

        try:
            # Give user time to prepare stop_calibration call
            _LOGGER.debug(
                "min_movement: waiting %.0fs before first pulse",
                CALIBRATION_MIN_MOVEMENT_INITIAL_PAUSE,
            )
            await sleep(CALIBRATION_MIN_MOVEMENT_INITIAL_PAUSE)

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

            # For successful completion, update the tracked position to
            # reflect where the cover ended up (at an endpoint).
            self._set_position_after_calibration(self._calibration)

        self._calibration = None
        self.async_write_ha_state()
        return result

    def _set_position_after_calibration(self, calibration):
        """Update tracked position after successful calibration.

        For travel/tilt time and startup delay tests, the cover has
        reached an endpoint. For min_movement_time the cover only nudged
        slightly so we leave the tracked position unchanged.
        """
        move_command = calibration.move_command
        if not move_command or calibration.attribute == "min_movement_time":
            return

        is_tilt = "tilt" in calibration.attribute
        if is_tilt and not hasattr(self, "tilt_calc"):
            return
        calc = self.tilt_calc if is_tilt else self.travel_calc

        # Cover ended at the endpoint in the direction of travel
        endpoint = 0 if move_command == SERVICE_CLOSE_COVER else 100

        _LOGGER.debug(
            "calibration: resetting %s position to %d",
            "tilt" if is_tilt else "travel",
            endpoint,
        )
        calc.set_position(endpoint)

    def _calculate_calibration_result(self):
        """Calculate the calibration result based on attribute type."""
        attribute = self._calibration.attribute

        if "travel_time" in attribute or "tilt_time" in attribute:
            elapsed = time.monotonic() - self._calibration.started_at
            return round(elapsed, 1)

        if attribute in ("travel_startup_delay", "tilt_startup_delay"):
            if attribute == "travel_startup_delay":
                total_time = self._travel_time_close or self._travel_time_open
            else:
                total_time = self._tilting_time_close or self._tilting_time_open

            if not total_time:
                _LOGGER.warning(
                    "Startup delay calibration requires travel/tilt time to be set first"
                )
                return 0.0
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
            if self._calibration.last_pulse_duration is None:
                _LOGGER.warning(
                    "Min movement calibration stopped before any pulses sent"
                )
                return 0.0
            return round(self._calibration.last_pulse_duration, 2)

        raise ValueError(f"Unexpected calibration attribute: {attribute}")

    def _save_calibration_result(self, attribute, value):
        """Save the calibration result to the config entry options."""
        attribute_to_conf = {
            "travel_time_close": CONF_TRAVEL_TIME_CLOSE,
            "travel_time_open": CONF_TRAVEL_TIME_OPEN,
            "tilt_time_close": CONF_TILT_TIME_CLOSE,
            "tilt_time_open": CONF_TILT_TIME_OPEN,
            "travel_startup_delay": CONF_TRAVEL_STARTUP_DELAY,
            "tilt_startup_delay": CONF_TILT_STARTUP_DELAY,
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

    @staticmethod
    def _extract_coupled_tilt(steps):
        """Extract the tilt target from a movement plan.

        For coupled steps, returns the coupled_tilt value.
        For multi-step plans (sequential), returns the TiltTo target.
        Returns None if no tilt movement in the plan.
        """
        from .tilt_strategies import TiltTo, TravelTo

        for step in steps:
            if isinstance(step, TravelTo) and step.coupled_tilt is not None:
                return step.coupled_tilt
            if isinstance(step, TiltTo):
                return step.target
        return None

    @staticmethod
    def _extract_coupled_travel(steps):
        """Extract the travel target from a movement plan.

        For coupled steps, returns the coupled_travel value.
        For multi-step plans (sequential), returns the TravelTo target.
        Returns None if no travel movement in the plan.
        """
        from .tilt_strategies import TiltTo, TravelTo

        for step in steps:
            if isinstance(step, TiltTo) and step.coupled_travel is not None:
                return step.coupled_travel
            if isinstance(step, TravelTo):
                return step.target
        return None

    def _calculate_pre_step_delay(self, steps) -> float:
        """Calculate delay before the primary calculator should start tracking.

        In sequential tilt mode (single motor), the strategy may plan a
        pre-step (e.g. TiltTo before TravelTo). The pre-step must complete
        before the primary movement begins, since both share the same motor.
        Returns 0.0 if no pre-step or if the strategy uses a separate tilt motor.
        """
        from .tilt_strategies import TiltTo, TravelTo

        if (
            self._tilt_strategy is None
            or self._tilt_strategy.uses_tilt_motor
            or len(steps) < 2
        ):
            return 0.0

        first, second = steps[0], steps[1]

        # TiltTo before TravelTo: tilt is the pre-step
        if isinstance(first, TiltTo) and isinstance(second, TravelTo):
            current_tilt = self.tilt_calc.current_position()
            if current_tilt is None:
                return 0.0
            return self.tilt_calc.calculate_travel_time(current_tilt, first.target)

        # TravelTo before TiltTo: travel is the pre-step
        if isinstance(first, TravelTo) and isinstance(second, TiltTo):
            current_pos = self.travel_calc.current_position()
            if current_pos is None:
                return 0.0
            return self.travel_calc.calculate_travel_time(current_pos, first.target)

        return 0.0

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

    # --- Tilt motor raw commands (dual_motor only) ---

    def _has_tilt_motor(self) -> bool:
        """Return True if tilt motor switches are configured."""
        return bool(self._tilt_open_switch_id and self._tilt_close_switch_id)

    async def _send_tilt_open(self) -> None:
        """Send open to the tilt motor (bypasses position tracker)."""
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_close_switch_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on",
            {"entity_id": self._tilt_open_switch_id},
            False,
        )

    async def _send_tilt_close(self) -> None:
        """Send close to the tilt motor (bypasses position tracker)."""
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_open_switch_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on",
            {"entity_id": self._tilt_close_switch_id},
            False,
        )

    async def _send_tilt_stop(self) -> None:
        """Send stop to the tilt motor (bypasses position tracker)."""
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_open_switch_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_close_switch_id},
            False,
        )
        if self._tilt_stop_switch_id:
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._tilt_stop_switch_id},
                False,
            )
