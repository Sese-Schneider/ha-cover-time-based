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

const ATTRIBUTE_TO_CONFIG = {
  travel_time_close: "travel_time_close",
  travel_time_open: "travel_time_open",
  tilt_time_close: "tilt_time_close",
  tilt_time_open: "tilt_time_open",
  travel_startup_delay: "travel_startup_delay",
  tilt_startup_delay: "tilt_startup_delay",
  min_movement_time: "min_movement_time",
};

class CoverTimeBasedCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _selectedEntity: { type: String },
      _config: { type: Object },
      _loading: { type: Boolean },
      _saving: { type: Boolean },
      _activeTab: { type: String },
      _knownPosition: { type: String },
      _loadError: { type: String },
    };
  }

  constructor() {
    super();
    this._selectedEntity = "";
    this._config = null;
    this._loading = false;
    this._saving = false;
    this._activeTab = "device";
    this._knownPosition = "unknown";
    this._helpersLoaded = false;
  }

  _getScrollParent() {
    let el = this;
    while (el) {
      el = el.parentElement || el.getRootNode()?.host;
      if (el && el.scrollTop > 0) return el;
    }
    return document.scrollingElement || document.documentElement;
  }

  async performUpdate() {
    const scroller = this._getScrollParent();
    const scrollTop = scroller?.scrollTop ?? 0;
    await super.performUpdate();
    if (scroller) scroller.scrollTop = scrollTop;
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

    // Load entity list from full registry (includes config_entry_id)
    this._loadEntityList();
  }

  async _loadEntityList() {
    if (!this.hass) return;
    try {
      const entries = await this.hass.callWS({
        type: "config/entity_registry/list",
      });
      this._configEntryEntities = entries
        .filter((e) => e.platform === "cover_time_based" && e.config_entry_id)
        .map((e) => e.entity_id);
      this.requestUpdate();
    } catch (err) {
      console.error("Failed to load entity registry:", err);
      this._configEntryEntities = [];
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._autoSaveTimer) clearTimeout(this._autoSaveTimer);
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
    this._loadError = null;
    try {
      this._config = await this.hass.callWS({
        type: "cover_time_based/get_config",
        entity_id: this._selectedEntity,
      });
    } catch (err) {
      console.error("Failed to load config:", err);
      this._config = null;
      this._loadError = "This entity uses YAML configuration and cannot be configured from this card. Please migrate to the UI: Settings → Devices & Services → Helpers → Create Helper → Cover Time Based.";
    }
    this._loading = false;
  }

  _updateLocal(updates) {
    this._config = { ...this._config, ...updates };
    this._scheduleAutoSave();
  }

  _scheduleAutoSave() {
    if (this._autoSaveTimer) clearTimeout(this._autoSaveTimer);
    this._autoSaveTimer = setTimeout(() => this._autoSave(), 500);
  }

  async _autoSave() {
    if (!this._selectedEntity || !this.hass || !this._config) return;
    this._saving = true;
    try {
      const { entry_id, ...fields } = this._config;
      await this.hass.callWS({
        type: "cover_time_based/update_config",
        entity_id: this._selectedEntity,
        ...fields,
      });
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
    if (this._calibratingOverride === true) return true;
    const state = this._getEntityState();
    return state?.attributes?.calibration_active === true;
  }

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

  _filterNonTimeBased = (stateObj) => {
    const entry = this.hass.entities[stateObj.entity_id];
    return !entry || entry.platform !== DOMAIN;
  };

  _onCoverEntityChange(e) {
    const value = e.detail?.value || e.target?.value || null;
    this._updateLocal({ cover_entity_id: value || null });
  }

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
      if (mode === "sequential") {
        // Clear dual-motor fields when switching to sequential
        updates.safe_tilt_position = null;
        updates.min_tilt_allowed_position = null;
        updates.tilt_open_switch = null;
        updates.tilt_close_switch = null;
        updates.tilt_stop_switch = null;
      } else if (mode === "dual_motor") {
        // Default min_tilt_allowed_position to fully closed
        if (this._config.min_tilt_allowed_position == null) {
          updates.min_tilt_allowed_position = 100;
        }
      }
      this._updateLocal(updates);
    }
  }

  async _onStartCalibration() {
    const attrSelect = this.shadowRoot.querySelector("#cal-attribute");
    const savedPosition = this._knownPosition;

    const data = {
      entity_id: this._selectedEntity,
      attribute: attrSelect.value,
      timeout: 300,
    };

    if (savedPosition === "open") {
      data.direction = "close";
    } else if (savedPosition === "closed" || savedPosition === "closed_tilt_open" || savedPosition === "closed_tilt_closed") {
      data.direction = "open";
    }

    this._calibratingAttribute = attrSelect.value;
    this._calibratingOverride = undefined;

    try {
      await this.hass.callWS({
        type: `${DOMAIN}/start_calibration`,
        ...data,
      });
      this._knownPosition = "unknown";
      this._calibratingOverride = true;
      this.requestUpdate();
    } catch (err) {
      console.error("Start calibration failed:", err);
      const msg = err?.message || String(err);
      alert(`Calibration failed: ${msg}`);
    }
  }

  async _onStopCalibration(cancel = false) {
    this._knownPosition = "unknown";
    this._calibratingOverride = false;
    this.requestUpdate();
    try {
      const result = await this.hass.callWS({
        type: "cover_time_based/stop_calibration",
        entity_id: this._selectedEntity,
        cancel,
      });
      if (!cancel && result?.attribute) {
        const configKey = ATTRIBUTE_TO_CONFIG[result.attribute];
        if (configKey) this._updateLocal({ [configKey]: result.value });
      }
    } catch (err) {
      console.error("Stop calibration failed:", err);
    }
  }

  async _onCoverCommand(command) {
    const cmdMap = {
      open_cover: "open",
      close_cover: "close",
      stop_cover: "stop",
      tilt_open: "tilt_open",
      tilt_close: "tilt_close",
      tilt_stop: "tilt_stop",
    };
    try {
      await this.hass.callWS({
        type: `${DOMAIN}/raw_command`,
        entity_id: this._selectedEntity,
        command: cmdMap[command],
      });
    } catch (err) {
      console.error(`Cover ${command} failed:`, err);
    }
  }

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
        tiltPosition = hasTilt ? 100 : null;
        break;
      case "closed":
        // Proportional/none mode: position+tilt both closed
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

  _onCreateNew() {
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
          ${this._loadError
            ? html`<div class="yaml-warning">${this._loadError}</div>`
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
          .includeEntities=${this._configEntryEntities || []}
          label=""
          @value-changed=${(e) => {
            const newEntity = e.detail?.value || "";
            if (newEntity === this._selectedEntity) return;
            if (this._isCalibrating()) {
              if (!confirm("A calibration is running. Cancel it and continue?")) {
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
            this._loadError = null;
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
          ${this._activeTab === "timing" && !(this._config?.tilt_open_switch && this._config?.tilt_close_switch) ? html`
            <div class="cover-controls">
              <ha-button title="Open" @click=${() => this._onCoverCommand("open_cover")}>
                <ha-icon icon="mdi:window-shutter-open" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
              <ha-button title="Stop" @click=${() => this._onCoverCommand("stop_cover")}>
                <ha-icon icon="mdi:stop" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
              <ha-button title="Close" @click=${() => this._onCoverCommand("close_cover")}>
                <ha-icon icon="mdi:window-shutter" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
            </div>
          ` : ""}
        </div>
        ${this._activeTab === "timing" && this._config?.tilt_open_switch && this._config?.tilt_close_switch ? html`
          <div class="cover-controls-wrapper">
            <div class="cover-controls">
              <span class="controls-label">Cover</span>
              <ha-button title="Open" @click=${() => this._onCoverCommand("open_cover")}>
                <ha-icon icon="mdi:window-shutter-open" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
              <ha-button title="Stop" @click=${() => this._onCoverCommand("stop_cover")}>
                <ha-icon icon="mdi:stop" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
              <ha-button title="Close" @click=${() => this._onCoverCommand("close_cover")}>
                <ha-icon icon="mdi:window-shutter" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
            </div>
            <div class="cover-controls">
              <span class="controls-label">Tilt</span>
              <ha-button title="Tilt open" @click=${() => this._onCoverCommand("tilt_open")}>
                <ha-icon icon="mdi:arrow-top-right" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
              <ha-button title="Tilt stop" @click=${() => this._onCoverCommand("tilt_stop")}>
                <ha-icon icon="mdi:stop" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
              <ha-button title="Tilt close" @click=${() => this._onCoverCommand("tilt_close")}>
                <ha-icon icon="mdi:arrow-bottom-left" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
            </div>
          </div>
        ` : ""}
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
              ${this._renderTiltMotorSection(c)}
            </fieldset>
          `
        : html`
            ${calibrating ? "" : this._renderPositionReset()}
            ${this._renderCalibration(calibrating)}
            ${this._renderTimingTable(c)}
          `}

      ${this._saving
        ? html`<div class="save-bar"><span class="saving-indicator">Saving...</span></div>`
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
            .entityFilter=${this._filterNonTimeBased}
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
        <div class="helper-text">
          Additional travel time at endpoints (0%/100%) for position reset
        </div>
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

  _renderTimingTable(c) {
    const hasTiltTimes = c.tilt_mode === "sequential" || c.tilt_mode === "dual_motor";

    const rows = [
      ["Travel time (close)", "travel_time_close", c.travel_time_close],
      ["Travel time (open)", "travel_time_open", c.travel_time_open],
      ["Travel startup delay", "travel_startup_delay", c.travel_startup_delay],
    ];

    if (hasTiltTimes) {
      rows.push(
        ["Tilt time (close)", "tilt_time_close", c.tilt_time_close],
        ["Tilt time (open)", "tilt_time_open", c.tilt_time_open],
        ["Tilt startup delay", "tilt_startup_delay", c.tilt_startup_delay]
      );
    }

    rows.push(["Minimum movement time", "min_movement_time", c.min_movement_time]);

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
    const tiltMode = this._config?.tilt_mode || "none";
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

  _renderCalibration(calibrating) {
    const state = this._getEntityState();
    const attrs = state?.attributes || {};
    const tiltMode = this._config?.tilt_mode || "none";
    const hasTiltCalibration = tiltMode === "sequential" || tiltMode === "dual_motor";

    const availableAttributes = Object.entries(ATTRIBUTE_LABELS).filter(
      ([key]) => {
        if (!hasTiltCalibration && key.startsWith("tilt_")) return false;
        return true;
      }
    );

    const c = this._config;
    const hasTravel = c?.travel_time_close || c?.travel_time_open;
    const hasTilt = c?.tilt_time_close || c?.tilt_time_open;

    const disabledKeys = new Set();
    if (this._knownPosition === "unknown") {
      availableAttributes.forEach(([key]) => disabledKeys.add(key));
    } else if (this._knownPosition === "open") {
      disabledKeys.add("travel_time_open");
      disabledKeys.add("tilt_time_open");
      if (hasTiltCalibration) {
        // Tilt only changes when cover is closed — can't test from open
        disabledKeys.add("tilt_time_close");
        disabledKeys.add("tilt_startup_delay");
      }
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
      // Tilt must open before travel can move
      disabledKeys.add("travel_time_open");
      disabledKeys.add("travel_startup_delay");
      disabledKeys.add("min_movement_time");
    }

    // Startup delay requires the corresponding time to be calibrated first
    if (!hasTravel) disabledKeys.add("travel_startup_delay");
    if (!hasTilt) disabledKeys.add("tilt_startup_delay");
    if (!hasTravel) disabledKeys.add("min_movement_time");

    if (calibrating) {
      return html`
        <div class="section calibration-active">
          <div class="field-label cal-label">
            <ha-icon icon="mdi:tune" style="--mdc-icon-size: 20px;"></ha-icon>
            Calibration Active
          </div>
          <div class="cal-form">
            <div class="cal-status">
              <strong>${ATTRIBUTE_LABELS[attrs.calibration_attribute || this._calibratingAttribute]}</strong>
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
            <select class="ha-select" id="cal-attribute"
              @change=${() => this.requestUpdate()}
            >
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
          : html`<div class="helper-text" style="margin-top: 8px;">
              ${this._getCalibrationHint()}
            </div>`}
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

      .cover-controls-wrapper {
        display: flex;
        justify-content: flex-end;
        gap: 12px;
        padding: 4px 0;
      }

      .cover-controls {
        display: flex;
        align-items: center;
        gap: 4px;
        flex-shrink: 0;
      }

      .controls-label {
        font-size: 11px;
        color: inherit;
        opacity: 0.8;
        white-space: nowrap;
        min-width: 36px;
        text-align: right;
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

      /* Dual motor config */
      .dual-motor-config {
        display: flex;
        gap: 16px;
        margin-top: 12px;
      }

      .dual-motor-config ha-textfield {
        flex: 1;
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

      /* Save indicator */
      .save-bar {
        display: flex;
        justify-content: flex-end;
        padding: 8px 0;
      }

      .saving-indicator {
        font-size: 12px;
        color: var(--secondary-text-color);
        font-style: italic;
      }

      .loading {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 24px;
        color: var(--secondary-text-color);
      }

      .yaml-warning {
        padding: 16px;
        margin: 8px 0;
        background: var(--warning-color, #ff9800);
        color: var(--text-primary-color, #fff);
        border-radius: 8px;
        font-size: 14px;
        line-height: 1.4;
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
