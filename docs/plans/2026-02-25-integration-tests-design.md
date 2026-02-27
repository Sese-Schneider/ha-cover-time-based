# Integration Test Design

## Problem

All 20 existing test files use a custom `make_hass` fixture backed by MagicMock.
This mock lacks a real event bus, state machine, and service registry.
Bugs at integration boundaries — the switch feedback loop, timer-driven auto-stop,
multi-phase tilt lifecycle — slip through unit tests and only surface during manual testing.

## Approach: Hybrid

Keep existing unit tests for pure logic (TravelCalculator, tilt strategies, calibration math).
Add a focused set of integration tests using `pytest-homeassistant-custom-component`
that exercise the full stack through a real HA instance.

## Infrastructure

### Real HA Instance

`pytest-homeassistant-custom-component` provides a `hass` fixture with:
- Real event bus (state_changed events fire and propagate)
- Real state machine (entity states are stored and retrievable)
- Real service registry (service calls dispatch to handlers)
- Real config entry lifecycle (async_setup_entry, async_unload_entry)

### Mock Switch Entities

Use `input_boolean` entities as stand-ins for physical relays.
When the cover calls `homeassistant.turn_on` on a switch entity,
the input_boolean state changes to "on" and fires a real `state_changed` event.
Our cover entity's `async_added_to_hass` listener picks this up,
testing the full echo-filtering and external-detection logic.

### Time Control

Use HA's `async_fire_time_changed` to advance the clock.
This triggers `async_track_utc_time_change` callbacks,
allowing us to test auto-stop, position tracking, run-on delays,
and multi-phase lifecycle transitions without real wall-clock waits.

### File Structure

```
tests/
  integration/
    conftest.py          # HA fixtures, helper to create cover via config entry
    test_lifecycle.py    # Config load, restart restore
    test_movement.py     # Open/close/stop/set_position, auto-stop, endpoint resync
    test_feedback.py     # Echo filtering, external button detection
    test_tilt.py         # Multi-phase dual motor, sequential constraints
    test_modes.py        # Toggle stop-before-reverse, pulse timing
```

## Test Scenarios

### 1. Config Entry Loads Correctly
Load a config entry with switch mode + sequential tilt.
Verify: cover entity exists, has correct device class, reports correct supported features.

### 2. Position Restored on Restart
Set up a cover, move it to 50%, unload, reload.
Verify: position is restored to 50%.

### 3. Open → Track → Auto-Stop
Call `cover.open_cover`. Advance time.
Verify: switch turned on, position increases over time, switch turns off at 100%.

### 4. Stop During Movement
Start opening, advance partway, call `cover.stop_cover`.
Verify: switch turns off, position freezes at intermediate value.

### 5. Set Position Mid-Range
Call `cover.set_cover_position(position=50)`.
Verify: relay activates, position tracks to 50%, relay deactivates at target.

### 6. Endpoint Resync
Position tracker already at 0. Call `cover.close_cover`.
Verify: relay still activates, run-on timer fires, relay deactivates after run-on.

### 7. Echo Filtering
Call `cover.open_cover` (which turns on the switch).
Verify: the resulting switch state_changed event is filtered (not treated as external).

### 8. External Button Press
Directly change the switch entity state (simulating a physical button press).
Verify: cover detects external change, starts tracking movement.

### 9. Dual Motor Tilt Lifecycle
Cover at position 50%, tilt at 50%. Call `cover.set_cover_position(position=20)`.
Verify three phases: tilt moves to safe position → travel to 20% → tilt restores to 50%.

### 10. Sequential Tilt Constraints
Cover at position 0%, tilt at 30%. Call `cover.open_cover`.
Verify: tilt moves to 100% first, then travel begins.
Also verify: tilt commands are rejected when cover is not at position 0%.

### 11. Toggle Mode Stop-Before-Reverse
Cover opening via toggle relay. Call `cover.close_cover`.
Verify: stop pulse sent → wait pulse_time → close pulse sent.

### 12. Pulse Mode Timing
Call `cover.open_cover` in pulse mode.
Verify: open switch pulsed on → off after pulse_time.
Call `cover.stop_cover`. Verify: stop switch pulsed.

## What We Don't Test Here

- **TravelCalculator math** — unit tests cover this
- **Tilt strategy planning logic** — unit tests cover this
- **Calibration stepping** — complex UI-driven workflow, stays as unit tests
- **WebSocket API** — extensive unit tests already exist

## Success Criteria

Integration tests catch the class of bugs unit tests miss:
- Feedback loop bugs (echo not filtered, external press not detected)
- Timer bugs (auto-stop doesn't fire, run-on never cancels)
- Multi-phase sequencing bugs (phases out of order, missing phase)
- Config → entity wiring bugs (wrong mode, missing tilt strategy)

## Code Fixes (Pre-Requisites)

The behavioral spec review identified 6 bugs to fix before or alongside integration tests:

1. Remove stop switch support from switch mode and toggle mode
2. Pulse mode external state change: react on OFF→ON (rising edge), not ON→OFF
3. Toggle mode external state change: react on OFF→ON only, ignore ON→OFF
4. Remove toggle mode same-direction override (async_open/close_cover overrides)
5. Endpoint resync: send command + runon even when already at target
6. Tilt overhead calibration: use 1/5 steps, not 1/10
