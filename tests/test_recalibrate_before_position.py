"""Fully open before moving to a position (issue #179).

A cover with no position feedback that an unseen remote can also move drifts:
Home Assistant keeps tracking from its last known position while the real cover
is somewhere else. With recalibrate_before_position on, a set_position command
first drives the cover fully open — a true datum, since the motor stalls at its
limit — and only then moves to the requested position.
"""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER


@pytest.mark.asyncio
async def test_option_exposed_as_state_attribute(make_cover):
    cover = make_cover(recalibrate_before_position=True)
    assert cover.extra_state_attributes["recalibrate_before_position"] is True


@pytest.mark.asyncio
async def test_option_off_moves_directly(make_cover):
    """Regression guard: with the option off nothing changes."""
    cover = make_cover()
    cover.travel_calc.set_position(75)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(25)

    assert cover.travel_calc.is_closing(), "must head straight for the target"
    assert cover.travel_calc._travel_to_position == 25
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_leg_a_drives_full_open_and_arms_leg_b(make_cover):
    """Believed 75, asked for 25: leg A is a full-travel open, leg B is armed."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(25)

    assert cover.travel_calc.is_opening(), "leg A must open, not close"
    assert cover.travel_calc._travel_to_position == 100
    assert cover._last_command == SERVICE_OPEN_COVER
    assert cover._pending_recalibrated_target == 25
    assert cover._pending_recalibrated_axis == "travel"
    assert cover._recalibration_epoch == cover._movement_epoch


@pytest.mark.asyncio
async def test_leg_b_runs_after_leg_a_completes(make_cover):
    """Leg A reaching 100 chains into the requested move from a true 100."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_position(25)
        cover.travel_calc.set_position(100)  # leg A arrives
        await cover.auto_stop_if_necessary()

    assert cover._pending_recalibrated_target is None
    assert cover.travel_calc.is_closing(), "leg B must head down to the target"
    assert cover.travel_calc._travel_to_position == 25
    assert cover._last_command == SERVICE_CLOSE_COVER


@pytest.mark.asyncio
async def test_leg_b_awaits_the_settle_gap(make_cover):
    """auto_stop_if_necessary clears _last_command, so leg B would not read
    itself as a direction change. Without an explicit settle it reverses the
    motor with no rest — the exact hazard DIRECTION_CHANGE_DELAY exists for."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)
    settle = AsyncMock()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=settle),
    ):
        await cover.set_position(25)
        cover.travel_calc.set_position(100)
        await cover.auto_stop_if_necessary()

    settle.assert_awaited_once()


@pytest.mark.asyncio
async def test_target_100_is_a_single_forced_open(make_cover):
    """An endpoint target IS the recalibration — no pointless extra leg."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(40)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(100)

    assert cover.travel_calc.is_opening()
    assert cover.travel_calc._travel_to_position == 100
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_target_0_has_no_open_leg(make_cover):
    """Going fully closed must not drive fully open first."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(40)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(0)

    assert cover.travel_calc.is_closing(), "must close, not open first"
    assert cover.travel_calc._travel_to_position == 0
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_external_trigger_never_recalibrates(make_cover):
    """A physical press must never cause a surprise full-open."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    with patch.object(cover, "async_write_ha_state"):
        cover._triggered_externally = True
        try:
            await cover.set_position(25)
        finally:
            cover._triggered_externally = False

    assert cover.travel_calc.is_closing()
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_leg_b_does_not_arm_a_third_leg(make_cover):
    """Leg B re-enters with recalibrate=False, so the chain terminates."""
    cover = make_cover(recalibrate_before_position=True)
    cover.travel_calc.set_position(75)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_position(25)
        cover.travel_calc.set_position(100)
        await cover.auto_stop_if_necessary()
        cover.travel_calc.set_position(25)  # leg B arrives
        await cover.auto_stop_if_necessary()

    assert cover._pending_recalibrated_target is None
    assert not cover.travel_calc.is_traveling(), "no third leg"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"control_mode": "pulse", "stop_switch": "switch.stop"},
        {"control_mode": "toggle", "close_switch": "switch.open"},
        {"control_mode": "toggle_opposite"},
        {"cover_entity_id": "cover.real"},
    ],
    ids=["switch", "pulse", "toggle", "toggle_opposite", "wrapped"],
)
async def test_recalibration_leg_runs_in_every_mode(make_cover, kwargs):
    cover = make_cover(recalibrate_before_position=True, **kwargs)
    cover.travel_calc.set_position(75)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_position(25)

    assert cover.travel_calc.is_opening()
    assert cover._pending_recalibrated_target == 25
