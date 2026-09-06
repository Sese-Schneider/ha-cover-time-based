import asyncio
from unittest.mock import patch

import pytest

from custom_components.cover_time_based.cover import CONTROL_MODE_SINGLE_BUTTON
from custom_components.cover_time_based.single_button_cycle import Phase
from tests.helpers import single_button_sleep_patch, stub_switches
from tests.test_cover_single_button_mode import _make_sb_cover


def test_extra_persist_data_carries_phase():
    cover = _make_sb_cover()
    cover._phase = Phase.STOPPED_AFTER_DOWN
    assert cover._extra_persist_data() == {"phase": "stopped_after_down"}


def test_apply_restored_extra_sets_phase():
    cover = _make_sb_cover()
    cover._phase = Phase.AT_CLOSED
    cover._apply_restored_extra({"position": 50, "phase": "moving_up"})
    assert cover._phase is Phase.MOVING_UP


def test_apply_restored_extra_ignores_missing_phase():
    cover = _make_sb_cover()
    cover._phase = Phase.AT_OPEN
    cover._apply_restored_extra({"position": 50})
    assert cover._phase is Phase.AT_OPEN


def test_apply_restored_extra_ignores_invalid_phase():
    # A corrupted store or a renamed/removed Phase value must not raise --
    # it should leave the current/default phase untouched instead of
    # breaking entity restore.
    cover = _make_sb_cover()
    cover._phase = Phase.AT_OPEN
    cover._apply_restored_extra({"position": 50, "phase": "not_a_real_phase"})
    assert cover._phase is Phase.AT_OPEN


@pytest.mark.asyncio
async def test_removal_mid_travel_persists_the_phase_at_the_limit(
    make_cover, _mock_position_store
):
    """The motor runs on to its limit; the restored phase must say so.

    A persisted MOVING_UP would plan a press for the next STOP, restarting a
    motor that is sitting at its limit.
    """
    cover = make_cover(
        control_mode=CONTROL_MODE_SINGLE_BUTTON,
        travel_time_close=5.0,
        travel_time_open=5.0,
    )
    stub_switches(cover)
    cover.travel_calc.set_position(0)
    cover._phase = Phase.AT_CLOSED

    with patch.object(cover, "async_write_ha_state"), single_button_sleep_patch():
        await cover.async_open_cover()
        await asyncio.sleep(0.2)
        assert cover.travel_calc.is_traveling()
        await cover.async_will_remove_from_hass()

    assert _mock_position_store.async_save.await_args is not None, "no final record"
    _, data = _mock_position_store.async_save.await_args.args
    assert data["position"] == 100
    assert data["phase"] == Phase.AT_OPEN.value
