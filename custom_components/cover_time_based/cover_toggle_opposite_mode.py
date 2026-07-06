"""Opposite-button toggle mode cover."""

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from .cover_toggle_base import ToggleBaseCover


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
            self._log("_send_stop :: opposite toggle with no last command, skipping")

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

        Decisions key off the travel tracker directly (``travel_calc``) rather
        than the cover-level ``is_opening``/``is_closing`` properties, which OR
        in tilt motion: on a dual-motor cover a moving tilt relay must not make a
        travel-relay press read as a stop (the tilt handler mirrors this with
        ``tilt_calc``).

        The base reversal guards and the same-button handler factor this same
        axis check into ``_travel_axis_opening``/``_travel_axis_closing`` (which
        additionally fold in shared-motor tilt and the dual-motor tilt-to-safe
        pre-step). The raw ``travel_calc`` check suffices here because these
        branches route to ``async_open_cover``/``async_close_cover``, whose base
        reversal guard applies those cases downstream.
        """
        if self._ignore_external_toggle_edge(
            entity_id, new_val, "_handle_external_state_change"
        ):
            return

        if entity_id == self._open_switch_entity_id:
            if self.travel_calc.is_closing():
                self._log(
                    "_handle_external_state_change :: open press while closing, stopping"
                )
                await self.async_stop_cover()
            elif not self.travel_calc.is_opening():
                self._log("_handle_external_state_change :: external open press")
                await self.async_open_cover()
            # else already opening -> continuation, no-op
        elif entity_id == self._close_switch_entity_id:
            if self.travel_calc.is_opening():
                self._log(
                    "_handle_external_state_change :: close press while opening, stopping"
                )
                await self.async_stop_cover()
            elif not self.travel_calc.is_closing():
                self._log("_handle_external_state_change :: external close press")
                await self.async_close_cover()
            # else already closing -> continuation, no-op

    async def _handle_external_tilt_state_change(self, entity_id, old_val, new_val):
        """Opposite-button tilt: opposite press while tilting stops; same continues."""
        if self._ignore_external_toggle_edge(
            entity_id, new_val, "_handle_external_tilt_state_change"
        ):
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
