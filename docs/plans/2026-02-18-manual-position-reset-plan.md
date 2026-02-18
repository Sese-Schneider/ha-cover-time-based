# Manual Position Reset Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a "Current Position" section to the calibration tab that gates calibration behind a known endpoint position, infers direction automatically, and resets the internal position tracker.

**Architecture:** Pure frontend state (`_knownPosition`) in the Lovelace card. Reset calls existing `set_known_position` / `set_known_tilt_position` services. No new backend code. Timeout field removed, hardcoded to 300s. Attribute dropdown options disabled based on position.

**Tech Stack:** LitElement card (cover-time-based-card.js), HA service calls

---

### Task 1: Add `_knownPosition` property and reset it on entity change

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js:28-48`

**Step 1: Add the property declaration and constructor init**

In `static get properties()`, add:
```js
_knownPosition: { type: String },
```

In `constructor()`, add:
```js
this._knownPosition = "unknown";
```

**Step 2: Reset on entity switch**

In the entity picker `@value-changed` handler (around line 308), where `this._config = null` and `this._dirty = false` are set, also add:
```js
this._knownPosition = "unknown";
```

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: add _knownPosition state property to card"
```

---

### Task 2: Add the Current Position section UI

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js` — `_renderCalibration()` method (around line 568)

**Step 1: Add `_renderPositionReset()` method**

Add this new method before `_renderCalibration()`:

```js
_renderPositionReset() {
  const isUnknown = this._knownPosition === "unknown";
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
            @change=${(e) => { this._knownPosition = e.target.value; }}
          >
            <option value="unknown" ?selected=${this._knownPosition === "unknown"}>Unknown</option>
            <option value="open" ?selected=${this._knownPosition === "open"}>Fully open</option>
            <option value="closed" ?selected=${this._knownPosition === "closed"}>Fully closed</option>
          </select>
        </div>
        <ha-button
          unelevated
          ?disabled=${isUnknown}
          @click=${this._onResetPosition}
        >Reset</ha-button>
      </div>
    </div>
  `;
}
```

**Step 2: Call it from the calibration tab render**

In the `render()` method, in the timing tab branch (around line 376), add the position reset before calibration:

Change:
```js
: html`
    ${this._renderCalibration(calibrating)}
    ${this._renderTimingTable(c)}
  `}
```
To:
```js
: html`
    ${this._renderPositionReset()}
    ${this._renderCalibration(calibrating)}
    ${this._renderTimingTable(c)}
  `}
```

**Step 3: Add `.helper-text` CSS**

Add in the styles section (after `.field-label` styles):

```css
.helper-text {
  font-size: 12px;
  color: var(--secondary-text-color, #727272);
  margin: -4px 0 8px;
}
```

**Step 4: Verify in browser**

Deploy and check the Calibration tab shows the new section above the calibration form.

**Step 5: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: add Current Position section to calibration tab"
```

---

### Task 3: Implement the Reset action

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js` — add `_onResetPosition()` method

**Step 1: Add the reset handler**

Add this method in the event handlers section (after `_onCoverCommand`):

```js
async _onResetPosition() {
  if (this._knownPosition === "unknown") return;
  const position = this._knownPosition === "open" ? 100 : 0;
  try {
    await this.hass.callService(DOMAIN, "set_known_position", {
      entity_id: this._selectedEntity,
      position,
    });
    await this.hass.callService(DOMAIN, "set_known_tilt_position", {
      entity_id: this._selectedEntity,
      position,
    });
  } catch (err) {
    console.error("Reset position failed:", err);
  }
}
```

**Step 2: Verify in browser**

Deploy, select "Fully open", click Reset. Confirm via HA developer tools that the entity's `current_position` attribute updates to 100.

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: implement position reset via set_known_position services"
```

---

### Task 4: Disable attributes based on position and gate Start button

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js` — `_renderCalibration()` method

**Step 1: Add attribute disabling logic**

In `_renderCalibration()`, after the `availableAttributes` filter, add a set of disabled keys:

```js
const disabledKeys = new Set();
if (this._knownPosition === "unknown") {
  availableAttributes.forEach(([key]) => disabledKeys.add(key));
} else if (this._knownPosition === "open") {
  disabledKeys.add("travel_time_open");
  disabledKeys.add("tilt_time_open");
} else if (this._knownPosition === "closed") {
  disabledKeys.add("travel_time_close");
  disabledKeys.add("tilt_time_close");
}
```

**Step 2: Update the attribute dropdown to use `disabled`**

Change the `<option>` rendering from:
```js
${availableAttributes.map(
  ([key, label]) =>
    html`<option value=${key}>${label}</option>`
)}
```
To:
```js
${availableAttributes.map(
  ([key, label]) =>
    html`<option value=${key} ?disabled=${disabledKeys.has(key)}>${label}</option>`
)}
```

**Step 3: Disable Start button when position is unknown**

Change the Start button from:
```js
<ha-button unelevated @click=${this._onStartCalibration}
  >Start</ha-button
>
```
To:
```js
<ha-button
  unelevated
  ?disabled=${this._knownPosition === "unknown"}
  @click=${this._onStartCalibration}
>Start</ha-button>
```

**Step 4: Add hint text when Start is disabled**

After the closing `</div>` of the `cal-form` div, add:
```js
${this._knownPosition === "unknown"
  ? html`<div class="helper-text" style="margin-top: 8px;">
      Set position to start calibration.
    </div>`
  : ""}
```

**Step 5: Verify in browser**

Deploy and check:
- Position Unknown → all attributes disabled, Start disabled, hint shown
- Position "Fully open" → travel_time_open and tilt_time_open greyed, others enabled, Start enabled
- Position "Fully closed" → travel_time_close and tilt_time_close greyed, others enabled, Start enabled

**Step 6: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: gate calibration behind known position, disable unavailable attributes"
```

---

### Task 5: Remove timeout field, hardcode 300s, add direction inference

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js` — `_onStartCalibration()` and `_renderCalibration()`

**Step 1: Remove timeout field from render**

In `_renderCalibration()`, remove the entire timeout `cal-field-narrow` div:
```js
          <div class="cal-field cal-field-narrow">
            <ha-textfield
              type="number"
              min="1"
              max="600"
              step="1"
              suffix="s"
              label="Timeout"
              value="120"
              id="cal-timeout"
            ></ha-textfield>
          </div>
```

**Step 2: Update `_onStartCalibration()` — hardcode timeout, add direction**

Replace the method body:
```js
async _onStartCalibration() {
  const attrSelect = this.shadowRoot.querySelector("#cal-attribute");

  const data = {
    entity_id: this._selectedEntity,
    attribute: attrSelect.value,
    timeout: 300,
  };

  if (this._knownPosition === "open") {
    data.direction = "close";
  } else if (this._knownPosition === "closed") {
    data.direction = "open";
  }

  this._knownPosition = "unknown";

  try {
    await this.hass.callService(DOMAIN, "start_calibration", data);
  } catch (err) {
    console.error("Start calibration failed:", err);
  }
}
```

Note: `this._knownPosition = "unknown"` is set before the service call so the UI updates immediately.

**Step 3: Also reset position dropdown UI**

After setting `this._knownPosition = "unknown"`, the LitElement reactive property will trigger re-render, so the dropdown will reflect "Unknown" automatically. However, also reset the position `<select>` element explicitly to be safe:

Add after the service call block (inside the method, at the end):
```js
const posSelect = this.shadowRoot.querySelector("#position-select");
if (posSelect) posSelect.value = "unknown";
```

**Step 4: Verify in browser**

Deploy and check:
- No timeout field shown
- Starting calibration from "Fully open" sends direction "close"
- Starting calibration resets position to Unknown

**Step 5: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: remove timeout field, hardcode 300s, infer direction from position"
```

---

### Task 6: Reset position to Unknown on calibration finish/cancel

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js` — `_onStopCalibration()`

**Step 1: Reset position in stop handler**

In `_onStopCalibration()`, add position reset:

```js
async _onStopCalibration(cancel = false) {
  this._knownPosition = "unknown";
  try {
    const data = { entity_id: this._selectedEntity };
    if (cancel) data.cancel = true;
    await this.hass.callService(DOMAIN, "stop_calibration", data);
  } catch (err) {
    console.error("Stop calibration failed:", err);
  }
}
```

**Step 2: Verify in browser**

Deploy and check:
- After Finish → position is Unknown, Start disabled
- After Cancel → position is Unknown, Start disabled

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: reset position to unknown on calibration finish or cancel"
```

---

### Task 7: Auto-select first enabled attribute when position changes

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js`

**Step 1: After position reset or dropdown change, select first enabled option**

The attribute dropdown may have its currently selected option become disabled when position changes. Add a `updated()` lifecycle hook or handle it in `_onResetPosition`:

At the end of `_onResetPosition()`, after the service calls, add:
```js
this.updateComplete.then(() => {
  const select = this.shadowRoot.querySelector("#cal-attribute");
  if (select) {
    const firstEnabled = [...select.options].find((o) => !o.disabled);
    if (firstEnabled) select.value = firstEnabled.value;
  }
});
```

**Step 2: Verify in browser**

Deploy and check that after Reset, the attribute dropdown jumps to the first available (non-disabled) option.

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: auto-select first enabled calibration attribute after position reset"
```

---

### Task 8: Hide position reset section during active calibration

**Files:**
- Modify: `custom_components/cover_time_based/frontend/cover-time-based-card.js`

**Step 1: Conditionally render position reset**

In the `render()` method, only show position reset when not calibrating. Change:
```js
: html`
    ${this._renderPositionReset()}
    ${this._renderCalibration(calibrating)}
    ${this._renderTimingTable(c)}
  `}
```
To:
```js
: html`
    ${calibrating ? "" : this._renderPositionReset()}
    ${this._renderCalibration(calibrating)}
    ${this._renderTimingTable(c)}
  `}
```

**Step 2: Verify in browser**

Deploy and trigger a calibration — confirm the Current Position section disappears while calibrating and reappears after.

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/frontend/cover-time-based-card.js
git commit -m "feat: hide position reset section during active calibration"
```
