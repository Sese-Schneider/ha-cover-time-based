"""_on_endpoint_reached hook.

A self-initiated, non-tilt travel move that terminates at a physical
endpoint (0 or 100) must fire ``_on_endpoint_reached(endpoint)``. The base
implementation is a no-op; single-button mode (a later change) overrides it
to re-anchor its internal phase tracking at the physical limit.
"""

from unittest.mock import patch

import pytest
from homeassistant.const import SERVICE_CLOSE_COVER

from custom_components.cover_time_based.cover import CONTROL_MODE_SWITCH
from custom_components.cover_time_based.cover_switch_mode import SwitchModeCover


def test_on_endpoint_reached_is_a_noop_hook():
    # CoverTimeBased itself is abstract (_send_open/_send_close/_send_stop are
    # unimplemented), so instantiate the hook via a concrete subclass instead
    # — the brief's literal `CoverTimeBased.__new__(CoverTimeBased)` raises
    # TypeError: Can't instantiate abstract class. The hook under test is
    # defined on the base class and unoverridden here, so this still exercises
    # the base no-op implementation.
    obj = SwitchModeCover.__new__(SwitchModeCover)
    # Must exist and accept an endpoint without raising or returning anything.
    assert obj._on_endpoint_reached(100) is None
    assert obj._on_endpoint_reached(0) is None


@pytest.mark.asyncio
async def test_hook_fires_at_endpoint(make_cover, monkeypatch):
    """auto_stop_if_necessary must call the hook with the reached endpoint.

    Mirrors tests/test_endpoint_self_stop.py's switch-mode endpoint setup
    (real make_cover fixture, endpoint_runon_time=0 for an immediate,
    single-branch stop) rather than the brief's ad-hoc position_reached
    monkeypatch: travel_calc.set_position(100) already makes
    position_reached() true via the real TravelCalculator, so no extra
    monkeypatching of that method is needed.
    """
    cover = make_cover(control_mode=CONTROL_MODE_SWITCH, endpoint_runon_time=0)
    seen = []
    monkeypatch.setattr(
        type(cover), "_on_endpoint_reached", lambda self, ep: seen.append(ep)
    )
    cover._self_initiated_movement = True
    cover._last_command = SERVICE_CLOSE_COVER
    cover.travel_calc.set_position(100)  # reached the open endpoint

    with patch.object(cover, "async_write_ha_state"):
        await cover.auto_stop_if_necessary()

    assert seen == [100]


@pytest.mark.asyncio
async def test_hook_does_not_fire_for_tilt_motor_settle_at_travel_endpoint(
    make_cover, monkeypatch
):
    """A dual-motor tilt-only settle must NOT fire the hook, even though the
    travel tracker happens to be parked at a physical endpoint.

    Reproduces the boundary-locked dual-motor pre-step (mirrors
    TestDualMotorTravelPreStep / test_full_lifecycle_travel_then_tilt in
    tests/test_base_movement.py): tilting requires travel to first move to
    the allowed boundary (here 0, chosen so the boundary coincides with a
    travel endpoint). _start_travel_pre_step drives travel to that boundary
    without ever setting ``_moving_tilt`` (it returns before the branch in
    _async_move_tilt_to_endpoint that would); once travel arrives,
    _start_pending_tilt sets only ``_moving_tilt_motor`` and starts the tilt
    phase. When that tilt phase later completes, auto_stop_if_necessary sees
    current_travel==0 (still parked at the boundary) and _moving_tilt==False,
    so endpoint_applies alone would be wrongly True for what is actually a
    tilt-motor-only settle — this is the exact gap the `not
    self._moving_tilt_motor` guard closes.
    """
    cover = make_cover(
        tilt_time_close=5.0,
        tilt_time_open=5.0,
        tilt_mode="dual_motor",
        tilt_open_switch="switch.tilt_open",
        tilt_close_switch="switch.tilt_close",
        tilt_stop_switch="switch.tilt_stop",
        safe_tilt_position=100,
        max_tilt_allowed_position=0,
    )
    seen = []
    monkeypatch.setattr(
        type(cover), "_on_endpoint_reached", lambda self, ep: seen.append(ep)
    )
    cover.travel_calc.set_position(50)
    cover.tilt_calc.set_position(100)

    with patch.object(cover, "async_write_ha_state"):
        # Phase 1: tilt command triggers the travel pre-step (boundary is 0).
        await cover.set_tilt_position(50)
        assert cover._pending_tilt_target == 50

        # Phase 2: travel reaches the boundary (also a travel endpoint) —
        # this takes the early "pending tilt target" return, never reaching
        # the endpoint_applies call site, and starts the tilt phase.
        cover.travel_calc.set_position(0)
        await cover.auto_stop_if_necessary()
        assert cover.tilt_calc.is_traveling()
        assert not cover._moving_tilt
        assert cover._moving_tilt_motor

        # Phase 3: tilt completes. Travel is still parked at the 0 boundary,
        # so endpoint_applies alone is True here — only the tilt-motor guard
        # prevents a false hook fire for this tilt-only settle.
        cover.tilt_calc.set_position(50)
        await cover.auto_stop_if_necessary()

    assert seen == [], (
        "a tilt-motor-only settle must not fire _on_endpoint_reached, even "
        "while travel sits parked at a physical endpoint"
    )
