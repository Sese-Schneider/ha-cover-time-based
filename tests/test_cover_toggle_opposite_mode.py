"""Tests for ToggleOppositeModeCover.

Opposite-button hardware halts a moving cover with a pulse on the OPPOSITE
direction relay (not the same one), and treats a same-direction press while
moving as a continuation. Stop therefore pulses the opposite of the last-used
direction.
"""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from custom_components.cover_time_based.cover_toggle_opposite_mode import (
    ToggleOppositeModeCover,
)
from custom_components.cover_time_based.tilt_strategies.dual_motor import (
    DualMotorTilt,
)
from tests.helpers import stub_switches


def _make_opposite_cover(
    open_switch="switch.open",
    close_switch="switch.close",
    stop_switch=None,
    tilt_open_switch=None,
    tilt_close_switch=None,
    tilt_stop_switch=None,
    relay_reports_off=True,
):
    # Tilt switches mean a dedicated tilt motor, so pair them with the
    # dual_motor strategy: an inline strategy shares the travel motor and
    # would make these covers report tilt motion as travel motion.
    tilt_time_close = 30 if tilt_open_switch or tilt_close_switch else None
    tilt_time_open = 30 if tilt_open_switch or tilt_close_switch else None
    tilt_strategy = DualMotorTilt() if tilt_open_switch or tilt_close_switch else None

    cover = ToggleOppositeModeCover(
        device_id="test_toggle_opposite",
        name="Test Toggle Opposite",
        tilt_strategy=tilt_strategy,
        travel_time_close=30,
        travel_time_open=30,
        tilt_time_close=tilt_time_close,
        tilt_time_open=tilt_time_open,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        endpoint_runon_time=None,
        min_movement_time=None,
        open_switch_entity_id=open_switch,
        close_switch_entity_id=close_switch,
        stop_switch_entity_id=stop_switch,
        tilt_open_switch=tilt_open_switch,
        tilt_close_switch=tilt_close_switch,
        tilt_stop_switch=tilt_stop_switch,
        relay_reports_off=relay_reports_off,
    )
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    created_tasks = []

    def create_task(coro):
        task = asyncio.ensure_future(coro)
        created_tasks.append(task)
        return task

    hass.async_create_task = create_task
    cover.hass = hass
    cover._test_tasks = created_tasks
    return cover


async def _cancel_tasks(cover):
    for task in cover._test_tasks:
        if not task.done():
            task.cancel()
    if cover._test_tasks:
        await asyncio.gather(*cover._test_tasks, return_exceptions=True)
    cover._test_tasks.clear()


def _calls(mock):
    return mock.call_args_list


def _ha(service, entity_id):
    return call("homeassistant", service, {"entity_id": entity_id}, False)


def _all_relays_off(cover):
    cover.hass.states.get = MagicMock(
        side_effect=lambda eid: SimpleNamespace(state="off")
    )


# The shared-motor (inline) and dual-motor cases below are built through the
# ``make_cover`` fixture so a whole config, not a hand-wired object, decides the
# tilt strategy.
SHARED_MOTOR_TILT = {
    "tilt_mode": "inline",
    "tilt_time_close": 5.0,
    "tilt_time_open": 5.0,
    "travel_time_close": 30.0,
    "travel_time_open": 30.0,
}

DUAL_MOTOR_TILT = {
    "tilt_mode": "dual_motor",
    "tilt_time_close": 5.0,
    "tilt_time_open": 5.0,
    "tilt_open_switch": "switch.tilt_open",
    "tilt_close_switch": "switch.tilt_close",
    "travel_time_close": 30.0,
    "travel_time_open": 30.0,
}


def _press(entity_id):
    """A relay rising edge, shaped like the HA state-changed event."""
    old = MagicMock()
    old.state = "off"
    old.attributes = {}
    new = MagicMock()
    new.state = "on"
    new.attributes = {}
    event = MagicMock()
    event.data = {"entity_id": entity_id, "old_state": old, "new_state": new}
    return event


def _no_settle():
    """Skip the 1s direction-change gap so the reversal path runs inline."""
    return patch(
        "custom_components.cover_time_based.cover_base.sleep", new_callable=AsyncMock
    )


def _relay_calls(cover, start=0):
    return [
        (c[0][1], c[0][2].get("entity_id"))
        for c in cover.hass.services.async_call.call_args_list[start:]
    ]


async def _start_shared_motor_tilt_close(cover):
    """Drive a tilt-close on a shared motor and return the relay-call watermark.

    Leaves travel_calc idle at 50 and tilt_calc closing. The pulse the tilt move
    emitted on switch.close is replayed so its echo counter is drained,
    otherwise a later genuine press on that relay is swallowed as our own echo.
    """
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(100)
    await cover.set_tilt_position(0)
    assert cover.tilt_calc.is_closing()
    assert not cover.travel_calc.is_traveling()
    await cover._async_switch_state_changed(_press("switch.close"))
    return len(cover.hass.services.async_call.call_args_list)


class TestOppositeSendStop:
    @pytest.mark.asyncio
    async def test_stop_after_open_pulses_close_switch(self):
        cover = _make_opposite_cover()
        _all_relays_off(cover)
        cover._last_command = SERVICE_OPEN_COVER
        await cover._send_stop()
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.close"),
        ]

    @pytest.mark.asyncio
    async def test_stop_after_close_pulses_open_switch(self):
        cover = _make_opposite_cover()
        _all_relays_off(cover)
        cover._last_command = SERVICE_CLOSE_COVER
        await cover._send_stop()
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.open"),
        ]

    @pytest.mark.asyncio
    async def test_stop_with_no_last_command_does_nothing(self):
        cover = _make_opposite_cover()
        cover._last_command = None
        await cover._send_stop()
        assert _calls(cover.hass.services.async_call) == []


class TestOppositeSendTiltStop:
    @pytest.mark.asyncio
    async def test_tilt_stop_after_open_pulses_tilt_close(self):
        cover = _make_opposite_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _all_relays_off(cover)
        cover._last_tilt_direction = "open"
        await cover._send_tilt_stop()
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.tilt_close"),
        ]
        assert cover._last_tilt_direction is None

    @pytest.mark.asyncio
    async def test_tilt_stop_after_close_pulses_tilt_open(self):
        cover = _make_opposite_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _all_relays_off(cover)
        cover._last_tilt_direction = "close"
        await cover._send_tilt_stop()
        assert _calls(cover.hass.services.async_call) == [
            _ha("turn_on", "switch.tilt_open"),
        ]
        assert cover._last_tilt_direction is None

    @pytest.mark.asyncio
    async def test_tilt_stop_no_last_direction_does_nothing(self):
        cover = _make_opposite_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        cover._last_tilt_direction = None
        await cover._send_tilt_stop()
        assert _calls(cover.hass.services.async_call) == []
        assert cover._last_tilt_direction is None


class TestOppositeExternalTravel:
    """Opposite press while moving stops; same-direction press continues."""

    @pytest.mark.asyncio
    async def test_external_close_while_opening_stops(self):
        cover = _make_opposite_cover()
        _all_relays_off(cover)
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER
        assert cover.travel_calc.is_traveling()

        cover._triggered_externally = True
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._handle_external_state_change("switch.close", "off", "on")
        finally:
            cover._triggered_externally = False

        # Motor already stopped physically; the integration only stops tracking
        # and fires NO relay of its own.
        assert not cover.travel_calc.is_traveling()
        assert cover.hass.services.async_call.await_count == 0
        await _cancel_tasks(cover)

    @pytest.mark.asyncio
    async def test_external_open_while_closing_stops(self):
        cover = _make_opposite_cover()
        _all_relays_off(cover)
        cover.travel_calc.set_position(100)
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER
        assert cover.travel_calc.is_traveling()

        cover._triggered_externally = True
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._handle_external_state_change("switch.open", "off", "on")
        finally:
            cover._triggered_externally = False

        assert not cover.travel_calc.is_traveling()
        assert cover.hass.services.async_call.await_count == 0
        await _cancel_tasks(cover)

    @pytest.mark.asyncio
    async def test_external_open_while_opening_continues(self):
        """Same-direction press while moving is a no-op continuation."""
        cover = _make_opposite_cover()
        _all_relays_off(cover)
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        cover._triggered_externally = True
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._handle_external_state_change("switch.open", "off", "on")
        finally:
            cover._triggered_externally = False

        # Still opening; no relay fired.
        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._travel_to_position == 100
        assert cover.hass.services.async_call.await_count == 0
        await _cancel_tasks(cover)

    @pytest.mark.asyncio
    async def test_external_open_when_idle_starts_opening(self):
        cover = _make_opposite_cover()
        _all_relays_off(cover)
        cover.travel_calc.set_position(0)
        assert not cover.travel_calc.is_traveling()

        cover._triggered_externally = True
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._handle_external_state_change("switch.open", "off", "on")
        finally:
            cover._triggered_externally = False

        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._travel_to_position == 100
        await _cancel_tasks(cover)

    @pytest.mark.asyncio
    async def test_external_travel_press_keys_off_travel_axis_not_tilt(self):
        """A travel press decides on travel-axis state, not conflated tilt motion.

        On a dual-motor cover a moving tilt motor makes the cover-level
        is_opening/is_closing True. A travel-relay press must NOT be read as a
        stop because of that — the travel-axis helpers reduce to travel_calc on
        this hardware. Regression guard for the tilt/travel conflation.
        """
        cover = _make_opposite_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _all_relays_off(cover)
        cover.travel_calc.set_position(50)  # travel idle
        cover.tilt_calc.set_position(0)
        cover.tilt_calc.start_travel(100)  # tilt opening
        assert not cover.travel_calc.is_traveling()
        # Cover-level property conflates in the tilt motion; the handler must not.
        assert cover.is_opening

        cover._triggered_externally = True
        try:
            with (
                patch.object(cover, "async_stop_cover", new_callable=AsyncMock) as stop,
                patch.object(
                    cover, "async_close_cover", new_callable=AsyncMock
                ) as close,
                patch.object(cover, "async_open_cover", new_callable=AsyncMock),
            ):
                # External travel-CLOSE press while travel is idle: start a close,
                # NOT a stop triggered by the moving tilt motor.
                await cover._handle_external_state_change("switch.close", "off", "on")
        finally:
            cover._triggered_externally = False

        stop.assert_not_awaited()
        close.assert_awaited_once()
        await _cancel_tasks(cover)


class TestOppositeExternalTilt:
    @pytest.mark.asyncio
    async def test_external_tilt_close_while_tilt_opening_stops(self):
        cover = _make_opposite_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _all_relays_off(cover)
        cover.tilt_calc.set_position(0)
        cover.tilt_calc.start_travel(100)  # tilt opening (UP)
        assert cover.tilt_calc.is_opening()

        cover._triggered_externally = True
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_close", "off", "on"
                )
        finally:
            cover._triggered_externally = False

        assert not cover.tilt_calc.is_traveling()
        assert cover.hass.services.async_call.await_count == 0
        await _cancel_tasks(cover)

    @pytest.mark.asyncio
    async def test_external_tilt_open_while_tilt_opening_continues(self):
        cover = _make_opposite_cover(
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
        )
        _all_relays_off(cover)
        cover.tilt_calc.set_position(0)
        cover.tilt_calc.start_travel(100)  # tilt opening (UP)
        assert cover.tilt_calc.is_opening()

        cover._triggered_externally = True
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._handle_external_tilt_state_change(
                    "switch.tilt_open", "off", "on"
                )
        finally:
            cover._triggered_externally = False

        assert cover.tilt_calc.is_traveling()
        assert cover.hass.services.async_call.await_count == 0
        await _cancel_tasks(cover)


class TestSharedMotorTiltExternalPress:
    """Shared-motor (inline) tilt phase + a physical travel-button press.

    The tilt phase IS the travel motor running, tracked on ``tilt_calc`` while
    ``travel_calc`` sits idle, so a press must be judged on the travel axis.
    """

    @pytest.mark.asyncio
    async def test_opposite_press_during_shared_motor_tilt_stops(self, make_cover):
        """The OPPOSITE button halts the motor — it must not start a travel move.

        Hardware: the cover is mid tilt-close, driven by the travel motor via
        the close relay. Pressing OPEN pulses the opposite relay, which on
        opposite-button hardware STOPS the motor. The integration must stop
        tracking and start nothing.
        """
        cover = make_cover(control_mode="toggle_opposite", **SHARED_MOTOR_TILT)
        stub_switches(cover)
        assert not cover._has_tilt_motor()

        with patch.object(cover, "async_write_ha_state"):
            watermark = await _start_shared_motor_tilt_close(cover)
            # The travel tracker is idle, so a raw travel_calc check would be
            # blind to the running motor; the axis helper is not.
            assert not cover.travel_calc.is_closing()
            assert cover._travel_axis_closing()

            with _no_settle():
                await cover._async_switch_state_changed(_press("switch.open"))

        assert _relay_calls(cover, watermark) == [], (
            "no relay should fire: the hardware already acted"
        )
        assert not cover.tilt_calc.is_traveling(), "tilt tracking must stop"
        assert not cover.travel_calc.is_traveling(), (
            "the motor was halted by the press; the integration must not animate "
            f"a travel move to {cover.travel_calc._travel_to_position}"
        )

    @pytest.mark.asyncio
    async def test_same_direction_press_during_shared_motor_tilt_continues(
        self, make_cover
    ):
        """The SAME-direction button is ignored by the hardware — a no-op.

        The motor keeps running the tilt phase and the pending tilt stop still
        applies. Converting it into a full travel close abandons that stop, so
        the shutter runs to 0 instead of parking at tilt 0.
        """
        cover = make_cover(control_mode="toggle_opposite", **SHARED_MOTOR_TILT)
        stub_switches(cover)

        with patch.object(cover, "async_write_ha_state"):
            watermark = await _start_shared_motor_tilt_close(cover)
            with _no_settle():
                await cover._async_switch_state_changed(_press("switch.close"))

        assert _relay_calls(cover, watermark) == []
        assert not cover.travel_calc.is_traveling(), (
            "a same-direction press is a continuation; travel must not start "
            f"(travelling to {cover.travel_calc._travel_to_position})"
        )
        assert cover.tilt_calc.is_traveling(), "the tilt phase keeps running"

    @pytest.mark.asyncio
    async def test_opposite_press_during_shared_motor_tilt_takes_the_stop_path(
        self, make_cover, caplog
    ):
        """The press is routed to the stop branch, not through the reversal guard.

        Reaching ``async_open_cover`` and relying on the base reversal guard is
        not equivalent: that guard turns the press into stop-settle-reverse and
        suppresses the relay command (the trigger is external), leaving the
        motor stationary while travel_calc animates 50 -> 100.
        """
        caplog.set_level(logging.DEBUG)
        cover = make_cover(control_mode="toggle_opposite", **SHARED_MOTOR_TILT)
        stub_switches(cover)

        with patch.object(cover, "async_write_ha_state"):
            await _start_shared_motor_tilt_close(cover)
            caplog.clear()
            with _no_settle():
                await cover._async_switch_state_changed(_press("switch.open"))

        messages = [r.getMessage() for r in caplog.records]
        assert any("open press while closing, stopping" in m for m in messages), (
            messages
        )
        assert not any("external open press" in m for m in messages), messages
        assert not cover.travel_calc.is_traveling()


class TestDualMotorUnaffected:
    """Dual motor keeps its current behaviour: the helpers reduce to travel_calc."""

    @pytest.mark.parametrize("relay", ["switch.open", "switch.close"])
    @pytest.mark.asyncio
    async def test_travel_press_during_tilt_motor_move_starts_travel(
        self, make_cover, relay
    ):
        """A dedicated tilt motor moves independently, so a travel press starts
        travel — and _travel_axis_* agrees with raw travel_calc here, so the
        handler keying off the helpers changes nothing on this hardware.
        """
        cover = make_cover(control_mode="toggle_opposite", **DUAL_MOTOR_TILT)
        stub_switches(cover)
        assert cover._has_tilt_motor()
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_tilt_position(0)
            assert cover.tilt_calc.is_closing()
            assert not cover.travel_calc.is_traveling()
            # The two checks agree, unlike on a shared motor.
            assert cover._travel_axis_closing() == cover.travel_calc.is_closing()
            assert cover._travel_axis_opening() == cover.travel_calc.is_opening()

            with _no_settle():
                await cover._async_switch_state_changed(_press(relay))

        assert cover.travel_calc.is_traveling()
        assert cover.travel_calc._travel_to_position == (
            100 if relay == "switch.open" else 0
        )
        assert cover.tilt_calc.is_traveling(), "the tilt motor keeps its own move"

    @pytest.mark.asyncio
    async def test_press_during_tilt_to_safe_pre_step_starts_travel(
        self, make_cover, caplog
    ):
        """A press during the tilt-to-safe pre-step starts the idle travel motor.

        The pre-step runs the tilt motor while a travel command sits pending,
        so the travel motor is stationary — and on opposite-button hardware a
        press against a stationary motor STARTS it. Reading the pending travel
        direction as motion would track a stop for a press that is really a
        move (the base ``_travel_axis_*`` helpers do fold that pending
        direction in, which is why this handler must not use them here).

        The pressed direction lands as a re-planned pending travel rather than
        as travel_calc motion: a dual-motor cover parks its slats at the safe
        position before travelling, so the reversal re-queues the pre-step.
        The stop path is unmistakably different — it clears the pending travel
        and halts tilt tracking.
        """
        caplog.set_level(logging.DEBUG)
        cover = make_cover(control_mode="toggle_opposite", **DUAL_MOTOR_TILT)
        stub_switches(cover)
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)  # off the safe position -> pre-step planned

        with patch.object(cover, "async_write_ha_state"):
            await cover.set_position(0)  # close, behind a tilt-to-safe pre-step
            assert cover._pending_travel_target == 0
            assert not cover.travel_calc.is_traveling(), "travel motor idle"
            assert cover.tilt_calc.is_traveling(), "the tilt motor runs the pre-step"
            # The base helper reports the pending close; the motor is not moving.
            assert cover._travel_axis_closing()
            assert not cover._motor_closing()

            caplog.clear()
            with _no_settle():
                await cover._async_switch_state_changed(_press("switch.open"))

        messages = [r.getMessage() for r in caplog.records]
        assert any("external open press" in m for m in messages), messages
        assert not any("open press while closing, stopping" in m for m in messages), (
            messages
        )
        assert cover._pending_travel_target == 100, (
            "the press started the stationary motor; the open move must be tracked, "
            "not discarded by a stop"
        )
        assert cover._pending_travel_command == SERVICE_OPEN_COVER
        assert cover.tilt_calc.is_traveling(), (
            "the tilt-to-safe pre-step is re-planned, not halted as it is on a stop"
        )


class TestToggleModeContrast:
    """ToggleModeCover already keys off the travel axis."""

    @pytest.mark.asyncio
    async def test_same_button_press_during_shared_motor_tilt_stops(self, make_cover):
        """On same-button hardware the stop press is the CLOSE button during a
        close-direction motion. ToggleModeCover's _travel_axis_closing() sees
        the shared-motor tilt phase and stops — the behaviour toggle_opposite
        used to miss for its own stop press.
        """
        cover = make_cover(control_mode="toggle", **SHARED_MOTOR_TILT)
        stub_switches(cover)

        with patch.object(cover, "async_write_ha_state"):
            watermark = await _start_shared_motor_tilt_close(cover)
            with _no_settle():
                await cover._async_switch_state_changed(_press("switch.close"))

        assert _relay_calls(cover, watermark) == []
        assert not cover.tilt_calc.is_traveling()
        assert not cover.travel_calc.is_traveling()
