"""_on_endpoint_reached hook.

A self-initiated, non-tilt travel move that terminates at a physical
endpoint (0 or 100) must fire ``_on_endpoint_reached(endpoint)``. The base
implementation is a no-op; single-button mode (a later change) overrides it
to re-anchor its internal phase tracking at the physical limit.
"""

from unittest.mock import AsyncMock, patch

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
