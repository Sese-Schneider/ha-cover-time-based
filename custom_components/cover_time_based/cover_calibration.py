"""Calibration mixin for time-based cover entities."""

from __future__ import annotations

import asyncio
import logging
import time
from asyncio import sleep
from typing import TYPE_CHECKING, Any

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
)
from homeassistant.exceptions import HomeAssistantError

from .calibration import CalibrationState

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .travel_calculator import TravelCalculator

_LOGGER = logging.getLogger(__name__)


class CalibrationMixin:
    """Mixin providing calibration functionality for CoverTimeBased."""

    if TYPE_CHECKING:
        hass: HomeAssistant
        _calibration: CalibrationState | None
        _tilt_strategy: Any
        _travel_time_close: float | None
        _travel_time_open: float | None
        _tilting_time_close: float | None
        _tilting_time_open: float | None
        current_cover_position: int | None
        current_cover_tilt_position: int | None
        travel_calc: TravelCalculator
        tilt_calc: TravelCalculator

        async def _async_handle_command(self, _command: str, *_args: Any) -> None: ...
        async def _send_stop(self) -> None: ...
        def async_write_ha_state(self) -> None: ...

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
        assert self._calibration is not None
        if direction:
            self._calibration.move_command = self._resolve_direction(direction, None)
        elif "close" in attribute:
            self._calibration.move_command = SERVICE_CLOSE_COVER
        else:
            self._calibration.move_command = SERVICE_OPEN_COVER
        await self._async_handle_command(self._calibration.move_command)

    async def _start_overhead_test(self, attribute, direction):
        """Start automated step test for motor overhead."""
        assert self._calibration is not None
        from .calibration import (
            CALIBRATION_OVERHEAD_STEPS,
            CALIBRATION_TILT_OVERHEAD_STEPS,
        )

        is_tilt = "tilt" in attribute

        if not is_tilt:
            position = self.current_cover_position
            move_command = self._resolve_direction(direction, position)
            if move_command == SERVICE_OPEN_COVER:
                travel_time = self._travel_time_open or self._travel_time_close
            else:
                travel_time = self._travel_time_close or self._travel_time_open
            num_steps = CALIBRATION_OVERHEAD_STEPS
            # Zero startup delay during test so tracker doesn't compensate
            self._calibration.saved_startup_delay = self._travel_startup_delay
            self._travel_startup_delay = None
        else:
            position = self.current_cover_tilt_position
            move_command = self._resolve_direction(direction, position)
            if move_command == SERVICE_OPEN_COVER:
                travel_time = self._tilting_time_open or self._tilting_time_close
            else:
                travel_time = self._tilting_time_close or self._tilting_time_open
            num_steps = CALIBRATION_TILT_OVERHEAD_STEPS
            # Zero startup delay during test so tracker doesn't compensate
            self._calibration.saved_startup_delay = self._tilt_startup_delay
            self._tilt_startup_delay = None

        assert travel_time is not None
        _LOGGER.debug(
            "overhead test: position=%s, direction=%s, travel_time=%.2f",
            position,
            move_command,
            travel_time,
        )

        total_divisions = num_steps + 2
        step_pct = 100 // total_divisions
        step_duration = travel_time * step_pct / 100
        self._calibration.step_duration = step_duration
        self._calibration.move_command = move_command

        self._calibration.automation_task = self.hass.async_create_task(
            self._run_overhead_steps(step_duration, num_steps, step_pct, is_tilt)
        )

    async def _run_overhead_steps(self, _step_duration, num_steps, step_pct, is_tilt):
        """Execute stepped moves then one continuous move for overhead test.

        Phase 1: num_steps stepped moves using the travel calculator's
        position tracking (same timing as normal operation).  After each
        step, force-set position to compensate for motor startup delay.
        Phase 2: Continuous move for the remaining distance.
        The user calls stop_calibration when the cover reaches the endpoint.
        """
        assert self._calibration is not None
        from .calibration import CALIBRATION_STEP_PAUSE

        move_command = self._calibration.move_command
        assert move_command is not None
        closing = move_command == SERVICE_CLOSE_COVER
        calc = self.tilt_calc if is_tilt else self.travel_calc

        try:
            # Phase 1: Stepped moves using travel calculator timing
            for i in range(num_steps):
                pct = (i + 1) * step_pct
                target = (100 - pct) if closing else pct
                _LOGGER.debug(
                    "overhead step %d/%d: target=%d%%",
                    i + 1,
                    num_steps,
                    target,
                )
                calc.start_travel(target)
                await self._async_handle_command(move_command)

                # Wait for travel calculator to say position reached
                while calc.current_position() != target:
                    await sleep(0.05)

                await self._send_stop()
                calc.stop()

                # Force position — motor fell short due to startup delay
                calc.set_position(target)
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
        assert self._calibration is not None
        assert self._calibration.move_command is not None
        from .calibration import (
            CALIBRATION_MIN_MOVEMENT_START,
            CALIBRATION_MIN_MOVEMENT_INCREMENT,
            CALIBRATION_MIN_MOVEMENT_INITIAL_PAUSE,
            CALIBRATION_STEP_PAUSE,
        )

        move_command = self._calibration.move_command
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

                step_start = time.monotonic()
                await self._async_handle_command(move_command)
                elapsed = time.monotonic() - step_start
                await sleep(max(0, pulse_duration - elapsed))
                await self._send_stop()
                self.async_write_ha_state()

                await sleep(CALIBRATION_STEP_PAUSE)
                pulse_duration += CALIBRATION_MIN_MOVEMENT_INCREMENT
        except asyncio.CancelledError:
            pass

    async def _calibration_timeout(self):
        """Handle calibration timeout."""
        assert self._calibration is not None
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

        # Restore startup delay that was zeroed during overhead test
        if self._calibration.saved_startup_delay is not None:
            attr = self._calibration.attribute
            if "tilt" in attr:
                self._tilt_startup_delay = self._calibration.saved_startup_delay
            else:
                self._travel_startup_delay = self._calibration.saved_startup_delay

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
        assert self._calibration is not None
        attribute = self._calibration.attribute

        if "travel_time" in attribute or "tilt_time" in attribute:
            elapsed = time.monotonic() - self._calibration.started_at
            return round(elapsed, 1)

        if attribute in ("travel_startup_delay", "tilt_startup_delay"):
            closing = self._calibration.move_command == SERVICE_CLOSE_COVER
            if attribute == "travel_startup_delay":
                if closing:
                    total_time = self._travel_time_close or self._travel_time_open
                else:
                    total_time = self._travel_time_open or self._travel_time_close
            else:
                if closing:
                    total_time = self._tilting_time_close or self._tilting_time_open
                else:
                    total_time = self._tilting_time_open or self._tilting_time_close

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
            # Subtract pulse overhead from continuous phase start for
            # pulse/toggle modes (the ON command includes a relay pulse
            # that doesn't contribute to motor travel time).
            pulse_time = getattr(self, "_pulse_time", None)
            if pulse_time:
                continuous_time -= pulse_time
            # Each step covers 1/10 of travel; remaining depends on step count
            expected_remaining = (1.0 - step_count / 10.0) * total_time
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
