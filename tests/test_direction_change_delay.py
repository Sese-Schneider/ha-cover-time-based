"""Tests for the direction-change (stop->reverse settle) delay.

Reversing a moving cover means stop, settle, then drive the new direction. The
gap is a fixed 1.0 second. It was briefly configurable per cover (never in a
promoted release): the justification turned out to be wrong -- the reporter's
hardware reverses correctly at 1.0s, which every prior version also used -- and
the only thing the knob demonstrably enabled was setting it *below* 1.0s, which
desyncs the cover and, in toggle-opposite mode, can drive it to its endpoint.
The key is still accepted from YAML and the websocket API so existing configs
load, but it is ignored.
"""

import asyncio
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
)

from custom_components.cover_time_based.const import (
    CONF_DIRECTION_CHANGE_DELAY,
    DIRECTION_CHANGE_DELAY,
)
from custom_components.cover_time_based.cover import (
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_CONTROL_MODE,
    CONF_DEFAULTS,
    CONF_DEVICES,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONTROL_MODE_PULSE,
    CONTROL_MODE_SWITCH,
    CONTROL_MODE_TOGGLE_OPPOSITE,
    _create_cover_from_options,
    devices_from_config,
)

SLEEP = "custom_components.cover_time_based.cover_base.sleep"


def _switch_options(**extra):
    return {
        CONF_CONTROL_MODE: CONTROL_MODE_SWITCH,
        CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
        CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
        **extra,
    }


@pytest.mark.asyncio
async def test_the_settle_gap_is_a_fixed_one_second(make_cover):
    """The historical 1.0s, now not configurable."""
    cover = make_cover()
    with patch(SLEEP, new_callable=AsyncMock) as slept:
        await cover._direction_change_delay()
    slept.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_a_stored_option_no_longer_changes_the_gap():
    """An rc tester's stored value must not shorten (or lengthen) the gap.

    Entries written while the option existed still carry the key; it is read
    by nothing, so the gap stays 1.0s.
    """
    cover = _create_cover_from_options(
        _switch_options(**{CONF_DIRECTION_CHANGE_DELAY: 0}),
        device_id="test",
        name="Test",
    )
    with patch(SLEEP, new_callable=AsyncMock) as slept:
        await cover._direction_change_delay()
    slept.assert_awaited_once_with(1.0)


def test_yaml_carrying_the_removed_key_still_loads():
    """Platform schemas are strict, so an unknown key would kill setup.

    The key stays in the schema precisely so a YAML config written against the
    rc keeps working -- accepted, then ignored.
    """
    config = {
        CONF_DEFAULTS: {},
        CONF_DEVICES: {
            "blind1": {
                "name": "Living Room",
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
                CONF_DIRECTION_CHANGE_DELAY: 4.0,
            },
        },
    }
    devices = devices_from_config(config)
    assert len(devices) == 1


def test_yaml_defaults_block_carrying_the_removed_key_still_loads():
    """Same, via the defaults: block (which also accepted null)."""
    config = {
        CONF_DEFAULTS: {CONF_DIRECTION_CHANGE_DELAY: None},
        CONF_DEVICES: {
            "blind1": {
                "name": "Living Room",
                CONF_OPEN_SWITCH_ENTITY_ID: "switch.open",
                CONF_CLOSE_SWITCH_ENTITY_ID: "switch.close",
            },
        },
    }
    assert len(devices_from_config(config)) == 1


@pytest.mark.asyncio
async def test_set_position_reversal_still_settles_between_stop_and_reverse(make_cover):
    """Regression guard for issue #153: the gap must land *between* the two."""
    cover = make_cover(control_mode=CONTROL_MODE_TOGGLE_OPPOSITE)
    cover.hass.states.get = MagicMock(
        side_effect=lambda eid: SimpleNamespace(state="off")
    )

    cover.travel_calc.set_position(40)
    cover.travel_calc.start_travel_up()
    cover._last_command = SERVICE_OPEN_COVER

    events = []
    real_handle = cover._async_handle_command

    async def record_command(command, *args):
        events.append(command)
        return await real_handle(command, *args)

    async def record_sleep(seconds):
        events.append(f"sleep:{seconds}")

    with (
        patch.object(cover, "async_write_ha_state"),
        patch.object(cover, "_async_handle_command", side_effect=record_command),
        patch(SLEEP, side_effect=record_sleep),
    ):
        await cover.set_position(20)

    assert (
        events.index(SERVICE_STOP_COVER)
        < events.index("sleep:1.0")
        < events.index(SERVICE_CLOSE_COVER)
    )


def test_the_key_is_not_exposed_as_a_state_attribute():
    cover = _create_cover_from_options(_switch_options(), device_id="test", name="Test")
    assert CONF_DIRECTION_CHANGE_DELAY not in cover.extra_state_attributes


class _ParkedReversal:
    """A reversal driven to the point where it is waiting out the settle gap.

    ``arrived`` resolves the moment the reversal enters the gap and ``release``
    lets it out, so tests rendezvous with it exactly rather than guessing how
    many event-loop turns it takes to get there.

    By default the UI slider reverses it. ``external_press`` instead runs the
    wall-switch entry point for that command, with _triggered_externally held
    for the whole call — settle gap included — exactly as
    _async_switch_state_changed's try/finally does. Everything else (which way
    the cover was already moving, which entry point to call, what should have
    been commanded by the time it parks) follows from that one choice, so no
    caller can pair them inconsistently.
    """

    def __init__(self, cover, *, external_press=None):
        self.cover = cover
        self.commands = []
        self.arrived = asyncio.Event()
        self._release = asyncio.Event()
        self._task = None
        self._slept_for = None
        self._external_press = external_press
        if external_press is None:
            # Opening at 40%, slider dragged below it.
            self._start = lambda c: c.set_position(20)
            self._was_closing = False
            # set_position stops via _async_handle_command, which we record.
            self._commands_at_park = [SERVICE_STOP_COVER]
        else:
            closing = external_press == SERVICE_OPEN_COVER
            # Press the real relay and let the mode's own handler decide what
            # that means, rather than calling async_open/close_cover directly —
            # otherwise the test proves only that the base guard works, not
            # that any external trigger actually reaches it.
            self._start = lambda c: c._handle_external_state_change(
                c._open_switch_entity_id if closing else c._close_switch_entity_id,
                "off",
                "on",
            )
            # A reversal only happens against the opposite direction.
            self._was_closing = closing
            # The prelude stop runs with _triggered_externally set, so it goes
            # out via _send_stop (itself suppressed) — never through
            # _async_handle_command, which is what we record.
            self._commands_at_park = []

    async def _record(self, command, *args):
        self.commands.append(command)
        return await self._real_handle(command, *args)

    async def _gated_sleep(self, seconds):
        self._slept_for = seconds
        self.arrived.set()
        await self._release.wait()

    async def _as_external(self, coro):
        """Hold the external flag across the whole call, settle gap included.

        _async_switch_state_changed wraps its handler in exactly this
        try/finally, so a command parked in the gap is still 'external' when
        anything else lands on the cover meanwhile.

        Set *inside* the task, not before it, because that is where the
        dispatcher sets it. A test that raises the flag in its own context and
        then calls the cover from that same context is not modelling a wall
        switch — it is modelling a wall switch and a UI click sharing one call
        stack, which never happens.
        """
        self.cover._triggered_externally = True
        try:
            await coro
        finally:
            self.cover._triggered_externally = False

    async def __aenter__(self):
        cover = self.cover
        cover.hass.states.get = MagicMock(
            side_effect=lambda eid: SimpleNamespace(state="off")
        )
        cover.travel_calc.set_position(40)
        if self._was_closing:
            cover.travel_calc.start_travel_down()
            cover._last_command = SERVICE_CLOSE_COVER
        else:
            cover.travel_calc.start_travel_up()
            cover._last_command = SERVICE_OPEN_COVER

        self._real_handle = cover._async_handle_command
        self._patches = [
            patch.object(cover, "async_write_ha_state"),
            patch.object(cover, "_async_handle_command", side_effect=self._record),
            patch(SLEEP, side_effect=self._gated_sleep),
        ]
        for p in self._patches:
            p.start()

        try:
            # Reverse: already moving at 40%, now told to go the other way.
            coro = self._start(cover)
            if self._external_press is not None:
                coro = self._as_external(coro)
            self._task = asyncio.create_task(coro)
            await self._wait_until_parked()
            # The settle gap is the only sleep with this duration, so this
            # pins us to it rather than to a startup delay or a run-on.
            assert self._slept_for == DIRECTION_CHANGE_DELAY
            assert self.commands == self._commands_at_park
        except BaseException:
            # __aexit__ never runs when __aenter__ raises, so without this the
            # module-level sleep patch would leak into every later test and the
            # reversal task would be stranded.
            await self._abort()
            raise
        return self

    async def _wait_until_parked(self):
        """Wait for the gap, but never outlive a reversal that never gets there.

        A bare arrived.wait() hangs the whole suite if the entry point bails
        before the gap (or raises), and there is no --timeout configured to cut
        it short — so race the rendezvous against the task itself.
        """
        arrived = asyncio.ensure_future(self.arrived.wait())
        done, _ = await asyncio.wait(
            {arrived, self._task}, return_when=asyncio.FIRST_COMPLETED
        )
        if arrived in done:
            return
        # Cancel *and* collect it, or the loop closes on a pending task and the
        # "Task was destroyed" warning lands on whichever test runs next.
        arrived.cancel()
        with suppress(asyncio.CancelledError):
            await arrived
        # The task finished without ever parking: surface its exception, or say
        # so plainly if it simply returned.
        self._task.result()
        raise AssertionError(
            "reversal completed without waiting out the settle gap"
            f" (commands={self.commands})"
        )

    async def as_external_press(self, coro):
        """Run ``coro`` the way the dispatcher runs a second wall press.

        Its own task with the flag raised for the duration — so a press landing
        inside the parked reversal's window is genuinely inside the external
        window, which is the only condition under which these tests say
        anything.
        """
        return await asyncio.create_task(self._as_external(coro))

    async def resume(self):
        self._release.set()
        await self._task

    async def _abort(self):
        """Tear down without masking whatever failure got us here."""
        self._release.set()
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)
        self._stop_patches()

    def _stop_patches(self):
        for p in self._patches:
            p.stop()

    async def __aexit__(self, *exc):
        try:
            if not self._release.is_set():
                await self.resume()
        finally:
            self._stop_patches()


def _reversing_cover(make_cover):
    return make_cover(control_mode=CONTROL_MODE_TOGGLE_OPPOSITE)


@pytest.mark.asyncio
async def test_stop_during_the_settle_gap_cancels_the_reversal(make_cover):
    """A stop landing inside the settle gap must win.

    The reversal stops the motor, waits out the gap, then drives the new
    direction. Nothing re-checked that the movement was still wanted, so a stop
    arriving during the gap was overridden when the coroutine resumed — the
    cover moved *after* the user told it to stop, up to direction_change_delay
    seconds later. Raising the gap for slow motors widens that window.
    """
    async with _ParkedReversal(_reversing_cover(make_cover)) as reversal:
        await reversal.cover.async_stop_cover()
        await reversal.resume()

    assert reversal.commands == [SERVICE_STOP_COVER]
    assert not reversal.cover.travel_calc.is_traveling()


@pytest.mark.asyncio
async def test_newer_target_during_the_settle_gap_supersedes_the_reversal(make_cover):
    """A second slider drag inside the gap wins over the first.

    The stale reversal must not wake and drive its own (now abandoned)
    direction while the newer movement is already tracking — that would leave
    motor and tracker disagreeing, the same desync class this option exists to
    fix.
    """
    async with _ParkedReversal(_reversing_cover(make_cover)) as reversal:
        # Same direction as the original travel, so it drives straight away
        # rather than parking in a gap of its own.
        await reversal.cover.set_position(60)
        await reversal.resume()

    assert SERVICE_CLOSE_COVER not in reversal.commands
    assert reversal.cover.travel_calc._travel_to_position == 60


@pytest.mark.asyncio
async def test_tilt_command_during_the_settle_gap_supersedes_the_reversal(make_cover):
    """A tilt command in the gap also invalidates a parked travel reversal.

    On an inline (shared-motor) cover the tilt IS the travel motor, so letting
    a stale travel reversal drive afterwards fights a tilt movement that is
    already tracking. Travel commands are not the only superseding route.
    """
    cover = make_cover(
        control_mode=CONTROL_MODE_TOGGLE_OPPOSITE,
        tilt_mode="inline",
        tilt_time_close=10,
        tilt_time_open=10,
    )
    async with _ParkedReversal(cover) as reversal:
        await cover.set_tilt_position(80)
        await reversal.resume()

    assert SERVICE_CLOSE_COVER not in reversal.commands


@pytest.mark.asyncio
async def test_undisturbed_reversal_still_completes(make_cover):
    """The guard must not cancel a reversal that nothing interrupted."""
    async with _ParkedReversal(_reversing_cover(make_cover)) as reversal:
        await reversal.resume()

    assert reversal.commands == [SERVICE_STOP_COVER, SERVICE_CLOSE_COVER]
    assert reversal.cover.travel_calc._travel_to_position == 20


@pytest.mark.asyncio
async def test_device_feedback_during_the_settle_gap_does_not_abort(make_cover):
    """Only our own intent supersedes a reversal — not the device talking back.

    Passive routes reach _handle_stop too: a wrapped cover reporting its
    settled position snaps via set_known_position, and a switch-mode relay's
    unmarked off (e.g. a hardware interlock clearing the opposite relay) calls
    async_stop_cover. Both run with _triggered_externally set, and both can
    land inside the settle window — the wrapped cover's self-echo suppressors
    are keyed on is_traveling(), which the reversal has already cleared.

    Treating those as supersessions silently drops the user's move, or worse
    freezes the tracker while the motor runs, which is the very desync the
    guard exists to prevent.

    Those routes say so with supersede=False. This is the direct test of that
    contract; test_wrapped_snap_does_not_claim_the_movement then checks a real
    one of them still declares itself feedback.
    """
    async with _ParkedReversal(_reversing_cover(make_cover)) as reversal:
        await reversal.cover.async_stop_cover(supersede=False)
        await reversal.resume()

    # The reversal was the user's; the echo must not have cancelled it.
    assert reversal.commands == [SERVICE_STOP_COVER, SERVICE_CLOSE_COVER]
    assert reversal.cover.travel_calc._travel_to_position == 20


@pytest.mark.asyncio
async def test_wrapped_snap_does_not_claim_the_movement(make_cover):
    """The real device-feedback route still declares itself feedback.

    _snap_to_position is how a wrapped cover records the position its inner
    entity just reported, and it reaches _handle_stop like any other stop.
    Claiming the movement is what cancels a parked reversal (the test above
    ties the two together), so it is enough — and far cheaper than parking a
    reversal on a natively-positioned wrapped cover — to assert this caller
    leaves the epoch alone.
    """
    cover = make_cover(cover_entity_id="cover.inner")
    cover.travel_calc.set_position(40)

    with patch.object(cover, "async_write_ha_state"):
        before = cover._movement_epoch
        await cover._snap_to_position(35)

    assert cover._movement_epoch == before


# ---------------------------------------------------------------------------
# The external-trigger reversals (wall switch / remote), which reach the same
# settle gap from async_close_cover and async_open_cover rather than from
# set_position. A UI click on a moving cover just stops it; only these external
# entry points keep the legacy stop-and-reverse.
# ---------------------------------------------------------------------------


def _external_cover(make_cover):
    """A mode whose external handler really does stop-settle-reverse.

    Pulse mode drives async_open_cover/async_close_cover straight off a relay
    pulse, so an opposite press while moving reaches the reversal branch.
    Toggle-opposite does not — its handler stops on an opposite press and waits
    for the next one — so it cannot stand in for a wall switch here.
    """
    return make_cover(
        control_mode=CONTROL_MODE_PULSE,
        stop_switch="switch.stop",
        direction_change_delay=2.5,
    )


def _parked_external(make_cover, press):
    """Moving at 40%, wall switch presses the opposite button: stop, settle,
    then reverse."""
    return _ParkedReversal(_external_cover(make_cover), external_press=press)


def _parked_external_close(make_cover):
    return _parked_external(make_cover, SERVICE_CLOSE_COVER)


@pytest.mark.asyncio
async def test_undisturbed_external_close_reversal_still_completes(make_cover):
    """The guard must not cancel an external reversal nothing interrupted."""
    async with _parked_external_close(make_cover) as reversal:
        await reversal.resume()

    assert SERVICE_CLOSE_COVER in reversal.commands
    assert reversal.cover.travel_calc._travel_to_position == 0


@pytest.mark.asyncio
async def test_undisturbed_external_open_reversal_still_completes(make_cover):
    """Mirror of the close case, entered from async_open_cover."""
    reversal = _parked_external(make_cover, SERVICE_OPEN_COVER)
    async with reversal:
        await reversal.resume()

    assert SERVICE_OPEN_COVER in reversal.commands
    assert reversal.cover.travel_calc._travel_to_position == 100


@pytest.mark.asyncio
async def test_stop_during_the_gap_cancels_an_external_close_reversal(make_cover):
    """A stop landing inside an external reversal's settle gap must win.

    Same requirement as the set_position reversal, reached from the wall-switch
    path — and the harder case. _handle_stop used to decide this by reading
    _triggered_externally, ambient instance state held for the *whole* external
    call, settle gap included; a genuine stop arriving in that window was
    therefore indistinguishable from a device echo, so it was dropped and the
    parked reversal drove the cover up to direction_change_delay seconds after
    the user said stop. Callers now say which kind of stop they are.
    """
    async with _parked_external_close(make_cover) as reversal:
        # No flag fiddling: production leaves it set, which is the whole point.
        await reversal.cover.async_stop_cover()
        await reversal.resume()

    assert SERVICE_CLOSE_COVER not in reversal.commands
    assert not reversal.cover.travel_calc.is_traveling()


@pytest.mark.asyncio
async def test_ui_stop_during_the_gap_actually_stops_the_relay(make_cover):
    """Cancelling the reversal is only half a stop — the relay must fire too.

    _triggered_externally suppresses relay writes so we never echo a command
    back at hardware that is already doing it. But it is instance state, and
    the parked external call holds it for the whole settle gap, so a UI stop
    arriving in that window inherited the suppression: the movement was
    claimed and nothing was ever sent. The tracker halted while the motor ran
    on to the endpoint.

    The stop is a separate task with its own context, exactly as HA dispatches
    a service call, so it must see the flag clear.
    """
    async with _parked_external_close(make_cover) as reversal:
        cover = reversal.cover
        with patch.object(cover, "_send_stop", new_callable=AsyncMock) as send_stop:
            await asyncio.create_task(cover.async_stop_cover())
        await reversal.resume()

    send_stop.assert_awaited_once()
    assert SERVICE_CLOSE_COVER not in reversal.commands


@pytest.mark.asyncio
async def test_the_external_flag_does_not_outlive_the_call_into_scheduled_work(
    make_cover,
):
    """Task scoping must not become descendant-task scoping.

    A context is *copied into* every task and timer callback created while it
    is active, and HA's interval timer reschedules itself from inside the copy
    — so a flag merely stored in a ContextVar propagates to the whole auto
    updater chain and every auto_stop_if_necessary it spawns, for the life of
    the movement. Externally-started moves would then suppress their own
    endpoint relay stop, which on latching hardware leaves the relay energized.

    Scoping it to the task that raised it, rather than to the context, is what
    keeps it from being inherited. The suite's mock hass never builds a real
    timer chain, so this drives the scheduling primitives directly.
    """
    cover = make_cover()
    seen = {}

    async def spawned():
        seen["task"] = cover._triggered_externally

    def timer_callback():
        seen["timer"] = cover._triggered_externally

    cover._triggered_externally = True
    try:
        assert cover._triggered_externally is True  # the handler's own view
        asyncio.get_running_loop().call_later(0, timer_callback)
        task = asyncio.create_task(spawned())
        await task
    finally:
        cover._triggered_externally = False

    await asyncio.sleep(0.01)

    assert seen["task"] is False, "a spawned task inherited the flag"
    assert seen["timer"] is False, "a timer callback inherited the flag"


@pytest.mark.asyncio
async def test_ui_move_during_the_gap_actually_drives_the_relay(make_cover):
    """The same leak, via _async_handle_command rather than _send_stop.

    A slider drag landing in an external reversal's gap correctly superseded
    it — _abandon_active_lifecycle never consulted the flag — and then tracked
    a movement it never commanded, because the relay write inherited the
    parked call's suppression. HA animates the position bar to the target
    while the cover does not move: a full desync, and the worse half of this
    bug, since the tracker ends up confidently wrong.
    """
    async with _parked_external_close(make_cover) as reversal:
        cover = reversal.cover
        with patch.object(cover, "_send_open", new_callable=AsyncMock) as send_open:
            await asyncio.create_task(cover.set_position(60))
        await reversal.resume()

    send_open.assert_awaited()
    assert cover.travel_calc._travel_to_position == 60


@pytest.mark.asyncio
async def test_ui_move_during_the_gap_is_recorded_as_self_initiated(make_cover):
    """_self_initiated_movement is snapshotted from the same flag.

    A UI move beginning inside the gap recorded itself as externally driven,
    which sends auto_stop_if_necessary down _settle_external_endpoint at
    completion instead of the normal endpoint stop and run-on handling — so
    the move ended wrong as well as starting wrong.
    """
    async with _parked_external_close(make_cover) as reversal:
        cover = reversal.cover
        with patch.object(cover, "_send_open", new_callable=AsyncMock):
            await asyncio.create_task(cover.set_position(60))
        assert cover._self_initiated_movement is True
        await reversal.resume()


@pytest.mark.asyncio
async def test_wall_stop_press_during_the_gap_cancels_an_external_reversal(make_cover):
    """A dedicated stop button is a command, even though it arrives externally.

    The rest of the external handlers report what the hardware did — a relay
    releasing, a wrapped cover settling — and must not cancel a reversal. A
    stop *switch* is the opposite: it only ever fires because someone pressed
    it. Lumping it in with the echoes let the press be swallowed by the settle
    gap and the cover reverse anyway, seconds after the user said stop.

    The press must be driven inside the external window the dispatcher holds,
    or the test proves nothing: the whole point is that this supersedes
    *despite* arriving with the flag raised, and outside that window it would
    pass on the old inferred behaviour too. No relay stop goes out as a result,
    which is correct — the stop relay the user pressed is already doing that.
    """
    async with _parked_external_close(make_cover) as reversal:
        cover = reversal.cover
        with patch.object(cover, "_send_stop", new_callable=AsyncMock) as send_stop:
            await reversal.as_external_press(
                cover._handle_external_state_change(
                    cover._stop_switch_entity_id, "off", "on"
                )
            )
        await reversal.resume()

    assert SERVICE_CLOSE_COVER not in reversal.commands
    assert not cover.travel_calc.is_traveling()
    send_stop.assert_not_awaited()


@pytest.mark.asyncio
async def test_newer_target_during_the_gap_supersedes_an_external_reversal(make_cover):
    """A slider drag inside an external reversal's gap wins over it.

    This route supersedes via _abandon_active_lifecycle, which is not gated on
    _triggered_externally, so it holds where the stop route does not.
    """
    async with _parked_external_close(make_cover) as reversal:
        await reversal.cover.set_position(60)
        await reversal.resume()

    assert SERVICE_CLOSE_COVER not in reversal.commands
    assert reversal.cover.travel_calc._travel_to_position == 60
