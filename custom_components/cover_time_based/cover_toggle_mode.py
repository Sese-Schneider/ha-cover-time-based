"""Same-button toggle mode cover."""

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
)

from .cover_toggle_base import ToggleBaseCover


class ToggleModeCover(ToggleBaseCover):
    """Cover controlled by toggle relays that stop on the SAME button.

    A second pulse on the direction button that is currently moving stops the
    motor, so _send_stop re-pulses the last-used direction relay.
    """

    async def _send_stop(self) -> None:
        # Stop re-pulses the last-used direction relay; the motor toggles off on
        # the ON edge (_pulse_relay marks its own echoes).
        if self._last_command == SERVICE_CLOSE_COVER:
            await self._pulse_relay(self._close_switch_entity_id)
        elif self._last_command == SERVICE_OPEN_COVER:
            await self._pulse_relay(self._open_switch_entity_id)
        else:
            self._log("_send_stop :: toggle mode with no last command, skipping")

    async def _send_tilt_stop(self) -> None:
        if self._last_tilt_direction == "close":
            await self._pulse_relay(self._tilt_close_switch_id)
        elif self._last_tilt_direction == "open":
            await self._pulse_relay(self._tilt_open_switch_id)
        else:
            self._log(
                "_send_tilt_stop :: toggle mode with no last tilt direction, skipping"
            )
        self._last_tilt_direction = None

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Same-button: a same-direction press while moving stops the motor.

        Decisions key off the travel axis (``_travel_axis_opening`` /
        ``_travel_axis_closing``) rather than the cover-level
        ``is_opening``/``is_closing`` properties, which OR in tilt motion: on a
        dual-motor cover a moving tilt relay must not make a travel-relay press
        read as a stop (the tilt handler keys off ``tilt_calc``). Shared-motor
        tilt is unchanged — its tilt phase is the travel motor running.
        """
        if self._ignore_external_toggle_edge(
            entity_id, new_val, "_handle_external_state_change"
        ):
            return

        if entity_id == self._open_switch_entity_id:
            if self._travel_axis_opening():
                self._log(
                    "_handle_external_state_change :: open toggle while opening, stopping"
                )
                await self.async_stop_cover()
            else:
                self._log(
                    "_handle_external_state_change :: external open toggle detected"
                )
                await self.async_open_cover()
        elif entity_id == self._close_switch_entity_id:
            if self._travel_axis_closing():
                self._log(
                    "_handle_external_state_change :: close toggle while closing, stopping"
                )
                await self.async_stop_cover()
            else:
                self._log(
                    "_handle_external_state_change :: external close toggle detected"
                )
                await self.async_close_cover()

    async def _handle_external_tilt_state_change(self, entity_id, old_val, new_val):
        """Same-button: any tilt toggle while tilt is moving stops the motor."""
        if self._ignore_external_toggle_edge(
            entity_id, new_val, "_handle_external_tilt_state_change"
        ):
            return

        if entity_id == self._tilt_open_switch_id:
            if self.tilt_calc.is_traveling():
                self._log(
                    "_handle_external_tilt_state_change :: tilt open toggle while traveling, stopping"
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
                    "_handle_external_tilt_state_change :: tilt close toggle while traveling, stopping"
                )
                await self.async_stop_cover()
            else:
                self._log(
                    "_handle_external_tilt_state_change :: external tilt close toggle detected"
                )
                await self.async_close_cover_tilt()
