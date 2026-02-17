# Calibration APIs Design

## Overview

Add `start_calibration` and `stop_calibration` services to help users measure and configure timing parameters for their covers. The services automate timing measurement and write results directly to the config entry.

These services only work with config-entry-based covers (not YAML-configured covers, which are deprecated).

A future dashboard configuration card will provide a UI on top of these APIs.

## Services

### `cover_time_based.start_calibration`

| Field | Type | Required | Description |
|---|---|---|---|
| `entity_id` | entity ID | yes | The cover to calibrate |
| `attribute` | select | yes | The parameter to calibrate (see below) |
| `timeout` | number (seconds) | yes | Safety timeout — auto-stops motor and discards results if exceeded |

**Calibratable attributes:**

| Attribute | Description |
|---|---|
| `travel_time_down` | Time for full downward travel |
| `travel_time_up` | Time for full upward travel |
| `tilt_time_down` | Time for full downward tilt (separate-phase covers only) |
| `tilt_time_up` | Time for full upward tilt (separate-phase covers only) |
| `travel_motor_overhead` | Motor startup/stop overhead per activation (travel) |
| `tilt_motor_overhead` | Motor startup/stop overhead per activation (tilt) |
| `min_movement_time` | Shortest relay activation that produces visible movement |

**Validation on start:**

- Fails if a calibration is already running on the entity.
- Fails if the entity is not a config-entry-based cover.
- Warns/fails if a prerequisite is missing:
  - `travel_motor_overhead` requires `travel_time_down` or `travel_time_up` to be set.
  - `tilt_motor_overhead` requires `tilt_time_down` or `tilt_time_up` to be set.
  - `tilt_time_down`/`tilt_time_up` require `travel_moves_with_tilt=false` (separate-phase covers only).

### `cover_time_based.stop_calibration`

| Field | Type | Required | Description |
|---|---|---|---|
| `entity_id` | entity ID | yes | The cover being calibrated |
| `cancel` | boolean | no (default: false) | If true, stop motor and discard results without saving |

**Three ways a test ends:**

1. `stop_calibration(cancel=false)` — stop motor, calculate result, save to config entry, reload.
2. `stop_calibration(cancel=true)` — stop motor, discard results.
3. Timeout fires — stop motor, discard results, fire warning event.

## Test Behaviors

### Simple Time Tests (travel_time_down/up, tilt_time_down/up)

1. `start_calibration` records a timestamp and starts moving the cover in the appropriate direction.
2. The user watches the cover and calls `stop_calibration` when it reaches the desired endpoint.
3. Elapsed time is saved as the attribute value.

No position prerequisites are enforced — the user is responsible for starting the cover at the appropriate position (e.g. fully open before measuring `travel_time_down`).

### Motor Overhead Tests (travel_motor_overhead, tilt_motor_overhead)

These measure the time lost per relay activation due to motor startup inertia and stop overshoot.

1. `start_calibration` begins an automated sequence:
   - Move for 1/10th of the configured travel/tilt time.
   - Pause for 2 seconds (`CALIBRATION_STEP_PAUSE`).
   - Repeat.
2. The user watches and calls `stop_calibration` when the cover reaches the endpoint.
3. Calculation: if travel_time is 60s and each step is 6s, but it took 15 steps instead of 10, then 30s was lost across 15 activations. `overhead = (elapsed_movement_time - travel_time) / step_count` where `elapsed_movement_time = step_count * step_duration`.

Wait, more precisely:
- `step_duration = travel_time / 10`
- `step_count` = number of steps completed when user calls stop
- If the cover should have completed in 10 steps but took N steps: `overhead = ((N - 10) * step_duration) / N`
- Simplified: `overhead = step_duration * (1 - 10/N)`

Actually the simplest model:
- Expected movement per step without overhead: `step_duration` (= travel_time / 10)
- Actual movement per step: `travel_time / step_count` (since it took `step_count` steps to cover the full distance)
- Lost time per step: `step_duration - (travel_time / step_count)`
- So: `overhead = step_duration - (travel_time / step_count)`

**One value for both directions** — motor overhead is a physical property of the motor, same in both directions. The test can be run in either direction.

### Minimum Movement Time (min_movement_time)

1. `start_calibration` begins an automated sequence:
   - Send a 0.1s pulse, pause 2s.
   - Send a 0.2s pulse, pause 2s.
   - Send a 0.3s pulse, pause 2s.
   - Continue incrementing by 0.1s.
2. The user watches and calls `stop_calibration` when they first see the cover move.
3. The duration of the last pulse sent is saved as `min_movement_time`.

## Tilt and Cover Types

Covers fall into two categories:

1. **Separate-phase tilt** (`travel_moves_with_tilt=false`): Tilt happens as a distinct phase at the beginning or end of travel. The tilt mechanism engages before/after the travel mechanism. Tilt time needs to be measured independently — the user starts a close/open and marks when the tilt phase ends and travel begins.

2. **Gradual tilt** (`travel_moves_with_tilt=true`): Tilt is proportional across the full travel range. `tilt_time = travel_time`, so no separate tilt time calibration is needed. The `tilt_time_down`/`tilt_time_up` calibration attributes are not available for these covers.

## Config Refactor: Motor Overhead

As part of this work, the existing timing parameters are merged:

| Old parameters | New parameter |
|---|---|
| `travel_startup_delay` + `travel_delay_at_end` | `travel_motor_overhead` |
| `tilt_startup_delay` | `tilt_motor_overhead` |

The `travel_motor_overhead` value is applied as half before movement and half after movement internally. This simplifies the user-facing configuration from three values to two, and maps directly to what the calibration test measures.

Since these APIs only work with config-entry-based covers and YAML is deprecated, this is a clean break with no backward-compatibility concerns.

## State Management

### Calibration state on the entity

Stored as a private `_calibration` attribute (dataclass or dict):

- `attribute` — what's being tested
- `started_at` — timestamp
- `timeout` — max duration
- `timeout_task` — asyncio task for auto-stop on timeout
- `step_count` — for overhead/min_movement tests, number of steps completed
- `step_duration` — for overhead tests, duration of each step
- `last_pulse_duration` — for min_movement_time, the most recent pulse length
- `automation_task` — asyncio task running the automated step sequence

### Extra state attributes (exposed while calibration is active)

- `calibration_active: true`
- `calibration_attribute: "travel_time_down"`
- `calibration_step: 7` (for overhead/min_movement tests)

These attributes enable a future dashboard card to show live calibration status.

### Config update flow

1. `stop_calibration` calculates the value.
2. Updates `config_entry.options` with the new value.
3. Calls `hass.config_entries.async_reload(entry.entry_id)` to apply.

## Constants

```python
CALIBRATION_STEP_PAUSE = 2.0        # seconds between automated steps
CALIBRATION_OVERHEAD_STEPS = 10     # number of steps per overhead test
CALIBRATION_MIN_MOVEMENT_START = 0.1  # initial pulse duration for min_movement test
CALIBRATION_MIN_MOVEMENT_INCREMENT = 0.1  # pulse duration increment
```

## Future Work

- Dashboard configuration card providing a UI over these APIs
- Visual feedback during calibration (e.g. progress indicators)
- Guided calibration wizard that walks through all parameters in sequence
