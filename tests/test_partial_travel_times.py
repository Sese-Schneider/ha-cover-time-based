"""A cover with only one travel time calibrated (issue #245).

Calibration saves each direction's time as it is measured, so between the
two steps the cover runs with the opening time known and the closing time
missing.
"""

import asyncio
from unittest.mock import patch

import pytest

from custom_components.cover_time_based.cover import CONTROL_MODE_SINGLE_BUTTON
from custom_components.cover_time_based.single_button_cycle import Phase
from tests.helpers import single_button_sleep_patch, stub_switches


@pytest.mark.asyncio
async def test_stop_mid_travel_then_removal_saves_the_stopped_position(
    make_cover, _mock_position_store
):
    cover = make_cover(
        control_mode=CONTROL_MODE_SINGLE_BUTTON,
        travel_time_close=None,
        travel_time_open=5.0,
    )
    stub_switches(cover)
    cover.travel_calc.set_position(0)
    cover._phase = Phase.AT_CLOSED

    with patch.object(cover, "async_write_ha_state"), single_button_sleep_patch():
        await cover.async_open_cover()
        await asyncio.sleep(0.2)
        assert cover.travel_calc.is_traveling()
        await cover.async_stop_cover()
        stopped_at = cover.current_cover_position
        await cover.async_will_remove_from_hass()

    assert 0 < stopped_at < 100
    assert _mock_position_store.async_save.await_args is not None, "no final record"
    _, data = _mock_position_store.async_save.await_args.args
    assert data["position"] == stopped_at


@pytest.mark.asyncio
@pytest.mark.parametrize("travel_time_open", [None, 5.0])
async def test_reload_of_an_idle_cover_saves_its_known_position(
    make_cover, _mock_position_store, travel_time_open
):
    """Saving a calibration result reloads the cover; removal must not crash.

    A crash here leaves the old entity half-removed, so HA refuses its
    replacement and the card reports "Entity not found".
    """
    cover = make_cover(
        control_mode=CONTROL_MODE_SINGLE_BUTTON,
        travel_time_close=None,
        travel_time_open=travel_time_open,
    )
    stub_switches(cover)

    with patch.object(cover, "async_write_ha_state"), single_button_sleep_patch():
        await cover.set_known_position(position=0)
        await cover.async_will_remove_from_hass()

    _, data = _mock_position_store.async_save.await_args.args
    assert data["position"] == 0
