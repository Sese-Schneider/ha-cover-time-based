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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
from .travel_calculator import TravelCalculator, TravelStatus

from .calibration import CalibrationState
from .cover_calibration import CalibrationMixin
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
)
from .tilt_strategies.planning import (
    calculate_pre_step_delay,
    extract_coupled_tilt,
    extract_coupled_travel,
)

_LOGGER = logging.getLogger(__name__)


class CoverTimeBased(CalibrationMixin, CoverEntity, RestoreEntity):
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

        self._config_entry_id: str | None = None
        self._calibration: CalibrationState | None = None
        self._unsubscribe_auto_updater = None
        self._delay_task = None
        self._startup_delay_task = None
        self._last_command = None
        self._tilt_restore_target: int | None = None
        self._tilt_restore_active: bool = False
        self._pending_travel_target: int | None = None
        self._pending_travel_command: str | None = None
        self._triggered_externally = False
        self._self_initiated_movement = True
        self._pending_switch = {}
        self._pending_switch_timers = {}
        self._state_listener_unsubs = []

        self.travel_calc = TravelCalculator(
            self._travel_time_close,
            self._travel_time_open,
        )
        if self._tilting_time_close is not None and self._tilting_time_open is not None:
            self.tilt_calc = TravelCalculator(
                self._tilting_time_close,
                self._tilting_time_open,
            )

    def _log(self, msg, *args):
        """Log a debug message prefixed with the entity ID."""
        _LOGGER.debug("(%s) " + msg, self.entity_id, *args)

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    async def async_added_to_hass(self):
        """Only cover's position and tilt matters."""
        old_state = await self.async_get_last_state()
        self._log("async_added_to_hass :: oldState %s", old_state)
        pos = (
            old_state.attributes.get(ATTR_CURRENT_POSITION)
            if old_state is not None
            else None
        )
        if old_state is not None and self.travel_calc is not None and pos is not None:
            self.travel_calc.set_position(int(pos))

            tilt_pos = old_state.attributes.get(ATTR_CURRENT_TILT_POSITION)
            if self._has_tilt_support() and tilt_pos is not None:
                self.tilt_calc.set_position(int(tilt_pos))

        # Register state change listeners for switch entities
        for attr in (
            "_open_switch_entity_id",
            "_close_switch_entity_id",
            "_stop_switch_entity_id",
            "_tilt_open_switch_id",
            "_tilt_close_switch_id",
            "_tilt_stop_switch_id",
        ):
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
        """Clean up when entity is removed."""
        for unsub in self._state_listener_unsubs:
            unsub()
        self._state_listener_unsubs.clear()
        for timer in self._pending_switch_timers.values():
            timer()
        self._pending_switch_timers.clear()
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

    # -----------------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------------

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
    def available(self) -> bool:
        """Return True if the cover is properly configured and available."""
        return len(self._get_missing_configuration()) == 0

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

    # -----------------------------------------------------------------------
    # Public HA service handlers
    # -----------------------------------------------------------------------

    async def async_close_cover(self, **kwargs):
        """Close the cover fully."""
        self._require_configured()
        self._log("async_close_cover")
        if self.is_opening:
            self._log("async_close_cover :: currently opening, stopping first")
            await self.async_stop_cover()
        await self._async_move_to_endpoint(target=0)

    async def async_open_cover(self, **kwargs):
        """Open the cover fully."""
        self._require_configured()
        self._log("async_open_cover")
        if self.is_closing:
            self._log("async_open_cover :: currently closing, stopping first")
            await self.async_stop_cover()
        await self._async_move_to_endpoint(target=100)

    async def async_stop_cover(self, **kwargs):
        """Turn the device stop."""
        self._require_configured()
        self._log("async_stop_cover")
        tilt_restore_was_active = self._tilt_restore_active
        tilt_pre_step_was_active = self._pending_travel_target is not None
        self._cancel_startup_delay_task()
        self._cancel_delay_task()
        self._handle_stop()
        if self._has_tilt_support():
            self._tilt_strategy.snap_trackers_to_physical(
                self.travel_calc, self.tilt_calc
            )
        if not self._triggered_externally:
            await self._send_stop()
            if (
                tilt_restore_was_active or tilt_pre_step_was_active
            ) and self._has_tilt_motor():
                await self._send_tilt_stop()
        self.async_write_ha_state()
        self._last_command = None

    async def async_close_cover_tilt(self, **kwargs):
        """Tilt the cover fully closed."""
        self._log("async_close_cover_tilt")
        await self._async_move_tilt_to_endpoint(target=0)

    async def async_open_cover_tilt(self, **kwargs):
        """Tilt the cover fully open."""
        self._log("async_open_cover_tilt")
        await self._async_move_tilt_to_endpoint(target=100)

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        self._require_configured()
        if ATTR_POSITION in kwargs:
            position = kwargs[ATTR_POSITION]
            self._log("async_set_cover_position: %d", position)
            await self.set_position(position)

    async def async_set_cover_tilt_position(self, **kwargs):
        """Move the cover tilt to a specific position."""
        if ATTR_TILT_POSITION in kwargs:
            position = kwargs[ATTR_TILT_POSITION]
            self._log("async_set_cover_tilt_position: %d", position)
            await self.set_tilt_position(position)

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

    # -----------------------------------------------------------------------
    # Movement orchestration
    # -----------------------------------------------------------------------

    async def _async_move_to_endpoint(self, target):
        """Move cover to an endpoint (0=fully closed, 100=fully open)."""
        self._self_initiated_movement = not self._triggered_externally
        await self._abandon_active_lifecycle()

        closing = target == 0
        command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
        opposite_command = SERVICE_OPEN_COVER if closing else SERVICE_CLOSE_COVER

        # Check startup delay conflicts BEFORE position check, since during
        # startup delay the position hasn't started changing yet.
        if self._startup_delay_task and not self._startup_delay_task.done():
            if self._last_command == opposite_command:
                self._log(
                    "_async_move_to_endpoint :: direction change, cancelling startup delay"
                )
                self._cancel_startup_delay_task()
                await self._async_handle_command(SERVICE_STOP_COVER)
                self._last_command = None
                return
            else:
                self._log(
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

        self._log(
            "_async_move_to_endpoint :: target=%d, travel_distance=%f%%, movement_time=%fs",
            target,
            travel_distance,
            movement_time,
        )

        self._last_command = command

        current_pos = self.travel_calc.current_position()
        current_tilt = (
            self.tilt_calc.current_position() if self._tilt_strategy else None
        )
        tilt_target, pre_step_delay, started = await self._plan_tilt_for_travel(
            target, command, current_pos, current_tilt
        )
        if started:
            return

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

    async def _async_move_tilt_to_endpoint(self, target):
        """Move tilt to an endpoint (0=fully closed, 100=fully open)."""
        await self._abandon_active_lifecycle()

        closing = target == 0
        command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
        opposite_command = SERVICE_OPEN_COVER if closing else SERVICE_CLOSE_COVER

        if self._startup_delay_task and not self._startup_delay_task.done():
            if self._last_command == opposite_command:
                self._log(
                    "_async_move_tilt_to_endpoint :: direction change, cancelling startup delay"
                )
                self._cancel_startup_delay_task()
                await self._async_handle_command(SERVICE_STOP_COVER)
                if (
                    self._tilt_strategy is not None
                    and self._tilt_strategy.uses_tilt_motor
                ):
                    await self._send_tilt_stop()
            else:
                self._log(
                    "_async_move_tilt_to_endpoint :: startup delay already active, not restarting"
                )
                return

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)
            if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
                await self._send_tilt_stop()

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
                travel_target = extract_coupled_travel(steps)
                pre_step_delay = calculate_pre_step_delay(
                    steps, self._tilt_strategy, self.tilt_calc, self.travel_calc
                )

        self._log(
            "_async_move_tilt_to_endpoint :: target=%d, tilt_distance=%f%%, movement_time=%fs, travel_pos=%s",
            target,
            tilt_distance,
            movement_time,
            travel_target if travel_target is not None else "N/A",
        )

        self._last_command = command
        if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
            if closing:
                await self._send_tilt_close()
            else:
                await self._send_tilt_open()
        else:
            await self._async_handle_command(command)
        self._begin_movement(
            target,
            travel_target,
            self.tilt_calc,
            self.travel_calc,
            self._tilt_startup_delay,
            pre_step_delay,
        )

    async def set_position(self, position):
        """Move cover to a designated position."""
        self._self_initiated_movement = not self._triggered_externally
        await self._abandon_active_lifecycle()
        current = self.travel_calc.current_position()
        target = position
        self._log(
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
            self._log("set_position :: stopping active travel movement")
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

        current_tilt = (
            self.tilt_calc.current_position() if self._tilt_strategy else None
        )
        tilt_target, pre_step_delay, started = await self._plan_tilt_for_travel(
            target, command, current, current_tilt
        )
        if started:
            return

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
        await self._abandon_active_lifecycle()
        current = self.tilt_calc.current_position()
        target = position
        self._log(
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
            if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
                await self._send_tilt_stop()
            current = self.tilt_calc.current_position()
            if target == current:
                return

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)
            if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
                await self._send_tilt_stop()

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
                travel_target = extract_coupled_travel(steps)
                pre_step_delay = calculate_pre_step_delay(
                    steps, self._tilt_strategy, self.tilt_calc, self.travel_calc
                )

        if self._is_movement_too_short(
            movement_time, target, current, "set_tilt_position"
        ):
            return

        self._last_command = command

        if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
            if closing:
                await self._send_tilt_close()
            else:
                await self._send_tilt_open()
        else:
            await self._async_handle_command(command)
        self._begin_movement(
            target,
            travel_target,
            self.tilt_calc,
            self.travel_calc,
            self._tilt_startup_delay,
            pre_step_delay,
        )

    async def _plan_tilt_for_travel(
        self, target: int, command: str, current_pos, current_tilt
    ) -> tuple[int | None, float, bool]:
        """Plan tilt coupling for a travel movement.

        Returns (tilt_target, pre_step_delay, started_pre_step).
        If started_pre_step is True, the caller should return immediately
        because _start_tilt_pre_step has taken over the movement lifecycle.
        """
        tilt_target = None
        pre_step_delay = 0.0
        self._tilt_restore_target = None

        if self._tilt_strategy is None:
            return tilt_target, pre_step_delay, False

        if current_pos is None or current_tilt is None:
            return tilt_target, pre_step_delay, False

        steps = self._tilt_strategy.plan_move_position(
            target, current_pos, current_tilt
        )
        tilt_target = extract_coupled_tilt(steps)
        pre_step_delay = calculate_pre_step_delay(
            steps, self._tilt_strategy, self.tilt_calc, self.travel_calc
        )

        # Dual motor: tilt to safe position first, then travel
        if (
            tilt_target is not None
            and self._tilt_strategy.uses_tilt_motor
            and current_tilt != tilt_target
        ):
            restore = target if target in (0, 100) else current_tilt
            await self._start_tilt_pre_step(tilt_target, target, command, restore)
            return tilt_target, pre_step_delay, True

        # Dual motor: pre-step skipped, but still snap tilt to endpoint
        if (
            tilt_target is not None
            and self._tilt_strategy.uses_tilt_motor
            and target in (0, 100)
            and current_tilt != target
        ):
            self._tilt_restore_target = target

        # Shared motor with restore: save tilt for post-travel restore
        if (
            tilt_target is not None
            and self._tilt_strategy.restores_tilt
            and not self._tilt_strategy.uses_tilt_motor
            and target not in (0, 100)
        ):
            self._tilt_restore_target = current_tilt

        return tilt_target, pre_step_delay, False

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
                self._log(
                    "_handle_pre_movement_checks :: startup delay active, skipping"
                )
                return False, is_direction_change
            self._log(
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

    def _has_tilt_support(self):
        """Return if cover has tilt support."""
        return self._tilt_strategy is not None and hasattr(self, "tilt_calc")

    # -----------------------------------------------------------------------
    # Movement tracking
    # -----------------------------------------------------------------------

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
        self._log(
            "_execute_with_startup_delay :: waiting %fs before starting position tracking",
            startup_delay,
        )
        try:
            await sleep(startup_delay)
            self._log(
                "_execute_with_startup_delay :: startup delay complete, starting position tracking"
            )
            start_callback()
            self._startup_delay_task = None
        except asyncio.CancelledError:
            self._log("_execute_with_startup_delay :: startup delay cancelled")
            self._startup_delay_task = None
            raise

    def _cancel_delay_task(self):
        """Cancel any active delay task."""
        if self._delay_task is not None and not self._delay_task.done():
            self._log("_cancel_delay_task :: cancelling active delay task")
            self._delay_task.cancel()
            self._delay_task = None
            return True
        return False

    def _cancel_startup_delay_task(self):
        """Cancel any active startup delay task."""
        if self._startup_delay_task is not None and not self._startup_delay_task.done():
            self._log(
                "_cancel_startup_delay_task :: cancelling active startup delay task"
            )
            self._startup_delay_task.cancel()
            self._startup_delay_task = None

    def start_auto_updater(self):
        """Start the autoupdater to update HASS while cover is moving."""
        self._log("start_auto_updater")
        if self._unsubscribe_auto_updater is None:
            self._log("init _unsubscribe_auto_updater")
            interval = timedelta(seconds=0.1)
            self._unsubscribe_auto_updater = async_track_time_interval(
                self.hass, self.auto_updater_hook, interval
            )

    @callback
    def auto_updater_hook(self, now):
        """Call for the autoupdater."""
        self.async_schedule_update_ha_state()
        if self.position_reached():
            self._log("auto_updater_hook :: position_reached")
            self.stop_auto_updater()
        self.hass.async_create_task(self.auto_stop_if_necessary())

    def stop_auto_updater(self):
        """Stop the autoupdater."""
        self._log("stop_auto_updater")
        if self._unsubscribe_auto_updater is not None:
            self._unsubscribe_auto_updater()
            self._unsubscribe_auto_updater = None

    def position_reached(self):
        """Return if cover has reached its final position."""
        return self.travel_calc.position_reached() and (
            not self._has_tilt_support() or self.tilt_calc.position_reached()
        )

    # -----------------------------------------------------------------------
    # Movement lifecycle (auto-stop, pre-step, restore)
    # -----------------------------------------------------------------------

    async def auto_stop_if_necessary(self):
        """Do auto stop if necessary."""
        if self.position_reached():
            self._log(
                "auto_stop_if_necessary :: position reached (self_initiated=%s)",
                self._self_initiated_movement,
            )
            self.travel_calc.stop()
            if self._has_tilt_support():
                self.tilt_calc.stop()

            if not self._self_initiated_movement:
                # Movement was triggered externally — just stop tracking,
                # don't send relay commands.
                self._log(
                    "auto_stop_if_necessary :: external movement, skipping relay stop"
                )
                if self._tilt_strategy is not None:
                    self._tilt_strategy.snap_trackers_to_physical(
                        self.travel_calc, self.tilt_calc
                    )
                self._last_command = None
                return

            if self._tilt_restore_active:
                self._log("auto_stop_if_necessary :: tilt restore complete")
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
                self._log("auto_stop_if_necessary :: tilt pre-step complete")
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
                self._log(
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

    async def _delayed_stop(self, delay):
        """Stop the relay after a delay."""
        self._log("_delayed_stop :: waiting %fs before stopping relay", delay)
        try:
            await sleep(delay)
            self._log("_delayed_stop :: delay complete, stopping relay")
            await self._async_handle_command(SERVICE_STOP_COVER)
            self._last_command = None
            self._delay_task = None
        except asyncio.CancelledError:
            self._log("_delayed_stop :: delay cancelled")
            self._delay_task = None
            raise

    async def _abandon_active_lifecycle(self):
        """Abandon any active multi-phase tilt lifecycle (pre-step, restore).

        Called at the start of every movement method. If a tilt restore or
        tilt pre-step is in progress, stops all hardware and calculators.
        Always clears the pending restore target so it won't fire after
        the next travel completes.
        """
        was_restoring = self._tilt_restore_active
        was_pre_stepping = self._pending_travel_target is not None

        # Always clear multi-phase state
        self._tilt_restore_target = None
        self._tilt_restore_active = False
        self._pending_travel_target = None
        self._pending_travel_command = None

        if not was_restoring and not was_pre_stepping:
            return

        self._log(
            "_abandon_active_lifecycle :: abandoning %s",
            "tilt restore" if was_restoring else "tilt pre-step",
        )

        self._cancel_startup_delay_task()

        if self.travel_calc.is_traveling():
            self.travel_calc.stop()
        if self._has_tilt_support() and self.tilt_calc.is_traveling():
            self.tilt_calc.stop()
        self.stop_auto_updater()

        await self._async_handle_command(SERVICE_STOP_COVER)
        if self._has_tilt_motor() and not self._triggered_externally:
            await self._send_tilt_stop()

    def _stop_travel_if_traveling(self):
        """Stop cover movement if it's currently traveling."""
        if self.travel_calc.is_traveling():
            self._log("_stop_travel_if_traveling :: stopping cover movement")
            self.travel_calc.stop()
            if self._has_tilt_support() and self.tilt_calc.is_traveling():
                self._log("_stop_travel_if_traveling :: also stopping tilt")
                self.tilt_calc.stop()

    def _handle_stop(self):
        """Handle stop"""
        self._tilt_restore_target = None
        self._tilt_restore_active = False
        self._pending_travel_target = None
        self._pending_travel_command = None

        if self.travel_calc.is_traveling():
            self._log("_handle_stop :: button stops cover movement")
            self.travel_calc.stop()
            self.stop_auto_updater()

        if self._has_tilt_support() and self.tilt_calc.is_traveling():
            self._log("_handle_stop :: button stops tilt movement")
            self.tilt_calc.stop()
            self.stop_auto_updater()

    async def _start_tilt_pre_step(
        self, tilt_target, travel_target, travel_command, restore_target
    ):
        """Move tilt to safe position before travel (dual_motor).

        Sends the tilt motor command and starts tilt_calc. When tilt reaches
        target, auto_stop_if_necessary will call _start_pending_travel to
        begin the actual cover travel.
        """
        current_tilt = self.tilt_calc.current_position()
        self._log(
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
        if not self._triggered_externally:
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
        assert target is not None and command is not None
        self._pending_travel_target = None
        self._pending_travel_command = None

        self._log(
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
        if restore_target is None:
            return

        current_tilt = self.tilt_calc.current_position()
        if current_tilt is None or current_tilt == restore_target:
            self._log(
                "_start_tilt_restore :: no restore needed (current=%s, target=%s)",
                current_tilt,
                restore_target,
            )
            await self._async_handle_command(SERVICE_STOP_COVER)
            self._last_command = None
            return

        self._log(
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

    # -----------------------------------------------------------------------
    # Relay command dispatch
    # -----------------------------------------------------------------------

    async def _async_handle_command(self, command, *args):
        cmd = command
        if command == SERVICE_CLOSE_COVER:
            cmd = "DOWN"
            self._state = False
            self._last_command = command
            if not self._triggered_externally:
                await self._send_close()
        elif command == SERVICE_OPEN_COVER:
            cmd = "UP"
            self._state = True
            self._last_command = command
            if not self._triggered_externally:
                await self._send_open()
        elif command == SERVICE_STOP_COVER:
            cmd = "STOP"
            self._state = True
            if not self._triggered_externally:
                await self._send_stop()

        self._log("_async_handle_command :: %s", cmd)
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

    # -----------------------------------------------------------------------
    # Tilt motor relay commands (dual_motor only)
    # -----------------------------------------------------------------------

    def _has_tilt_motor(self) -> bool:
        """Return True if a dedicated tilt motor is configured (dual_motor mode)."""
        return (
            self._tilt_strategy is not None
            and self._tilt_strategy.uses_tilt_motor
            and bool(self._tilt_open_switch_id and self._tilt_close_switch_id)
        )

    async def _send_tilt_open(self) -> None:
        """Send open to the tilt motor (bypasses position tracker)."""
        if self._switch_is_on(self._tilt_close_switch_id):
            self._mark_switch_pending(self._tilt_close_switch_id, 1)
        self._mark_switch_pending(self._tilt_open_switch_id, 2)
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
        if self._switch_is_on(self._tilt_open_switch_id):
            self._mark_switch_pending(self._tilt_open_switch_id, 1)
        self._mark_switch_pending(self._tilt_close_switch_id, 2)
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
        if self._switch_is_on(self._tilt_open_switch_id):
            self._mark_switch_pending(self._tilt_open_switch_id, 1)
        if self._switch_is_on(self._tilt_close_switch_id):
            self._mark_switch_pending(self._tilt_close_switch_id, 1)
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
            self._mark_switch_pending(self._tilt_stop_switch_id, 2)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._tilt_stop_switch_id},
                False,
            )

    # -----------------------------------------------------------------------
    # Switch echo filtering
    # -----------------------------------------------------------------------

    def _switch_is_on(self, entity_id) -> bool:
        """Check if a switch entity is currently on."""
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == "on"

    def _mark_switch_pending(self, entity_id, expected_transitions):
        """Mark a switch as having pending echo transitions to ignore."""
        self._pending_switch[entity_id] = (
            self._pending_switch.get(entity_id, 0) + expected_transitions
        )
        self._log(
            "_mark_switch_pending :: %s pending=%d",
            entity_id,
            self._pending_switch[entity_id],
        )

        # Cancel any existing timeout for this switch
        if entity_id in self._pending_switch_timers:
            self._pending_switch_timers[entity_id]()

        # Safety timeout: clear pending after 5 seconds
        @callback
        def _clear_pending(_now):
            if entity_id in self._pending_switch:
                self._log("_mark_switch_pending :: timeout clearing %s", entity_id)
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

        self._log(
            "_async_switch_state_changed :: %s: %s -> %s (pending=%s)",
            entity_id,
            old_val,
            new_val,
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
            self._log(
                "_async_switch_state_changed :: echo filtered, remaining=%s",
                self._pending_switch.get(entity_id, 0),
            )
            return

        # Tilt switches: pulse-mode (ON→OFF = command complete)
        if entity_id in (
            self._tilt_open_switch_id,
            self._tilt_close_switch_id,
            self._tilt_stop_switch_id,
        ):
            self._triggered_externally = True
            try:
                await self._handle_external_tilt_state_change(
                    entity_id, old_val, new_val
                )
            finally:
                self._triggered_externally = False
            return

        # External state change detected — handle per mode
        self._triggered_externally = True
        try:
            await self._handle_external_state_change(entity_id, old_val, new_val)
        finally:
            self._triggered_externally = False

    # -----------------------------------------------------------------------
    # External state change handlers
    # -----------------------------------------------------------------------

    async def _handle_external_tilt_state_change(self, entity_id, old_val, new_val):
        """Handle external state change on tilt switches (dual_motor).

        Tilt switches use pulse-mode behavior: a complete ON→OFF pulse
        represents a command. We react on the OFF transition (pulse complete).
        """
        if old_val != "on" or new_val != "off":
            return

        if entity_id == self._tilt_open_switch_id:
            self._log(
                "_handle_external_tilt_state_change :: external tilt open pulse detected"
            )
            await self.async_open_cover_tilt()
        elif entity_id == self._tilt_close_switch_id:
            self._log(
                "_handle_external_tilt_state_change :: external tilt close pulse detected"
            )
            await self.async_close_cover_tilt()
        elif entity_id == self._tilt_stop_switch_id:
            self._log(
                "_handle_external_tilt_state_change :: external tilt stop pulse detected"
            )
            await self.async_stop_cover()

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle external state change. Override in subclasses for mode-specific behavior."""
