"""Entity-teardown quiescence.

Removal happens on every configuration-card save (the entry reloads). It must
leave nothing behind that can later drive the relays: the endpoint run-on stop
timer (``_delay_task``), the startup-delay arming timer (``_startup_delay_task``),
and — mid-calibration — the driven motor itself. These tests pin that
``async_will_remove_from_hass`` cancels the two ghost timers and stops a
calibration-driven motor, and that removal never sends a call to a relay that
was never set.

The timer and calibration tests are adapted from the audit probe corpus
(``verify_backend.py::test_b10_*`` inverted and
``test_audit_config_calib.py::test_removal_mid_calibration_leaves_relay_latched``).
"""

import asyncio
from unittest.mock import patch

import pytest

from custom_components.cover_time_based.cover import CONTROL_MODE_SINGLE_BUTTON
from tests.helpers import relay_calls


@pytest.mark.asyncio
async def test_removal_cancels_delay_task(make_cover):
    cover = make_cover(
        travel_time_close=0.2, travel_time_open=0.2, endpoint_runon_time=0.4
    )
    cover.travel_calc.set_position(0)
    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()
        await asyncio.sleep(0.3)
        await cover.auto_stop_if_necessary()  # arms endpoint run-on
        assert cover._delay_task is not None and not cover._delay_task.done()
        await cover.async_will_remove_from_hass()
        assert cover._delay_task is None or cover._delay_task.done()


@pytest.mark.asyncio
async def test_removal_cancels_startup_delay_task(make_cover):
    cover = make_cover(
        travel_time_close=5.0, travel_time_open=5.0, travel_startup_delay=0.3
    )
    cover.travel_calc.set_position(0)
    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()
        await cover.async_will_remove_from_hass()
        await asyncio.sleep(0.4)
    assert cover._unsubscribe_auto_updater is None  # ghost never re-armed it


@pytest.mark.asyncio
async def test_removal_mid_calibration_stops_the_motor(make_cover):
    cover = make_cover()  # switch mode
    cover.travel_calc.set_position(100)
    with patch.object(cover, "async_write_ha_state"):
        await cover.start_calibration(attribute="travel_time_close", timeout=60.0)
        cover.hass.services.async_call.reset_mock()
        await cover.async_will_remove_from_hass()
        await asyncio.sleep(0.05)
    offs = [
        c
        for c in cover.hass.services.async_call.call_args_list
        if c.args[1] == "turn_off"
    ]
    assert offs, "removal mid-calibration must de-energize the latched relay"


@pytest.mark.asyncio
async def test_removal_mid_calibration_no_stop_pulse_on_toggle_opposite(make_cover):
    # Momentary hardware that self-stops at its endpoints must NOT be pulsed on
    # removal. On toggle-opposite a "stop" pulses the OPPOSITE direction relay,
    # which on a motor already self-stopped at its limit is a movement command
    # that drives the cover back off the endpoint (#153/#133). Only switch
    # mode's latched relay needs de-energizing (see the test above).
    cover = make_cover(control_mode="toggle_opposite")
    # Closed endpoint: the travel_time_close calibration drove close and the
    # momentary motor self-stopped here.
    cover.travel_calc.set_position(0)
    with patch.object(cover, "async_write_ha_state"):
        await cover.start_calibration(attribute="travel_time_close", timeout=60.0)
        cover.hass.services.async_call.reset_mock()
        await cover.async_will_remove_from_hass()
        await asyncio.sleep(0.05)
    pulses = [
        (c.args[1], c.args[2].get("entity_id"))
        for c in cover.hass.services.async_call.call_args_list
        if c.args[1] == "turn_on"
    ]
    assert ("turn_on", "switch.open") not in pulses, pulses
    assert ("turn_on", "switch.close") not in pulses, pulses


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "open_switch,close_switch", [("", ""), ("switch.open", "")], ids=["none", "partial"]
)
async def test_removal_sends_nothing_to_an_unset_relay(
    make_cover, _mock_position_store, open_switch, close_switch
):
    """A new cover has no relays until its first card save, which reloads it.

    Home Assistant rejects a service call with an empty entity id, and a
    removal that raises leaves the entity half-removed (issue #245).
    """
    cover = make_cover(
        open_switch=open_switch,
        close_switch=close_switch,
        travel_time_close=None,
        travel_time_open=None,
    )
    with patch.object(cover, "async_write_ha_state"):
        await cover.async_will_remove_from_hass()

    targets = [eid for _, eid in relay_calls(cover)]
    assert "" not in targets
    if open_switch:
        assert open_switch in targets
    assert _mock_position_store.async_save.await_args is not None


@pytest.mark.asyncio
async def test_single_button_removal_sends_nothing_without_a_button(
    make_cover, _mock_position_store
):
    """Removal releases the button; a new cover has none set yet."""
    cover = make_cover(
        control_mode=CONTROL_MODE_SINGLE_BUTTON,
        open_switch="",
        close_switch="",
        relay_reports_off=True,
        travel_time_close=None,
        travel_time_open=None,
    )
    with patch.object(cover, "async_write_ha_state"):
        await cover.async_will_remove_from_hass()

    assert relay_calls(cover) == []
    assert _mock_position_store.async_save.await_args is not None
