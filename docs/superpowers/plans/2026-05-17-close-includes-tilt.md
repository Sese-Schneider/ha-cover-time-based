# `close_includes_tilt` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `cover.toggle` work correctly on every tilt strategy by redefining `is_closed` as travel-only and adding a `close_includes_tilt` option (default `true`) that makes `close_cover` also close the slats for `sequential_close` and `dual_motor`.

**Architecture:** Two surgical changes in `cover_base.py`: (1) drop the AND-tilt branch from `is_closed`; (2) rewrite `async_close_cover` to skip the travel resync pulse when already settled at 0, then optionally trigger a tilt-close when the new option is on. The option is plumbed from the config entry through `_create_cover_from_options` into the `CoverTimeBased` constructor. The websocket API and frontend card expose the option in the integration UI.

**Tech Stack:** Python 3 / Home Assistant custom component; pytest with `pytest-asyncio`; `unittest.mock` for hass + service-call mocks; tests use the `make_cover` fixture from `tests/conftest.py`.

**Spec:** [docs/superpowers/specs/2026-05-17-close-includes-tilt-design.md](../specs/2026-05-17-close-includes-tilt-design.md)

---

## File Inventory

- **Modify:** `custom_components/cover_time_based/const.py` (add 2 constants)
- **Modify:** `custom_components/cover_time_based/cover_base.py` (change `is_closed`; add ctor param; rewrite `async_close_cover`)
- **Modify:** `custom_components/cover_time_based/cover.py` (wire the option from config into the constructor)
- **Modify:** `custom_components/cover_time_based/websocket_api.py` (add to schema, `_FIELD_MAP`, and `get_config` response)
- **Modify:** `custom_components/cover_time_based/frontend/cover-time-based-card.js` (conditional UI field for sequential_close + dual_motor)
- **Modify:** `tests/conftest.py` (add `close_includes_tilt` param to `make_cover` fixture)
- **Modify:** `tests/test_base_movement.py` (rewrite the two `is_closed` tests whose semantics flip)
- **Create:** `tests/test_close_includes_tilt.py` (new behavior + regression tests)
- **Modify:** `tests/test_websocket_api.py` (add round-trip test for the new field)

---

## Task 1: Add constants to const.py

**Files:**
- Modify: `custom_components/cover_time_based/const.py`

- [ ] **Step 1: Add constants**

Edit `custom_components/cover_time_based/const.py` to append after `DEFAULT_ENDPOINT_RUNON_TIME`:

```python
CONF_CLOSE_INCLUDES_TILT = "close_includes_tilt"
DEFAULT_CLOSE_INCLUDES_TILT = True
```

- [ ] **Step 2: Verify imports resolve**

Run: `python -c "from custom_components.cover_time_based.const import CONF_CLOSE_INCLUDES_TILT, DEFAULT_CLOSE_INCLUDES_TILT; print(CONF_CLOSE_INCLUDES_TILT, DEFAULT_CLOSE_INCLUDES_TILT)"`
Expected: `close_includes_tilt True`

- [ ] **Step 3: Commit**

```bash
git add custom_components/cover_time_based/const.py
git commit -m "feat: add CONF_CLOSE_INCLUDES_TILT constant"
```

---

## Task 2: Redefine `is_closed` as travel-only

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py:310-316`
- Modify: `tests/test_base_movement.py:960-970` and `tests/test_base_movement.py:2270-2281`

- [ ] **Step 1: Rewrite the existing is_closed-with-tilt tests to assert new behavior**

In `tests/test_base_movement.py`, replace the two test methods at lines 960-970:

```python
    def test_is_closed_with_tilt(self, make_cover):
        """is_closed reports travel position only — tilt is independent."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)
        assert cover.is_closed is True

    def test_is_closed_when_tilt_open(self, make_cover):
        """is_closed is True at travel=0 even if tilt is still open."""
        cover = make_cover(tilt_time_close=5.0, tilt_time_open=5.0)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(100)
        assert cover.is_closed is True
```

And replace the two test methods at lines 2270-2281:

```python
    def test_is_closed_travel_only_inline(self, make_cover):
        """For inline, is_closed tracks travel position regardless of tilt."""
        cover = self._make_inline_cover(make_cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(50)
        assert cover.is_closed is True

    def test_is_closed_when_both_closed(self, make_cover):
        cover = self._make_inline_cover(make_cover)
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(0)
        assert cover.is_closed is True
```

- [ ] **Step 2: Run rewritten tests to verify they fail**

Run: `pytest tests/test_base_movement.py::TestCoverProperties::test_is_closed_when_tilt_open tests/test_base_movement.py::TestInlineTilt::test_is_closed_travel_only_inline -v`

Expected: both FAIL — `is_closed` currently returns `False` when tilt is not 0.

- [ ] **Step 3: Implement is_closed change**

In `custom_components/cover_time_based/cover_base.py`, replace lines 310-316:

```python
    @property
    def is_closed(self):
        """Return if the cover is closed.

        Tracks travel position only — tilt is reported independently via
        current_cover_tilt_position. This matches HA's general cover
        semantics and is what drives the built-in toggle action.
        """
        return self.travel_calc.is_closed()
```

- [ ] **Step 4: Run the rewritten tests and the unchanged is_closed tests**

Run: `pytest tests/test_base_movement.py -k "is_closed" -v`

Expected: all pass.

- [ ] **Step 5: Run the full test suite to catch any unexpected regressions**

Run: `pytest tests/ -x -q`

Expected: all green. (If any other test asserts `is_closed is False` at travel=0 + tilt≠0, update it to reflect the new semantics. No such tests are expected based on the grep done while writing this plan.)

- [ ] **Step 6: Commit**

```bash
git add custom_components/cover_time_based/cover_base.py tests/test_base_movement.py
git commit -m "feat: is_closed tracks travel position only, not tilt"
```

---

## Task 3: Add `close_includes_tilt` constructor param

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py:60-130`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cover_base_extra.py` (append at end of file):

```python
def test_close_includes_tilt_defaults_to_true(make_cover):
    """The new close_includes_tilt option defaults to True when not set."""
    cover = make_cover()
    assert cover._close_includes_tilt is True


def test_close_includes_tilt_can_be_disabled(make_cover):
    """The option can be set False via the make_cover fixture."""
    cover = make_cover(close_includes_tilt=False)
    assert cover._close_includes_tilt is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cover_base_extra.py -k close_includes_tilt -v`

Expected: FAIL — `_close_includes_tilt` not set; the fixture doesn't accept the kwarg yet either.

- [ ] **Step 3: Add the constructor parameter**

In `custom_components/cover_time_based/cover_base.py`, update `CoverTimeBased.__init__` (around lines 60-95):

```python
    def __init__(
        self,
        device_id,
        name,
        tilt_strategy,
        travel_time_close,
        travel_time_open,
        tilt_time_close,
        tilt_time_open,
        travel_startup_delay,
        tilt_startup_delay,
        endpoint_runon_time,
        min_movement_time,
        tilt_open_switch=None,
        tilt_close_switch=None,
        tilt_stop_switch=None,
        tilt_mode_str="none",
        close_includes_tilt=True,
    ):
        """Initialize the cover."""
```

And add this line after the existing `self._tilt_stop_switch_id = tilt_stop_switch` line (currently around line 95):

```python
        self._close_includes_tilt = close_includes_tilt
```

- [ ] **Step 4: Wire the fixture kwarg through `make_cover`**

Now wire the option through `_create_cover_from_options` and the fixture; without this the tests can't pass.

In `custom_components/cover_time_based/cover.py`, add to the `common = dict(...)` block in `_create_cover_from_options` (after `tilt_stop_switch=...`, around line 315):

```python
        close_includes_tilt=options.get(
            CONF_CLOSE_INCLUDES_TILT, DEFAULT_CLOSE_INCLUDES_TILT
        ),
```

Add the import at the top of `cover.py` to the `from .const import (...)` block:

```python
    CONF_CLOSE_INCLUDES_TILT,
    DEFAULT_CLOSE_INCLUDES_TILT,
```

In `tests/conftest.py`, in `make_cover`'s `_make` signature (around line 78), add the kwarg:

```python
        close_includes_tilt=None,
```

And in the body, after the existing `if max_tilt_allowed_position is not None:` block (around line 149), add:

```python
        if close_includes_tilt is not None:
            options[CONF_CLOSE_INCLUDES_TILT] = close_includes_tilt
```

Also add the import to `tests/conftest.py`'s import block (around line 8-32):

```python
    CONF_CLOSE_INCLUDES_TILT,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cover_base_extra.py -k close_includes_tilt -v`

Expected: both PASS.

- [ ] **Step 6: Run the full test suite**

Run: `pytest tests/ -x -q`

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add custom_components/cover_time_based/cover.py custom_components/cover_time_based/cover_base.py tests/conftest.py tests/test_cover_base_extra.py
git commit -m "feat: plumb close_includes_tilt option from config to CoverTimeBased"
```

---

## Task 4: Skip travel resync when settled at 0

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py:353-361`
- Create: `tests/test_close_includes_tilt.py`

- [ ] **Step 1: Create the new test file with the first failing test**

Create `tests/test_close_includes_tilt.py`:

```python
"""Tests for close_includes_tilt option and the related changes to
async_close_cover (resync-skip when settled at 0).

These tests use mocked _async_move_to_endpoint and _async_move_tilt_to_endpoint
to assert orchestration rather than running real motor timing.
"""

import pytest
from unittest.mock import AsyncMock, patch

from custom_components.cover_time_based.travel_calculator import TravelStatus


class TestSkipResyncAtZero:
    """async_close_cover should not call _async_move_to_endpoint(0) when
    travel is already settled at 0. This avoids the resync motor pulse
    HA-convention violation."""

    @pytest.mark.asyncio
    async def test_skips_endpoint_call_when_settled_at_zero(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(0)
        # set_position() leaves direction at STOPPED, which is what we want
        assert cover.travel_calc.travel_direction == TravelStatus.STOPPED

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_move,
        ):
            await cover.async_close_cover()

        mock_move.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_calls_endpoint_when_not_at_zero(self, make_cover):
        cover = make_cover()
        cover.travel_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_move,
        ):
            await cover.async_close_cover()

        mock_move.assert_awaited_once_with(target=0)

    @pytest.mark.asyncio
    async def test_calls_endpoint_when_at_zero_but_still_moving(self, make_cover):
        """In the final 1% of a close, current_position() can read 0 while
        the motor is still finishing. travel_direction is the clean signal."""
        cover = make_cover()
        cover.travel_calc.set_position(100)
        cover.travel_calc.start_travel_down()
        # Force the calculator into a state where current is 0 but direction
        # is still DOWN (mid-finish).
        cover.travel_calc.set_position(0)
        cover.travel_calc.start_travel_down()
        assert cover.travel_calc.travel_direction == TravelStatus.DIRECTION_DOWN

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_move,
        ):
            await cover.async_close_cover()

        mock_move.assert_awaited_once_with(target=0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_close_includes_tilt.py::TestSkipResyncAtZero -v`

Expected: `test_skips_endpoint_call_when_settled_at_zero` FAILS — current code always calls `_async_move_to_endpoint(0)`. The other two should PASS as a sanity check that the test setup is sound.

- [ ] **Step 3: Implement the skip-resync guard**

In `custom_components/cover_time_based/cover_base.py`, replace `async_close_cover` (lines 353-361):

```python
    async def async_close_cover(self, **kwargs):
        """Close the cover fully.

        When already settled at travel=0, skip the resync motor pulse that
        the default _async_move_to_endpoint(0) emits at target==current.
        This matches HA's convention that close_cover re-applied is a no-op.
        """
        self._require_configured()
        self._log("async_close_cover")
        if self.is_opening:
            self._log("async_close_cover :: currently opening, stopping first")
            await self.async_stop_cover()
            await self._direction_change_delay()

        settled_at_zero = (
            self.travel_calc.current_position() == 0
            and self.travel_calc.travel_direction == TravelStatus.STOPPED
        )
        if not settled_at_zero:
            await self._async_move_to_endpoint(target=0)
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `pytest tests/test_close_includes_tilt.py::TestSkipResyncAtZero -v`

Expected: all three PASS.

- [ ] **Step 5: Run the full suite to catch regressions**

Run: `pytest tests/ -x -q`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add custom_components/cover_time_based/cover_base.py tests/test_close_includes_tilt.py
git commit -m "feat: skip travel resync pulse when close_cover called at settled 0"
```

---

## Task 5: Trailing tilt-close when option is enabled

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py` — `async_close_cover`
- Modify: `tests/test_close_includes_tilt.py`

- [ ] **Step 1: Write the failing tests for the trailing tilt-close**

Append to `tests/test_close_includes_tilt.py`:

```python
class TestTrailingTiltClose:
    """When close_includes_tilt=True, async_close_cover follows the travel
    move with a tilt-close if tilt is not already at 0."""

    @pytest.mark.asyncio
    async def test_sequential_close_option_true_from_fully_open(self, make_cover):
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_close",
            close_includes_tilt=True,
        )
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_travel,
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_travel.assert_awaited_once_with(target=0)
        mock_tilt.assert_awaited_once_with(target=0)

    @pytest.mark.asyncio
    async def test_sequential_close_option_true_from_articulated(self, make_cover):
        """Settled at (0, 100): travel skipped, tilt-close fires."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_close",
            close_includes_tilt=True,
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_travel,
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_travel.assert_not_awaited()
        mock_tilt.assert_awaited_once_with(target=0)

    @pytest.mark.asyncio
    async def test_sequential_close_option_false_from_fully_open(self, make_cover):
        """Option off: travel only, no tilt-close."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_close",
            close_includes_tilt=False,
        )
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_travel,
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_travel.assert_awaited_once_with(target=0)
        mock_tilt.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sequential_close_option_false_from_articulated(self, make_cover):
        """Option off + already at 0 + tilt open: total no-op."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_close",
            close_includes_tilt=False,
        )
        cover.travel_calc.set_position(0)
        cover.tilt_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_travel,
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_travel.assert_not_awaited()
        mock_tilt.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_trailing_tilt_when_tilt_already_zero(self, make_cover):
        """Even with option=true, skip the tilt-close when tilt is already 0."""
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_close",
            close_includes_tilt=True,
        )
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(0)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ),
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_tilt.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_trailing_tilt_when_no_tilt_support(self, make_cover):
        """No tilt support → no trailing tilt-close, period."""
        cover = make_cover(close_includes_tilt=True)  # no tilt times
        cover.travel_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ),
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_tilt.assert_not_awaited()
```

- [ ] **Step 2: Run tests to verify they fail where expected**

Run: `pytest tests/test_close_includes_tilt.py::TestTrailingTiltClose -v`

Expected:
- `test_sequential_close_option_true_from_fully_open` FAIL (tilt-close not implemented)
- `test_sequential_close_option_true_from_articulated` FAIL (tilt-close not implemented)
- `test_sequential_close_option_false_from_fully_open` PASS (trailing tilt-close not implemented, so option=false naturally skips it — matches expectation)
- `test_sequential_close_option_false_from_articulated` PASS (settled-at-zero already skips travel)
- `test_no_trailing_tilt_when_tilt_already_zero` PASS (vacuously, nothing implemented)
- `test_no_trailing_tilt_when_no_tilt_support` PASS (vacuously)

- [ ] **Step 3: Implement the trailing tilt-close**

In `custom_components/cover_time_based/cover_base.py`, extend `async_close_cover` (the version from Task 4) — replace it entirely with this:

```python
    async def async_close_cover(self, **kwargs):
        """Close the cover fully.

        Travel is moved to 0 unless already settled there (no resync
        pulse — matches HA convention).

        When close_includes_tilt is True and the cover has tilt support
        and tilt is not already at 0, the slats are closed afterward.
        This makes close_cover land at (0, 0) on strategies that would
        otherwise park tilt at an implicit-open or safe position
        (sequential_close, dual_motor).
        """
        self._require_configured()
        self._log("async_close_cover")
        if self.is_opening:
            self._log("async_close_cover :: currently opening, stopping first")
            await self.async_stop_cover()
            await self._direction_change_delay()

        settled_at_zero = (
            self.travel_calc.current_position() == 0
            and self.travel_calc.travel_direction == TravelStatus.STOPPED
        )
        if not settled_at_zero:
            await self._async_move_to_endpoint(target=0)

        if (
            self._close_includes_tilt
            and self._has_tilt_support()
            and self.tilt_calc.current_position() not in (None, 0)
        ):
            self._log(
                "async_close_cover :: close_includes_tilt=True, "
                "closing tilt to 0"
            )
            await self._async_move_tilt_to_endpoint(target=0)
```

- [ ] **Step 4: Run all tests in this file to verify**

Run: `pytest tests/test_close_includes_tilt.py -v`

Expected: all PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest tests/ -x -q`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add custom_components/cover_time_based/cover_base.py tests/test_close_includes_tilt.py
git commit -m "feat: close_cover follows travel with tilt-close when close_includes_tilt is on"
```

---

## Task 6: Dual_motor parallel tests

**Files:**
- Modify: `tests/test_close_includes_tilt.py`

- [ ] **Step 1: Add dual_motor tests**

Append to `tests/test_close_includes_tilt.py`:

```python
class TestDualMotor:
    """The implementation is strategy-agnostic. Confirm dual_motor behaves
    identically to sequential_close for the trailing tilt-close decision."""

    @pytest.mark.asyncio
    async def test_dual_motor_option_true_closes_tilt_after_travel(self, make_cover):
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            safe_tilt_position=100,
            close_includes_tilt=True,
        )
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)  # parked at safe

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_travel,
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_travel.assert_awaited_once_with(target=0)
        mock_tilt.assert_awaited_once_with(target=0)

    @pytest.mark.asyncio
    async def test_dual_motor_option_false_leaves_tilt_at_safe(self, make_cover):
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="dual_motor",
            tilt_open_switch="switch.tilt_open",
            tilt_close_switch="switch.tilt_close",
            safe_tilt_position=100,
            close_includes_tilt=False,
        )
        cover.travel_calc.set_position(100)
        cover.tilt_calc.set_position(100)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ) as mock_travel,
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_travel.assert_awaited_once_with(target=0)
        mock_tilt.assert_not_awaited()
```

- [ ] **Step 2: Run the new tests**

Run: `pytest tests/test_close_includes_tilt.py::TestDualMotor -v`

Expected: both PASS (implementation is strategy-agnostic; no new code needed).

- [ ] **Step 3: Commit**

```bash
git add tests/test_close_includes_tilt.py
git commit -m "test: confirm close_includes_tilt works for dual_motor"
```

---

## Task 7: Inline and sequential_open regression tests

**Files:**
- Modify: `tests/test_close_includes_tilt.py`

- [ ] **Step 1: Add regression tests**

Append to `tests/test_close_includes_tilt.py`:

```python
class TestUnaffectedStrategies:
    """inline and sequential_open already land tilt at 0 after close_cover,
    so the trailing tilt-close should be a no-op regardless of option value.
    These tests pin that behavior."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("option", [True, False])
    async def test_inline_no_trailing_tilt_close(self, make_cover, option):
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="inline",
            close_includes_tilt=option,
        )
        cover.travel_calc.set_position(100)
        # Simulate the post-_async_move_to_endpoint(0) state for inline:
        # tilt ends at 0 because plan_move_position pre-steps TiltTo(0).
        # Since we mock _async_move_to_endpoint, we set tilt manually.
        cover.tilt_calc.set_position(0)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ),
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_tilt.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("option", [True, False])
    async def test_sequential_open_no_trailing_tilt_close(self, make_cover, option):
        cover = make_cover(
            tilt_time_close=5.0,
            tilt_time_open=5.0,
            tilt_mode="sequential_open",
            close_includes_tilt=option,
        )
        cover.travel_calc.set_position(100)
        # For sequential_open, implicit_tilt_during_travel=0, so tilt sits at 0.
        cover.tilt_calc.set_position(0)

        with (
            patch.object(cover, "async_write_ha_state"),
            patch.object(
                cover, "_async_move_to_endpoint", new_callable=AsyncMock
            ),
            patch.object(
                cover, "_async_move_tilt_to_endpoint", new_callable=AsyncMock
            ) as mock_tilt,
        ):
            await cover.async_close_cover()

        mock_tilt.assert_not_awaited()
```

- [ ] **Step 2: Run the regression tests**

Run: `pytest tests/test_close_includes_tilt.py::TestUnaffectedStrategies -v`

Expected: all 4 parametrized cases PASS.

- [ ] **Step 3: Run the full suite once more**

Run: `pytest tests/ -x -q`

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_close_includes_tilt.py
git commit -m "test: confirm inline and sequential_open unaffected by close_includes_tilt"
```

---

## Task 8: Expose option in websocket_api

**Files:**
- Modify: `custom_components/cover_time_based/websocket_api.py:26-30` (imports), `48-69` (_FIELD_MAP), `124-150` (get_config response), `158-216` (update_config schema)
- Modify: `tests/test_websocket_api.py`

- [ ] **Step 1: Write the failing round-trip test**

Append to `tests/test_websocket_api.py` after the `TestDualMotorFieldRoundTrip` class:

```python
class TestCloseIncludesTiltFieldRoundTrip:
    """get_config returns the value (defaulting to True); update_config persists it."""

    @pytest.mark.asyncio
    async def test_get_config_returns_default_true_when_unset(self):
        hass = MagicMock()
        connection = MagicMock()
        entry = MagicMock()
        entry.entry_id = ENTRY_ID
        entry.domain = DOMAIN
        entry.options = {"tilt_mode": "sequential_close"}
        msg = {"id": 1, "type": "cover_time_based/get_config", "entity_id": ENTITY_ID}

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(entry, None),
        ):
            handler = _unwrap(ws_get_config)
            await handler(hass, connection, msg)

        result = connection.send_result.call_args[0][1]
        assert result["close_includes_tilt"] is True

    @pytest.mark.asyncio
    async def test_get_config_returns_stored_false(self):
        hass = MagicMock()
        connection = MagicMock()
        entry = MagicMock()
        entry.entry_id = ENTRY_ID
        entry.domain = DOMAIN
        entry.options = {
            "tilt_mode": "sequential_close",
            "close_includes_tilt": False,
        }
        msg = {"id": 1, "type": "cover_time_based/get_config", "entity_id": ENTITY_ID}

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(entry, None),
        ):
            handler = _unwrap(ws_get_config)
            await handler(hass, connection, msg)

        result = connection.send_result.call_args[0][1]
        assert result["close_includes_tilt"] is False

    @pytest.mark.asyncio
    async def test_update_config_persists_close_includes_tilt(self):
        hass = MagicMock()
        connection = MagicMock()
        config_entry = MagicMock()
        config_entry.options = {"tilt_mode": "dual_motor"}
        config_entry.domain = DOMAIN

        msg = {
            "id": 2,
            "type": "cover_time_based/update_config",
            "entity_id": ENTITY_ID,
            "close_includes_tilt": False,
        }

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry, None),
        ):
            handler = _unwrap(ws_update_config)
            await handler(hass, connection, msg)

        new_opts = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_opts["close_includes_tilt"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_websocket_api.py::TestCloseIncludesTiltFieldRoundTrip -v`

Expected: FAIL — field not in get_config response, not in update schema.

- [ ] **Step 3: Add the import**

In `custom_components/cover_time_based/websocket_api.py`, add to the existing `from .cover import (...)` block (around lines 26-40):

```python
    CONF_CLOSE_INCLUDES_TILT,
    DEFAULT_CLOSE_INCLUDES_TILT,
```

- [ ] **Step 4: Add to `_FIELD_MAP`**

Append to `_FIELD_MAP` (around line 68):

```python
    "close_includes_tilt": CONF_CLOSE_INCLUDES_TILT,
```

- [ ] **Step 5: Add to `get_config` response**

In `ws_get_config`'s `send_result` payload (around lines 124-150), add:

```python
            "close_includes_tilt": options.get(
                CONF_CLOSE_INCLUDES_TILT, DEFAULT_CLOSE_INCLUDES_TILT
            ),
```

- [ ] **Step 6: Add to `update_config` schema**

In `ws_update_config`'s `@websocket_api.websocket_command({...})` schema dict (around line 215, after `tilt_stop_switch`), add:

```python
        vol.Optional("close_includes_tilt"): bool,
```

- [ ] **Step 7: Run the websocket tests**

Run: `pytest tests/test_websocket_api.py::TestCloseIncludesTiltFieldRoundTrip -v`

Expected: all 3 PASS.

- [ ] **Step 8: Run the full suite**

Run: `pytest tests/ -x -q`

Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add custom_components/cover_time_based/websocket_api.py tests/test_websocket_api.py
git commit -m "feat: expose close_includes_tilt in websocket config API"
```

---

## Task 9: Expose option in frontend card

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js`

This task has no automated tests — the frontend is a vanilla JS Lit-style component without test infrastructure in scope. The change is small and follows the existing `safe_tilt_position` pattern. Verification is manual.

- [ ] **Step 1: Find the dual_motor / sequential_close UI region**

Open `custom_components/cover_time_based/frontend/cover-time-based-card.js` and locate the block around line 1112 where `safe_tilt_position` is rendered. Note the conditional rendering pattern that shows fields only when `tilt_mode === "dual_motor"`.

- [ ] **Step 2: Add the option to the local state defaults**

Find the existing block around line 640-670 that handles tilt-mode-specific defaults (it currently handles `safe_tilt_position` and `max_tilt_allowed_position`). Add `close_includes_tilt` so it:
- defaults to `true` when tilt_mode becomes `sequential_close` or `dual_motor`
- is cleared (set to `null`) when tilt_mode is `none`, `inline`, or `sequential_open`

Match the existing style; example structure (adapt to actual surrounding code):

```javascript
if (tilt_mode === "sequential_close" || tilt_mode === "dual_motor") {
  if (this._config.close_includes_tilt == null) {
    updates.close_includes_tilt = true;
  }
} else {
  updates.close_includes_tilt = null;
}
```

- [ ] **Step 3: Add the UI control**

In the render method around line 1100-1130, after the dual-motor / sequential-close-specific fields, add a checkbox/toggle for `close_includes_tilt`. The control should only render when `c.tilt_mode === "sequential_close" || c.tilt_mode === "dual_motor"`. Follow the same translation-key + on-change pattern as the existing fields:

```javascript
${c.tilt_mode === "sequential_close" || c.tilt_mode === "dual_motor"
  ? html`
      <ha-formfield label="Close cover also closes slats">
        <ha-switch
          .checked=${c.close_includes_tilt !== false}
          @change=${(e) =>
            this._updateLocal({ close_includes_tilt: e.target.checked })}
        ></ha-switch>
      </ha-formfield>
    `
  : ""}
```

(Adapt label / component names to whatever the existing card uses — search for `ha-switch` or `ha-formfield` elsewhere in the file to match the convention.)

- [ ] **Step 4: Add translation strings if applicable**

Check `custom_components/cover_time_based/translations/en.json` for similar config-option strings. If translations are used for field labels in the card, add an entry for `close_includes_tilt` describing what it does. If the card uses hardcoded English strings, skip this step.

- [ ] **Step 5: Manual verification**

Restart Home Assistant (or reload the integration) and:
- Open a cover's config card.
- Select `sequential_close` or `dual_motor` as the tilt mode.
- Verify the "Close cover also closes slats" toggle appears and defaults to on.
- Toggle it off, save, reopen the card — verify it persists.
- Switch tilt mode to `inline` — verify the toggle disappears.

- [ ] **Step 6: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
# Also stage translations if changed:
# git add custom_components/cover_time_based/translations/en.json
git commit -m "feat: expose close_includes_tilt toggle in cover config card"
```

---

## Task 10: Final verification

- [ ] **Step 1: Full test pass**

Run: `pytest tests/ -q`

Expected: all green.

- [ ] **Step 2: Lint / format**

Run: `ruff check custom_components/cover_time_based/ tests/ && ruff format --check custom_components/cover_time_based/ tests/`

If ruff finds issues, run `ruff check --fix` and `ruff format` then re-stage and amend the relevant commit (only if it's the most recent — otherwise add a fixup commit).

- [ ] **Step 3: Review the full diff against main**

Run: `git diff main..HEAD --stat`

Confirm only the expected files changed: `const.py`, `cover_base.py`, `cover.py`, `websocket_api.py`, `cover-time-based-card.js`, `tests/conftest.py`, `tests/test_base_movement.py`, `tests/test_close_includes_tilt.py`, `tests/test_websocket_api.py`, the design spec, and this plan.

- [ ] **Step 4: Open PR**

```bash
git push -u origin toggle
gh pr create --title "feat: add close_includes_tilt option; redefine is_closed as travel-only" --body "$(cat <<'EOF'
## Summary
- Redefine `is_closed` to track travel position only (drop the AND-tilt branch). The cover is "closed" when its travel is at 0, regardless of slat position. Matches HA conventions and unsticks `cover.toggle` on tilt covers.
- Add per-cover `close_includes_tilt` option (default `true`) for `sequential_close` and `dual_motor`. When on, `close_cover` follows travel→0 with a tilt→0 so the cover lands at `(0, 0)`. When off, `close_cover` does travel only and slats are handled separately by `close_cover_tilt`.
- Skip the travel resync motor pulse when `close_cover` is called at settled travel=0 (matches HA convention; replaces the special-case logic from the abandoned PR #74).

Addresses issue #70 with a different approach than PR #74 — see [docs/superpowers/specs/2026-05-17-close-includes-tilt-design.md](docs/superpowers/specs/2026-05-17-close-includes-tilt-design.md) for the design rationale.

Closes #74 in spirit (different implementation, broader scope).

## Test plan
- [ ] `pytest tests/` — all green
- [ ] On a real sequential_close cover: `cover.toggle` closes in one press (travel + slats), opens in one press
- [ ] On a real sequential_close cover with `close_includes_tilt=false`: `cover.toggle` closes travel only; second toggle press opens
- [ ] On a real dual_motor cover: `cover.toggle` closes both motors in sequence (default)
- [ ] On inline / sequential_open covers: no behavior change observed
- [ ] Frontend card shows the toggle only for sequential_close and dual_motor
EOF
)"
```

---

## Self-Review

**Spec coverage:** Every section of the spec maps to a task:
- "Change 1: Redefine `is_closed`" → Task 2
- "Change 2: New `close_includes_tilt` option" → Tasks 1, 3, 4 (constructor wiring)
- "Change 3: Implementation in `async_close_cover`" → Tasks 4, 5
- "Files changed" line items → Tasks 1, 2, 3 (cover_base), 3 (cover.py), 8 (websocket), 5 (tests new file), 2 (tests modified)
- Frontend wiring (mentioned indirectly in the websocket_api task and the design's general scope) → Task 9
- "Tests" list → Tasks 2, 4, 5, 6, 7, 8

**Placeholder scan:** No TBD/TODO/"fill in details" in any step. The frontend task (Task 9) is light on "exact code" because the card's existing pattern needs to be matched and the file is too large to dump inline; the steps name specific line ranges and the pattern to copy. Manual verification is explicit.

**Type consistency:** `_close_includes_tilt` attribute name is consistent across tasks. `CONF_CLOSE_INCLUDES_TILT` / `DEFAULT_CLOSE_INCLUDES_TILT` constants are consistent. Tests reference `cover._close_includes_tilt` (matches the constructor assignment in Task 3). `close_includes_tilt` kwarg name matches across `__init__`, `_create_cover_from_options`, `make_cover` fixture, and WS field map.
