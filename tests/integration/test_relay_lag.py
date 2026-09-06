"""Switch mode driving relays whose HA state lags the command (slow mesh).

The relays here are NOT input_boolean: they are bare states driven by the
``LaggingRelays`` harness, which models a Zigbee switch whose HA state trails
the command by a couple of seconds. The command flips the *physical* contact
immediately; the state machine only learns about it ``lag`` seconds later, in
command order. ``relay_lag`` is parametrisable indirectly, so the harness is
reusable for any slow-mesh scenario; lag 0 is the control.

The reversal below is the case that made the harness necessary: a command
issued inside the lag window has to pre-count the echo it will cause from what
it commanded, because HA still shows the state the relay had before.

Not covered here: ``wait_for_relay_feedback``. Mock time and feedback waits
stay mutually exclusive in this harness: the feedback wait runs on a background
task whose ``commanded_at`` reads the real monotonic clock, while ``mock_clock``
drives only the calculator's module clock. The feedback interaction is covered
at unit level in tests/test_relay_feedback.py, with both module clocks aligned.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.util import dt as dt_util

from custom_components.cover_time_based.calibration import CalibrationState
from tests.helpers import FakeClock

OPEN_RELAY = "switch.lag_open"
CLOSE_RELAY = "switch.lag_close"

LAG = 2.0
TRAVEL_TIME = 10.0


class LaggingRelays:
    """A pair of relays whose HA state trails the command by ``LAG`` seconds.

    ``homeassistant.turn_on`` / ``turn_off`` are overridden so the cover's
    relay writes land here. A write that actually flips the contact queues one
    state report for ``now + lag``; a write that does not (turn_off on an
    already-open contact) reports nothing, exactly as real hardware behaves.
    """

    def __init__(self, hass: HomeAssistant, mock_clock: FakeClock, lag: float = LAG):
        self.hass = hass
        self.mock_clock = mock_clock
        self._clock_start = mock_clock.monotonic()
        self.lag = lag
        self.physical: dict[str, bool] = {OPEN_RELAY: False, CLOSE_RELAY: False}
        self._queue: list[tuple[float, str, str]] = []
        self.commands: list[tuple[float, str, str]] = []
        for entity_id in self.physical:
            hass.states.async_set(entity_id, "off")

    def install(self):
        self.hass.services.async_register("homeassistant", "turn_on", self._handle)
        self.hass.services.async_register("homeassistant", "turn_off", self._handle)

    async def _handle(self, call):
        raw = call.data.get("entity_id")
        entity_ids = [raw] if isinstance(raw, str) else list(raw or [])
        want_on = call.service == "turn_on"
        for entity_id in entity_ids:
            if entity_id not in self.physical:
                continue
            self.commands.append(
                (
                    round(self.mock_clock.monotonic() - self._clock_start, 3),
                    call.service,
                    entity_id,
                )
            )
            if self.physical[entity_id] == want_on:
                continue  # no contact change -> the device reports nothing
            self.physical[entity_id] = want_on
            self._queue.append(
                (
                    self.mock_clock.time() + self.lag,
                    entity_id,
                    "on" if want_on else "off",
                )
            )

    async def deliver_due(self):
        """Push every report whose lag has expired into the state machine."""
        now = self.mock_clock.time()
        due = sorted((r for r in self._queue if r[0] <= now), key=lambda r: r[0])
        self._queue = [r for r in self._queue if r[0] > now]
        for _, entity_id, state in due:
            self.hass.states.async_set(entity_id, state)
            await self.hass.async_block_till_done()


def _get_cover_entity(hass: HomeAssistant):
    entity_comp = hass.data[DATA_INSTANCES]["cover"]
    entities = [e for e in entity_comp.entities if e.entity_id == "cover.test_cover"]
    assert entities, "Cover entity not found"
    return entities[0]


async def _advance(hass, cover, mock_clock, relays, seconds, step=0.25):
    """Advance mock time in small steps, delivering reports and ticking.

    Deliberately does NOT use ``async_fire_time_changed(..., fire_all=True)``:
    that fires every scheduled handle, including the 5 s echo-pending safety
    timers, which would clear the pending counts this repro depends on. The
    auto-updater is pumped by calling its hook directly instead — but only
    while it is actually subscribed, or the harness would drive arrival logic
    the real integration has already unsubscribed from.
    """
    remaining = seconds
    while remaining > 1e-9:
        chunk = min(step, remaining)
        mock_clock.advance(chunk)
        await relays.deliver_due()
        if cover._unsubscribe_auto_updater is not None:
            cover.auto_updater_hook(dt_util.utcnow())
        await hass.async_block_till_done()
        remaining -= chunk


@pytest.fixture
def no_settle_sleep():
    """Collapse the 1 s direction-change settle gap (real asyncio.sleep)."""
    with patch(
        "custom_components.cover_time_based.cover_base.sleep", new_callable=AsyncMock
    ):
        yield


@pytest.fixture
def relay_lag(request):
    """Report lag in seconds; parametrise indirectly to change it."""
    return getattr(request, "param", LAG)


@pytest.fixture
async def lagging_relays(hass, setup_input_booleans, mock_clock, relay_lag):
    relays = LaggingRelays(hass, mock_clock, lag=relay_lag)
    relays.install()
    await hass.async_block_till_done()
    return relays


@pytest.fixture
def base_options(lagging_relays):
    """Switch mode wired to the lagging relays."""
    return {
        "control_mode": "switch",
        "open_switch_entity_id": OPEN_RELAY,
        "close_switch_entity_id": CLOSE_RELAY,
        "travel_time_open": TRAVEL_TIME,
        "travel_time_close": TRAVEL_TIME,
        "endpoint_runon_time": 0,
    }


async def _run_reversal(hass, cover, mock_clock, relays):
    """50% -> set_position(80), then set_position(20) inside the lag window."""
    await cover.set_known_position(position=50)
    await hass.async_block_till_done()
    assert cover.current_cover_position == 50

    # t=0: open towards 80%. The contact closes now; HA still shows "off".
    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": "cover.test_cover", "position": 80},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert relays.physical[OPEN_RELAY] is True
    assert hass.states.get(OPEN_RELAY).state == "off", "open relay report should lag"

    # t=1: reverse to 20% while the open relay's ON report is still in flight.
    await _advance(hass, cover, mock_clock, relays, 1.0)
    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": "cover.test_cover", "position": 20},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert relays.physical[OPEN_RELAY] is False
    assert relays.physical[CLOSE_RELAY] is True, "close contact should be driving"


def _snapshot(cover, relays):
    """The three things the finding is about, read together."""
    return {
        "tracked_as_closing": cover.is_closing,
        "position": cover.current_cover_position,
        "close_contact_made": relays.physical[CLOSE_RELAY],
    }


@pytest.mark.parametrize("relay_lag", [0.0], indirect=True)
async def test_control_prompt_relay_reversal_completes(
    hass: HomeAssistant, setup_cover, mock_clock, no_settle_sleep, lagging_relays
):
    """Control: the identical sequence on a promptly-reporting relay is fine.

    Same harness, same commands, lag 0 — so a failure of the two tests below
    is the lag, not the rig.
    """
    relays = lagging_relays
    cover = _get_cover_entity(hass)

    await _run_reversal(hass, cover, mock_clock, relays)

    await _advance(hass, cover, mock_clock, relays, 2.5)
    assert _snapshot(cover, relays) == {
        "tracked_as_closing": True,
        "position": 35,
        "close_contact_made": True,
    }

    await _advance(hass, cover, mock_clock, relays, 3.0)
    assert _snapshot(cover, relays) == {
        "tracked_as_closing": False,
        "position": 20,
        "close_contact_made": False,
    }


async def test_lagging_off_echo_freezes_tracking_mid_reversal(
    hass: HomeAssistant, setup_cover, mock_clock, no_settle_sleep, lagging_relays
):
    """The previous relay's late OFF is our own echo, not an external release."""
    relays = lagging_relays
    cover = _get_cover_entity(hass)

    await _run_reversal(hass, cover, mock_clock, relays)

    # t=2: the open relay's lagged ON report arrives (pre-counted by _send_open,
    # so it is filtered). t=3: its lagged OFF report arrives — pre-counted by
    # _send_stop/_send_close from what they commanded, since HA still showed
    # the relay "off" when they ran.
    await _advance(hass, cover, mock_clock, relays, 2.5)
    assert hass.states.get(OPEN_RELAY).state == "off"

    # Mid-travel the cover is physically closing towards 20% (close contact
    # made) and should still be tracked as closing.
    assert _snapshot(cover, relays) == {
        "tracked_as_closing": True,
        "position": 35,
        "close_contact_made": True,
    }, f"relay commands so far: {relays.commands}"


async def test_lagging_off_echo_leaves_the_close_relay_latched(
    hass: HomeAssistant, setup_cover, mock_clock, no_settle_sleep, lagging_relays
):
    """The other half: nothing is left to de-energize the latched close relay."""
    relays = lagging_relays
    cover = _get_cover_entity(hass)

    await _run_reversal(hass, cover, mock_clock, relays)
    # Well past the t=5 arrival at 20%, and past every echo.
    await _advance(hass, cover, mock_clock, relays, 9.0)

    assert _snapshot(cover, relays) == {
        "tracked_as_closing": False,
        "position": 20,
        "close_contact_made": False,
    }, f"relay commands: {relays.commands}"


@pytest.mark.parametrize("relay_lag", [0.0], indirect=True)
async def test_idle_stop_before_calibration_does_not_hide_external_relay_on(
    hass: HomeAssistant, setup_cover, mock_clock, no_settle_sleep, lagging_relays
):
    """An idle stop leaves HA authoritative when a relay changes in calibration.

    The next movement must count its OFF echo and keep tracking until it
    releases the close relay at the target.
    """
    cover = _get_cover_entity(hass)
    relays = lagging_relays
    await cover.set_known_position(position=50)
    await cover.async_stop_cover()
    await hass.async_block_till_done()
    assert not cover._pending_switch

    cover._calibration = CalibrationState(attribute="travel_startup_delay", timeout=600)
    relays.physical[OPEN_RELAY] = True
    hass.states.async_set(OPEN_RELAY, "on")
    await hass.async_block_till_done()
    await cover.stop_calibration(cancel=True)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": cover.entity_id, "position": 20},
        blocking=True,
    )
    await hass.async_block_till_done()
    await _advance(hass, cover, mock_clock, relays, 0.25)
    assert cover.is_closing
    await _advance(hass, cover, mock_clock, relays, 4)
    assert not relays.physical[CLOSE_RELAY]
    assert cover.current_cover_position == 20
