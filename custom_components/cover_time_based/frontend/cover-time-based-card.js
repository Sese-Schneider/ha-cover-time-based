/**
 * Cover Time Based Configuration Card
 *
 * A Lovelace card for configuring and calibrating cover_time_based entities.
 * Uses HA built-in elements (ha-entity-picker, ha-textfield, ha-checkbox,
 * ha-button) for consistent look and feel.
 */

import {
  LitElement,
  html,
  css,
} from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";

const DOMAIN = "cover_time_based";

const ATTRIBUTE_LABELS = {
  travel_time_close: "Travel time (close)",
  travel_time_open: "Travel time (open)",
  travel_motor_overhead: "Travel motor overhead",
  tilt_time_close: "Tilt time (close)",
  tilt_time_open: "Tilt time (open)",
  tilt_motor_overhead: "Tilt motor overhead",
  min_movement_time: "Minimum movement time",
};

class CoverTimeBasedCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _selectedEntity: { type: String },
      _config: { type: Object },
      _loading: { type: Boolean },
      _saving: { type: Boolean },
      _dirty: { type: Boolean },
      _activeTab: { type: String },
    };
  }

  constructor() {
    super();
    this._selectedEntity = "";
    this._config = null;
    this._loading = false;
    this._saving = false;
    this._dirty = false;
    this._activeTab = "device";
    this._helpersLoaded = false;
  }

  async connectedCallback() {
    super.connectedCallback();
    if (!this._helpersLoaded) {
      this._helpersLoaded = true;

      // ha-entity-picker is lazy-loaded and may only live in a scoped
      // registry.  Force HA to load the module by triggering the config
      // editor of a card that uses it (same pattern as Mushroom cards).
      if (!customElements.get("ha-entity-picker")) {
        try {
          const helpers = await window.loadCardHelpers();
          // Create an entities card instance so we can access its class
          const c = await helpers.createCardElement({
            type: "entities",
            entities: [],
          });
          // The static getConfigElement() imports the editor module,
          // which in turn imports ha-entity-picker and registers it.
          if (c?.constructor?.getConfigElement) {
            await c.constructor.getConfigElement();
          }
        } catch (_) {
          // best-effort
        }
      }

      // Wait for the element to be defined (with timeout).
      if (!customElements.get("ha-entity-picker")) {
        try {
          await Promise.race([
            customElements.whenDefined("ha-entity-picker"),
            new Promise((_, reject) =>
              setTimeout(() => reject(new Error("timeout")), 10000)
            ),
          ]);
        } catch (_) {
          console.warn(
            "[cover-time-based-card] ha-entity-picker not available"
          );
        }
      }

      this.requestUpdate();
    }
  }

  setConfig(_config) {
    // No user-configurable options
  }

  getCardSize() {
    return 8;
  }

  getGridOptions() {
    return { columns: "full", min_columns: 6, min_rows: 4 };
  }

  // --- Data fetching ---

  async _loadConfig() {
    if (!this._selectedEntity || !this.hass) return;
    this._loading = true;
    try {
      this._config = await this.hass.callWS({
        type: "cover_time_based/get_config",
        entity_id: this._selectedEntity,
      });
      this._dirty = false;
    } catch (err) {
      console.error("Failed to load config:", err);
      this._config = null;
    }
    this._loading = false;
  }

  _updateLocal(updates) {
    this._config = { ...this._config, ...updates };
    this._dirty = true;
  }

  async _save() {
    if (!this._selectedEntity || !this.hass || !this._config) return;
    this._saving = true;
    try {
      const { entry_id, ...fields } = this._config;
      await this.hass.callWS({
        type: "cover_time_based/update_config",
        entity_id: this._selectedEntity,
        ...fields,
      });
      this._dirty = false;
      // Reload to get server-confirmed values
      await this._loadConfig();
    } catch (err) {
      console.error("Failed to save config:", err);
    }
    this._saving = false;
  }

  // --- Entity helpers ---

  _getEntityState() {
    if (!this._selectedEntity || !this.hass) return null;
    return this.hass.states[this._selectedEntity];
  }

  _isCalibrating() {
    const state = this._getEntityState();
    return state?.attributes?.calibration_active === true;
  }

  // --- Event handlers ---

  _onEntityChange(e) {
    const newValue = e.detail?.value || e.target?.value || "";
    this._selectedEntity = newValue;
    this._config = null;
    if (this._selectedEntity) {
      this._loadConfig();
    }
  }

  _onDeviceTypeChange(e) {
    this._updateLocal({ device_type: e.target.value });
  }

  _onInputModeChange(e) {
    this._updateLocal({ input_mode: e.target.value });
  }

  _onPulseTimeChange(e) {
    const val = parseFloat(e.target.value);
    if (!isNaN(val) && val >= 0.1) {
      this._updateLocal({ pulse_time: val });
    }
  }

  _onSwitchEntityChange(field, e) {
    const value = e.detail?.value || e.target?.value || null;
    this._updateLocal({ [field]: value || null });
  }

  _onCoverEntityChange(e) {
    const value = e.detail?.value || e.target?.value || null;
    this._updateLocal({ cover_entity_id: value || null });
  }

  _onTiltModeChange(e) {
    const mode = e.target.value;
    if (mode === "none") {
      this._updateLocal({
        tilting_time_down: null,
        tilting_time_up: null,
        travel_moves_with_tilt: false,
      });
    } else {
      const updates = { travel_moves_with_tilt: mode === "during" };
      // Initialize tilt times if enabling for the first time
      if (this._config.tilting_time_down == null) {
        updates.tilting_time_down = 5.0;
      }
      if (this._config.tilting_time_up == null) {
        updates.tilting_time_up = 5.0;
      }
      this._updateLocal(updates);
    }
  }

  async _onStartCalibration() {
    const attrSelect = this.shadowRoot.querySelector("#cal-attribute");
    const dirSelect = this.shadowRoot.querySelector("#cal-direction");
    const timeoutInput = this.shadowRoot.querySelector("#cal-timeout");

    const data = {
      entity_id: this._selectedEntity,
      attribute: attrSelect.value,
      timeout: parseInt(timeoutInput.value) || 120,
    };
    if (dirSelect.value) {
      data.direction = dirSelect.value;
    }

    try {
      await this.hass.callService(DOMAIN, "start_calibration", data);
    } catch (err) {
      console.error("Start calibration failed:", err);
    }
  }

  async _onStopCalibration(cancel = false) {
    try {
      const data = { entity_id: this._selectedEntity };
      if (cancel) data.cancel = true;
      await this.hass.callService(DOMAIN, "stop_calibration", data);
    } catch (err) {
      console.error("Stop calibration failed:", err);
    }
  }

  async _onCoverCommand(command) {
    try {
      await this.hass.callService("cover", command, {
        entity_id: this._selectedEntity,
      });
    } catch (err) {
      console.error(`Cover ${command} failed:`, err);
    }
  }

  _onCreateNew() {
    if (this._dirty) {
      if (!confirm("You have unsaved changes. Discard and continue?")) {
        return;
      }
    }
    // Navigate to helpers/add with domain param — HA auto-opens the config flow
    window.history.pushState(
      null,
      "",
      `/config/helpers/add?domain=${DOMAIN}`
    );
    window.dispatchEvent(new Event("location-changed"));
  }

  // --- Rendering ---

  render() {
    if (!this.hass) return html``;
    return html`
      <ha-card>
        <div class="card-header">Cover Time Based Configuration</div>
        <div class="card-content">
          ${this._renderEntityPicker()}
          ${this._selectedEntity && this._config
            ? this._renderConfigSections()
            : ""}
          ${this._loading
            ? html`<div class="loading">
                <ha-icon icon="mdi:loading" class="spin"></ha-icon> Loading...
              </div>`
            : ""}
        </div>
      </ha-card>
    `;
  }

  _renderEntityPicker() {
    return html`
      <div class="section">
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this._selectedEntity}
          .includeDomains=${["cover"]}
          .entityFilter=${(entity) =>
            "travelling_time_down" in (entity.attributes || {})}
          label="Entity"
          @value-changed=${(e) => {
            this._selectedEntity = e.detail?.value || "";
            this._config = null;
            this._dirty = false;
            if (this._selectedEntity) this._loadConfig();
          }}
        ></ha-entity-picker>
        <a class="create-new-link" href="#" @click=${(e) => {
          e.preventDefault();
          this._onCreateNew();
        }}>+ Create new cover entity</a>
      </div>
    `;
  }

  _renderConfigSections() {
    const c = this._config;
    const calibrating = this._isCalibrating();
    const disabled = this._saving || calibrating;

    return html`
      <div class="entity-info">
        <div class="entity-info-row">
          <div>
            <strong>
              ${this._getEntityState()?.attributes?.friendly_name ||
              this._selectedEntity}
            </strong>
            <span class="entity-id">${this._selectedEntity}</span>
          </div>
          <div class="cover-controls">
            <ha-button @click=${() => this._onCoverCommand("open_cover")}>
              <ha-icon icon="mdi:arrow-up" style="--mdc-icon-size: 18px;"></ha-icon>
            </ha-button>
            <ha-button @click=${() => this._onCoverCommand("stop_cover")}>
              <ha-icon icon="mdi:stop" style="--mdc-icon-size: 18px;"></ha-icon>
            </ha-button>
            <ha-button @click=${() => this._onCoverCommand("close_cover")}>
              <ha-icon icon="mdi:arrow-down" style="--mdc-icon-size: 18px;"></ha-icon>
            </ha-button>
          </div>
        </div>
      </div>

      <div class="tabs">
        <button
          class="tab ${this._activeTab === "device" ? "active" : ""}"
          @click=${() => { this._activeTab = "device"; }}
        >Device</button>
        <button
          class="tab ${this._activeTab === "timing" ? "active" : ""}"
          @click=${() => { this._activeTab = "timing"; }}
        >Timing</button>
      </div>

      ${this._activeTab === "device"
        ? html`
            <fieldset ?disabled=${disabled}>
              ${this._renderDeviceType(c)} ${this._renderInputEntities(c)}
              ${this._renderInputMode(c)} ${this._renderTiltSupport(c)}
            </fieldset>

            ${this._dirty
              ? html`
                  <div class="save-bar">
                    <ha-button unelevated @click=${this._save} ?disabled=${this._saving}>
                      ${this._saving ? "Saving..." : "Save"}
                    </ha-button>
                    <ha-button @click=${this._loadConfig}>Discard</ha-button>
                  </div>
                `
              : ""}
          `
        : html`
            ${this._renderTimingTable(c)}
            ${this._renderCalibration(calibrating)}
          `}
    `;
  }

  _renderDeviceType(c) {
    return html`
      <div class="section">
        <div class="field-label">Device Type</div>
        <div class="radio-group">
          <label class="radio-label">
            <input
              type="radio"
              name="device_type"
              value="switch"
              ?checked=${c.device_type === "switch"}
              @change=${this._onDeviceTypeChange}
            />
            Control via switches
          </label>
          <label class="radio-label">
            <input
              type="radio"
              name="device_type"
              value="cover"
              ?checked=${c.device_type === "cover"}
              @change=${this._onDeviceTypeChange}
            />
            Wrap an existing cover entity
          </label>
        </div>
      </div>
    `;
  }

  _renderInputEntities(c) {
    if (c.device_type === "cover") {
      return html`
        <div class="section">
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.cover_entity_id || ""}
            .includeDomains=${["cover"]}
            label="Cover Entity"
            @value-changed=${this._onCoverEntityChange}
          ></ha-entity-picker>
        </div>
      `;
    }

    return html`
      <div class="section">
        <div class="field-label">Switch Entities</div>
        <div class="entity-grid">
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.open_switch_entity_id || ""}
            .includeDomains=${["switch"]}
            label="Open switch"
            @value-changed=${(e) =>
              this._onSwitchEntityChange("open_switch_entity_id", e)}
          ></ha-entity-picker>
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.close_switch_entity_id || ""}
            .includeDomains=${["switch"]}
            label="Close switch"
            @value-changed=${(e) =>
              this._onSwitchEntityChange("close_switch_entity_id", e)}
          ></ha-entity-picker>
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.stop_switch_entity_id || ""}
            .includeDomains=${["switch"]}
            label="Stop switch (optional)"
            @value-changed=${(e) =>
              this._onSwitchEntityChange("stop_switch_entity_id", e)}
          ></ha-entity-picker>
        </div>
      </div>
    `;
  }

  _renderInputMode(c) {
    const showPulseTime =
      c.input_mode === "pulse" || c.input_mode === "toggle";

    return html`
      <div class="section">
        <div class="field-label">Input Mode</div>
        <div class="radio-group">
          <label class="radio-label">
            <input
              type="radio"
              name="input_mode"
              value="switch"
              ?checked=${c.input_mode === "switch"}
              @change=${this._onInputModeChange}
            />
            Switch (latching)
          </label>
          <label class="radio-label">
            <input
              type="radio"
              name="input_mode"
              value="pulse"
              ?checked=${c.input_mode === "pulse"}
              @change=${this._onInputModeChange}
            />
            Pulse (momentary)
          </label>
          <label class="radio-label">
            <input
              type="radio"
              name="input_mode"
              value="toggle"
              ?checked=${c.input_mode === "toggle"}
              @change=${this._onInputModeChange}
            />
            Toggle (same button)
          </label>
        </div>
        ${showPulseTime
          ? html`
              <div class="inline-field">
                <ha-textfield
                  type="number"
                  min="0.1"
                  max="10"
                  step="0.1"
                  suffix="s"
                  label="Pulse time"
                  .value=${String(c.pulse_time || 1.0)}
                  @change=${this._onPulseTimeChange}
                ></ha-textfield>
              </div>
            `
          : ""}
      </div>
    `;
  }

  _renderTiltSupport(c) {
    const hasTilt = c.tilting_time_down != null || c.tilting_time_up != null;
    const tiltMode = !hasTilt ? "none" : c.travel_moves_with_tilt ? "during" : "before_after";

    return html`
      <div class="section">
        <div class="field-label">Tilting</div>
        <div class="radio-group">
          <label class="radio-label">
            <input type="radio" name="tilt_mode" value="none"
              ?checked=${tiltMode === "none"}
              @change=${this._onTiltModeChange} />
            Not supported
          </label>
          <label class="radio-label">
            <input type="radio" name="tilt_mode" value="before_after"
              ?checked=${tiltMode === "before_after"}
              @change=${this._onTiltModeChange} />
            Tilts before/after cover movement
          </label>
          <label class="radio-label">
            <input type="radio" name="tilt_mode" value="during"
              ?checked=${tiltMode === "during"}
              @change=${this._onTiltModeChange} />
            Tilts during cover movement
          </label>
        </div>
      </div>
    `;
  }

  _renderTimingTable(c) {
    const state = this._getEntityState();
    if (!state) return "";

    const attrs = state.attributes;
    const hasTilt = c.tilting_time_down != null || c.tilting_time_up != null;

    const rows = [
      ["Travel time (close)", attrs.travelling_time_down],
      ["Travel time (open)", attrs.travelling_time_up],
      ["Travel motor overhead", attrs.travel_motor_overhead],
    ];

    if (hasTilt) {
      rows.push(
        ["Tilt time (close)", attrs.tilting_time_down],
        ["Tilt time (open)", attrs.tilting_time_up],
        ["Tilt motor overhead", attrs.tilt_motor_overhead]
      );
    }

    rows.push(["Minimum movement time", attrs.min_movement_time]);

    return html`
      <div class="section">
        <div class="field-label">Timing Configuration</div>
        <table class="timing-table">
          <thead>
            <tr>
              <th>Attribute</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(
              ([label, value]) => html`
                <tr>
                  <td>${label}</td>
                  <td class="value-cell">
                    ${value != null
                      ? html`${value}<span class="unit">s</span>`
                      : html`<span class="not-set">Not set</span>`}
                  </td>
                </tr>
              `
            )}
          </tbody>
        </table>
      </div>
    `;
  }

  _renderCalibration(calibrating) {
    const state = this._getEntityState();
    const attrs = state?.attributes || {};
    const hasTilt =
      this._config?.tilting_time_down != null ||
      this._config?.tilting_time_up != null;

    const availableAttributes = Object.entries(ATTRIBUTE_LABELS).filter(
      ([key]) => {
        if (!hasTilt && key.startsWith("tilt_")) return false;
        return true;
      }
    );

    if (calibrating) {
      return html`
        <div class="section calibration-active">
          <div class="field-label cal-label">
            <ha-icon icon="mdi:tune" style="--mdc-icon-size: 20px;"></ha-icon>
            Calibration Active
          </div>
          <div class="cal-status">
            <strong>${ATTRIBUTE_LABELS[attrs.calibration_attribute]}</strong>
            ${attrs.calibration_step
              ? html`<span class="cal-step"
                  >Step ${attrs.calibration_step}</span
                >`
              : ""}
          </div>
          <div class="button-row">
            <ha-button unelevated @click=${() => this._onStopCalibration(false)}
              >Stop</ha-button
            >
            <ha-button @click=${() => this._onStopCalibration(true)}
              >Cancel</ha-button
            >
          </div>
        </div>
      `;
    }

    return html`
      <div class="section">
        <div class="field-label">Calibration</div>
        <div class="cal-form">
          <div class="cal-field">
            <label class="sub-label" for="cal-attribute">Attribute</label>
            <select class="ha-select" id="cal-attribute">
              ${availableAttributes.map(
                ([key, label]) =>
                  html`<option value=${key}>${label}</option>`
              )}
            </select>
          </div>
          <div class="cal-field">
            <label class="sub-label" for="cal-direction"
              >Direction (optional)</label
            >
            <select class="ha-select" id="cal-direction">
              <option value="">Auto</option>
              <option value="open">Open</option>
              <option value="close">Close</option>
            </select>
          </div>
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
          <ha-button unelevated @click=${this._onStartCalibration}
            >Go</ha-button
          >
        </div>
      </div>
    `;
  }

  // --- Styles ---

  static get styles() {
    return css`
      :host {
        display: block;
      }

      .card-header {
        font-size: 24px;
        font-weight: 400;
        padding: 24px 16px 16px;
        line-height: 32px;
        color: var(--ha-card-header-color, --primary-text-color);
      }

      .card-content {
        padding: 0 16px 16px;
      }

      .section {
        margin-bottom: 16px;
        padding-bottom: 16px;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
      }

      .section:last-child {
        border-bottom: none;
        margin-bottom: 0;
        padding-bottom: 0;
      }

      .field-label {
        font-weight: 500;
        font-size: var(--paper-font-body1_-_font-size, 14px);
        margin-bottom: 8px;
        color: var(--primary-text-color);
      }

      .sub-label {
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-bottom: 4px;
        display: block;
      }

      /* Entity info banner */
      .entity-info {
        margin-bottom: 16px;
        padding: 12px 16px;
        background: var(--primary-color);
        color: var(--text-primary-color, #fff);
        border-radius: 8px;
      }

      .entity-info-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }

      .entity-id {
        display: block;
        font-size: 0.85em;
        opacity: 0.8;
        font-family: var(--code-font-family, monospace);
      }

      .cover-controls {
        display: flex;
        gap: 4px;
        flex-shrink: 0;
      }

      /* Tabs */
      .tabs {
        display: flex;
        border-bottom: 2px solid var(--divider-color, #e0e0e0);
        margin-bottom: 16px;
      }

      .tab {
        flex: 1;
        padding: 10px 16px;
        border: none;
        background: none;
        cursor: pointer;
        font-size: var(--paper-font-body1_-_font-size, 14px);
        font-weight: 500;
        color: var(--secondary-text-color);
        border-bottom: 2px solid transparent;
        margin-bottom: -2px;
        transition: color 0.2s, border-color 0.2s;
        font-family: inherit;
      }

      .tab:hover {
        color: var(--primary-text-color);
      }

      .tab.active {
        color: var(--primary-color);
        border-bottom-color: var(--primary-color);
      }

      /* Radio groups */
      .radio-group {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .radio-label {
        display: flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
        font-size: var(--paper-font-body1_-_font-size, 14px);
        color: var(--primary-text-color);
      }

      .radio-group.indent {
        margin-left: 28px;
        margin-top: 8px;
      }

      /* Tilt toggle */
      .tilt-toggle {
        display: flex;
        align-items: center;
        gap: 4px;
        cursor: pointer;
        font-size: var(--paper-font-body1_-_font-size, 14px);
        color: var(--primary-text-color);
        font-weight: 500;
      }

      /* Entity grid */
      .entity-grid {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .inline-field {
        margin-top: 8px;
      }

      ha-textfield {
        --mdc-text-field-fill-color: transparent;
      }

      ha-entity-picker {
        display: block;
      }

      .create-new-link {
        display: inline-block;
        margin-top: 8px;
        font-size: 13px;
        color: var(--primary-color);
        text-decoration: none;
        cursor: pointer;
      }

      .create-new-link:hover {
        text-decoration: underline;
      }

      /* Fieldset for disabling during calibration */
      fieldset {
        border: none;
        margin: 0;
        padding: 0;
      }

      fieldset:disabled {
        opacity: 0.5;
        pointer-events: none;
      }

      /* Timing table */
      .timing-table {
        width: 100%;
        border-collapse: collapse;
        font-size: var(--paper-font-body1_-_font-size, 14px);
      }

      .timing-table th {
        text-align: left;
        padding: 8px 12px;
        border-bottom: 2px solid var(--divider-color);
        color: var(--secondary-text-color);
        font-weight: 500;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }

      .timing-table td {
        padding: 10px 12px;
        border-bottom: 1px solid var(--divider-color);
        color: var(--primary-text-color);
      }

      .value-cell {
        font-family: var(--code-font-family, monospace);
      }

      .unit {
        color: var(--secondary-text-color);
        margin-left: 2px;
      }

      .not-set {
        color: var(--secondary-text-color);
        font-style: italic;
        font-family: inherit;
      }

      /* Native select for calibration dropdowns */
      .ha-select {
        width: 100%;
        padding: 8px 12px;
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        background: var(--card-background-color, var(--ha-card-background));
        color: var(--primary-text-color);
        font-size: var(--paper-font-body1_-_font-size, 14px);
        font-family: var(--paper-font-body1_-_font-family, inherit);
        cursor: pointer;
        box-sizing: border-box;
      }

      .ha-select:focus {
        outline: none;
        border-color: var(--primary-color);
      }

      /* Calibration */
      .cal-form {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: flex-end;
      }

      .cal-field {
        display: flex;
        flex-direction: column;
        flex: 1;
        min-width: 140px;
      }

      .cal-field-narrow {
        flex: 0;
        min-width: 100px;
      }

      .cal-status {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 8px 0;
        font-size: var(--paper-font-body1_-_font-size, 14px);
      }

      .cal-step {
        opacity: 0.9;
        font-size: 0.9em;
      }

      .calibration-active {
        background: var(--warning-color, #ff9800);
        color: var(--text-primary-color, #fff);
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 0;
        border-bottom: none;
      }

      .cal-label {
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--text-primary-color, #fff);
      }

      .button-row {
        display: flex;
        gap: 8px;
        margin-top: 8px;
      }

      /* Save bar */
      .save-bar {
        display: flex;
        gap: 8px;
        padding: 12px 0;
        margin-bottom: 16px;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
      }

      .loading {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 24px;
        color: var(--secondary-text-color);
      }

      @keyframes spin {
        from {
          transform: rotate(0deg);
        }
        to {
          transform: rotate(360deg);
        }
      }

      .spin {
        animation: spin 1s linear infinite;
      }
    `;
  }
}

customElements.define("cover-time-based-card", CoverTimeBasedCard);

// Register with Lovelace card picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: "cover-time-based-card",
  name: "Cover Time Based Configuration",
  description:
    "Configure device type, input entities, timing, and run calibration tests for cover_time_based entities.",
});
