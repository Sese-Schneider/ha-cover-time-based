"""Cover that wraps an existing cover entity."""

import logging
import time

from homeassistant.components.cover import ATTR_CURRENT_POSITION
from homeassistant.const import STATE_CLOSED, STATE_CLOSING, STATE_OPEN, STATE_OPENING
from homeassistant.helpers.event import async_track_state_change_event

from .cover_base import CoverTimeBased

_LOGGER = logging.getLogger(__name__)

_MOVING_STATES = {STATE_OPENING, STATE_CLOSING}
_STOPPED_STATES = {STATE_OPEN, STATE_CLOSED}

# After we issue a command to the wrapped cover, ignore external state
# changes for this many seconds. Some wrapped covers (e.g. Tuya TS130F on
# ZHA) briefly bounce back to their pre-command state before settling on
# the destination state — within this window we trust our own time-based
# position calculation rather than the wrapped cover's transient state.
# Observed bounces happen <250 ms after the command; 500 ms gives a 2×
# safety margin without interfering with legitimate later state changes.
_BOUNCE_GRACE_PERIOD = 0.5


class WrappedCoverTimeBased(CoverTimeBased):
    """A cover that delegates open/close/stop to an underlying cover entity."""

    def __init__(
        self,
        cover_entity_id,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._cover_entity_id = cover_entity_id
        self._last_self_command_time: float | None = None

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

    def _start_bounce_grace_window(self) -> None:
        self._last_self_command_time = time.monotonic()

    def _in_bounce_grace_window(self) -> bool:
        if self._last_self_command_time is None:
            return False
        return time.monotonic() - self._last_self_command_time < _BOUNCE_GRACE_PERIOD

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle state changes on the wrapped cover entity.

        Mirrors the inner cover's state transitions — start, stop, and
        direction changes. When the wrapped cover settles into a stopped
        state we snap to its reported position; for covers without a
        current_position attribute we fall back to stopping the tracker.
        """
        if self._in_bounce_grace_window():
            self._log(
                "_handle_external_state_change :: ignoring %s -> %s"
                " within bounce grace window",
                old_val,
                new_val,
            )
            return

        if new_val == STATE_OPENING:
            self._log("_handle_external_state_change :: wrapped cover opening")
            await self.async_open_cover()
        elif new_val == STATE_CLOSING:
            self._log("_handle_external_state_change :: wrapped cover closing")
            await self.async_close_cover()
        elif new_val in _STOPPED_STATES:
            target = self._wrapped_reported_position()
            if target is not None:
                await self._snap_to_position(target)
            elif old_val in _MOVING_STATES:
                self._log(
                    "_handle_external_state_change :: wrapped cover stopped,"
                    " no position info"
                )
                await self.async_stop_cover()

    async def _handle_external_attribute_change(self, event):
        """Handle attribute-only updates on the wrapped cover.

        When the wrapped cover is in a stopped state and its
        current_position attribute changes, trust the new position.
        Mid-travel attribute updates (state opening/closing) are ignored
        because their values may be stale or live depending on the device.
        """
        if event.data.get("entity_id") != self._cover_entity_id:
            return
        if self._in_bounce_grace_window():
            return
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state not in _STOPPED_STATES:
            return
        target = self._wrapped_reported_position()
        if target is not None:
            await self._snap_to_position(target)

    async def _snap_to_position(self, target: int) -> None:
        """Snap our tracker to a known position.

        Always goes through set_known_position so that a still-running
        auto-updater is stopped even when our calculated position happens
        to match the target at this instant.
        """
        self._log("_snap_to_position :: snapping to %d", target)
        await self.set_known_position(position=target)
        self._last_command = None

    def _wrapped_reported_position(self) -> int | None:
        """Return the wrapped cover's reported position, or None if unknown.

        Prefers the current_position attribute. Falls back to 0 for
        state=closed (unambiguous); state=open without an attribute is
        ambiguous (could be any position > 0) and returns None.
        """
        state = self.hass.states.get(self._cover_entity_id)
        if state is None:
            return None
        attr_pos = state.attributes.get(ATTR_CURRENT_POSITION)
        if isinstance(attr_pos, (int, float)) and 0 <= attr_pos <= 100:
            return int(attr_pos)
        if state.state == STATE_CLOSED:
            return 0
        return None

    async def _call_cover_service(self, service: str, expected: int = 1) -> None:
        self._mark_switch_pending(self._cover_entity_id, expected)
        self._start_bounce_grace_window()
        await self.hass.services.async_call(
            "cover", service, {"entity_id": self._cover_entity_id}, False
        )

    async def _send_open(self) -> None:
        # If the wrapped cover is currently closing, the open command produces
        # two state transitions (closing→open, then open→opening).
        state = self.hass.states.get(self._cover_entity_id)
        expected = 2 if state and state.state == STATE_CLOSING else 1
        await self._call_cover_service("open_cover", expected)

    async def _send_close(self) -> None:
        # If the wrapped cover is currently opening, the close command produces
        # two state transitions (opening→open, then open→closing).
        state = self.hass.states.get(self._cover_entity_id)
        expected = 2 if state and state.state == STATE_OPENING else 1
        await self._call_cover_service("close_cover", expected)

    async def _send_stop(self) -> None:
        await self._call_cover_service("stop_cover")

    # --- Tilt motor relay commands ---

    def _has_tilt_motor(self) -> bool:
        """Wrapped covers use the cover entity for tilt commands."""
        return self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor

    async def _send_tilt_open(self) -> None:
        await self._call_cover_service("open_cover_tilt")

    async def _send_tilt_close(self) -> None:
        await self._call_cover_service("close_cover_tilt")

    async def _send_tilt_stop(self) -> None:
        await self._call_cover_service("stop_cover_tilt")
