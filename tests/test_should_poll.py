"""The cover is push-based, so HA must not poll it.

CoverTimeBased writes its own state from the auto-updater and defines no
async_update; if HA kept polling (the CoverEntity default), every poll would
only rewrite the unchanged state.
"""

from custom_components.cover_time_based.cover_switch_mode import SwitchModeCover


def _make_cover() -> SwitchModeCover:
    return SwitchModeCover(
        device_id="test_switch",
        name="Test Switch",
        tilt_strategy=None,
        travel_time_close=30,
        travel_time_open=30,
        tilt_time_close=None,
        tilt_time_open=None,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        endpoint_runon_time=None,
        min_movement_time=None,
        open_switch_entity_id="switch.open",
        close_switch_entity_id="switch.close",
        stop_switch_entity_id=None,
    )


def test_should_not_poll() -> None:
    assert _make_cover().should_poll is False
