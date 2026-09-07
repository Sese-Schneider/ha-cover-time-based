"""The shared ``_CoverHost`` typing surface must stay typing-only.

The movement, lifecycle, calibration and switch-echo mixins declare the members
of ``CoverTimeBased`` they borrow via a single ``_CoverHost`` stub, named as a
base only under ``TYPE_CHECKING``. If that conditional base ever leaks into a
real inheritance, ``_CoverHost`` would join the runtime MRO and the mixins would
gain (empty) attributes they must not own. These tests lock the runtime shape so
that regression is caught.
"""

from custom_components.cover_time_based import (
    cover_calibration,
    cover_echo_filter,
    cover_lifecycle,
    cover_movement,
)
from custom_components.cover_time_based.cover_base import CoverTimeBased

MIXIN_MODULES = (
    cover_movement,
    cover_lifecycle,
    cover_echo_filter,
    cover_calibration,
)
MIXINS = (
    cover_movement.MovementMixin,
    cover_lifecycle.MovementLifecycleMixin,
    cover_echo_filter.SwitchEchoMixin,
    cover_calibration.CalibrationMixin,
)


def test_mixins_inherit_only_object_at_runtime():
    """Each mixin's sole runtime base is ``object`` — the stub base never leaks."""
    for mixin in MIXINS:
        assert mixin.__bases__ == (object,), (
            f"{mixin.__name__} inherits {mixin.__bases__}, not (object,)"
        )


def test_mixin_base_alias_is_object_at_runtime():
    """The ``_MixinBase`` alias resolves to ``object`` outside type-checking."""
    for module in MIXIN_MODULES:
        assert module._MixinBase is object


def test_cover_host_stays_out_of_the_runtime_mro():
    """``_CoverHost`` must not appear in the assembled entity's MRO."""
    mro_names = [cls.__name__ for cls in CoverTimeBased.__mro__]
    assert "_CoverHost" not in mro_names
    # The documented mixin order is preserved.
    assert mro_names[:5] == [
        "CoverTimeBased",
        "CalibrationMixin",
        "SwitchEchoMixin",
        "MovementMixin",
        "MovementLifecycleMixin",
    ]
