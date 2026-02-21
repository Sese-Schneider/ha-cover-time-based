"""Position calculator for time-based covers.

Predicts the current position of a cover based on travel time and direction.
Uses Home Assistant convention: 0 = fully closed, 100 = fully open.

Derived from xknx.devices.TravelCalculator
(https://github.com/XKNX/xknx, MIT License).
Original convention (0=open, 100=closed) was inverted to match
Home Assistant's cover position convention (0=closed, 100=open).
"""

from __future__ import annotations

from enum import Enum
import time


class TravelStatus(Enum):
    """Enum class for travel status."""

    DIRECTION_UP = 1
    DIRECTION_DOWN = 2
    STOPPED = 3


class TravelCalculator:
    """Calculate the current position of a cover based on travel time.

    Position convention: 0 = fully closed, 100 = fully open.
    """

    __slots__ = (
        "_last_known_position",
        "_last_known_position_timestamp",
        "_position_confirmed",
        "_travel_to_position",
        "position_closed",
        "position_open",
        "travel_direction",
        "travel_time_down",
        "travel_time_up",
    )

    def __init__(self, travel_time_down: float, travel_time_up: float) -> None:
        """Initialize TravelCalculator.

        Args:
            travel_time_down: Time in seconds to travel from open to closed.
            travel_time_up: Time in seconds to travel from closed to open.
        """
        self.travel_direction = TravelStatus.STOPPED
        self.travel_time_down = travel_time_down
        self.travel_time_up = travel_time_up

        self._last_known_position: int | None = None
        self._last_known_position_timestamp: float = 0.0
        self._position_confirmed: bool = False
        self._travel_to_position: int | None = None

        # 0 is closed, 100 is fully open
        self.position_closed: int = 0
        self.position_open: int = 100

    def set_position(self, position: int) -> None:
        """Set position and target of cover."""
        self._travel_to_position = position
        self.update_position(position)

    def update_position(self, position: int) -> None:
        """Update known position of cover."""
        self._last_known_position = position
        self._last_known_position_timestamp = time.time()
        if position == self._travel_to_position:
            self._position_confirmed = True

    def stop(self) -> None:
        """Stop traveling."""
        stop_position = self.current_position()
        if stop_position is None:
            return
        self._last_known_position = stop_position
        self._travel_to_position = stop_position
        self._position_confirmed = False
        self.travel_direction = TravelStatus.STOPPED

    def start_travel(self, _travel_to_position: int, delay: float = 0.0) -> None:
        """Start traveling to position.

        Args:
            _travel_to_position: Target position.
            delay: Seconds to wait before tracking starts. Used for
                sequential multi-step movements where a pre-step (e.g. tilt)
                must complete before this calculator begins progressing.
        """
        if self._last_known_position is None:
            self.set_position(_travel_to_position)
            return
        self.stop()
        self._last_known_position_timestamp = time.time() + delay
        self._travel_to_position = _travel_to_position
        self._position_confirmed = False

        self.travel_direction = (
            TravelStatus.DIRECTION_UP
            if _travel_to_position > self._last_known_position
            else TravelStatus.DIRECTION_DOWN
        )

    def start_travel_up(self) -> None:
        """Start traveling up (opening)."""
        self.start_travel(self.position_open)

    def start_travel_down(self) -> None:
        """Start traveling down (closing)."""
        self.start_travel(self.position_closed)

    def current_position(self) -> int | None:
        """Return current (calculated or known) position."""
        if not self._position_confirmed:
            return self._calculate_position()
        return self._last_known_position

    def is_traveling(self) -> bool:
        """Return if cover is traveling."""
        return self.current_position() != self._travel_to_position

    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        return (
            self.is_traveling() and self.travel_direction == TravelStatus.DIRECTION_UP
        )

    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        return (
            self.is_traveling() and self.travel_direction == TravelStatus.DIRECTION_DOWN
        )

    def position_reached(self) -> bool:
        """Return if cover has reached designated position."""
        return self.current_position() == self._travel_to_position

    def is_open(self) -> bool:
        """Return if cover is (fully) open."""
        return self.current_position() == self.position_open

    def is_closed(self) -> bool:
        """Return if cover is (fully) closed."""
        return self.current_position() == self.position_closed

    def _calculate_position(self) -> int | None:
        """Return calculated position."""
        if self._travel_to_position is None or self._last_known_position is None:
            return self._last_known_position
        relative_position = self._travel_to_position - self._last_known_position

        def position_reached_or_exceeded(relative_position: int) -> bool:
            """Return if designated position was reached.

            DOWN means position is decreasing (e.g. 100→0). relative starts
            negative and reaches 0 (or positive if overshot) when done.
            UP means position is increasing (e.g. 0→100). relative starts
            positive and reaches 0 (or negative if overshot) when done.
            """
            return (
                relative_position >= 0
                and self.travel_direction == TravelStatus.DIRECTION_DOWN
            ) or (
                relative_position <= 0
                and self.travel_direction == TravelStatus.DIRECTION_UP
            )

        if position_reached_or_exceeded(relative_position):
            return self._travel_to_position

        remaining_travel_time = self.calculate_travel_time(
            from_position=self._last_known_position,
            to_position=self._travel_to_position,
        )
        if remaining_travel_time <= 0:
            return self._travel_to_position
        if time.time() > self._last_known_position_timestamp + remaining_travel_time:
            return self._travel_to_position

        progress = max(
            0.0,
            (time.time() - self._last_known_position_timestamp) / remaining_travel_time,
        )
        return int(self._last_known_position + relative_position * progress)

    def calculate_travel_time(self, from_position: int, to_position: int) -> float:
        """Calculate time to travel from one position to another."""
        travel_range = to_position - from_position
        # Positive range = opening (position increasing), use travel_time_up
        # Negative range = closing (position decreasing), use travel_time_down
        travel_time_full = (
            self.travel_time_up if travel_range > 0 else self.travel_time_down
        )
        return travel_time_full * abs(travel_range) / 100
