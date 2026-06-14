"""Toggle mode cover."""

import asyncio
import logging
import time
from asyncio import sleep

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
)

from .cover_switch import SwitchCoverTimeBased

_LOGGER = logging.getLogger(__name__)

# Short debounce window (seconds) to suppress contact bounce on external
# momentary switches — a few tens of ms is enough in practice. Must be
# shorter than any realistic human click cadence (≥ 200ms between
# deliberate presses) so legitimate rapid toggles (e.g. "start then stop")
# are not dropped.
_EXTERNAL_TOGGLE_DEBOUNCE = 0.1


class ToggleModeCover(SwitchCoverTimeBased):
    """Cover controlled by toggle-style relays (toggle mode).

    In toggle mode, the motor controller toggles state on each pulse.
    A second pulse on the same direction button stops the motor.
    _send_stop therefore re-presses the last-used direction button.

    The send methods return immediately after the ON edge so that position
    tracking starts from the moment the motor begins moving. The pulse
    completion (sleep + turn_off) runs in the background.
    """

    def __init__(self, pulse_time, **kwargs):
        super().__init__(**kwargs)
        self._pulse_time = pulse_time
        self._last_external_toggle_time = {}
        self._last_tilt_direction = None
        # In-flight _complete_pulse tasks, keyed by relay entity_id. Tracked so
        # a new pulse on the same relay can cancel the stale completion before
        # it releases the fresh pulse mid-flight (see _pulse_relay).
        self._pulse_tasks = {}
        # Serializes _pulse_relay: cover service calls aren't serialized by HA
        # (no PARALLEL_UPDATES), so concurrent pulses on the same relay could
        # otherwise interleave between the task pop and the task store, each
        # missing the other's in-flight pulse.
        self._pulse_lock = asyncio.Lock()

    async def _complete_pulse(self, entity_id):
        """Complete a relay pulse by turning OFF after pulse_time.

        Only releases the relay if this task is still the one registered for it.
        A newer pulse replaces the registration (and cancels this task), but
        asyncio cancellation is cooperative — a task already past the sleep and
        into the turn_off call could otherwise still fire it and release the
        fresh pulse. Keying off the registration makes that impossible
        regardless of cancellation timing.
        """
        try:
            await sleep(self._pulse_time)
            if self._pulse_tasks.get(entity_id) is not asyncio.current_task():
                return
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": entity_id},
                False,
            )
        except asyncio.CancelledError:
            pass

    async def _pulse_relay(self, entity_id):
        """Pulse a relay ON with a guaranteed edge, then schedule its release.

        A toggle motor controller acts on the relay's rising edge. The OFF half
        of a pulse is deferred to a background ``_complete_pulse`` task, so a
        new command can arrive while the relay is still held ON. A bare
        ``turn_on`` on an already-on relay produces no edge — the motor misses
        the pulse while the position tracker keeps advancing, desyncing the
        entity from the physical cover.

        Cancel any stale completion for this relay (so it can't release the
        fresh pulse mid-flight) and, if the relay is still held ON, drive it OFF
        first so the ``turn_on`` is a genuine edge. The release OFF echo is
        absorbed by the pending count the caller already marked for this relay's
        own completion turn_off, so no extra echo bookkeeping is needed. Finally
        schedule (and track) the OFF half so the next pulse can cancel it.

        "Still held ON" is decided by the in-flight pulse *task*, not by
        ``_switch_is_on``: a real switch confirms its state only after a device
        round-trip (tens of ms), which is far longer than the gap between rapid
        presses, so the reported state still reads OFF while our own pulse holds
        the relay ON. ``_switch_is_on`` is kept as a secondary trigger for the
        relay being ON for some other reason (e.g. left ON across a restart);
        that path emits one extra OFF echo over the caller's pending budget, but
        a stray OFF is harmless — external handlers act only on the rising edge.

        The whole body runs under ``_pulse_lock`` so the pop/cancel/turn_on/
        store sequence is atomic: HA does not serialize cover service calls, so
        two concurrent pulses on the same relay would otherwise both pop before
        either stored, both miss the in-flight pulse, and skip the release.
        """
        async with self._pulse_lock:
            stale = self._pulse_tasks.pop(entity_id, None)
            pulse_in_flight = stale is not None and not stale.done()
            if pulse_in_flight:
                stale.cancel()
            if pulse_in_flight or self._switch_is_on(entity_id):
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_off",
                    {"entity_id": entity_id},
                    False,
                )
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": entity_id},
                False,
            )
            self._pulse_tasks[entity_id] = self.hass.async_create_task(
                self._complete_pulse(entity_id)
            )

    async def async_stop_cover(self, **kwargs):
        """Stop the cover, only sending relay command if it was active."""
        was_active = (
            self.is_opening
            or self.is_closing
            or (self._startup_delay_task and not self._startup_delay_task.done())
            or (self._delay_task and not self._delay_task.done())
        )
        tilt_restore_was_active = self._tilt_restore_active
        tilt_pre_step_was_active = self._pending_travel_target is not None
        self._cancel_startup_delay_task()
        self._cancel_delay_task()
        self._handle_stop()
        if self._tilt_strategy is not None:
            self._tilt_strategy.snap_trackers_to_physical(
                self.travel_calc, self.tilt_calc
            )
        if not self._triggered_externally and was_active:
            await self._send_stop()
            if (
                tilt_restore_was_active or tilt_pre_step_was_active
            ) and self._has_tilt_motor():
                await self._send_tilt_stop()
        self.async_write_ha_state()
        self._last_command = None
        self._last_tilt_direction = None

    # --- External state change handlers ---

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle external state change in toggle mode.

        Only the rising edge (OFF→ON) is interesting — this is the button
        press. The ON→OFF transition is just the relay releasing and is ignored.

        A debounce prevents double-triggering for momentary switches that
        produce OFF->ON->OFF per click.
        """
        if new_val != "on":
            return

        now = time.monotonic()
        last = self._last_external_toggle_time.get(entity_id, 0)
        if now - last < _EXTERNAL_TOGGLE_DEBOUNCE:
            self._log(
                "_handle_external_state_change :: debounced toggle on %s",
                entity_id,
            )
            return
        self._last_external_toggle_time[entity_id] = now

        if entity_id == self._open_switch_entity_id:
            if self.is_opening:
                # Same direction while opening: toggle-style motor controllers
                # latch OFF on a second same-direction pulse → stop.
                self._log(
                    "_handle_external_state_change ::"
                    " open toggle while opening, stopping"
                )
                await self.async_stop_cover()
            else:
                # Idle or closing (opposite direction): async_open_cover
                # handles the direction-change stop-and-reverse internally.
                self._log(
                    "_handle_external_state_change :: external open toggle detected"
                )
                await self.async_open_cover()
        elif entity_id == self._close_switch_entity_id:
            if self.is_closing:
                self._log(
                    "_handle_external_state_change ::"
                    " close toggle while closing, stopping"
                )
                await self.async_stop_cover()
            else:
                self._log(
                    "_handle_external_state_change :: external close toggle detected"
                )
                await self.async_close_cover()

    async def _handle_external_tilt_state_change(self, entity_id, old_val, new_val):
        """Handle external tilt state change in toggle mode.

        Only reacts on rising edge (OFF→ON). Same debounce as travel handler.
        If tilt is already moving, treat any toggle as stop.
        """
        if new_val != "on":
            return

        now = time.monotonic()
        last = self._last_external_toggle_time.get(entity_id, 0)
        if now - last < _EXTERNAL_TOGGLE_DEBOUNCE:
            self._log(
                "_handle_external_tilt_state_change :: debounced toggle on %s",
                entity_id,
            )
            return
        self._last_external_toggle_time[entity_id] = now

        if entity_id == self._tilt_open_switch_id:
            if self.tilt_calc.is_traveling():
                self._log(
                    "_handle_external_tilt_state_change ::"
                    " tilt open toggle while traveling, stopping"
                )
                await self.async_stop_cover()
            else:
                self._log(
                    "_handle_external_tilt_state_change :: external tilt open toggle detected"
                )
                await self.async_open_cover_tilt()
        elif entity_id == self._tilt_close_switch_id:
            if self.tilt_calc.is_traveling():
                self._log(
                    "_handle_external_tilt_state_change ::"
                    " tilt close toggle while traveling, stopping"
                )
                await self.async_stop_cover()
            else:
                self._log(
                    "_handle_external_tilt_state_change :: external tilt close toggle detected"
                )
                await self.async_close_cover_tilt()

    # --- Raw direction commands (calibration screen) ---

    async def _raw_direction_command(self, command: str) -> None:
        """In toggle mode, opposite-direction = stop, not reverse.

        To change direction: stop first, wait for pulse, then send new direction.
        """
        if command in ("open", "close"):
            opposite = SERVICE_CLOSE_COVER if command == "open" else SERVICE_OPEN_COVER
            if self._last_command == opposite:
                await self._send_stop()
                await sleep(self._pulse_time)
        elif command in ("tilt_open", "tilt_close"):
            opposite_dir = "close" if command == "tilt_open" else "open"
            if self._last_tilt_direction == opposite_dir:
                await self._send_tilt_stop()
                await sleep(self._pulse_time)
        await super()._raw_direction_command(command)

    # --- Internal relay commands ---

    async def _send_open(self) -> None:
        if self._switch_is_on(self._close_switch_entity_id):
            self._mark_switch_pending(self._close_switch_entity_id, 1)
        self._mark_switch_pending(self._open_switch_entity_id, 2)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._close_switch_entity_id},
            False,
        )
        # Motor controller acts on ON edge; complete pulse in background
        await self._pulse_relay(self._open_switch_entity_id)

    async def _send_close(self) -> None:
        if self._switch_is_on(self._open_switch_entity_id):
            self._mark_switch_pending(self._open_switch_entity_id, 1)
        self._mark_switch_pending(self._close_switch_entity_id, 2)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._open_switch_entity_id},
            False,
        )
        # Motor controller acts on ON edge; complete pulse in background
        await self._pulse_relay(self._close_switch_entity_id)

    async def _send_stop(self) -> None:
        if self._last_command == SERVICE_CLOSE_COVER:
            self._mark_switch_pending(self._close_switch_entity_id, 2)
            # Motor toggles on ON edge; complete pulse in background
            await self._pulse_relay(self._close_switch_entity_id)
        elif self._last_command == SERVICE_OPEN_COVER:
            self._mark_switch_pending(self._open_switch_entity_id, 2)
            # Motor toggles on ON edge; complete pulse in background
            await self._pulse_relay(self._open_switch_entity_id)
        else:
            self._log("_send_stop :: toggle mode with no last command, skipping")

    # --- Tilt motor relay commands ---

    async def _send_tilt_open(self) -> None:
        if self._switch_is_on(self._tilt_close_switch_id):
            self._mark_switch_pending(self._tilt_close_switch_id, 1)
        self._mark_switch_pending(self._tilt_open_switch_id, 2)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_close_switch_id},
            False,
        )
        await self._pulse_relay(self._tilt_open_switch_id)
        self._last_tilt_direction = "open"

    async def _send_tilt_close(self) -> None:
        if self._switch_is_on(self._tilt_open_switch_id):
            self._mark_switch_pending(self._tilt_open_switch_id, 1)
        self._mark_switch_pending(self._tilt_close_switch_id, 2)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_open_switch_id},
            False,
        )
        await self._pulse_relay(self._tilt_close_switch_id)
        self._last_tilt_direction = "close"

    async def _send_tilt_stop(self) -> None:
        if self._last_tilt_direction == "close":
            self._mark_switch_pending(self._tilt_close_switch_id, 2)
            await self._pulse_relay(self._tilt_close_switch_id)
        elif self._last_tilt_direction == "open":
            self._mark_switch_pending(self._tilt_open_switch_id, 2)
            await self._pulse_relay(self._tilt_open_switch_id)
        else:
            self._log(
                "_send_tilt_stop :: toggle mode with no last tilt direction, skipping"
            )
        self._last_tilt_direction = None
