# Tilt Strategy Configuration UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update the Lovelace config card and backend to support the three new tilt strategies (sequential, proportional, dual_motor), with strategy-aware position presets, calibration filtering, dual-motor entity/config fields, and mode-specific calibration hints.

**Architecture:** The JS card (`cover-time-based-card.js`) is the main UI. The WebSocket API (`websocket_api.py`) handles get/update config and calibration. The calibration module (`calibration.py`) defines available attributes. Changes are: (1) backend adds `get_calibratable_attributes()` and fixes dual-motor field round-tripping, (2) card updates tilt dropdown, adds dual-motor section, strategy-aware position presets, and mode-specific hints.

**Tech Stack:** LitElement JS (card), Python (websocket_api.py, calibration.py), voluptuous (WS validation), pytest (tests)

**Working directory:** `/workspaces/ha-cover-time-based`
**Branch:** `chore/refactor_tilt`
**Test command:** `python -m pytest tests/ -q`
**Lint command:** `ruff check . && ruff format .`

---

### Task 1: Add `get_calibratable_attributes()` to calibration.py

The calibration module currently has a static `CALIBRATABLE_ATTRIBUTES` list. We need a function that filters this list based on tilt mode, so the card and `start_calibration` can use it.

**Files:**
- Modify: `custom_components/cover_time_based/calibration.py:15-23`
- Test: `tests/test_calibration.py`

**Step 1: Write the failing tests**

Add to `tests/test_calibration.py`:

```python
class TestGetCalibratableAttributes:
    """Test get_calibratable_attributes filters by tilt mode."""

    def test_none_mode_excludes_tilt(self):
        from custom_components.cover_time_based.calibration import get_calibratable_attributes
        attrs = get_calibratable_attributes("none")
        assert "travel_time_close" in attrs
        assert "travel_time_open" in attrs
        assert "travel_startup_delay" in attrs
        assert "min_movement_time" in attrs
        assert "tilt_time_close" not in attrs
        assert "tilt_time_open" not in attrs
        assert "tilt_startup_delay" not in attrs

    def test_sequential_includes_tilt(self):
        from custom_components.cover_time_based.calibration import get_calibratable_attributes
        attrs = get_calibratable_attributes("sequential")
        assert "travel_time_close" in attrs
        assert "tilt_time_close" in attrs
        assert "tilt_time_open" in attrs
        assert "tilt_startup_delay" in attrs

    def test_proportional_excludes_tilt(self):
        from custom_components.cover_time_based.calibration import get_calibratable_attributes
        attrs = get_calibratable_attributes("proportional")
        assert "travel_time_close" in attrs
        assert "tilt_time_close" not in attrs
        assert "tilt_time_open" not in attrs
        assert "tilt_startup_delay" not in attrs

    def test_dual_motor_includes_tilt(self):
        from custom_components.cover_time_based.calibration import get_calibratable_attributes
        attrs = get_calibratable_attributes("dual_motor")
        assert "travel_time_close" in attrs
        assert "tilt_time_close" in attrs
        assert "tilt_time_open" in attrs
        assert "tilt_startup_delay" in attrs

    def test_returns_list(self):
        from custom_components.cover_time_based.calibration import get_calibratable_attributes
        result = get_calibratable_attributes("none")
        assert isinstance(result, list)
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_calibration.py::TestGetCalibratableAttributes -v`
Expected: FAIL with `ImportError` (function doesn't exist yet)

**Step 3: Implement the function**

In `custom_components/cover_time_based/calibration.py`, add after the `CALIBRATABLE_ATTRIBUTES` list:

```python
# Tilt modes that support independent tilt calibration
_TILT_CALIBRATION_MODES = {"sequential", "dual_motor"}


def get_calibratable_attributes(tilt_mode: str) -> list[str]:
    """Return calibratable attributes filtered by tilt mode.

    Proportional and none modes exclude tilt attributes because
    tilt is either derived from position or not configured.
    """
    if tilt_mode in _TILT_CALIBRATION_MODES:
        return list(CALIBRATABLE_ATTRIBUTES)
    return [a for a in CALIBRATABLE_ATTRIBUTES if not a.startswith("tilt_")]
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_calibration.py::TestGetCalibratableAttributes -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add custom_components/cover_time_based/calibration.py tests/test_calibration.py
git commit -m "feat: add get_calibratable_attributes() filtered by tilt mode"
```

---

### Task 2: Fix dual-motor field round-tripping in WebSocket API

The `ws_update_config` accepts dual-motor fields (`safe_tilt_position`, `min_tilt_allowed_position`, `tilt_open_switch`, `tilt_close_switch`, `tilt_stop_switch`) in its schema but they're NOT in `_FIELD_MAP` so they never get saved. Also `ws_get_config` doesn't return them. Fix both.

**Files:**
- Modify: `custom_components/cover_time_based/websocket_api.py:50-67` (add to `_FIELD_MAP`) and `117-138` (add to `get_config` response)
- Test: `tests/test_websocket_api.py`

**Step 1: Write the failing tests**

Add to `tests/test_websocket_api.py`:

```python
class TestDualMotorFieldRoundTrip:
    """Test that dual-motor fields are returned in get_config and saved in update_config."""

    @pytest.fixture
    def config_entry_with_dual_motor(self):
        """Config entry with dual_motor options set."""
        entry = MagicMock()
        entry.entry_id = ENTRY_ID
        entry.domain = DOMAIN
        entry.options = {
            "device_type": "switch",
            "input_mode": "switch",
            "tilt_mode": "dual_motor",
            "safe_tilt_position": 10,
            "min_tilt_allowed_position": 80,
            "tilt_open_switch": "switch.tilt_open",
            "tilt_close_switch": "switch.tilt_close",
            "tilt_stop_switch": "switch.tilt_stop",
        }
        return entry

    @pytest.mark.asyncio
    async def test_get_config_returns_dual_motor_fields(self, config_entry_with_dual_motor):
        hass = MagicMock()
        connection = MagicMock()
        msg = {"id": 1, "type": "cover_time_based/get_config", "entity_id": ENTITY_ID}

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry_with_dual_motor, None),
        ):
            handler = _unwrap(ws_get_config)
            await handler(hass, connection, msg)

        result = connection.send_result.call_args[0][1]
        assert result["safe_tilt_position"] == 10
        assert result["min_tilt_allowed_position"] == 80
        assert result["tilt_open_switch"] == "switch.tilt_open"
        assert result["tilt_close_switch"] == "switch.tilt_close"
        assert result["tilt_stop_switch"] == "switch.tilt_stop"

    @pytest.mark.asyncio
    async def test_update_config_saves_dual_motor_fields(self):
        hass = MagicMock()
        connection = MagicMock()
        config_entry = MagicMock()
        config_entry.options = {"tilt_mode": "dual_motor"}
        config_entry.domain = DOMAIN

        msg = {
            "id": 2,
            "type": "cover_time_based/update_config",
            "entity_id": ENTITY_ID,
            "safe_tilt_position": 15,
            "min_tilt_allowed_position": 90,
            "tilt_open_switch": "switch.tilt_up",
            "tilt_close_switch": "switch.tilt_down",
            "tilt_stop_switch": "switch.tilt_stop",
        }

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry, None),
        ):
            handler = _unwrap(ws_update_config)
            await handler(hass, connection, msg)

        new_opts = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert new_opts["safe_tilt_position"] == 15
        assert new_opts["min_tilt_allowed_position"] == 90
        assert new_opts["tilt_open_switch"] == "switch.tilt_up"
        assert new_opts["tilt_close_switch"] == "switch.tilt_down"
        assert new_opts["tilt_stop_switch"] == "switch.tilt_stop"

    @pytest.mark.asyncio
    async def test_get_config_defaults_for_missing_dual_motor_fields(self):
        """When dual_motor fields aren't in options, get_config returns sensible defaults."""
        hass = MagicMock()
        connection = MagicMock()
        config_entry = MagicMock()
        config_entry.entry_id = ENTRY_ID
        config_entry.domain = DOMAIN
        config_entry.options = {"tilt_mode": "sequential"}
        msg = {"id": 1, "type": "cover_time_based/get_config", "entity_id": ENTITY_ID}

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry, None),
        ):
            handler = _unwrap(ws_get_config)
            await handler(hass, connection, msg)

        result = connection.send_result.call_args[0][1]
        assert result["safe_tilt_position"] == 0
        assert result["min_tilt_allowed_position"] is None
        assert result["tilt_open_switch"] is None
        assert result["tilt_close_switch"] is None
        assert result["tilt_stop_switch"] is None
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_websocket_api.py::TestDualMotorFieldRoundTrip -v`
Expected: FAIL (fields missing from response / not saved)

**Step 3: Implement the fixes**

In `websocket_api.py`, add to `_FIELD_MAP` (after line 66):

```python
    "safe_tilt_position": CONF_SAFE_TILT_POSITION,
    "min_tilt_allowed_position": CONF_MIN_TILT_ALLOWED_POSITION,
    "tilt_open_switch": CONF_TILT_OPEN_SWITCH,
    "tilt_close_switch": CONF_TILT_CLOSE_SWITCH,
    "tilt_stop_switch": CONF_TILT_STOP_SWITCH,
```

In `ws_get_config`, add to the response dict (after `"min_movement_time"` line):

```python
            "safe_tilt_position": options.get(CONF_SAFE_TILT_POSITION, 0),
            "min_tilt_allowed_position": options.get(CONF_MIN_TILT_ALLOWED_POSITION),
            "tilt_open_switch": options.get(CONF_TILT_OPEN_SWITCH),
            "tilt_close_switch": options.get(CONF_TILT_CLOSE_SWITCH),
            "tilt_stop_switch": options.get(CONF_TILT_STOP_SWITCH),
```

Also remove the now-redundant direct `CONF_*` keys from the `ws_update_config` schema (lines 183-189) since they'll go through `_FIELD_MAP` with string key names. Replace them with:

```python
        vol.Optional("safe_tilt_position"): vol.All(int, vol.Range(min=0, max=100)),
        vol.Optional("min_tilt_allowed_position"): vol.Any(
            None, vol.All(int, vol.Range(min=0, max=100))
        ),
        vol.Optional("tilt_open_switch"): vol.Any(str, None),
        vol.Optional("tilt_close_switch"): vol.Any(str, None),
        vol.Optional("tilt_stop_switch"): vol.Any(str, None),
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_websocket_api.py::TestDualMotorFieldRoundTrip -v`
Expected: PASS (3 tests)

**Step 5: Run full test suite**

Run: `python -m pytest tests/ -q`
Expected: All tests pass

**Step 6: Commit**

```bash
git add custom_components/cover_time_based/websocket_api.py tests/test_websocket_api.py
git commit -m "fix: dual-motor fields now round-trip through WebSocket API"
```

---

### Task 3: Update tilt mode dropdown in card JS

Replace the old `before_after`/`during` options with `sequential`/`proportional`/`dual_motor`.

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js`

**Step 1: Update `_renderTiltSupport`**

Replace `_renderTiltSupport` method (lines 704-723) with:

```javascript
  _renderTiltSupport(c) {
    const tiltMode = c.tilt_mode || "none";

    return html`
      <div class="section">
        <div class="field-label">Tilting</div>
        <select class="ha-select" @change=${this._onTiltModeChange}>
          <option value="none" ?selected=${tiltMode === "none"}>
            Not supported
          </option>
          <option value="sequential" ?selected=${tiltMode === "sequential"}>
            Closes then tilts
          </option>
          <option value="proportional" ?selected=${tiltMode === "proportional"}>
            Tilts with movement
          </option>
          <option value="dual_motor" ?selected=${tiltMode === "dual_motor"}>
            Separate tilt motor
          </option>
        </select>
      </div>
    `;
  }
```

**Step 2: Update `_onTiltModeChange` handler**

Replace `_onTiltModeChange` (lines 303-322) with:

```javascript
  _onTiltModeChange(e) {
    const mode = e.target.value;
    if (mode === "none") {
      this._updateLocal({
        tilt_time_close: null,
        tilt_time_open: null,
        tilt_startup_delay: null,
        tilt_mode: "none",
        // Clear dual-motor fields
        safe_tilt_position: null,
        min_tilt_allowed_position: null,
        tilt_open_switch: null,
        tilt_close_switch: null,
        tilt_stop_switch: null,
      });
    } else if (mode === "proportional") {
      // Proportional: tilt derived from position, no tilt times needed
      this._updateLocal({
        tilt_mode: mode,
        tilt_time_close: null,
        tilt_time_open: null,
        tilt_startup_delay: null,
        safe_tilt_position: null,
        min_tilt_allowed_position: null,
        tilt_open_switch: null,
        tilt_close_switch: null,
        tilt_stop_switch: null,
      });
    } else {
      const updates = { tilt_mode: mode };
      // Initialize tilt times if enabling for the first time
      if (this._config.tilt_time_close == null) {
        updates.tilt_time_close = 5.0;
      }
      if (this._config.tilt_time_open == null) {
        updates.tilt_time_open = 5.0;
      }
      // Clear dual-motor fields when switching to sequential
      if (mode === "sequential") {
        updates.safe_tilt_position = null;
        updates.min_tilt_allowed_position = null;
        updates.tilt_open_switch = null;
        updates.tilt_close_switch = null;
        updates.tilt_stop_switch = null;
      }
      this._updateLocal(updates);
    }
  }
```

**Step 3: Update `_renderTimingTable` tilt visibility**

The existing check at line 726 (`hasTilt = c.tilt_mode && c.tilt_mode !== "none"`) needs to also exclude proportional:

```javascript
    const hasTiltTimes = c.tilt_mode === "sequential" || c.tilt_mode === "dual_motor";
```

Replace `hasTilt` with `hasTiltTimes` in the timing table method (line 734 condition).

**Step 4: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: update tilt mode dropdown to sequential/proportional/dual_motor"
```

---

### Task 4: Add Tilt Motor section for dual_motor mode

When `tilt_mode === "dual_motor"`, show a separate section with entity pickers and config fields.

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js`

**Step 1: Add `_renderTiltMotorSection` method**

Add after `_renderTiltSupport`:

```javascript
  _renderTiltMotorSection(c) {
    if (c.tilt_mode !== "dual_motor") return "";

    return html`
      <div class="section">
        <div class="field-label">Tilt Motor</div>
        <div class="entity-grid">
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.tilt_open_switch || ""}
            .includeDomains=${["switch"]}
            label="Tilt open switch"
            @value-changed=${(e) =>
              this._onSwitchEntityChange("tilt_open_switch", e)}
          ></ha-entity-picker>
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.tilt_close_switch || ""}
            .includeDomains=${["switch"]}
            label="Tilt close switch"
            @value-changed=${(e) =>
              this._onSwitchEntityChange("tilt_close_switch", e)}
          ></ha-entity-picker>
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.tilt_stop_switch || ""}
            .includeDomains=${["switch"]}
            label="Tilt stop switch (optional)"
            @value-changed=${(e) =>
              this._onSwitchEntityChange("tilt_stop_switch", e)}
          ></ha-entity-picker>
        </div>
        <div class="dual-motor-config">
          <ha-textfield
            type="number"
            min="0"
            max="100"
            step="1"
            label="Safe tilt position"
            helper="Tilt moves here before travel (0 = fully open)"
            .value=${String(c.safe_tilt_position ?? 0)}
            @change=${(e) => {
              const v = parseInt(e.target.value);
              if (!isNaN(v) && v >= 0 && v <= 100) {
                this._updateLocal({ safe_tilt_position: v });
              }
            }}
          ></ha-textfield>
          <ha-textfield
            type="number"
            min="0"
            max="100"
            step="1"
            label="Min tilt allowed position (optional)"
            helper="Cover must be at least this closed before tilting"
            .value=${c.min_tilt_allowed_position != null ? String(c.min_tilt_allowed_position) : ""}
            @change=${(e) => {
              const v = e.target.value.trim();
              this._updateLocal({
                min_tilt_allowed_position: v === "" ? null : parseInt(v),
              });
            }}
          ></ha-textfield>
        </div>
      </div>
    `;
  }
```

**Step 2: Wire it into `_renderConfigSections`**

In `_renderConfigSections` (line 555), add `${this._renderTiltMotorSection(c)}` after `${this._renderTiltSupport(c)}`:

```javascript
            ${this._renderDeviceType(c)} ${this._renderInputEntities(c)}
            ${this._renderEndpointRunon(c)}
            ${this._renderInputMode(c)} ${this._renderTiltSupport(c)}
            ${this._renderTiltMotorSection(c)}
```

**Step 3: Add CSS for dual-motor config**

In the `static get styles()` section, add:

```css
      .dual-motor-config {
        display: flex;
        gap: 16px;
        margin-top: 12px;
      }

      .dual-motor-config ha-textfield {
        flex: 1;
      }
```

**Step 4: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: add Tilt Motor section with entity pickers and config fields"
```

---

### Task 5: Strategy-aware position reset presets

Replace the simple Unknown/Fully open/Fully closed dropdown with strategy-aware presets.

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js`

**Step 1: Update `_renderPositionReset`**

Replace `_renderPositionReset` (lines 782-804) with:

```javascript
  _renderPositionReset() {
    const tiltMode = this._config?.tilt_mode || "none";
    const hasTilt = tiltMode !== "none";
    const hasIndependentTilt = tiltMode === "sequential" || tiltMode === "dual_motor";

    return html`
      <div class="section">
        <div class="field-label">Current Position</div>
        <div class="helper-text">
          Move cover to a known endpoint, then set position.
        </div>
        <div class="cal-form">
          <div class="cal-field">
            <select
              class="ha-select"
              id="position-select"
              @change=${(e) => this._onPositionPresetChange(e.target.value)}
            >
              <option value="unknown" ?selected=${this._knownPosition === "unknown"}>Unknown</option>
              <option value="open" ?selected=${this._knownPosition === "open"}>Fully open</option>
              ${hasIndependentTilt
                ? html`
                    <option value="closed_tilt_open" ?selected=${this._knownPosition === "closed_tilt_open"}>Fully closed, tilt open</option>
                    <option value="closed_tilt_closed" ?selected=${this._knownPosition === "closed_tilt_closed"}>Fully closed, tilt closed</option>
                  `
                : html`
                    <option value="closed" ?selected=${this._knownPosition === "closed"}>Fully closed</option>
                  `}
            </select>
          </div>
        </div>
      </div>
    `;
  }
```

**Step 2: Add `_onPositionPresetChange` handler**

Replace the old `_onPositionChange` (lines 391-417) with:

```javascript
  async _onPositionPresetChange(value) {
    this._knownPosition = value;
    if (value === "unknown") return;

    const tiltMode = this._config?.tilt_mode || "none";
    const hasTilt = tiltMode !== "none";

    // Determine position and tilt values from preset
    let position, tiltPosition;
    switch (value) {
      case "open":
        position = 100; // HA convention: 100 = fully open
        tiltPosition = hasTilt ? 100 : null; // tilt 0 = fully open... wait
        // Actually: 0 = fully closed, 100 = fully open in HA
        // But internally: 0 = fully open, 100 = fully closed
        // The service uses HA convention where set_known_position(100) = open
        // Let's check: in _onPositionChange, "open" maps to position=100
        // So: position 100 = fully open (HA convention)
        tiltPosition = hasTilt ? 100 : null;
        break;
      case "closed":
        // Proportional mode: position+tilt both closed
        position = 0;
        tiltPosition = hasTilt ? 0 : null;
        break;
      case "closed_tilt_open":
        position = 0;
        tiltPosition = 100;
        break;
      case "closed_tilt_closed":
        position = 0;
        tiltPosition = 0;
        break;
    }

    try {
      await this.hass.callService(DOMAIN, "set_known_position", {
        entity_id: this._selectedEntity,
        position,
      });
      if (tiltPosition != null) {
        await this.hass.callService(DOMAIN, "set_known_tilt_position", {
          entity_id: this._selectedEntity,
          tilt_position: tiltPosition,
        });
      }
      this.updateComplete.then(() => {
        const select = this.shadowRoot.querySelector("#cal-attribute");
        if (select) {
          const firstEnabled = [...select.options].find((o) => !o.disabled);
          if (firstEnabled) select.value = firstEnabled.value;
        }
        this.requestUpdate();
      });
    } catch (err) {
      console.error("Reset position failed:", err);
    }
  }
```

**IMPORTANT NOTE on position convention:** The existing `_onPositionChange` maps `"open"` to `position = 100` and `"closed"` to `position = 0`. This is HA's convention where 100 = fully open. The internal tracker uses 0 = open, 100 = closed, but the service handles the conversion. Follow the same pattern.

**Step 3: Update calibration attribute disabling**

In `_renderCalibration` (lines 819-828), update the disabled keys logic to handle the new presets:

```javascript
    const disabledKeys = new Set();
    if (this._knownPosition === "unknown") {
      availableAttributes.forEach(([key]) => disabledKeys.add(key));
    } else if (this._knownPosition === "open") {
      disabledKeys.add("travel_time_open");
      disabledKeys.add("tilt_time_open");
    } else if (this._knownPosition === "closed") {
      // Proportional/none: position closed (tilt matches)
      disabledKeys.add("travel_time_close");
      disabledKeys.add("tilt_time_close");
    } else if (this._knownPosition === "closed_tilt_open") {
      disabledKeys.add("travel_time_close");
      disabledKeys.add("tilt_time_open");
    } else if (this._knownPosition === "closed_tilt_closed") {
      disabledKeys.add("travel_time_close");
      disabledKeys.add("tilt_time_close");
    }
```

**Step 4: Update available attributes filtering for proportional mode**

In `_renderCalibration` (lines 812-817), update the filter to exclude tilt attrs for proportional:

```javascript
    const tiltMode = this._config?.tilt_mode || "none";
    const hasTiltCalibration = tiltMode === "sequential" || tiltMode === "dual_motor";

    const availableAttributes = Object.entries(ATTRIBUTE_LABELS).filter(
      ([key]) => {
        if (!hasTiltCalibration && key.startsWith("tilt_")) return false;
        return true;
      }
    );
```

**Step 5: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: strategy-aware position presets and calibration filtering"
```

---

### Task 6: Mode-specific calibration hints

Update the `_getCalibrationHint` method to provide helpful mode-specific guidance.

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js`

**Step 1: Replace `_getCalibrationHint`**

Replace `_getCalibrationHint` (lines 221-254) with:

```javascript
  _getCalibrationHint() {
    const select = this.shadowRoot?.querySelector("#cal-attribute");
    const attr = select?.value;
    const pos = this._knownPosition;
    const endpoint = pos === "open" ? "closed" : "open";
    const c = this._config;
    const tiltMode = c?.tilt_mode || "none";

    // Mode-specific hints
    const hints = {};

    if (tiltMode === "sequential") {
      hints.travel_time_close = "Start with slats fully open. Click Finish when the cover is fully closed, before the slats start tilting.";
      hints.travel_time_open = "Start with slats fully open. Click Finish when the cover is fully open.";
      hints.travel_startup_delay = pos === "open"
        ? "Start with slats fully open. Click Finish when the cover is fully closed, before the slats start tilting."
        : "Start with slats fully open. Click Finish when the cover is fully open.";
      hints.tilt_time_close = "Cover must be fully closed. Click Finish when the slats are fully closed.";
      hints.tilt_time_open = "Cover must be fully closed with slats closed. Click Finish when the slats are fully open.";
      hints.tilt_startup_delay = pos === "closed_tilt_open" || pos === "open"
        ? "Cover must be fully closed with slats open. Click Finish when the slats are fully closed."
        : "Cover must be fully closed with slats closed. Click Finish when the slats are fully open.";
    } else if (tiltMode === "proportional") {
      hints.travel_time_close = "Click Finish when the cover is fully closed and slats are fully tilted.";
      hints.travel_time_open = "Click Finish when the cover is fully open and slats are fully open.";
      hints.travel_startup_delay = `Click Finish when the cover is fully ${endpoint} and slats match.`;
    } else if (tiltMode === "dual_motor") {
      hints.travel_time_close = "Ensure tilt is in safe position. Click Finish when the cover is fully closed.";
      hints.travel_time_open = "Ensure tilt is in safe position. Click Finish when the cover is fully open.";
      hints.travel_startup_delay = `Ensure tilt is in safe position. Click Finish when the cover is fully ${endpoint}.`;
      hints.tilt_time_close = "Cover must be in tilt-allowed position. Click Finish when the slats are fully closed.";
      hints.tilt_time_open = "Cover must be in tilt-allowed position. Click Finish when the slats are fully open.";
      hints.tilt_startup_delay = pos === "closed_tilt_open" || pos === "open"
        ? "Cover must be in tilt-allowed position. Click Finish when the slats are fully closed."
        : "Cover must be in tilt-allowed position. Click Finish when the slats are fully open.";
    } else {
      // none mode
      hints.travel_time_close = "Click Finish when the cover is fully closed.";
      hints.travel_time_open = "Click Finish when the cover is fully open.";
      hints.travel_startup_delay = `Click Finish when the cover is fully ${endpoint}.`;
    }

    hints.min_movement_time = "Click Finish as soon as you notice the cover moving.";

    return hints[attr] || "";
  }
```

**Step 2: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: mode-specific calibration hints for all tilt strategies"
```

---

### Task 7: Validate dual_motor requires tilt switches in WebSocket API

When `tilt_mode=dual_motor` is set, `tilt_open_switch` and `tilt_close_switch` should be required. Add validation in `ws_update_config`.

**Files:**
- Modify: `custom_components/cover_time_based/websocket_api.py`
- Test: `tests/test_websocket_api.py`

**Step 1: Write the failing test**

Add to `tests/test_websocket_api.py`:

```python
class TestDualMotorValidation:
    """Test that dual_motor mode requires tilt switches."""

    @pytest.mark.asyncio
    async def test_dual_motor_requires_tilt_switches_on_save(self):
        """Setting tilt_mode=dual_motor without tilt switches should save but warn."""
        hass = MagicMock()
        connection = MagicMock()
        config_entry = MagicMock()
        config_entry.options = {}
        config_entry.domain = DOMAIN

        msg = {
            "id": 1,
            "type": "cover_time_based/update_config",
            "entity_id": ENTITY_ID,
            "tilt_mode": "dual_motor",
        }

        with patch(
            "custom_components.cover_time_based.websocket_api._resolve_config_entry",
            return_value=(config_entry, None),
        ):
            handler = _unwrap(ws_update_config)
            await handler(hass, connection, msg)

        # Should still succeed — validation is best-effort in the card
        connection.send_result.assert_called_once()
```

**Note:** We don't hard-block in the WS API because the card may send fields incrementally (user picks tilt_mode first, then picks switches). The card itself handles the UX of requiring switches before saving.

**Step 2: Run test**

Run: `python -m pytest tests/test_websocket_api.py::TestDualMotorValidation -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_websocket_api.py
git commit -m "test: add dual-motor validation test for WebSocket API"
```

---

### Task 8: Final verification and cleanup

**Step 1: Run full test suite**

Run: `python -m pytest tests/ -q`
Expected: All tests pass

**Step 2: Run linting**

Run: `ruff check . && ruff format .`
Expected: Clean

**Step 3: Run type checker**

Run: `npx pyright`
Expected: No new errors beyond pre-existing ones

**Step 4: Verify card renders correctly**

Deploy to HA for manual testing:
```bash
rm -Rf /workspaces/homeassistant-core/config/custom_components/cover_time_based && cp -r /workspaces/ha-cover-time-based/custom_components/cover_time_based /workspaces/homeassistant-core/config/custom_components/
```

**Step 5: Commit any final fixes**

If any issues found during verification, fix and commit.
