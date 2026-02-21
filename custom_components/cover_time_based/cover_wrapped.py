"""Cover that wraps an existing cover entity."""

import logging

from homeassistant.helpers.event import async_track_state_change_event

from .cover_base import CoverTimeBased

_LOGGER = logging.getLogger(__name__)

# Cover states that indicate movement
_OPENING = "opening"
_CLOSING = "closing"
_MOVING_STATES = {_OPENING, _CLOSING}


class WrappedCoverTimeBased(CoverTimeBased):
    """A cover that delegates open/close/stop to an underlying cover entity."""

    def __init__(
        self,
        cover_entity_id,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._cover_entity_id = cover_entity_id

    async def async_added_to_hass(self):
        """Register state listener for the wrapped cover entity."""
        await super().async_added_to_hass()
        if self._cover_entity_id:
            self._state_listener_unsubs.append(
                async_track_state_change_event(
                    self.hass,
                    [self._cover_entity_id],
                    self._async_switch_state_changed,
                )
            )

    def _are_entities_configured(self) -> bool:
        """Return True if the wrapped cover entity is configured."""
        return bool(self._cover_entity_id)

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle state changes on the wrapped cover entity.

        Unlike switch-based covers, a wrapped cover's state transitions
        are explicit — we mirror whatever the inner cover is doing.
        This handles start, stop, AND direction changes (opening→closing).
        """
        if new_val == _OPENING:
            _LOGGER.debug("_handle_external_state_change :: wrapped cover opening")
            await self.async_open_cover()
        elif new_val == _CLOSING:
            _LOGGER.debug("_handle_external_state_change :: wrapped cover closing")
            await self.async_close_cover()
        elif old_val in _MOVING_STATES:
            # Was moving, now stopped
            _LOGGER.debug("_handle_external_state_change :: wrapped cover stopped")
            await self.async_stop_cover()

    async def _send_open(self) -> None:
        self._mark_switch_pending(self._cover_entity_id, 1)
        await self.hass.services.async_call(
            "cover", "open_cover", {"entity_id": self._cover_entity_id}, False
        )

    async def _send_close(self) -> None:
        self._mark_switch_pending(self._cover_entity_id, 1)
        await self.hass.services.async_call(
            "cover", "close_cover", {"entity_id": self._cover_entity_id}, False
        )

    async def _send_stop(self) -> None:
        self._mark_switch_pending(self._cover_entity_id, 1)
        await self.hass.services.async_call(
            "cover", "stop_cover", {"entity_id": self._cover_entity_id}, False
        )
