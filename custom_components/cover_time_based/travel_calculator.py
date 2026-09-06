"""Position calculator for time-based covers.

Predicts the current position of a cover based on travel time and direction.
Uses Home Assistant convention: 0 = fully closed, 100 = fully open.

Derived from xknx.devices.TravelCalculator
(https://github.com/XKNX/xknx, MIT License).
Original convention (0=open, 100=closed) was inverted to match
Home Assistant's cover position convention (0=closed, 100=open).
"""

from __future__ import annotations

import logging
import time
from enum import Enum

_LOGGER = logging.getLogger(__name__)


class TravelStatus(Enum):
    """Enum class for travel status."""

    DIRECTION_UP = 1
    DIRECTION_DOWN = 2
    STOPPED = 3


class TravelCalculator:
    """Calculate the current position of a cover based on travel time.

    Timestamps are time.monotonic() readings: a wall-clock step mid-travel must not move the tracker.

    Position convention: 0 = fully closed, 100 = fully open.
    """

    __slots__ = (
        "_last_known_position",
        "_last_known_position_timestamp",
        "_name",
        "_position_confirmed",
        "_travel_to_position",
        "position_closed",
        "position_open",
        "travel_direction",
        "travel_time_down",
        "travel_time_up",
    )

    def __init__(
        self, travel_time_down: float, travel_time_up: float, name: str = ""
    ) -> None:
        """Initialize TravelCalculator.

        Args:
            travel_time_down: Time in seconds to travel from open to closed.
            travel_time_up: Time in seconds to travel from closed to open.
            name: Label used only in debug logs to tell the travel and tilt
                calculators apart (issue #231 diagnostics).
        """
        self._name = name
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

    def _log_state(self, action: str) -> None:
        """Debug-log an anchor mutation so the position timeline is traceable.

        The tracked position is derived entirely from ``_last_known_position``,
        ``_travel_to_position`` and ``_last_known_position_timestamp``; logging
        every change to them makes an out-of-sync jump (e.g. the anchor snapping
        back to an earlier position, issue #231) visible in the log.
        """
        if not _LOGGER.isEnabledFor(logging.DEBUG):
            return
        _LOGGER.debug(
            "TravelCalculator[%s] %s :: known=%s target=%s ts=%.3f confirmed=%s dir=%s",
            self._name,
            action,
            self._last_known_position,
            self._travel_to_position,
            self._last_known_position_timestamp,
            self._position_confirmed,
            self.travel_direction.name,
        )

    def set_position(self, position: int) -> None:
        """Set position and target of cover."""
        self._travel_to_position = position
        self.update_position(position)

    def update_position(self, position: int) -> None:
        """Update known position of cover."""
        self._last_known_position = position
        self._last_known_position_timestamp = time.monotonic()
        if position == self._travel_to_position:
            self._position_confirmed = True
        self._log_state("update_position")

    def clear_position(self) -> None:
        """Clear position to unknown (e.g. after external movement)."""
        self._last_known_position = None
        self._travel_to_position = None
        self._position_confirmed = False
        self.travel_direction = TravelStatus.STOPPED
        self._log_state("clear_position")

    def snapshot(self) -> tuple:
        """Capture the mutable tracker state for exception-safe rollback.

        Restore with :meth:`restore`. Used where a mutation must be undone if a
        later step in the same operation raises (e.g. a forced redrive seeds the
        opposite endpoint before driving relays that may fail).
        """
        return (
            self._last_known_position,
            self._last_known_position_timestamp,
            self._position_confirmed,
            self._travel_to_position,
            self.travel_direction,
        )

    def restore(self, snapshot: tuple) -> None:
        """Restore state captured by :meth:`snapshot`."""
        (
            self._last_known_position,
            self._last_known_position_timestamp,
            self._position_confirmed,
            self._travel_to_position,
            self.travel_direction,
        ) = snapshot
        self._log_state("restore")

    def stop(self) -> None:
        """Stop traveling."""
        stop_position = self.current_position()
        if stop_position is None:
            return
        self._last_known_position = stop_position
        self._travel_to_position = stop_position
        self._position_confirmed = False
        self.travel_direction = TravelStatus.STOPPED
        self._log_state("stop")

    def start_travel(
        self,
        _travel_to_position: int,
        *,
        delay: float = 0.0,
        base_monotonic: float | None = None,
    ) -> None:
        """Start traveling to position.

        Args:
            _travel_to_position: Target position.
            delay: Seconds to wait before tracking starts. Used for
                sequential multi-step movements where a pre-step (e.g. tilt)
                must complete before this calculator begins progressing.
            ``base_monotonic``: a ``time.monotonic()`` reading the move actually
                began at, instead of now. Relay-feedback timing passes the relay's
                confirmation instant so the command-to-echo gap falls outside
                the tracked travel.
        """
        if self._last_known_position is None:
            self.set_position(_travel_to_position)
            return
        self.stop()
        base = time.monotonic() if base_monotonic is None else base_monotonic
        self._last_known_position_timestamp = base + delay
        self._travel_to_position = _travel_to_position
        self._position_confirmed = False

        self.travel_direction = (
            TravelStatus.DIRECTION_UP
            if _travel_to_position > self._last_known_position
            else TravelStatus.DIRECTION_DOWN
        )
        self._log_state(f"start_travel(target={_travel_to_position}, delay={delay})")

    def start_travel_up(self) -> None:
        """Start traveling up (opening)."""
        self.start_travel(self.position_open)

    def start_travel_down(self) -> None:
        """Start traveling down (closing)."""
        self.start_travel(self.position_closed)

    def current_position(self) -> int | None:
        """Return current (calculated or known) position.

        While a move is in flight, the calculated position never equals the
        target until the travel time has elapsed; position_reached,
        is_traveling, is_open, is_closed and external `== target` checks rely
        on this.
        """
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

    def position_reached(self, current: int | None = None) -> bool:
        """Return if cover has reached designated position.

        ``current`` lets a caller that already computed the position (the
        auto-updater tick) pass it in rather than recalculating it.
        """
        current = self.current_position() if current is None else current
        return current == self._travel_to_position

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
        now = time.monotonic()
        if now >= self._last_known_position_timestamp + remaining_travel_time:
            return self._travel_to_position

        progress = max(
            0.0,
            (now - self._last_known_position_timestamp) / remaining_travel_time,
        )
        position = round(self._last_known_position + relative_position * progress)
        # Arrival is the time check above, never rounding: hold one step short of the
        # target so position_reached()/is_traveling()/stop() and external `== target`
        # checks cannot call the move done while the motor is still running.
        if position == self._travel_to_position:
            position = self._travel_to_position - (1 if relative_position > 0 else -1)
        return position

    def calculate_travel_time(self, from_position: int, to_position: int) -> float:
        """Calculate time to travel from one position to another."""
        travel_range = to_position - from_position
        # Positive range = opening (position increasing), use travel_time_up
        # Negative range = closing (position decreasing), use travel_time_down
        travel_time_full = (
            self.travel_time_up if travel_range > 0 else self.travel_time_down
        )
        return travel_time_full * abs(travel_range) / 100
