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

    def _are_entities_configured(self) -> bool:
        """Return True if open and close switch entities are configured."""
        return bool(self._open_switch_entity_id and self._close_switch_entity_id)

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle external state change in pulse mode.

        In pulse mode, the ON signal is the button press (rising edge).
        The OFF transition is just the button release and is ignored.

        Toggle mode overrides this with its own edge detection.
        """
        if new_val != "on":
            return

        if entity_id == self._open_switch_entity_id:
            self._log("_handle_external_state_change :: external open pulse detected")
            await self.async_open_cover()
        elif entity_id == self._close_switch_entity_id:
            self._log("_handle_external_state_change :: external close pulse detected")
            await self.async_close_cover()
        elif entity_id == self._stop_switch_entity_id:
            self._log("_handle_external_state_change :: external stop pulse detected")
            await self.async_stop_cover()
