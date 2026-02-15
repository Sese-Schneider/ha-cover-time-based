"""Cover that wraps an existing cover entity."""

from .cover_base import CoverTimeBased


class WrappedCoverTimeBased(CoverTimeBased):
    """A cover that delegates open/close/stop to an underlying cover entity."""

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
            "cover", "open_cover", {"entity_id": self._cover_entity_id}, False
        )

    async def _send_close(self):
        await self.hass.services.async_call(
            "cover", "close_cover", {"entity_id": self._cover_entity_id}, False
        )

    async def _send_stop(self):
        await self.hass.services.async_call(
            "cover", "stop_cover", {"entity_id": self._cover_entity_id}, False
        )
