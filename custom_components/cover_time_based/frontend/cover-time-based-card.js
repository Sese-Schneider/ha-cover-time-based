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
  travel_startup_delay: "Travel startup delay",
  tilt_time_close: "Tilt time (close)",
  tilt_time_open: "Tilt time (open)",
  tilt_startup_delay: "Tilt startup delay",
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
      _knownPosition: { type: String },
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
    this._knownPosition = "unknown";
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

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._isCalibrating()) {
      this._onStopCalibration(true);
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
    if (this._calibratingOverride === false) return false;
    const state = this._getEntityState();
    return state?.attributes?.calibration_active === true;
  }

  _hasRequiredEntities(c) {
    if (!c) return false;
    if (c.device_type === "cover") return !!c.cover_entity_id;
    return !!c.open_switch_entity_id && !!c.close_switch_entity_id;
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
    this._calibratingOverride = undefined;

    try {
      await this.hass.callService(DOMAIN, "start_calibration", data);
    } catch (err) {
      console.error("Start calibration failed:", err);
    }

    const posSelect = this.shadowRoot.querySelector("#position-select");
    if (posSelect) posSelect.value = "unknown";
  }

  async _onStopCalibration(cancel = false) {
    this._knownPosition = "unknown";
    this._calibratingOverride = false;
    this.requestUpdate();
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

  async _onPositionChange(value) {
    this._knownPosition = value;
    if (value === "unknown") return;
    const position = value === "open" ? 100 : 0;
    try {
      await this.hass.callService(DOMAIN, "set_known_position", {
        entity_id: this._selectedEntity,
        position,
      });
      if (this._config?.tilting_time_down != null || this._config?.tilting_time_up != null) {
        await this.hass.callService(DOMAIN, "set_known_tilt_position", {
          entity_id: this._selectedEntity,
          tilt_position: position,
        });
      }
      this.updateComplete.then(() => {
        const select = this.shadowRoot.querySelector("#cal-attribute");
        if (select) {
          const firstEnabled = [...select.options].find((o) => !o.disabled);
          if (firstEnabled) select.value = firstEnabled.value;
        }
      });
    } catch (err) {
      console.error("Reset position failed:", err);
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
          label=""
          @value-changed=${(e) => {
            const newEntity = e.detail?.value || "";
            if (newEntity === this._selectedEntity) return;
            if (this._dirty || this._isCalibrating()) {
              const msg = this._isCalibrating()
                ? "A calibration is running. Cancel it and continue?"
                : "You have unsaved changes. Discard and continue?";
              if (!confirm(msg)) {
                const current = this._selectedEntity;
                const picker = e.target;
                picker.value = current;
                requestAnimationFrame(() => {
                  picker.value = current;
                });
                this.requestUpdate();
                return;
              }
              if (this._isCalibrating()) {
                this._onStopCalibration(true);
              }
            }
            this._selectedEntity = newEntity;
            this._config = null;
            this._dirty = false;
            this._knownPosition = "unknown";
            this._calibratingOverride = undefined;
            this._activeTab = "device";
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
          ?disabled=${!this._hasRequiredEntities(c)}
          @click=${() => { this._activeTab = "timing"; }}
        >Calibration</button>
      </div>

      ${this._activeTab === "device"
        ? html`
            <fieldset ?disabled=${disabled}>
              ${this._renderDeviceType(c)} ${this._renderInputEntities(c)}
              ${this._renderEndpointRunon(c)}
              ${this._renderInputMode(c)} ${this._renderTiltSupport(c)}
            </fieldset>
          `
        : html`
            ${calibrating ? "" : this._renderPositionReset()}
            ${this._renderCalibration(calibrating)}
            ${this._renderTimingTable(c)}
          `}

      ${this._dirty
        ? html`
            <div class="save-bar">
              <ha-button @click=${this._loadConfig}>Discard</ha-button>
              <ha-button unelevated @click=${this._save} ?disabled=${this._saving}>
                ${this._saving ? "Saving..." : "Save"}
              </ha-button>
            </div>
          `
        : ""}
    `;
  }

  _renderDeviceType(c) {
    return html`
      <div class="section">
        <div class="field-label">Device Type</div>
        <select class="ha-select" @change=${this._onDeviceTypeChange}>
          <option value="switch" ?selected=${c.device_type === "switch"}>
            Control via switches
          </option>
          <option value="cover" ?selected=${c.device_type === "cover"}>
            Wrap an existing cover entity
          </option>
        </select>
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
        <select class="ha-select" @change=${this._onInputModeChange}>
          <option value="switch" ?selected=${c.input_mode === "switch"}>
            Switch (latching)
          </option>
          <option value="pulse" ?selected=${c.input_mode === "pulse"}>
            Pulse (momentary)
          </option>
          <option value="toggle" ?selected=${c.input_mode === "toggle"}>
            Toggle (same button)
          </option>
        </select>
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

  _renderEndpointRunon(c) {
    return html`
      <div class="section">
        <div class="field-label">Endpoint Run-on Time</div>
        <ha-textfield
          type="number"
          min="0"
          max="10"
          step="0.1"
          suffix="s"
          label=""
          .value=${String(c.endpoint_runon_time || "")}
          @change=${(e) => {
            const v = e.target.value.trim();
            this._updateLocal({ endpoint_runon_time: v === "" ? null : parseFloat(v) });
          }}
        ></ha-textfield>
      </div>
    `;
  }

  _renderTiltSupport(c) {
    const hasTilt = c.tilting_time_down != null || c.tilting_time_up != null;
    const tiltMode = !hasTilt ? "none" : c.travel_moves_with_tilt ? "during" : "before_after";

    return html`
      <div class="section">
        <div class="field-label">Tilting</div>
        <select class="ha-select" @change=${this._onTiltModeChange}>
          <option value="none" ?selected=${tiltMode === "none"}>
            Not supported
          </option>
          <option value="before_after" ?selected=${tiltMode === "before_after"}>
            Tilts before/after cover movement
          </option>
          <option value="during" ?selected=${tiltMode === "during"}>
            Tilts with cover movement
          </option>
        </select>
      </div>
    `;
  }

  _renderTimingTable(c) {
    const hasTilt = c.tilting_time_down != null || c.tilting_time_up != null;

    const rows = [
      ["Travel time (close)", "travelling_time_down", c.travelling_time_down],
      ["Travel time (open)", "travelling_time_up", c.travelling_time_up],
      ["Travel startup delay", "travel_startup_delay", c.travel_startup_delay],
    ];

    if (hasTilt) {
      rows.push(
        ["Tilt time (close)", "tilting_time_down", c.tilting_time_down],
        ["Tilt time (open)", "tilting_time_up", c.tilting_time_up],
        ["Tilt startup delay", "tilt_startup_delay", c.tilt_startup_delay]
      );
    }

    rows.push(
      ["Endpoint runon time", "endpoint_runon_time", c.endpoint_runon_time],
      ["Minimum movement time", "min_movement_time", c.min_movement_time]
    );

    return html`
      <div class="section">
        <table class="timing-table">
          <thead>
            <tr>
              <th>Attribute</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(
              ([label, key, value]) => html`
                <tr>
                  <td>${label}</td>
                  <td class="value-cell">
                    <input
                      type="number"
                      class="timing-input"
                      .value=${value != null ? String(value) : ""}
                      placeholder="Not set"
                      step="0.1"
                      min="0"
                      max="600"
                      @change=${(e) => {
                        const v = e.target.value.trim();
                        this._updateLocal({ [key]: v === "" ? null : parseFloat(v) });
                      }}
                    /><span class="unit">s</span>
                  </td>
                </tr>
              `
            )}
          </tbody>
        </table>
      </div>
    `;
  }

  _renderPositionReset() {
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
              @change=${(e) => this._onPositionChange(e.target.value)}
            >
              <option value="unknown" ?selected=${this._knownPosition === "unknown"}>Unknown</option>
              <option value="open" ?selected=${this._knownPosition === "open"}>Fully open</option>
              <option value="closed" ?selected=${this._knownPosition === "closed"}>Fully closed</option>
            </select>
          </div>
        </div>
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

    if (calibrating) {
      return html`
        <div class="section calibration-active">
          <div class="field-label cal-label">
            <ha-icon icon="mdi:tune" style="--mdc-icon-size: 20px;"></ha-icon>
            Calibration Active
          </div>
          <div class="cal-form">
            <div class="cal-status">
              <strong>${ATTRIBUTE_LABELS[attrs.calibration_attribute]}</strong>
              ${attrs.calibration_step
                ? html`<span class="cal-step"
                    >Step ${attrs.calibration_step}</span
                  >`
                : ""}
            </div>
            <ha-button @click=${() => this._onStopCalibration(true)}
              >Cancel</ha-button
            >
            <ha-button unelevated @click=${() => this._onStopCalibration(false)}
              >Finish</ha-button
            >
          </div>
        </div>
      `;
    }

    return html`
      <div class="section">
        <div class="field-label">Timing Calibration</div>
        <div class="cal-form">
          <div class="cal-field">
            <label class="sub-label" for="cal-attribute">Attribute</label>
            <select class="ha-select" id="cal-attribute">
              ${availableAttributes.map(
                ([key, label]) =>
                  html`<option value=${key} ?disabled=${disabledKeys.has(key)}>${label}</option>`
              )}
            </select>
          </div>
          <ha-button unelevated ?disabled=${this._knownPosition === "unknown"} @click=${this._onStartCalibration}
            >Start</ha-button
          >
        </div>
        ${this._knownPosition === "unknown"
          ? html`<div class="helper-text" style="margin-top: 8px;">
              Set position to start calibration.
            </div>`
          : ""}
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

      .helper-text {
        font-size: 12px;
        color: var(--secondary-text-color, #727272);
        margin: -4px 0 8px;
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

      .tab:disabled {
        opacity: 0.4;
        cursor: default;
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
        display: flex;
        align-items: center;
        gap: 4px;
      }

      .timing-input {
        width: 80px;
        padding: 4px 8px;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 4px;
        font-family: var(--code-font-family, monospace);
        font-size: inherit;
        color: var(--primary-text-color);
        background: var(--card-background-color, #fff);
        text-align: right;
      }

      .timing-input::placeholder {
        color: var(--secondary-text-color);
        font-style: italic;
        font-family: inherit;
      }

      .unit {
        color: var(--secondary-text-color);
        margin-left: 2px;
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
        flex: 1;
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
        justify-content: flex-end;
        gap: 8px;
        margin-top: 8px;
      }

      /* Save bar */
      .save-bar {
        display: flex;
        justify-content: flex-end;
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
