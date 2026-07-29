"""Tilt behaviour of recalibrate_before_position (issue #179).

On dual_motor the tilt motor is independent, with its own limits, so it gets a
tilt recalibration leg of its own. On the shared-motor strategies the tilt
"motor" IS the travel motor: over-driving a tilt leg does not stall against a
limit, it bleeds into cover travel and desyncs the travel tracker. There the
datum is a travel endpoint, so the recalibration leg is a TRAVEL drive.
"""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
)
from homeassistant.exceptions import HomeAssistantError


def _command_spy(cover):
    """Wrap cover._async_handle_command to record the command sequence
    while still calling through to the real implementation, so relay state
    and _last_command bookkeeping behave exactly as in production. Mirrors
    the identically-named helper in test_recalibrate_before_position.py."""
    original = cover._async_handle_command
    calls = []

    async def spy(command, *args):
        calls.append(command)
        return await original(command, *args)

    return calls, spy


def _tilt_send_spy(cover):
    """Wrap cover._send_tilt_stop/_send_tilt_open/_send_tilt_close to record
    the call sequence -- the dual-motor analogue of _command_spy, since a
    dual-motor tilt drive fires these directly rather than going through
    _async_handle_command."""
    calls = []
    originals = {
        name: getattr(cover, name)
        for name in ("_send_tilt_stop", "_send_tilt_open", "_send_tilt_close")
    }

    def make_spy(name):
        async def spy(*args, **kwargs):
            calls.append(name)
            return await originals[name](*args, **kwargs)

        return spy

    patchers = [
        patch.object(cover, name, side_effect=make_spy(name)) for name in originals
    ]
    return calls, patchers


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
    # A travel re-drive (_plan_tilt_for_travel -> _start_tilt_pre_step) is
    # indistinguishable from a tilt-motor leg under every assertion above --
    # both leave travel_calc not traveling. These two are what actually
    # differ: a travel leg arms _pending_travel_target and leaves
    # travel_calc's *believed* position seeded at the modelled opposite
    # endpoint, not the real 50.
    assert cover._pending_travel_target is None
    assert cover.travel_calc.current_position() == 50
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
    """open_cover_tilt / close_cover_tilt already target an endpoint and go
    through _async_move_tilt_to_endpoint directly, never set_tilt_position (so
    never _should_recalibrate). Deliberately uses inline, not dual_motor: on
    dual_motor a tilt target of 100 is exempt by the endpoint carve-out
    anyway, so that fixture can't tell "never reaches _should_recalibrate"
    apart from "reaches it but is carved out". inline has no carve-out --
    every tilt target there recalibrates -- so this only stays green because
    the endpoint services bypass set_tilt_position entirely."""
    cover = make_cover(
        recalibrate_before_position=True,
        tilt_mode="inline",
        tilt_time_open=2,
        tilt_time_close=2,
    )
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(40)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover_tilt()

    assert cover._pending_recalibrated_target is None


# ===================================================================
# Fix round 1 (post-review)
# ===================================================================


@pytest.mark.asyncio
async def test_min_movement_time_does_not_strand_tilt_leg_b(make_cover):
    """IMPORTANT 1: min_movement_time must not silently drop leg B after leg A
    has already moved the cover. Reproduced with inline: leg A drives BOTH
    travel and tilt fully open (its tilt phase runs inline with travel), then
    leg B's pulse back down to 30 computes to 1.4s -- under the 2s floor.
    Dropping it would strand the cover fully open with the user's tilt
    request never applied; min_movement_time exists to skip imperceptible
    nudges, not to swallow the whole point of a two-leg recalibrated move."""
    cover = make_cover(
        recalibrate_before_position=True,
        tilt_mode="inline",
        tilt_time_open=2,
        tilt_time_close=2,
        min_movement_time=2,
    )
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(40)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_tilt_position(30)
        cover.travel_calc.set_position(100)  # leg A arrives (travel)
        cover.tilt_calc.set_position(100)  # leg A arrives (inline tilt phase)
        await cover.auto_stop_if_necessary()

    assert cover._pending_recalibrated_target is None
    assert cover.tilt_calc.is_closing(), (
        "leg B must still run despite being 'too short'"
    )
    assert cover.tilt_calc._travel_to_position == 30
    assert cover.travel_calc.current_position() == 100, (
        "inline's plan_move_tilt does not couple travel, so leg B leaves it"
        " where leg A parked it"
    )


@pytest.mark.asyncio
async def test_external_trigger_never_recalibrates_tilt_direct(make_cover):
    """Mirror of test_external_trigger_never_recalibrates (travel axis) for
    tilt: a physical press must never cause a surprise full-open (or, on a
    dedicated tilt motor, a surprise full-tilt-open) drive."""
    cover = _dual(make_cover)
    cover.tilt_calc.set_position(40)

    with patch.object(cover, "async_write_ha_state"):
        cover._triggered_externally = True
        try:
            await cover.set_tilt_position(30)
        finally:
            cover._triggered_externally = False

    assert cover.tilt_calc.is_closing()
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_external_sequential_close_never_recalibrates(make_cover):
    """IMPORTANT 2, driven through the real production path: cover_base.py's
    sequential external-close redirect (_async_move_to_endpoint ->
    set_tilt_position(articulated), called with _triggered_externally=True)
    must not force a full-open recalibration leg. If the self-initiated-only
    guard in _should_recalibrate ever regressed to only checking the travel
    axis, a user physically pressing close on sequential hardware would
    instead trigger the motor running fully open -- the opposite direction
    from the button they just pressed."""
    cover = make_cover(
        recalibrate_before_position=True,
        tilt_time_close=4.0,
        tilt_time_open=4.0,
        tilt_mode="sequential_close",
    )
    cover.travel_calc.set_position(100)
    cover.tilt_calc.set_position(100)

    cover._triggered_externally = True
    try:
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover()
    finally:
        cover._triggered_externally = False

    assert cover.travel_calc._travel_to_position == 0, "must close, not force open"
    assert cover.tilt_calc._travel_to_position == 0
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_leg_a_failing_travel_prestep_does_not_strand_pending_tilt(make_cover):
    """MINOR 2: mirror of
    test_force_redrive_failing_tilt_prestep_does_not_corrupt_tracker
    (tests/test_force_endpoint_redrive.py) for the tilt side. A boundary-locked
    dual_motor leg A seeds tilt at the opposite endpoint, then -- because
    travel is above max_tilt_allowed_position -- drives a travel pre-step
    BEFORE tilt (_start_travel_pre_step), which sets the continuation fields
    _pending_tilt_target / _pending_tilt_command before firing the travel
    relay. A failure in that relay call must not leave those dangling with no
    continuation left to consume them."""
    cover = _dual(make_cover, max_tilt_allowed_position=40)
    cover.travel_calc.set_position(80)  # above max_tilt_allowed_position
    cover.tilt_calc.set_position(40)

    async def _boom():
        raise HomeAssistantError("travel relay failed")

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_send_close", side_effect=_boom),
        pytest.raises(HomeAssistantError),
    ):
        await cover.set_tilt_position(30)

    assert cover.tilt_calc.current_position() == 40, (
        "tilt tracker must not be left seeded at the opposite endpoint"
    )
    assert cover._pending_tilt_target is None, cover._pending_tilt_target
    assert cover._pending_tilt_command is None, cover._pending_tilt_command


@pytest.mark.asyncio
async def test_sequential_leg_b_full_journey_ends_at_travel_0(make_cover):
    """TEST GAP: design spec T18 -- leg B's sequential plan starts
    TravelTo(0) from the now-trustworthy 100 (leg A's true datum), then tilts
    to the requested target. Drives leg A to completion and the full two-phase
    leg B journey to its final resting state, not just leg A's own targets."""
    cover = make_cover(
        recalibrate_before_position=True,
        tilt_mode="sequential",
        tilt_time_open=2,
        tilt_time_close=2,
    )
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(100)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()),
    ):
        await cover.set_tilt_position(30)
        cover.travel_calc.set_position(100)  # leg A arrives at the true datum
        await cover.auto_stop_if_necessary()

        # Leg B's plan, from the now-trustworthy 100: TravelTo(0) then
        # TiltTo(30) -- travel starts at once, tilt is delayed behind it.
        assert cover.travel_calc.is_closing()
        assert cover.travel_calc._travel_to_position == 0
        assert cover.tilt_calc._travel_to_position == 30

        # Drive the rest of the two-phase journey to completion.
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(30)
        await cover.auto_stop_if_necessary()

    assert cover.travel_calc.current_position() == 0
    assert cover.tilt_calc.current_position() == 30
    assert not cover.travel_calc.is_traveling()
    assert not cover.tilt_calc.is_traveling()
    assert cover._pending_recalibrated_target is None


# ===================================================================
# Fix round 3 — set_tilt_position's recalibration drive must stop and
# settle before reversing (same defect as set_position, fix round 2)
# ===================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("tilt_mode", ["inline", "sequential_close", "sequential_open"])
async def test_travel_leg_reversal_stops_and_settles(make_cover, tilt_mode):
    """Requirement 1/2: cover closing (a plain TRAVEL movement, not a tilt
    one), option on, set_tilt_position(30) -- the axis="travel"
    recalibration leg always drives OPEN, so it reverses the in-flight
    close. Must stop and settle first, exactly like set_position's leg A
    (fix round 2). sequential_open's tilt_command_for inversion is
    irrelevant here since leg A drives via the plain travel command, never
    through tilt_command_for."""
    cover = make_cover(
        control_mode="toggle_opposite",
        recalibrate_before_position=True,
        tilt_mode=tilt_mode,
        tilt_time_open=5,
        tilt_time_close=5,
    )
    cover.travel_calc.set_position(60)
    cover.travel_calc.start_travel(20)
    cover.tilt_calc.set_position(50)
    cover._last_command = SERVICE_CLOSE_COVER
    assert cover.travel_calc.is_closing()

    calls, spy = _command_spy(cover)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", side_effect=spy),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.set_tilt_position(30)

    assert calls[:2] == [SERVICE_STOP_COVER, SERVICE_OPEN_COVER], (
        f"must stop before reversing to open, in that order: {calls}"
    )
    settle.assert_awaited_once()
    assert cover._pending_recalibrated_target == 30


@pytest.mark.asyncio
async def test_sequential_open_shared_motor_same_direction_no_spurious_stop(
    make_cover,
):
    """Requirement 2 ('verify rather than assume'): on sequential_open,
    tilt_command_for inverts the mapping -- tilt_command_for(closing_tilt=True)
    returns OPEN, not CLOSE (SequentialOpenTilt.tilt_command_for). A tilt
    move that is semantically "closing" therefore energises the OPEN relay.
    Leg A always drives OPEN too, so when a tilt-closing move is already in
    flight, leg A's own OPEN drive must NOT be treated as a reversal --
    _last_command already reads OPEN, matching the relay leg A itself wants
    to drive."""
    cover = make_cover(
        control_mode="toggle_opposite",
        recalibrate_before_position=True,
        tilt_mode="sequential_open",
        tilt_time_open=5,
        tilt_time_close=5,
    )
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(80)
    cover.tilt_calc.start_travel(20)  # tilt closing: sends OPEN (inverted)
    cover._last_command = SERVICE_OPEN_COVER
    assert cover.tilt_calc.is_closing()

    calls, spy = _command_spy(cover)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", side_effect=spy),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.set_tilt_position(30)

    assert SERVICE_STOP_COVER not in calls, (
        f"no spurious stop -- OPEN relay is already the one leg A wants: {calls}"
    )
    settle.assert_not_awaited()


@pytest.mark.asyncio
async def test_sequential_open_shared_motor_reversal_stops_and_settles(make_cover):
    """Requirement 2 companion: the other half of the inversion check. A
    tilt-opening move on sequential_open sends CLOSE (tilt_command_for(
    closing_tilt=False) == SERVICE_CLOSE_COVER, inverted). Leg A's OPEN
    drive genuinely opposes the energised CLOSE relay here, so it must stop
    and settle first."""
    cover = make_cover(
        control_mode="toggle_opposite",
        recalibrate_before_position=True,
        tilt_mode="sequential_open",
        tilt_time_open=5,
        tilt_time_close=5,
    )
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(20)
    cover.tilt_calc.start_travel(80)  # tilt opening: sends CLOSE (inverted)
    cover._last_command = SERVICE_CLOSE_COVER
    assert cover.tilt_calc.is_opening()

    calls, spy = _command_spy(cover)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", side_effect=spy),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.set_tilt_position(30)

    assert calls[:2] == [SERVICE_STOP_COVER, SERVICE_OPEN_COVER], (
        f"CLOSE relay energised, leg A wants OPEN -- must stop first: {calls}"
    )
    settle.assert_awaited_once()


@pytest.mark.asyncio
async def test_travel_axis_same_direction_no_spurious_stop(make_cover):
    """Requirement 4 (travel axis): already opening, option on,
    set_tilt_position -- leg A's OPEN drive matches the direction already
    running, so no stop/settle must be inserted."""
    cover = make_cover(
        control_mode="toggle_opposite",
        recalibrate_before_position=True,
        tilt_mode="inline",
        tilt_time_open=5,
        tilt_time_close=5,
    )
    cover.travel_calc.set_position(20)
    cover.travel_calc.start_travel(100)
    cover.tilt_calc.set_position(50)
    cover._last_command = SERVICE_OPEN_COVER
    assert cover.travel_calc.is_opening()

    calls, spy = _command_spy(cover)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", side_effect=spy),
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.set_tilt_position(30)

    assert SERVICE_STOP_COVER not in calls, f"no spurious stop: {calls}"
    settle.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_during_settle_aborts_travel_leg(make_cover):
    """Requirement 5 (travel axis): a stop landing inside the pre-drive
    settle gap must win -- the recalibration drive must not proceed, and
    set_tilt_position must not fall back to a plain move either."""
    cover = make_cover(
        recalibrate_before_position=True,
        tilt_mode="inline",
        tilt_time_open=5,
        tilt_time_close=5,
    )
    cover.travel_calc.set_position(60)
    cover.travel_calc.start_travel(20)
    cover.tilt_calc.set_position(50)
    cover._last_command = SERVICE_CLOSE_COVER

    async def stop_during_settle():
        cover._supersede_movement()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", side_effect=stop_during_settle),
    ):
        await cover.set_tilt_position(30)

    assert not cover.travel_calc.is_traveling(), (
        "no recalibration drive, and no fallback plain move, after a stop mid-settle"
    )
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_dual_motor_leg_a_reversal_stops_and_settles(make_cover):
    """Requirement 3: dual_motor, tilt motor moving in the opposite
    direction, option on -- the tilt recalibration leg (axis="tilt") must
    stop and settle first.

    The gap is real here too, though the mechanism differs from the travel
    axis: _force_full_tilt_redrive seeds tilt_calc to the opposite endpoint
    BEFORE _async_move_tilt_to_endpoint ever runs. That seed sets
    tilt_calc's target equal to its own position, so tilt_calc.is_traveling()
    reads False by the time _async_move_tilt_to_endpoint's own in-motion-
    reversal check runs -- defeating it, even though it exists. This must be
    evaluated from the tracker's TRUE state, before the seed."""
    cover = _dual(make_cover)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(60)
    cover.tilt_calc.start_travel(20)  # tilt closing
    cover._last_command = SERVICE_CLOSE_COVER
    cover._moving_tilt_motor = True
    assert cover.tilt_calc.is_closing()

    calls, patchers = _tilt_send_spy(cover)

    with (
        patch.object(cover, "async_write_ha_state"),
        patchers[0],
        patchers[1],
        patchers[2],
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.set_tilt_position(30)

    assert calls == ["_send_tilt_stop", "_send_tilt_open"], (
        f"must stop the tilt motor then reverse it open, in order: {calls}"
    )
    settle.assert_awaited_once()
    assert cover._pending_recalibrated_target == 30
    assert cover._pending_recalibrated_axis == "tilt"


@pytest.mark.asyncio
async def test_dual_motor_same_direction_no_spurious_stop(make_cover):
    """Requirement 4 (tilt axis): the tilt motor is already opening, option
    on -- leg A's own open drive matches, so no stop/settle must be
    inserted."""
    cover = _dual(make_cover)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(20)
    cover.tilt_calc.start_travel(100)  # tilt already opening
    cover._last_command = SERVICE_OPEN_COVER
    cover._moving_tilt_motor = True
    assert cover.tilt_calc.is_opening()

    calls, patchers = _tilt_send_spy(cover)

    with (
        patch.object(cover, "async_write_ha_state"),
        patchers[0],
        patchers[1],
        patchers[2],
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.set_tilt_position(30)

    assert "_send_tilt_stop" not in calls, f"no spurious tilt stop: {calls}"
    settle.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_during_settle_aborts_dual_motor_leg(make_cover):
    """Requirement 5 (tilt axis): a stop landing inside the pre-drive settle
    gap must win for the dual-motor recalibration leg too -- no drive, no
    fallback plain move."""
    cover = _dual(make_cover)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(60)
    cover.tilt_calc.start_travel(20)  # tilt closing
    cover._last_command = SERVICE_CLOSE_COVER
    cover._moving_tilt_motor = True

    async def stop_during_settle():
        cover._supersede_movement()

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_direction_change_delay", side_effect=stop_during_settle),
    ):
        await cover.set_tilt_position(30)

    assert not cover.tilt_calc.is_traveling(), (
        "no recalibration drive, and no fallback plain move, after a stop mid-settle"
    )
    assert cover._pending_recalibrated_target is None


@pytest.mark.asyncio
async def test_dual_motor_idle_stale_last_command_no_spurious_stop(make_cover):
    """Final-review fix (item 1): ``is_direction_change`` alone is not enough
    to gate the pre-drive stop in
    ``_stop_and_settle_tilt_before_recalibration_drive`` -- it must also
    require something to actually be moving (``was_moving``). A dual_motor
    cover idle on both axes with a stale ``_last_command`` (e.g. left over
    from an earlier move) reads as a direction change against nothing
    moving; without the ``was_moving`` conjunct this pulses
    ``_async_handle_command(STOP)`` plus a ``_send_tilt_stop()`` -- exactly
    the hazard ``async_stop_cover`` was written to avoid."""
    cover = _dual(make_cover)
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(60)
    cover._last_command = SERVICE_CLOSE_COVER  # stale: nothing is moving
    assert not cover.tilt_calc.is_traveling()
    assert not cover.travel_calc.is_traveling()

    tilt_calls, patchers = _tilt_send_spy(cover)
    cmd_calls, cmd_spy = _command_spy(cover)

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", side_effect=cmd_spy),
        patchers[0],
        patchers[1],
        patchers[2],
        patch.object(cover, "_direction_change_delay", new=AsyncMock()) as settle,
    ):
        await cover.set_tilt_position(30)

    assert cmd_calls == [], f"no spurious stop at an idle motor: {cmd_calls}"
    assert "_send_tilt_stop" not in tilt_calls, f"no spurious tilt stop: {tilt_calls}"
    settle.assert_not_awaited()
    assert cover._pending_recalibrated_target == 30, "leg A must still proceed normally"


@pytest.mark.asyncio
async def test_should_recalibrate_tilt_axis_tolerates_no_tilt_strategy(make_cover):
    """Final-review fix (item 3): ``_should_recalibrate(axis="tilt")`` must
    not return True when ``_tilt_strategy`` is None. It's unreachable via HA
    (the required_features gate keeps set_tilt_position from running without
    tilt configured), but the rest of this function -- and the rest of
    set_tilt_position -- explicitly tolerates ``_tilt_strategy is None``.
    Left unguarded, the caller's ``self._tilt_strategy.uses_tilt_motor``
    dereference right after this call would raise AttributeError, which
    ``_maybe_start_recalibrated_leg``'s ``except HomeAssistantError`` would
    not catch. Constructed directly since the state isn't reachable through
    the public API."""
    cover = make_cover(recalibrate_before_position=True)
    assert cover._tilt_strategy is None

    assert cover._should_recalibrate(True, 50, axis="tilt") is False
