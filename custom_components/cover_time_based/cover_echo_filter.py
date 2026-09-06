"""Switch echo filtering mixin for time-based cover entities."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later

from .const import (
    ECHO_PENDING_WINDOW,
    PULSE_ECHO_MARGIN,
    RELAY_FEEDBACK_PENDING_TIMEOUT,
    RELAY_FEEDBACK_TIMEOUT,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .calibration import CalibrationState
    from .travel_calculator import TravelCalculator


class SwitchEchoMixin:
    """Mixin providing switch echo filtering for CoverTimeBased."""

    if TYPE_CHECKING:
        hass: HomeAssistant
        _relay_intent: dict[str, bool]
        _pending_switch: dict[str, int]
        _pending_switch_timers: dict[str, Any]
        _pending_switch_deadlines: dict[str, float]
        _removed: bool
        _wait_for_relay_feedback: bool
        _feedback_armed_entity: str | None
        _feedback_wait_entity: str | None
        _feedback_wait_future: asyncio.Future | None
        _startup_delay_task: asyncio.Task[Any] | None
        _stop_is_a_tap: bool
        _triggered_externally: bool
        _own_echoes_after_confirming_on: int
        _calibration: CalibrationState | None
        _tilt_open_switch_id: str | None
        _tilt_close_switch_id: str | None
        _tilt_stop_switch_id: str | None
        _self_initiated_movement: bool
        travel_calc: TravelCalculator

        def _log(self, msg: str, *args: Any) -> None: ...
        def _is_stale_reappearance(self, old_val: Any, new_val: Any) -> bool: ...
        def _has_tilt_support(self) -> bool: ...
        @staticmethod
        def _entity_unavailable(state: Any) -> bool: ...
        def async_write_ha_state(self) -> None: ...
        def _neutralize_tracked_movement(self, *, supersede: bool = True) -> None: ...
        async def _handle_external_attribute_change(self, event: Any) -> None: ...
        async def _handle_external_tilt_state_change(
            self, entity_id: Any, old_val: Any, new_val: Any
        ) -> None: ...
        async def _handle_external_state_change(
            self, entity_id: Any, old_val: Any, new_val: Any
        ) -> None: ...

    def _switch_is_on(self, entity_id) -> bool:
        """Check if a switch entity is currently on."""
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == "on"

    def _relay_is_on(self, entity_id) -> bool:
        """Whether a latching relay is ON as far as we can tell.

        HA's state lags a slow-reporting relay by seconds, so between our
        command and its echo HA still shows the old state. A pre-count for
        the echo our next command will produce has to be decided from what
        we last told the relay (``_relay_intent``). Intent exists only while
        an echo is outstanding; without one, HA's state is authoritative.
        """
        intent = self._relay_intent.get(entity_id)
        return self._switch_is_on(entity_id) if intent is None else intent

    def _note_relay_intent(self, entity_id, on: bool) -> None:
        """Record the commanded state only while this relay has an echo pending.

        Intent answers whether the next command will flip the relay while
        HA's state lags our command. A send with no outstanding echo leaves
        HA authoritative, so it records nothing and drops any leftover intent.
        """
        if self._pending_switch.get(entity_id, 0) > 0:
            self._relay_intent[entity_id] = on
        else:
            self._relay_intent.pop(entity_id, None)

    def _switch_is_optimistic(self, entity_id) -> bool:
        """Whether the underlying switch reports optimistic (assumed) state.

        An optimistic switch writes its new state immediately, before the
        device confirms, so its state-change echo proves nothing about the
        relay — a feedback-gated move must fall back to the inline start.
        """
        state = self.hass.states.get(entity_id)
        return bool(state is not None and state.attributes.get("assumed_state"))

    def _arm_relay_feedback(self, entity_id) -> bool:
        """Arm a relay-feedback wait for a relay this move is energizing.

        Records ``entity_id`` as the relay whose ON echo should start tracking,
        and returns True, only when ``wait_for_relay_feedback`` is enabled and
        the relay actually reports its state (not optimistic). Otherwise clears
        the arm and returns False, so the caller falls back to the inline
        command-fire start used everywhere today. Called from the ``_send_*``
        method that flips the relay, and consumed by ``_begin_movement``.
        """
        # A removed entity's drive is refused by _call_service, so nothing may
        # be left armed for an ON echo its listener is gone to hear.
        if self._removed:
            return False
        self._feedback_armed_entity = None
        if not self._wait_for_relay_feedback:
            return False
        if entity_id is None or self._switch_is_optimistic(entity_id):
            return False
        self._feedback_armed_entity = entity_id
        return True

    def _consume_feedback_arm(self):
        """Read and clear the arm the preceding ``_send_*`` left, if any.

        The single hand-off channel from a ``_send_*`` (which knows it energized
        a relay) to the deferral point (``_begin_movement`` or a feedback-timed
        calibration drive), consumed exactly once.
        """
        entity_id = self._feedback_armed_entity
        self._feedback_armed_entity = None
        return entity_id

    def _held_echo_window(self, hold_time) -> float:
        """Pending window for an output held ON for ``hold_time``, then released.

        The release's own OFF echo arrives after the hold, so the window has to
        outlast it; the default window still applies to a short hold.
        """
        return max(ECHO_PENDING_WINDOW, hold_time + PULSE_ECHO_MARGIN)

    def _armed_echo_window(self, base_timeout) -> float:
        """Widen a pending window for an armed relay-feedback wait.

        The awaited confirmation may arrive any time up to the feedback
        timeout, and must still be filtered as our own echo when it does.
        """
        return max(base_timeout, RELAY_FEEDBACK_PENDING_TIMEOUT)

    def _mark_driving_relay_pending(
        self,
        entity_id,
        expected_transitions=1,
        arm=True,
        base_timeout=ECHO_PENDING_WINDOW,
    ):
        """Mark the direction relay a move is energizing OFF->ON as pending.

        Call only when the relay will actually flip (inside a rising-edge
        guard). When ``arm`` and ``wait_for_relay_feedback`` can use this relay
        (enabled and not optimistic), also arm the wait on the relay's ON echo
        and widen the echo's safety window to at least
        ``RELAY_FEEDBACK_PENDING_TIMEOUT`` so a slow confirmation is still
        filtered as our own rather than read as an external press.

        ``expected_transitions`` is how many own echoes this drive emits: 1 for
        a plain turn_on, 2 when the relay is released first (toggle) or when a
        pulse also schedules a deferred OFF completion. ``base_timeout`` is the
        pending window used when not armed — pulse mode passes its pulse
        duration so the deferred completion OFF echo stays filtered even when
        the pulse is longer than the default window.
        """
        if arm and self._arm_relay_feedback(entity_id):
            self._mark_switch_pending(
                entity_id,
                expected_transitions,
                timeout=self._armed_echo_window(base_timeout),
            )
        else:
            self._mark_switch_pending(
                entity_id, expected_transitions, timeout=base_timeout
            )

    def _mark_switch_pending(
        self, entity_id, expected_transitions, timeout=ECHO_PENDING_WINDOW
    ):
        """Mark a switch as having pending echo transitions to ignore.

        ``timeout`` is the safety window (seconds) after which a still-unmatched
        count is cleared. The default matches a promptly-reporting relay; a
        feedback-gated move extends it (RELAY_FEEDBACK_PENDING_TIMEOUT) so the
        awaited echo stays classifiable as our own for the full feedback wait.
        """
        # Removal's stops still reach the motor, but its echo listener is gone:
        # no new echo-expiry timer may outlive that listener.
        if self._removed:
            return
        self._pending_switch[entity_id] = (
            self._pending_switch.get(entity_id, 0) + expected_transitions
        )
        self._log(
            "_mark_switch_pending :: %s pending=%d",
            entity_id,
            self._pending_switch[entity_id],
        )

        # The window never shrinks: a stop's default window arriving while a
        # feedback-gated move's long window is outstanding would otherwise
        # truncate it, and the late echo would dispatch as an external press.
        now = time.monotonic()
        deadline = self._pending_switch_deadlines.get(entity_id)
        if deadline is not None and now + timeout <= deadline:
            # The timer already armed ends this window; re-arming it for the
            # same instant would only churn a closure and a handle.
            return
        self._pending_switch_deadlines[entity_id] = now + timeout

        # Cancel any existing timeout for this switch
        if entity_id in self._pending_switch_timers:
            self._pending_switch_timers[entity_id]()

        # Safety timeout: clear pending after the window elapses
        @callback
        def _clear_pending(_now):
            if entity_id in self._pending_switch:
                self._log("_mark_switch_pending :: timeout clearing %s", entity_id)
            self._clear_pending_switch(entity_id, cancel_timer=False)

        self._pending_switch_timers[entity_id] = async_call_later(
            self.hass, timeout, _clear_pending
        )

    def _clear_pending_switch(self, entity_id, *, cancel_timer=True):
        """Drop every trace of ``entity_id``'s pending-echo bookkeeping.

        Count, deadline and safety timer are one unit: a surviving deadline
        would keep extending a later, unrelated window, and a surviving timer
        would clear a count it no longer owns. ``cancel_timer`` is False when
        the safety timer itself is the caller — it is already firing.
        """
        self._pending_switch.pop(entity_id, None)
        self._pending_switch_deadlines.pop(entity_id, None)
        # No echo outstanding — consumed or timed out — so HA's state is
        # current again and the recorded intent has done its job.
        self._relay_intent.pop(entity_id, None)
        timer = self._pending_switch_timers.pop(entity_id, None)
        if timer is not None and cancel_timer:
            timer()

    def _resolve_relay_feedback(self, entity_id, new_val, new_state) -> bool:
        """Start a parked feedback-gated move when its relay confirms.

        The awaited relay going ON *is* the "motor now energized" signal,
        whichever transition on it is offered here — our own filtered echo or a
        rising edge nothing pre-counted; _async_switch_state_changed decides
        which are. Resolves the waiting future with the echo's ``last_changed``
        timestamp (wall-clock; the wait converts it) so tracking starts from when
        the relay actually switched, not when the listener ran. Returns whether
        the wait was resolved.
        """
        future = self._feedback_wait_future
        if (
            future is None
            or future.done()
            or entity_id != self._feedback_wait_entity
            or new_val != "on"
        ):
            return False
        last_changed = getattr(new_state, "last_changed", None)
        stamp = last_changed.timestamp() if last_changed is not None else None
        self._log(
            "_resolve_relay_feedback :: %s confirmed on (stamp=%s)",
            entity_id,
            stamp,
        )
        future.set_result(stamp)
        return True

    async def _on_own_echo_consumed(self, entity_id: str, new_val: str) -> None:
        """Hook: an event just consumed one of this entity's pending echoes.

        Base is a no-op. Overridden by wrapped covers to drain surplus echoes
        when the commanded moving state arrives. Runs after relay-feedback
        resolution so dropping the surplus cannot prevent tracking from starting.
        """
        return

    async def _wait_for_relay_echo(self, entity_id, timeout, *, since=None):
        """Await ``entity_id``'s ON echo; return a monotonic anchor, or None.

        The echo carries the relay's wall-clock ``last_changed``; the tracker
        runs on the monotonic clock. The stamp is converted by its age,
        bounded to the interval this wait has been open (``since``, a
        monotonic reading, defaults to now): a device clock ahead of ours
        cannot anchor in the future, and a wall-clock step landing between
        the echo and the listener cannot backdate the anchor past the
        command. None on timeout (relay never confirmed) or when the echo
        carried no timestamp, so the caller falls back to a command-fire
        timeline. Uses the running loop's future — the mock hass in unit
        tests has no real ``hass.loop``.
        """
        if since is None:
            since = time.monotonic()
        future = asyncio.get_running_loop().create_future()
        self._feedback_wait_entity = entity_id
        self._feedback_wait_future = future
        try:
            stamp = await asyncio.wait_for(future, timeout)
        except TimeoutError:
            self._log(
                "_wait_for_relay_echo :: %s did not confirm within %ss",
                entity_id,
                timeout,
            )
            return None
        finally:
            # Only the owner clears the slot: a replacement wait may have
            # registered before this cleanup ran.
            if self._feedback_wait_future is future:
                self._feedback_wait_entity = None
                self._feedback_wait_future = None
        if stamp is None:
            return None
        now = time.monotonic()
        age = min(max(time.time() - stamp, 0.0), max(now - since, 0.0))
        return now - age

    async def _await_relay_confirmation(self, entity_id, commanded_at):
        """Wait for ``entity_id``'s ON echo; return the anchor to track from.

        The anchor is a ``time.monotonic()`` reading.

        On timeout the anchor is ``commanded_at``, not the instant the wait gave
        up: the relay may have switched without reporting it, so the motor has
        been running since the command — anchoring on the timeout would drop the
        whole wait out of the travel.
        """
        anchor = await self._wait_for_relay_echo(
            entity_id, RELAY_FEEDBACK_TIMEOUT, since=commanded_at
        )
        if anchor is not None:
            self._log(
                "_await_relay_confirmation :: %s confirmed (anchor=%s)"
                " -> starting tracking",
                entity_id,
                anchor,
            )
            return anchor
        self._log(
            "_await_relay_confirmation :: %s did NOT confirm within timeout"
            " -> command-fire start",
            entity_id,
        )
        return commanded_at

    async def _neutralize_parked_move(self) -> None:
        """Park the tracker of a move whose start may still be deferred.

        On tap hardware the relay confirmation is waited out first, and the
        confirmation runs the parked start: what is neutralised is then a
        tracked move whose position holds the run up to the stop about to be
        sent. Otherwise the start is cancelled unrun. The supersede inside is
        a second epoch bump behind _abandon_active_lifecycle's; nothing
        compares epochs by distance, so it is redundant but benign.
        """
        await self._await_confirmation_before_stop()
        self._neutralize_tracked_movement()

    async def _await_confirmation_before_stop(self) -> None:
        """Wait out a pending relay confirmation before stopping tap hardware.

        A toggle stop is a tap and a single-button stop is another press: sent
        before the relay's ON echo lands it can be swallowed, leaving the motor
        running while tracking is torn down. The confirmation runs the parked
        start first, so the run the motor makes between it and the tap is
        counted rather than lost. A no-op on hardware whose stop de-energises
        (switch, pulse, wrapped) and for an external trigger: that path sends
        no tap, so there is nothing to protect and a wall-switch press must not
        park for the feedback timeout.

        The wait is on the deferred-start TASK, not on the future the echo
        resolves: both wake off that same future, so waiting on the future alone
        would only put this caller in the same wake-up batch as the task that
        owns it, leaving "the start ran first" to callback ordering. Once the
        task is done, tracking has started (confirmation) or been anchored on
        the command (the owner's own timeout fallback).

        Waiting is passive — ``asyncio.wait`` never cancels what it waits on — so
        the owner keeps its slot and its own timeout. The explicit timeout here
        is a backstop, not the normal exit: the owner's timeout started earlier
        with the same length, so it fires first and completes the task; with no
        task (a calibration drive owns its wait inline) the wait falls back to
        the future, and the backstop ends a wait left behind with no owner.
        """
        if not self._stop_is_a_tap or self._triggered_externally:
            return
        future = self._feedback_wait_future
        if future is None or future.done():
            return
        self._log(
            "_await_confirmation_before_stop :: deferring until %s confirms",
            self._feedback_wait_entity,
        )
        task = self._startup_delay_task
        if task is not None and not task.done():
            await asyncio.wait([task], timeout=RELAY_FEEDBACK_TIMEOUT)
            return
        await asyncio.wait([future], timeout=RELAY_FEEDBACK_TIMEOUT)

    def _unmark_switch_pending(self, entity_id, count=1):
        """Drop ``count`` pending echo transitions previously marked.

        Used when a state-change echo we pre-counted will no longer arrive —
        e.g. a scheduled relay ``turn_off`` gets cancelled before it fires, so
        its deferred OFF echo never happens. Clamps at zero and tears down
        through the same helper as the decrement in
        ``_async_switch_state_changed``, so a stale count can never linger and
        swallow a genuine press.
        """
        current = self._pending_switch.get(entity_id, 0)
        if current <= 0:
            return
        remaining = current - count
        if remaining > 0:
            self._pending_switch[entity_id] = remaining
            return
        self._clear_pending_switch(entity_id)

    async def _async_switch_state_changed(self, event):
        """Handle state changes on monitored switch entities."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        # Availability transition: push a state write so `available` updates
        # live in the UI. Done before the None-guard below so entity
        # removal/re-appearance is also reflected. An "unavailable" transition
        # drives no movement (it matches no opening/closing/stopped branch).
        was_unavailable = self._entity_unavailable(old_state)
        now_unavailable = self._entity_unavailable(new_state)
        if was_unavailable != now_unavailable:
            self.async_write_ha_state()

        if new_state is None or old_state is None:
            return

        new_val = new_state.state
        old_val = old_state.state

        pending = self._pending_switch.get(entity_id, 0)
        self._log(
            "_async_switch_state_changed :: %s: %s -> %s (pending=%s)",
            entity_id,
            old_val,
            new_val,
            pending,
        )

        # Attribute-only updates (same state string, only attributes changed)
        # must not consume pending echo counts, but may carry useful info
        # (e.g. a wrapped cover updating its current_position attribute).
        # Dispatch to a subclass hook, then return without touching the echo
        # filter or external-state handler. _triggered_externally is set so
        # downstream helpers (async_stop_cover etc.) don't echo a service
        # call back to the wrapped entity in response to its own update.
        if old_val == new_val:
            self._triggered_externally = True
            try:
                await self._handle_external_attribute_change(event)
            finally:
                self._triggered_externally = False
            return

        # Which ON on the awaited relay is the parked move's confirmation
        # (issue #231) is decided from the pending count, and that count is a
        # bound, not an exact ledger: a toggle relay's hardware self-release OFF
        # is deliberately never pre-counted (see _pulse_relay), so it can spend
        # a later mark. Hence one policy in two halves. A pre-counted ON is the
        # confirmation only when it leaves no more than the drive's own trailing
        # echoes outstanding — a reversal taps the same relay for its stop and
        # its drive, and the stop's ON landing after the drive armed still has
        # the drive's transitions outstanding (#268). And a rising edge nothing
        # pre-counted is the confirmation whose mark was spent by such a late
        # OFF; whoever raised the relay, the motor is driven from here. That
        # half deliberately precedes the calibration and stale-reappearance
        # guards below: a calibration drive's mark can be spent the same way,
        # and ``old_val == "off"`` already excludes a relay coming back online.
        if pending > 0:
            remaining = pending - 1
            if remaining <= 0:
                self._clear_pending_switch(entity_id)
            else:
                self._pending_switch[entity_id] = remaining
            self._log(
                "_async_switch_state_changed :: echo filtered, remaining=%s",
                remaining,
            )
            if remaining <= self._own_echoes_after_confirming_on:
                self._resolve_relay_feedback(entity_id, new_val, new_state)
            await self._on_own_echo_consumed(entity_id, new_val)
            return

        if old_val == "off" and self._resolve_relay_feedback(
            entity_id, new_val, new_state
        ):
            self._log(
                "_async_switch_state_changed :: unmarked ON on the awaited relay"
                " taken as its confirmation"
            )
            return

        # Skip external state handling during calibration — calibration drives
        # the motors directly and must not be interfered with.
        if self._calibration is not None:
            self._log("_async_switch_state_changed :: calibration active, skipping")
            return

        # A relay that does not report its own OFF stays stuck reporting 'on'
        # across a restart/reconnect (it pulsed and physically released but
        # never told HA). The entity (re)appearing — unavailable/unknown -> on —
        # is then that stale retained state resurfacing, NOT a fresh button
        # press; replaying it as one would start a phantom movement (tracked,
        # but with no relay fired since _triggered_externally) and desync the
        # tracker from the physical cover. Modes that know their relay is
        # unreliable this way opt in via _is_stale_reappearance.
        if self._is_stale_reappearance(old_val, new_val):
            self._log(
                "_async_switch_state_changed :: %s came online (%s -> %s),"
                " not treating as a command",
                entity_id,
                old_val,
                new_val,
            )
            return

        # Not our echo: someone else moved this relay, so our recorded intent
        # is stale. Dropped only here — after the calibration and stale-
        # reappearance guards, both of which mean "this is NOT someone moving
        # the relay" and must not let a stale retained ``on`` clobber a
        # correct intent of ours.
        self._relay_intent.pop(entity_id, None)

        # External state change (physical button / remote / HA button).
        # Delegate to mode-specific handlers which start/stop position
        # tracking normally via async_open_cover / async_close_cover etc.
        is_tilt = entity_id in (
            self._tilt_open_switch_id,
            self._tilt_close_switch_id,
            self._tilt_stop_switch_id,
        )
        if is_tilt and not self._has_tilt_support():
            # Tilt switches can be wired before tilt times are calibrated (a
            # supported pre-calibration state — dual_motor chosen, tilt
            # switches configured, tilt times not yet set): _tilt_strategy is
            # None and tilt_calc doesn't exist yet. Every mode's external-tilt
            # handler reads one or the other, so ignore the press here rather
            # than crash in each of them separately.
            self._log(
                "_async_switch_state_changed :: tilt event on %s ignored —"
                " tilt not calibrated yet (no tilt times)",
                entity_id,
            )
            return
        # Not our own echo, not stale: a genuine external transition. Logged
        # with the live position because these are what re-drive tracking mid
        # move (e.g. a flaky relay's spurious off/on), the prime suspect for an
        # out-of-sync jump on a slow mesh (issue #231).
        self._log(
            "_async_switch_state_changed :: EXTERNAL %s %s->%s (pos=%s, "
            "traveling=%s, self_initiated=%s) -> dispatching",
            entity_id,
            old_val,
            new_val,
            self.travel_calc.current_position(),
            self.travel_calc.is_traveling(),
            self._self_initiated_movement,
        )
        self._triggered_externally = True
        try:
            if is_tilt:
                await self._handle_external_tilt_state_change(
                    entity_id, old_val, new_val
                )
            else:
                await self._handle_external_state_change(entity_id, old_val, new_val)
        finally:
            self._triggered_externally = False
