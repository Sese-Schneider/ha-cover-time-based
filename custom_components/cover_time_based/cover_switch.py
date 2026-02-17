"""Abstract base for covers controlled via switch entities."""

import logging

from .cover_base import CoverTimeBased

_LOGGER = logging.getLogger(__name__)


class SwitchCoverTimeBased(CoverTimeBased):
    """Abstract base for covers controlled via switch entities."""

    def __init__(
        self,
        open_switch_entity_id,
        close_switch_entity_id,
        stop_switch_entity_id=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._open_switch_entity_id = open_switch_entity_id
        self._close_switch_entity_id = close_switch_entity_id
        self._stop_switch_entity_id = stop_switch_entity_id

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle external state change in pulse/toggle mode.

        In pulse/toggle mode, a physical press produces ON->OFF.
        We react on the OFF transition (pulse complete).
        """
        if old_val != "on" or new_val != "off":
            return

        if entity_id == self._open_switch_entity_id:
            _LOGGER.debug(
                "_handle_external_state_change :: external open pulse detected"
            )
            await self.async_open_cover()
        elif entity_id == self._close_switch_entity_id:
            _LOGGER.debug(
                "_handle_external_state_change :: external close pulse detected"
            )
            await self.async_close_cover()
        elif entity_id == self._stop_switch_entity_id:
            _LOGGER.debug(
                "_handle_external_state_change :: external stop pulse detected"
            )
            await self.async_stop_cover()
