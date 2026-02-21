# Inline Tilt Strategy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an "inline" tilt mode for single-motor roller shutters where tilt is embedded in the travel cycle.

**Architecture:** New `InlineTilt` strategy class following existing strategy pattern. Add `restores_tilt` property to base class to generalize tilt restore for shared-motor strategies. Modify `cover_base.py` to support tilt restore via main motor (not just tilt motor). Wire up config/frontend/API.

**Tech Stack:** Python, Home Assistant cover platform, JavaScript (frontend card)

---

### Task 1: Add `restores_tilt` property to TiltStrategy base class

**Files:**
- Modify: `custom_components/cover_time_based/tilt_strategies/base.py:59-101`
- Modify: `custom_components/cover_time_based/tilt_strategies/sequential.py:17-65`
- Modify: `custom_components/cover_time_based/tilt_strategies/dual_motor.py`
- Test: `tests/test_tilt_strategy.py`

**Step 1: Write failing tests**

In `tests/test_tilt_strategy.py`, add to existing test classes:

```python
# In TestSequentialTiltProperties:
def test_restores_tilt(self):
    assert SequentialTilt().restores_tilt is False

# In TestDualMotorTiltProperties:
def test_restores_tilt(self):
    assert DualMotorTilt().restores_tilt is True
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tilt_strategy.py::TestSequentialTiltProperties::test_restores_tilt tests/test_tilt_strategy.py::TestDualMotorTiltProperties::test_restores_tilt -v`
Expected: FAIL with `AttributeError: 'SequentialTilt' object has no attribute 'restores_tilt'`

**Step 3: Add abstract property to base class**

In `custom_components/cover_time_based/tilt_strategies/base.py`, add after the `uses_tilt_motor` property (line 74):

```python
    @property
    @abstractmethod
    def restores_tilt(self) -> bool:
        """Whether tilt should be restored after a position change."""
```

Implement in each subclass:

In `sequential.py`, add after `uses_tilt_motor`:
```python
    @property
    def restores_tilt(self) -> bool:
        return False
```

In `dual_motor.py`, add after `uses_tilt_motor`:
```python
    @property
    def restores_tilt(self) -> bool:
        return True
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tilt_strategy.py -v`
Expected: All pass

**Step 5: Commit**

```
git add -A && git commit -m "feat: add restores_tilt property to TiltStrategy"
```

---

### Task 2: Create InlineTilt strategy class with tests

**Files:**
- Create: `custom_components/cover_time_based/tilt_strategies/inline.py`
- Modify: `custom_components/cover_time_based/tilt_strategies/__init__.py`
- Test: `tests/test_tilt_strategy.py`

**Step 1: Write failing tests**

Add to `tests/test_tilt_strategy.py`:

```python
from custom_components.cover_time_based.tilt_strategies import (
    DualMotorTilt,
    InlineTilt,
    SequentialTilt,
    TiltTo,
    TravelTo,
)

# ===================================================================
# InlineTilt
# ===================================================================


class TestInlineTiltProperties:
    def test_name(self):
        assert InlineTilt().name == "inline"

    def test_uses_tilt_motor(self):
        assert InlineTilt().uses_tilt_motor is False

    def test_restores_tilt(self):
        assert InlineTilt().restores_tilt is True

    def test_can_calibrate_tilt(self):
        assert InlineTilt().can_calibrate_tilt() is True


class TestInlinePlanMovePosition:
    def test_closing_with_tilt_open_adds_pre_step(self):
        """Closing from open tilt: tilt closes first, then travel."""
        strategy = InlineTilt()
        steps = strategy.plan_move_position(
            target_pos=30, current_pos=80, current_tilt=100
        )
        assert steps == [TiltTo(0), TravelTo(30)]

    def test_closing_with_tilt_already_closed_skips_pre_step(self):
        """Closing when tilt already closed: just travel."""
        strategy = InlineTilt()
        steps = strategy.plan_move_position(
            target_pos=30, current_pos=80, current_tilt=0
        )
        assert steps == [TravelTo(30)]

    def test_opening_with_tilt_closed_adds_pre_step(self):
        """Opening from closed tilt: tilt opens first, then travel."""
        strategy = InlineTilt()
        steps = strategy.plan_move_position(
            target_pos=80, current_pos=30, current_tilt=0
        )
        assert steps == [TiltTo(100), TravelTo(80)]

    def test_opening_with_tilt_already_open_skips_pre_step(self):
        """Opening when tilt already open: just travel."""
        strategy = InlineTilt()
        steps = strategy.plan_move_position(
            target_pos=80, current_pos=30, current_tilt=100
        )
        assert steps == [TravelTo(80)]

    def test_closing_to_endpoint_still_has_pre_step(self):
        """Even targeting 0%, tilt phase still happens for timing."""
        strategy = InlineTilt()
        steps = strategy.plan_move_position(
            target_pos=0, current_pos=50, current_tilt=100
        )
        assert steps == [TiltTo(0), TravelTo(0)]

    def test_opening_to_endpoint_still_has_pre_step(self):
        """Even targeting 100%, tilt phase still happens for timing."""
        strategy = InlineTilt()
        steps = strategy.plan_move_position(
            target_pos=100, current_pos=50, current_tilt=0
        )
        assert steps == [TiltTo(100), TravelTo(100)]

    def test_closing_with_partial_tilt_adds_pre_step(self):
        """Closing with tilt at 60% (not fully closed): pre-step needed."""
        strategy = InlineTilt()
        steps = strategy.plan_move_position(
            target_pos=20, current_pos=70, current_tilt=60
        )
        assert steps == [TiltTo(0), TravelTo(20)]

    def test_opening_with_partial_tilt_adds_pre_step(self):
        """Opening with tilt at 40% (not fully open): pre-step needed."""
        strategy = InlineTilt()
        steps = strategy.plan_move_position(
            target_pos=70, current_pos=20, current_tilt=40
        )
        assert steps == [TiltTo(100), TravelTo(70)]


class TestInlinePlanMoveTilt:
    def test_tilt_only_no_travel(self):
        """Tilt command: just tilt, no travel coupling."""
        strategy = InlineTilt()
        steps = strategy.plan_move_tilt(
            target_tilt=50, current_pos=30, current_tilt=100
        )
        assert steps == [TiltTo(50)]

    def test_tilt_at_fully_open(self):
        strategy = InlineTilt()
        steps = strategy.plan_move_tilt(
            target_tilt=0, current_pos=100, current_tilt=100
        )
        assert steps == [TiltTo(0)]

    def test_tilt_at_closed(self):
        strategy = InlineTilt()
        steps = strategy.plan_move_tilt(
            target_tilt=80, current_pos=0, current_tilt=0
        )
        assert steps == [TiltTo(80)]


class TestInlineSnapTrackers:
    def test_forces_tilt_closed_at_position_zero(self):
        strategy = InlineTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(0)
        tilt.set_position(50)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0

    def test_forces_tilt_open_at_position_hundred(self):
        strategy = InlineTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(100)
        tilt.set_position(50)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 100

    def test_no_op_at_mid_position(self):
        strategy = InlineTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(50)
        tilt.set_position(30)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 30

    def test_already_correct_at_closed(self):
        strategy = InlineTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(0)
        tilt.set_position(0)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 0

    def test_already_correct_at_open(self):
        strategy = InlineTilt()
        travel = TravelCalculator(10.0, 10.0)
        tilt = TravelCalculator(2.0, 2.0)
        travel.set_position(100)
        tilt.set_position(100)
        strategy.snap_trackers_to_physical(travel, tilt)
        assert tilt.current_position() == 100
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tilt_strategy.py::TestInlineTiltProperties -v`
Expected: FAIL with `ImportError: cannot import name 'InlineTilt'`

**Step 3: Create inline.py**

Create `custom_components/cover_time_based/tilt_strategies/inline.py`:

```python
"""Inline tilt strategy.

Single-motor roller shutter where tilt is embedded in the travel cycle.
At the start of any movement there is a fixed tilt phase, then travel
continues. Tilt works at any position. Tilt is restored after position
changes to non-endpoint targets.
"""

from __future__ import annotations

import logging

from .base import TiltStrategy, TiltTo, TravelTo

_LOGGER = logging.getLogger(__name__)


class InlineTilt(TiltStrategy):
    """Inline tilt mode.

    Single motor where tilt is part of the travel cycle. Each direction
    has a fixed tilt phase at the start of movement. Tilt works at any
    position in the travel range.
    """

    def can_calibrate_tilt(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "inline"

    @property
    def uses_tilt_motor(self) -> bool:
        return False

    @property
    def restores_tilt(self) -> bool:
        return True

    def plan_move_position(
        self, target_pos: int, current_pos: int, current_tilt: int
    ) -> list[TiltTo | TravelTo]:
        closing = target_pos < current_pos
        tilt_endpoint = 0 if closing else 100
        steps: list[TiltTo | TravelTo] = []
        if current_tilt != tilt_endpoint:
            steps.append(TiltTo(tilt_endpoint))
        steps.append(TravelTo(target_pos))
        return steps

    def plan_move_tilt(
        self, target_tilt: int, current_pos: int, current_tilt: int
    ) -> list[TiltTo | TravelTo]:
        return [TiltTo(target_tilt)]

    def snap_trackers_to_physical(self, travel_calc, tilt_calc):
        current_travel = travel_calc.current_position()
        current_tilt = tilt_calc.current_position()
        if current_travel == 0 and current_tilt != 0:
            _LOGGER.debug(
                "InlineTilt :: Travel at 0%% (closed), forcing tilt to 0%% (was %d%%)",
                current_tilt,
            )
            tilt_calc.set_position(0)
        elif current_travel == 100 and current_tilt != 100:
            _LOGGER.debug(
                "InlineTilt :: Travel at 100%% (open), forcing tilt to 100%% (was %d%%)",
                current_tilt,
            )
            tilt_calc.set_position(100)
```

Update `__init__.py` to export `InlineTilt`:

```python
from .inline import InlineTilt
```

Add `"InlineTilt"` to `__all__`.

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tilt_strategy.py -v`
Expected: All pass

**Step 5: Commit**

```
git add -A && git commit -m "feat: add InlineTilt strategy class"
```

---

### Task 3: Wire InlineTilt into factory, websocket API, and frontend

**Files:**
- Modify: `custom_components/cover_time_based/cover.py:243-260`
- Modify: `custom_components/cover_time_based/websocket_api.py:166`
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js:312-344,769-788,859`
- Test: `tests/test_cover_factory.py`

**Step 1: Write failing test**

In `tests/test_cover_factory.py`, add import and test:

```python
from custom_components.cover_time_based.tilt_strategies import (
    DualMotorTilt,
    InlineTilt,
    SequentialTilt,
)

# In TestResolveTiltStrategy:
def test_inline(self):
    result = _resolve_tilt_strategy("inline", 2.0, 2.0)
    assert isinstance(result, InlineTilt)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cover_factory.py::TestResolveTiltStrategy::test_inline -v`
Expected: FAIL (returns SequentialTilt because unknown mode falls through to default)

**Step 3: Update factory, API, and frontend**

In `custom_components/cover_time_based/cover.py` at line 245, update the import and add the inline case:

```python
def _resolve_tilt_strategy(tilt_mode_str, tilt_time_close, tilt_time_open, **kwargs):
    """Map tilt_mode config string to a TiltStrategy instance (or None)."""
    from .tilt_strategies import DualMotorTilt, InlineTilt, SequentialTilt

    if tilt_mode_str in ("none", "proportional"):
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
    # "sequential" or any other value with tilt times → sequential
    return SequentialTilt()
```

In `custom_components/cover_time_based/websocket_api.py` line 166, add `"inline"`:

```python
vol.Optional("tilt_mode"): vol.In(["none", "sequential", "dual_motor", "inline"]),
```

In `custom_components/cover_time_based/frontend/cover-time-based-card.js`:

At line 784 (after the dual_motor option), add:
```javascript
          <option value="inline" ?selected=${tiltMode === "inline"}>
            Tilts inline with travel
          </option>
```

In `_onTiltModeChange` (line 312), add an `else if` for inline that clears dual-motor fields (same as sequential):
```javascript
      } else if (mode === "inline") {
        // Clear dual-motor fields when switching to inline
        updates.safe_tilt_position = null;
        updates.max_tilt_allowed_position = null;
        updates.tilt_open_switch = null;
        updates.tilt_close_switch = null;
        updates.tilt_stop_switch = null;
      }
```

In `_renderTimingTable` (line 859), update the tilt times condition to include inline:
```javascript
const hasTiltTimes = c.tilt_mode === "sequential" || c.tilt_mode === "dual_motor" || c.tilt_mode === "inline";
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cover_factory.py -v`
Expected: All pass

**Step 5: Commit**

```
git add -A && git commit -m "feat: wire InlineTilt into factory, API, and frontend"
```

---

### Task 4: Enable tilt restore for shared-motor strategies in cover_base.py

This is the core integration task. Currently tilt restore only works for dual_motor (`uses_tilt_motor=True`). We need to:
1. Set `_tilt_restore_target` when `restores_tilt=True` and target is not an endpoint
2. Make `_start_tilt_restore` work with the main motor (not just tilt motor)
3. Make `auto_stop_if_necessary` handle restore completion for shared motor
4. Make `async_stop_cover` handle stop-during-restore for shared motor

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py`
- Test: `tests/test_base_movement.py`

**Step 1: Write failing tests**

Add a new test class `TestInlineTiltRestore` in `tests/test_base_movement.py`. These tests use the same test helpers as the existing `TestDualMotorTiltPreStep` class. Use the inline tilt strategy and verify the complete lifecycle.

```python
class TestInlineTiltRestore:
    """Test tilt restore for inline tilt (shared motor)."""

    def _make_inline_cover(self):
        """Create a cover with inline tilt strategy."""
        from custom_components.cover_time_based.tilt_strategies import InlineTilt
        # Same helper pattern as TestDualMotorTiltPreStep but with InlineTilt
        return make_cover(
            tilt_strategy=InlineTilt(),
            travel_time_close=20.0,
            travel_time_open=20.0,
            tilt_time_close=2.0,
            tilt_time_open=2.0,
        )

    @pytest.mark.asyncio
    async def test_close_with_tilt_open_uses_pre_step_delay(self):
        """Closing with tilt open: pre-step delay accounts for tilt phase."""
        cover = self._make_inline_cover()
        cover.travel_calc.set_position(80)
        cover.tilt_calc.set_position(100)
        await cover._async_move_to_endpoint(target=30)
        # Motor is running (close command sent)
        assert cover._last_command == SERVICE_CLOSE_COVER
        # Tilt restore target is saved (non-endpoint target)
        assert cover._tilt_restore_target == 100

    @pytest.mark.asyncio
    async def test_no_restore_at_endpoint_zero(self):
        """Closing to 0%: no tilt restore (endpoint forces tilt=0)."""
        cover = self._make_inline_cover()
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)
        await cover._async_move_to_endpoint(target=0)
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_no_restore_at_endpoint_hundred(self):
        """Opening to 100%: no tilt restore (endpoint forces tilt=100)."""
        cover = self._make_inline_cover()
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(0)
        await cover._async_move_to_endpoint(target=100)
        assert cover._tilt_restore_target is None

    @pytest.mark.asyncio
    async def test_restore_uses_main_motor(self):
        """After travel completes, restore reverses main motor direction."""
        cover = self._make_inline_cover()
        cover.travel_calc.set_position(80)
        cover.tilt_calc.set_position(100)  # tilt fully open
        # Close to 30 — tilt closes first, then travel
        await cover.set_position(30)
        # Simulate travel reaching target
        cover.travel_calc.set_position(30)
        cover.tilt_calc.set_position(0)  # tilt closed after closing movement
        await cover.auto_stop_if_necessary()
        # Restore phase: should reverse to open command to restore tilt
        assert cover._tilt_restore_active is True
        # The main motor open command was sent (to restore tilt from 0→100)
        assert cover._last_command is None  # restore clears _last_command

    @pytest.mark.asyncio
    async def test_restore_complete_stops_main_motor(self):
        """When tilt restore completes, main motor is stopped."""
        cover = self._make_inline_cover()
        cover.travel_calc.set_position(80)
        cover.tilt_calc.set_position(100)
        await cover.set_position(30)
        # Simulate travel complete
        cover.travel_calc.set_position(30)
        cover.tilt_calc.set_position(0)
        await cover.auto_stop_if_necessary()
        # Now simulate tilt restore complete
        cover.tilt_calc.set_position(100)
        await cover.auto_stop_if_necessary()
        assert cover._tilt_restore_active is False

    @pytest.mark.asyncio
    async def test_stop_during_restore_stops_motor(self):
        """Stopping during tilt restore stops the main motor."""
        cover = self._make_inline_cover()
        cover.travel_calc.set_position(80)
        cover.tilt_calc.set_position(100)
        await cover.set_position(30)
        cover.travel_calc.set_position(30)
        cover.tilt_calc.set_position(0)
        await cover.auto_stop_if_necessary()
        assert cover._tilt_restore_active is True
        # User presses stop during restore
        await cover.async_stop_cover()
        assert cover._tilt_restore_active is False

    @pytest.mark.asyncio
    async def test_no_restore_when_tilt_already_at_target(self):
        """No tilt restore when tilt is already at the correct position."""
        cover = self._make_inline_cover()
        cover.travel_calc.set_position(80)
        cover.tilt_calc.set_position(0)  # tilt already closed
        await cover.set_position(30)  # closing — tilt endpoint is 0, already there
        # No pre-step delay, no restore target
        assert cover._tilt_restore_target is None
```

Note: The exact test implementation will depend on the test helpers available in `test_base_movement.py`. The tests above show the intent — adapt `make_cover` or equivalent helper to accept an `InlineTilt` strategy.

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_base_movement.py::TestInlineTiltRestore -v`
Expected: FAIL — `_tilt_restore_target` is never set for non-dual-motor strategies

**Step 3: Modify cover_base.py**

**3a. Set `_tilt_restore_target` in `_async_move_to_endpoint` and `set_position`**

In both `_async_move_to_endpoint` (around line 486-506) and `set_position` (around line 717-736), after computing `tilt_target` and `pre_step_delay`, add restore target logic for strategies with `restores_tilt=True` that don't use the tilt motor:

```python
                # Dual motor: tilt to safe position first, then travel
                if (
                    tilt_target is not None
                    and self._tilt_strategy.uses_tilt_motor
                    and current_tilt != tilt_target
                ):
                    await self._start_tilt_pre_step(
                        tilt_target, target, command, current_tilt
                    )
                    return

                # Shared motor with restore: save tilt for post-travel restore
                if (
                    tilt_target is not None
                    and self._tilt_strategy.restores_tilt
                    and not self._tilt_strategy.uses_tilt_motor
                    and target not in (0, 100)
                ):
                    self._tilt_restore_target = current_tilt
```

**3b. Generalize `_start_tilt_restore` to work with main motor**

In `_start_tilt_restore` (line 978), branch on `uses_tilt_motor`:

```python
    async def _start_tilt_restore(self):
        """Restore tilt to its pre-movement position.

        For dual_motor: stops travel motor, starts tilt motor.
        For shared motor (inline): reverses main motor direction.
        """
        restore_target = self._tilt_restore_target
        self._tilt_restore_target = None

        current_tilt = self.tilt_calc.current_position()
        if current_tilt is None or current_tilt == restore_target:
            _LOGGER.debug(
                "_start_tilt_restore :: no restore needed (current=%s, target=%s)",
                current_tilt,
                restore_target,
            )
            await self._async_handle_command(SERVICE_STOP_COVER)
            self._last_command = None
            return

        _LOGGER.debug(
            "_start_tilt_restore :: restoring tilt from %d%% to %d%%",
            current_tilt,
            restore_target,
        )

        closing = restore_target < current_tilt

        if self._tilt_strategy.uses_tilt_motor:
            # Dual motor: stop travel, start tilt motor
            await self._async_handle_command(SERVICE_STOP_COVER)
            if closing:
                await self._send_tilt_close()
            else:
                await self._send_tilt_open()
        else:
            # Shared motor (inline): reverse main motor direction
            command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
            await self._async_handle_command(command)

        self.tilt_calc.start_travel(restore_target)
        self._tilt_restore_active = True
        self._last_command = None
        self.start_auto_updater()
```

**3c. Generalize `auto_stop_if_necessary` restore completion**

In `auto_stop_if_necessary` (around line 870-880), branch on `uses_tilt_motor` when restore completes:

```python
            if self._tilt_restore_active:
                # Tilt restore just completed
                _LOGGER.debug("auto_stop_if_necessary :: tilt restore complete")
                self._tilt_restore_active = False
                if self._has_tilt_motor():
                    await self._send_tilt_stop()
                else:
                    await self._async_handle_command(SERVICE_STOP_COVER)
                if self._tilt_strategy is not None:
                    self._tilt_strategy.snap_trackers_to_physical(
                        self.travel_calc, self.tilt_calc
                    )
                self._last_command = None
                return
```

**3d. Generalize `async_stop_cover` for stop during restore**

In `async_stop_cover` (around line 610-613), the condition for sending tilt stop:

```python
        if (
            tilt_restore_was_active or tilt_pre_step_was_active
        ) and self._has_tilt_motor():
            await self._send_tilt_stop()
```

This already correctly only sends `_send_tilt_stop()` for tilt motor covers. For inline (shared motor), the main motor stop via `_send_stop()` at line 609 already handles it. No change needed here.

**Step 4: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All pass (258 existing + new inline tests)

**Step 5: Commit**

```
git add -A && git commit -m "feat: enable tilt restore for inline tilt via main motor"
```

---

### Task 5: Add set_position integration test for inline tilt

**Files:**
- Test: `tests/test_base_movement.py`

**Step 1: Write additional integration tests**

Verify that `set_position` (not just `_async_move_to_endpoint`) also sets the restore target:

```python
    @pytest.mark.asyncio
    async def test_set_position_sets_restore_target(self):
        """set_position with inline tilt saves restore target."""
        cover = self._make_inline_cover()
        cover.travel_calc.set_position(80)
        cover.tilt_calc.set_position(100)
        await cover.set_position(30)
        assert cover._tilt_restore_target == 100

    @pytest.mark.asyncio
    async def test_set_position_no_restore_at_endpoint(self):
        """set_position targeting 0% does not set restore target."""
        cover = self._make_inline_cover()
        cover.travel_calc.set_position(50)
        cover.tilt_calc.set_position(100)
        await cover.set_position(0)
        assert cover._tilt_restore_target is None
```

**Step 2: Run tests**

Run: `python -m pytest tests/test_base_movement.py::TestInlineTiltRestore -v`
Expected: All pass

**Step 3: Commit**

```
git add -A && git commit -m "test: add set_position integration tests for inline tilt"
```

---

### Task 6: Run full test suite and deploy

**Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All pass

**Step 2: Run linting and type checking**

Run: `ruff check . && ruff format . && npx pyright`
Expected: Clean

**Step 3: Deploy to HA**

```
rm -Rf /workspaces/homeassistant-core/config/custom_components/cover_time_based && cp -r /workspaces/ha-cover-time-based/custom_components/cover_time_based /workspaces/homeassistant-core/config/custom_components/
```

**Step 4: Commit any linting fixes**

If ruff or pyright required changes, commit them.
