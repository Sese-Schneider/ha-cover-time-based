"""Pulse-mode relay-pulse lifecycle: the echo bookkeeping must track reality.

In pulse mode a direction command turns the relay ON and schedules a
background ``_complete_pulse`` task that turns it OFF ``pulse_time`` later.
Both the ON edge and the deferred OFF edge echo back to us as state-change
events, so ``_send_open``/``_send_close``/``_send_stop`` pre-mark the relays in
``_pending_switch`` to filter those self-inflicted echoes out.

The bug (audit Task 14): when a *second* command lands inside the pulse window
— a stop, a double-stop, a re-press, or an auto-stop from a ``set_position``
move shorter than ``pulse_time`` — the still-scheduled completion's ``turn_off``
either never fires a real edge (relay already off) or is superseded, yet its
pre-counted echo lingers. That orphaned count then swallows the *next genuine
wall-button press* for up to the 5 s safety window.

These tests reproduce every corner of that window against a *physically
accurate* relay model: a service call only produces a state-change echo when it
actually flips the relay, and a background completion's ``turn_off`` echoes only
if the relay is still ON when it runs. For each scenario we assert the two
invariants that matter to real hardware:

1. once every self-inflicted echo has landed, ``_pending_switch`` is empty — no
   orphan; and
2. a fresh ``off -> on`` press afterwards reaches ``async_open_cover`` — it is
   not eaten by a stale pending count.

The repro is adapted from the audit probe
``test_pulse_stop_within_pulse_window_orphans_pending`` (which asserted the
*buggy* orphan); here we assert the *desired* no-orphan behaviour, so the suite
is RED on HEAD and GREEN once the fix lands.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.cover_time_based.cover import CONTROL_MODE_PULSE

OPEN = "switch.open"
CLOSE = "switch.close"
STOP = "switch.stop"


# ---------------------------------------------------------------------------
# A physically accurate relay + echo harness
# ---------------------------------------------------------------------------


class _FakeStates:
    """A minimal stateful ``hass.states`` (the repo ``make_hass`` has none)."""

    def __init__(self):
        self._states = {}

    def set(self, entity_id, value):
        self._states[entity_id] = value

    def state(self, entity_id):
        return self._states.get(entity_id)

    def get(self, entity_id):
        value = self._states.get(entity_id)
        if value is None:
            return None
        obj = MagicMock()
        obj.state = value
        return obj


def _install_stateful_hass(cover, relays=(OPEN, CLOSE, STOP)):
    """Replace the cover's mock hass with one that models relay state.

    ``homeassistant.turn_on``/``turn_off`` service calls mutate the relay's
    state and, *only when the state actually changes*, queue a state-change
    echo — exactly what HA fires back at our listener. Background completion
    tasks route their ``turn_off`` through the same mock, so a completion that
    lands on an already-off relay produces no echo, just like real hardware.
    """
    hass = MagicMock()
    states = _FakeStates()
    for relay in relays:
        states.set(relay, "off")
    hass.states = states

    echoes = []  # queued (entity_id, old, new) self-inflicted echoes
    tasks = []

    async def _service_call(domain, service, data, blocking=False):
        entity_id = data["entity_id"]
        old = states.state(entity_id) or "off"
        new = "on" if service == "turn_on" else "off"
        if old != new:
            states.set(entity_id, new)
            echoes.append((entity_id, old, new))

    hass.services.async_call = AsyncMock(side_effect=_service_call)

    def _create_task(coro):
        task = asyncio.ensure_future(coro)
        tasks.append(task)
        return task

    hass.async_create_task = _create_task
    hass._test_tasks = tasks
    hass._echoes = echoes
    cover.hass = hass
    return hass


def _make_event(entity_id, old, new):
    old_state = MagicMock()
    old_state.state = old
    new_state = MagicMock()
    new_state.state = new
    event = MagicMock()
    event.data = {
        "entity_id": entity_id,
        "old_state": old_state,
        "new_state": new_state,
    }
    return event


async def _deliver_echoes(cover):
    """Deliver every queued self-inflicted relay echo, in order."""
    queue = cover.hass._echoes
    while queue:
        entity_id, old, new = queue.pop(0)
        await cover._async_switch_state_changed(_make_event(entity_id, old, new))


async def _run_completions(cover):
    """Run (or reap, if cancelled) every background pulse-completion task, then
    deliver whatever echoes their ``turn_off`` calls produced.

    ``sleep`` is patched to return instantly, so an *uncancelled* completion
    fires its ``turn_off`` here; a completion the fix cancelled is reaped
    without firing. Either way we then flush the resulting echoes.
    """
    tasks = list(cover.hass._test_tasks)
    cover.hass._test_tasks.clear()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await _deliver_echoes(cover)


def _nonzero_pending(cover):
    return {k: v for k, v in cover._pending_switch.items() if v}


# ---------------------------------------------------------------------------
# The four in-the-window scenarios
# ---------------------------------------------------------------------------


async def _scenario_stop_within_window(cover):
    """Open, the relay reports ON, then the user STOPS before the pulse OFF."""
    await cover._send_open()
    await _deliver_echoes(cover)  # relay echoes ON
    await cover._send_stop()  # stop inside the pulse window
    await _deliver_echoes(cover)


async def _scenario_double_stop(cover):
    """Open, report ON, stop, then a SECOND stop inside the stop-pulse window."""
    await cover._send_open()
    await _deliver_echoes(cover)
    await cover._send_stop()
    await _deliver_echoes(cover)
    await cover._send_stop()  # double stop, stop relay still mid-pulse
    await _deliver_echoes(cover)


async def _scenario_repulse_same_direction(cover):
    """Open, report ON, then RE-PRESS open while the open relay is still ON."""
    await cover._send_open()
    await _deliver_echoes(cover)
    await cover._send_open()  # re-pulse same direction inside the window
    await _deliver_echoes(cover)


async def _scenario_setposition_shorter_than_pulse(cover):
    """A ``set_position`` move whose travel time is shorter than ``pulse_time``:
    the auto-stop fires before the relay's ON echo has even been delivered."""
    await cover._send_open()
    await cover._send_stop()  # stop before any echo is processed
    await _deliver_echoes(cover)


async def _scenario_direction_after_stop_within_window(cover):
    """A direction command that lands inside the *stop*-pulse window.

    After ``_send_stop`` the stop relay is ON with its own completion scheduled.
    A ``_send_open`` (a re-open, or any direction command following a
    ``set_position`` auto-stop) turns the stop relay off — so it must cancel the
    stop relay's completion too, or that completion's turn_off lands on an
    already-off relay and orphans ``{'switch.stop': 1}``.
    """
    await cover._send_open()
    await _deliver_echoes(cover)  # relay reports ON
    await cover._send_stop()  # stop relay pulses ON, completion scheduled
    await _deliver_echoes(cover)  # open OFF echo, stop ON echo
    await cover._send_open()  # re-open inside the stop-pulse window
    await _deliver_echoes(cover)


# Each scenario maps to (drive fn, the relay a genuine press then arrives on,
# the handler that press must reach).
SCENARIOS = {
    "stop_within_window": (_scenario_stop_within_window, OPEN, "async_open_cover"),
    "double_stop": (_scenario_double_stop, OPEN, "async_open_cover"),
    "repulse_same_direction": (
        _scenario_repulse_same_direction,
        OPEN,
        "async_open_cover",
    ),
    "setposition_shorter_than_pulse": (
        _scenario_setposition_shorter_than_pulse,
        OPEN,
        "async_open_cover",
    ),
    "direction_after_stop_within_window": (
        _scenario_direction_after_stop_within_window,
        STOP,
        "async_stop_cover",
    ),
}


@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
@pytest.mark.asyncio
async def test_pulse_lifecycle_no_orphan_and_press_not_swallowed(
    make_cover, scenario_id
):
    """For every in-window scenario: no orphaned pending echo remains, and a
    genuine wall-button press afterwards still reaches its handler."""
    drive, press_relay, handler_name = SCENARIOS[scenario_id]
    cover = make_cover(
        control_mode=CONTROL_MODE_PULSE,
        stop_switch=STOP,
        pulse_time=1.0,
    )
    _install_stateful_hass(cover)

    with (
        patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.cover_time_based.cover_base.async_call_later",
            return_value=lambda: None,
        ),
    ):
        await drive(cover)
        await _run_completions(cover)

        # Invariant 1: every self-inflicted echo has landed; nothing orphaned.
        assert _nonzero_pending(cover) == {}, (
            f"orphaned pending echo count(s): {cover._pending_switch}"
        )

        # Invariant 2: a genuine wall-button press is not swallowed. The pressed
        # relay is back off, so off -> on is a real external press.
        assert cover.hass.states.state(press_relay) == "off"
        cover.async_open_cover = AsyncMock()
        cover.async_close_cover = AsyncMock()
        cover.async_stop_cover = AsyncMock()
        await cover._async_switch_state_changed(_make_event(press_relay, "off", "on"))
        getattr(cover, handler_name).assert_awaited_once()


@pytest.mark.asyncio
async def test_pulse_stop_within_window_probe_desired_behaviour(make_cover):
    """The audit probe, re-expressed to assert the *desired* outcome.

    The probe ``test_pulse_stop_within_pulse_window_orphans_pending`` walked the
    same steps and asserted the orphan (``== 1``) and the swallowed press; here
    we assert no orphan and that the press reaches the handler. RED on HEAD.
    """
    cover = make_cover(
        control_mode=CONTROL_MODE_PULSE,
        stop_switch=STOP,
        pulse_time=1.0,
    )
    _install_stateful_hass(cover)

    with (
        patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.cover_time_based.cover_base.async_call_later",
            return_value=lambda: None,
        ),
    ):
        # 1. open command
        await cover._send_open()
        # 2. relay echoes ON
        await _deliver_echoes(cover)
        assert cover._pending_switch.get(OPEN) == 1  # deferred off still pending
        # 3. user stops before the pulse completes
        await cover._send_stop()
        # 4. stop's turn_off echoes OFF; stop relay echoes ON
        await _deliver_echoes(cover)
        # 5. the (now superseded) open completion fires/reaps; stop completes
        await _run_completions(cover)

        # No orphan: the open relay's pending count is fully consumed.
        assert cover._pending_switch.get(OPEN, 0) == 0
        assert _nonzero_pending(cover) == {}

        # 6. genuine wall-button press is NOT swallowed
        cover.async_open_cover = AsyncMock()
        await cover._async_switch_state_changed(_make_event(OPEN, "off", "on"))
        cover.async_open_cover.assert_awaited_once()


@pytest.mark.asyncio
async def test_removal_cancels_pulses_and_turns_relays_off(make_cover):
    """``async_will_remove_from_hass`` must cancel in-flight completions AND fire
    their ``turn_off`` so a relay caught mid-pulse is not left latched ON."""
    cover = make_cover(
        control_mode=CONTROL_MODE_PULSE,
        stop_switch=STOP,
        pulse_time=1.0,
    )
    hass = _install_stateful_hass(cover)
    cover.stop_auto_updater = MagicMock()

    with (
        patch(
            "custom_components.cover_time_based.cover_pulse_mode.sleep",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.cover_time_based.cover_base.async_call_later",
            return_value=lambda: None,
        ),
    ):
        # Open: the open relay is now ON with its completion still scheduled.
        await cover._send_open()
        await _deliver_echoes(cover)
        assert hass.states.state(OPEN) == "on"
        assert cover._pulse_tasks  # a completion is in flight

        await cover.async_will_remove_from_hass()

        # The mid-pulse relay was turned off, not left latched.
        assert hass.states.state(OPEN) == "off"
        # The completion task was cancelled and the registry cleared.
        assert cover._pulse_tasks == {}
