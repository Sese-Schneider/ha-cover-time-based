"""Latching relay (switch) mode cover."""

from .cover_switch import SwitchCoverTimeBased


class SwitchModeCover(SwitchCoverTimeBased):
    """Cover controlled by latching relays (switch mode).

    In switch mode, the direction switch stays ON for the entire duration
    of the movement. _send_stop turns both direction switches OFF.
    """

    def __init__(
        self,
        device_id,
        name,
        travel_moves_with_tilt,
        travel_time_down,
        travel_time_up,
        tilt_time_down,
        tilt_time_up,
        travel_delay_at_end,
        min_movement_time,
        travel_startup_delay,
        tilt_startup_delay,
        open_switch_entity_id,
        close_switch_entity_id,
        stop_switch_entity_id,
        input_mode,
        pulse_time,
        cover_entity_id,
    ):
        super().__init__(
            device_id,
            name,
            travel_moves_with_tilt,
            travel_time_down,
            travel_time_up,
            tilt_time_down,
            tilt_time_up,
            travel_delay_at_end,
            min_movement_time,
            travel_startup_delay,
            tilt_startup_delay,
            open_switch_entity_id,
            close_switch_entity_id,
            stop_switch_entity_id,
            input_mode,
            pulse_time,
            cover_entity_id,
        )

    async def _send_open(self):
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

    async def _send_close(self):
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

    async def _send_stop(self):
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
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._stop_switch_entity_id},
                False,
            )
