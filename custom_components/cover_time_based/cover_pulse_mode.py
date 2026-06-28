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
    """

    def __init__(self, pulse_time, send_endpoint_stop=True, **kwargs):
        super().__init__(**kwargs)
        self._pulse_time = pulse_time
        self._send_endpoint_stop = send_endpoint_stop

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

    async def _send_open(self) -> None:
        if self._switch_is_on(self._close_switch_entity_id):
            self._mark_switch_pending(self._close_switch_entity_id, 1)
        self._mark_switch_pending(self._open_switch_entity_id, 2)
        if self._stop_switch_entity_id is not None:
            if self._switch_is_on(self._stop_switch_entity_id):
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
        # Motor controller latches on ON edge; complete pulse in background
        self.hass.async_create_task(self._complete_pulse(self._open_switch_entity_id))

    async def _send_close(self) -> None:
        if self._switch_is_on(self._open_switch_entity_id):
            self._mark_switch_pending(self._open_switch_entity_id, 1)
        self._mark_switch_pending(self._close_switch_entity_id, 2)
        if self._stop_switch_entity_id is not None:
            if self._switch_is_on(self._stop_switch_entity_id):
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
        # Motor controller latches on ON edge; complete pulse in background
        self.hass.async_create_task(self._complete_pulse(self._close_switch_entity_id))

    async def _send_stop(self) -> None:
        if self._switch_is_on(self._close_switch_entity_id):
            self._mark_switch_pending(self._close_switch_entity_id, 1)
        if self._switch_is_on(self._open_switch_entity_id):
            self._mark_switch_pending(self._open_switch_entity_id, 1)
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
            self._mark_switch_pending(self._stop_switch_entity_id, 2)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._stop_switch_entity_id},
                False,
            )
            # Motor stops on ON edge; complete pulse in background
            self.hass.async_create_task(
                self._complete_pulse(self._stop_switch_entity_id)
            )

    # --- Tilt motor relay commands ---

    async def _send_tilt_open(self) -> None:
        if self._switch_is_on(self._tilt_close_switch_id):
            self._mark_switch_pending(self._tilt_close_switch_id, 1)
        self._mark_switch_pending(self._tilt_open_switch_id, 2)
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
        self.hass.async_create_task(self._complete_pulse(self._tilt_open_switch_id))

    async def _send_tilt_close(self) -> None:
        if self._switch_is_on(self._tilt_open_switch_id):
            self._mark_switch_pending(self._tilt_open_switch_id, 1)
        self._mark_switch_pending(self._tilt_close_switch_id, 2)
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
        self.hass.async_create_task(self._complete_pulse(self._tilt_close_switch_id))

    async def _send_tilt_stop(self) -> None:
        if self._switch_is_on(self._tilt_open_switch_id):
            self._mark_switch_pending(self._tilt_open_switch_id, 1)
        if self._switch_is_on(self._tilt_close_switch_id):
            self._mark_switch_pending(self._tilt_close_switch_id, 1)
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
            self._mark_switch_pending(self._tilt_stop_switch_id, 2)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._tilt_stop_switch_id},
                False,
            )
            self.hass.async_create_task(self._complete_pulse(self._tilt_stop_switch_id))
