"""Position-reporting trust policy for wrapped covers (backlog 5.4).

A wrapped cover trusts the underlying entity's reports to a degree named by
one enum profile. PositionReportingPolicy states that trust as six predicates
so the decision sites in cover_wrapped.py read one policy instead of
re-deciding from four raw booleans in their own order.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import (
    DEFAULT_POSITION_REPORTING,
    POSITION_REPORTING_COMMAND_ECHO,
    POSITION_REPORTING_IGNORE_ALL,
    POSITION_REPORTING_NO_ENDPOINTS,
    POSITION_REPORTING_RELIABLE,
    POSITION_REPORTING_UNRELIABLE,
)


@dataclass(frozen=True)
class PositionReportingPolicy:
    """How far the wrapped entity's reports are trusted."""

    trusts_position_attr: bool  # read the numeric current_position attribute
    trusts_endpoint_states: bool  # trust open/closed as real endpoints
    trusts_tilt_attr: bool  # read the current_tilt_position attribute
    state_is_command: bool  # the wrapped state IS a command echo, not a reading
    ignores_all_transitions: bool  # ignore state/attribute changes entirely
    permits_native: bool  # allow native set_position / tilt forwarding


RELIABLE = PositionReportingPolicy(True, True, True, False, False, True)
UNRELIABLE = PositionReportingPolicy(False, True, False, False, False, True)
NO_ENDPOINTS = PositionReportingPolicy(True, False, True, False, False, True)
COMMAND_ECHO = PositionReportingPolicy(False, False, False, True, False, False)
IGNORE_ALL = PositionReportingPolicy(False, False, False, False, True, False)

_BY_PROFILE = {
    POSITION_REPORTING_RELIABLE: RELIABLE,
    POSITION_REPORTING_UNRELIABLE: UNRELIABLE,
    POSITION_REPORTING_NO_ENDPOINTS: NO_ENDPOINTS,
    POSITION_REPORTING_COMMAND_ECHO: COMMAND_ECHO,
    POSITION_REPORTING_IGNORE_ALL: IGNORE_ALL,
}


def from_profile(value: str | None) -> PositionReportingPolicy:
    """Return the policy for an enum value; unknown/None falls back to reliable."""
    return _BY_PROFILE.get(value or DEFAULT_POSITION_REPORTING, RELIABLE)


def from_legacy_flags(
    *,
    ignore_reported_position: bool = False,
    ignore_endpoint_states: bool = False,
    reports_command_not_endpoint: bool = False,
    ignore_all_reports: bool = False,
) -> str:
    """Collapse the four legacy booleans to one enum value.

    Precedence matches the card's positionReportingProfile():
    ignore_all > command_echo > no_endpoints > unreliable > reliable. A
    contradictory legacy combination resolves to the highest-precedence flag
    set, exactly as the card has always shown it.
    """
    if ignore_all_reports:
        return POSITION_REPORTING_IGNORE_ALL
    if reports_command_not_endpoint:
        return POSITION_REPORTING_COMMAND_ECHO
    if ignore_endpoint_states:
        return POSITION_REPORTING_NO_ENDPOINTS
    if ignore_reported_position:
        return POSITION_REPORTING_UNRELIABLE
    return POSITION_REPORTING_RELIABLE
