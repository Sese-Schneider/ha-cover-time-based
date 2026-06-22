"""Toggle mode cover."""

import logging
import time

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)

from .cover_switch import SwitchCoverTimeBased

_LOGGER = logging.getLogger(__name__)

# Short debounce window (seconds) to suppress contact bounce on external
# momentary switches — a few tens of ms is enough in practice. Must be
# shorter than any realistic human click cadence (≥ 200ms between
# deliberate presses) so legitimate rapid toggles (e.g. "start then stop")
# are not dropped.
_EXTERNAL_TOGGLE_DEBOUNCE = 0.1


class ToggleModeCover(SwitchCoverTimeBased):
    """Cover controlled by toggle-style relays (toggle mode).

    In toggle mode, the motor controller toggles state on each pulse.
    A second pulse on the same direction button stops the motor.
    _send_stop therefore re-presses the last-used direction button.

    The send methods pulse a relay with a single ``turn_on`` and never hold it
    ON: toggle relays are momentary/self-releasing, so the next command is
    naturally a clean rising edge. Position tracking starts from the moment the
    motor begins moving (the ON edge).

    ``relay_reports_off`` (default ``True``) controls how a relay's OFF state is
    treated. When ``True``, the relay is trusted to report its own OFF, so a
    relay still *reporting* ON is driven OFF first to force a clean edge. When
    ``False`` (hardware-managed pulse modules such as the Aqara T2, issue #105),
    the relay self-releases physically but never reports the OFF to HA — the
    entity stays stuck ``on`` — and a ``turn_off`` is itself an activation pulse
    on that hardware. In that case the send methods only ever issue ``turn_on``
    and never a ``turn_off``, so each command is exactly one clean activation.
    """

    def __init__(self, relay_reports_off=True, **kwargs):
        super().__init__(**kwargs)
        self._relay_reports_off = relay_reports_off
        self._last_external_toggle_time = {}
        self._last_tilt_direction = None

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
        """
        is_on = self._switch_is_on(entity_id)
        if self._relay_reports_off and is_on:
            # Relay reports ON and we trust that report: release it first so the
            # following turn_on is a genuine OFF->ON edge. Two state changes
            # (off, then on) → two echoes.
            self._mark_switch_pending(entity_id, 2)
            await self._turn_off_relay(entity_id)
        elif not is_on:
            # Relay reports OFF: the turn_on produces a real OFF->ON edge → one
            # echo.
            self._mark_switch_pending(entity_id, 1)
        # else: relay_reports_off is disabled and the relay still *reports* ON
        # (it never announced its self-release). The turn_on lands on an
        # already-on entity, so HA emits no state change and no echo — marking
        # one would orphan a pending count that could swallow the user's next
        # genuine press until the safety timeout clears it.
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

    async def async_stop_cover(self, **kwargs):
        """Stop the cover, only sending relay command if it was active."""
        was_active = (
            self.is_opening
            or self.is_closing
            or (self._startup_delay_task and not self._startup_delay_task.done())
            or (self._delay_task and not self._delay_task.done())
        )
        tilt_restore_was_active = self._tilt_restore_active
        tilt_pre_step_was_active = self._pending_travel_target is not None
        self._cancel_startup_delay_task()
        self._cancel_delay_task()
        self._handle_stop()
        if self._tilt_strategy is not None:
            self._tilt_strategy.snap_trackers_to_physical(
                self.travel_calc, self.tilt_calc
            )
        if not self._triggered_externally and was_active:
            await self._send_stop()
            if (
                tilt_restore_was_active or tilt_pre_step_was_active
            ) and self._has_tilt_motor():
                await self._send_tilt_stop()
        self.async_write_ha_state()
        self._last_command = None
        self._last_tilt_direction = None

    # --- External state change handlers ---

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
        return not self._relay_reports_off and old_val in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        )

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle external state change in toggle mode.

        Only the rising edge (OFF→ON) is interesting — this is the button
        press. The ON→OFF transition is just the relay releasing and is ignored.

        A debounce prevents double-triggering for momentary switches that
        produce OFF->ON->OFF per click.
        """
        if new_val != "on":
            return

        now = time.monotonic()
        last = self._last_external_toggle_time.get(entity_id, 0)
        if now - last < _EXTERNAL_TOGGLE_DEBOUNCE:
            self._log(
                "_handle_external_state_change :: debounced toggle on %s",
                entity_id,
            )
            return
        self._last_external_toggle_time[entity_id] = now

        if entity_id == self._open_switch_entity_id:
            if self.is_opening:
                # Same direction while opening: toggle-style motor controllers
                # latch OFF on a second same-direction pulse → stop.
                self._log(
                    "_handle_external_state_change ::"
                    " open toggle while opening, stopping"
                )
                await self.async_stop_cover()
            else:
                # Idle or closing (opposite direction): async_open_cover
                # handles the direction-change stop-and-reverse internally.
                self._log(
                    "_handle_external_state_change :: external open toggle detected"
                )
                await self.async_open_cover()
        elif entity_id == self._close_switch_entity_id:
            if self.is_closing:
                self._log(
                    "_handle_external_state_change ::"
                    " close toggle while closing, stopping"
                )
                await self.async_stop_cover()
            else:
                self._log(
                    "_handle_external_state_change :: external close toggle detected"
                )
                await self.async_close_cover()

    async def _handle_external_tilt_state_change(self, entity_id, old_val, new_val):
        """Handle external tilt state change in toggle mode.

        Only reacts on rising edge (OFF→ON). Same debounce as travel handler.
        If tilt is already moving, treat any toggle as stop.
        """
        if new_val != "on":
            return

        now = time.monotonic()
        last = self._last_external_toggle_time.get(entity_id, 0)
        if now - last < _EXTERNAL_TOGGLE_DEBOUNCE:
            self._log(
                "_handle_external_tilt_state_change :: debounced toggle on %s",
                entity_id,
            )
            return
        self._last_external_toggle_time[entity_id] = now

        if entity_id == self._tilt_open_switch_id:
            if self.tilt_calc.is_traveling():
                self._log(
                    "_handle_external_tilt_state_change ::"
                    " tilt open toggle while traveling, stopping"
                )
                await self.async_stop_cover()
            else:
                self._log(
                    "_handle_external_tilt_state_change :: external tilt open toggle detected"
                )
                await self.async_open_cover_tilt()
        elif entity_id == self._tilt_close_switch_id:
            if self.tilt_calc.is_traveling():
                self._log(
                    "_handle_external_tilt_state_change ::"
                    " tilt close toggle while traveling, stopping"
                )
                await self.async_stop_cover()
            else:
                self._log(
                    "_handle_external_tilt_state_change :: external tilt close toggle detected"
                )
                await self.async_close_cover_tilt()

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

    async def _send_stop(self) -> None:
        # Stop re-pulses the last-used direction relay; the motor toggles on
        # the ON edge (_pulse_relay marks its own echoes).
        if self._last_command == SERVICE_CLOSE_COVER:
            await self._pulse_relay(self._close_switch_entity_id)
        elif self._last_command == SERVICE_OPEN_COVER:
            await self._pulse_relay(self._open_switch_entity_id)
        else:
            self._log("_send_stop :: toggle mode with no last command, skipping")

    # --- Tilt motor relay commands ---

    async def _send_tilt_open(self) -> None:
        await self._release_relay(self._tilt_close_switch_id)
        await self._pulse_relay(self._tilt_open_switch_id)
        self._last_tilt_direction = "open"

    async def _send_tilt_close(self) -> None:
        await self._release_relay(self._tilt_open_switch_id)
        await self._pulse_relay(self._tilt_close_switch_id)
        self._last_tilt_direction = "close"

    async def _send_tilt_stop(self) -> None:
        if self._last_tilt_direction == "close":
            await self._pulse_relay(self._tilt_close_switch_id)
        elif self._last_tilt_direction == "open":
            await self._pulse_relay(self._tilt_open_switch_id)
        else:
            self._log(
                "_send_tilt_stop :: toggle mode with no last tilt direction, skipping"
            )
        self._last_tilt_direction = None
