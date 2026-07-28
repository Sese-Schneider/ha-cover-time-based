"""Tilt behaviour of recalibrate_before_position (issue #179).

On dual_motor the tilt motor is independent, with its own limits, so it gets a
tilt recalibration leg of its own. On the shared-motor strategies the tilt
"motor" IS the travel motor: over-driving a tilt leg does not stall against a
limit, it bleeds into cover travel and desyncs the travel tracker. There the
datum is a travel endpoint, so the recalibration leg is a TRAVEL drive.
"""

from unittest.mock import AsyncMock, patch

import pytest


def _dual(make_cover, **over):
    return make_cover(
        recalibrate_before_position=True,
        tilt_mode="dual_motor",
        tilt_time_open=5,
        tilt_time_close=5,
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        tilt_stop_switch="switch.tilt_stop",
        **over,
    )


@pytest.mark.asyncio
async def test_dual_motor_leg_a_drives_the_tilt_motor(make_cover):
    cover = _dual(make_cover)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(40)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(30)

    assert cover.tilt_calc.is_opening(), "leg A must drive tilt open"
    assert cover.tilt_calc._travel_to_position == 100
    assert not cover.travel_calc.is_traveling(), "travel must be untouched"
    assert cover._pending_recalibrated_target == 30
    assert cover._pending_recalibrated_axis == "tilt"


@pytest.mark.asyncio
async def test_dual_motor_leg_b_tilts_to_target(make_cover):
    cover = _dual(make_cover)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(40)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_tilt_position(30)
        cover.tilt_calc.set_position(100)
        await cover.auto_stop_if_necessary()

    assert cover._pending_recalibrated_target is None
    assert cover.tilt_calc.is_closing()
    assert cover.tilt_calc._travel_to_position == 30


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [0, 100])
async def test_dual_motor_tilt_endpoint_is_a_single_drive(make_cover, target):
    """A dedicated tilt motor stalls at its own limit, so a tilt endpoint IS
    the recalibration."""
    cover = _dual(make_cover)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(40)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(target)

    assert cover.tilt_calc._travel_to_position == target
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_inline_tilt_recalibrates_travel_not_tilt(make_cover):
    """The guarantee that stops a tilt over-drive bleeding into cover travel:
    on inline the leg must be a TRAVEL drive to 100, never a tilt drive."""
    cover = make_cover(
        recalibrate_before_position=True,
        tilt_mode="inline",
        tilt_time_open=2,
        tilt_time_close=2,
    )
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(40)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(30)

    assert cover.travel_calc.is_opening(), "leg A must be a travel drive"
    assert cover.travel_calc._travel_to_position == 100
    assert cover._pending_recalibrated_target == 30
    assert cover._pending_recalibrated_axis == "tilt"


@pytest.mark.asyncio
async def test_sequential_tilt_recalibrates_travel(make_cover):
    cover = make_cover(
        recalibrate_before_position=True,
        tilt_mode="sequential",
        tilt_time_open=2,
        tilt_time_close=2,
    )
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(100)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(30)

    assert cover.travel_calc.is_opening()
    assert cover.travel_calc._travel_to_position == 100
    assert cover._pending_recalibrated_target == 30


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [0, 100])
async def test_shared_motor_tilt_endpoints_still_recalibrate(make_cover, target):
    """No endpoint carve-out on shared-motor tilt: a tilt endpoint there is
    reached by running the travel motor for a tilt time, with nothing to stall
    against, so it is not a datum."""
    cover = make_cover(
        recalibrate_before_position=True,
        tilt_mode="inline",
        tilt_time_open=2,
        tilt_time_close=2,
    )
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(40)

    with patch.object(cover, "async_write_ha_state"):
        await cover.set_tilt_position(target)

    assert cover.travel_calc.is_opening(), "still needs the travel leg"
    assert cover._pending_recalibrated_target == target


@pytest.mark.asyncio
async def test_tilt_endpoint_services_are_unaffected(make_cover):
    """open_cover_tilt / close_cover_tilt already target an endpoint."""
    cover = _dual(make_cover)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(40)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover_tilt()

    assert cover._pending_recalibrated_target is None
