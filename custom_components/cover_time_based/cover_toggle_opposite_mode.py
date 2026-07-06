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
