"""Latching relay (switch) mode cover."""

import logging

from .cover_switch import SwitchCoverTimeBased

_LOGGER = logging.getLogger(__name__)


class SwitchModeCover(SwitchCoverTimeBased):
    """Cover controlled by latching relays (switch mode).

    In switch mode, the direction switch stays ON for the entire duration
    of the movement. _send_stop turns both direction switches OFF.
    """

    def _self_stops_at_endpoints(self) -> bool:
        """Switch mode latches the direction relay ON for the whole travel.

        Unlike the momentary modes, reaching an endpoint must still de-energize
        that relay, so the endpoint stop (and run-on) are kept rather than
        skipped.
        """
        return False

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle external state change in switch (latching) mode.

        ON = relay is driving the motor → start tracking.
        OFF = relay released → stop tracking.

        Software up/down interlock: when we observe one direction relay turn ON
        externally (e.g. a decoupled wall switch, or the switch wired straight
        to the relays), turn the opposite relay OFF so both directions are never
        energized at once — mirroring the interlock the driver path already does
        in _send_open / _send_close. Switch mode is the only mode that latches a
        direction relay, so it is the only mode that needs this.
        """
        if entity_id == self._open_switch_entity_id:
            if new_val == "on":
                _LOGGER.debug("_handle_external_state_change :: external open detected")
                await self._interlock_off(self._close_switch_entity_id)
                await self.async_open_cover()
            elif new_val == "off":
                _LOGGER.debug(
                    "_handle_external_state_change :: external open switch off, stopping"
                )
                await self.async_stop_cover()
        elif entity_id == self._close_switch_entity_id:
            if new_val == "on":
                _LOGGER.debug(
                    "_handle_external_state_change :: external close detected"
                )
                await self._interlock_off(self._open_switch_entity_id)
                await self.async_close_cover()
            elif new_val == "off":
                _LOGGER.debug(
                    "_handle_external_state_change :: external close switch off, stopping"
                )
                await self.async_stop_cover()

    async def _interlock_off(self, entity_id) -> None:
        """Turn the opposite direction relay OFF (software interlock).

        Only writes when the relay is actually ON — there is nothing to
        interlock otherwise, and the passive observe path should not produce
        needless relay writes. Marks the resulting state-change event as a
        pending echo so _async_switch_state_changed does not misread our own
        turn_off as the user releasing that switch (which would call
        async_stop_cover and cancel the move we just started).
        """
        if self._switch_is_on(entity_id):
            _LOGGER.debug("_interlock_off :: turning off %s", entity_id)
            self._mark_switch_pending(entity_id, 1)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": entity_id},
                False,
            )

    async def _settle_external_endpoint(self) -> None:
        """De-energize the latched relay at the end of an externally-triggered move.

        An external trigger (a wall switch wired straight to the relay) leaves
        the direction relay latched ON; auto-stop's external-skip path tracks
        the move but never turns it off, so it would stay energized at the
        endpoint forever. Turn off whichever relay is still on — the move may
        already have been released externally, and we must not touch the
        opposite relay — reusing the interlock's guarded, echo-marked turn_off.
        Dual-motor tilt relays latch the same way, so settle them too.
        """
        await self._interlock_off(self._open_switch_entity_id)
        await self._interlock_off(self._close_switch_entity_id)
        if self._has_tilt_motor():
            await self._interlock_off(self._tilt_open_switch_id)
            await self._interlock_off(self._tilt_close_switch_id)

    async def _handle_external_tilt_state_change(self, entity_id, old_val, new_val):
        """Handle external tilt state change in switch (latching) mode.

        ON = tilt relay is driving the motor → start tilt tracking.
        OFF = tilt relay released → stop tilt tracking.

        Dual-motor tilt relays latch the same way the travel relays do, so the
        same up/down interlock applies: observing one tilt direction turn ON
        externally turns the opposite tilt relay OFF (mirroring _send_tilt_open
        / _send_tilt_close on the driver path). See _interlock_off.
        """
        if entity_id == self._tilt_open_switch_id:
            if new_val == "on":
                _LOGGER.debug(
                    "_handle_external_tilt_state_change :: external tilt open detected"
                )
                await self._interlock_off(self._tilt_close_switch_id)
                await self.async_open_cover_tilt()
            elif new_val == "off":
                _LOGGER.debug(
                    "_handle_external_tilt_state_change :: external tilt open off, stopping"
                )
                await self.async_stop_cover()
        elif entity_id == self._tilt_close_switch_id:
            if new_val == "on":
                _LOGGER.debug(
                    "_handle_external_tilt_state_change :: external tilt close detected"
                )
                await self._interlock_off(self._tilt_open_switch_id)
                await self.async_close_cover_tilt()
            elif new_val == "off":
                _LOGGER.debug(
                    "_handle_external_tilt_state_change :: external tilt close off, stopping"
                )
                await self.async_stop_cover()
        elif entity_id == self._tilt_stop_switch_id:
            if new_val == "on":
                _LOGGER.debug(
                    "_handle_external_tilt_state_change :: external tilt stop detected"
                )
                await self.async_stop_cover()

    async def _send_open(self) -> None:
        # Mark a pending echo only when the relay call will actually flip state
        # (matching _send_tilt_open). Marking unconditionally orphans the count
        # when the relay is already ON — e.g. a continuation re-driving the
        # user's still-latched relay — and that orphan then swallows the next
        # real event (such as the user switching it off to stop).
        if self._switch_is_on(self._close_switch_entity_id):
            self._mark_switch_pending(self._close_switch_entity_id, 1)
        if not self._switch_is_on(self._open_switch_entity_id):
            self._mark_switch_pending(self._open_switch_entity_id, 1)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._close_switch_entity_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on",
            {"entity_id": self._open_switch_entity_id},
            False,
        )

    async def _send_close(self) -> None:
        # See _send_open: mark only when the relay will actually flip state.
        if self._switch_is_on(self._open_switch_entity_id):
            self._mark_switch_pending(self._open_switch_entity_id, 1)
        if not self._switch_is_on(self._close_switch_entity_id):
            self._mark_switch_pending(self._close_switch_entity_id, 1)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._open_switch_entity_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on",
            {"entity_id": self._close_switch_entity_id},
            False,
        )

    async def _send_stop(self) -> None:
        if self._switch_is_on(self._close_switch_entity_id):
            self._mark_switch_pending(self._close_switch_entity_id, 1)
        if self._switch_is_on(self._open_switch_entity_id):
            self._mark_switch_pending(self._open_switch_entity_id, 1)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._close_switch_entity_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._open_switch_entity_id},
            False,
        )
