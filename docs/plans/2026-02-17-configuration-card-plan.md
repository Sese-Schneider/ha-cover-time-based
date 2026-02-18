# Configuration Card Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a custom Lovelace card for configuring and calibrating cover_time_based entities, with WebSocket API backend.

**Architecture:** Zero-build LitElement card (vanilla ES6 from CDN), WebSocket API for config CRUD, existing HA services for calibration. Card registered via `__init__.py`.

**Tech Stack:** LitElement 2.4.0 (CDN), HA WebSocket API, voluptuous validation

---

### Task 1: Backend - WebSocket API module

Create the WebSocket API handlers for reading and writing cover configuration.

**Files:**
- Create: `custom_components/cover_time_based/websocket_api.py`

**Step 1: Create websocket_api.py**

```python
"""WebSocket API for cover_time_based configuration card."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .cover import (
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_COVER_ENTITY_ID,
    CONF_DEVICE_TYPE,
    CONF_INPUT_MODE,
    CONF_MIN_MOVEMENT_TIME,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_TILT_MOTOR_OVERHEAD,
    CONF_TILTING_TIME_DOWN,
    CONF_TILTING_TIME_UP,
    CONF_TRAVEL_MOTOR_OVERHEAD,
    CONF_TRAVEL_MOVES_WITH_TILT,
    CONF_TRAVELLING_TIME_DOWN,
    CONF_TRAVELLING_TIME_UP,
    DEFAULT_PULSE_TIME,
    DEFAULT_TRAVEL_TIME,
    DEVICE_TYPE_COVER,
    DEVICE_TYPE_SWITCH,
    INPUT_MODE_PULSE,
    INPUT_MODE_SWITCH,
    INPUT_MODE_TOGGLE,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "cover_time_based"


def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register WebSocket API commands."""
    websocket_api.async_register_command(hass, ws_get_config)
    websocket_api.async_register_command(hass, ws_update_config)


def _resolve_config_entry(hass: HomeAssistant, entity_id: str):
    """Resolve an entity_id to its config entry.

    Returns (config_entry, error_msg) tuple.
    """
    entity_reg = er.async_get(hass)
    entry = entity_reg.async_get(entity_id)
    if not entry or not entry.config_entry_id:
        return None, "Entity not found or not a config entry entity"

    config_entry = hass.config_entries.async_get_entry(entry.config_entry_id)
    if not config_entry or config_entry.domain != DOMAIN:
        return None, "Entity does not belong to cover_time_based"

    return config_entry, None


@websocket_api.websocket_command(
    {
        "type": "cover_time_based/get_config",
        vol.Required("entity_id"): str,
    }
)
@websocket_api.async_response
async def ws_get_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get_config WebSocket command."""
    config_entry, error = _resolve_config_entry(hass, msg["entity_id"])
    if error:
        connection.send_error(msg["id"], "not_found", error)
        return

    options = config_entry.options
    connection.send_result(
        msg["id"],
        {
            "entry_id": config_entry.entry_id,
            "device_type": options.get(CONF_DEVICE_TYPE, DEVICE_TYPE_SWITCH),
            "input_mode": options.get(CONF_INPUT_MODE, INPUT_MODE_SWITCH),
            "pulse_time": options.get(CONF_PULSE_TIME, DEFAULT_PULSE_TIME),
            "open_switch_entity_id": options.get(CONF_OPEN_SWITCH_ENTITY_ID),
            "close_switch_entity_id": options.get(CONF_CLOSE_SWITCH_ENTITY_ID),
            "stop_switch_entity_id": options.get(CONF_STOP_SWITCH_ENTITY_ID),
            "cover_entity_id": options.get(CONF_COVER_ENTITY_ID),
            "travel_moves_with_tilt": options.get(CONF_TRAVEL_MOVES_WITH_TILT, False),
            "travelling_time_down": options.get(CONF_TRAVELLING_TIME_DOWN, DEFAULT_TRAVEL_TIME),
            "travelling_time_up": options.get(CONF_TRAVELLING_TIME_UP, DEFAULT_TRAVEL_TIME),
            "tilting_time_down": options.get(CONF_TILTING_TIME_DOWN),
            "tilting_time_up": options.get(CONF_TILTING_TIME_UP),
            "travel_motor_overhead": options.get(CONF_TRAVEL_MOTOR_OVERHEAD),
            "tilt_motor_overhead": options.get(CONF_TILT_MOTOR_OVERHEAD),
            "min_movement_time": options.get(CONF_MIN_MOVEMENT_TIME),
        },
    )


@websocket_api.websocket_command(
    {
        "type": "cover_time_based/update_config",
        vol.Required("entity_id"): str,
        vol.Optional("device_type"): vol.In([DEVICE_TYPE_SWITCH, DEVICE_TYPE_COVER]),
        vol.Optional("input_mode"): vol.In(
            [INPUT_MODE_SWITCH, INPUT_MODE_PULSE, INPUT_MODE_TOGGLE]
        ),
        vol.Optional("pulse_time"): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=10)),
        vol.Optional("open_switch_entity_id"): vol.Any(str, None),
        vol.Optional("close_switch_entity_id"): vol.Any(str, None),
        vol.Optional("stop_switch_entity_id"): vol.Any(str, None),
        vol.Optional("cover_entity_id"): vol.Any(str, None),
        vol.Optional("travel_moves_with_tilt"): bool,
        vol.Optional("travelling_time_down"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("travelling_time_up"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("tilting_time_down"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("tilting_time_up"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("travel_motor_overhead"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("tilt_motor_overhead"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
        vol.Optional("min_movement_time"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=600))
        ),
    }
)
@websocket_api.async_response
async def ws_update_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle update_config WebSocket command."""
    config_entry, error = _resolve_config_entry(hass, msg["entity_id"])
    if error:
        connection.send_error(msg["id"], "not_found", error)
        return

    # Build new options from existing + updates
    new_options = dict(config_entry.options)

    # Map WS field names to config entry option keys
    field_map = {
        "device_type": CONF_DEVICE_TYPE,
        "input_mode": CONF_INPUT_MODE,
        "pulse_time": CONF_PULSE_TIME,
        "open_switch_entity_id": CONF_OPEN_SWITCH_ENTITY_ID,
        "close_switch_entity_id": CONF_CLOSE_SWITCH_ENTITY_ID,
        "stop_switch_entity_id": CONF_STOP_SWITCH_ENTITY_ID,
        "cover_entity_id": CONF_COVER_ENTITY_ID,
        "travel_moves_with_tilt": CONF_TRAVEL_MOVES_WITH_TILT,
        "travelling_time_down": CONF_TRAVELLING_TIME_DOWN,
        "travelling_time_up": CONF_TRAVELLING_TIME_UP,
        "tilting_time_down": CONF_TILTING_TIME_DOWN,
        "tilting_time_up": CONF_TILTING_TIME_UP,
        "travel_motor_overhead": CONF_TRAVEL_MOTOR_OVERHEAD,
        "tilt_motor_overhead": CONF_TILT_MOTOR_OVERHEAD,
        "min_movement_time": CONF_MIN_MOVEMENT_TIME,
    }

    # Skip keys that are WS metadata, not config fields
    skip_keys = {"id", "type", "entity_id"}

    for ws_key, conf_key in field_map.items():
        if ws_key in msg and ws_key not in skip_keys:
            value = msg[ws_key]
            if value is None:
                new_options.pop(conf_key, None)
            else:
                new_options[conf_key] = value

    hass.config_entries.async_update_entry(config_entry, options=new_options)

    connection.send_result(msg["id"], {"success": True})
```

**Step 2: Run tests to verify no import errors**

Run: `cd /workspaces/ha-cover-time-based-config-helpers && python -c "from custom_components.cover_time_based.websocket_api import async_register_websocket_api; print('OK')"`

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/websocket_api.py
git commit -m "feat: add WebSocket API for configuration card"
```

---

### Task 2: Backend - Update __init__.py and manifest.json

Register the frontend static path, card JS, and WebSocket API in the integration setup.

**Files:**
- Modify: `custom_components/cover_time_based/__init__.py`
- Modify: `custom_components/cover_time_based/manifest.json`

**Step 1: Update manifest.json**

Add `"dependencies": ["http"]` (needed for static path registration). Keep keys sorted per CLAUDE.md rules (domain, name first, then alphabetical):

```json
{
  "domain": "cover_time_based",
  "name": "Cover Time Based",
  "codeowners": ["@Sese-Schneider"],
  "config_flow": true,
  "dependencies": ["http"],
  "documentation": "https://github.com/Sese-Schneider/ha-cover-time-based",
  "integration_type": "helper",
  "iot_class": "calculated",
  "issue_tracker": "https://github.com/Sese-Schneider/ha-cover-time-based/issues",
  "requirements": [
    "xknx==3.11.0"
  ],
  "version": "3.0.0"
}
```

**Step 2: Update __init__.py**

```python
"""Cover Time Based integration."""

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .websocket_api import async_register_websocket_api

DOMAIN = "cover_time_based"
PLATFORMS: list[Platform] = [Platform.COVER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cover Time Based from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # Register WebSocket API (idempotent - safe to call multiple times)
    async_register_websocket_api(hass)

    # Register frontend
    if hass.http is not None:
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    "/cover_time_based_panel",
                    str(Path(__file__).parent / "frontend"),
                    cache_headers=False,
                )
            ]
        )

        hass.data.setdefault(frontend.DATA_EXTRA_MODULE_URL, set())
        frontend.add_extra_js_url(
            hass, "/cover_time_based_panel/cover-time-based-card.js"
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update - reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)
```

**Step 3: Run existing tests**

Run: `cd /workspaces/ha-cover-time-based-config-helpers && python -m pytest tests/ -x -q`
Expected: All 149 tests pass

**Step 4: Commit**

```bash
git add custom_components/cover_time_based/__init__.py custom_components/cover_time_based/manifest.json
git commit -m "feat: register frontend and WebSocket API in init"
```

---

### Task 3: Frontend - Card skeleton with entity picker

Create the card JS file with LitElement, entity picker, and card registration.

**Files:**
- Create: `custom_components/cover_time_based/frontend/cover-time-based-card.js`

**Step 1: Create the card file**

The card should:
- Import LitElement from CDN
- Register as `cover-time-based-card` custom element
- Have a `setConfig(config)` method (required by Lovelace)
- Accept `hass` property (set by HA when state changes)
- Show an entity picker filtered to `cover` domain entities that belong to `cover_time_based`
- When entity is selected, call `cover_time_based/get_config` via WS
- Display the entity name and entity ID

Entity filtering: use `hass.states` to find entities whose `entity_id` starts with `cover.` and check if they have `travelling_time_down` in their attributes (a marker for cover_time_based entities). Alternatively, filter by checking if the entity has the expected state attributes.

The card renders:
1. Header: "Cover Time Based Configuration"
2. Entity dropdown: `<select>` populated from `hass.states` filtered to cover_time_based entities
3. When selected: show name and entity ID

Use the same CDN pattern as fado:
```javascript
import { LitElement, html, css } from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";
```

**Step 2: Test manually**

Deploy to HA:
```bash
rm -Rf /workspaces/homeassistant-core/config/custom_components/cover_time_based && cp -r /workspaces/ha-cover-time-based-config-helpers/custom_components/cover_time_based /workspaces/homeassistant-core/config/custom_components/
```

Restart HA, add card to dashboard using YAML:
```yaml
type: custom:cover-time-based-card
```

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: card skeleton with entity picker"
```

---

### Task 4: Frontend - Device type and input entity sections

Add the device type selector and input entity configuration to the card.

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js`

**Step 1: Add device type section**

After entity picker, show:
- Radio buttons or `<select>` for device type: "Control via switches" / "Wrap an existing cover entity"
- On change, call `cover_time_based/update_config` with `device_type`

**Step 2: Add input entity section**

Based on device type:
- If `switch`: show 3 entity pickers (open, close, stop) using `<select>` from `hass.states` filtered to `switch.*`
- If `cover`: show 1 entity picker filtered to `cover.*`
- On change, save via WS

**Step 3: Add input mode section**

Show radio/select for input mode (switch/pulse/toggle).
If pulse or toggle, show pulse time number input.
On change, save via WS.

**Step 4: Deploy and test**

```bash
rm -Rf /workspaces/homeassistant-core/config/custom_components/cover_time_based && cp -r /workspaces/ha-cover-time-based-config-helpers/custom_components/cover_time_based /workspaces/homeassistant-core/config/custom_components/
```

**Step 5: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: device type, input entities, and input mode sections"
```

---

### Task 5: Frontend - Tilt support and timing table

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js`

**Step 1: Add tilt support toggle**

- Toggle for "Cover supports tilting?" (renders tilt time fields when yes)
- If yes, radio for tilt behavior:
  - "Before opening and after closing" (`travel_moves_with_tilt: false`)
  - "During opening/closing" (`travel_moves_with_tilt: true`)
- On change, save via WS

**Step 2: Add timing attributes table**

Read-only table showing current values from `hass.states[entityId].attributes`:
- Travel time (close): `travelling_time_down`
- Travel time (open): `travelling_time_up`
- Travel motor overhead: `travel_motor_overhead`
- (If tilt enabled) Tilt time (close): `tilting_time_down`
- (If tilt enabled) Tilt time (open): `tilting_time_up`
- (If tilt enabled) Tilt motor overhead: `tilt_motor_overhead`
- Minimum movement time: `min_movement_time`

Format: `<table>` with Attribute | Value columns. Values in seconds, show "Not set" for null.

**Step 3: Deploy and test**

**Step 4: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: tilt support section and timing attributes table"
```

---

### Task 6: Frontend - Calibration controls

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js`

**Step 1: Add calibration form**

Below the timing table:
- Attribute dropdown (same options as start_calibration service)
- Direction dropdown (Open/Close, optional)
- Timeout number input (default 120)
- "Go" button

On Go click:
```javascript
await this.hass.callService("cover_time_based", "start_calibration", {
  entity_id: this._selectedEntity,
  attribute: this._calibrationAttribute,
  timeout: this._calibrationTimeout,
  direction: this._calibrationDirection || undefined,
});
```

**Step 2: Add active calibration display**

When entity state has `calibration_active: true`:
- Show "Calibrating: {attribute}" with step count
- Replace Go with Stop and Cancel buttons
- Disable config sections above

Stop button:
```javascript
await this.hass.callService("cover_time_based", "stop_calibration", {
  entity_id: this._selectedEntity,
});
```

Cancel button:
```javascript
await this.hass.callService("cover_time_based", "stop_calibration", {
  entity_id: this._selectedEntity,
  cancel: true,
});
```

**Step 3: Deploy and test end-to-end**

Test:
1. Select entity
2. Start calibration
3. Verify status updates in card
4. Stop calibration
5. Verify value appears in table

**Step 4: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: calibration controls with live status"
```

---

### Task 7: Styling and polish

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js`

**Step 1: Apply HA theme styling**

- Use `ha-card` wrapper for proper card appearance
- Use HA CSS variables: `--primary-color`, `--primary-text-color`, `--divider-color`, etc.
- Style sections with proper spacing, borders, labels
- Style the table to match HA's look
- Style buttons (Go = primary color, Cancel = secondary/warning)

**Step 2: Add loading states**

- Show spinner/loading indicator while fetching config
- Disable inputs while saving

**Step 3: Deploy and visual review**

**Step 4: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: card styling and polish"
```

---

### Task 8: Tests for WebSocket API

**Files:**
- Create: `tests/test_websocket_api.py`

**Step 1: Write tests for ws_get_config**

Test:
- Returns config entry options for valid entity
- Returns error for unknown entity
- Returns error for non-cover_time_based entity

**Step 2: Write tests for ws_update_config**

Test:
- Updates single field (e.g. device_type)
- Updates multiple fields
- Setting value to None removes it from options
- Returns error for unknown entity
- Validates input (e.g. invalid device_type rejected by voluptuous)

**Step 3: Run tests**

Run: `cd /workspaces/ha-cover-time-based-config-helpers && python -m pytest tests/test_websocket_api.py -v`

**Step 4: Commit**

```bash
git add tests/test_websocket_api.py
git commit -m "test: WebSocket API tests for get_config and update_config"
```

---

### Task 9: Final integration test and deploy

**Step 1: Run all tests**

Run: `cd /workspaces/ha-cover-time-based-config-helpers && python -m pytest tests/ -v`
Expected: All tests pass

**Step 2: Lint and type check**

Run: `cd /workspaces/ha-cover-time-based-config-helpers && ruff check . && ruff format .`
Run: `cd /workspaces/ha-cover-time-based-config-helpers && npx pyright`

**Step 3: Deploy and full manual test**

```bash
rm -Rf /workspaces/homeassistant-core/config/custom_components/cover_time_based && cp -r /workspaces/ha-cover-time-based-config-helpers/custom_components/cover_time_based /workspaces/homeassistant-core/config/custom_components/
```

Manual test checklist:
- [ ] Card loads in dashboard
- [ ] Entity picker shows cover_time_based entities
- [ ] Selecting entity loads config
- [ ] Device type change saves and reloads entity
- [ ] Input entity pickers work
- [ ] Input mode change works
- [ ] Tilt toggle shows/hides tilt fields
- [ ] Timing table shows current values
- [ ] Calibration start/stop/cancel work
- [ ] Calibration status updates in real-time

**Step 4: Commit any fixes**
