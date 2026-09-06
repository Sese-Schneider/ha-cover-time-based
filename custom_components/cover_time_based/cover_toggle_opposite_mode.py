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

    def _motor_opening(self) -> bool:
        """Whether the travel MOTOR is physically running in the open direction.

        Opposite-button presses are judged on motor motion alone: a press
        against a running motor halts it, while a press with the motor
        stationary starts it and must be tracked as a move. Shared-motor tilt
        (inline/sequential) drives the travel motor off ``tilt_calc``, which
        ``_travel_axis_opening`` folds in. On dual-motor that helper also
        reports a *pending* travel direction while the tilt-to-safe pre-step
        runs — right for the base reversal guard, which is deciding what a new
        command must supersede, but wrong here: the travel motor is idle
        during the pre-step, so a press that starts it would be mistracked as
        a stop.
        """
        if self._has_tilt_motor():
            return self.travel_calc.is_opening()
        return self._travel_axis_opening()

    def _motor_closing(self) -> bool:
        """Travel-motor counterpart of :meth:`_motor_opening`."""
        if self._has_tilt_motor():
            return self.travel_calc.is_closing()
        return self._travel_axis_closing()

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Opposite-button: an opposite-direction press while moving stops.

        A same-direction press while already moving that way is a continuation
        (the hardware keeps moving), so it is a no-op. From idle, a press starts
        the movement in that direction.

        Decisions key off ``_motor_opening``/``_motor_closing`` — whether the
        travel motor is physically running — not the raw ``travel_calc``: on a
        shared-motor tilt strategy the tilt phase runs the travel motor while
        ``travel_calc`` sits idle, and an opposite press there halts that
        motor, so it must read as a stop, not as a new move. The tilt handler
        below keys off ``tilt_calc`` for the same reason.
        """
        if self._ignore_external_toggle_edge(
            entity_id, new_val, "_handle_external_state_change"
        ):
            return

        if entity_id == self._open_switch_entity_id:
            if self._motor_closing():
                self._log(
                    "_handle_external_state_change :: open press while closing, stopping"
                )
                await self.async_stop_cover(supersede=False)
            elif not self._motor_opening():
                self._log("_handle_external_state_change :: external open press")
                await self.async_open_cover()
            # else already opening -> continuation, no-op
        elif entity_id == self._close_switch_entity_id:
            if self._motor_opening():
                self._log(
                    "_handle_external_state_change :: close press while opening, stopping"
                )
                await self.async_stop_cover(supersede=False)
            elif not self._motor_closing():
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
                await self.async_stop_cover(supersede=False, tilt_axis_reported=True)
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
                await self.async_stop_cover(supersede=False, tilt_axis_reported=True)
            elif not self.tilt_calc.is_closing():
                self._log(
                    "_handle_external_tilt_state_change :: external tilt close press"
                )
                await self.async_close_cover_tilt()
            # else already tilt-closing -> continuation, no-op
