# Cover Time Based - Behavioral Specification

This document describes the expected behavior of the `cover_time_based` integration.
Its purpose is to serve as a shared understanding between developer and AI, and as
the basis for integration tests.

**Position convention:** 0 = fully closed, 100 = fully open (HA standard).

---

## 1. Integration Lifecycle

### 1.1 Config Entry Setup

When a config entry is created (via the UI config flow or YAML migration):

1. `__init__.async_setup_entry` runs **once per entry**:
   - Registers the WebSocket API and frontend static path (once globally, not per entry)
   - Forwards the entry to the `cover` platform
   - Registers an update listener so option changes trigger a reload

2. `cover.async_setup_entry` creates the entity:
   - Calls `_create_cover_from_options(entry.options)` to build the correct subclass
   - Registers entity services (`set_known_position`, `set_known_tilt_position`,
     `start_calibration`, `stop_calibration`)

3. The entity's `async_added_to_hass`:
   - Restores position/tilt from the last known state (via `RestoreEntity`)
   - Registers state change listeners on all configured switch entities
     (open, close, stop, tilt_open, tilt_close, tilt_stop)

### 1.2 Config Update (via WebSocket or Options Flow)

When `ws_update_config` updates the config entry options:
1. `hass.config_entries.async_update_entry` is called with new options
2. The update listener fires `async_update_options`
3. Which calls `hass.config_entries.async_reload(entry_id)`
4. The old entity is torn down (`async_will_remove_from_hass`), then a new entity
   is created with the new options

**Expected behavior:** After reload, the cover entity should reflect the new
configuration (control mode, travel times, tilt mode, etc.). Position is restored
from the state machine (RestoreEntity).

### 1.3 Entity Removal

`async_will_remove_from_hass`:
- Unsubscribes all state change listeners
- Cancels pending switch echo timers
- Cancels calibration tasks (timeout + automation)

---

## 2. Control Modes

The integration supports four control modes, each defining how relay commands
are sent to the physical motor controller.

### 2.1 Switch Mode (Latching Relays)

**How it works:** Two switch entities (open + close). No stop switch.
The direction switch stays ON for the entire duration of movement. Turning it OFF
stops the motor.

**Relay sequences:**
- **Open:** turn_off(close_switch) → turn_on(open_switch)
- **Close:** turn_off(open_switch) → turn_on(close_switch)
- **Stop:** turn_off(close_switch) → turn_off(open_switch)

**External state changes (physical button/remote):**
- open_switch ON → start tracking open movement
- open_switch OFF → stop tracking
- close_switch ON → start tracking close movement
- close_switch OFF → stop tracking

### 2.2 Pulse Mode (Momentary Relays)

**How it works:** Two switch entities (open + close), **requires** a stop switch.
A short ON pulse (pulse_time seconds) triggers the motor controller, which latches
internally. The relay turns OFF after the pulse — this is just cleanup, not a stop.

**Relay sequences:**
- **Open:** turn_off(close_switch) → turn_on(open_switch) → [turn_off(stop_switch)]
  → *background:* sleep(pulse_time) → turn_off(open_switch)
- **Close:** turn_off(open_switch) → turn_on(close_switch) → [turn_off(stop_switch)]
  → *background:* sleep(pulse_time) → turn_off(close_switch)
- **Stop:** turn_off(close_switch) → turn_off(open_switch) → turn_on(stop_switch)
  → *background:* sleep(pulse_time) → turn_off(stop_switch)

**External state changes:** Reacts on the ON transition (rising edge):
- open_switch OFF→ON → start tracking open
- close_switch OFF→ON → start tracking close
- stop_switch OFF→ON → stop tracking
- The subsequent OFF transition (button release) is ignored

**Required configuration:** stop_switch is mandatory (raises error if missing).

### 2.3 Toggle Mode

**How it works:** Two switch entities (open + close). No stop switch.
The motor controller toggles state on each pulse. A second pulse on the same
direction button STOPS the motor (not reverses it). Therefore: `_send_stop`
re-pulses the last-used direction switch.

**Relay sequences:**
- **Open:** turn_off(close_switch) → turn_on(open_switch)
  → *background:* sleep(pulse_time) → turn_off(open_switch)
- **Close:** turn_off(open_switch) → turn_on(close_switch)
  → *background:* sleep(pulse_time) → turn_off(close_switch)
- **Stop:** turn_on(last_direction_switch) → *background:* sleep(pulse_time)
  → turn_off(last_direction_switch)
  *(If no last_command, stop is a no-op)*

**Direction change requires two steps:** Because sending the opposite-direction
pulse would stop the motor (not reverse it), a direction change must: stop first →
wait pulse_time → then send new direction.

**No special-casing of cover services:** The open/stop/close buttons in the HA cover
widget (and the corresponding service APIs) should behave identically regardless of
control mode. `open` means open, `close` means close, `stop` means stop. The control
mode only affects what relay commands are sent, not the semantics. If `open` is called
while already opening, it's a no-op (base class handles this via position check).

**External state changes:**
- Reacts on the ON transition (rising edge, OFF→ON) only
- The subsequent OFF transition (relay relaxing) is ignored
- Debounce window = pulse_time + 0.5s to prevent double-triggering
- If cover is already moving when external toggle detected:
  - Same-direction toggle → stop
  - Any-direction toggle (externally triggered) → stop (the physical motor already
    stopped when the button was pressed)

### 2.4 Wrapped Mode

**How it works:** Delegates to an existing HA cover entity. No switch entities.
Sends `cover.open_cover`, `cover.close_cover`, `cover.stop_cover` service calls.

**External state changes:** Monitors the wrapped cover's state:
- State → "opening" → start tracking open
- State → "closing" → start tracking close
- Was "opening"/"closing", now something else → stop tracking

**Self-wrap prevention:** WebSocket update_config rejects wrapping another
`cover_time_based` entity.

---

## 3. Position Tracking (TravelCalculator)

### 3.1 Core Behavior

The `TravelCalculator` predicts cover position based on elapsed time:
- `start_travel(target)` → records start time and direction, begins calculating
- `current_position()` → interpolates between last known position and target
  based on elapsed time / total travel time
- `stop()` → freezes current position at whatever the interpolation says
- `position_reached()` → True when calculated position equals target

**Asymmetric travel times:** `travel_time_down` (open→closed) can differ from
`travel_time_up` (closed→open). The calculator uses the correct one based on
direction.

**Unknown position:** If position has never been set (None), `current_position()`
returns None. Movement commands handle this by assuming the cover is at the
opposite endpoint (so full travel occurs).

### 3.2 Auto-Updater

While the cover is moving, a periodic timer (every 0.1s) fires `auto_updater_hook`:
1. Calls `async_schedule_update_ha_state()` → HA reads `current_cover_position`
   which interpolates from the calculator
2. Checks `position_reached()` → if True, calls `auto_stop_if_necessary()`
3. The auto-updater is stopped when position is reached

### 3.3 Startup Delay

Some motors have a delay between receiving the relay signal and actually starting
to move. `travel_startup_delay` / `tilt_startup_delay` compensate for this:

- When configured, after sending the relay command, we wait `startup_delay` seconds
  before starting the TravelCalculator (so position tracking doesn't run ahead of
  the actual motor)
- During the startup delay, the `_startup_delay_task` is active
- A direction change during startup delay cancels the delay and sends stop

### 3.4 Endpoint Run-On

When the cover reaches a fully open (100) or fully closed (0) endpoint, the relay
stays ON for an extra `endpoint_runon_time` seconds (default 2.0s) before sending
stop. This ensures the cover reaches the mechanical endpoint even if travel time
calibration is slightly off.

For mid-range targets (not 0 or 100), stop is sent immediately when position is
reached.

**Resync behavior:** If the tracker already shows the cover at an endpoint (e.g.
position 100) and the user calls open again, the integration should still send
the open command and perform the endpoint run-on. This allows resyncing the
physical cover to the mechanical endpoint when calibration drift or an obstruction
has caused the tracked and physical positions to diverge. Multiple open/close
presses at an endpoint should each trigger a run-on.

### 3.5 Minimum Movement Time

If configured, movements shorter than `min_movement_time` are rejected (no relay
command sent). This prevents jitter from tiny position adjustments. **Exception:**
Movements to endpoints (0 or 100) are never rejected.

---

## 4. Tilt Strategies

Three tilt modes control how tilt (slat angle) interacts with travel (cover position).

### 4.1 Sequential Tilt

**Physical model:** Single motor. Tilt and travel share the same motor. The slats
can only change angle when the cover is fully closed (position 0). Opening the
cover first fully opens the slats (tilt 100), then the cover rises. Closing the
cover first descends, then tilts the slats closed at the bottom.

**Physical constraints:**
- Slats can only be at a non-100 tilt when cover position is 0 (fully closed)
- The cover cannot start opening until the slats are fully open (tilt 100)
- When the cover is anywhere above position 0, tilt is always 100

**Behavior:**
- Before opening: Slats must flatten to 100% (fully open) first, creating a
  delay (`pre_step_delay`) before position tracking starts
- Tilt-only: Cover must be at position 0 (fully closed) to tilt
- `snap_trackers_to_physical`: If travel position is not 0 (not closed), force
  tilt to 100 (fully open) to match physical reality

**Tilt does NOT restore after position changes.** (`restores_tilt = False`)

### 4.2 Inline Tilt

**Physical model:** Single motor. Tilt is embedded in the travel cycle — at the
start of any movement there's a tilt phase. Tilt works at any position.

**Behavior:**
- Before travel: Tilt moves to the direction endpoint first (0 if closing,
  100 if opening) as a pre-step
- Tilt-only: Just moves tilt directly, no position constraints
- **Tilt restores after position changes** to non-endpoint targets: After travel
  completes, the motor reverses briefly to restore the original tilt angle
- No snap correction needed (tilt is valid at any position)

### 4.3 Dual Motor Tilt

**Physical model:** Separate tilt motor with its own switch entities (tilt_open_switch,
tilt_close_switch). A tilt_stop_switch is only used in pulse mode (same rule as the
main stop switch). The tilt motor is independent of the travel motor.

**Behavior:**
- Before travel: Move slats to `safe_tilt_position` (default 100) first using the
  tilt motor, then start travel using the travel motor. This is a multi-phase
  lifecycle: tilt pre-step → travel → tilt restore
- After travel to endpoint (0 or 100): Restore tilt to the endpoint value
- After travel to mid-range: If `allows_tilt_at_position(target)` → restore
  original tilt; otherwise → stay at safe position
- `max_tilt_allowed_position`: If set, tilt is only allowed when cover position
  is at or below this threshold. Moving tilt when above the threshold first
  moves the cover down to the threshold (travel pre-step)
- `snap_trackers_to_physical`: If travel is above max_tilt_allowed_position,
  force tilt to safe_tilt_position

**Multi-phase lifecycle for travel:**
1. Tilt pre-step: tilt motor moves to safe position
2. `auto_stop_if_necessary` detects tilt reached → calls `_start_pending_travel`
3. Travel phase: travel motor moves to target
4. `auto_stop_if_necessary` detects travel reached → calls `_start_tilt_restore`
5. Tilt restore: tilt motor restores tilt
6. `auto_stop_if_necessary` detects tilt restore reached → done

**Multi-phase lifecycle for tilt (with boundary lock):**
1. Travel pre-step: travel motor moves to max_tilt_allowed_position
2. `auto_stop_if_necessary` detects travel reached → calls `_start_pending_tilt`
3. Tilt phase: tilt motor moves to target
4. Done

---

## 5. Switch Echo Filtering

When the integration sends a command to a switch entity (e.g., `turn_on(open_switch)`),
the switch changes state, which fires a state_change event back to the integration.
Without filtering, this would be misinterpreted as an external button press.

### 5.1 Mechanism

Before sending a command, the integration marks the affected switch(es) as
"pending" with an expected number of transitions:
- `_mark_switch_pending(entity_id, expected_transitions)` increments a counter
- When `_async_switch_state_changed` fires, it checks the counter:
  - If counter > 0: decrement and skip (this is our own echo)
  - If counter == 0: this is an external change, handle it

### 5.2 Transition Counting

- **Switch mode:** Each relay change = 1 transition. `_send_open` marks
  close_switch=1 (if on), open_switch=1.
- **Pulse/Toggle mode:** Each pulse = 2 transitions (ON then OFF after pulse_time).
  `_send_open` marks open_switch=2.
- Safety timeout: After 5 seconds, pending counters are cleared automatically
  (in case a transition never arrives).

### 5.3 What Gets Filtered

- Attribute-only updates (same state string) are always skipped
- State changes during active calibration are always skipped
- Everything else goes through the counter check, then to mode-specific external
  state change handlers

---

## 6. Movement Orchestration

### 6.1 Open/Close (Endpoint Movements)

`async_open_cover` / `async_close_cover`:
1. If moving in the opposite direction, stop first
2. Call `_async_move_to_endpoint(target=100 or 0)`
3. Check startup delay conflicts:
   - If startup delay active for same direction → ignore (already starting)
   - If startup delay active for opposite direction → cancel delay + stop
4. Cancel any active endpoint run-on delay (from a previous movement)
5. If already at target position → send the command + endpoint run-on (resync)
6. If position unknown → assume opposite endpoint
7. Plan tilt for travel (if tilt strategy exists)
8. Send relay command
9. Begin movement tracking (with startup delay if configured)

### 6.2 Set Position (Mid-Range Movements)

`async_set_cover_position`:
1. Determine direction from current vs target
2. Handle startup delay conflicts (same as above)
3. If direction change while already traveling → stop first, recalculate
4. Cancel any active endpoint run-on delay
5. Check minimum movement time
6. Plan tilt for travel
7. Send relay command
8. Begin movement tracking

### 6.3 Stop

`async_stop_cover`:
1. Cancel startup delay task
2. Cancel endpoint run-on delay task
3. Stop travel calculator (freezes position at current interpolation)
4. Stop tilt calculator
5. Snap trackers to physical reality (tilt strategy)
6. Send stop relay command (unless triggered externally)
7. If tilt restore or pre-step was active and has tilt motor → also stop tilt motor
8. Clear `_last_command`

**Toggle mode override:** Only sends stop relay if cover was actually active
(moving, or in startup delay, or in endpoint run-on). This prevents sending a
toggle pulse when the motor is already stopped.

### 6.4 Abandoning Active Lifecycle

At the start of every movement method, `_abandon_active_lifecycle` is called:
- If a tilt restore or pre-step is in progress: stop all motors, stop all
  calculators, stop auto-updater
- Always clears all pending multi-phase state variables

---

## 7. WebSocket API

Five WebSocket commands for the configuration card:

### 7.1 `cover_time_based/get_config`
Returns the current config entry options for a given entity.

### 7.2 `cover_time_based/update_config`
Updates config entry options, triggering entity reload. Validates:
- Cannot wrap another cover_time_based entity
- Travel/tilt times: min 0.1, max 600
- Pulse time: min 0.1, max 10
- Setting a value to null removes it from options

### 7.3 `cover_time_based/start_calibration`
Starts a calibration test. Dispatches to the appropriate calibration type based
on the attribute being calibrated.

### 7.4 `cover_time_based/stop_calibration`
Stops calibration, optionally cancelling (discarding results). Returns the
calculated result if not cancelled.

### 7.5 `cover_time_based/raw_command`
Sends a raw open/close/stop/tilt_open/tilt_close/tilt_stop command, bypassing
position tracking. Used by the calibration screen's manual buttons. Works for
all control modes:
1. If not in calibration: stops active lifecycle tracking first
2. Calls `_raw_direction_command` which sends the relay command directly
   - **Toggle mode only:** if the current direction is opposite to the requested
     direction, it first sends stop, waits pulse_time, then sends the new
     direction (because an opposite-direction pulse would stop the motor, not
     reverse it). This applies to both travel and tilt commands.
   - **All other modes:** sends the command directly (motors handle direction
     changes natively)
3. If not in calibration: clears tracked position to "unknown"

---

## 8. Calibration

### 8.1 Travel/Tilt Time Calibration (Simple)

Measures time for full travel:
1. Start calibration → motor starts moving in specified direction
2. User watches the physical cover
3. User calls stop_calibration when cover reaches the endpoint
4. Result = elapsed time since calibration started

### 8.2 Startup Delay Calibration (Overhead Steps)

Measures motor startup overhead using stepped movements:
1. Phase 1: Execute N stepped moves, each covering 1/Nth of the total range.
   After each step, force-set position (compensating for overhead). Pause between steps.
   - **Travel:** 8 steps of 1/10 each (covering 80%, leaving 20% for continuous phase)
   - **Tilt:** 3 steps of 1/5 each (covering 60%, leaving 40% for continuous phase)
2. Phase 2: Continuous move for remaining distance
3. User calls stop_calibration when cover reaches endpoint
4. Result = (continuous_time - expected_remaining) / step_count
   Represents the average per-step startup overhead

During overhead calibration, the startup delay is temporarily zeroed so the
tracker doesn't compensate for it. Restored after calibration ends.

### 8.3 Minimum Movement Time Calibration (Pulses)

Finds the shortest pulse the motor responds to:
1. Initial 3-second pause (user preparation time)
2. Send increasingly longer pulses: 0.1s, 0.2s, 0.3s, ...
3. 2-second pause between pulses
4. User calls stop_calibration when they see the cover move
5. Result = duration of the last pulse sent

### 8.4 Calibration Guards

- Only one calibration at a time (raises error if already active)
- External state changes are ignored during calibration
- Calibration has a configurable timeout (auto-cancels)
- Tilt time calibration not available if tilt strategy doesn't support it
- Startup delay calibration requires travel/tilt times to be configured first

---

## 9. State Restoration

On startup (`async_added_to_hass`):
- Reads the last stored position from `ATTR_CURRENT_POSITION`
- Reads the last stored tilt from `ATTR_CURRENT_TILT_POSITION`
- Sets these on the respective `TravelCalculator` instances
- If no previous state exists, position remains None (unknown)

---

## 10. Entity Properties

- `is_opening`: True if travel OR tilt calculator is traveling upward
- `is_closing`: True if travel OR tilt calculator is traveling downward
- `is_closed`: True if travel position is 0 AND (no tilt OR tilt is 0)
- `available`: True if required entities and travel times are configured
- `assumed_state`: Always True (covers can be stopped mid-way)
- `supported_features`: OPEN + CLOSE + STOP + SET_POSITION, plus tilt features
  if tilt strategy is configured
- `extra_state_attributes`: Exposes timing config + calibration status

---

## 11. Services

### Entity Services (via entity platform)
- `set_known_position`: Set position without moving (0-100). Stops any active
  movement, snaps tilt trackers.
- `set_known_tilt_position`: Set tilt without moving (0-100).

### Domain Services
- `start_calibration`: Start calibration test (attribute, timeout, direction)
- `stop_calibration`: Stop calibration test (cancel flag), returns result

---

## 12. YAML Configuration (Deprecated)

YAML configuration is deprecated and shows a warning + repair issue. It supports:
- Per-device and defaults sections
- Legacy key migration (travelling_time_down → travel_time_close, etc.)
- Legacy is_button → pulse mode migration
- Legacy travel_moves_with_tilt → inline tilt mode migration
