"""Tests for the motor overhead configuration merge.

travel_motor_overhead and tilt_motor_overhead replace the old separate
startup-delay and delay-at-end parameters. The overhead value is split
50/50 internally into startup delay and end delay.
"""

import pytest


class TestTravelMotorOverhead:
    @pytest.mark.asyncio
    async def test_overhead_splits_into_startup_and_end_delay(self, make_cover):
        cover = make_cover(travel_motor_overhead=2.0)
        assert cover._travel_startup_delay == 1.0
        assert cover._travel_delay_at_end == 1.0

    @pytest.mark.asyncio
    async def test_no_overhead_gives_no_delays(self, make_cover):
        cover = make_cover()
        assert cover._travel_startup_delay is None
        assert cover._travel_delay_at_end is None

    @pytest.mark.asyncio
    async def test_odd_overhead_splits_evenly(self, make_cover):
        cover = make_cover(travel_motor_overhead=1.5)
        assert cover._travel_startup_delay == 0.75
        assert cover._travel_delay_at_end == 0.75


class TestTiltMotorOverhead:
    @pytest.mark.asyncio
    async def test_tilt_overhead_sets_startup_delay(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0, tilt_time_up=5.0, tilt_motor_overhead=1.0
        )
        assert cover._tilt_startup_delay == 0.5

    @pytest.mark.asyncio
    async def test_no_tilt_overhead(self, make_cover):
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        assert cover._tilt_startup_delay is None


class TestMotorOverheadStoredOnInstance:
    """Verify that the overhead values are stored on the instance for state attributes."""

    @pytest.mark.asyncio
    async def test_travel_motor_overhead_stored(self, make_cover):
        cover = make_cover(travel_motor_overhead=4.0)
        assert cover._travel_motor_overhead == 4.0

    @pytest.mark.asyncio
    async def test_tilt_motor_overhead_stored(self, make_cover):
        cover = make_cover(
            tilt_time_down=5.0, tilt_time_up=5.0, tilt_motor_overhead=2.0
        )
        assert cover._tilt_motor_overhead == 2.0

    @pytest.mark.asyncio
    async def test_no_overhead_stored_as_none(self, make_cover):
        cover = make_cover()
        assert cover._travel_motor_overhead is None
        assert cover._tilt_motor_overhead is None
