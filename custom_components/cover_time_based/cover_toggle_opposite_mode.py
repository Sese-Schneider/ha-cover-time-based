"""Opposite-button toggle mode cover."""

import logging

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from .cover_toggle_base import ToggleBaseCover

_LOGGER = logging.getLogger(__name__)


class ToggleOppositeModeCover(ToggleBaseCover):
    """Cover controlled by toggle relays that stop on the OPPOSITE button.

    On this hardware a pulse on the opposite direction relay halts a moving
    motor (it does NOT reverse), while a same-direction re-press is ignored and
    the motor keeps moving. Reversing therefore takes two presses: an opposite
    pulse (stop), settle, then a pulse to move the new direction — the base's
    _raw_direction_command / _direction_change_delay orchestration handles this
    via the polymorphic _send_stop below.

    Stop pulses the OPPOSITE of the last-used direction relay.
    """

    async def _send_stop(self) -> None:
        # Halt by pulsing the relay opposite to the last-used direction; the
        # motor stops on that edge (_pulse_relay marks its own echoes).
        if self._last_command == SERVICE_CLOSE_COVER:
            await self._pulse_relay(self._open_switch_entity_id)
        elif self._last_command == SERVICE_OPEN_COVER:
            await self._pulse_relay(self._close_switch_entity_id)
        else:
            self._log(
                "_send_stop :: opposite toggle with no last command, skipping"
            )

    async def _send_tilt_stop(self) -> None:
        # Pulse the opposite tilt relay to halt a moving tilt motor.
        if self._last_tilt_direction == "close":
            await self._pulse_relay(self._tilt_open_switch_id)
        elif self._last_tilt_direction == "open":
            await self._pulse_relay(self._tilt_close_switch_id)
        else:
            self._log(
                "_send_tilt_stop :: opposite toggle with no last tilt direction,"
                " skipping"
            )
        self._last_tilt_direction = None

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Opposite-button: an opposite-direction press while moving stops.

        A same-direction press while already moving that way is a continuation
        (the hardware keeps moving), so it is a no-op. From idle, a press starts
        the movement in that direction.
        """
        if new_val != "on":
            return
        if self._debounce_external_toggle(entity_id):
            self._log(
                "_handle_external_state_change :: debounced toggle on %s", entity_id
            )
            return

        if entity_id == self._open_switch_entity_id:
            if self.is_closing:
                self._log(
                    "_handle_external_state_change :: open press while closing, stopping"
                )
                await self.async_stop_cover()
            elif not self.is_opening:
                self._log("_handle_external_state_change :: external open press")
                await self.async_open_cover()
            # else already opening -> continuation, no-op
        elif entity_id == self._close_switch_entity_id:
            if self.is_opening:
                self._log(
                    "_handle_external_state_change :: close press while opening, stopping"
                )
                await self.async_stop_cover()
            elif not self.is_closing:
                self._log("_handle_external_state_change :: external close press")
                await self.async_close_cover()
            # else already closing -> continuation, no-op

    async def _handle_external_tilt_state_change(self, entity_id, old_val, new_val):
        """Opposite-button tilt: opposite press while tilting stops; same continues."""
        if new_val != "on":
            return
        if self._debounce_external_toggle(entity_id):
            self._log(
                "_handle_external_tilt_state_change :: debounced toggle on %s",
                entity_id,
            )
            return

        if entity_id == self._tilt_open_switch_id:
            if self.tilt_calc.is_closing():
                self._log(
                    "_handle_external_tilt_state_change :: tilt open press while"
                    " tilt closing, stopping"
                )
                await self.async_stop_cover()
            elif not self.tilt_calc.is_opening():
                self._log(
                    "_handle_external_tilt_state_change :: external tilt open press"
                )
                await self.async_open_cover_tilt()
            # else already tilt-opening -> continuation, no-op
        elif entity_id == self._tilt_close_switch_id:
            if self.tilt_calc.is_opening():
                self._log(
                    "_handle_external_tilt_state_change :: tilt close press while"
                    " tilt opening, stopping"
                )
                await self.async_stop_cover()
            elif not self.tilt_calc.is_closing():
                self._log(
                    "_handle_external_tilt_state_change :: external tilt close press"
                )
                await self.async_close_cover_tilt()
            # else already tilt-closing -> continuation, no-op
