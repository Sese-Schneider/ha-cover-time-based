"""Force endpoint re-drive (issue #167).

Covers with no position feedback can be moved by an external remote HA never
sees, so HA keeps believing the cover is at an endpoint. With
force_endpoint_redrive on, an open/close commanded at that believed endpoint is
re-driven for the full travel time (modeled from the opposite endpoint) instead
of being skipped as a no-op / short resync pulse.
"""

import pytest
from unittest.mock import patch

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER


@pytest.mark.asyncio
async def test_force_close_at_closed_redrives_full_travel(make_cover):
    """Switch cover believed fully closed: force-close starts a real full
    journey (is_traveling), not the skip no-op."""
    cover = make_cover()  # switch mode
    cover._force_endpoint_redrive = True
    cover.travel_calc.set_position(0)  # believed fully closed

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()

    assert cover.travel_calc.is_traveling(), "force-close must start a full journey"
    assert cover._last_command == SERVICE_CLOSE_COVER
    cover.hass.services.async_call.assert_awaited()


@pytest.mark.asyncio
async def test_force_open_at_open_redrives_full_travel(make_cover):
    """Switch cover believed fully open: force-open starts a real full journey,
    not the short resync (which does not travel)."""
    cover = make_cover()  # switch mode
    cover._force_endpoint_redrive = True
    cover.travel_calc.set_position(100)  # believed fully open

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_open_cover()

    assert cover.travel_calc.is_traveling(), "force-open must start a full journey"
    assert cover._last_command == SERVICE_OPEN_COVER
    cover.hass.services.async_call.assert_awaited()


@pytest.mark.asyncio
async def test_option_off_close_at_closed_is_noop(make_cover):
    """Regression guard: with the flag off, close at believed-0 is still the
    existing no-op (nothing sent)."""
    cover = make_cover()  # switch mode, flag off by default
    assert cover._force_endpoint_redrive is False
    cover.travel_calc.set_position(0)

    with patch.object(cover, "async_write_ha_state"):
        await cover.async_close_cover()

    assert not cover.travel_calc.is_traveling()
    cover.hass.services.async_call.assert_not_awaited()
    assert cover._last_command is None
