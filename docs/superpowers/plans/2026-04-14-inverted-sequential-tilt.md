# Inverted Sequential Tilt Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `sequential_open` tilt mode for covers whose slats articulate by the motor driving *further down* past the cover-closed position, and rename the existing `sequential` mode to `sequential_close` for symmetry.

**Architecture:** Introduce a `tilt_command_for(closing_tilt: bool) -> str` method on `TiltStrategy` that call sites consult to decide motor direction. `SequentialTilt` becomes a shared base holding planning/snap logic parameterised on `implicit_tilt_during_travel`. `SequentialCloseTilt` (100) and `SequentialOpenTilt` (0) are the two concrete subclasses; the latter also overrides `tilt_command_for` to invert the relay.

**Tech Stack:** Python 3.13, pytest (asyncio_mode=auto), Home Assistant custom component.

**Spec:** [docs/superpowers/specs/2026-04-14-inverted-sequential-tilt-design.md](../specs/2026-04-14-inverted-sequential-tilt-design.md)

---

## File Structure

### Files to modify

- `custom_components/cover_time_based/tilt_strategies/base.py` — add `tilt_command_for` default on `TiltStrategy`.
- `custom_components/cover_time_based/tilt_strategies/sequential.py` — refactor `SequentialTilt` into shared base class; add `SequentialCloseTilt` and `SequentialOpenTilt` concrete subclasses parameterised on `implicit_tilt_during_travel`.
- `custom_components/cover_time_based/tilt_strategies/__init__.py` — export the two new concrete classes.
- `custom_components/cover_time_based/cover.py` — update `_resolve_tilt_strategy` to map `sequential_close`/`sequential_open` (with `sequential` as legacy alias).
- `custom_components/cover_time_based/cover_base.py` — route `_async_move_tilt_to_endpoint`, `set_tilt_position`, `_start_tilt_restore` through `tilt_command_for`.
- `custom_components/cover_time_based/cover_calibration.py` — route `_start_simple_time_test` tilt dispatch through `tilt_command_for`.
- `custom_components/cover_time_based/config_flow.py` — bump `VERSION` 2 → 3.
- `custom_components/cover_time_based/__init__.py` — add `async_migrate_entry`.
- `custom_components/cover_time_based/frontend/cover-time-based-card.js` — update dropdown, `_onTiltModeChange`, and translations (en/pl/pt).
- `README.md` — document the new mode.

### Tests

All under `tests/`:

- `tests/test_tilt_strategy.py` — rename class references, add `SequentialOpenTilt` test class + `tilt_command_for` tests.
- `tests/test_cover_factory.py` — update `_resolve_tilt_strategy` tests for new names, add alias test, add `sequential_open` test.
- `tests/test_base_movement.py` or `tests/test_cover_base_extra.py` — integration tests for `_async_move_tilt_to_endpoint` and `set_tilt_position` direction with `SequentialOpenTilt`.
- `tests/test_calibration.py` — tilt calibration direction test with `SequentialOpenTilt`.
- `tests/integration/test_lifecycle.py` — config migration test (co-located with existing lifecycle tests that use `MockConfigEntry`).

---

## Task 1: Add `tilt_command_for` method to `TiltStrategy` base

**Files:**
- Modify: `custom_components/cover_time_based/tilt_strategies/base.py`
- Test: `tests/test_tilt_strategy.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tilt_strategy.py`:

```python
# ===================================================================
# TiltStrategy.tilt_command_for (default implementation)
# ===================================================================


class TestTiltCommandForDefault:
    """Default tilt_command_for maps closing_tilt to the standard direction."""

    def test_closing_tilt_sends_close(self):
        from homeassistant.const import SERVICE_CLOSE_COVER

        strategy = InlineTilt()
        assert strategy.tilt_command_for(closing_tilt=True) == SERVICE_CLOSE_COVER

    def test_opening_tilt_sends_open(self):
        from homeassistant.const import SERVICE_OPEN_COVER

        strategy = InlineTilt()
        assert strategy.tilt_command_for(closing_tilt=False) == SERVICE_OPEN_COVER

    def test_default_applies_to_sequential(self):
        from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

        strategy = SequentialTilt()
        assert strategy.tilt_command_for(True) == SERVICE_CLOSE_COVER
        assert strategy.tilt_command_for(False) == SERVICE_OPEN_COVER

    def test_default_applies_to_dual_motor(self):
        from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

        strategy = DualMotorTilt()
        assert strategy.tilt_command_for(True) == SERVICE_CLOSE_COVER
        assert strategy.tilt_command_for(False) == SERVICE_OPEN_COVER
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tilt_strategy.py::TestTiltCommandForDefault -v`
Expected: FAIL with `AttributeError: ... object has no attribute 'tilt_command_for'`

- [ ] **Step 3: Add the method to `TiltStrategy` base**

Edit `custom_components/cover_time_based/tilt_strategies/base.py`. Add the import at the top (after the existing imports), then add the method to `TiltStrategy`:

```python
from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER
```

Then inside `class TiltStrategy(ABC):`, after `allows_tilt_at_position` (just before `snap_trackers_to_physical`), add:

```python
    def tilt_command_for(self, closing_tilt: bool) -> str:
        """Return the HA cover service to send for this tilt direction.

        The default maps closing_tilt=True to close and closing_tilt=False
        to open. Strategies with inverted physical direction (e.g.
        SequentialOpenTilt, where slats open by motor driving further down)
        override this.
        """
        return SERVICE_CLOSE_COVER if closing_tilt else SERVICE_OPEN_COVER
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tilt_strategy.py::TestTiltCommandForDefault -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full test file to ensure no regressions**

Run: `pytest tests/test_tilt_strategy.py -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/cover_time_based/tilt_strategies/base.py tests/test_tilt_strategy.py
git commit -m "feat: add tilt_command_for method to TiltStrategy base"
```

---

## Task 2: Parameterise `SequentialTilt` on `implicit_tilt_during_travel`

Refactor `SequentialTilt` to read the "what tilt value is physically valid during travel" constant from `self.implicit_tilt_during_travel` instead of hard-coded `100`. No behavior change — `implicit_tilt_during_travel` defaults to `100`. Sets up Task 4 (subclass that overrides).

**Files:**
- Modify: `custom_components/cover_time_based/tilt_strategies/sequential.py`
- Test: `tests/test_tilt_strategy.py` (existing tests must keep passing)

- [ ] **Step 1: Write the passing test for the new property**

Append to `tests/test_tilt_strategy.py` inside `class TestSequentialTiltProperties:` (around line 67):

```python
    def test_implicit_tilt_during_travel(self):
        assert SequentialTilt().implicit_tilt_during_travel == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tilt_strategy.py::TestSequentialTiltProperties::test_implicit_tilt_during_travel -v`
Expected: FAIL with `AttributeError: ... has no attribute 'implicit_tilt_during_travel'`

- [ ] **Step 3: Refactor `SequentialTilt` to use the property**

Replace the body of `custom_components/cover_time_based/tilt_strategies/sequential.py` with:

```python
"""Sequential tilt strategies.

Tilt couples proportionally when travel moves, but travel does NOT
couple when tilt moves. No boundary constraints are enforced.
Tilt calibration is allowed.

Two concrete variants share this logic:

- SequentialCloseTilt (the conventional behavior):  slats physically
  sit at tilt=100 (open) while the cover is not at the closed
  position. Tilt-close from the closed position sends CLOSE (motor
  down); tilt-open sends OPEN (motor up).
- SequentialOpenTilt (Sese-Schneider/ha-cover-time-based#61):  slats
  physically sit at tilt=0 (closed) while the cover is not at the
  closed position. Tilt-open articulates the slats by driving the
  motor further DOWN past the cover-closed position; tilt-close
  sends OPEN (motor up).
"""

from __future__ import annotations

import logging

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from .base import TiltStrategy, TiltTo, TravelTo

_LOGGER = logging.getLogger(__name__)


class SequentialTilt(TiltStrategy):
    """Sequential tilt base.

    Shared planning and snap logic for sequential modes. Subclasses
    set ``implicit_tilt_during_travel`` — the tilt value physically
    enforced whenever the cover is not at the closed position — and
    optionally override ``tilt_command_for``.
    """

    implicit_tilt_during_travel: int = 100

    def can_calibrate_tilt(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "sequential"

    @property
    def uses_tilt_motor(self) -> bool:
        return False

    @property
    def restores_tilt(self) -> bool:
        return False

    def plan_move_position(
        self, target_pos: int, current_pos: int, current_tilt: int
    ) -> list[TiltTo | TravelTo]:
        steps: list[TiltTo | TravelTo] = []
        if current_tilt != self.implicit_tilt_during_travel:
            steps.append(TiltTo(self.implicit_tilt_during_travel))
        steps.append(TravelTo(target_pos))
        return steps

    def plan_move_tilt(
        self, target_tilt: int, current_pos: int, current_tilt: int
    ) -> list[TiltTo | TravelTo]:
        steps: list[TiltTo | TravelTo] = []
        if current_pos != 0:
            steps.append(TravelTo(0))
        steps.append(TiltTo(target_tilt))
        return steps

    def snap_trackers_to_physical(self, travel_calc, tilt_calc):
        current_travel = travel_calc.current_position()
        current_tilt_pos = tilt_calc.current_position()
        if current_travel is None or current_tilt_pos is None:
            return
        implicit = self.implicit_tilt_during_travel
        if current_travel != 0 and current_tilt_pos != implicit:
            _LOGGER.debug(
                "%s :: Travel at %d%% (not closed), forcing tilt to %d%% (was %d%%)",
                type(self).__name__,
                current_travel,
                implicit,
                current_tilt_pos,
            )
            tilt_calc.set_position(implicit)
```

Note: the new file does NOT yet define `SequentialCloseTilt` or `SequentialOpenTilt` — those come in Tasks 3 and 4. The `SERVICE_*` imports are unused for now; they will be consumed when `SequentialOpenTilt` lands in Task 4.

- [ ] **Step 4: Run the full tilt_strategy test file**

Run: `pytest tests/test_tilt_strategy.py -v`
Expected: All existing tests pass (the refactor preserves behavior) AND the new `test_implicit_tilt_during_travel` passes.

- [ ] **Step 5: Run the full test suite to catch regressions**

Run: `pytest tests/ -x -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/cover_time_based/tilt_strategies/sequential.py tests/test_tilt_strategy.py
git commit -m "refactor: parameterise SequentialTilt on implicit_tilt_during_travel"
```

---

## Task 3: Rename internal mode `sequential` → `sequential_close` with legacy alias

Rename the `SequentialTilt.name` return value to `"sequential_close"` and update `_resolve_tilt_strategy` to accept both `"sequential_close"` and the legacy `"sequential"`. This does *not* introduce new class names yet — that's Task 4. The existing `SequentialTilt` class keeps its name (we'll split it into concrete variants in Task 4).

**Files:**
- Modify: `custom_components/cover_time_based/tilt_strategies/sequential.py`
- Modify: `custom_components/cover_time_based/cover.py`
- Test: `tests/test_tilt_strategy.py`
- Test: `tests/test_cover_factory.py`

- [ ] **Step 1: Update name assertion test**

In `tests/test_tilt_strategy.py`, change the existing `test_name` assertion inside `TestSequentialTiltProperties`:

```python
    def test_name(self):
        assert SequentialTilt().name == "sequential_close"
```

- [ ] **Step 2: Add resolver alias tests**

In `tests/test_cover_factory.py`, replace the existing `test_sequential` and `test_unknown_mode_defaults_to_sequential` tests (around lines 436-469) with:

```python
    def test_sequential_close(self):
        result = _resolve_tilt_strategy("sequential_close", 2.0, 2.0)
        assert isinstance(result, SequentialTilt)
        assert result.name == "sequential_close"

    def test_sequential_legacy_alias(self):
        """Legacy 'sequential' value still resolves (covers unmigrated configs)."""
        result = _resolve_tilt_strategy("sequential", 2.0, 2.0)
        assert isinstance(result, SequentialTilt)

    def test_unknown_mode_defaults_to_sequential(self):
        result = _resolve_tilt_strategy("unknown_value", 2.0, 2.0)
        assert isinstance(result, SequentialTilt)
```

Also update the two `_resolve_tilt_strategy("sequential", None, ...)` tests above to use `"sequential_close"` to reflect the new canonical name:

```python
    def test_none_when_no_tilt_times(self):
        assert _resolve_tilt_strategy("sequential_close", None, None) is None

    def test_none_when_partial_tilt_times(self):
        assert _resolve_tilt_strategy("sequential_close", 2.0, None) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_tilt_strategy.py::TestSequentialTiltProperties::test_name tests/test_cover_factory.py::TestResolveTiltStrategy -v`
Expected: FAIL — `test_name` asserts "sequential_close" but class returns "sequential"; `test_sequential_close` not yet supported by resolver.

- [ ] **Step 4: Update `SequentialTilt.name`**

In `custom_components/cover_time_based/tilt_strategies/sequential.py`, change:

```python
    @property
    def name(self) -> str:
        return "sequential"
```

to:

```python
    @property
    def name(self) -> str:
        return "sequential_close"
```

- [ ] **Step 5: Update `_resolve_tilt_strategy`**

In `custom_components/cover_time_based/cover.py`, replace the block at lines 247-266 with:

```python
def _resolve_tilt_strategy(tilt_mode_str, tilt_time_close, tilt_time_open, **kwargs):
    """Map tilt_mode config string to a TiltStrategy instance (or None)."""
    from .tilt_strategies import DualMotorTilt, InlineTilt, SequentialTilt

    if tilt_mode_str == "none":
        return None

    has_tilt_times = tilt_time_close is not None and tilt_time_open is not None
    if not has_tilt_times:
        return None

    if tilt_mode_str == "dual_motor":
        return DualMotorTilt(
            safe_tilt_position=kwargs.get("safe_tilt_position", 100),
            max_tilt_allowed_position=kwargs.get("max_tilt_allowed_position"),
        )
    if tilt_mode_str == "inline":
        return InlineTilt()
    # "sequential_close", legacy "sequential", or any other value with tilt times
    return SequentialTilt()
```

No functional change yet — `SequentialTilt()` still constructs the same concrete class. Task 4 replaces this with the concrete subclasses.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_tilt_strategy.py tests/test_cover_factory.py -v`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add custom_components/cover_time_based/tilt_strategies/sequential.py custom_components/cover_time_based/cover.py tests/test_tilt_strategy.py tests/test_cover_factory.py
git commit -m "refactor: rename sequential tilt mode to sequential_close"
```

---

## Task 4: Split `SequentialTilt` into `SequentialCloseTilt` + `SequentialOpenTilt`

Introduce two concrete subclasses of `SequentialTilt`. `SequentialCloseTilt` is the existing behavior; `SequentialOpenTilt` inverts both `implicit_tilt_during_travel` and `tilt_command_for`. Make `SequentialTilt` abstract enough that only subclasses are instantiated (we keep it importable as the shared base for `isinstance` checks and inheritance).

**Files:**
- Modify: `custom_components/cover_time_based/tilt_strategies/sequential.py`
- Modify: `custom_components/cover_time_based/tilt_strategies/__init__.py`
- Test: `tests/test_tilt_strategy.py`

- [ ] **Step 1: Write failing tests for the new subclasses**

Append to `tests/test_tilt_strategy.py`, replacing the import line and adding new test classes:

First, update the existing import (around line 5):

```python
from custom_components.cover_time_based.tilt_strategies import (
    DualMotorTilt,
    InlineTilt,
    SequentialCloseTilt,
    SequentialOpenTilt,
    SequentialTilt,
    TiltTo,
    TravelTo,
)
```

Then append these new test classes at the end of the file:

```python
# ===================================================================
# SequentialCloseTilt (concrete, conventional direction)
# ===================================================================


class TestSequentialCloseTilt:
    def test_name(self):
        assert SequentialCloseTilt().name == "sequential_close"

    def test_is_sequential_tilt(self):
        assert isinstance(SequentialCloseTilt(), SequentialTilt)

    def test_implicit_tilt_during_travel(self):
        assert SequentialCloseTilt().implicit_tilt_during_travel == 100

    def test_tilt_command_for_closing(self):
        from homeassistant.const import SERVICE_CLOSE_COVER

        assert SequentialCloseTilt().tilt_command_for(True) == SERVICE_CLOSE_COVER

    def test_tilt_command_for_opening(self):
        from homeassistant.const import SERVICE_OPEN_COVER

        assert SequentialCloseTilt().tilt_command_for(False) == SERVICE_OPEN_COVER


# ===================================================================
# SequentialOpenTilt (concrete, inverted direction)
# ===================================================================


class TestSequentialOpenTilt:
    def test_name(self):
        assert SequentialOpenTilt().name == "sequential_open"

    def test_is_sequential_tilt(self):
        assert isinstance(SequentialOpenTilt(), SequentialTilt)

    def test_implicit_tilt_during_travel(self):
        assert SequentialOpenTilt().implicit_tilt_during_travel == 0

    def test_uses_tilt_motor(self):
        assert SequentialOpenTilt().uses_tilt_motor is False

    def test_restores_tilt(self):
        assert SequentialOpenTilt().restores_tilt is False

    def test_can_calibrate_tilt(self):
        assert SequentialOpenTilt().can_calibrate_tilt() is True

    def test_tilt_command_for_closing_returns_open(self):
        """Inverted: closing_tilt=True sends OPEN (motor up)."""
        from homeassistant.const import SERVICE_OPEN_COVER

        assert SequentialOpenTilt().tilt_command_for(True) == SERVICE_OPEN_COVER

    def test_tilt_command_for_opening_returns_close(self):
        """Inverted: closing_tilt=False sends CLOSE (motor further down)."""
        from homeassistant.const import SERVICE_CLOSE_COVER

        assert SequentialOpenTilt().tilt_command_for(False) == SERVICE_CLOSE_COVER


class TestSequentialOpenPlanMovePosition:
    def test_flattens_tilt_to_zero_before_travel(self):
        strategy = SequentialOpenTilt()
        steps = strategy.plan_move_position(
            target_pos=70, current_pos=0, current_tilt=80
        )
        assert steps == [TiltTo(0), TravelTo(70)]

    def test_skips_tilt_when_already_zero(self):
        strategy = SequentialOpenTilt()
        steps = strategy.plan_move_position(
            target_pos=70, current_pos=0, current_tilt=0
        )
        assert steps == [TravelTo(70)]


class TestSequentialOpenPlanMoveTilt:
    def test_travels_to_closed_before_tilting(self):
        strategy = SequentialOpenTilt()
        steps = strategy.plan_move_tilt(
            target_tilt=50, current_pos=70, current_tilt=0
        )
        assert steps == [TravelTo(0), TiltTo(50)]

    def test_tilts_directly_when_at_closed(self):
        strategy = SequentialOpenTilt()
        steps = strategy.plan_move_tilt(target_tilt=100, current_pos=0, current_tilt=0)
        assert steps == [TiltTo(100)]


class TestSequentialOpenSnapTrackers:
    def test_forces_tilt_to_zero_when_not_at_closed(self):
        strategy = SequentialOpenTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(50)
        tilt.set_position(80)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0

    def test_no_op_when_at_closed(self):
        strategy = SequentialOpenTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(0)
        tilt.set_position(50)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 50

    def test_no_op_when_already_zero(self):
        strategy = SequentialOpenTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(30)
        tilt.set_position(0)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0
```

Also, update the existing `TestSequentialTiltProperties` class — rename it to `TestSequentialCloseTiltViaBase` to clarify it exercises the conventional variant, and update all the existing test classes `TestSequentialTilt*` that call `SequentialTilt()` directly to call `SequentialCloseTilt()` instead. These are the classes at lines 56-194:

- `TestSequentialTiltCanCalibrate` — `SequentialTilt()` → `SequentialCloseTilt()`
- `TestSequentialTiltProperties` — `SequentialTilt()` → `SequentialCloseTilt()`
- `TestSequentialPlanMovePosition` — `SequentialTilt()` → `SequentialCloseTilt()` (5 occurrences)
- `TestSequentialPlanMoveTilt` — `SequentialTilt()` → `SequentialCloseTilt()` (4 occurrences)
- `TestSequentialSnapTrackers` — `SequentialTilt()` → `SequentialCloseTilt()` (6 occurrences)

Plus `TestTiltCommandForDefault.test_default_applies_to_sequential` — `SequentialTilt()` → `SequentialCloseTilt()`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tilt_strategy.py -v 2>&1 | tail -40`
Expected: Import error — `SequentialCloseTilt` and `SequentialOpenTilt` are not exported yet.

- [ ] **Step 3: Add the subclasses**

Append to `custom_components/cover_time_based/tilt_strategies/sequential.py`:

```python
class SequentialCloseTilt(SequentialTilt):
    """Conventional sequential tilt.

    Slats are physically at tilt=100 (open) while the cover is not at
    the closed position. Tilt-close sends CLOSE (motor down);
    tilt-open sends OPEN (motor up).
    """

    implicit_tilt_during_travel: int = 100

    @property
    def name(self) -> str:
        return "sequential_close"


class SequentialOpenTilt(SequentialTilt):
    """Inverted sequential tilt (Sese-Schneider/ha-cover-time-based#61).

    Slats are physically at tilt=0 (closed) while the cover is not at
    the closed position. Tilt-open articulates the slats by driving
    the motor further DOWN past the cover-closed position; tilt-close
    sends OPEN (motor up to return from the open-slats position to
    the slats-closed position).
    """

    implicit_tilt_during_travel: int = 0

    @property
    def name(self) -> str:
        return "sequential_open"

    def tilt_command_for(self, closing_tilt: bool) -> str:
        return SERVICE_OPEN_COVER if closing_tilt else SERVICE_CLOSE_COVER
```

- [ ] **Step 4: Export the new classes**

Edit `custom_components/cover_time_based/tilt_strategies/__init__.py`:

```python
"""Tilt strategy classes for cover_time_based.

Tilt strategies determine how travel and tilt movements are coupled.
"""

from .base import MovementStep, TiltStrategy, TiltTo, TravelTo
from .dual_motor import DualMotorTilt
from .inline import InlineTilt
from .planning import (
    calculate_pre_step_delay,
    extract_coupled_tilt,
    extract_coupled_travel,
)
from .sequential import SequentialCloseTilt, SequentialOpenTilt, SequentialTilt

__all__ = [
    "DualMotorTilt",
    "InlineTilt",
    "MovementStep",
    "SequentialCloseTilt",
    "SequentialOpenTilt",
    "SequentialTilt",
    "TiltStrategy",
    "TiltTo",
    "TravelTo",
    "calculate_pre_step_delay",
    "extract_coupled_tilt",
    "extract_coupled_travel",
]
```

- [ ] **Step 5: Run tilt_strategy tests**

Run: `pytest tests/test_tilt_strategy.py -v`
Expected: All tests pass (old ones renamed, new `TestSequentialCloseTilt`, `TestSequentialOpenTilt`, `TestSequentialOpenPlanMovePosition`, `TestSequentialOpenPlanMoveTilt`, `TestSequentialOpenSnapTrackers` pass).

- [ ] **Step 6: Commit**

```bash
git add custom_components/cover_time_based/tilt_strategies/sequential.py custom_components/cover_time_based/tilt_strategies/__init__.py tests/test_tilt_strategy.py
git commit -m "feat: add SequentialCloseTilt and SequentialOpenTilt variants"
```

---

## Task 5: Wire `sequential_close` and `sequential_open` through `_resolve_tilt_strategy`

Update the resolver to instantiate the correct concrete subclass per mode string, keeping `"sequential"` as a legacy alias.

**Files:**
- Modify: `custom_components/cover_time_based/cover.py`
- Test: `tests/test_cover_factory.py`

- [ ] **Step 1: Write failing tests**

In `tests/test_cover_factory.py`, update the import (around line 41):

```python
from custom_components.cover_time_based.tilt_strategies import (
    DualMotorTilt,
    InlineTilt,
    SequentialCloseTilt,
    SequentialOpenTilt,
    SequentialTilt,
)
```

Then update the resolver tests (the ones you added in Task 3):

```python
    def test_sequential_close(self):
        result = _resolve_tilt_strategy("sequential_close", 2.0, 2.0)
        assert isinstance(result, SequentialCloseTilt)
        assert result.name == "sequential_close"

    def test_sequential_open(self):
        result = _resolve_tilt_strategy("sequential_open", 2.0, 2.0)
        assert isinstance(result, SequentialOpenTilt)
        assert result.name == "sequential_open"

    def test_sequential_legacy_alias(self):
        """Legacy 'sequential' value resolves to SequentialCloseTilt."""
        result = _resolve_tilt_strategy("sequential", 2.0, 2.0)
        assert isinstance(result, SequentialCloseTilt)

    def test_unknown_mode_defaults_to_sequential_close(self):
        result = _resolve_tilt_strategy("unknown_value", 2.0, 2.0)
        assert isinstance(result, SequentialCloseTilt)
```

(Delete the old `test_unknown_mode_defaults_to_sequential`, replaced by `test_unknown_mode_defaults_to_sequential_close`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cover_factory.py::TestResolveTiltStrategy -v`
Expected: FAIL — `sequential_close` currently returns base `SequentialTilt`, not `SequentialCloseTilt`; `sequential_open` not handled.

- [ ] **Step 3: Update `_resolve_tilt_strategy`**

In `custom_components/cover_time_based/cover.py`, replace the `_resolve_tilt_strategy` function (lines 247-266) with:

```python
def _resolve_tilt_strategy(tilt_mode_str, tilt_time_close, tilt_time_open, **kwargs):
    """Map tilt_mode config string to a TiltStrategy instance (or None)."""
    from .tilt_strategies import (
        DualMotorTilt,
        InlineTilt,
        SequentialCloseTilt,
        SequentialOpenTilt,
    )

    if tilt_mode_str == "none":
        return None

    has_tilt_times = tilt_time_close is not None and tilt_time_open is not None
    if not has_tilt_times:
        return None

    if tilt_mode_str == "dual_motor":
        return DualMotorTilt(
            safe_tilt_position=kwargs.get("safe_tilt_position", 100),
            max_tilt_allowed_position=kwargs.get("max_tilt_allowed_position"),
        )
    if tilt_mode_str == "inline":
        return InlineTilt()
    if tilt_mode_str == "sequential_open":
        return SequentialOpenTilt()
    # "sequential_close", legacy "sequential", or any unknown value → close variant
    return SequentialCloseTilt()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cover_factory.py::TestResolveTiltStrategy -v`
Expected: PASS.

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/ -x -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/cover_time_based/cover.py tests/test_cover_factory.py
git commit -m "feat: resolve sequential_close and sequential_open tilt modes"
```

---

## Task 6: Route `_async_move_tilt_to_endpoint` through `tilt_command_for`

Update the single-motor command path in `_async_move_tilt_to_endpoint` to consult the strategy for motor direction. This makes `SequentialOpenTilt` actually send inverted commands when tilt endpoints are requested.

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py`
- Test: `tests/test_base_movement.py` or `tests/test_cover_base_extra.py`

- [ ] **Step 1: Find an existing integration test pattern**

Run: `grep -n "async_move_tilt_to_endpoint\|async_open_cover_tilt\|async_close_cover_tilt" tests/test_base_movement.py | head -20`

This shows which file has integration tests for tilt movement. Look at the most recent 2-3 tests to identify the fixture pattern (`switch_cover` or similar).

- [ ] **Step 2: Write a failing integration test**

Append to `tests/test_base_movement.py` (or the file surfaced in Step 1). Replace the fixture construction pattern with whatever that file uses — the test asserts that calling `async_close_cover_tilt()` on a cover with `SequentialOpenTilt` sends `SERVICE_OPEN_COVER` (inverted):

```python
async def test_sequential_open_tilt_close_sends_open_command(hass):
    """SequentialOpenTilt: closing the tilt physically sends OPEN (motor up)."""
    from homeassistant.const import SERVICE_OPEN_COVER
    from custom_components.cover_time_based.tilt_strategies import SequentialOpenTilt

    cover = make_switch_cover(
        hass,
        tilt_strategy=SequentialOpenTilt(),
        travel_time_open=10.0,
        travel_time_close=10.0,
        tilt_time_open=2.0,
        tilt_time_close=2.0,
    )
    # Position: cover at 0 (closed), slats at tilt=100 (fully open, bottom)
    cover.travel_calc.set_position(0)
    cover.tilt_calc.set_position(100)

    hass.services.async_call = AsyncMock()
    await cover.async_close_cover_tilt()

    # Find the relay service call that was made. For switch-mode, closing the
    # tilt from tilt=100 to tilt=0 should send OPEN (motor up) with the
    # inverted strategy.
    calls = [c for c in hass.services.async_call.mock_calls if c.args[:2] == ("homeassistant", "turn_on")]
    activated_entities = [c.args[2]["entity_id"] for c in calls]
    # The OPEN switch (travel-up relay) should have been turned on.
    assert cover._open_switch_entity_id in activated_entities
    assert cover._close_switch_entity_id not in activated_entities
```

If `make_switch_cover` does not exist, copy the inline construction used by neighboring tests in the same file (it typically builds a `SwitchModeCover` directly with MagicMock entities). The key assertion is that `hass.services.async_call` is invoked with `turn_on` on the OPEN relay, not the CLOSE relay.

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_base_movement.py::test_sequential_open_tilt_close_sends_open_command -v`
Expected: FAIL — the cover sends CLOSE because direction is still hard-coded.

- [ ] **Step 4: Update `_async_move_tilt_to_endpoint`**

In `custom_components/cover_time_based/cover_base.py`, replace lines 510-512 (the `command`/`opposite_command` derivation):

```python
        closing = target == 0
        command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
        opposite_command = SERVICE_OPEN_COVER if closing else SERVICE_CLOSE_COVER
```

with:

```python
        closing = target == 0
        if self._tilt_strategy is not None:
            command = self._tilt_strategy.tilt_command_for(closing)
            opposite_command = self._tilt_strategy.tilt_command_for(not closing)
        else:
            command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
            opposite_command = SERVICE_OPEN_COVER if closing else SERVICE_CLOSE_COVER
```

Do NOT change lines 583-587 (the `uses_tilt_motor` / dual-motor branch calling `_send_tilt_close` / `_send_tilt_open`). Dual-motor drives dedicated tilt switches — inversion does not apply.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_base_movement.py::test_sequential_open_tilt_close_sends_open_command -v`
Expected: PASS.

- [ ] **Step 6: Run the full test suite**

Run: `pytest tests/ -x -q`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add custom_components/cover_time_based/cover_base.py tests/test_base_movement.py
git commit -m "feat: route _async_move_tilt_to_endpoint through tilt_command_for"
```

---

## Task 7: Route `set_tilt_position` through `tilt_command_for`

`set_tilt_position` handles arbitrary tilt targets (not just endpoints). Its command choice sits at lines 687-695 of `cover_base.py`. Route the three branches through `tilt_command_for`.

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py`
- Test: same test file as Task 6

- [ ] **Step 1: Write a failing test**

Append to the test file used in Task 6:

```python
async def test_sequential_open_set_tilt_position_sends_close(hass):
    """SequentialOpenTilt: moving tilt from 0→50 sends CLOSE (motor further down)."""
    from custom_components.cover_time_based.tilt_strategies import SequentialOpenTilt

    cover = make_switch_cover(
        hass,
        tilt_strategy=SequentialOpenTilt(),
        travel_time_open=10.0,
        travel_time_close=10.0,
        tilt_time_open=2.0,
        tilt_time_close=2.0,
    )
    cover.travel_calc.set_position(0)
    cover.tilt_calc.set_position(0)

    hass.services.async_call = AsyncMock()
    await cover.set_tilt_position(50)

    calls = [c for c in hass.services.async_call.mock_calls if c.args[:2] == ("homeassistant", "turn_on")]
    activated_entities = [c.args[2]["entity_id"] for c in calls]
    # Opening the tilt (target 50 > current 0) should drive the close relay (motor down).
    assert cover._close_switch_entity_id in activated_entities
    assert cover._open_switch_entity_id not in activated_entities
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_base_movement.py::test_sequential_open_set_tilt_position_sends_close -v`
Expected: FAIL.

- [ ] **Step 3: Update `set_tilt_position`**

In `custom_components/cover_time_based/cover_base.py`, replace lines 687-695 with:

```python
        if current is None:
            closing = target <= 50
            current = 100 if closing else 0
            self.tilt_calc.update_position(current)
        elif target < current:
            closing = True
        elif target > current:
            closing = False
        else:
            return

        if self._tilt_strategy is not None:
            command = self._tilt_strategy.tilt_command_for(closing)
        else:
            command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
```

Then remove the now-redundant `closing = command == SERVICE_CLOSE_COVER` assignment on the line immediately below (currently line 699) — `closing` is already bound.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_base_movement.py::test_sequential_open_set_tilt_position_sends_close -v`
Expected: PASS.

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/ -x -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/cover_time_based/cover_base.py tests/test_base_movement.py
git commit -m "feat: route set_tilt_position through tilt_command_for"
```

---

## Task 8: Route `_start_tilt_restore` through `tilt_command_for`

Only `InlineTilt` currently has `restores_tilt=True`, so this path is dead for sequential modes today. We route it through `tilt_command_for` for symmetry and to future-proof. No behavior change for inline (its default `tilt_command_for` returns the conventional mapping).

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py`

- [ ] **Step 1: Run the existing inline tilt tests as a regression baseline**

Run: `pytest tests/ -k "tilt_restore or inline" -v`
Note which tests pass. After the change, they must still pass.

- [ ] **Step 2: Update `_start_tilt_restore`**

In `custom_components/cover_time_based/cover_base.py`, the shared-motor branch currently reads (lines 1370-1373):

```python
        else:
            # Shared motor (inline): reverse main motor direction
            command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
            await self._async_handle_command(command)
```

Change to:

```python
        else:
            # Shared motor (inline or sequential): consult the strategy for direction.
            command = self._tilt_strategy.tilt_command_for(closing)
            await self._async_handle_command(command)
```

- [ ] **Step 3: Run regression tests**

Run: `pytest tests/ -k "tilt_restore or inline" -v`
Expected: Same tests pass as in Step 1.

- [ ] **Step 4: Run the full test suite**

Run: `pytest tests/ -x -q`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/cover_time_based/cover_base.py
git commit -m "refactor: route _start_tilt_restore through tilt_command_for"
```

---

## Task 9: Route `_start_simple_time_test` for tilt attributes through `tilt_command_for`

The calibration dispatcher currently derives direction from the attribute name (`"close" in attribute → SERVICE_CLOSE_COVER`). For `SequentialOpenTilt`, `tilt_time_open` calibration must send CLOSE (motor down) and `tilt_time_close` must send OPEN.

**Files:**
- Modify: `custom_components/cover_time_based/cover_calibration.py`
- Test: `tests/test_calibration.py`

- [ ] **Step 1: Write failing tests**

Look at existing patterns in `tests/test_calibration.py` for how tilt calibration is invoked (search for `tilt_time_open` or `start_calibration`). Mirror that pattern to assert that, with `SequentialOpenTilt`:

```python
async def test_sequential_open_tilt_time_open_sends_close(hass):
    """With SequentialOpenTilt, calibrating tilt_time_open moves motor DOWN."""
    from homeassistant.const import SERVICE_CLOSE_COVER
    from custom_components.cover_time_based.tilt_strategies import SequentialOpenTilt

    cover = make_switch_cover(
        hass,
        tilt_strategy=SequentialOpenTilt(),
        travel_time_open=10.0,
        travel_time_close=10.0,
        tilt_time_open=2.0,
        tilt_time_close=2.0,
    )
    cover.travel_calc.set_position(0)
    cover.tilt_calc.set_position(0)

    hass.services.async_call = AsyncMock()
    await cover.start_calibration(attribute="tilt_time_open", timeout=60)

    # The close relay should fire (motor down to articulate slats open).
    calls = [c for c in hass.services.async_call.mock_calls if c.args[:2] == ("homeassistant", "turn_on")]
    activated = [c.args[2]["entity_id"] for c in calls]
    assert cover._close_switch_entity_id in activated
    assert cover._open_switch_entity_id not in activated

    # Cleanup — cancel the running calibration.
    await cover.stop_calibration(cancel=True)


async def test_sequential_open_tilt_time_close_sends_open(hass):
    """With SequentialOpenTilt, calibrating tilt_time_close moves motor UP."""
    from custom_components.cover_time_based.tilt_strategies import SequentialOpenTilt

    cover = make_switch_cover(
        hass,
        tilt_strategy=SequentialOpenTilt(),
        travel_time_open=10.0,
        travel_time_close=10.0,
        tilt_time_open=2.0,
        tilt_time_close=2.0,
    )
    cover.travel_calc.set_position(0)
    cover.tilt_calc.set_position(100)

    hass.services.async_call = AsyncMock()
    await cover.start_calibration(attribute="tilt_time_close", timeout=60)

    calls = [c for c in hass.services.async_call.mock_calls if c.args[:2] == ("homeassistant", "turn_on")]
    activated = [c.args[2]["entity_id"] for c in calls]
    assert cover._open_switch_entity_id in activated
    assert cover._close_switch_entity_id not in activated

    await cover.stop_calibration(cancel=True)
```

Reuse the cover-factory helper (`make_switch_cover` or inline construction) from the file's existing tests.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_calibration.py -k "sequential_open" -v`
Expected: FAIL — current dispatcher sends the conventional direction.

- [ ] **Step 3: Update `_start_simple_time_test`**

In `custom_components/cover_time_based/cover_calibration.py`, replace `_start_simple_time_test` (lines 116-125) with:

```python
    async def _start_simple_time_test(self, attribute, direction):
        """Start a simple travel/tilt time test by moving the cover."""
        assert self._calibration is not None
        if direction:
            move_command = self._resolve_direction(direction, None)
        elif attribute.startswith("tilt_") and self._tilt_strategy is not None:
            closing_tilt = "close" in attribute
            move_command = self._tilt_strategy.tilt_command_for(closing_tilt)
        elif "close" in attribute:
            move_command = SERVICE_CLOSE_COVER
        else:
            move_command = SERVICE_OPEN_COVER
        self._calibration.move_command = move_command
        await self._async_handle_command(move_command)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_calibration.py -k "sequential_open" -v`
Expected: PASS.

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/ -x -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/cover_time_based/cover_calibration.py tests/test_calibration.py
git commit -m "feat: route tilt calibration dispatch through tilt_command_for"
```

---

## Task 10: Bump ConfigFlow VERSION and add migration

Bump `VERSION` 2 → 3 and add `async_migrate_entry` that rewrites `tilt_mode == "sequential"` to `"sequential_close"`.

**Files:**
- Modify: `custom_components/cover_time_based/config_flow.py`
- Modify: `custom_components/cover_time_based/__init__.py`
- Test: `tests/integration/test_lifecycle.py`

The integration test suite under `tests/integration/` already uses `pytest_homeassistant_custom_component.common.MockConfigEntry` and a real `hass` fixture (see `tests/integration/conftest.py`). Add the migration tests there so they get a working `hass.config_entries.async_update_entry`.

- [ ] **Step 1: Write failing migration tests**

Append to `tests/integration/test_lifecycle.py`:

```python
async def test_migrate_v2_sequential_to_v3_sequential_close(hass: HomeAssistant):
    """v2 entries with tilt_mode='sequential' migrate to v3 'sequential_close'."""
    from custom_components.cover_time_based import async_migrate_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Test",
        data={},
        options={"tilt_mode": "sequential", "travel_time_open": 10},
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 3
    assert entry.options["tilt_mode"] == "sequential_close"
    assert entry.options["travel_time_open"] == 10


async def test_migrate_v2_non_sequential_bumps_version_only(hass: HomeAssistant):
    """v2 entries whose tilt_mode is not 'sequential' only bump the version."""
    from custom_components.cover_time_based import async_migrate_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Test",
        data={},
        options={"tilt_mode": "inline"},
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 3
    assert entry.options["tilt_mode"] == "inline"


async def test_migrate_v3_is_idempotent(hass: HomeAssistant):
    """v3 entries are not modified."""
    from custom_components.cover_time_based import async_migrate_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        title="Test",
        data={},
        options={"tilt_mode": "sequential_close"},
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 3
    assert entry.options["tilt_mode"] == "sequential_close"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_lifecycle.py -k migrate -v`
Expected: FAIL — `async_migrate_entry` does not exist yet.

- [ ] **Step 3: Bump VERSION**

In `custom_components/cover_time_based/config_flow.py`, change line 21:

```python
    VERSION = 3
```

- [ ] **Step 4: Add `async_migrate_entry`**

Edit `custom_components/cover_time_based/__init__.py`. Add the function below `async_setup_entry`:

```python
async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries between versions."""
    _LOGGER.debug(
        "Migrating config entry %s from version %s", entry.entry_id, entry.version
    )

    if entry.version < 3:
        new_options = dict(entry.options)
        if new_options.get("tilt_mode") == "sequential":
            new_options["tilt_mode"] = "sequential_close"
        hass.config_entries.async_update_entry(entry, options=new_options, version=3)

    return True
```

The string `"tilt_mode"` here matches `CONF_TILT_MODE`'s value (defined in `const.py:5`); hard-coding keeps the function free of circular imports on startup.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/integration/test_lifecycle.py -k migrate -v`
Expected: PASS.

- [ ] **Step 6: Run the full test suite**

Run: `pytest tests/ -x -q`
Expected: All tests pass. Existing integration tests create entries with `version=2` and `tilt_mode="sequential"` — migration runs at setup time and rewrites to `sequential_close`, while the legacy alias in `_resolve_tilt_strategy` covers any code path that sees the un-migrated value.

- [ ] **Step 7: Commit**

```bash
git add custom_components/cover_time_based/config_flow.py custom_components/cover_time_based/__init__.py tests/integration/test_lifecycle.py
git commit -m "feat: migrate tilt_mode 'sequential' to 'sequential_close' (v2→v3)"
```

---

## Task 11: Update frontend dropdown, handler, and translations

Update the frontend card to offer `sequential_close` and `sequential_open` as distinct dropdown options, adjust the mode-change handler, and add translations in en/pl/pt.

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js`

No automated tests (frontend JS is not covered by the pytest suite). Manual verification steps are listed at the end of the task.

- [ ] **Step 1: Update English translations (around lines 40-110)**

Find the English translation block (starts around line 32 with `"tilt.label":`). Replace:

```javascript
  "tilt.sequential": "Closes then tilts",
```

with:

```javascript
  "tilt.sequential_close": "Closes then tilts closed",
  "tilt.sequential_open": "Closes then tilts open",
```

Also find the hint keys (around lines 92-95):

```javascript
  "hints.sequential.travel_time_close": "Start with cover fully open. Click Finish when the cover is fully closed, before the slats start tilting.",
  "hints.sequential.travel_time_open": "Start with cover closed and slats open. Click Finish when the cover is fully open.",
  "hints.sequential.tilt_time_close": "Start with cover closed but slats open. Click Finish when the slats are fully closed.",
  "hints.sequential.tilt_time_open": "Start with cover and slats closed. Click Finish when the slats are open.",
```

Replace with:

```javascript
  "hints.sequential_close.travel_time_close": "Start with cover fully open. Click Finish when the cover is fully closed, before the slats start tilting.",
  "hints.sequential_close.travel_time_open": "Start with cover closed and slats open. Click Finish when the cover is fully open.",
  "hints.sequential_close.tilt_time_close": "Start with cover closed but slats open. Click Finish when the slats are fully closed.",
  "hints.sequential_close.tilt_time_open": "Start with cover and slats closed. Click Finish when the slats are open.",
  "hints.sequential_open.travel_time_close": "Start with cover fully open and slats closed. Click Finish when the cover is fully closed, before the slats start tilting open.",
  "hints.sequential_open.travel_time_open": "Start with cover closed and slats closed. Click Finish when the cover is fully open.",
  "hints.sequential_open.tilt_time_close": "Start with cover closed but slats open. Click Finish when the slats are fully closed.",
  "hints.sequential_open.tilt_time_open": "Start with cover and slats closed. Click Finish when the slats are fully open.",
```

- [ ] **Step 2: Update Portuguese translations (around lines 134-193)**

Find the Portuguese block (starts around line 120 with `"pt": {`). Replace:

```javascript
    "tilt.sequential": "Fecha e depois inclina",
```

with:

```javascript
    "tilt.sequential_close": "Fecha e depois inclina fechadas",
    "tilt.sequential_open": "Fecha e depois inclina abertas",
```

Replace the four `hints.sequential.*` keys (around lines 182-185) with:

```javascript
    "hints.sequential_close.travel_time_close": "Comece com o estore totalmente aberto. Clique em Concluir quando o estore estiver totalmente fechado, antes de as lâminas começarem a inclinar.",
    "hints.sequential_close.travel_time_open": "Comece com o estore fechado e as lâminas abertas. Clique em Concluir quando o estore estiver totalmente aberto.",
    "hints.sequential_close.tilt_time_close": "Comece com o estore fechado mas as lâminas abertas. Clique em Concluir quando as lâminas estiverem totalmente fechadas.",
    "hints.sequential_close.tilt_time_open": "Comece com o estore e as lâminas fechados. Clique em Concluir quando as lâminas estiverem abertas.",
    "hints.sequential_open.travel_time_close": "Comece com o estore totalmente aberto e as lâminas fechadas. Clique em Concluir quando o estore estiver totalmente fechado, antes de as lâminas começarem a inclinar-se abertas.",
    "hints.sequential_open.travel_time_open": "Comece com o estore fechado e as lâminas fechadas. Clique em Concluir quando o estore estiver totalmente aberto.",
    "hints.sequential_open.tilt_time_close": "Comece com o estore fechado mas as lâminas abertas. Clique em Concluir quando as lâminas estiverem totalmente fechadas.",
    "hints.sequential_open.tilt_time_open": "Comece com o estore e as lâminas fechados. Clique em Concluir quando as lâminas estiverem totalmente abertas.",
```

- [ ] **Step 3: Update Polish translations (around lines 221-280)**

Find the Polish block (starts around line 207 with `"pl": {`). Replace:

```javascript
    "tilt.sequential": "Najpierw zamyka, potem nachyla",
```

with:

```javascript
    "tilt.sequential_close": "Najpierw zamyka, potem nachyla zamknięte",
    "tilt.sequential_open": "Najpierw zamyka, potem nachyla otwarte",
```

Replace the four `hints.sequential.*` keys (around lines 269-272) with:

```javascript
    "hints.sequential_close.travel_time_close": "Zacznij z roletą w pełni otwartą. Kliknij Zakończ, gdy roleta jest w pełni zamknięta, zanim listwy zaczną się nachylać.",
    "hints.sequential_close.travel_time_open": "Zacznij z zamkniętą roletą i otwartymi listwami. Kliknij Zakończ, gdy roleta jest w pełni otwarta.",
    "hints.sequential_close.tilt_time_close": "Zacznij z zamkniętą roletą, ale otwartymi listwami. Kliknij Zakończ, gdy listwy są w pełni zamknięte.",
    "hints.sequential_close.tilt_time_open": "Zacznij z zamkniętą roletą i zamkniętymi listwami. Kliknij Zakończ, gdy listwy są otwarte.",
    "hints.sequential_open.travel_time_close": "Zacznij z roletą w pełni otwartą i zamkniętymi listwami. Kliknij Zakończ, gdy roleta jest w pełni zamknięta, zanim listwy zaczną się nachylać otwarte.",
    "hints.sequential_open.travel_time_open": "Zacznij z zamkniętą roletą i zamkniętymi listwami. Kliknij Zakończ, gdy roleta jest w pełni otwarta.",
    "hints.sequential_open.tilt_time_close": "Zacznij z zamkniętą roletą, ale otwartymi listwami. Kliknij Zakończ, gdy listwy są w pełni zamknięte.",
    "hints.sequential_open.tilt_time_open": "Zacznij z zamkniętą roletą i zamkniętymi listwami. Kliknij Zakończ, gdy listwy są w pełni otwarte.",
```

- [ ] **Step 4: Update the dropdown (around lines 1023-1035)**

Find the tilt mode dropdown. Replace:

```javascript
          <option value="sequential" ?selected=${tiltMode === "sequential"}>
            ${this._t("tilt.sequential")}
          </option>
```

with:

```javascript
          <option value="sequential_close" ?selected=${tiltMode === "sequential_close"}>
            ${this._t("tilt.sequential_close")}
          </option>
          <option value="sequential_open" ?selected=${tiltMode === "sequential_open"}>
            ${this._t("tilt.sequential_open")}
          </option>
```

- [ ] **Step 5: Update `_onTiltModeChange` (around lines 610-653)**

The current handler checks `if (mode === "sequential")` to clear dual-motor fields. Both sequential variants want the same field-clearing behavior. Replace:

```javascript
      if (mode === "sequential") {
        // Clear dual-motor fields when switching to sequential
        updates.safe_tilt_position = null;
        updates.max_tilt_allowed_position = null;
        updates.tilt_open_switch = null;
        updates.tilt_close_switch = null;
        updates.tilt_stop_switch = null;
      } else if (mode === "dual_motor") {
```

with:

```javascript
      if (mode === "sequential_close" || mode === "sequential_open") {
        // Clear dual-motor fields when switching to either sequential variant
        updates.safe_tilt_position = null;
        updates.max_tilt_allowed_position = null;
        updates.tilt_open_switch = null;
        updates.tilt_close_switch = null;
        updates.tilt_stop_switch = null;
      } else if (mode === "dual_motor") {
```

- [ ] **Step 6: Grep for any remaining references to the old key**

Run: `grep -n '"sequential"' custom_components/cover_time_based/frontend/cover-time-based-card.js`

Expected: no matches (any match indicates a missed rename).

Also: `grep -n 'hints\.sequential\.' custom_components/cover_time_based/frontend/cover-time-based-card.js`

Expected: no matches.

- [ ] **Step 7: Manual verification**

This step is manual (frontend, no pytest coverage). Start a dev Home Assistant instance pointing at this repo, open the card, and verify:

1. The Tilt Mode dropdown shows three entries besides `Not supported`: "Closes then tilts closed", "Closes then tilts open", "Separate tilt motor", "Tilts inline with travel".
2. Selecting "Closes then tilts open" saves `tilt_mode: sequential_open` to the entry options.
3. The Calibration tab's hint text for each attribute matches what the spec calls for in each mode.

If you cannot run a dev HA instance, document this step as pending in the PR description.

- [ ] **Step 8: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat(ui): split sequential tilt into close/open variants"
```

---

## Task 12: Update README

Document the new mode in the tilt mode list.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the tilt mode description**

In `README.md`, find the "Tilt Mode" section (around line 117). Replace the `Sequential (closes then tilts)` bullet:

```markdown
- **Sequential (closes then tilts):** Tilting can only happen in the fully closed position. First the cover closes then the slats tilt closed. When opening, first the slats tilt open then the cover opens.
```

with:

```markdown
- **Sequential (closes then tilts closed):** Tilting can only happen in the fully closed position. First the cover closes then the slats tilt closed (motor drives further down past cover-closed to close the slats). When opening, the slats first tilt open (motor up) then the cover opens.
- **Sequential (closes then tilts open):** Mirror image of the above — for covers where slats articulate *open* when the motor drives further down past cover-closed, not closed. First the cover closes then the slats tilt open (motor continues down). When opening, the slats first tilt closed (motor up) then the cover opens.
```

Also, update the "Features" bullet at line 22 if the text mentions the number of tilt modes — currently it says "three tilt modes". Change to "four tilt modes" (close/open sequential, inline, dual-motor):

```markdown
- **Control the tilt of your cover based on time** with four tilt modes: inline, sequential closes-then-tilts-closed, sequential closes-then-tilts-open, or separate tilt motor.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document sequential_open tilt mode"
```

---

## Final verification

- [ ] **Step 1: Run the entire test suite**

Run: `pytest tests/ -v`
Expected: All tests pass, including new ones added for this feature.

- [ ] **Step 2: Run type-checking**

Run: `pyright custom_components/cover_time_based/`
Expected: No new errors introduced by this change (pre-existing errors may remain — compare against the pre-change baseline if unsure).

- [ ] **Step 3: Grep for stragglers**

Run: `grep -rn '"sequential"' custom_components/cover_time_based/ | grep -v sequential_close | grep -v sequential_open`

Expected: One line only — the legacy-alias branch in `_resolve_tilt_strategy` (the comment `# "sequential_close", legacy "sequential", or any unknown value → close variant`). Anything else indicates a missed rename.
