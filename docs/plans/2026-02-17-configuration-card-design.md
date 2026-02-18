# Configuration Card Design

## Goal

Replace most of the multi-step config flow with a single Lovelace dashboard card that handles both initial configuration and calibration of cover_time_based entities.

## Architecture

A zero-build custom Lovelace card using LitElement (from CDN), following the same patterns as the ha-fado card. The card communicates with the backend via WebSocket API for reading/writing configuration, and via HA service calls for calibration. The config flow is stripped down to just collecting the entity name - all other configuration happens through the card.

## Tech Stack

- **Frontend**: Vanilla ES6 module with LitElement 2.4.0 from unpkg CDN
- **Backend**: HA WebSocket API handlers for config read/write
- **Communication**: `hass.callWS()` for config, `hass.callService()` for calibration
- **State updates**: Entity state subscription for calibration status

---

## Card Design

### Entity Selection

At the top of the card, an entity picker filtered to `cover.cover_time_based_*` entities. Once selected, the card displays:
- **Name** and **Entity ID**

### Configuration Sections

The card shows configuration in a progressive flow. Each section is shown based on the current state of configuration.

#### 1. Device Type
Radio/select:
- **Control via switches** (`switch`)
- **Wrap an existing cover entity** (`cover`)

#### 2. Input Entities (shown after device type is selected)

If **switches**:
- Open switch entity (entity picker, filtered to `switch` domain)
- Close switch entity (entity picker, filtered to `switch` domain)
- Stop switch entity (optional, entity picker, filtered to `switch` domain)

If **cover**:
- Cover entity (entity picker, filtered to `cover` domain)

#### 3. Input Mode
Radio/select:
- **Switch** - Latching relays (on/off stay in position)
- **Pulse** - Momentary press, separate stop
- **Toggle** - Same button starts and stops

If pulse or toggle, show:
- Pulse time (number input, seconds)

#### 4. Tilt Support
Toggle: **Cover supports tilting?** Yes/No

If yes:
- **Tilting happens:**
  - Before opening and after closing (`travel_moves_with_tilt: false`)
  - During opening/closing (`travel_moves_with_tilt: true`)

#### 5. Timing Attributes Table (read-only)

A table showing the relevant timing attributes and their current values. Which rows are shown depends on the configuration:

| Attribute | Shown when | Value source |
|-----------|-----------|--------------|
| Travel time (close) | Always | `travelling_time_down` |
| Travel time (open) | Always | `travelling_time_up` |
| Travel motor overhead | Always | `travel_motor_overhead` |
| Tilt time (close) | Tilt enabled | `tilting_time_down` |
| Tilt time (open) | Tilt enabled | `tilting_time_up` |
| Tilt motor overhead | Tilt enabled | `tilt_motor_overhead` |
| Minimum movement time | Always | `min_movement_time` |

Values come from `extra_state_attributes` on the selected entity.

#### 6. Calibration Controls

Below the table:
- **Attribute** dropdown (same options as start_calibration service)
- **Direction** dropdown (Open/Close, optional)
- **Timeout** number input (default 120s)
- **Go** button

When calibration is active (detected via `calibration_active` state attribute):
- Replace Go with **Stop** and **Cancel** buttons
- Show the active attribute and step count
- Disable the configuration sections above (prevent changes during calibration)

### Save Behavior

Each configuration section saves independently when the user changes a value (like the fado card pattern - save on change, not a single "Save All" button). The backend validates and applies immediately.

After saving, the entity reloads (existing `async_update_options` listener handles this).

---

## Backend Design

### WebSocket API

Two new WebSocket commands in a new `websocket_api.py` module:

#### `cover_time_based/get_config`

**Input:** `{ type: "cover_time_based/get_config", entity_id: "cover.xxx" }`

**Response:** Returns the config entry options for the entity:
```json
{
  "entry_id": "abc123",
  "device_type": "switch",
  "input_mode": "switch",
  "pulse_time": 1.0,
  "open_switch_entity_id": "switch.open",
  "close_switch_entity_id": "switch.close",
  "stop_switch_entity_id": "switch.stop",
  "cover_entity_id": null,
  "travel_moves_with_tilt": false,
  "travelling_time_down": 30,
  "travelling_time_up": 30,
  "tilting_time_down": null,
  "tilting_time_up": null,
  "travel_motor_overhead": null,
  "tilt_motor_overhead": null,
  "min_movement_time": null
}
```

Resolves entity_id → config entry via the entity registry.

#### `cover_time_based/update_config`

**Input:** Partial update - only send fields that changed:
```json
{
  "type": "cover_time_based/update_config",
  "entity_id": "cover.xxx",
  "device_type": "switch",
  "input_mode": "pulse",
  "pulse_time": 0.5
}
```

**Validation:**
- Same rules as the current config flow (tilt times must be paired, etc.)
- Entity must belong to cover_time_based integration

**Effect:**
- Updates config entry options
- Triggers entity reload via existing `async_update_options` listener

### Frontend Registration

In `__init__.py`:
- Register static path `/cover_time_based_panel` pointing to `frontend/` directory
- Register card JS via `frontend.add_extra_js_url()`
- Register WebSocket API handlers

### File Structure

```
custom_components/cover_time_based/
├── frontend/
│   └── cover-time-based-card.js    # The card (single file)
├── websocket_api.py                 # WS handlers
├── __init__.py                      # Updated: static path + WS registration
└── ... (existing files)
```

---

## What Changes in Existing Code

### Config Flow
- **Keep as-is for now.** The config flow still works for creating entities. We can simplify it later (strip to name-only) once the card is proven.
- The card provides an alternative way to configure, but doesn't replace the config flow yet.

### __init__.py
- Add frontend static path registration
- Add WebSocket API registration
- Add `"http"` to `dependencies` in manifest.json

### manifest.json
- Add `"dependencies": ["http"]`

### No changes to:
- cover_base.py (calibration logic stays)
- cover.py (services stay)
- calibration.py (constants stay)
