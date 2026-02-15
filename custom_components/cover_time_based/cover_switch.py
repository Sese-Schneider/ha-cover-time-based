"""Abstract base for covers controlled via switch entities."""

from .cover_base import CoverTimeBased


class SwitchCoverTimeBased(CoverTimeBased):
    """Abstract base for covers controlled via switch entities."""

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
