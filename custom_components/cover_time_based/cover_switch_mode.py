"""Latching relay (switch) mode cover."""

import logging

from .cover_switch import SwitchCoverTimeBased

_LOGGER = logging.getLogger(__name__)


class SwitchModeCover(SwitchCoverTimeBased):
    """Cover controlled by latching relays (switch mode).

    In switch mode, the direction switch stays ON for the entire duration
    of the movement. _send_stop turns both direction switches OFF.
    """

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle external state change in switch (latching) mode."""
        if entity_id == self._open_switch_entity_id:
            if new_val == "on":
                _LOGGER.debug("_handle_external_state_change :: external open detected")
                await self.async_open_cover()
            elif new_val == "off":
                _LOGGER.debug(
                    "_handle_external_state_change :: external open-stop detected"
                )
                await self.async_stop_cover()
        elif entity_id == self._close_switch_entity_id:
            if new_val == "on":
                _LOGGER.debug(
                    "_handle_external_state_change :: external close detected"
                )
                await self.async_close_cover()
            elif new_val == "off":
                _LOGGER.debug(
                    "_handle_external_state_change :: external close-stop detected"
                )
                await self.async_stop_cover()
        elif entity_id == self._stop_switch_entity_id:
            if new_val == "on":
                _LOGGER.debug("_handle_external_state_change :: external stop detected")
                await self.async_stop_cover()

    async def _send_open(self) -> None:
        self._mark_switch_pending(self._close_switch_entity_id, 1)
        self._mark_switch_pending(self._open_switch_entity_id, 1)
        if self._stop_switch_entity_id is not None:
            self._mark_switch_pending(self._stop_switch_entity_id, 1)
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
        if self._stop_switch_entity_id is not None:
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": self._stop_switch_entity_id},
                False,
            )

    async def _send_close(self) -> None:
        self._mark_switch_pending(self._open_switch_entity_id, 1)
        self._mark_switch_pending(self._close_switch_entity_id, 1)
        if self._stop_switch_entity_id is not None:
            self._mark_switch_pending(self._stop_switch_entity_id, 1)
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
        if self._stop_switch_entity_id is not None:
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": self._stop_switch_entity_id},
                False,
            )

    async def _send_stop(self) -> None:
        self._mark_switch_pending(self._close_switch_entity_id, 1)
        self._mark_switch_pending(self._open_switch_entity_id, 1)
        if self._stop_switch_entity_id is not None:
            self._mark_switch_pending(self._stop_switch_entity_id, 1)
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
        if self._stop_switch_entity_id is not None:
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._stop_switch_entity_id},
                False,
            )
