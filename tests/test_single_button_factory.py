"""Tests wiring the single_button control mode into the cover factory."""

from custom_components.cover_time_based.cover import _create_cover_from_options
from custom_components.cover_time_based.cover_single_button_mode import (
    SingleButtonModeCover,
)


def _base_options(**over):
    """Options dict as accepted by _create_cover_from_options.

    Mirrors the option keys used throughout tests/test_cover_factory.py:
    device_id and name are separate kwargs to the factory, not options
    entries, and CONF_* string values (e.g. "control_mode",
    "open_switch_entity_id") match the actual constants in cover.py.
    """
    opts = {
        "control_mode": "single_button",
        "open_switch_entity_id": "switch.button",
        "travel_time_open": 30,
        "travel_time_close": 30,
    }
    opts.update(over)
    return opts


def test_factory_builds_single_button_cover():
    cover = _create_cover_from_options(_base_options(), device_id="sb", name="SB")
    assert isinstance(cover, SingleButtonModeCover)


def test_factory_forces_tilt_off():
    # tilt_time_close/open must be present: _resolve_tilt_strategy short-
    # circuits to None whenever either is missing (cover.py), which would
    # make _tilt_strategy is None true for any mode and defeat this guard.
    cover = _create_cover_from_options(
        _base_options(tilt_mode="inline", tilt_time_close=5, tilt_time_open=5),
        device_id="sb",
        name="SB",
    )
    assert cover._tilt_strategy is None
    assert cover._has_tilt_support() is False
