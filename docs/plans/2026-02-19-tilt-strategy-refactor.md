# Tilt Strategy Refactor — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract tilt mode logic from `cover_base.py` into a Strategy pattern, rename `"during"` → `"proportional"` and `"before_after"` → `"sequential"`, preserving all current behavior exactly.

**Architecture:** Composition over inheritance — a `TiltStrategy` protocol with `SequentialTilt` and `ProportionalTilt` implementations. The base class delegates tilt-mode-specific decisions to the strategy. Config strings map to strategy instances in the factory.

**Tech Stack:** Python, Home Assistant custom component, xknx TravelCalculator, pytest

---

### Task 1: Create `tilt_strategy.py` with strategy classes

**Files:**
- Create: `custom_components/cover_time_based/tilt_strategy.py`
- Test: `tests/test_tilt_strategy.py`

**Step 1: Write failing tests for the strategy interface**

Create `tests/test_tilt_strategy.py`:

```python
"""Tests for tilt strategy classes."""

import pytest
from xknx.devices import TravelCalculator

from custom_components.cover_time_based.tilt_strategy import (
    ProportionalTilt,
    SequentialTilt,
)


class TestSequentialTilt:
    """SequentialTilt: current 'before_after' behavior."""

    def test_calc_tilt_for_travel_closing(self):
        """When travel closes, tilt should couple proportionally."""
        strategy = SequentialTilt()
        tilt_calc = TravelCalculator(5.0, 5.0)
        tilt_calc.set_position(0)
        # 3s of 30s travel → (3/5)*100 = 60% tilt distance
        result = strategy.calc_tilt_for_travel(3.0, True, tilt_calc, 5.0, 5.0)
        assert result == 60  # 0 + 60 = 60

    def test_calc_tilt_for_travel_opening(self):
        strategy = SequentialTilt()
        tilt_calc = TravelCalculator(5.0, 5.0)
        tilt_calc.set_position(100)
        result = strategy.calc_tilt_for_travel(2.5, False, tilt_calc, 5.0, 5.0)
        assert result == 50  # 100 - 50 = 50

    def test_calc_travel_for_tilt_returns_none(self):
        """Sequential: tilt movement does NOT couple travel."""
        strategy = SequentialTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        travel_calc.set_position(50)
        result = strategy.calc_travel_for_tilt(2.0, True, travel_calc, 30.0, 30.0)
        assert result is None

    def test_enforce_constraints_is_noop(self):
        """Sequential: no constraints enforced."""
        strategy = SequentialTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        tilt_calc = TravelCalculator(5.0, 5.0)
        travel_calc.set_position(0)
        tilt_calc.set_position(50)
        strategy.enforce_constraints(travel_calc, tilt_calc)
        assert tilt_calc.current_position() == 50  # unchanged

    def test_can_calibrate_tilt(self):
        assert SequentialTilt().can_calibrate_tilt() is True


class TestProportionalTilt:
    """ProportionalTilt: current 'during' behavior."""

    def test_calc_tilt_for_travel_closing(self):
        strategy = ProportionalTilt()
        tilt_calc = TravelCalculator(5.0, 5.0)
        tilt_calc.set_position(0)
        result = strategy.calc_tilt_for_travel(3.0, True, tilt_calc, 5.0, 5.0)
        assert result == 60

    def test_calc_travel_for_tilt_closing(self):
        """Proportional: tilt movement DOES couple travel."""
        strategy = ProportionalTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        travel_calc.set_position(50)
        # 2.5s tilt → (2.5/30)*100 = 8.33% travel distance
        result = strategy.calc_travel_for_tilt(2.5, True, travel_calc, 30.0, 30.0)
        assert result == 58  # min(100, 50 + 8.33) = 58

    def test_calc_travel_for_tilt_opening(self):
        strategy = ProportionalTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        travel_calc.set_position(50)
        result = strategy.calc_travel_for_tilt(2.5, False, travel_calc, 30.0, 30.0)
        assert result == 42  # max(0, 50 - 8.33) = 42 (int truncation)

    def test_enforce_constraints_forces_tilt_open(self):
        """At travel=0, tilt must be forced to 0."""
        strategy = ProportionalTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        tilt_calc = TravelCalculator(5.0, 5.0)
        travel_calc.set_position(0)
        tilt_calc.set_position(50)
        strategy.enforce_constraints(travel_calc, tilt_calc)
        assert tilt_calc.current_position() == 0

    def test_enforce_constraints_forces_tilt_closed(self):
        """At travel=100, tilt must be forced to 100."""
        strategy = ProportionalTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        tilt_calc = TravelCalculator(5.0, 5.0)
        travel_calc.set_position(100)
        tilt_calc.set_position(50)
        strategy.enforce_constraints(travel_calc, tilt_calc)
        assert tilt_calc.current_position() == 100

    def test_enforce_constraints_noop_at_midpoint(self):
        """At travel=50, tilt is left alone."""
        strategy = ProportionalTilt()
        travel_calc = TravelCalculator(30.0, 30.0)
        tilt_calc = TravelCalculator(5.0, 5.0)
        travel_calc.set_position(50)
        tilt_calc.set_position(30)
        strategy.enforce_constraints(travel_calc, tilt_calc)
        assert tilt_calc.current_position() == 30

    def test_can_calibrate_tilt(self):
        assert ProportionalTilt().can_calibrate_tilt() is False
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tilt_strategy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.cover_time_based.tilt_strategy'`

**Step 3: Create `tilt_strategy.py` with implementations**

Create `custom_components/cover_time_based/tilt_strategy.py`:

```python
"""Tilt strategy classes for cover_time_based.

Each strategy defines how tilt and travel interact during movement.
The base class CoverTimeBased delegates tilt-mode-specific decisions
to the active strategy instance.
"""

from __future__ import annotations

import logging

from xknx.devices import TravelCalculator

_LOGGER = logging.getLogger(__name__)


def _calc_coupled_target(
    movement_time: float,
    closing: bool,
    coupled_calc: TravelCalculator,
    coupled_time_close: float,
    coupled_time_open: float,
) -> int:
    """Calculate target position for a coupled calculator based on primary movement time.

    When travel moves, tilt moves proportionally (and vice versa).
    This computes how far the coupled calculator should move given
    the primary movement duration.
    """
    coupled_time = coupled_time_close if closing else coupled_time_open
    coupled_distance = (movement_time / coupled_time) * 100.0
    current = coupled_calc.current_position()
    if closing:
        return min(100, int(current + coupled_distance))
    return max(0, int(current - coupled_distance))


class TiltStrategy:
    """Base class for tilt strategies.

    Subclasses define how tilt and travel interact during movement.
    """

    def calc_tilt_for_travel(
        self,
        movement_time: float,
        closing: bool,
        tilt_calc: TravelCalculator,
        tilt_time_close: float,
        tilt_time_open: float,
    ) -> int | None:
        """When travel moves, what tilt target should be set? None = no coupling."""
        raise NotImplementedError

    def calc_travel_for_tilt(
        self,
        movement_time: float,
        closing: bool,
        travel_calc: TravelCalculator,
        travel_time_close: float,
        travel_time_open: float,
    ) -> int | None:
        """When tilt moves, what travel target should be set? None = no coupling."""
        raise NotImplementedError

    def enforce_constraints(
        self, travel_calc: TravelCalculator, tilt_calc: TravelCalculator
    ) -> None:
        """Enforce any constraints after movement stops."""

    def can_calibrate_tilt(self) -> bool:
        """Whether independent tilt calibration is allowed."""
        raise NotImplementedError


class SequentialTilt(TiltStrategy):
    """Sequential tilt: tilt phase before/after travel phase.

    Current behavior (formerly 'before_after'):
    - When travel moves, tilt couples proportionally
    - When tilt moves, travel does NOT couple
    - No constraints enforced at boundaries
    - Tilt calibration allowed
    """

    def calc_tilt_for_travel(self, movement_time, closing, tilt_calc, tilt_time_close, tilt_time_open):
        return _calc_coupled_target(movement_time, closing, tilt_calc, tilt_time_close, tilt_time_open)

    def calc_travel_for_tilt(self, movement_time, closing, travel_calc, travel_time_close, travel_time_open):
        return None

    def enforce_constraints(self, travel_calc, tilt_calc):
        pass  # No constraints in sequential mode

    def can_calibrate_tilt(self):
        return True


class ProportionalTilt(TiltStrategy):
    """Proportional tilt: tilt and travel are coupled bidirectionally.

    Current behavior (formerly 'during'):
    - When travel moves, tilt couples proportionally
    - When tilt moves, travel ALSO couples proportionally
    - At travel boundaries (0%/100%), tilt is forced to match
    - Tilt calibration NOT allowed (coupled movement)
    """

    def calc_tilt_for_travel(self, movement_time, closing, tilt_calc, tilt_time_close, tilt_time_open):
        return _calc_coupled_target(movement_time, closing, tilt_calc, tilt_time_close, tilt_time_open)

    def calc_travel_for_tilt(self, movement_time, closing, travel_calc, travel_time_close, travel_time_open):
        return _calc_coupled_target(movement_time, closing, travel_calc, travel_time_close, travel_time_open)

    def enforce_constraints(self, travel_calc, tilt_calc):
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

    def can_calibrate_tilt(self):
        return False
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tilt_strategy.py -v`
Expected: All 12 tests PASS

**Step 5: Commit**

```bash
git add custom_components/cover_time_based/tilt_strategy.py tests/test_tilt_strategy.py
git commit -m "feat: add TiltStrategy classes (sequential and proportional)"
```

---

### Task 2: Update `cover_base.py` to use TiltStrategy

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py`

**Step 1: Change constructor signature**

In `cover_base.py` `__init__` (line 50-97):

Replace the `tilt_mode` parameter and `_tilt_mode_config` attribute with `tilt_strategy`:

```python
def __init__(
    self,
    device_id,
    name,
    tilt_strategy,       # was: tilt_mode
    travel_time_close,
    travel_time_open,
    tilt_time_close,
    tilt_time_open,
    travel_startup_delay,
    tilt_startup_delay,
    endpoint_runon_time,
    min_movement_time,
):
    """Initialize the cover."""
    self._unique_id = device_id

    self._tilt_strategy = tilt_strategy    # was: self._tilt_mode_config = tilt_mode
    self._travel_time_close = travel_time_close
    ...
```

Keep `tilt_time_close`/`tilt_time_open` parameters — they're still needed for the TravelCalculator init. But change `_has_tilt_support()` to check strategy:

```python
def _has_tilt_support(self):
    """Return if cover has tilt support."""
    return self._tilt_strategy is not None
```

Tilt calc init changes from `if self._has_tilt_support():` to checking times directly:

```python
if self._tilting_time_close is not None and self._tilting_time_open is not None:
    self.tilt_calc = TravelCalculator(
        self._tilting_time_close,
        self._tilting_time_open,
    )
```

**Step 2: Remove `_tilt_mode` property (lines 245-257)**

Delete the entire `_tilt_mode` property. It's no longer needed — callers use `self._tilt_strategy` directly.

**Step 3: Remove `_calc_coupled_target` method (lines 174-188)**

Delete the method. It's now in `tilt_strategy.py` as module-level `_calc_coupled_target()`.

**Step 4: Remove `_enforce_tilt_constraints` method (lines 812-835)**

Delete the method. Callers will use `self._tilt_strategy.enforce_constraints(...)` instead.

**Step 5: Update `_async_move_to_endpoint` (lines 490-498)**

Replace:

```python
tilt_target = None
if self._has_tilt_support():
    tilt_target = self._calc_coupled_target(
        movement_time,
        closing,
        self.tilt_calc,
        self._tilting_time_close,
        self._tilting_time_open,
    )
```

With:

```python
tilt_target = None
if self._tilt_strategy is not None:
    tilt_target = self._tilt_strategy.calc_tilt_for_travel(
        movement_time,
        closing,
        self.tilt_calc,
        self._tilting_time_close,
        self._tilting_time_open,
    )
```

**Step 6: Update `_async_move_tilt_to_endpoint` (lines 556-564)**

Replace:

```python
travel_target = None
if self._tilt_mode == "during":
    travel_target = self._calc_coupled_target(
        movement_time,
        closing,
        self.travel_calc,
        self._travel_time_close,
        self._travel_time_open,
    )
```

With:

```python
travel_target = None
if self._tilt_strategy is not None:
    travel_target = self._tilt_strategy.calc_travel_for_tilt(
        movement_time,
        closing,
        self.travel_calc,
        self._travel_time_close,
        self._travel_time_open,
    )
```

**Step 7: Update `set_position` (lines 685-693)**

Same pattern as step 5 — replace `_calc_coupled_target` with `_tilt_strategy.calc_tilt_for_travel`.

**Step 8: Update `set_tilt_position` (lines 747-755)**

Same pattern as step 6 — replace `_calc_coupled_target` with `_tilt_strategy.calc_travel_for_tilt`.

**Step 9: Update `async_stop_cover` (line 591)**

Replace:

```python
self._enforce_tilt_constraints()
```

With:

```python
if self._tilt_strategy is not None:
    self._tilt_strategy.enforce_constraints(self.travel_calc, self.tilt_calc)
```

**Step 10: Update `auto_stop_if_necessary` (line 845)**

Same as step 9.

**Step 11: Update `set_known_position` (line 885)**

Same as step 9.

**Step 12: Update `start_calibration` (lines 905-909)**

Replace:

```python
if attribute in ("tilt_time_close", "tilt_time_open"):
    if self._tilt_mode == "during":
        raise HomeAssistantError(
            "Tilt time calibration not available when tilt mode is 'during'"
        )
```

With:

```python
if attribute in ("tilt_time_close", "tilt_time_open"):
    if self._tilt_strategy is not None and not self._tilt_strategy.can_calibrate_tilt():
        raise HomeAssistantError(
            "Tilt time calibration not available in proportional tilt mode"
        )
```

**Step 13: Update `extra_state_attributes` (lines 313-314)**

Replace:

```python
if self._tilt_mode_config is not None:
    attr[CONF_TILT_MODE] = self._tilt_mode_config
```

With:

```python
if self._tilt_strategy is not None:
    from .tilt_strategy import ProportionalTilt, SequentialTilt
    if isinstance(self._tilt_strategy, ProportionalTilt):
        attr[CONF_TILT_MODE] = "proportional"
    elif isinstance(self._tilt_strategy, SequentialTilt):
        attr[CONF_TILT_MODE] = "sequential"
```

**Step 14: Run all tests**

Run: `pytest tests/ -v`
Expected: Failures in tests that pass `tilt_mode=` to `make_cover` or reference `_tilt_mode_config` — these will be fixed in Task 4.

**Step 15: Commit**

```bash
git add custom_components/cover_time_based/cover_base.py
git commit -m "refactor: replace tilt mode strings with TiltStrategy in cover_base"
```

---

### Task 3: Update `cover_toggle_mode.py`

**Files:**
- Modify: `custom_components/cover_time_based/cover_toggle_mode.py:141`

**Step 1: Replace `_enforce_tilt_constraints` call**

In `async_stop_cover` (line 141), replace:

```python
self._enforce_tilt_constraints()
```

With:

```python
if self._tilt_strategy is not None:
    self._tilt_strategy.enforce_constraints(self.travel_calc, self.tilt_calc)
```

**Step 2: Commit**

```bash
git add custom_components/cover_time_based/cover_toggle_mode.py
git commit -m "refactor: use tilt strategy in toggle mode stop"
```

---

### Task 4: Update factory and conftest to use new tilt_mode strings

**Files:**
- Modify: `custom_components/cover_time_based/cover.py:248-262`
- Modify: `tests/conftest.py:63,92-93`

**Step 1: Update factory to create strategy instances**

In `cover.py` `_create_cover_from_options` (line 248-262), replace:

```python
common = dict(
    device_id=device_id,
    name=name,
    tilt_mode=options.get(CONF_TILT_MODE, "none"),
    ...
)
```

With:

```python
from .tilt_strategy import ProportionalTilt, SequentialTilt

tilt_mode_str = options.get(CONF_TILT_MODE, "none")
tilt_strategy = _resolve_tilt_strategy(
    tilt_mode_str,
    options.get(CONF_TILT_TIME_CLOSE),
    options.get(CONF_TILT_TIME_OPEN),
)

common = dict(
    device_id=device_id,
    name=name,
    tilt_strategy=tilt_strategy,
    ...
)
```

Add helper function before `_create_cover_from_options`:

```python
def _resolve_tilt_strategy(tilt_mode_str, tilt_time_close, tilt_time_open):
    """Map tilt_mode config string to a TiltStrategy instance (or None)."""
    from .tilt_strategy import ProportionalTilt, SequentialTilt

    has_tilt_times = tilt_time_close is not None and tilt_time_open is not None
    if not has_tilt_times:
        return None

    if tilt_mode_str == "proportional":
        return ProportionalTilt()
    # Default to sequential if tilt times are configured
    return SequentialTilt()
```

**Step 2: Update conftest `make_cover` fixture**

In `tests/conftest.py`, the `tilt_mode` parameter value `"none"` stays the same. But since existing tests pass `"during"` and `"before_after"`, the factory now needs to accept both old and new names during the transition. However, since we're renaming, update conftest to use the new names and update all tests in Task 5.

No changes needed to conftest itself — it already passes `tilt_mode` as a string into `options[CONF_TILT_MODE]`, and the factory will handle it.

But we need `_resolve_tilt_strategy` to also accept old names for backward compatibility during migration. Add:

```python
def _resolve_tilt_strategy(tilt_mode_str, tilt_time_close, tilt_time_open):
    from .tilt_strategy import ProportionalTilt, SequentialTilt

    has_tilt_times = tilt_time_close is not None and tilt_time_open is not None
    if not has_tilt_times:
        return None

    if tilt_mode_str in ("proportional", "during"):
        return ProportionalTilt()
    # "sequential", "before_after", or any other value with tilt times
    return SequentialTilt()
```

**Step 3: Run tests**

Run: `pytest tests/ -v`
Expected: Tests may fail on `_enforce_tilt_constraints` references or error message text. Fix in next steps.

**Step 4: Commit**

```bash
git add custom_components/cover_time_based/cover.py tests/conftest.py
git commit -m "refactor: factory creates TiltStrategy from config string"
```

---

### Task 5: Update all tests to use new tilt_mode names

**Files:**
- Modify: `tests/test_base_movement.py` — lines 234, 250, 266, 448, 464, 902, 915, 928, 941
- Modify: `tests/test_calibration.py` — lines 220, 221
- Modify: `tests/test_websocket_api.py` — lines 220, 251, 447, 454, 462, 480

**Step 1: Update `test_base_movement.py`**

Replace all occurrences:
- `tilt_mode="during"` → `tilt_mode="proportional"`
- `tilt_mode="before_after"` → `tilt_mode="sequential"`

All 9 occurrences at lines: 234, 250, 266, 448, 464, 902, 915, 928, 941.

Also update class docstrings and test names if they reference "during" or "before_after".

Additionally, the tests at lines 907, 920, 933 call `cover._enforce_tilt_constraints()` directly. This method no longer exists on the cover. Update these tests to call the strategy directly:

```python
# Was:
cover._enforce_tilt_constraints()

# Now:
if cover._tilt_strategy is not None:
    cover._tilt_strategy.enforce_constraints(cover.travel_calc, cover.tilt_calc)
```

Or better — since these tests are now covered by `test_tilt_strategy.py`, consider whether they're redundant. If kept, update the calls.

**Step 2: Update `test_calibration.py`**

Line 220: `tilt_mode="during"` → `tilt_mode="proportional"`
Line 221: `match="tilt mode is 'during'"` → `match="proportional tilt mode"`

**Step 3: Update `test_websocket_api.py`**

Lines 220, 251: `"during"` → `"proportional"` in config options and assertions.
Line 151 (websocket validation): This is tested against the WS schema, which we'll update in Task 6. For now, update the test values to new names.
Lines 447, 454: `"during"` → `"proportional"` in send/assert.
Lines 462, 480: `"during"` → `"proportional"`, `"none"` stays `"none"`.

**Step 4: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add tests/
git commit -m "test: update tilt_mode values to new names (proportional, sequential)"
```

---

### Task 6: Update WebSocket API validation

**Files:**
- Modify: `custom_components/cover_time_based/websocket_api.py:151`

**Step 1: Update tilt_mode validation**

Line 151, replace:

```python
vol.Optional("tilt_mode"): vol.In(["none", "before_after", "during"]),
```

With:

```python
vol.Optional("tilt_mode"): vol.In(["none", "sequential", "proportional"]),
```

**Step 2: Run websocket tests**

Run: `pytest tests/test_websocket_api.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/websocket_api.py
git commit -m "refactor: update websocket tilt_mode validation to new names"
```

---

### Task 7: Update config entry migration

**Files:**
- Modify: `custom_components/cover_time_based/__init__.py:62-92`

**Step 1: Update v1→v2 migration to output new names**

In `async_migrate_entry`, the v1→v2 migration currently outputs `"during"` and `"before_after"`. Update to output new names directly:

Lines 84-87, replace:

```python
elif old_val:
    new_options["tilt_mode"] = "during"
else:
    new_options["tilt_mode"] = "before_after"
```

With:

```python
elif old_val:
    new_options["tilt_mode"] = "proportional"
else:
    new_options["tilt_mode"] = "sequential"
```

**Step 2: Add v2→v3 migration**

After the v1→v2 block, add:

```python
if entry.version <= 2:
    _LOGGER.debug("Migrating config entry %s from version %d to 3", entry.entry_id, entry.version)
    new_options = dict(entry.options) if entry.version == 2 else new_options

    # Rename tilt_mode values
    tilt_mode = new_options.get("tilt_mode")
    if tilt_mode == "during":
        new_options["tilt_mode"] = "proportional"
    elif tilt_mode == "before_after":
        new_options["tilt_mode"] = "sequential"

    hass.config_entries.async_update_entry(entry, options=new_options, version=3)
    _LOGGER.debug("Migration to version 3 complete for %s", entry.entry_id)
```

**Step 3: Update YAML migration in `cover.py`**

In `cover.py` `_migrate_yaml_keys` (lines 346-351), update the `travel_moves_with_tilt` migration to output new names:

Replace:

```python
if CONF_TRAVEL_MOVES_WITH_TILT in config:
    if CONF_TILT_MODE not in config:
        config[CONF_TILT_MODE] = (
            "during" if config[CONF_TRAVEL_MOVES_WITH_TILT] else "before_after"
        )
    config.pop(CONF_TRAVEL_MOVES_WITH_TILT)
```

With:

```python
if CONF_TRAVEL_MOVES_WITH_TILT in config:
    if CONF_TILT_MODE not in config:
        config[CONF_TILT_MODE] = (
            "proportional" if config[CONF_TRAVEL_MOVES_WITH_TILT] else "sequential"
        )
    config.pop(CONF_TRAVEL_MOVES_WITH_TILT)
```

**Step 4: Update `config_flow.py` version**

In `config_flow.py`, update `VERSION = 2` to `VERSION = 3`.

**Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add custom_components/cover_time_based/__init__.py custom_components/cover_time_based/cover.py custom_components/cover_time_based/config_flow.py
git commit -m "feat: add v2→v3 config migration for tilt_mode rename"
```

---

### Task 8: Update translations

**Files:**
- Modify: `custom_components/cover_time_based/strings.json` (if tilt_mode options are listed)
- Modify: `custom_components/cover_time_based/translations/en.json` (if tilt_mode options are listed)

**Step 1: Check for tilt_mode references in translations**

Search for "during" or "before_after" in strings.json and translations. If found, update to "proportional"/"sequential".

**Step 2: Commit if changes made**

```bash
git add custom_components/cover_time_based/strings.json custom_components/cover_time_based/translations/
git commit -m "chore: update translations for tilt_mode rename"
```

---

### Task 9: Final verification

**Step 1: Run linting**

```bash
ruff check .
ruff format .
```

**Step 2: Run type checking**

```bash
npx pyright
```

**Step 3: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests PASS, no lint errors, no type errors.

**Step 4: Deploy to HA**

```bash
rm -Rf /workspaces/homeassistant-core/config/custom_components/cover_time_based && cp -r /workspaces/ha-cover-time-based/custom_components/cover_time_based /workspaces/homeassistant-core/config/custom_components/
```

**Step 5: Final commit if any cleanup**

```bash
git add -A && git commit -m "chore: lint and format"
```
