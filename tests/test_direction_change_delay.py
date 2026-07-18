"""Tests for the configurable direction-change (stop->reverse settle) delay.

Reversing a moving cover means stop, settle, then drive the new direction. The
settle gap must outlast the motor's stop-settle time, or the reverse command is
ignored while the position tracker keeps advancing (issue #153 follow-up: the
blind stays put, the entity ticks on to the target). Motors differ, so the gap
is configurable; it defaults to the historical 1.0s.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
)

from custom_components.cover_time_based.const import CONF_DIRECTION_CHANGE_DELAY
from custom_components.cover_time_based.cover import (
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_CONTROL_MODE,
    CONF_DEFAULTS,
    CONF_DEVICES,
    CONF_OPEN_SWITCH_ENTITY_ID,
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
async def test_direction_change_delay_uses_configured_value(make_cover):
    """A configured settle gap is what the reversal waits for."""
    cover = make_cover(direction_change_delay=2.5)
    with patch(SLEEP, new_callable=AsyncMock) as slept:
        await cover._direction_change_delay()
    slept.assert_awaited_once_with(2.5)


@pytest.mark.asyncio
async def test_direction_change_delay_defaults_to_one_second(make_cover):
    """Unset keeps the historical 1.0s, so existing covers are unaffected."""
    cover = make_cover()
    with patch(SLEEP, new_callable=AsyncMock) as slept:
        await cover._direction_change_delay()
    slept.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_explicit_none_in_options_falls_back_to_the_default():
    """An explicit None must not reach sleep().

    ``options.get(key, default)`` only substitutes the default for a *missing*
    key, so a present-but-None value is handed straight through. Resolving it
    at the boundary alone is therefore not enough; without the entity-side
    fallback this raises TypeError from sleep(None) on every reversal.
    """
    cover = _create_cover_from_options(
        _switch_options(**{CONF_DIRECTION_CHANGE_DELAY: None}),
        device_id="test",
        name="Test",
    )
    with patch(SLEEP, new_callable=AsyncMock) as slept:
        await cover._direction_change_delay()
    slept.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_yaml_defaults_block_may_null_the_delay():
    """The live route by which an explicit None reaches the entity.

    The YAML ``defaults:`` block accepts null, and ``_get_value`` returns it
    verbatim into options. (The card cannot produce this — ws_update_config
    pops the key on null — so this is the path that keeps the entity-side
    fallback load-bearing.)
    """
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
    cover = devices_from_config(config)[0]
    with patch(SLEEP, new_callable=AsyncMock) as slept:
        await cover._direction_change_delay()
    slept.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_zero_is_preserved_as_no_settle_gap():
    """0 is a legitimate value and must not be coerced to the default."""
    cover = _create_cover_from_options(
        _switch_options(**{CONF_DIRECTION_CHANGE_DELAY: 0}),
        device_id="test",
        name="Test",
    )
    with patch(SLEEP, new_callable=AsyncMock) as slept:
        await cover._direction_change_delay()
    slept.assert_awaited_once_with(0)


@pytest.mark.asyncio
async def test_set_position_reversal_settles_for_the_configured_gap(make_cover):
    """Regression guard for issue #153.

    Reversing mid-travel via set_position (opening, then a lower target) must
    wait the configured settle gap between the stop and the reverse command.
    With the old hardcoded 1.0s the reverse landed while the motor was still
    coming to rest, so the cover stayed put while the tracker ran on.
    """
    cover = make_cover(
        control_mode=CONTROL_MODE_TOGGLE_OPPOSITE, direction_change_delay=2.5
    )
    cover.hass.states.get = MagicMock(
        side_effect=lambda eid: SimpleNamespace(state="off")
    )

    cover.travel_calc.set_position(40)
    cover.travel_calc.start_travel_up()
    cover._last_command = SERVICE_OPEN_COVER

    # Record commands and sleeps on one timeline: the gap has to land *between*
    # the stop and the reverse. Asserting only that sleep(2.5) happened would
    # still pass if the settle were awaited after the reverse was already sent,
    # which is exactly the ordering the fix depends on.
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
        < events.index("sleep:2.5")
        < events.index(SERVICE_CLOSE_COVER)
    )


def test_configured_delay_is_wired_through_from_options():
    """The option reaches the cover built by the factory."""
    cover = _create_cover_from_options(
        _switch_options(**{CONF_DIRECTION_CHANGE_DELAY: 3.0}),
        device_id="test",
        name="Test",
    )
    assert cover._direction_change_delay_time == 3.0


def test_yaml_device_config_accepts_the_delay():
    """YAML parity with the other timing options."""
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
    assert devices[0]._direction_change_delay_time == 4.0


def test_omitted_option_leaves_the_default():
    """An unset option falls back to the historical 1.0s."""
    cover = _create_cover_from_options(_switch_options(), device_id="test", name="Test")
    assert cover._direction_change_delay_time == 1.0


class _ParkedReversal:
    """A reversal driven to the point where it is waiting out the settle gap.

    ``arrived`` resolves the moment the reversal enters the gap and ``release``
    lets it out, so tests rendezvous with it exactly rather than guessing how
    many event-loop turns it takes to get there.

    ``start`` selects the entry point that reverses (the UI slider by default);
    ``external`` runs it the way a wall switch does, with _triggered_externally
    held for the whole call — including the settle gap — exactly as
    _async_switch_state_changed's try/finally does.
    """

    def __init__(
        self,
        cover,
        *,
        start=None,
        external=False,
        closing=False,
        commands_at_park=None,
    ):
        self.cover = cover
        self.commands = []
        self.arrived = asyncio.Event()
        self._release = asyncio.Event()
        self._task = None
        self._start = start or (lambda c: c.set_position(20))
        self._external = external
        self._closing = closing
        self._commands_at_park = (
            [SERVICE_STOP_COVER] if commands_at_park is None else commands_at_park
        )

    async def _record(self, command, *args):
        self.commands.append(command)
        return await self._real_handle(command, *args)

    async def _gated_sleep(self, _seconds):
        self.arrived.set()
        await self._release.wait()

    async def _as_external(self, coro):
        """Hold the external flag across the whole call, settle gap included.

        _async_switch_state_changed wraps its handler in exactly this
        try/finally, so a command parked in the gap is still 'external' when
        anything else lands on the cover meanwhile.
        """
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
        if self._closing:
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
            # Reverse: opening at 40%, now told to go the other way.
            coro = self._start(cover)
            if self._external:
                cover._triggered_externally = True
                coro = self._as_external(coro)
            self._task = asyncio.create_task(coro)
            await self.arrived.wait()
            assert self.commands == self._commands_at_park
        except BaseException:
            # __aexit__ never runs when __aenter__ raises, so without this the
            # module-level sleep patch would leak into every later test and the
            # reversal task would be stranded.
            await self._abort()
            raise
        return self

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
    return make_cover(
        control_mode=CONTROL_MODE_TOGGLE_OPPOSITE, direction_change_delay=2.5
    )


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
        direction_change_delay=2.5,
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

    Those routes say so with supersede=False; test_wrapped_snap_during_the_gap
    _does_not_abort drives one of them for real, so this stays a direct test of
    the contract itself.
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


def _parked_external_close(make_cover):
    """Opening at 40%, wall switch says close: stop, settle, then reverse."""
    return _ParkedReversal(
        _reversing_cover(make_cover),
        start=lambda c: c.async_close_cover(),
        external=True,
        # async_stop_cover drives the relay via _send_stop, not
        # _async_handle_command, so nothing is recorded on the way in.
        commands_at_park=[],
    )


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
    reversal = _ParkedReversal(
        _reversing_cover(make_cover),
        start=lambda c: c.async_open_cover(),
        external=True,
        closing=True,
        commands_at_park=[],
    )
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
