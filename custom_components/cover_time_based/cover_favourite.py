"""Favourite position: recall by service or by a held gesture.

A favourite is a (position, tilt) pair in the cover's own coordinates. It can
be recalled three ways:

- the ``go_to_favourite`` service, which always drives the cover there;
- the open and close inputs both held on (``both_inputs``);
- a trigger entity holding a state (``entity``).

The two gestures either *track* the move (the motor has a favourite of its own
and is already going there, so nothing is sent) or *drive* it (a plain motor,
moved here on the same gesture).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)

from .const import (
    FAVOURITE_ACTION_TRACK,
    FAVOURITE_GESTURE_BOTH_INPUTS,
    FAVOURITE_GESTURE_ENTITY,
    FAVOURITE_GESTURE_ROLLBACK_WINDOW,
)

if TYPE_CHECKING:
    from .cover_host import _CoverHost as _MixinBase
else:
    _MixinBase = object


class FavouriteMixin(_MixinBase):
    """Mixin providing the favourite position for CoverTimeBased."""

    def _init_favourite(
        self,
        *,
        position,
        tilt_position,
        gesture,
        trigger_entity_id,
        trigger_state,
        hold_time,
        action,
    ) -> None:
        self._favourite_position = position
        self._favourite_tilt_position = tilt_position
        self._favourite_gesture = gesture
        self._favourite_trigger_entity_id: str | None = trigger_entity_id or None
        self._favourite_trigger_state = trigger_state
        self._favourite_hold_time = hold_time
        self._favourite_action = action
        # True from both inputs on until both are off again; every transition
        # of the two inputs in between belongs to the gesture, not to a move.
        self._favourite_gesture_active = False
        self._favourite_hold_unsub = None
        # (monotonic time, travel position, tilt position) just before the
        # last lone press was followed, so the first half of a gesture can be
        # undone.
        self._favourite_pre_press: tuple[float, int | None, int | None] | None = None
        # (tilt target, movement epoch) of a tracked favourite whose tilt runs
        # after its travel. Dropped when anything newer claims the movement.
        self._favourite_tracked_tilt: tuple[int, int] | None = None

    # -- configuration ----------------------------------------------------

    def _has_favourite(self) -> bool:
        return (
            self._favourite_position is not None
            or self._favourite_tilt_position is not None
        )

    def _favourite_uses_both_inputs(self) -> bool:
        return (
            self._has_favourite()
            and self._favourite_gesture == FAVOURITE_GESTURE_BOTH_INPUTS
            and bool(getattr(self, "_open_switch_entity_id", None))
            and bool(getattr(self, "_close_switch_entity_id", None))
        )

    def _favourite_uses_trigger_entity(self) -> bool:
        return (
            self._has_favourite()
            and self._favourite_gesture == FAVOURITE_GESTURE_ENTITY
            and self._favourite_trigger_entity_id is not None
            and self._favourite_trigger_state is not None
        )

    # -- lifecycle --------------------------------------------------------

    def _favourite_added_to_hass(self) -> None:
        """Start watching the trigger entity, if the gesture is one."""
        trigger = self._favourite_trigger_entity_id
        if trigger is None or not self._favourite_uses_trigger_entity():
            return
        self._state_listener_unsubs.append(
            async_track_state_change_event(
                self.hass, [trigger], self._favourite_trigger_state_changed
            )
        )

    def _favourite_will_remove(self) -> None:
        self._cancel_favourite_hold()
        self._favourite_gesture_active = False
        self._favourite_tracked_tilt = None

    # -- hold timer -------------------------------------------------------

    def _cancel_favourite_hold(self) -> None:
        if self._favourite_hold_unsub is not None:
            self._favourite_hold_unsub()
            self._favourite_hold_unsub = None

    def _start_favourite_hold(self) -> None:
        self._cancel_favourite_hold()
        self._favourite_hold_unsub = async_call_later(
            self.hass, self._favourite_hold_time, self._favourite_hold_elapsed
        )

    def _favourite_still_held(self) -> bool:
        if self._favourite_uses_both_inputs():
            return self._switch_is_on(
                self._open_switch_entity_id
            ) and self._switch_is_on(self._close_switch_entity_id)
        trigger = self._favourite_trigger_entity_id
        if trigger is not None and self._favourite_uses_trigger_entity():
            state = self.hass.states.get(trigger)
            return state is not None and state.state == self._favourite_trigger_state
        return False

    @callback
    def _favourite_hold_elapsed(self, _now) -> None:
        self._favourite_hold_unsub = None
        if self._removed or not self._favourite_still_held():
            return
        if self._calibration is not None:
            self._log("_favourite_hold_elapsed :: calibration active, skipping")
            return
        self._log(
            "_favourite_hold_elapsed :: gesture held for %ss, %s the favourite",
            self._favourite_hold_time,
            "tracking"
            if self._favourite_action == FAVOURITE_ACTION_TRACK
            else "driving",
        )
        self.hass.async_create_task(
            self._run_favourite_from_gesture(),
            f"{self.entity_id} favourite gesture",
        )

    async def _run_favourite_from_gesture(self) -> None:
        try:
            await self.async_go_to_favourite(
                track=self._favourite_action == FAVOURITE_ACTION_TRACK
            )
        except HomeAssistantError as err:
            # Raised from a timer, the refusal has no caller to reach.
            self._log("_run_favourite_from_gesture :: refused (%s)", err)

    # -- gesture: trigger entity -------------------------------------------

    @callback
    def _favourite_trigger_state_changed(self, event) -> None:
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        new_val = new_state.state if new_state is not None else None
        old_val = old_state.state if old_state is not None else None
        if new_val == old_val:
            return
        if new_val == self._favourite_trigger_state:
            self._log(
                "_favourite_trigger_state_changed :: %s is %s, hold started",
                self._favourite_trigger_entity_id,
                new_val,
            )
            self._start_favourite_hold()
        elif self._favourite_hold_unsub is not None:
            self._log("_favourite_trigger_state_changed :: released early")
            self._cancel_favourite_hold()

    # -- gesture: both inputs ----------------------------------------------

    async def _favourite_intercepts_input(self, entity_id, old_val, new_val) -> bool:
        """Claim a transition of the open/close inputs for the gesture.

        Called for genuine external transitions only (never our own echoes),
        before the mode handler. Returns True when the transition belongs to a
        both-inputs gesture and must not be read as a press.
        """
        if not self._favourite_uses_both_inputs():
            return False
        open_id = self._open_switch_entity_id
        close_id = self._close_switch_entity_id
        if entity_id not in (open_id, close_id):
            return False

        both_on = self._switch_is_on(open_id) and self._switch_is_on(close_id)

        if self._favourite_gesture_active:
            if not both_on and self._favourite_hold_unsub is not None:
                self._log("_favourite_intercepts_input :: released early")
                self._cancel_favourite_hold()
            if not self._switch_is_on(open_id) and not self._switch_is_on(close_id):
                self._favourite_gesture_active = False
            return True

        if not both_on:
            if new_val == "on":
                # A lone press: let the mode follow it, but remember where the
                # cover was in case this is the first half of a gesture.
                self._favourite_pre_press = (
                    time.monotonic(),
                    self.travel_calc.current_position(),
                    self.tilt_calc.current_position()
                    if self._has_tilt_support()
                    else None,
                )
            return False

        self._log("_favourite_intercepts_input :: both inputs on, hold started")
        self._favourite_gesture_active = True
        await self._undo_first_half_of_gesture()
        self._start_favourite_hold()
        return True

    async def _undo_first_half_of_gesture(self) -> None:
        """Stop following the lone press that opened the gesture.

        The dispatcher holds ``_triggered_externally`` here, so nothing below
        reaches a relay.
        """
        pre_press = self._favourite_pre_press
        self._favourite_pre_press = None
        if (
            pre_press is not None
            and time.monotonic() - pre_press[0] <= FAVOURITE_GESTURE_ROLLBACK_WINDOW
        ):
            _, position, tilt = pre_press
            if position is not None:
                await self.set_known_position(position=position)
                if tilt is not None and self._has_tilt_support():
                    await self.set_known_tilt_position(tilt_position=tilt)
                return
        await self.async_stop_cover()

    # -- the move ----------------------------------------------------------

    async def async_go_to_favourite(self, *, track: bool = False) -> None:
        """Move to the favourite position, or just follow the motor there.

        With ``track`` the hardware is already on its way: the trackers run to
        the favourite and no relay or underlying cover is commanded.
        """
        self._require_configured()
        if not self._has_favourite():
            raise HomeAssistantError(
                f"{self.entity_id} has no favourite position configured"
            )
        position = self._favourite_position
        tilt = self._favourite_tilt_position if self._has_tilt_support() else None
        if track and tilt is not None and self._tilt_strategy.uses_tilt_motor:
            # A motor's own favourite is a point on that one motor's run. With
            # a dedicated tilt motor the gesture on the travel inputs moves
            # travel only, and following a tilt nothing drives would desync it.
            self._log("async_go_to_favourite :: tilt motor is separate, travel only")
            tilt = None
            if position is None:
                return
        self._log(
            "async_go_to_favourite :: position=%s tilt=%s track=%s",
            position,
            tilt,
            track,
        )
        self._favourite_tracked_tilt = None
        if track:
            self._triggered_externally = True
        try:
            await self._move_to_favourite(position, tilt, track=track)
        finally:
            if track:
                self._triggered_externally = False

    async def _move_to_favourite(self, position, tilt, *, track: bool) -> None:
        if position is None:
            await self.set_tilt_position(tilt)
            return
        heading_there = await self.set_position(position)
        if tilt is None or not heading_there:
            return
        if not self._travel_under_way():
            await self.set_tilt_position(tilt)
        elif track:
            # The tracked-move branch of auto_stop_if_necessary picks this up
            # once travel arrives; see _continue_tracked_favourite.
            self._favourite_tracked_tilt = (tilt, self._movement_epoch)
        else:
            # Chained by the auto-updater after travel, like the slat close
            # after a close (_close_tilt_after_travel_close).
            self._tilt_restore_target = tilt

    async def _continue_tracked_favourite(self) -> None:
        """Follow the tilt leg of a tracked favourite once its travel arrived.

        Runs on the auto-updater's task, where ``_triggered_externally`` is
        not set, so it is raised here for the duration of the call.
        """
        pending = self._favourite_tracked_tilt
        self._favourite_tracked_tilt = None
        if pending is None:
            return
        tilt, epoch = pending
        if epoch != self._movement_epoch or not self._has_tilt_support():
            return
        self._log("_continue_tracked_favourite :: following tilt to %d", tilt)
        self._triggered_externally = True
        try:
            await self.set_tilt_position(tilt)
        finally:
            self._triggered_externally = False
