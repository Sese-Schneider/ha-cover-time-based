"""Unit tests for the position-reporting policy (backlog 5.4)."""

from dataclasses import FrozenInstanceError

import pytest

from custom_components.cover_time_based import position_reporting as pr
from custom_components.cover_time_based.position_reporting import (
    PositionReportingPolicy,
)

# profile value -> the six predicates, in field order.
EXPECTED = {
    "reliable": (True, True, True, False, False, True),
    "unreliable": (False, True, False, False, False, True),
    "no_endpoints": (True, False, True, False, False, True),
    "command_echo": (False, False, False, True, False, False),
    "ignore_all": (False, False, False, False, True, False),
}


def _as_tuple(p: PositionReportingPolicy):
    return (
        p.trusts_position_attr,
        p.trusts_endpoint_states,
        p.trusts_tilt_attr,
        p.state_is_command,
        p.ignores_all_transitions,
        p.permits_native,
    )


@pytest.mark.parametrize("value,expected", EXPECTED.items())
def test_from_profile_predicate_table(value, expected):
    assert _as_tuple(pr.from_profile(value)) == expected


def test_from_profile_defaults_to_reliable():
    assert pr.from_profile(None) is pr.RELIABLE
    assert pr.from_profile("nonsense") is pr.RELIABLE


def test_from_legacy_flags_single_flags():
    assert pr.from_legacy_flags() == "reliable"
    assert pr.from_legacy_flags(ignore_reported_position=True) == "unreliable"
    assert pr.from_legacy_flags(ignore_endpoint_states=True) == "no_endpoints"
    assert pr.from_legacy_flags(reports_command_not_endpoint=True) == "command_echo"
    assert pr.from_legacy_flags(ignore_all_reports=True) == "ignore_all"


def test_from_legacy_flags_precedence():
    # ignore_all beats everything; command_echo beats no_endpoints/unreliable.
    assert (
        pr.from_legacy_flags(
            ignore_all_reports=True, reports_command_not_endpoint=True
        )
        == "ignore_all"
    )
    assert (
        pr.from_legacy_flags(
            reports_command_not_endpoint=True, ignore_reported_position=True
        )
        == "command_echo"
    )
    assert (
        pr.from_legacy_flags(
            ignore_endpoint_states=True, ignore_reported_position=True
        )
        == "no_endpoints"
    )


def test_policy_is_frozen():
    with pytest.raises(FrozenInstanceError):
        pr.RELIABLE.permits_native = False  # type: ignore[misc]
