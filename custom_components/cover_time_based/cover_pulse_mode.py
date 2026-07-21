"""Momentary pulse mode cover."""

import asyncio
from asyncio import sleep

from .cover_switch import SwitchCoverTimeBased


class PulseModeCover(SwitchCoverTimeBased):
    """Cover controlled by momentary pulse relays (pulse mode).

    In pulse mode, the direction switch is turned ON for a short pulse
    (pulse_time seconds) then turned OFF. The motor controller latches
    on the ON edge — the OFF is just relay cleanup.

    The send methods return immediately after the ON edge so that position
    tracking starts from the moment the motor begins moving. The pulse
    completion (sleep + turn_off) runs in the background.

    Echo bookkeeping
    ----------------
    Every relay flip we cause echoes back as a state-change event, and the
    completion's deferred ``turn_off`` is a second, later flip. We pre-count
    those self-inflicted echoes in ``_pending_switch`` so they are filtered out
    rather than read as external presses. The counting must therefore match the
    edges that *actually* occur:

    - a ``turn_on`` on an already-ON relay flips nothing → no echo;
    - a completion that is cancelled (superseded by a stop or a re-press)
      never fires its ``turn_off`` → no deferred OFF echo.

    So completions live in a per-relay registry (:attr:`_pulse_tasks`): a new
    one supersedes the old, cancelling it drops its pre-counted OFF echo, and
    the ON/OFF marks are made conditional on the relay's live state.
    """

    def __init__(self, pulse_time, send_endpoint_stop=True, **kwargs):
        super().__init__(**kwargs)
        self._pulse_time = pulse_time
        self._send_endpoint_stop = send_endpoint_stop
        # entity_id -> the in-flight _complete_pulse task for that relay.
        self._pulse_tasks: dict[str, asyncio.Task] = {}

    def _get_missing_configuration(self) -> list[str]:
        """Return list of missing configuration items."""
        missing = super()._get_missing_configuration()
        if not self._stop_switch_entity_id:
            missing.append("stop switch")
        if self._has_tilt_motor() and not self._tilt_stop_switch_id:
            missing.append("tilt stop switch")
        return missing

    def _self_stops_at_endpoints(self) -> bool:
        """Whether to treat a pulse cover's motor as self-stopping at endpoints.

        Pulse mode serves two opposite momentary controllers, selected by the
        per-cover ``send_endpoint_stop`` option:

        - ``send_endpoint_stop=True`` (default) → return False. The endpoint stop
          IS sent. Pulse mode's stop is a *separate* relay (a stop switch is
          required), so it can never restart the motor. A latching controller
          keeps running until it receives that stop pulse — skipping it leaves
          the controller stuck "moving", blocking the next press and external
          buttons (issue #129). This restores the 4.3.0 / v4.5.3 behaviour:
          endpoint stop pulse, deferred by endpoint_runon_time if configured.

        - ``send_endpoint_stop=False`` → return True. The endpoint stop is
          SKIPPED (the self-stopping path). An auto-stop controller has already
          halted at its limit switch, and a stop pulse received "while stopped"
          is read as go-to-favourite, repositioning the cover (issue #133), so
          the stop must not be sent at all.

        The same flag gates ``_tilt_settle``, so a pulse dual-motor cover's
        (required) tilt-stop relay follows the option at the tilt endpoints too.
        """
        return not self._send_endpoint_stop

    # --- Pulse-completion registry -----------------------------------------

    async def _complete_pulse(self, entity_id):
        """Complete a relay pulse by turning OFF after pulse_time."""
        try:
            await sleep(self._pulse_time)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": entity_id},
                False,
            )
        except asyncio.CancelledError:
            pass
        finally:
            # Only clear the registry if we are still the registered task; a
            # re-pulse may already have replaced us with a newer completion.
            if self._pulse_tasks.get(entity_id) is asyncio.current_task():
                self._pulse_tasks.pop(entity_id, None)

    def _schedule_pulse_completion(self, entity_id) -> None:
        """Schedule the deferred ``turn_off`` for a relay we just pulsed ON.

        Supersedes any in-flight completion for the same relay (its ``turn_off``
        would otherwise land twice / on an already-off relay), then tracks the
        new task so it can be cancelled on stop, re-press or removal.
        """
        self._cancel_pulse_completion(entity_id)
        self._pulse_tasks[entity_id] = self.hass.async_create_task(
            self._complete_pulse(entity_id)
        )

    def _cancel_pulse_completion(self, entity_id) -> bool:
        """Cancel a relay's in-flight completion, if any.

        Returns True when a live completion was cancelled. Its scheduled
        ``turn_off`` will now never fire, so the deferred OFF echo we
        pre-counted for it is dropped here — otherwise it would orphan a
        pending count and swallow the next genuine press.
        """
        task = self._pulse_tasks.pop(entity_id, None)
        if task is not None and not task.done():
            task.cancel()
            self._unmark_switch_pending(entity_id, 1)
            return True
        return False

    async def _cancel_background_pulses(self) -> None:
        """On removal, cancel every in-flight completion and turn its relay off.

        A relay may be mid-pulse — turned ON with its OFF still scheduled in a
        background task. Cancelling the task alone would leave the relay latched
        ON, so fire each pending ``turn_off`` immediately as we cancel.
        """
        pending = list(self._pulse_tasks.items())
        self._pulse_tasks.clear()
        for entity_id, task in pending:
            if not task.done():
                task.cancel()
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": entity_id},
                False,
            )

    # --- Relay pulse helpers -----------------------------------------------

    def _mark_pulse_on(self, entity_id) -> None:
        """Pre-count the echoes for turning a relay ON then pulsing it OFF.

        An OFF relay flips ON now (one echo) and OFF later via its completion
        (a second echo) → mark 2. An already-ON relay (a re-pulse inside the
        window) flips nothing on ``turn_on`` and only its completion's OFF
        echoes → mark 1. ``_schedule_pulse_completion`` (called by the caller
        after ``turn_on``) reconciles the deferred OFF against any superseded
        completion, so exactly one OFF echo is ever counted.
        """
        if self._switch_is_on(entity_id):
            self._mark_switch_pending(entity_id, 1)
        else:
            self._mark_switch_pending(entity_id, 2)

    def _mark_pulse_off(self, entity_id) -> None:
        """Cancel a relay's completion and pre-count our own ``turn_off`` echo.

        Cancelling drops the completion's deferred OFF (it will not fire); our
        immediate ``turn_off`` then produces the one real OFF echo iff the relay
        is currently ON.
        """
        self._cancel_pulse_completion(entity_id)
        if self._switch_is_on(entity_id):
            self._mark_switch_pending(entity_id, 1)

    async def _send_open(self) -> None:
        # Opposite (close) relay: cancel its completion, then account for our
        # turn_off so its echo bookkeeping matches its live state.
        self._mark_pulse_off(self._close_switch_entity_id)
        # Open relay: ON edge now + deferred OFF from the completion.
        self._mark_pulse_on(self._open_switch_entity_id)
        if self._stop_switch_entity_id is not None:
            # A stop pulse may still be in flight (direction command right after
            # a stop): cancel its completion and mark our own turn_off per live
            # state, else its deferred OFF orphans a pending stop echo.
            self._mark_pulse_off(self._stop_switch_entity_id)
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
        # Motor controller latches on ON edge; complete pulse in background
        self._schedule_pulse_completion(self._open_switch_entity_id)

    async def _send_close(self) -> None:
        self._mark_pulse_off(self._open_switch_entity_id)
        self._mark_pulse_on(self._close_switch_entity_id)
        if self._stop_switch_entity_id is not None:
            # A stop pulse may still be in flight (direction command right after
            # a stop): cancel its completion and mark our own turn_off per live
            # state, else its deferred OFF orphans a pending stop echo.
            self._mark_pulse_off(self._stop_switch_entity_id)
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
        # Motor controller latches on ON edge; complete pulse in background
        self._schedule_pulse_completion(self._close_switch_entity_id)

    async def _send_stop(self) -> None:
        # Both direction relays: cancel any in-flight completion (its deferred
        # turn_off must not linger as a phantom echo) and account for our own
        # turn_off against their live state.
        self._mark_pulse_off(self._close_switch_entity_id)
        self._mark_pulse_off(self._open_switch_entity_id)
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
            # The stop relay's own pulse: ON now + deferred OFF (or just the
            # deferred OFF on a double-stop where it is already ON).
            self._mark_pulse_on(self._stop_switch_entity_id)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._stop_switch_entity_id},
                False,
            )
            # Motor stops on ON edge; complete pulse in background
            self._schedule_pulse_completion(self._stop_switch_entity_id)

    # --- Tilt motor relay commands ---

    async def _send_tilt_open(self) -> None:
        self._mark_pulse_off(self._tilt_close_switch_id)
        self._mark_pulse_on(self._tilt_open_switch_id)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_close_switch_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on",
            {"entity_id": self._tilt_open_switch_id},
            False,
        )
        self._schedule_pulse_completion(self._tilt_open_switch_id)

    async def _send_tilt_close(self) -> None:
        self._mark_pulse_off(self._tilt_open_switch_id)
        self._mark_pulse_on(self._tilt_close_switch_id)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_open_switch_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on",
            {"entity_id": self._tilt_close_switch_id},
            False,
        )
        self._schedule_pulse_completion(self._tilt_close_switch_id)

    async def _send_tilt_stop(self) -> None:
        self._mark_pulse_off(self._tilt_open_switch_id)
        self._mark_pulse_off(self._tilt_close_switch_id)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_open_switch_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_close_switch_id},
            False,
        )
        if self._tilt_stop_switch_id:
            self._mark_pulse_on(self._tilt_stop_switch_id)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._tilt_stop_switch_id},
                False,
            )
            self._schedule_pulse_completion(self._tilt_stop_switch_id)
