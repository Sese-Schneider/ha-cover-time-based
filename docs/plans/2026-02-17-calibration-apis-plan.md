# Calibration APIs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `start_calibration` and `stop_calibration` services that help users measure timing parameters by physically testing their covers, then auto-save the results to the config entry.

**Architecture:** Two new entity services on `CoverTimeBased`. Calibration state lives as a `_calibration` dataclass on the entity. Three test types: simple timing (user-timed), motor overhead (automated 1/10th steps), and minimum movement time (incremental pulses). Results are written to `config_entry.options` and the entry is reloaded. As part of this work, `travel_startup_delay` + `travel_delay_at_end` are merged into `travel_motor_overhead`, and `tilt_startup_delay` becomes `tilt_motor_overhead`.

**Tech Stack:** Python, Home Assistant config entries, asyncio, pytest, voluptuous schemas.

**Design doc:** `docs/plans/2026-02-17-calibration-apis-design.md`

---

## Task 1: Merge startup delay + delay-at-end into motor overhead (config layer)

Rename the config keys so the UI and storage use the new names. The internal behavior stays the same for now (split 50/50 into startup and end delay).

**Files:**
- Modify: `custom_components/cover_time_based/cover.py:28-36` (constants)
- Modify: `custom_components/cover_time_based/cover.py:148-170` (factory function)
- Modify: `custom_components/cover_time_based/cover_base.py:34-42` (local constant copies)
- Modify: `custom_components/cover_time_based/cover_base.py:46-91` (constructor)
- Modify: `custom_components/cover_time_based/cover_base.py:187-217` (startup delay usage)
- Modify: `custom_components/cover_time_based/cover_base.py:235-256` (extra_state_attributes)
- Modify: `custom_components/cover_time_based/cover_base.py:751-791` (delay-at-end usage)
- Modify: `custom_components/cover_time_based/config_flow.py` (options schema)
- Modify: `custom_components/cover_time_based/strings.json`
- Modify: `tests/conftest.py` (make_cover fixture)
- Test: `tests/test_motor_overhead.py` (new)

### Step 1: Write failing tests for motor overhead split

Create `tests/test_motor_overhead.py` with tests that verify the 50/50 split behavior:

```python
"""Tests for travel_motor_overhead and tilt_motor_overhead config."""

import pytest
from unittest.mock import patch


class TestTravelMotorOverhead:
    """Test that travel_motor_overhead splits into startup delay and end delay."""

    @pytest.mark.asyncio
    async def test_overhead_splits_into_startup_and_end_delay(self, make_cover):
        """Motor overhead of 2.0 should give 1.0 startup + 1.0 end delay."""
        cover = make_cover(travel_motor_overhead=2.0)
        assert cover._travel_startup_delay == 1.0
        assert cover._travel_delay_at_end == 1.0

    @pytest.mark.asyncio
    async def test_no_overhead_gives_no_delays(self, make_cover):
        """No motor overhead means no startup or end delay."""
        cover = make_cover()
        assert cover._travel_startup_delay is None
        assert cover._travel_delay_at_end is None

    @pytest.mark.asyncio
    async def test_odd_overhead_splits_evenly(self, make_cover):
        """Motor overhead of 1.5 should give 0.75 + 0.75."""
        cover = make_cover(travel_motor_overhead=1.5)
        assert cover._travel_startup_delay == 0.75
        assert cover._travel_delay_at_end == 0.75


class TestTiltMotorOverhead:
    """Test that tilt_motor_overhead maps to tilt startup delay."""

    @pytest.mark.asyncio
    async def test_tilt_overhead_sets_startup_delay(self, make_cover):
        """Tilt motor overhead should set the tilt startup delay."""
        cover = make_cover(
            tilt_time_down=5.0,
            tilt_time_up=5.0,
            tilt_motor_overhead=1.0,
        )
        assert cover._tilt_startup_delay == 0.5

    @pytest.mark.asyncio
    async def test_no_tilt_overhead(self, make_cover):
        """No tilt motor overhead means no tilt startup delay."""
        cover = make_cover(tilt_time_down=5.0, tilt_time_up=5.0)
        assert cover._tilt_startup_delay is None
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_motor_overhead.py -v`
Expected: FAIL — `make_cover` doesn't accept `travel_motor_overhead` or `tilt_motor_overhead` kwargs yet.

### Step 3: Update constants in cover.py

Replace in `cover.py` lines 33-36:
```python
# Old:
CONF_TRAVEL_DELAY_AT_END = "travel_delay_at_end"
CONF_MIN_MOVEMENT_TIME = "min_movement_time"
CONF_TRAVEL_STARTUP_DELAY = "travel_startup_delay"
CONF_TILT_STARTUP_DELAY = "tilt_startup_delay"

# New:
CONF_TRAVEL_MOTOR_OVERHEAD = "travel_motor_overhead"
CONF_TILT_MOTOR_OVERHEAD = "tilt_motor_overhead"
CONF_MIN_MOVEMENT_TIME = "min_movement_time"
```

Also remove the old constants. Keep `CONF_TRAVEL_DELAY_AT_END` and `CONF_TRAVEL_STARTUP_DELAY` and `CONF_TILT_STARTUP_DELAY` temporarily as aliases if needed for the YAML deprecation path, or remove them entirely if YAML parsing can be updated too.

### Step 4: Update the factory function in cover.py

In `_create_cover_from_options` (line 148), read the new config keys and split:

```python
travel_motor_overhead = options.get(CONF_TRAVEL_MOTOR_OVERHEAD)
tilt_motor_overhead = options.get(CONF_TILT_MOTOR_OVERHEAD)

common = dict(
    ...
    travel_delay_at_end=travel_motor_overhead / 2 if travel_motor_overhead else None,
    min_movement_time=options.get(CONF_MIN_MOVEMENT_TIME),
    travel_startup_delay=travel_motor_overhead / 2 if travel_motor_overhead else None,
    tilt_startup_delay=tilt_motor_overhead / 2 if tilt_motor_overhead else None,
)
```

Note: The `CoverTimeBased.__init__` signature stays the same internally — it still takes `travel_delay_at_end`, `travel_startup_delay`, `tilt_startup_delay` as separate values. The merge is done at the factory/config layer.

### Step 5: Update conftest.py make_cover fixture

Replace `travel_startup_delay`, `tilt_startup_delay`, `travel_delay_at_end` params with `travel_motor_overhead` and `tilt_motor_overhead`:

```python
def _make(
    ...
    travel_motor_overhead=None,
    tilt_motor_overhead=None,
    min_movement_time=None,
):
    ...
    if travel_motor_overhead is not None:
        options[CONF_TRAVEL_MOTOR_OVERHEAD] = travel_motor_overhead
    if tilt_motor_overhead is not None:
        options[CONF_TILT_MOTOR_OVERHEAD] = tilt_motor_overhead
    if min_movement_time is not None:
        options[CONF_MIN_MOVEMENT_TIME] = min_movement_time
```

### Step 6: Update extra_state_attributes in cover_base.py

Replace the three separate attribute entries with two:
```python
if self._travel_startup_delay is not None:
    overhead = (self._travel_startup_delay or 0) + (self._travel_delay_at_end or 0)
    attr[CONF_TRAVEL_MOTOR_OVERHEAD] = overhead
if self._tilt_startup_delay is not None:
    attr[CONF_TILT_MOTOR_OVERHEAD] = self._tilt_startup_delay * 2
```

Or store `_travel_motor_overhead` and `_tilt_motor_overhead` as instance vars on the base class alongside the split values. This is cleaner:

In `__init__`, add:
```python
self._travel_motor_overhead = travel_motor_overhead  # stored for extra_state_attributes
self._tilt_motor_overhead = tilt_motor_overhead
```

But wait — `__init__` doesn't receive the overhead values directly, it receives the split values. The cleanest approach: pass the overhead values through and store them, then derive the split values.

Update `__init__` signature:
```python
def __init__(self, device_id, name, travel_moves_with_tilt, travel_time_down,
             travel_time_up, tilt_time_down, tilt_time_up, travel_motor_overhead,
             tilt_motor_overhead, min_movement_time):
```

And derive internally:
```python
self._travel_motor_overhead = travel_motor_overhead
self._tilt_motor_overhead = tilt_motor_overhead
self._min_movement_time = min_movement_time
self._travel_startup_delay = travel_motor_overhead / 2 if travel_motor_overhead else None
self._travel_delay_at_end = travel_motor_overhead / 2 if travel_motor_overhead else None
self._tilt_startup_delay = tilt_motor_overhead / 2 if tilt_motor_overhead else None
```

Then the factory becomes simpler (just passes the raw values through) and `extra_state_attributes` can reference the overhead values directly.

This requires updating all subclass constructors that call `super().__init__()` and the factory function.

### Step 7: Update config_flow.py

Replace `travel_startup_delay`, `travel_delay_at_end`, `tilt_startup_delay` with `travel_motor_overhead` and `tilt_motor_overhead` in the "Advanced" section of `_build_details_schema()`.

### Step 8: Update strings.json and translations

Replace the three old translation keys with two new ones.

### Step 9: Update existing tests that use old parameter names

Search all test files for `travel_startup_delay`, `travel_delay_at_end`, `tilt_startup_delay` and update to use `travel_motor_overhead` / `tilt_motor_overhead`.

### Step 10: Run all tests

Run: `pytest tests/ -v`
Expected: ALL PASS

### Step 11: Run linting

Run: `ruff check . && ruff format . && npx pyright`

### Step 12: Commit

```bash
git add -A
git commit -m "refactor: merge startup/end delays into travel_motor_overhead and tilt_motor_overhead"
```

---

## Task 2: Store config_entry reference on the entity

The calibration services need to update `config_entry.options`. Currently the entity has no reference to its config entry.

**Files:**
- Modify: `custom_components/cover_time_based/cover.py:311-322` (async_setup_entry)
- Modify: `custom_components/cover_time_based/cover_base.py:46-91` (add _config_entry_id)
- Test: `tests/test_calibration.py` (new — will grow across tasks)

### Step 1: Write failing test

```python
"""Tests for calibration services."""

import pytest
from unittest.mock import patch, MagicMock


class TestConfigEntryAccess:
    """Test that config entry ID is available on the entity."""

    @pytest.mark.asyncio
    async def test_config_entry_id_stored(self, make_cover):
        """Cover should store its config entry ID for later options update."""
        cover = make_cover()
        assert cover._config_entry_id is not None
        assert cover._config_entry_id == "test_cover"
```

### Step 2: Run test to verify it fails

Run: `pytest tests/test_calibration.py::TestConfigEntryAccess -v`
Expected: FAIL — `_config_entry_id` attribute doesn't exist.

### Step 3: Add _config_entry_id to CoverTimeBased.__init__

In `cover_base.py`, add to `__init__`:
```python
self._config_entry_id = None  # Set by async_setup_entry
```

### Step 4: Set it in async_setup_entry

In `cover.py` `async_setup_entry`, after creating the entity:
```python
entity._config_entry_id = config_entry.entry_id
```

### Step 5: Set it in the test fixture

In `conftest.py`, the `make_cover` fixture already passes `device_id="test_cover"`. Set `_config_entry_id` there too:
```python
cover = _create_cover_from_options(options, device_id="test_cover", name="Test Cover")
cover.hass = make_hass()
cover._config_entry_id = "test_cover"
```

### Step 6: Run test to verify it passes

Run: `pytest tests/test_calibration.py::TestConfigEntryAccess -v`
Expected: PASS

### Step 7: Commit

```bash
git add -A
git commit -m "feat: store config entry ID on cover entity for calibration support"
```

---

## Task 3: Add CalibrationState dataclass and service schemas

Define the data structures and voluptuous schemas for the two new services.

**Files:**
- Create: `custom_components/cover_time_based/calibration.py`
- Modify: `custom_components/cover_time_based/cover.py` (add constants, schemas)
- Test: `tests/test_calibration.py` (extend)

### Step 1: Write failing tests for CalibrationState

```python
class TestCalibrationState:
    """Test the CalibrationState dataclass."""

    def test_initial_state(self):
        """CalibrationState should initialize with required fields."""
        from custom_components.cover_time_based.calibration import CalibrationState

        state = CalibrationState(
            attribute="travel_time_down",
            timeout=120.0,
        )
        assert state.attribute == "travel_time_down"
        assert state.timeout == 120.0
        assert state.started_at is not None
        assert state.step_count == 0
        assert state.step_duration is None
        assert state.last_pulse_duration is None
        assert state.timeout_task is None
        assert state.automation_task is None
```

### Step 2: Run test to verify it fails

Run: `pytest tests/test_calibration.py::TestCalibrationState -v`
Expected: FAIL — module doesn't exist.

### Step 3: Create calibration.py

```python
"""Calibration support for cover_time_based."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from asyncio import Task

CALIBRATION_STEP_PAUSE = 2.0
CALIBRATION_OVERHEAD_STEPS = 10
CALIBRATION_MIN_MOVEMENT_START = 0.1
CALIBRATION_MIN_MOVEMENT_INCREMENT = 0.1

CALIBRATABLE_ATTRIBUTES = [
    "travel_time_down",
    "travel_time_up",
    "tilt_time_down",
    "tilt_time_up",
    "travel_motor_overhead",
    "tilt_motor_overhead",
    "min_movement_time",
]

SERVICE_START_CALIBRATION = "start_calibration"
SERVICE_STOP_CALIBRATION = "stop_calibration"


@dataclass
class CalibrationState:
    """Holds state for an in-progress calibration test."""

    attribute: str
    timeout: float
    started_at: float = field(default_factory=time.monotonic)
    step_count: int = 0
    step_duration: float | None = None
    last_pulse_duration: float | None = None
    timeout_task: Task | None = field(default=None, repr=False)
    automation_task: Task | None = field(default=None, repr=False)
```

### Step 4: Run test to verify it passes

Run: `pytest tests/test_calibration.py::TestCalibrationState -v`
Expected: PASS

### Step 5: Commit

```bash
git add -A
git commit -m "feat: add CalibrationState dataclass and calibration constants"
```

---

## Task 4: Implement start_calibration for simple time tests

Start with the simplest case: `travel_time_down` and `travel_time_up`. The service starts moving the cover and records the start time.

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py` (add start_calibration, _calibration attr)
- Modify: `custom_components/cover_time_based/cover.py` (register service)
- Test: `tests/test_calibration.py` (extend)

### Step 1: Write failing tests

```python
class TestStartCalibrationTravelTime:
    """Test start_calibration for travel_time_down/up."""

    @pytest.mark.asyncio
    async def test_start_travel_time_down(self, make_cover):
        """Starting calibration for travel_time_down should move cover down."""
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_time_down", timeout=120.0
            )
        assert cover._calibration is not None
        assert cover._calibration.attribute == "travel_time_down"
        cover.hass.services.async_call.assert_awaited()

    @pytest.mark.asyncio
    async def test_start_travel_time_up(self, make_cover):
        """Starting calibration for travel_time_up should move cover up."""
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_time_up", timeout=120.0
            )
        assert cover._calibration is not None
        assert cover._calibration.attribute == "travel_time_up"

    @pytest.mark.asyncio
    async def test_cannot_start_while_calibrating(self, make_cover):
        """Should raise if calibration already running."""
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_time_down", timeout=120.0
            )
            with pytest.raises(Exception, match="[Cc]alibration already"):
                await cover.start_calibration(
                    attribute="travel_time_up", timeout=120.0
                )

    @pytest.mark.asyncio
    async def test_calibration_exposes_state_attributes(self, make_cover):
        """Extra state attributes should include calibration status."""
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_time_down", timeout=120.0
            )
        attrs = cover.extra_state_attributes
        assert attrs["calibration_active"] is True
        assert attrs["calibration_attribute"] == "travel_time_down"
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_calibration.py::TestStartCalibrationTravelTime -v`
Expected: FAIL

### Step 3: Implement start_calibration on CoverTimeBased

In `cover_base.py`, add `_calibration = None` to `__init__`, then add:

```python
async def start_calibration(self, **kwargs):
    """Start a calibration test for the specified attribute."""
    attribute = kwargs["attribute"]
    timeout = kwargs["timeout"]

    if self._calibration is not None:
        raise HomeAssistantError("Calibration already in progress")

    from .calibration import CalibrationState
    self._calibration = CalibrationState(attribute=attribute, timeout=timeout)

    # Start timeout task
    self._calibration.timeout_task = self.hass.async_create_task(
        self._calibration_timeout()
    )

    # Start the appropriate test
    if attribute in ("travel_time_down", "travel_time_up"):
        await self._start_simple_time_test(attribute)
    # Other types handled in later tasks

    self.async_write_ha_state()

async def _start_simple_time_test(self, attribute):
    """Start a simple timing test — move in one direction."""
    if attribute == "travel_time_down":
        await self._async_handle_command(SERVICE_CLOSE_COVER)
    else:
        await self._async_handle_command(SERVICE_OPEN_COVER)

async def _calibration_timeout(self):
    """Auto-stop calibration after timeout."""
    await sleep(self._calibration.timeout)
    _LOGGER.warning("Calibration timed out for %s", self._calibration.attribute)
    await self._send_stop()
    self._calibration = None
    self.async_write_ha_state()
```

Update `extra_state_attributes` to include calibration state:
```python
if self._calibration is not None:
    attr["calibration_active"] = True
    attr["calibration_attribute"] = self._calibration.attribute
    if self._calibration.step_count > 0:
        attr["calibration_step"] = self._calibration.step_count
```

### Step 4: Register the service in cover.py

In `async_setup_entry`, add:
```python
platform.async_register_entity_service(
    SERVICE_START_CALIBRATION,
    vol.Schema({
        vol.Required("attribute"): vol.In(CALIBRATABLE_ATTRIBUTES),
        vol.Required("timeout"): vol.All(vol.Coerce(float), vol.Range(min=1)),
    }),
    "start_calibration",
)
```

### Step 5: Run tests

Run: `pytest tests/test_calibration.py::TestStartCalibrationTravelTime -v`
Expected: PASS

### Step 6: Commit

```bash
git add -A
git commit -m "feat: implement start_calibration for simple travel time tests"
```

---

## Task 5: Implement stop_calibration for simple time tests

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py`
- Modify: `custom_components/cover_time_based/cover.py` (register service)
- Test: `tests/test_calibration.py` (extend)

### Step 1: Write failing tests

```python
class TestStopCalibrationTravelTime:
    """Test stop_calibration for travel_time_down/up."""

    @pytest.mark.asyncio
    async def test_stop_calculates_elapsed_time(self, make_cover):
        """stop_calibration should calculate elapsed time."""
        cover = make_cover()
        cover._config_entry_id = "test_cover"

        # Mock the config entry on hass
        mock_entry = MagicMock()
        mock_entry.options = dict(cover.hass.config_entries.async_get_entry().options or {})
        cover.hass.config_entries.async_get_entry.return_value = mock_entry

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_down", timeout=120.0)

            # Fake elapsed time by backdating started_at
            cover._calibration.started_at -= 45.0

            result = await cover.stop_calibration()

        assert result["value"] == pytest.approx(45.0, abs=0.5)
        assert cover._calibration is None

    @pytest.mark.asyncio
    async def test_stop_with_cancel_discards(self, make_cover):
        """stop_calibration with cancel=True should discard results."""
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="travel_time_down", timeout=120.0)
            await cover.stop_calibration(cancel=True)
        assert cover._calibration is None

    @pytest.mark.asyncio
    async def test_stop_without_active_calibration_raises(self, make_cover):
        """stop_calibration with no active calibration should raise."""
        cover = make_cover()
        with pytest.raises(Exception, match="[Nn]o calibration"):
            await cover.stop_calibration()
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_calibration.py::TestStopCalibrationTravelTime -v`
Expected: FAIL

### Step 3: Implement stop_calibration

```python
async def stop_calibration(self, **kwargs):
    """Stop calibration and optionally save the result."""
    if self._calibration is None:
        raise HomeAssistantError("No calibration in progress")

    cancel = kwargs.get("cancel", False)

    # Cancel timeout task
    if self._calibration.timeout_task and not self._calibration.timeout_task.done():
        self._calibration.timeout_task.cancel()

    # Cancel automation task if running
    if self._calibration.automation_task and not self._calibration.automation_task.done():
        self._calibration.automation_task.cancel()

    # Stop the motor
    await self._send_stop()

    result = {}
    if not cancel:
        value = self._calculate_calibration_result()
        result["value"] = value
        await self._save_calibration_result(self._calibration.attribute, value)

    self._calibration = None
    self.async_write_ha_state()
    return result

def _calculate_calibration_result(self):
    """Calculate the calibration result based on test type."""
    import time
    elapsed = time.monotonic() - self._calibration.started_at
    attribute = self._calibration.attribute

    if attribute in ("travel_time_down", "travel_time_up",
                     "tilt_time_down", "tilt_time_up"):
        return round(elapsed, 1)

    # Other types handled in later tasks
    return elapsed

async def _save_calibration_result(self, attribute, value):
    """Save the calibration result to config entry options."""
    from .cover import CONF_TRAVELLING_TIME_DOWN, CONF_TRAVELLING_TIME_UP

    # Map calibration attribute names to config entry option keys
    ATTR_TO_CONF = {
        "travel_time_down": CONF_TRAVELLING_TIME_DOWN,
        "travel_time_up": CONF_TRAVELLING_TIME_UP,
        "tilt_time_down": CONF_TILTING_TIME_DOWN,
        "tilt_time_up": CONF_TILTING_TIME_UP,
        "travel_motor_overhead": CONF_TRAVEL_MOTOR_OVERHEAD,
        "tilt_motor_overhead": CONF_TILT_MOTOR_OVERHEAD,
        "min_movement_time": CONF_MIN_MOVEMENT_TIME,
    }

    conf_key = ATTR_TO_CONF[attribute]
    entry = self.hass.config_entries.async_get_entry(self._config_entry_id)
    new_options = dict(entry.options)
    new_options[conf_key] = value
    self.hass.config_entries.async_update_entry(entry, options=new_options)
```

### Step 4: Register the service

```python
platform.async_register_entity_service(
    SERVICE_STOP_CALIBRATION,
    vol.Schema({
        vol.Optional("cancel", default=False): cv.boolean,
    }),
    "stop_calibration",
)
```

### Step 5: Run tests

Run: `pytest tests/test_calibration.py::TestStopCalibrationTravelTime -v`
Expected: PASS

### Step 6: Commit

```bash
git add -A
git commit -m "feat: implement stop_calibration for simple travel/tilt time tests"
```

---

## Task 6: Implement start_calibration for tilt time tests

Same as travel time but validates `travel_moves_with_tilt=false` and moves tilt instead of travel.

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py`
- Test: `tests/test_calibration.py` (extend)

### Step 1: Write failing tests

```python
class TestCalibrationTiltTime:
    """Test calibration for tilt_time_down/up."""

    @pytest.mark.asyncio
    async def test_start_tilt_time_down(self, make_cover):
        """Should start closing tilt."""
        cover = make_cover(
            tilt_time_down=5.0, tilt_time_up=5.0,
            travel_moves_with_tilt=False,
        )
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(attribute="tilt_time_down", timeout=30.0)
        assert cover._calibration.attribute == "tilt_time_down"

    @pytest.mark.asyncio
    async def test_tilt_rejected_when_travel_moves_with_tilt(self, make_cover):
        """Should reject tilt calibration when travel_moves_with_tilt=True."""
        cover = make_cover(
            tilt_time_down=5.0, tilt_time_up=5.0,
            travel_moves_with_tilt=True,
        )
        with pytest.raises(Exception, match="travel_moves_with_tilt"):
            await cover.start_calibration(attribute="tilt_time_down", timeout=30.0)
```

### Step 2: Implement validation and tilt movement

Add to `start_calibration`:
```python
if attribute in ("tilt_time_down", "tilt_time_up"):
    if self._travel_moves_with_tilt:
        raise HomeAssistantError(
            "Tilt time calibration not available when travel_moves_with_tilt is enabled"
        )
    await self._start_simple_time_test(attribute)
```

Update `_start_simple_time_test` to handle tilt direction:
```python
async def _start_simple_time_test(self, attribute):
    if attribute in ("travel_time_down", "tilt_time_down"):
        await self._async_handle_command(SERVICE_CLOSE_COVER)
    else:
        await self._async_handle_command(SERVICE_OPEN_COVER)
```

### Step 3: Run tests

Run: `pytest tests/test_calibration.py::TestCalibrationTiltTime -v`
Expected: PASS

### Step 4: Commit

```bash
git add -A
git commit -m "feat: add tilt time calibration with travel_moves_with_tilt validation"
```

---

## Task 7: Implement motor overhead calibration (automated step test)

The most complex test type: automated 1/10th steps with pause between each.

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py`
- Test: `tests/test_calibration.py` (extend)

### Step 1: Write failing tests

```python
class TestMotorOverheadCalibration:
    """Test motor overhead calibration with automated steps."""

    @pytest.mark.asyncio
    async def test_prerequisite_travel_time_required(self, make_cover):
        """Should fail if travel_time is not configured."""
        cover = make_cover(travel_time_down=None, travel_time_up=None)
        with pytest.raises(Exception, match="[Tt]ravel time"):
            await cover.start_calibration(
                attribute="travel_motor_overhead", timeout=300.0
            )

    @pytest.mark.asyncio
    async def test_starts_automated_steps(self, make_cover):
        """Should create an automation task for the step sequence."""
        cover = make_cover(travel_time_down=60.0, travel_time_up=60.0)
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_motor_overhead", timeout=300.0
            )
        assert cover._calibration.automation_task is not None
        assert cover._calibration.step_duration == 6.0  # 60 / 10

    @pytest.mark.asyncio
    async def test_overhead_calculation(self, make_cover):
        """If 15 steps needed instead of 10, overhead = step_duration - (travel_time / 15)."""
        cover = make_cover(travel_time_down=60.0, travel_time_up=60.0)
        cover._config_entry_id = "test_cover"

        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry.return_value = mock_entry

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="travel_motor_overhead", timeout=300.0
            )
            # Simulate 15 steps completed
            cover._calibration.step_count = 15
            result = await cover.stop_calibration()

        # overhead = 6.0 - (60.0 / 15) = 6.0 - 4.0 = 2.0
        assert result["value"] == pytest.approx(2.0, abs=0.1)
```

### Step 2: Implement the overhead test

Add to `start_calibration`:
```python
elif attribute in ("travel_motor_overhead", "tilt_motor_overhead"):
    await self._start_overhead_test(attribute)
```

```python
async def _start_overhead_test(self, attribute):
    """Start an automated step test for motor overhead."""
    if attribute == "travel_motor_overhead":
        travel_time = self._travel_time_down or self._travel_time_up
        if not travel_time:
            raise HomeAssistantError("Travel time must be configured before testing motor overhead")
    else:
        travel_time = self._tilting_time_down or self._tilting_time_up
        if not travel_time:
            raise HomeAssistantError("Tilt time must be configured before testing motor overhead")

    from .calibration import CALIBRATION_OVERHEAD_STEPS
    step_duration = travel_time / CALIBRATION_OVERHEAD_STEPS
    self._calibration.step_duration = step_duration

    self._calibration.automation_task = self.hass.async_create_task(
        self._run_overhead_steps(attribute, step_duration)
    )

async def _run_overhead_steps(self, attribute, step_duration):
    """Execute the automated step sequence."""
    from .calibration import CALIBRATION_STEP_PAUSE

    is_travel = attribute == "travel_motor_overhead"
    # Alternate direction each time? No — just go in one direction (close)
    close_cmd = SERVICE_CLOSE_COVER

    try:
        while True:
            # Move for step_duration
            await self._async_handle_command(close_cmd)
            await sleep(step_duration)
            await self._send_stop()
            self._calibration.step_count += 1
            self.async_write_ha_state()

            # Pause between steps
            await sleep(CALIBRATION_STEP_PAUSE)
    except asyncio.CancelledError:
        pass
```

Add to `_calculate_calibration_result`:
```python
if attribute in ("travel_motor_overhead", "tilt_motor_overhead"):
    step_duration = self._calibration.step_duration
    step_count = self._calibration.step_count
    if attribute == "travel_motor_overhead":
        travel_time = self._travel_time_down or self._travel_time_up
    else:
        travel_time = self._tilting_time_down or self._tilting_time_up
    overhead = step_duration - (travel_time / step_count)
    return round(overhead, 2)
```

### Step 3: Run tests

Run: `pytest tests/test_calibration.py::TestMotorOverheadCalibration -v`
Expected: PASS

### Step 4: Commit

```bash
git add -A
git commit -m "feat: implement motor overhead calibration with automated step test"
```

---

## Task 8: Implement min_movement_time calibration

Sends incrementally longer pulses until the user sees movement.

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py`
- Test: `tests/test_calibration.py` (extend)

### Step 1: Write failing tests

```python
class TestMinMovementTimeCalibration:
    """Test min_movement_time calibration with incremental pulses."""

    @pytest.mark.asyncio
    async def test_starts_incremental_pulses(self, make_cover):
        """Should create automation task for pulse sequence."""
        cover = make_cover()
        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="min_movement_time", timeout=60.0
            )
        assert cover._calibration.automation_task is not None

    @pytest.mark.asyncio
    async def test_min_movement_result_is_last_pulse(self, make_cover):
        """Result should be the last pulse duration sent."""
        cover = make_cover()
        cover._config_entry_id = "test_cover"

        mock_entry = MagicMock()
        mock_entry.options = {}
        cover.hass.config_entries.async_get_entry.return_value = mock_entry

        with patch.object(cover, "async_write_ha_state"):
            await cover.start_calibration(
                attribute="min_movement_time", timeout=60.0
            )
            # Simulate 5 pulses completed (0.1, 0.2, 0.3, 0.4, 0.5)
            cover._calibration.step_count = 5
            cover._calibration.last_pulse_duration = 0.5
            result = await cover.stop_calibration()

        assert result["value"] == pytest.approx(0.5)
```

### Step 2: Implement

Add to `start_calibration`:
```python
elif attribute == "min_movement_time":
    self._calibration.automation_task = self.hass.async_create_task(
        self._run_min_movement_pulses()
    )
```

```python
async def _run_min_movement_pulses(self):
    """Send increasingly longer pulses."""
    from .calibration import (
        CALIBRATION_MIN_MOVEMENT_START,
        CALIBRATION_MIN_MOVEMENT_INCREMENT,
        CALIBRATION_STEP_PAUSE,
    )

    pulse_duration = CALIBRATION_MIN_MOVEMENT_START

    try:
        while True:
            self._calibration.last_pulse_duration = pulse_duration
            self._calibration.step_count += 1

            await self._async_handle_command(SERVICE_CLOSE_COVER)
            await sleep(pulse_duration)
            await self._send_stop()
            self.async_write_ha_state()

            await sleep(CALIBRATION_STEP_PAUSE)
            pulse_duration += CALIBRATION_MIN_MOVEMENT_INCREMENT
    except asyncio.CancelledError:
        pass
```

Add to `_calculate_calibration_result`:
```python
if attribute == "min_movement_time":
    return round(self._calibration.last_pulse_duration, 2)
```

### Step 3: Run tests

Run: `pytest tests/test_calibration.py::TestMinMovementTimeCalibration -v`
Expected: PASS

### Step 4: Commit

```bash
git add -A
git commit -m "feat: implement min_movement_time calibration with incremental pulses"
```

---

## Task 9: Add service descriptions and translations

**Files:**
- Modify: `custom_components/cover_time_based/services.yaml`
- Modify: `custom_components/cover_time_based/strings.json`
- Modify: `custom_components/cover_time_based/translations/en.json`

### Step 1: Add to services.yaml

```yaml
start_calibration:
  fields:
    entity_id:
      example: cover.blinds
    attribute:
      example: travel_time_down
    timeout:
      example: 120
stop_calibration:
  fields:
    entity_id:
      example: cover.blinds
    cancel:
      example: false
```

### Step 2: Add to strings.json

Add service descriptions under the `services` key:
```json
"start_calibration": {
    "name": "Start calibration",
    "description": "Start a calibration test to measure a timing parameter. The cover will begin moving — call stop_calibration when the desired endpoint is reached.",
    "fields": {
        "attribute": {
            "name": "Attribute",
            "description": "The timing parameter to calibrate"
        },
        "timeout": {
            "name": "Timeout",
            "description": "Safety timeout in seconds — motor will auto-stop if stop_calibration is not called"
        }
    }
},
"stop_calibration": {
    "name": "Stop calibration",
    "description": "Stop an active calibration test. Calculates the result and saves it to the configuration unless cancelled.",
    "fields": {
        "cancel": {
            "name": "Cancel",
            "description": "If true, discard the test results without saving"
        }
    }
}
```

### Step 3: Sync en.json

Copy the services section from strings.json to translations/en.json.

### Step 4: Commit

```bash
git add -A
git commit -m "feat: add service descriptions and translations for calibration APIs"
```

---

## Task 10: Update config_flow for motor overhead rename

Update the options flow UI to show the new field names.

**Files:**
- Modify: `custom_components/cover_time_based/config_flow.py`
- Modify: `custom_components/cover_time_based/strings.json`
- Test: `tests/test_config_flow.py` (update existing tests)

### Step 1: Update _build_details_schema

In the "Advanced" collapsible section, replace:
- `travel_startup_delay` → remove
- `travel_delay_at_end` → remove
- `tilt_startup_delay` → remove
- Add: `travel_motor_overhead` (NumberSelector 0-30, step 0.1)
- Add: `tilt_motor_overhead` (NumberSelector 0-30, step 0.1)

### Step 2: Update strings.json

Replace translation keys for the removed fields with the new ones.

### Step 3: Update config flow tests

Update any test that references the old parameter names.

### Step 4: Run all tests

Run: `pytest tests/ -v`
Expected: ALL PASS

### Step 5: Run linting

Run: `ruff check . && ruff format . && npx pyright`

### Step 6: Commit

```bash
git add -A
git commit -m "feat: update config flow UI for motor overhead parameters"
```

---

## Task 11: Full integration test and cleanup

Run the full test suite, fix any remaining issues, clean up imports.

**Files:**
- All modified files

### Step 1: Run full test suite

Run: `pytest tests/ -v`
Expected: ALL PASS

### Step 2: Run linting and type checking

Run: `ruff check . && ruff format . && npx pyright`

### Step 3: Final commit if needed

```bash
git add -A
git commit -m "chore: cleanup and fix linting issues"
```
