"""A cover with only one travel time calibrated (issue #245).

Calibration saves each direction's time as it is measured, so between the
two steps the cover has the opening time and not the closing time. It counts
as not configured until both are set.
"""

from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.cover_time_based.cover import CONTROL_MODE_SINGLE_BUTTON
from custom_components.cover_time_based.single_button_cycle import Phase
from tests.helpers import relay_calls, single_button_sleep_patch, stub_switches


@pytest.mark.asyncio
async def test_open_is_refused_and_presses_nothing(make_cover):
    cover = make_cover(
        control_mode=CONTROL_MODE_SINGLE_BUTTON,
        travel_time_close=None,
        travel_time_open=5.0,
    )
    stub_switches(cover)
    cover.travel_calc.set_position(0)
    cover._phase = Phase.AT_CLOSED

    with (
        patch.object(cover, "async_write_ha_state"),
        single_button_sleep_patch(),
        pytest.raises(HomeAssistantError, match="missing travel times"),
    ):
        await cover.async_open_cover()

    assert relay_calls(cover) == []
    assert cover._phase is Phase.AT_CLOSED


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
