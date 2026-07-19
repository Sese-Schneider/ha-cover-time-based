"""Shared base for toggle-style momentary-relay covers.

Toggle-style motor controllers act on a relay's OFF->ON edge and self-release
their momentary relays. Two sibling modes build on this base and differ only in
which button stops a moving cover:

- ToggleModeCover (same button): a second pulse on the *same* direction relay
  stops the motor.
- ToggleOppositeModeCover (opposite button): a pulse on the *opposite* direction
  relay stops the motor.

Everything else — the rising-edge pulse machinery, the relay_reports_off
handling for hardware-managed pulse modules (Aqara T2, issue #105), the
stale-reappearance guard, direction-change orchestration and the shared
open/close/tilt-open/tilt-close relay commands — lives here.
"""

import time

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
)

from .cover_switch import SwitchCoverTimeBased


class ToggleBaseCover(SwitchCoverTimeBased):
    """Shared machinery for toggle-style momentary-relay covers."""

    # Short debounce window (seconds) to suppress contact bounce on external
    # momentary switches. Must be shorter than any realistic human click cadence
    # (>= 200ms) so legitimate rapid toggles ("start then stop") are not dropped.
    _EXTERNAL_TOGGLE_DEBOUNCE = 0.1

    def __init__(self, relay_reports_off=True, **kwargs):
        super().__init__(**kwargs)
        self._relay_reports_off = relay_reports_off
        self._last_external_toggle_time = {}
        self._last_tilt_direction = None

    def _debounce_external_toggle(self, entity_id) -> bool:
        """Return True if this rising edge should be dropped as contact bounce.

        Records the accept time on the entity when it is NOT dropped, so the
        next edge within the debounce window is suppressed. Momentary switches
        produce OFF->ON->OFF per physical click; without this a single click
        could double-trigger.
        """
        now = time.monotonic()
        last = self._last_external_toggle_time.get(entity_id, 0)
        if now - last < self._EXTERNAL_TOGGLE_DEBOUNCE:
            return True
        self._last_external_toggle_time[entity_id] = now
        return False

    def _ignore_external_toggle_edge(self, entity_id, new_val, caller) -> bool:
        """Return True if this external edge is not an actionable press.

        Only the rising edge (OFF->ON) is a button press; the ON->OFF release is
        ignored. Contact bounce (a repeat edge within the debounce window) is
        dropped too, logging the drop under ``caller``. Both toggle modes gate
        their external handlers on this, so the rising-edge + debounce boilerplate
        lives in one place.
        """
        if new_val != "on":
            return True
        if self._debounce_external_toggle(entity_id):
            self._log("%s :: debounced toggle on %s", caller, entity_id)
            return True
        return False

    async def _pulse_relay(self, entity_id):
        """Pulse a relay ON with a guaranteed rising edge.

        A toggle motor controller acts on the relay's OFF→ON edge, so a plain
        ``turn_on`` is enough when the relay is already OFF (the momentary relay
        released itself — see the class docstring); no deferred ``turn_off`` is
        scheduled. Only when the relay still *reports* ON (a non-self-releasing
        relay, or one left ON across a restart) is it driven OFF first, so the
        ``turn_on`` is a genuine edge rather than a no-op on an already-on relay
        (which the motor would miss while the position tracker keeps advancing,
        desyncing the entity from the physical cover).

        With ``relay_reports_off`` disabled the OFF→ON-edge release is skipped
        entirely: the relay never reports its OFF (so a reported ON is stale,
        not the real state) and a ``turn_off`` would fire a spurious activation
        pulse. A lone ``turn_on`` still pulses the motor on such hardware.

        Mark only the echoes this pulse actually emits, so the integration
        ignores its own state changes without over-counting. Marking more echoes
        than are emitted would leave a stale pending count that swallows the
        user's next genuine press until the safety timeout clears it. A service
        call that doesn't change the entity's state (``turn_off`` on an
        already-off relay, ``turn_on`` on an already-on one) fires no event and
        so produces no echo to mark.

        Each branch logs the relay's reported state and whether its ``turn_on``
        can carry a rising edge, so a user-supplied debug log shows which
        pulses could have moved the motor (issue #153).
        """
        is_on = self._switch_is_on(entity_id)
        if self._relay_reports_off and is_on:
            # Relay reports ON and we trust that report: release it first so the
            # following turn_on is a genuine OFF->ON edge. Two state changes
            # (off, then on) → two echoes.
            self._log(
                "_pulse_relay :: %s reports on, releasing first so the"
                " turn_on is a rising edge",
                entity_id,
            )
            self._mark_switch_pending(entity_id, 2)
            await self._turn_off_relay(entity_id)
        elif not is_on:
            # Relay reports OFF: the turn_on produces a real OFF->ON edge → one
            # echo.
            self._log(
                "_pulse_relay :: %s reports off, turn_on is a rising edge",
                entity_id,
            )
            self._mark_switch_pending(entity_id, 1)
        else:
            # relay_reports_off is disabled and the relay still *reports* ON
            # (it never announced its self-release). The turn_on lands on an
            # already-on entity, so HA emits no state change and no echo —
            # marking one would orphan a pending count that could swallow the
            # user's next genuine press until the safety timeout clears it.
            # Log it: if the relay is also *physically* still on (a rapid
            # re-pulse inside its own pulse window), this turn_on carries no
            # edge and the motor never sees the command (issue #153).
            self._log(
                '_pulse_relay :: %s still reports on ("Relay reports its own'
                ' OFF" disabled): no rising edge if the relay is physically'
                " still on",
                entity_id,
            )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on",
            {"entity_id": entity_id},
            False,
        )

    async def _turn_off_relay(self, entity_id):
        """The single, gated path for every toggle-mode ``turn_off``.

        Funnelling all OFF commands through here keeps one invariant enforceable
        in one place: when ``relay_reports_off`` is disabled the relay never
        receives a ``turn_off`` at all, because that hardware treats a
        ``turn_off`` as an activation pulse rather than an idempotent "off"
        (issue #105). A new relay path can't reintroduce the bug by forgetting
        the gate as long as it issues its OFF through this method.

        Echo-marking stays with the caller: how many echoes a command emits
        depends on whether a ``turn_on`` follows the OFF, which only the caller
        knows.
        """
        if not self._relay_reports_off:
            return
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": entity_id},
            False,
        )

    async def _release_relay(self, entity_id):
        """Drive the opposite-direction relay OFF before pulsing a direction.

        Clears a direction relay that may still be latched (or reporting ON
        across a restart) so the two directions are never energised together.

        Delegates the actual OFF to :meth:`_turn_off_relay`, so it is skipped
        entirely when ``relay_reports_off`` is disabled (that hardware
        self-releases physically — the opposite direction is already clear — and
        a ``turn_off`` there is a spurious extra activation). An echo is marked
        only when the relay both reports OFF *and* actually reports ON now, since
        a ``turn_off`` on a relay already reporting OFF produces no state change
        to filter.
        """
        if self._relay_reports_off and self._switch_is_on(entity_id):
            self._mark_switch_pending(entity_id, 1)
        await self._turn_off_relay(entity_id)

    async def async_stop_cover(
        self, *, supersede: bool = True, tilt_axis_reported: bool = False, **kwargs
    ):
        """Stop the cover, only sending relay command if it was active.

        See CoverTimeBased.async_stop_cover for ``supersede`` and
        ``tilt_axis_reported``.
        """
        was_active = (
            self.is_opening
            or self.is_closing
            or (self._startup_delay_task and not self._startup_delay_task.done())
            or (self._delay_task and not self._delay_task.done())
        )
        tilt_restore_was_active = self._tilt_restore_active
        tilt_pre_step_was_active = self._pending_travel_target is not None
        stop_tilt = was_active and self._should_stop_tilt_motor(
            tilt_restore_was_active or tilt_pre_step_was_active,
            tilt_axis_reported=tilt_axis_reported,
        )
        self._cancel_startup_delay_task()
        self._cancel_delay_task()
        self._handle_stop(supersede=supersede)
        if self._tilt_strategy is not None:
            self._tilt_strategy.snap_trackers_to_physical(
                self.travel_calc, self.tilt_calc
            )
        if not self._triggered_externally and was_active:
            await self._send_stop()
        if stop_tilt:
            # See CoverTimeBased.async_stop_cover — endpoint-safe teardown.
            await self._tilt_settle()
        self.async_write_ha_state()
        self._last_command = None
        self._last_tilt_direction = None

    # --- Stale-reappearance guard ---

    def _is_stale_reappearance(self, old_val, new_val) -> bool:
        """A non-self-reporting relay coming back online is not a press.

        When ``relay_reports_off`` is disabled the relay pulses and physically
        releases but never reports its OFF (e.g. an Aqara T2 in hardware-pulse
        mode — see issue #105), so its HA entity stays stuck ``on``. After a
        restart or Zigbee reconnect the entity reappears as
        ``unavailable``/``unknown`` → ``on``: that is the stale retained state
        resurfacing, not a button press. Treating it as one would start a
        phantom movement with no relay fired and desync the tracker. Relays
        that report their OFF (the default) come back ``off``, so there is
        nothing to guard and a genuine ``off`` → ``on`` press is unambiguous.
        """
        return not self._relay_reports_off and self._came_back_online(old_val)

    # --- Raw direction commands (calibration screen) ---

    async def _raw_direction_command(self, command: str) -> None:
        """In toggle mode, opposite-direction = stop, not reverse.

        To change direction: stop first, wait for pulse, then send new direction.
        """
        if command in ("open", "close"):
            opposite = SERVICE_CLOSE_COVER if command == "open" else SERVICE_OPEN_COVER
            if self._last_command == opposite:
                await self._send_stop()
                await self._direction_change_delay()
        elif command in ("tilt_open", "tilt_close"):
            opposite_dir = "close" if command == "tilt_open" else "open"
            if self._last_tilt_direction == opposite_dir:
                await self._send_tilt_stop()
                await self._direction_change_delay()
        await super()._raw_direction_command(command)

    # --- Internal relay commands ---

    async def _send_open(self) -> None:
        await self._release_relay(self._close_switch_entity_id)
        # Motor controller acts on the ON edge (_pulse_relay marks its echoes)
        await self._pulse_relay(self._open_switch_entity_id)

    async def _send_close(self) -> None:
        await self._release_relay(self._open_switch_entity_id)
        # Motor controller acts on the ON edge (_pulse_relay marks its echoes)
        await self._pulse_relay(self._close_switch_entity_id)

    # --- Tilt motor relay commands ---

    async def _send_tilt_open(self) -> None:
        await self._release_relay(self._tilt_close_switch_id)
        await self._pulse_relay(self._tilt_open_switch_id)
        self._last_tilt_direction = "open"

    async def _send_tilt_close(self) -> None:
        await self._release_relay(self._tilt_open_switch_id)
        await self._pulse_relay(self._tilt_close_switch_id)
        self._last_tilt_direction = "close"
