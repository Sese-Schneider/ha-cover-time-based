"""Tests for rejecting commands / marking unavailable when targets are unavailable."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError

from custom_components.cover_time_based.cover import (
    CONTROL_MODE_SWITCH,
)


def _set_target_states(cover, mapping):
    """Make cover.hass.states.get return per-entity states.

    mapping: {entity_id: state_string or None}. None => entity missing.
    Any entity not in mapping returns a default 'on' state (available).
    """

    def _get(entity_id):
        if entity_id in mapping:
            value = mapping[entity_id]
            if value is None:
                return None
            st = MagicMock()
            st.state = value
            return st
        st = MagicMock()
        st.state = "on"
        return st

    cover.hass.states.get = MagicMock(side_effect=_get)


def _make_state_event(entity_id, old_state, new_state):
    """Build a HA-style state-change event (old/new states may be None)."""
    old = None
    if old_state is not None:
        old = MagicMock()
        old.state = old_state
        old.attributes = {}
    new = None
    if new_state is not None:
        new = MagicMock()
        new.state = new_state
        new.attributes = {}
    event = MagicMock()
    event.data = {"entity_id": entity_id, "old_state": old, "new_state": new}
    return event


class TestEntityUnavailableHelper:
    def test_none_state_is_unavailable(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        assert cover._entity_unavailable(None) is True

    def test_unavailable_state_is_unavailable(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        st = MagicMock()
        st.state = STATE_UNAVAILABLE
        assert cover._entity_unavailable(st) is True

    def test_unknown_state_is_available(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        st = MagicMock()
        st.state = STATE_UNKNOWN
        assert cover._entity_unavailable(st) is False

    def test_on_state_is_available(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        st = MagicMock()
        st.state = "on"
        assert cover._entity_unavailable(st) is False


class TestUnavailableTargetHelpers:
    def test_target_entity_ids_lists_configured_switches(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_SWITCH,
            open_switch="switch.open",
            close_switch="switch.close",
            stop_switch="switch.stop",
        )
        assert set(cover._target_entity_ids()) == {
            "switch.open",
            "switch.close",
            "switch.stop",
        }

    def test_target_entity_ids_for_wrapped_includes_cover(self, make_cover):
        cover = make_cover(cover_entity_id="cover.real")
        assert cover._target_entity_ids() == ["cover.real"]

    def test_any_target_unavailable_flags_unavailable_state(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        _set_target_states(cover, {"switch.open": STATE_UNAVAILABLE})
        assert cover._any_target_unavailable() is True

    def test_any_target_unavailable_flags_missing_entity(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        _set_target_states(cover, {"switch.close": None})
        assert cover._any_target_unavailable() is True

    def test_any_target_unavailable_ignores_unknown(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        _set_target_states(cover, {"switch.open": STATE_UNKNOWN})
        assert cover._any_target_unavailable() is False

    def test_any_target_unavailable_false_when_all_available(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        _set_target_states(cover, {})
        assert cover._any_target_unavailable() is False


class TestAvailableProperty:
    def test_available_true_when_targets_present(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        _set_target_states(cover, {})
        assert cover.available is True

    def test_available_false_when_target_unavailable(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        _set_target_states(cover, {"switch.open": STATE_UNAVAILABLE})
        assert cover.available is False

    def test_available_false_when_target_missing(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        _set_target_states(cover, {"switch.open": None})
        assert cover.available is False

    def test_available_true_when_target_unknown(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        _set_target_states(cover, {"switch.open": STATE_UNKNOWN})
        assert cover.available is True

    def test_available_false_for_wrapped_when_cover_unavailable(self, make_cover):
        cover = make_cover(cover_entity_id="cover.real")
        _set_target_states(cover, {"cover.real": STATE_UNAVAILABLE})
        assert cover.available is False


class TestExternalTriggerNotGatedByUnavailableTarget:
    """Event-driven re-entry (physical switch reactions) must NOT be blocked by
    the unavailable-target gate — only direct service calls are rejected.
    Otherwise a legitimate stop/track is aborted and the tracker desyncs."""

    @pytest.mark.asyncio
    async def test_external_stop_not_blocked_when_other_target_unavailable(
        self, make_cover
    ):
        cover = make_cover(
            control_mode=CONTROL_MODE_SWITCH,
            open_switch="switch.open",
            close_switch="switch.close",
        )
        # close switch is dead, but the open relay is physically operating
        _set_target_states(cover, {"switch.close": STATE_UNAVAILABLE})
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel_down()
        # open relay releasing (on->off) = physical stop in latching mode
        event = _make_state_event("switch.open", "on", "off")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_switch_state_changed(event)  # must NOT raise
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_external_open_not_blocked_when_other_target_unavailable(
        self, make_cover
    ):
        cover = make_cover(
            control_mode=CONTROL_MODE_SWITCH,
            open_switch="switch.open",
            close_switch="switch.close",
        )
        _set_target_states(cover, {"switch.close": STATE_UNAVAILABLE})
        cover.travel_calc.set_position(0)
        # open relay engaging (off->on) = physical open in latching mode
        event = _make_state_event("switch.open", "off", "on")
        with patch.object(cover, "async_write_ha_state"):
            await cover._async_switch_state_changed(event)  # must NOT raise
        assert cover.travel_calc.is_traveling()


class TestAvailabilityPush:
    @pytest.mark.asyncio
    async def test_write_state_when_target_becomes_unavailable(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        event = _make_state_event("switch.open", "off", STATE_UNAVAILABLE)
        with patch.object(cover, "async_write_ha_state") as write:
            await cover._async_switch_state_changed(event)
        write.assert_called()

    @pytest.mark.asyncio
    async def test_write_state_when_target_recovers(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        event = _make_state_event("switch.open", STATE_UNAVAILABLE, "off")
        with patch.object(cover, "async_write_ha_state") as write:
            await cover._async_switch_state_changed(event)
        write.assert_called()

    @pytest.mark.asyncio
    async def test_write_state_when_target_removed(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        event = _make_state_event("switch.open", "off", None)
        with patch.object(cover, "async_write_ha_state") as write:
            await cover._async_switch_state_changed(event)
        write.assert_called()


class TestMovementStartGating:
    @pytest.mark.asyncio
    async def test_open_raises_when_open_target_unavailable(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        _set_target_states(cover, {"switch.open": STATE_UNAVAILABLE})
        cover.travel_calc.set_position(0)
        with (
            patch.object(cover, "async_write_ha_state"),
            pytest.raises(HomeAssistantError),
        ):
            await cover.async_open_cover()
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_open_allowed_when_only_close_target_unavailable(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        _set_target_states(cover, {"switch.close": STATE_UNAVAILABLE})
        cover.travel_calc.set_position(0)
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()  # open target fine → must NOT raise
        assert cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_close_raises_when_close_target_unavailable(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        _set_target_states(cover, {"switch.close": STATE_UNAVAILABLE})
        cover.travel_calc.set_position(100)
        with (
            patch.object(cover, "async_write_ha_state"),
            pytest.raises(HomeAssistantError),
        ):
            await cover.async_close_cover()
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_stop_never_gated(self, make_cover):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        _set_target_states(
            cover,
            {"switch.open": STATE_UNAVAILABLE, "switch.close": STATE_UNAVAILABLE},
        )
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel(100)  # opening
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()  # must NOT raise
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_in_motion_open_resolves_to_stop_even_if_open_target_unavailable(
        self, make_cover
    ):
        cover = make_cover(open_switch="switch.open", close_switch="switch.close")
        _set_target_states(cover, {"switch.open": STATE_UNAVAILABLE})
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel(100)  # opening
        assert cover.is_opening
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover()  # in-motion open == stop; must NOT raise
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_external_open_not_gated(self, make_cover):
        cover = make_cover(
            control_mode=CONTROL_MODE_SWITCH,
            open_switch="switch.open",
            close_switch="switch.close",
        )
        _set_target_states(cover, {"switch.open": STATE_UNAVAILABLE})
        cover.travel_calc.set_position(0)
        cover._triggered_externally = True
        try:
            with patch.object(cover, "async_write_ha_state"):
                await cover._async_move_to_endpoint(target=100)  # external → not gated
        finally:
            cover._triggered_externally = False
        assert cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_wrapped_open_raises_when_cover_unavailable(self, make_cover):
        cover = make_cover(cover_entity_id="cover.real")
        _set_target_states(cover, {"cover.real": STATE_UNAVAILABLE})
        cover.travel_calc.set_position(0)
        with (
            patch.object(cover, "async_write_ha_state"),
            pytest.raises(HomeAssistantError),
        ):
            await cover.async_open_cover()
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_wrapped_stop_not_gated(self, make_cover):
        cover = make_cover(cover_entity_id="cover.real")
        _set_target_states(cover, {"cover.real": STATE_UNAVAILABLE})
        cover.travel_calc.set_position(50)
        cover.travel_calc.start_travel(100)
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_stop_cover()  # must NOT raise
        assert not cover.travel_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_open_raises_when_tilt_open_target_unavailable(self, make_cover):
        cover = make_cover(
            open_switch="switch.open",
            close_switch="switch.close",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_mode="dual_motor",
            tilt_time_open=5,
            tilt_time_close=5,
        )
        _set_target_states(cover, {"switch.tilt_open": STATE_UNAVAILABLE})
        cover.tilt_calc.set_position(0)
        with (
            patch.object(cover, "async_write_ha_state"),
            pytest.raises(HomeAssistantError),
        ):
            await cover.async_open_cover_tilt()
        assert not cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_open_allowed_when_only_tilt_close_unavailable(self, make_cover):
        cover = make_cover(
            open_switch="switch.open",
            close_switch="switch.close",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_mode="dual_motor",
            tilt_time_open=5,
            tilt_time_close=5,
        )
        _set_target_states(cover, {"switch.tilt_close": STATE_UNAVAILABLE})
        cover.tilt_calc.set_position(0)
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_open_cover_tilt()  # tilt_open fine → must NOT raise
        assert cover.tilt_calc.is_traveling()


class TestSequentialOpenTiltGating:
    """sequential_open inverts tilt_command_for: closing the tilt drives the
    OPEN travel switch. The gate must key off the actual command, not `closing`.
    """

    def _make(self, make_cover):
        return make_cover(
            open_switch="switch.open",
            close_switch="switch.close",
            tilt_mode="sequential_open",
            tilt_time_open=5,
            tilt_time_close=5,
        )

    @pytest.mark.asyncio
    async def test_tilt_close_raises_when_open_switch_unavailable(self, make_cover):
        # tilt-close fires OPEN (inverted) → gate must check switch.open
        cover = self._make(make_cover)
        _set_target_states(cover, {"switch.open": STATE_UNAVAILABLE})
        cover.tilt_calc.set_position(100)
        with (
            patch.object(cover, "async_write_ha_state"),
            pytest.raises(HomeAssistantError),
        ):
            await cover.async_close_cover_tilt()
        assert not cover.tilt_calc.is_traveling()

    @pytest.mark.asyncio
    async def test_tilt_close_allowed_when_only_close_switch_unavailable(
        self, make_cover
    ):
        # tilt-close fires OPEN; the CLOSE switch being dead must NOT block it
        cover = self._make(make_cover)
        _set_target_states(cover, {"switch.close": STATE_UNAVAILABLE})
        cover.tilt_calc.set_position(100)
        with patch.object(cover, "async_write_ha_state"):
            await cover.async_close_cover_tilt()  # must NOT raise
        assert cover.tilt_calc.is_traveling()


class TestPreStepGating:
    """Dual-motor pre-step paths must honour the movement-target gate.

    These exercise the two cases the per-direction gate could be bypassed by
    a pre-step that starts a relay before the gate is reached.
    """

    # GAP 1: dual-motor travel that needs a tilt pre-step must check the tilt target
    @pytest.mark.asyncio
    async def test_travel_with_tilt_prestep_raises_when_tilt_target_unavailable(
        self, make_cover
    ):
        cover = make_cover(
            open_switch="switch.open",
            close_switch="switch.close",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_mode="dual_motor",
            tilt_time_open=5,
            tilt_time_close=5,
        )
        # safe_tilt_position defaults to 100. Tilt at 30 (not safe) + a real
        # travel move (50 -> 100) forces the dual-motor tilt-to-safe pre-step:
        # _plan_tilt_for_travel appends TiltTo(100) and starts _start_tilt_pre_step.
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(30)
        # Tilt opens 30 -> 100, so the gated tilt target is switch.tilt_open;
        # kill both tilt switches. Travel targets stay available.
        _set_target_states(
            cover,
            {
                "switch.tilt_open": STATE_UNAVAILABLE,
                "switch.tilt_close": STATE_UNAVAILABLE,
            },
        )
        with (
            patch.object(cover, "async_write_ha_state"),
            pytest.raises(HomeAssistantError),
        ):
            await cover.async_open_cover()
        assert not cover.tilt_calc.is_traveling()
        assert not cover.travel_calc.is_traveling()

    # GAP 1b: same path must also check the travel target up front
    @pytest.mark.asyncio
    async def test_travel_with_tilt_prestep_raises_when_travel_target_unavailable(
        self, make_cover
    ):
        cover = make_cover(
            open_switch="switch.open",
            close_switch="switch.close",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_mode="dual_motor",
            tilt_time_open=5,
            tilt_time_close=5,
        )
        # Same tilt pre-step trigger as above (tilt 30 -> safe 100, travel 50 -> 100).
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(30)
        # Tilt targets fine; the OPEN travel relay (fired after the pre-step) is dead.
        _set_target_states(cover, {"switch.open": STATE_UNAVAILABLE})
        with (
            patch.object(cover, "async_write_ha_state"),
            pytest.raises(HomeAssistantError),
        ):
            await cover.async_open_cover()
        assert not cover.tilt_calc.is_traveling()
        assert not cover.travel_calc.is_traveling()

    # GAP 2: dual-motor tilt that needs a travel pre-step must check the travel target
    @pytest.mark.asyncio
    async def test_tilt_with_travel_prestep_raises_when_travel_target_unavailable(
        self, make_cover
    ):
        cover = make_cover(
            open_switch="switch.open",
            close_switch="switch.close",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            tilt_stop_switch="switch.tilt_stop",
            tilt_mode="dual_motor",
            tilt_time_open=5,
            tilt_time_close=5,
            safe_tilt_position=100,
            max_tilt_allowed_position=0,
        )
        # Travel at 50 (above max_tilt_allowed_position=0) forces the travel
        # pre-step: plan_move_tilt appends TravelTo(0) before TiltTo, and
        # _start_travel_pre_step closes the cover to 0 first.
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)
        # Tilt targets fine; both travel relays dead (travel pre-step closes -> switch.close).
        _set_target_states(
            cover,
            {
                "switch.open": STATE_UNAVAILABLE,
                "switch.close": STATE_UNAVAILABLE,
            },
        )
        with (
            patch.object(cover, "async_write_ha_state"),
            pytest.raises(HomeAssistantError),
        ):
            await cover.async_set_cover_tilt_position(tilt_position=50)
        assert not cover.travel_calc.is_traveling()
        assert not cover.tilt_calc.is_traveling()
