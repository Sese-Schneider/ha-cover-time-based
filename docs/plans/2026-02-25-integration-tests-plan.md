# Integration Tests & Bug Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 6 identified bugs and add focused integration tests using `pytest-homeassistant-custom-component` to catch feedback-loop, lifecycle, and timer bugs that unit tests miss.

**Architecture:** Bug fixes first (with unit tests proving the fix), then integration test infrastructure, then 12 integration test scenarios exercising the full HA stack. Integration tests use real HA event bus, state machine, and service registry with `input_boolean` entities as mock switches.

**Tech Stack:** pytest, pytest-asyncio, pytest-homeassistant-custom-component, homeassistant core test utilities

**Reference:** Read `docs/plans/2026-02-25-behavioral-spec.md` for expected behavior. Read `docs/plans/2026-02-25-integration-tests-design.md` for design rationale.

---

## Phase 1: Bug Fixes

### Task 1: Remove stop switch support from switch mode and toggle mode

**Files:**
- Modify: `custom_components/cover_time_based/cover_switch_mode.py:79-158`
- Modify: `custom_components/cover_time_based/cover_toggle_mode.py:210-266`
- Test: `tests/test_relay_commands.py` (add tests)

**Context:** Stop switches are only valid in pulse mode. Switch mode and toggle mode should not reference `_stop_switch_entity_id`. Currently both modes check and manipulate `_stop_switch_entity_id` in their `_send_open`, `_send_close`, and `_send_stop` methods.

**Step 1: Write failing tests**

Add tests to `tests/test_relay_commands.py` that verify switch mode and toggle mode never call services on a stop switch entity, even when one is configured:

```python
@pytest.mark.asyncio
async def test_switch_mode_ignores_stop_switch(make_hass, make_cover):
    """Switch mode should not interact with a stop switch."""
    hass = make_hass()
    cover = make_cover(
        hass=hass,
        control_mode="switch",
        stop_switch="switch.stop",
    )
    await cover._send_open()
    await cover._send_close()
    await cover._send_stop()
    # stop switch should never be referenced in any call
    for call in hass.services.async_call.call_args_list:
        entity_ids = call[1].get("service_data", call[0][2] if len(call[0]) > 2 else {}).get("entity_id", "")
        assert "switch.stop" not in str(entity_ids), f"Stop switch referenced: {call}"


@pytest.mark.asyncio
async def test_toggle_mode_ignores_stop_switch(make_hass, make_cover):
    """Toggle mode should not interact with a stop switch."""
    hass = make_hass()
    cover = make_cover(
        hass=hass,
        control_mode="toggle",
        stop_switch="switch.stop",
    )
    await cover._send_open()
    await cover._send_close()
    for call in hass.services.async_call.call_args_list:
        entity_ids = call[1].get("service_data", call[0][2] if len(call[0]) > 2 else {}).get("entity_id", "")
        assert "switch.stop" not in str(entity_ids), f"Stop switch referenced: {call}"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_relay_commands.py -v -k "stop_switch"`
Expected: FAIL (stop switch entity IS currently referenced)

**Step 3: Fix the code**

In `cover_switch_mode.py`, remove all `_stop_switch_entity_id` blocks from `_send_open` (lines 83-104), `_send_close` (lines 110-131), and `_send_stop` (lines 138-158). In `_send_stop`, just turn off both open and close switches (no stop switch).

In `cover_toggle_mode.py`, remove all `_stop_switch_entity_id` blocks from `_send_open` (lines 214-233) and `_send_close` (lines 243-262).

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_relay_commands.py -v -k "stop_switch"`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (some existing tests may need updating if they assert stop switch calls)

**Step 6: Commit**

```bash
git add -A && git commit -m "fix: remove stop switch support from switch and toggle modes

Stop switches are only valid in pulse mode. Switch mode and toggle mode
should never interact with a stop switch entity."
```

---

### Task 2: Fix pulse mode external state change to react on rising edge

**Files:**
- Modify: `custom_components/cover_time_based/cover_switch.py:38`
- Test: `tests/test_state_monitoring.py` (add test)

**Context:** `SwitchCoverTimeBased._handle_external_state_change` (line 38) currently checks `if old_val != "on" or new_val != "off"` — this reacts on the falling edge (ON→OFF). It should react on the rising edge (OFF→ON), because the ON signal is the button press; the OFF is just the button release.

**Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_pulse_mode_reacts_on_rising_edge(make_hass, make_cover):
    """Pulse mode should react on OFF→ON (rising edge), not ON→OFF."""
    hass = make_hass()
    cover = make_cover(hass=hass, control_mode="pulse")
    cover.travel_calc.update_position(50)

    # OFF→ON should trigger movement
    with patch.object(cover, "async_open_cover", new_callable=AsyncMock) as mock_open:
        await cover._handle_external_state_change(
            cover._open_switch_entity_id, "off", "on"
        )
        mock_open.assert_called_once()

    # ON→OFF should be ignored
    with patch.object(cover, "async_open_cover", new_callable=AsyncMock) as mock_open:
        await cover._handle_external_state_change(
            cover._open_switch_entity_id, "on", "off"
        )
        mock_open.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_state_monitoring.py -v -k "rising_edge"`
Expected: FAIL (currently reacts on ON→OFF, not OFF→ON)

**Step 3: Fix the code**

In `cover_switch.py` line 38, change:
```python
if old_val != "on" or new_val != "off":
```
to:
```python
if new_val != "on":
```

**Step 4: Run tests**

Run: `pytest tests/ -v`
Expected: All pass (update any existing tests that assert ON→OFF behavior)

**Step 5: Commit**

```bash
git add -A && git commit -m "fix: pulse mode reacts on rising edge (OFF→ON) not falling edge

The ON signal is the button press; OFF is just the release and should
be ignored."
```

---

### Task 3: Fix toggle mode external state change to react on OFF→ON only

**Files:**
- Modify: `custom_components/cover_time_based/cover_toggle_mode.py:116-145`
- Test: `tests/test_state_monitoring.py` (add test)

**Context:** `ToggleModeCover._handle_external_state_change` currently reacts to any state transition (both ON→OFF and OFF→ON). Only OFF→ON (rising edge) should trigger a reaction. ON→OFF should be ignored.

**Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_toggle_mode_reacts_only_on_rising_edge(make_hass, make_cover):
    """Toggle mode should react on OFF→ON only, ignore ON→OFF."""
    hass = make_hass()
    cover = make_cover(hass=hass, control_mode="toggle")
    cover.travel_calc.update_position(50)

    # OFF→ON should trigger
    with patch.object(cover, "async_open_cover", new_callable=AsyncMock) as mock_open:
        await cover._handle_external_state_change(
            cover._open_switch_entity_id, "off", "on"
        )
        mock_open.assert_called_once()

    # ON→OFF should be ignored
    with patch.object(cover, "async_open_cover", new_callable=AsyncMock) as mock_open:
        await cover._handle_external_state_change(
            cover._open_switch_entity_id, "on", "off"
        )
        mock_open.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_state_monitoring.py -v -k "toggle_mode_reacts_only"`
Expected: FAIL (ON→OFF currently triggers movement)

**Step 3: Fix the code**

In `cover_toggle_mode.py`, at the start of `_handle_external_state_change` (after line 128), add:

```python
if new_val != "on":
    return
```

This goes before the debounce check. The debounce logic remains unchanged.

**Step 4: Run tests**

Run: `pytest tests/ -v`
Expected: All pass

**Step 5: Commit**

```bash
git add -A && git commit -m "fix: toggle mode external state reacts on OFF→ON only

ON→OFF transitions are just relay releases and should be ignored.
Only the rising edge (OFF→ON) indicates a real button press."
```

---

### Task 4: Remove toggle mode same-direction override

**Files:**
- Modify: `custom_components/cover_time_based/cover_toggle_mode.py:51-85`
- Test: `tests/test_cover_toggle_mode.py` (add test)

**Context:** `ToggleModeCover` overrides `async_open_cover` and `async_close_cover` to treat same-direction commands as stop. This should be removed — the HA cover services should behave identically regardless of control mode. `open` means open, `close` means close, `stop` means stop.

**Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_toggle_open_while_opening_does_not_stop(make_hass, make_cover):
    """In toggle mode, calling open while already opening should NOT stop."""
    hass = make_hass()
    cover = make_cover(hass=hass, control_mode="toggle")
    cover.travel_calc.update_position(50)
    cover.travel_calc.start_travel(100)  # simulate opening

    with patch.object(cover, "async_stop_cover", new_callable=AsyncMock) as mock_stop:
        await cover.async_open_cover()
        mock_stop.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cover_toggle_mode.py -v -k "does_not_stop"`
Expected: FAIL (currently stops on same-direction)

**Step 3: Fix the code**

Delete the `async_open_cover` override (lines 69-85) and `async_close_cover` override (lines 51-67) entirely from `ToggleModeCover`. The base class implementations will be used instead.

Also remove the `_triggered_externally` property/attribute if it was only used by these overrides (check first).

**Step 4: Run tests**

Run: `pytest tests/ -v`
Expected: All pass (some existing toggle mode tests may need updating)

**Step 5: Commit**

```bash
git add -A && git commit -m "fix: remove toggle mode same-direction override

Cover services (open/close/stop) should behave identically regardless
of control mode. No special-casing for toggle mode."
```

---

### Task 5: Fix endpoint resync — send command even when already at target

**Files:**
- Modify: `custom_components/cover_time_based/cover_base.py:432-434`
- Test: `tests/test_base_movement.py` (add test)

**Context:** `_async_move_to_endpoint` returns early at line 433-434 when `current == target`. Instead, it should send the relay command plus endpoint run-on to allow physical resyncing.

**Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_endpoint_resync_sends_command_when_at_target(make_hass, make_cover):
    """Even if tracker says we're at the endpoint, still send command + runon."""
    hass = make_hass()
    cover = make_cover(hass=hass, endpoint_runon_time=2.0)
    cover.travel_calc.update_position(0)  # already at closed endpoint

    await cover._async_move_to_endpoint(0)  # close when already closed

    # Should have sent the close command
    assert hass.services.async_call.call_count > 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_base_movement.py -v -k "resync"`
Expected: FAIL (currently returns early, no service call)

**Step 3: Fix the code**

In `cover_base.py`, replace lines 432-434:

```python
current = self.travel_calc.current_position()
if current is not None and current == target:
    return
```

With:

```python
current = self.travel_calc.current_position()
if current is not None and current == target:
    # Resync: send command + endpoint run-on even though tracker
    # says we're already there. Physical cover may need resyncing.
    self._cancel_delay_task()
    self._last_command = command
    await self._async_handle_command(command)
    if (
        self._endpoint_runon_time is not None
        and self._endpoint_runon_time > 0
    ):
        self._delay_task = self.hass.async_create_task(
            self._delayed_stop(self._endpoint_runon_time)
        )
    else:
        await self._async_handle_command(SERVICE_STOP_COVER)
    return
```

**Step 4: Run tests**

Run: `pytest tests/ -v`
Expected: All pass

**Step 5: Commit**

```bash
git add -A && git commit -m "fix: endpoint resync sends command + runon when already at target

Pressing open/close when tracker already shows the endpoint should
still send the relay command plus run-on time. This allows physical
covers that are out of sync to resync."
```

---

### Task 6: Fix tilt overhead calibration step size (1/5 not 1/10)

**Files:**
- Modify: `custom_components/cover_time_based/cover_calibration.py:168,196`
- Test: `tests/test_calibration.py` (add test)

**Context:** Overhead calibration uses `step_duration = travel_time / 10` and `pct = (i + 1) * 10` for both travel and tilt. Travel should use 1/10 steps (8 steps + 2/10 continuous). Tilt should use 1/5 steps (3 steps + 2/5 continuous). Currently `CALIBRATION_OVERHEAD_STEPS = 8` and `CALIBRATION_TILT_OVERHEAD_STEPS = 3`. The pattern is: `total_divisions = num_steps + 2`, `step_pct = 100 // total_divisions`.

**Step 1: Write failing test**

Add to `tests/test_calibration.py`:

```python
@pytest.mark.asyncio
async def test_tilt_overhead_uses_one_fifth_steps(make_hass, make_cover):
    """Tilt overhead calibration should use 1/5 steps (20%), not 1/10 (10%)."""
    hass = make_hass()
    cover = make_cover(hass=hass, tilt_time_open=10.0, tilt_time_close=10.0)
    # Start tilt overhead calibration
    await cover.start_calibration(calibration_type="tilt_overhead", direction="open")
    # step_duration should be 10.0 / 5 = 2.0, not 10.0 / 10 = 1.0
    assert cover._calibration.step_duration == 2.0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_calibration.py -v -k "one_fifth"`
Expected: FAIL (step_duration is 1.0, expected 2.0)

**Step 3: Fix the code**

In `cover_calibration.py`, replace the hardcoded step size calculation. Change line 168:

```python
step_duration = travel_time / 10
```

To:

```python
total_divisions = num_steps + 2
step_pct = 100 // total_divisions
step_duration = travel_time * step_pct / 100
```

Then pass `step_pct` to `_run_overhead_steps`. Update the method signature at line 176:

```python
async def _run_overhead_steps(self, _step_duration, num_steps, is_tilt):
```

To:

```python
async def _run_overhead_steps(self, _step_duration, num_steps, step_pct, is_tilt):
```

And update line 196 from:

```python
pct = (i + 1) * 10
```

To:

```python
pct = (i + 1) * step_pct
```

Update the caller at line 172-174 to pass `step_pct`:

```python
self._calibration.automation_task = self.hass.async_create_task(
    self._run_overhead_steps(step_duration, num_steps, step_pct, is_tilt)
)
```

**Step 4: Run tests**

Run: `pytest tests/ -v`
Expected: All pass (verify travel calibration still uses 10% steps)

**Step 5: Commit**

```bash
git add -A && git commit -m "fix: tilt overhead calibration uses 1/5 steps, not 1/10

Travel calibration: 8 steps of 10% + continuous 20% (unchanged).
Tilt calibration: 3 steps of 20% + continuous 40% (was incorrectly
using 10% steps like travel)."
```

---

## Phase 2: Integration Test Infrastructure

### Task 7: Create integration test conftest and verify it works

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/test_smoke.py`

**Context:** Set up the HA integration test infrastructure. Use `pytest-homeassistant-custom-component` for a real `hass` instance. Create `input_boolean` entities to simulate switches. Use `MockConfigEntry` to load the integration.

**Step 1: Create the integration test directory**

```bash
mkdir -p tests/integration
touch tests/integration/__init__.py
```

**Step 2: Write conftest.py**

```python
"""Integration test fixtures for cover_time_based."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "cover_time_based"


@pytest.fixture
async def setup_input_booleans(hass: HomeAssistant):
    """Create input_boolean entities to act as mock switches."""
    assert await async_setup_component(hass, "input_boolean", {
        "input_boolean": {
            "open_switch": {"name": "Open Switch"},
            "close_switch": {"name": "Close Switch"},
            "stop_switch": {"name": "Stop Switch"},
            "tilt_open": {"name": "Tilt Open"},
            "tilt_close": {"name": "Tilt Close"},
        }
    })
    await hass.async_block_till_done()


@pytest.fixture
def base_options():
    """Return minimal config options for a switch-mode cover."""
    return {
        "control_mode": "switch",
        "open_switch_entity_id": "input_boolean.open_switch",
        "close_switch_entity_id": "input_boolean.close_switch",
        "travel_time_open": 30,
        "travel_time_close": 30,
    }


@pytest.fixture
async def setup_cover(hass: HomeAssistant, setup_input_booleans, base_options):
    """Create and load a cover_time_based config entry, return the entity."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Cover",
        data={},
        options=base_options,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("cover.test_cover")
    assert state is not None, "Cover entity was not created"

    return entry
```

**Step 3: Write a smoke test**

```python
"""Smoke test: verify integration loads and creates an entity."""

import pytest
from homeassistant.core import HomeAssistant


@pytest.mark.asyncio
async def test_integration_loads(hass: HomeAssistant, setup_cover):
    """Config entry loads and creates a cover entity."""
    state = hass.states.get("cover.test_cover")
    assert state is not None
    assert state.state in ("open", "closed", "unknown")
```

**Step 4: Run the smoke test**

Run: `pytest tests/integration/test_smoke.py -v`
Expected: PASS — this proves the HA integration test infrastructure works end-to-end.

If this fails, debug the fixture setup. Common issues:
- Wrong domain name
- Missing platform setup
- Entity ID doesn't match expected pattern

**Step 5: Commit**

```bash
git add tests/integration/ && git commit -m "test: add integration test infrastructure with smoke test

Uses pytest-homeassistant-custom-component for a real HA instance.
input_boolean entities simulate physical switches. MockConfigEntry
loads the integration through the real config entry lifecycle."
```

---

## Phase 3: Integration Test Scenarios

### Task 8: Movement lifecycle tests

**Files:**
- Create: `tests/integration/test_movement.py`

**Write 4 tests:**

1. **Open → track → auto-stop**: Call `cover.open_cover` service. Use `async_fire_time_changed` to advance time. Assert: open switch turned on, position increases, switch turns off at 100%.

2. **Stop during movement**: Start opening, advance time halfway, call `cover.stop_cover`. Assert: switch turns off, position is ~50%.

3. **Set position mid-range**: Call `cover.set_cover_position(position=50)`. Advance time. Assert: relay on, position reaches 50%, relay off.

4. **Endpoint resync**: Set position to 0 via `set_known_position`. Call `cover.close_cover`. Assert: relay fires, run-on timer fires, relay stops. (Requires `endpoint_runon_time` in options.)

Each test should:
- Set up the cover via the `setup_cover` fixture (override `base_options` if needed)
- Use `hass.services.async_call("cover", "open_cover", ...)` to trigger actions
- Use `async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=N))` to advance time
- Assert switch entity states and cover entity attributes

Run: `pytest tests/integration/test_movement.py -v`
Expected: All 4 pass

Commit: `git add -A && git commit -m "test: integration tests for movement lifecycle"`

---

### Task 9: Switch feedback loop tests

**Files:**
- Create: `tests/integration/test_feedback.py`

**Write 2 tests:**

1. **Echo filtering**: Call `cover.open_cover`. The service turns on `input_boolean.open_switch`. The state_changed event should be filtered (cover doesn't interpret it as an external button press). Assert: no double-start, movement continues normally.

2. **External button**: Directly call `input_boolean.turn_on` on the open switch (without going through the cover service). Assert: cover detects external state change and starts tracking movement.

Run: `pytest tests/integration/test_feedback.py -v`
Expected: Both pass

Commit: `git add -A && git commit -m "test: integration tests for switch feedback loop"`

---

### Task 10: Multi-phase tilt lifecycle tests

**Files:**
- Create: `tests/integration/test_tilt.py`

**Write 2 tests:**

1. **Dual motor tilt lifecycle**: Configure cover with `tilt_mode=dual_motor`, separate tilt switches. Set position=50, tilt=50. Call `set_cover_position(20)`. Assert three phases: tilt safe → travel to 20% → tilt restore to 50%.

2. **Sequential tilt constraints**: Configure cover with `tilt_mode=sequential`. Position=0, tilt=30. Call `open_cover`. Assert: tilt moves to 100% first, then travel begins. Also test: tilt command rejected when position != 0.

Run: `pytest tests/integration/test_tilt.py -v`
Expected: Both pass

Commit: `git add -A && git commit -m "test: integration tests for multi-phase tilt lifecycle"`

---

### Task 11: Mode-specific behavior tests

**Files:**
- Create: `tests/integration/test_modes.py`

**Write 2 tests:**

1. **Toggle stop-before-reverse**: Configure toggle mode. Start opening. Call `close_cover`. Assert: stop pulse sent (open switch toggled to stop), pause, then close pulse sent (close switch toggled to start closing).

2. **Pulse mode timing**: Configure pulse mode with stop switch. Call `open_cover`. Assert: open switch pulsed on then off after `pulse_time`. Call `stop_cover`. Assert: stop switch pulsed.

Run: `pytest tests/integration/test_modes.py -v`
Expected: Both pass

Commit: `git add -A && git commit -m "test: integration tests for mode-specific behavior"`

---

### Task 12: Config and restart tests

**Files:**
- Create: `tests/integration/test_lifecycle.py`

**Write 2 tests:**

1. **Config entry creates correct entity**: Load config with pulse mode + sequential tilt. Assert: entity has correct supported features (position + tilt), device class is correct.

2. **Position restored on restart**: Load cover, set position to 50 via `set_known_position`. Unload entry (`async_unload_entry`). Reload. Assert: position is restored to 50%.

Run: `pytest tests/integration/test_lifecycle.py -v`
Expected: Both pass

Commit: `git add -A && git commit -m "test: integration tests for config lifecycle and restart"`

---

## Phase 4: Final Validation

### Task 13: Full test suite + lint + type check

**Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests pass (both unit and integration)

**Step 2: Lint**

Run: `ruff check . && ruff format .`

**Step 3: Type check**

Run: `npx pyright`

**Step 4: Fix any issues found, commit fixes**

**Step 5: Create PR**

```bash
git push -u origin feat/integration-tests
gh pr create --title "Add integration tests and fix 6 behavioral bugs" --body "$(cat <<'EOF'
## Summary
- Fix 6 bugs identified during behavioral spec review
- Add integration test infrastructure using pytest-homeassistant-custom-component
- Add 12 focused integration test scenarios covering movement lifecycle, switch
  feedback loop, multi-phase tilt, mode-specific behavior, and config lifecycle

## Bug Fixes
1. Remove stop switch support from switch/toggle modes (pulse-only)
2. Pulse mode reacts on rising edge (OFF→ON), not falling edge
3. Toggle mode reacts on OFF→ON only, ignores ON→OFF
4. Remove toggle mode same-direction override
5. Endpoint resync sends command + runon when already at target
6. Tilt calibration uses 1/5 steps, not 1/10

## Test plan
- [ ] All existing unit tests pass
- [ ] All 12 new integration tests pass
- [ ] Manual test: switch mode open/close/stop
- [ ] Manual test: pulse mode with stop switch
- [ ] Manual test: toggle mode direction change
- [ ] Manual test: endpoint resync (press close when already closed)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
