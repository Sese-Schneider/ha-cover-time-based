"""Position-reporting trust policy for wrapped covers.

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
    state_is_command: bool  # the wrapped state IS a command echo, not a reading
    ignores_all_transitions: bool  # ignore state/attribute changes entirely

    @property
    def trusts_tilt_attr(self) -> bool:
        # Tilt reports are trusted exactly when the position attribute is:
        # a device whose position number is untrustworthy is untrustworthy on tilt too.
        return self.trusts_position_attr

    @property
    def permits_native(self) -> bool:
        # Native set_position/tilt forwarding is unsafe when the wrapped state is a
        # command echo or all reports are ignored.
        return not (self.state_is_command or self.ignores_all_transitions)


RELIABLE = PositionReportingPolicy(True, True, False, False)
UNRELIABLE = PositionReportingPolicy(False, True, False, False)
NO_ENDPOINTS = PositionReportingPolicy(True, False, False, False)
COMMAND_ECHO = PositionReportingPolicy(False, False, True, False)
IGNORE_ALL = PositionReportingPolicy(False, False, False, True)

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
    # Precedence is lossy only for multi-flag combinations. The sole combo any
    # shipped UI could persist, ignore_reported_position + reports_command_not_endpoint
    # (both pre-#239 separate options), collapses to command_echo and is
    # behaviour-preserving. The other multi-flag combos were never co-settable:
    # ignore_endpoint_states (#239) and ignore_all_reports (#248) each shipped
    # dropdown-only, with no YAML surface.
    if ignore_all_reports:
        return POSITION_REPORTING_IGNORE_ALL
    if reports_command_not_endpoint:
        return POSITION_REPORTING_COMMAND_ECHO
    if ignore_endpoint_states:
        return POSITION_REPORTING_NO_ENDPOINTS
    if ignore_reported_position:
        return POSITION_REPORTING_UNRELIABLE
    return POSITION_REPORTING_RELIABLE
