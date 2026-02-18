"""Tests for the startup delay and endpoint runon time configuration.

travel_startup_delay, tilt_startup_delay, and endpoint_runon_time are
standalone config values that map directly to internal delay attributes.
"""

import pytest


class TestTravelStartupDelay:
    @pytest.mark.asyncio
    async def test_startup_delay_stored_directly(self, make_cover):
        cover = make_cover(travel_startup_delay=2.0)
        assert cover._travel_startup_delay == 2.0

    @pytest.mark.asyncio
    async def test_no_startup_delay_gives_none(self, make_cover):
        cover = make_cover()
        assert cover._travel_startup_delay is None

    @pytest.mark.asyncio
    async def test_endpoint_runon_time_stored_directly(self, make_cover):
        cover = make_cover(endpoint_runon_time=1.5)
        assert cover._endpoint_runon_time == 1.5

    @pytest.mark.asyncio
    async def test_no_endpoint_runon_time_gives_none(self, make_cover):
        cover = make_cover()
        assert cover._endpoint_runon_time is None


class TestTiltStartupDelay:
    @pytest.mark.asyncio
    async def test_tilt_startup_delay_stored_directly(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0, tilt_startup_delay=1.0)
        assert cover._tilt_startup_delay == 1.0

    @pytest.mark.asyncio
    async def test_no_tilt_startup_delay(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        assert cover._tilt_startup_delay is None


class TestDelayValuesStoredOnInstance:
    """Verify that the delay values are stored on the instance for state attributes."""

    @pytest.mark.asyncio
    async def test_travel_startup_delay_stored(self, make_cover):
        cover = make_cover(travel_startup_delay=4.0)
        assert cover._travel_startup_delay == 4.0

    @pytest.mark.asyncio
    async def test_tilt_startup_delay_stored(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0, tilt_startup_delay=2.0)
        assert cover._tilt_startup_delay == 2.0

    @pytest.mark.asyncio
    async def test_endpoint_runon_time_stored(self, make_cover):
        cover = make_cover(endpoint_runon_time=1.0)
        assert cover._endpoint_runon_time == 1.0

    @pytest.mark.asyncio
    async def test_no_delays_stored_as_none(self, make_cover):
        cover = make_cover()
        assert cover._travel_startup_delay is None
        assert cover._tilt_startup_delay is None
        assert cover._endpoint_runon_time is None
