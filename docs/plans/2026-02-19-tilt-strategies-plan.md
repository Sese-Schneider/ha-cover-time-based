# Tilt Strategies Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the reactive tilt coupling interface with a command-based strategy system that returns `MovementStep` lists, redesign Sequential to use phased movement, and add a new Dual-Motor strategy.

**Architecture:** Strategies return `list[MovementStep]` (where steps are `TiltTo` or `TravelTo` dataclasses). The cover entity executes steps sequentially, grouping consecutive same-motor steps into continuous runs. Each strategy declares `name`, `uses_tilt_motor`, and `can_calibrate_tilt` properties.

**Tech Stack:** Python 3.12, Home Assistant custom component, xknx TravelCalculator, pytest

**Design doc:** `docs/plans/2026-02-19-tilt-strategies-design.md`

---

### Task 1: Add MovementStep dataclasses to base.py

**Files:**
- Modify: `custom_components/cover_time_based/tilt_strategies/base.py`
- Test: `tests/test_tilt_strategy.py`

**Step 1: Write the test**

Add to top of `tests/test_tilt_strategy.py`:

```python
from custom_components.cover_time_based.tilt_strategies import TiltTo, TravelTo


class TestMovementSteps:
    """Test MovementStep dataclasses."""

    def test_tilt_to_defaults(self):
        step = TiltTo(50)
        assert step.target == 50
        assert step.coupled_travel is None

    def test_tilt_to_with_coupling(self):
        step = TiltTo(50, coupled_travel=30)
        assert step.target == 50
        assert step.coupled_travel == 30

    def test_travel_to_defaults(self):
        step = TravelTo(30)
        assert step.target == 30
        assert step.coupled_tilt is None

    def test_travel_to_with_coupling(self):
        step = TravelTo(30, coupled_tilt=30)
        assert step.target == 30
        assert step.coupled_tilt == 30

    def test_equality(self):
        assert TiltTo(50) == TiltTo(50)
        assert TravelTo(30) == TravelTo(30)
        assert TiltTo(50) != TravelTo(50)
```

**Step 2: Run test to verify it fails**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_tilt_strategy.py::TestMovementSteps -v`
Expected: FAIL with ImportError (TiltTo/TravelTo not defined)

**Step 3: Implement MovementStep dataclasses**

Add to `custom_components/cover_time_based/tilt_strategies/base.py` after the imports, before `calc_coupled_target`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TiltTo:
    """Step: move tilt to target position."""

    target: int
    coupled_travel: int | None = None


@dataclass(frozen=True)
class TravelTo:
    """Step: move travel to target position."""

    target: int
    coupled_tilt: int | None = None


MovementStep = TiltTo | TravelTo
```

Update `custom_components/cover_time_based/tilt_strategies/__init__.py` to export:

```python
from .base import MovementStep, TiltStrategy, TiltTo, TravelTo, calc_coupled_target
```

And update `__all__`:

```python
__all__ = [
    "MovementStep",
    "TiltStrategy",
    "TiltTo",
    "TravelTo",
    "calc_coupled_target",
    "ProportionalTilt",
    "SequentialTilt",
]
```

**Step 4: Run test to verify it passes**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_tilt_strategy.py::TestMovementSteps -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /workspaces/ha-cover-time-based && git add custom_components/cover_time_based/tilt_strategies/base.py custom_components/cover_time_based/tilt_strategies/__init__.py tests/test_tilt_strategy.py && git commit -m "feat: add MovementStep dataclasses (TiltTo, TravelTo)"
```

---

### Task 2: Add new abstract interface to TiltStrategy ABC

Add `name`, `uses_tilt_motor`, `plan_move_position`, `plan_move_tilt`, and `snap_trackers_to_physical` to the ABC. Keep the old methods for now (they'll be removed after cover_base migration). This lets us add the new interface without breaking existing code.

**Files:**
- Modify: `custom_components/cover_time_based/tilt_strategies/base.py`

**Step 1: Add new abstract methods to TiltStrategy**

Add after the existing abstract methods in the `TiltStrategy` class in `base.py`:

```python
    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for config/state."""

    @property
    @abstractmethod
    def uses_tilt_motor(self) -> bool:
        """Whether TiltTo steps require a separate tilt motor."""

    @abstractmethod
    def plan_move_position(
        self,
        target_pos: int,
        current_pos: int,
        current_tilt: int,
    ) -> list[TiltTo | TravelTo]:
        """Plan steps to move cover to target_pos."""

    @abstractmethod
    def plan_move_tilt(
        self,
        target_tilt: int,
        current_pos: int,
        current_tilt: int,
    ) -> list[TiltTo | TravelTo]:
        """Plan steps to move tilt to target_tilt."""

    @abstractmethod
    def snap_trackers_to_physical(
        self,
        travel_calc: TravelCalculator,
        tilt_calc: TravelCalculator,
    ) -> None:
        """Correct tracker drift after stop to match physical reality."""
```

**Step 2: Run tests to verify they still pass (old interface intact)**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_tilt_strategy.py -v`
Expected: FAIL — existing concrete classes don't implement the new abstract methods yet. This is expected; we'll fix in Tasks 3 and 4.

**Step 3: Commit**

```bash
cd /workspaces/ha-cover-time-based && git add custom_components/cover_time_based/tilt_strategies/base.py && git commit -m "feat: add new command-based abstract methods to TiltStrategy ABC"
```

---

### Task 3: Implement new interface on ProportionalTilt

**Files:**
- Modify: `custom_components/cover_time_based/tilt_strategies/proportional.py`
- Test: `tests/test_tilt_strategy.py`

**Step 1: Write the failing tests**

Add to `tests/test_tilt_strategy.py`:

```python
from custom_components.cover_time_based.tilt_strategies import TiltTo, TravelTo


class TestProportionalTiltProperties:
    """Test ProportionalTilt name and uses_tilt_motor properties."""

    def test_name(self):
        assert ProportionalTilt().name == "proportional"

    def test_uses_tilt_motor(self):
        assert ProportionalTilt().uses_tilt_motor is False


class TestProportionalPlanMovePosition:
    """Test ProportionalTilt.plan_move_position."""

    def test_returns_travel_with_coupled_tilt(self):
        strategy = ProportionalTilt()
        steps = strategy.plan_move_position(target_pos=30, current_pos=100, current_tilt=100)
        assert steps == [TravelTo(30, coupled_tilt=30)]

    def test_fully_open(self):
        strategy = ProportionalTilt()
        steps = strategy.plan_move_position(target_pos=0, current_pos=100, current_tilt=100)
        assert steps == [TravelTo(0, coupled_tilt=0)]

    def test_fully_closed(self):
        strategy = ProportionalTilt()
        steps = strategy.plan_move_position(target_pos=100, current_pos=0, current_tilt=0)
        assert steps == [TravelTo(100, coupled_tilt=100)]


class TestProportionalPlanMoveTilt:
    """Test ProportionalTilt.plan_move_tilt."""

    def test_returns_tilt_with_coupled_travel(self):
        strategy = ProportionalTilt()
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=80, current_tilt=100)
        assert steps == [TiltTo(50, coupled_travel=50)]

    def test_fully_open(self):
        strategy = ProportionalTilt()
        steps = strategy.plan_move_tilt(target_tilt=0, current_pos=50, current_tilt=50)
        assert steps == [TiltTo(0, coupled_travel=0)]


class TestProportionalSnapTrackers:
    """Test ProportionalTilt.snap_trackers_to_physical."""

    def test_forces_tilt_to_zero_at_travel_zero(self):
        strategy = ProportionalTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(0)
        tilt.set_position(5)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0

    def test_forces_tilt_to_100_at_travel_100(self):
        strategy = ProportionalTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(100)
        tilt.set_position(95)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 100

    def test_no_op_at_midpoint(self):
        strategy = ProportionalTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(50)
        tilt.set_position(30)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 30
```

**Step 2: Run tests to verify they fail**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_tilt_strategy.py::TestProportionalTiltProperties tests/test_tilt_strategy.py::TestProportionalPlanMovePosition tests/test_tilt_strategy.py::TestProportionalPlanMoveTilt tests/test_tilt_strategy.py::TestProportionalSnapTrackers -v`
Expected: FAIL — ProportionalTilt can't be instantiated (missing abstract methods)

**Step 3: Implement new methods on ProportionalTilt**

In `custom_components/cover_time_based/tilt_strategies/proportional.py`, add to the `ProportionalTilt` class:

```python
    @property
    def name(self) -> str:
        """Strategy name."""
        return "proportional"

    @property
    def uses_tilt_motor(self) -> bool:
        """Proportional uses the same motor for tilt and travel."""
        return False

    def plan_move_position(
        self,
        target_pos: int,
        current_pos: int,
        current_tilt: int,
    ) -> list[TiltTo | TravelTo]:
        """Travel and tilt move together — single coupled step."""
        return [TravelTo(target_pos, coupled_tilt=target_pos)]

    def plan_move_tilt(
        self,
        target_tilt: int,
        current_pos: int,
        current_tilt: int,
    ) -> list[TiltTo | TravelTo]:
        """Tilt and travel move together — single coupled step."""
        return [TiltTo(target_tilt, coupled_travel=target_tilt)]

    def snap_trackers_to_physical(
        self,
        travel_calc: TravelCalculator,
        tilt_calc: TravelCalculator,
    ) -> None:
        """Force tilt to match at travel boundaries (0% or 100%)."""
        current_travel = travel_calc.current_position()
        current_tilt = tilt_calc.current_position()

        if current_travel == 0 and current_tilt != 0:
            _LOGGER.debug(
                "ProportionalTilt :: Travel at 0%%, forcing tilt to 0%% (was %d%%)",
                current_tilt,
            )
            tilt_calc.set_position(0)
        elif current_travel == 100 and current_tilt != 100:
            _LOGGER.debug(
                "ProportionalTilt :: Travel at 100%%, forcing tilt to 100%% (was %d%%)",
                current_tilt,
            )
            tilt_calc.set_position(100)
```

Add imports at top of proportional.py:

```python
from .base import TiltTo, TravelTo
```

**Step 4: Run tests to verify they pass**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_tilt_strategy.py -v`
Expected: PASS (all new and existing tests)

**Step 5: Commit**

```bash
cd /workspaces/ha-cover-time-based && git add custom_components/cover_time_based/tilt_strategies/proportional.py tests/test_tilt_strategy.py && git commit -m "feat: implement command-based interface on ProportionalTilt"
```

---

### Task 4: Redesign SequentialTilt with phased movement

The Sequential strategy changes fundamentally: tilt only happens at position 100 (closed endpoint). plan_move_position returns `[TiltTo(0), TravelTo(x)]`. plan_move_tilt returns `[TravelTo(100), TiltTo(x)]`.

**Files:**
- Modify: `custom_components/cover_time_based/tilt_strategies/sequential.py`
- Test: `tests/test_tilt_strategy.py`

**Step 1: Write the failing tests**

Add to `tests/test_tilt_strategy.py`:

```python
class TestSequentialTiltProperties:
    """Test SequentialTilt name and uses_tilt_motor properties."""

    def test_name(self):
        assert SequentialTilt().name == "sequential"

    def test_uses_tilt_motor(self):
        assert SequentialTilt().uses_tilt_motor is False


class TestSequentialPlanMovePosition:
    """Test SequentialTilt.plan_move_position."""

    def test_flattens_tilt_before_travel(self):
        """When tilt is not 0, flatten slats first then travel."""
        strategy = SequentialTilt()
        steps = strategy.plan_move_position(target_pos=30, current_pos=100, current_tilt=80)
        assert steps == [TiltTo(0), TravelTo(30)]

    def test_skips_tilt_when_already_flat(self):
        """When tilt is already 0, just travel."""
        strategy = SequentialTilt()
        steps = strategy.plan_move_position(target_pos=30, current_pos=100, current_tilt=0)
        assert steps == [TravelTo(30)]

    def test_opening_fully(self):
        strategy = SequentialTilt()
        steps = strategy.plan_move_position(target_pos=0, current_pos=100, current_tilt=100)
        assert steps == [TiltTo(0), TravelTo(0)]

    def test_closing_fully_from_open(self):
        """Closing from open — tilt is already 0, just travel."""
        strategy = SequentialTilt()
        steps = strategy.plan_move_position(target_pos=100, current_pos=0, current_tilt=0)
        assert steps == [TravelTo(100)]

    def test_partial_move_with_flat_tilt(self):
        strategy = SequentialTilt()
        steps = strategy.plan_move_position(target_pos=50, current_pos=80, current_tilt=0)
        assert steps == [TravelTo(50)]


class TestSequentialPlanMoveTilt:
    """Test SequentialTilt.plan_move_tilt."""

    def test_travels_to_closed_before_tilting(self):
        """When not at position 100, travel there first."""
        strategy = SequentialTilt()
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=30, current_tilt=0)
        assert steps == [TravelTo(100), TiltTo(50)]

    def test_tilts_directly_when_at_closed(self):
        """When already at position 100, just tilt."""
        strategy = SequentialTilt()
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=100, current_tilt=0)
        assert steps == [TiltTo(50)]

    def test_tilt_fully_closed(self):
        strategy = SequentialTilt()
        steps = strategy.plan_move_tilt(target_tilt=100, current_pos=100, current_tilt=0)
        assert steps == [TiltTo(100)]

    def test_tilt_open_from_partially_tilted(self):
        strategy = SequentialTilt()
        steps = strategy.plan_move_tilt(target_tilt=0, current_pos=100, current_tilt=50)
        assert steps == [TiltTo(0)]


class TestSequentialSnapTrackers:
    """Test SequentialTilt.snap_trackers_to_physical."""

    def test_forces_tilt_to_zero_when_not_at_closed(self):
        """When position is not 100, slats must be flat (tilt=0)."""
        strategy = SequentialTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(50)
        tilt.set_position(30)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0

    def test_no_op_when_at_closed(self):
        """When position is 100, tilt can be anything."""
        strategy = SequentialTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(100)
        tilt.set_position(50)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 50

    def test_no_op_when_already_flat(self):
        """When tilt is already 0, no change needed."""
        strategy = SequentialTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(30)
        tilt.set_position(0)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0

    def test_forces_at_fully_open(self):
        """Position 0 (fully open) — tilt must be 0."""
        strategy = SequentialTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(0)
        tilt.set_position(10)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_tilt_strategy.py::TestSequentialTiltProperties tests/test_tilt_strategy.py::TestSequentialPlanMovePosition tests/test_tilt_strategy.py::TestSequentialPlanMoveTilt tests/test_tilt_strategy.py::TestSequentialSnapTrackers -v`
Expected: FAIL

**Step 3: Implement new methods on SequentialTilt**

Replace the entire `custom_components/cover_time_based/tilt_strategies/sequential.py`:

```python
"""Sequential tilt strategy.

Single motor. Tilt mechanism only engages at position 100% (fully closed).
Opening from closed: tilt phase (slats open) then travel phase.
Closing to closed: travel phase then tilt phase.
Tilt-only commands require traveling to position 100% first.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import TiltStrategy, TiltTo, TravelTo, calc_coupled_target

if TYPE_CHECKING:
    from xknx.devices import TravelCalculator

_LOGGER = logging.getLogger(__name__)


class SequentialTilt(TiltStrategy):
    """Sequential tilt mode — phased single-motor movement.

    Tilt only engages at position 100 (closed endpoint).
    """

    @property
    def name(self) -> str:
        """Strategy name."""
        return "sequential"

    @property
    def uses_tilt_motor(self) -> bool:
        """Sequential uses the same motor for tilt and travel."""
        return False

    def plan_move_position(
        self,
        target_pos: int,
        current_pos: int,
        current_tilt: int,
    ) -> list[TiltTo | TravelTo]:
        """Flatten slats before travel."""
        steps: list[TiltTo | TravelTo] = []
        if current_tilt != 0:
            steps.append(TiltTo(0))
        steps.append(TravelTo(target_pos))
        return steps

    def plan_move_tilt(
        self,
        target_tilt: int,
        current_pos: int,
        current_tilt: int,
    ) -> list[TiltTo | TravelTo]:
        """Travel to closed position first, then tilt."""
        steps: list[TiltTo | TravelTo] = []
        if current_pos != 100:
            steps.append(TravelTo(100))
        steps.append(TiltTo(target_tilt))
        return steps

    def snap_trackers_to_physical(
        self,
        travel_calc: TravelCalculator,
        tilt_calc: TravelCalculator,
    ) -> None:
        """When not at closed endpoint, slats must be flat."""
        current_travel = travel_calc.current_position()
        current_tilt = tilt_calc.current_position()
        if current_travel != 100 and current_tilt != 0:
            _LOGGER.debug(
                "SequentialTilt :: Travel at %d%% (not closed), forcing tilt to 0%% (was %d%%)",
                current_travel,
                current_tilt,
            )
            tilt_calc.set_position(0)

    # --- Legacy interface (kept until cover_base.py migrates) ---

    def calc_tilt_for_travel(
        self,
        movement_time: float,
        closing: bool,
        tilt_calc: TravelCalculator,
        tilt_time_close: float,
        tilt_time_open: float,
    ) -> int | None:
        """Return proportional tilt target when travel moves."""
        return calc_coupled_target(
            movement_time, closing, tilt_calc, tilt_time_close, tilt_time_open
        )

    def calc_travel_for_tilt(
        self,
        movement_time: float,
        closing: bool,
        travel_calc: TravelCalculator,
        travel_time_close: float,
        travel_time_open: float,
    ) -> int | None:
        """Tilt movement does not couple travel in sequential mode."""
        return None

    def enforce_constraints(
        self,
        travel_calc: TravelCalculator,
        tilt_calc: TravelCalculator,
    ) -> None:
        """No constraints in old sequential mode."""

    def can_calibrate_tilt(self) -> bool:
        """Tilt calibration is allowed in sequential mode."""
        return True
```

**Step 4: Run all tests to verify they pass**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_tilt_strategy.py -v`
Expected: PASS (all new and existing tests)

**Step 5: Commit**

```bash
cd /workspaces/ha-cover-time-based && git add custom_components/cover_time_based/tilt_strategies/sequential.py tests/test_tilt_strategy.py && git commit -m "feat: redesign SequentialTilt with phased movement model"
```

---

### Task 5: Add DualMotorTilt strategy

**Files:**
- Create: `custom_components/cover_time_based/tilt_strategies/dual_motor.py`
- Modify: `custom_components/cover_time_based/tilt_strategies/__init__.py`
- Test: `tests/test_tilt_strategy.py`

**Step 1: Write the failing tests**

Add to `tests/test_tilt_strategy.py`:

```python
from custom_components.cover_time_based.tilt_strategies import DualMotorTilt


class TestDualMotorTiltProperties:
    """Test DualMotorTilt name and uses_tilt_motor properties."""

    def test_name(self):
        assert DualMotorTilt().name == "dual_motor"

    def test_uses_tilt_motor(self):
        assert DualMotorTilt().uses_tilt_motor is True

    def test_can_calibrate_tilt(self):
        assert DualMotorTilt().can_calibrate_tilt() is True


class TestDualMotorPlanMovePosition:
    """Test DualMotorTilt.plan_move_position."""

    def test_moves_tilt_to_safe_before_travel(self):
        strategy = DualMotorTilt(safe_tilt_position=0)
        steps = strategy.plan_move_position(target_pos=30, current_pos=100, current_tilt=50)
        assert steps == [TiltTo(0), TravelTo(30)]

    def test_skips_tilt_when_already_safe(self):
        strategy = DualMotorTilt(safe_tilt_position=0)
        steps = strategy.plan_move_position(target_pos=30, current_pos=100, current_tilt=0)
        assert steps == [TravelTo(30)]

    def test_custom_safe_position(self):
        strategy = DualMotorTilt(safe_tilt_position=50)
        steps = strategy.plan_move_position(target_pos=30, current_pos=100, current_tilt=80)
        assert steps == [TiltTo(50), TravelTo(30)]

    def test_already_at_custom_safe(self):
        strategy = DualMotorTilt(safe_tilt_position=50)
        steps = strategy.plan_move_position(target_pos=30, current_pos=100, current_tilt=50)
        assert steps == [TravelTo(30)]


class TestDualMotorPlanMoveTilt:
    """Test DualMotorTilt.plan_move_tilt."""

    def test_tilts_directly_when_no_boundary(self):
        strategy = DualMotorTilt()
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=30, current_tilt=0)
        assert steps == [TiltTo(50)]

    def test_travels_to_boundary_when_below_min(self):
        strategy = DualMotorTilt(min_tilt_allowed_position=80)
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=30, current_tilt=0)
        assert steps == [TravelTo(80), TiltTo(50)]

    def test_tilts_directly_when_at_boundary(self):
        strategy = DualMotorTilt(min_tilt_allowed_position=80)
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=80, current_tilt=0)
        assert steps == [TiltTo(50)]

    def test_tilts_directly_when_beyond_boundary(self):
        strategy = DualMotorTilt(min_tilt_allowed_position=80)
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=100, current_tilt=0)
        assert steps == [TiltTo(50)]

    def test_no_boundary_set(self):
        strategy = DualMotorTilt(min_tilt_allowed_position=None)
        steps = strategy.plan_move_tilt(target_tilt=50, current_pos=10, current_tilt=0)
        assert steps == [TiltTo(50)]


class TestDualMotorSnapTrackers:
    """Test DualMotorTilt.snap_trackers_to_physical."""

    def test_forces_tilt_to_safe_when_below_min(self):
        strategy = DualMotorTilt(safe_tilt_position=0, min_tilt_allowed_position=80)
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(50)
        tilt.set_position(30)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0

    def test_no_op_when_at_boundary(self):
        strategy = DualMotorTilt(safe_tilt_position=0, min_tilt_allowed_position=80)
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(80)
        tilt.set_position(30)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 30

    def test_no_op_when_no_boundary(self):
        strategy = DualMotorTilt(safe_tilt_position=0, min_tilt_allowed_position=None)
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(30)
        tilt.set_position(50)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 50

    def test_already_at_safe_position(self):
        strategy = DualMotorTilt(safe_tilt_position=0, min_tilt_allowed_position=80)
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(50)
        tilt.set_position(0)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_tilt_strategy.py::TestDualMotorTiltProperties tests/test_tilt_strategy.py::TestDualMotorPlanMovePosition tests/test_tilt_strategy.py::TestDualMotorPlanMoveTilt tests/test_tilt_strategy.py::TestDualMotorSnapTrackers -v`
Expected: FAIL with ImportError

**Step 3: Create dual_motor.py**

Create `custom_components/cover_time_based/tilt_strategies/dual_motor.py`:

```python
"""Dual-motor tilt strategy.

Separate tilt motor with its own switch entities. Optionally boundary-locked
(tilt only allowed when position >= min_tilt_allowed_position). Before travel,
slats move to a configurable safe position.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import TiltStrategy, TiltTo, TravelTo

if TYPE_CHECKING:
    from xknx.devices import TravelCalculator

_LOGGER = logging.getLogger(__name__)


class DualMotorTilt(TiltStrategy):
    """Dual-motor tilt — independent tilt motor with optional boundary lock."""

    def __init__(
        self,
        safe_tilt_position: int = 0,
        min_tilt_allowed_position: int | None = None,
    ) -> None:
        """Initialize with optional safety and boundary parameters."""
        self._safe_tilt_position = safe_tilt_position
        self._min_tilt_allowed_position = min_tilt_allowed_position

    @property
    def name(self) -> str:
        """Strategy name."""
        return "dual_motor"

    @property
    def uses_tilt_motor(self) -> bool:
        """Dual-motor uses a separate tilt motor."""
        return True

    def plan_move_position(
        self,
        target_pos: int,
        current_pos: int,
        current_tilt: int,
    ) -> list[TiltTo | TravelTo]:
        """Move tilt to safe position first, then travel."""
        steps: list[TiltTo | TravelTo] = []
        if current_tilt != self._safe_tilt_position:
            steps.append(TiltTo(self._safe_tilt_position))
        steps.append(TravelTo(target_pos))
        return steps

    def plan_move_tilt(
        self,
        target_tilt: int,
        current_pos: int,
        current_tilt: int,
    ) -> list[TiltTo | TravelTo]:
        """Travel to boundary if needed, then tilt."""
        steps: list[TiltTo | TravelTo] = []
        if (
            self._min_tilt_allowed_position is not None
            and current_pos < self._min_tilt_allowed_position
        ):
            steps.append(TravelTo(self._min_tilt_allowed_position))
        steps.append(TiltTo(target_tilt))
        return steps

    def snap_trackers_to_physical(
        self,
        travel_calc: TravelCalculator,
        tilt_calc: TravelCalculator,
    ) -> None:
        """If below boundary, tilt must be at safe position."""
        if self._min_tilt_allowed_position is None:
            return
        current_travel = travel_calc.current_position()
        current_tilt = tilt_calc.current_position()
        if (
            current_travel < self._min_tilt_allowed_position
            and current_tilt != self._safe_tilt_position
        ):
            _LOGGER.debug(
                "DualMotorTilt :: Travel at %d%% (below min %d%%), "
                "forcing tilt to safe %d%% (was %d%%)",
                current_travel,
                self._min_tilt_allowed_position,
                self._safe_tilt_position,
                current_tilt,
            )
            tilt_calc.set_position(self._safe_tilt_position)

    # --- Legacy interface (stubs for ABC compliance, not used for dual_motor) ---

    def calc_tilt_for_travel(self, movement_time, closing, tilt_calc, tilt_time_close, tilt_time_open):
        """Not used in dual-motor mode."""
        return None

    def calc_travel_for_tilt(self, movement_time, closing, travel_calc, travel_time_close, travel_time_open):
        """Not used in dual-motor mode."""
        return None

    def enforce_constraints(self, travel_calc, tilt_calc):
        """Delegate to snap_trackers_to_physical."""
        self.snap_trackers_to_physical(travel_calc, tilt_calc)

    def can_calibrate_tilt(self):
        """Tilt calibration is allowed in dual-motor mode."""
        return True
```

Update `__init__.py`:

```python
"""Tilt strategy classes for cover_time_based.

Tilt strategies determine how travel and tilt movements are coupled.
"""

from .base import MovementStep, TiltStrategy, TiltTo, TravelTo, calc_coupled_target
from .dual_motor import DualMotorTilt
from .proportional import ProportionalTilt
from .sequential import SequentialTilt

__all__ = [
    "DualMotorTilt",
    "MovementStep",
    "TiltStrategy",
    "TiltTo",
    "TravelTo",
    "calc_coupled_target",
    "ProportionalTilt",
    "SequentialTilt",
]
```

**Step 4: Run all tilt strategy tests**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_tilt_strategy.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /workspaces/ha-cover-time-based && git add custom_components/cover_time_based/tilt_strategies/ tests/test_tilt_strategy.py && git commit -m "feat: add DualMotorTilt strategy with boundary lock and safety"
```

---

### Task 6: Update extra_state_attributes to use strategy.name

Replace the `isinstance` checks with the `name` property.

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py:283-289`
- Test: `tests/test_base_movement.py` (existing tests should still pass)

**Step 1: Update cover_base.py**

Replace the `isinstance` block in `extra_state_attributes` (around line 283):

```python
        if self._tilt_strategy is not None:
            attr[CONF_TILT_MODE] = self._tilt_strategy.name
```

Remove the `from .tilt_strategies import ProportionalTilt, SequentialTilt` import that was inside this method.

**Step 2: Run tests to verify nothing breaks**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/ -v`
Expected: PASS (all 217+ tests)

**Step 3: Commit**

```bash
cd /workspaces/ha-cover-time-based && git add custom_components/cover_time_based/cover_base.py && git commit -m "refactor: use strategy.name property for state attributes"
```

---

### Task 7: Update _resolve_tilt_strategy for dual_motor

**Files:**
- Modify: `custom_components/cover_time_based/cover.py:238-249`
- Test: `tests/test_cover_factory.py` (add factory-level tilt tests)

**Step 1: Write the failing tests**

Add to `tests/test_cover_factory.py` (or create if needed):

```python
from custom_components.cover_time_based.cover import _resolve_tilt_strategy
from custom_components.cover_time_based.tilt_strategies import (
    DualMotorTilt,
    ProportionalTilt,
    SequentialTilt,
)


class TestResolveTiltStrategy:
    """Test _resolve_tilt_strategy factory function."""

    def test_none_when_no_tilt_times(self):
        result = _resolve_tilt_strategy("sequential", None, None)
        assert result is None

    def test_none_when_tilt_mode_none(self):
        result = _resolve_tilt_strategy("none", 2.0, 2.0)
        assert result is None

    def test_sequential(self):
        result = _resolve_tilt_strategy("sequential", 2.0, 2.0)
        assert isinstance(result, SequentialTilt)

    def test_proportional(self):
        result = _resolve_tilt_strategy("proportional", 2.0, 2.0)
        assert isinstance(result, ProportionalTilt)

    def test_dual_motor_defaults(self):
        result = _resolve_tilt_strategy("dual_motor", 2.0, 2.0)
        assert isinstance(result, DualMotorTilt)

    def test_dual_motor_with_options(self):
        result = _resolve_tilt_strategy(
            "dual_motor", 2.0, 2.0,
            safe_tilt_position=10,
            min_tilt_allowed_position=80,
        )
        assert isinstance(result, DualMotorTilt)
        assert result._safe_tilt_position == 10
        assert result._min_tilt_allowed_position == 80

    def test_unknown_mode_defaults_to_sequential(self):
        result = _resolve_tilt_strategy("unknown", 2.0, 2.0)
        assert isinstance(result, SequentialTilt)
```

**Step 2: Run tests to verify they fail**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_cover_factory.py::TestResolveTiltStrategy -v`
Expected: FAIL (dual_motor tests fail, none mode not handled)

**Step 3: Update _resolve_tilt_strategy**

In `custom_components/cover_time_based/cover.py`, update `_resolve_tilt_strategy`:

```python
def _resolve_tilt_strategy(tilt_mode_str, tilt_time_close, tilt_time_open, **kwargs):
    """Map tilt_mode config string to a TiltStrategy instance (or None)."""
    from .tilt_strategies import DualMotorTilt, ProportionalTilt, SequentialTilt

    if tilt_mode_str == "none":
        return None

    has_tilt_times = tilt_time_close is not None and tilt_time_open is not None
    if not has_tilt_times:
        return None

    if tilt_mode_str == "proportional":
        return ProportionalTilt()
    if tilt_mode_str == "dual_motor":
        return DualMotorTilt(
            safe_tilt_position=kwargs.get("safe_tilt_position", 0),
            min_tilt_allowed_position=kwargs.get("min_tilt_allowed_position"),
        )
    # "sequential" or any other value with tilt times -> sequential
    return SequentialTilt()
```

Also update `_create_cover_from_options` to pass the new kwargs:

```python
    tilt_strategy = _resolve_tilt_strategy(
        tilt_mode_str,
        options.get(CONF_TILT_TIME_CLOSE),
        options.get(CONF_TILT_TIME_OPEN),
        safe_tilt_position=options.get("safe_tilt_position", 0),
        min_tilt_allowed_position=options.get("min_tilt_allowed_position"),
    )
```

**Step 4: Run tests**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/ -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /workspaces/ha-cover-time-based && git add custom_components/cover_time_based/cover.py tests/test_cover_factory.py && git commit -m "feat: add dual_motor to strategy factory with config passthrough"
```

---

### Task 8: Update websocket_api to accept dual_motor

**Files:**
- Modify: `custom_components/cover_time_based/websocket_api.py:151`
- Test: `tests/test_websocket_api.py`

**Step 1: Update validation**

Change line 151 in `websocket_api.py`:

```python
vol.Optional("tilt_mode"): vol.In(["none", "sequential", "proportional", "dual_motor"]),
```

Also add the new config fields to the validation schema:

```python
vol.Optional("safe_tilt_position"): vol.All(int, vol.Range(min=0, max=100)),
vol.Optional("min_tilt_allowed_position"): vol.Any(None, vol.All(int, vol.Range(min=0, max=100))),
vol.Optional("tilt_open_switch"): str,
vol.Optional("tilt_close_switch"): str,
vol.Optional("tilt_stop_switch"): str,
```

**Step 2: Run tests**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_websocket_api.py -v`
Expected: PASS

**Step 3: Commit**

```bash
cd /workspaces/ha-cover-time-based && git add custom_components/cover_time_based/websocket_api.py && git commit -m "feat: add dual_motor config options to websocket API"
```

---

### Task 9: Add CONF constants for new dual-motor config

**Files:**
- Modify: `custom_components/cover_time_based/cover.py` (add constants)
- Modify: `custom_components/cover_time_based/cover_base.py` (add constants if needed)

**Step 1: Add constants**

In `cover.py`, add after the existing CONF constants:

```python
CONF_SAFE_TILT_POSITION = "safe_tilt_position"
CONF_MIN_TILT_ALLOWED_POSITION = "min_tilt_allowed_position"
CONF_TILT_OPEN_SWITCH = "tilt_open_switch"
CONF_TILT_CLOSE_SWITCH = "tilt_close_switch"
CONF_TILT_STOP_SWITCH = "tilt_stop_switch"
```

Update `_create_cover_from_options` to use the constants instead of string literals.

**Step 2: Run tests**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/ -v`
Expected: PASS

**Step 3: Commit**

```bash
cd /workspaces/ha-cover-time-based && git add custom_components/cover_time_based/cover.py custom_components/cover_time_based/cover_base.py && git commit -m "feat: add CONF constants for dual-motor config options"
```

---

### Task 10: Remove old abstract methods from TiltStrategy ABC

Now that all three strategies implement the new interface, and the old methods are only kept as legacy stubs, remove the old abstract methods from the ABC. The concrete implementations will keep their legacy methods until cover_base.py is migrated (separate PR scope).

**Files:**
- Modify: `custom_components/cover_time_based/tilt_strategies/base.py`

**Step 1: Remove old abstract methods**

Remove `calc_tilt_for_travel`, `calc_travel_for_tilt`, `enforce_constraints`, and `can_calibrate_tilt` from the `TiltStrategy` ABC. Keep them as concrete methods on the subclasses for backward compatibility with cover_base.py.

Note: `can_calibrate_tilt` is still part of the new interface. Keep it in the ABC.

Actually, on reflection, `can_calibrate_tilt` should stay as an abstract method since it's part of the new interface too. Remove only:
- `calc_tilt_for_travel`
- `calc_travel_for_tilt`
- `enforce_constraints` (replaced by `snap_trackers_to_physical`)

**Step 2: Run all tests**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/ -v`
Expected: PASS (all tests, since cover_base still calls the concrete methods on subclasses)

**Step 3: Commit**

```bash
cd /workspaces/ha-cover-time-based && git add custom_components/cover_time_based/tilt_strategies/base.py && git commit -m "refactor: remove old reactive abstract methods from TiltStrategy ABC"
```

---

### Task 11: Run full verification

**Step 1: Run all tests**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/ -x -v`
Expected: All tests PASS

**Step 2: Run ruff**

Run: `cd /workspaces/ha-cover-time-based && ruff check . && ruff format .`
Expected: All checks passed

**Step 3: Run pyright on source**

Run: `cd /workspaces/ha-cover-time-based && npx pyright custom_components/`
Expected: Same pre-existing errors as before (websocket_api import issues), no new errors

**Step 4: Update translations if needed**

Check if any new strings.json entries are needed for the new tilt_mode option ("dual_motor") in `custom_components/cover_time_based/strings.json`.

---

## Notes for Implementer

### What this plan covers:
- New `MovementStep` dataclasses (`TiltTo`, `TravelTo`)
- New command-based interface on `TiltStrategy` ABC
- Redesigned `SequentialTilt` with phased movement model
- New `DualMotorTilt` strategy
- Updated factory, websocket API, and state attributes
- Tests for all of the above

### What this plan does NOT cover (future work):
- **Cover entity execution model** — migrating `cover_base.py` from old reactive interface to executing `MovementStep` lists. This is a large change that should be a separate PR.
- **Tilt switch entity wiring** — actually activating separate tilt motor switches for dual-motor mode.
- **Config flow UI** — adding dual_motor option to the UI config flow.
- **Translation updates** — adding dual_motor to strings.json.

The strategy layer is complete and testable independently. The cover_base migration is the next major PR.
