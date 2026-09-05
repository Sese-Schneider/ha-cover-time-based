import asyncio
from itertools import pairwise
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.components.cover import CoverEntityFeature

from custom_components.cover_time_based.cover_single_button_mode import (
    SingleButtonModeCover,
)
from custom_components.cover_time_based.single_button_cycle import Phase


def _make_sb_cover(button="switch.button", pulse_time=1.0, travel=30):
    cover = SingleButtonModeCover(
        device_id="test_sb",
        name="Test SB",
        tilt_strategy=None,
        travel_time_close=travel,
        travel_time_open=travel,
        tilt_time_close=None,
        tilt_time_open=None,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        endpoint_runon_time=None,
        min_movement_time=None,
        open_switch_entity_id=button,
        close_switch_entity_id=None,
        stop_switch_entity_id=None,
        pulse_time=pulse_time,
    )
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    created = []

    def create_task(coro):
        task = asyncio.ensure_future(coro)
        created.append(task)
        return task

    hass.async_create_task = create_task
    cover.hass = hass
    cover._test_tasks = created
    return cover


async def _drain(cover):
    # Drain repeatedly: a settle task and a press-sequence task can both be
    # pending at once, or (after a mid-press interruption) an already-done
    # superseded sequence's task plus its replacement.
    while cover._test_tasks:
        task = cover._test_tasks.pop(0)
        await task


def test_supports_tilt_false():
    assert SingleButtonModeCover.supports_tilt is False


def test_tilt_absent_from_supported_features_even_if_tilt_strategy_present():
    # supports_tilt=False alone must gate the tilt bits out of
    # supported_features. _make_sb_cover() already passes tilt_strategy=None,
    # which would suppress tilt independently of the flag (via
    # _has_tilt_support()'s `_tilt_strategy is not None` check) and so isn't a
    # real test of the flag itself. Force a tilt_strategy + tilt_calc onto
    # the instance -- as if tilt were somehow configured -- to prove
    # supports_tilt=False is still what blocks it.
    cover = _make_sb_cover()
    cover._tilt_strategy = object()
    cover.tilt_calc = object()
    tilt_bits = (
        CoverEntityFeature.OPEN_TILT
        | CoverEntityFeature.CLOSE_TILT
        | CoverEntityFeature.STOP_TILT
        | CoverEntityFeature.SET_TILT_POSITION
    )
    assert cover.supported_features & tilt_bits == 0
    assert cover.supported_features & CoverEntityFeature.SET_POSITION


def test_only_button_required():
    cover = _make_sb_cover()
    assert cover._are_entities_configured() is True
    cover._open_switch_entity_id = None
    assert cover._are_entities_configured() is False


def test_self_stops_at_endpoints():
    assert _make_sb_cover()._self_stops_at_endpoints() is True


def test_initial_phase_is_at_closed():
    assert _make_sb_cover()._phase is Phase.AT_CLOSED


@pytest.mark.asyncio
async def test_external_state_change_ignored():
    cover = _make_sb_cover()
    # Must not raise and must not call any service.
    await cover._handle_external_state_change("switch.button", None, MagicMock())
    cover.hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_single_press_turns_button_on_then_off():
    cover = _make_sb_cover(pulse_time=1.0)
    cover._phase = Phase.AT_CLOSED
    with patch(
        "custom_components.cover_time_based.cover_single_button_mode.sleep",
        new_callable=AsyncMock,
    ):
        await cover._send_open()
        await _drain(cover)
    assert cover.hass.services.async_call.call_args_list == [
        call("homeassistant", "turn_on", {"entity_id": "switch.button"}, False),
        call("homeassistant", "turn_off", {"entity_id": "switch.button"}, False),
    ]


@pytest.mark.asyncio
async def test_multi_press_sequence_is_discrete_on_off_pulses():
    """A multi-press plan (the 3-press nudge) must show the button OFF
    between consecutive presses, not a re-press racing the previous press's
    pending OFF. Asserts the exact ordered on/off pairs."""
    cover = _make_sb_cover(pulse_time=1.0)
    cover._phase = Phase.STOPPED_AFTER_UP  # 3-press nudge
    with patch(
        "custom_components.cover_time_based.cover_single_button_mode.sleep",
        new_callable=AsyncMock,
    ):
        await cover._send_open()
        await _drain(cover)
    assert cover.hass.services.async_call.call_args_list == [
        call("homeassistant", "turn_on", {"entity_id": "switch.button"}, False),
        call("homeassistant", "turn_off", {"entity_id": "switch.button"}, False),
        call("homeassistant", "turn_on", {"entity_id": "switch.button"}, False),
        call("homeassistant", "turn_off", {"entity_id": "switch.button"}, False),
        call("homeassistant", "turn_on", {"entity_id": "switch.button"}, False),
        call("homeassistant", "turn_off", {"entity_id": "switch.button"}, False),
    ]


def _presses(cover):
    """Count turn_on calls on the button (one per press)."""
    return [
        c
        for c in cover.hass.services.async_call.call_args_list
        if c == call("homeassistant", "turn_on", {"entity_id": "switch.button"}, False)
    ]


class TestSendCommands:
    @pytest.mark.asyncio
    async def test_open_from_closed_is_one_press_moving_up(self):
        cover = _make_sb_cover()
        cover._phase = Phase.AT_CLOSED
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_open()
            await _drain(cover)
        assert len(_presses(cover)) == 1
        assert cover._phase is Phase.MOVING_UP

    @pytest.mark.asyncio
    async def test_open_from_stopped_after_up_is_three_press_nudge(self):
        cover = _make_sb_cover()
        cover._phase = Phase.STOPPED_AFTER_UP
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_open()
            await _drain(cover)
        assert len(_presses(cover)) == 3
        assert cover._phase is Phase.MOVING_UP

    @pytest.mark.asyncio
    async def test_open_when_already_moving_up_is_noop(self):
        cover = _make_sb_cover()
        cover._phase = Phase.MOVING_UP
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_open()
            await _drain(cover)
        assert len(_presses(cover)) == 0
        assert cover._phase is Phase.MOVING_UP

    @pytest.mark.asyncio
    async def test_stop_while_moving_up_is_one_press_stopped_after_up(self):
        cover = _make_sb_cover()
        cover._phase = Phase.MOVING_UP
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_stop()
            await _drain(cover)
        assert len(_presses(cover)) == 1
        assert cover._phase is Phase.STOPPED_AFTER_UP

    @pytest.mark.asyncio
    async def test_close_from_open_is_one_press_moving_down(self):
        cover = _make_sb_cover()
        cover._phase = Phase.AT_OPEN
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._send_close()
            await _drain(cover)
        assert len(_presses(cover)) == 1
        assert cover._phase is Phase.MOVING_DOWN

    @pytest.mark.asyncio
    async def test_uses_direction_change_delay_between_presses(self):
        # pulse_time deliberately != DIRECTION_CHANGE_DELAY (1.0) so the
        # inter-press gaps are distinguishable from the pulse-off sleeps.
        cover = _make_sb_cover(pulse_time=0.3)
        cover._phase = Phase.STOPPED_AFTER_UP  # 3-press nudge
        gaps = []
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new=AsyncMock(side_effect=lambda d: gaps.append(d)),
        ):
            await cover._send_open()
            await _drain(cover)
        # Two inter-press gaps of DIRECTION_CHANGE_DELAY (before the 2nd and
        # 3rd presses); three inline pulse-width sleeps of pulse_time (0.3),
        # one per discrete press.
        from custom_components.cover_time_based.const import DIRECTION_CHANGE_DELAY

        assert gaps.count(DIRECTION_CHANGE_DELAY) == 2
        assert gaps.count(0.3) == 3

    @pytest.mark.asyncio
    async def test_raw_open_command_presses_the_button(self):
        cover = _make_sb_cover()
        cover._phase = Phase.AT_CLOSED
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            await cover._raw_direction_command("open")
            await _drain(cover)
        assert len(_presses(cover)) == 1


def _no_adjacent_turn_on(cover):
    """True if the button's on/off calls never show two turn_on calls back
    to back with no turn_off between them (i.e. no merged presses)."""
    on_call = call("homeassistant", "turn_on", {"entity_id": "switch.button"}, False)
    off_call = call("homeassistant", "turn_off", {"entity_id": "switch.button"}, False)
    relevant = [
        c
        for c in cover.hass.services.async_call.call_args_list
        if c in (on_call, off_call)
    ]
    for previous, current in pairwise(relevant):
        if previous == on_call and current == on_call:
            return False
    return True


class TestMidPressInterruption:
    """A second command can land while the first command's press is still
    inside its pulse_time sleep (button ON, turn_off not yet issued). These
    tests deliberately do NOT patch `sleep` with an instant AsyncMock (that
    fully serializes execution and never lets a second command land
    mid-press); instead they use the real asyncio.sleep with tiny durations
    so the press task genuinely suspends and `await asyncio.sleep(0)` can
    park it mid-pulse, exactly as TestRemovalCancelsBackgroundWork does."""

    @pytest.mark.asyncio
    async def test_stop_mid_press_issues_a_real_stop_press(self):
        # AT_CLOSED -> open is a 1-press plan (turn_on issued, then parked
        # inside the pulse-time sleep with the button still ON). A stop
        # landing there must not be silently dropped by planning from the
        # stale pre-press phase (AT_CLOSED, which already satisfies STOP).
        cover = _make_sb_cover(pulse_time=0.01)
        cover._phase = Phase.AT_CLOSED
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode."
            "DIRECTION_CHANGE_DELAY",
            0.01,
        ):
            await cover._send_open()
            await asyncio.sleep(0)  # let the open press reach its pulse sleep
            assert len(_presses(cover)) == 1
            assert cover._press_task is not None
            assert not cover._press_task.done()

            await cover._send_stop()
            await _drain(cover)

        # A real stop press was issued: turn_on/turn_off for the open press,
        # a cleanup turn_off for the interrupted press, then a genuine
        # turn_on/turn_off pair for the stop press -- never two turn_on
        # calls back to back.
        assert cover.hass.services.async_call.call_args_list == [
            call("homeassistant", "turn_on", {"entity_id": "switch.button"}, False),
            call("homeassistant", "turn_off", {"entity_id": "switch.button"}, False),
            call("homeassistant", "turn_on", {"entity_id": "switch.button"}, False),
            call("homeassistant", "turn_off", {"entity_id": "switch.button"}, False),
        ]
        assert cover._phase is Phase.STOPPED_AFTER_UP

    @pytest.mark.asyncio
    async def test_close_mid_press_does_not_merge_with_the_open_nudge(self):
        # STOPPED_AFTER_UP -> open is the 3-press nudge; interrupt while the
        # first press is still mid-pulse (button ON) with a close. The
        # replacement must never turn_on onto an already-ON relay.
        cover = _make_sb_cover(pulse_time=0.01)
        cover._phase = Phase.STOPPED_AFTER_UP
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode."
            "DIRECTION_CHANGE_DELAY",
            0.01,
        ):
            await cover._send_open()
            await asyncio.sleep(0)  # let the first nudge press reach its pulse sleep
            assert len(_presses(cover)) == 1
            assert cover._press_task is not None
            assert not cover._press_task.done()

            await cover._send_close()
            await _drain(cover)

        assert _no_adjacent_turn_on(cover)


class TestMidPulseErrorHandling:
    """A service call (turn_on/turn_off) can raise mid-pulse -- e.g. a relay
    comms failure -- while `_press_active` is True. Left unhandled (the
    original bare `except asyncio.CancelledError: pass` doesn't catch it),
    the task exits with `_press_active` stuck True and the relay possibly
    still latched ON; a later `_supersede_active_press` then sees a
    done/None task and returns early WITHOUT the compensating turn_off, so
    the next command's press merges onto an already-ON relay."""

    @pytest.mark.asyncio
    async def test_mid_pulse_turn_off_error_clears_relay_and_press_active(self):
        cover = _make_sb_cover(pulse_time=0.01)
        cover._phase = Phase.AT_CLOSED  # open is a 1-press plan

        raised = False

        async def flaky_call(domain, service, data, blocking):
            nonlocal raised
            if service == "turn_off" and not raised:
                raised = True
                raise RuntimeError("simulated relay comms failure")

        cover.hass.services.async_call = AsyncMock(side_effect=flaky_call)

        with patch(
            "custom_components.cover_time_based.cover_single_button_mode."
            "DIRECTION_CHANGE_DELAY",
            0.01,
        ):
            await cover._send_open()
            with pytest.raises(RuntimeError):
                await _drain(cover)

            # The unexpected error must not leave the relay latched ON or the
            # in-flight flag stuck -- either would let a later command merge
            # its press onto an already-ON relay.
            assert cover._press_active is False

            # Mock still records a call even when its side_effect raises, so
            # "a turn_off appears in the log" is not on its own proof of a
            # cleanup attempt -- the real differentiator is a SECOND turn_off
            # (the best-effort cleanup) beyond the one that raised.
            off_calls = [
                c
                for c in cover.hass.services.async_call.call_args_list
                if c.args[1] == "turn_off"
            ]
            assert len(off_calls) == 2

            # A subsequent command must not merge: from the settled state
            # (_press_active False, task cleared) _supersede_active_press is
            # a no-op and the new sequence presses cleanly.
            await cover._send_stop()
            await _drain(cover)

        assert cover.hass.services.async_call.call_args_list == [
            call("homeassistant", "turn_on", {"entity_id": "switch.button"}, False),
            call("homeassistant", "turn_off", {"entity_id": "switch.button"}, False),
            call("homeassistant", "turn_off", {"entity_id": "switch.button"}, False),
            call("homeassistant", "turn_on", {"entity_id": "switch.button"}, False),
            call("homeassistant", "turn_off", {"entity_id": "switch.button"}, False),
        ]
        assert cover._phase is Phase.STOPPED_AFTER_UP


class TestSupersedeHardensDoneTaskCase:
    """Defence in depth for `_supersede_active_press`: even when
    `_press_task` is already done/None, if `_press_active` is somehow still
    True the compensating turn_off + gap must still run before a new
    sequence starts. The normal, clean path (nothing in flight,
    `_press_active` already False) must stay penalty-free -- no service
    calls, no sleep."""

    @pytest.mark.asyncio
    async def test_cleans_up_when_task_already_done_but_press_active_stuck(self):
        cover = _make_sb_cover()
        cover._press_task = None
        cover._press_active = True

        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            await cover._supersede_active_press()

        cover.hass.services.async_call.assert_awaited_once_with(
            "homeassistant",
            "turn_off",
            {"entity_id": "switch.button"},
            False,
        )
        from custom_components.cover_time_based.const import DIRECTION_CHANGE_DELAY

        mock_sleep.assert_awaited_once_with(DIRECTION_CHANGE_DELAY)
        assert cover._press_active is False

    @pytest.mark.asyncio
    async def test_penalty_free_when_nothing_in_flight(self):
        cover = _make_sb_cover()
        cover._press_task = None
        cover._press_active = False

        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            await cover._supersede_active_press()

        cover.hass.services.async_call.assert_not_awaited()
        mock_sleep.assert_not_awaited()


class TestEndpointReanchor:
    def test_immediate_anchor_when_no_runon(self):
        cover = _make_sb_cover()
        cover._endpoint_runon_time = None
        cover._phase = Phase.MOVING_UP
        cover._on_endpoint_reached(100)
        assert cover._phase is Phase.AT_OPEN

    def test_immediate_anchor_closed(self):
        cover = _make_sb_cover()
        cover._endpoint_runon_time = 0
        cover._phase = Phase.MOVING_DOWN
        cover._on_endpoint_reached(0)
        assert cover._phase is Phase.AT_CLOSED

    @pytest.mark.asyncio
    async def test_settle_margin_defers_anchor(self):
        cover = _make_sb_cover()
        cover._endpoint_runon_time = 2.0
        cover._phase = Phase.MOVING_UP
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            cover._on_endpoint_reached(100)
            # Phase still moving until the margin elapses.
            assert cover._phase is Phase.MOVING_UP
            await _drain(cover)
        assert cover._phase is Phase.AT_OPEN


class TestResync:
    @pytest.mark.asyncio
    async def test_resync_closed(self):
        cover = _make_sb_cover()
        cover._phase = Phase.MOVING_UP
        cover.async_write_ha_state = MagicMock()
        cover._async_persist_position = AsyncMock()
        cover.travel_calc.set_position(70)
        await cover.async_resync("closed")
        assert cover._phase is Phase.AT_CLOSED
        assert cover.travel_calc.current_position() == 0
        cover._async_persist_position.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resync_open(self):
        cover = _make_sb_cover()
        cover.async_write_ha_state = MagicMock()
        cover._async_persist_position = AsyncMock()
        await cover.async_resync("open")
        assert cover._phase is Phase.AT_OPEN
        assert cover.travel_calc.current_position() == 100

    @pytest.mark.asyncio
    async def test_resync_rejects_unknown(self):
        from homeassistant.exceptions import HomeAssistantError

        cover = _make_sb_cover()
        with pytest.raises(HomeAssistantError, match="halfway"):
            await cover.async_resync("halfway")
        # An invalid state must not touch the phase -- it is left at
        # whatever it was, since the base class rejects before
        # _on_known_position is ever called.
        assert cover._phase is Phase.AT_CLOSED

    @pytest.mark.asyncio
    async def test_resync_while_moving_presses_nothing(self):
        """A declared endpoint means the motor is parked there; a 'stop' press
        on a parked single-button motor would start it."""
        cover = _make_sb_cover()
        cover._phase = Phase.MOVING_UP
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel(100)
        cover.async_write_ha_state = MagicMock()
        cover._async_persist_position = AsyncMock()
        cover.hass.services.async_call.reset_mock()
        await cover.async_resync("open")
        turn_ons = [
            c
            for c in cover.hass.services.async_call.await_args_list
            if c.args[1] == "turn_on"
        ]
        assert turn_ons == []
        assert cover._phase is Phase.AT_OPEN
        assert not cover.travel_calc.is_traveling()


class TestKnownPosition:
    """A declared position anchors the tracked phase only at an endpoint --
    an intermediate position says nothing about where the motor is in its
    cycle."""

    @pytest.mark.asyncio
    async def test_set_known_position_endpoint_anchors_phase(self):
        cover = _make_sb_cover()
        cover._phase = Phase.MOVING_UP
        cover.async_write_ha_state = MagicMock()
        cover._async_persist_position = AsyncMock()
        await cover.set_known_position(position=100)
        assert cover._phase is Phase.AT_OPEN
        assert cover.travel_calc.current_position() == 100

    @pytest.mark.asyncio
    async def test_set_known_position_intermediate_leaves_phase(self):
        cover = _make_sb_cover()
        cover._phase = Phase.STOPPED_AFTER_DOWN
        cover.async_write_ha_state = MagicMock()
        cover._async_persist_position = AsyncMock()
        await cover.set_known_position(position=50)
        assert cover._phase is Phase.STOPPED_AFTER_DOWN
        assert cover.travel_calc.current_position() == 50

    @pytest.mark.asyncio
    async def test_pending_startup_delay_is_cancelled(self):
        """The startup-delay wait must go too: its deferred start() would
        re-animate the tracker from the declared position toward the old
        target with no press behind it."""
        cover = _make_sb_cover()
        cover._phase = Phase.MOVING_UP
        cover.async_write_ha_state = MagicMock()
        cover._async_persist_position = AsyncMock()
        cover._startup_delay_task = cover.hass.async_create_task(asyncio.sleep(60))
        cover.hass.services.async_call.reset_mock()
        await cover.set_known_position(position=100)
        assert (
            cover._startup_delay_task is None or cover._startup_delay_task.cancelled()
        )
        turn_ons = [
            c
            for c in cover.hass.services.async_call.await_args_list
            if c.args[1] == "turn_on"
        ]
        assert turn_ons == []
        assert cover._phase is Phase.AT_OPEN


class TestRemovalCancelsBackgroundWork:
    """A config-entry reload (every card save) can land mid-sequence: the
    press sequence's inter-press gap, the settle margin after an endpoint,
    or a single pulse's own completion may all be in flight. Left alone the
    OLD entity keeps pressing the physical button after the new one takes
    over -- real motor desync. Removal must cancel everything in flight and
    leave the button relay OFF, mirroring
    PulseModeCover._cancel_background_pulses (cover_pulse_mode.py)."""

    @pytest.mark.asyncio
    async def test_removal_cancels_in_flight_press_sequence_and_turns_button_off(
        self,
    ):
        cover = _make_sb_cover()
        cover._phase = Phase.STOPPED_AFTER_UP  # 3-press nudge: a multi-step sequence

        # Deliberately do NOT patch `sleep`: the real pulse-width sleep inside
        # the first discrete press gives the task a genuine suspend point, so
        # we can observe it paused mid-sequence (one press issued, still ON,
        # the next still pending) without waiting out the real delay.
        await cover._send_open()
        await asyncio.sleep(0)

        assert len(_presses(cover)) == 1
        assert cover._press_task is not None
        assert not cover._press_task.done()

        await cover.async_will_remove_from_hass()

        assert cover._press_task is None
        assert cover._settle_task is None
        # No further presses were issued once removal started.
        assert len(_presses(cover)) == 1
        # The button relay ends OFF, not left latched from the in-flight pulse.
        cover.hass.services.async_call.assert_any_call(
            "homeassistant", "turn_off", {"entity_id": "switch.button"}, False
        )

    @pytest.mark.asyncio
    async def test_removal_cancels_in_flight_settle_task(self):
        cover = _make_sb_cover()
        cover._endpoint_runon_time = 2.0
        cover._phase = Phase.MOVING_UP

        with patch(
            "custom_components.cover_time_based.cover_single_button_mode.sleep",
            new_callable=AsyncMock,
        ):
            # The settle task is created but not yet drained/awaited here, so
            # it is still in flight when removal happens.
            cover._on_endpoint_reached(100)
            assert cover._settle_task is not None
            assert not cover._settle_task.done()

            await cover.async_will_remove_from_hass()

            assert cover._settle_task is None
            # The phase must not have been silently anchored by a settle task
            # that kept running after removal.
            assert cover._phase is Phase.MOVING_UP


class TestResyncCancelsInFlightPress:
    """resync declares a fixed endpoint (issue #245). If it fires while a
    press sequence is mid-flight, that sequence's own next iteration would
    otherwise overwrite `_phase` from the plan it computed before resync
    ran -- silently clobbering the phase resync just set, while the motor
    keeps running the old sequence against a cover we just declared parked.
    resync must cancel the in-flight sequence (and leave the button OFF)
    before anchoring the phase, via the same _abort_press_plan that
    _send_open/_send_close/_send_stop run before starting a new one."""

    @pytest.mark.asyncio
    async def test_resync_cancels_in_flight_press_sequence_and_wins_the_phase(
        self,
    ):
        cover = _make_sb_cover(pulse_time=0.01)
        # STOPPED_AFTER_UP -> open is the 3-press nudge: a genuinely
        # multi-step sequence, so there is more than one press left for the
        # old plan to (wrongly) keep issuing if resync doesn't cancel it.
        cover._phase = Phase.STOPPED_AFTER_UP
        cover.async_write_ha_state = MagicMock()
        cover._async_persist_position = AsyncMock()

        # Deliberately do NOT patch `sleep`: real asyncio.sleep with a tiny
        # pulse_time gives the press task a genuine suspend point, so
        # `await asyncio.sleep(0)` can park it mid-pulse (button ON, task
        # not done) exactly as TestMidPressInterruption does.
        with patch(
            "custom_components.cover_time_based.cover_single_button_mode."
            "DIRECTION_CHANGE_DELAY",
            0.01,
        ):
            await cover._send_open()
            await asyncio.sleep(0)  # park mid-pulse

            assert cover._press_task is not None
            assert not cover._press_task.done()

            await cover.async_resync("open")
            await _drain(cover)

        # The in-flight sequence was cancelled outright -- not left to run
        # its remaining presses.
        assert cover._press_task is None
        # The button ended OFF, not left latched from the interrupted pulse.
        assert cover.hass.services.async_call.call_args_list[-1] == call(
            "homeassistant", "turn_off", {"entity_id": "switch.button"}, False
        )
        # Resync's phase wins -- not whatever the interrupted sequence would
        # have gone on to set.
        assert cover._phase is Phase.AT_OPEN
