/**
 * Cover Time Based Configuration Card
 *
 * A Lovelace card for configuring and calibrating cover_time_based entities.
 * Uses HA built-in elements (ha-entity-picker, ha-input/ha-textfield, ha-checkbox,
 * ha-button) for consistent look and feel.
 *
 * All user-visible strings are translatable. Translations are embedded below.
 */

import {
  LitElement,
  html,
  css,
} from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";
import {
  filterEntitiesByValidEntries,
  switchPickerDomains,
  switchLabelKey,
  showsPulseTime,
  clearedEntitiesForMode,
  clearedTiltConfig,
  coverHasNativeTilt,
  coverConfirmedWithoutTilt,
} from "./entity-filter.js";
import { renderTextfield } from "./textfield-render.js";
import {
  DOMAIN,
  TIMING_ATTRIBUTES,
  ATTRIBUTE_TO_CONFIG,
} from "./constants.js";
import { translate } from "./translations.js";

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
      _saveError: { type: Boolean },
      _openHelp: { type: String },
    };
  }

  constructor() {
    super();
    this._selectedEntity = "";
    this._config = null;
    this._loading = false;
    this._saving = false;
    this._saveError = false;
    this._activeTab = "device";
    this._knownPosition = "unknown";
    this._helpersLoaded = false;
    this._openHelp = null;
  }

  // --- Translation support ---

  _t(key, replacements) {
    return translate(this.hass?.language || "en", key, replacements);
  }

  _switchLabel(baseKey, controlMode) {
    return this._t(switchLabelKey(baseKey, controlMode));
  }

  // --- Lifecycle ---

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

  updated(changedProperties) {
  }

  async _loadEntityList() {
    if (!this.hass) return;
    try {
      const [registry, configEntries] = await Promise.all([
        this.hass.callWS({ type: "config/entity_registry/list" }),
        this.hass.callWS({ type: "config_entries/get", domain: DOMAIN }),
      ]);
      const validEntryIds = configEntries.map((e) => e.entry_id);
      this._configEntryEntities = filterEntitiesByValidEntries(
        registry,
        validEntryIds,
        DOMAIN
      );
      this.requestUpdate();
    } catch (err) {
      console.error(
        "Failed to load entity registry / config entries:",
        err
      );
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
      this._loadError = this._t("yaml_warning");
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
    this._saveError = false;
    try {
      const { entry_id, ...fields } = this._config;
      await this.hass.callWS({
        type: "cover_time_based/update_config",
        ...fields,
        entity_id: this._selectedEntity,
      });
    } catch (err) {
      console.error("Failed to save config:", err);
      this._saveError = true;
      await this._loadConfig();
      setTimeout(() => { this._saveError = false; }, 3000);
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
    const c = this._config;
    const tiltMode = c?.tilt_mode || "none";

    // Startup delay uses the same hint as the corresponding direction
    let effectiveAttr = attr;
    if (attr === "travel_startup_delay") {
      effectiveAttr = pos === "open" ? "travel_time_close" : "travel_time_open";
    } else if (attr === "tilt_startup_delay") {
      effectiveAttr = (pos === "closed_tilt_open" || pos === "open")
        ? "tilt_time_close" : "tilt_time_open";
    }

    if (attr === "min_movement_time") {
      return this._t("hints.min_movement_time");
    }

    return this._t(`hints.${tiltMode}.${effectiveAttr}`);
  }

  _hasRequiredEntities(c) {
    if (!c) return false;
    if (c.control_mode === "wrapped") {
      if (!c.cover_entity_id) return false;
    } else if (c.control_mode === "pulse") {
      if (!c.open_switch_entity_id || !c.close_switch_entity_id || !c.stop_switch_entity_id) return false;
    } else {
      if (!c.open_switch_entity_id || !c.close_switch_entity_id) return false;
    }
    // Dual motor tilt requires tilt entities to be complete
    if (c.tilt_mode === "dual_motor" && c.control_mode !== "wrapped") {
      if (!c.tilt_open_switch || !c.tilt_close_switch) return false;
      if (c.control_mode === "pulse" && !c.tilt_stop_switch) return false;
    }
    return true;
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

  _onControlModeChange(e) {
    const mode = e.target.value;
    // Clear entities that don't belong to the new mode so they don't linger
    // as stale config (see clearedEntitiesForMode).
    const updates = { control_mode: mode, ...clearedEntitiesForMode(mode) };
    // Dual-motor tilt on a wrapped cover delegates tilt to the underlying
    // entity, so it is only valid once a cover that supports tilt natively is
    // selected. Switching into wrapped mode can't carry a dual_motor selection
    // from another mode, so reset it (the user can re-select it after picking a
    // suitable cover). Mirrors the "none" reset in _onTiltModeChange.
    if (mode === "wrapped" && this._config?.tilt_mode === "dual_motor") {
      Object.assign(updates, clearedTiltConfig());
    }
    this._updateLocal(updates);
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

  _coverSupportsNativeTilt(entityId) {
    return coverHasNativeTilt(entityId ? this.hass?.states?.[entityId] : null);
  }

  _onCoverEntityChange(e) {
    const value = e.detail?.value || e.target?.value || null;
    const updates = { cover_entity_id: value || null };
    // If dual_motor tilt is selected but the newly chosen cover is available and
    // doesn't support tilt natively, dual_motor can no longer be backed — reset
    // it. We only reset when the cover's tilt support can be positively
    // confirmed: an unavailable cover reports no features, and clearing then
    // would destroy a valid config while it is momentarily offline.
    if (
      this._config?.tilt_mode === "dual_motor" &&
      coverConfirmedWithoutTilt(value ? this.hass?.states?.[value] : null)
    ) {
      Object.assign(updates, clearedTiltConfig());
    }
    this._updateLocal(updates);
  }

  _onTiltModeChange(e) {
    const mode = e.target.value;
    if (mode === "none") {
      this._updateLocal(clearedTiltConfig());
    } else {
      const updates = { tilt_mode: mode };
      if (mode === "sequential_close" || mode === "sequential_open") {
        // Clear dual-motor fields when switching to either sequential variant
        updates.safe_tilt_position = null;
        updates.max_tilt_allowed_position = null;
        updates.tilt_open_switch = null;
        updates.tilt_close_switch = null;
        updates.tilt_stop_switch = null;
      } else if (mode === "dual_motor") {
        // Default safe_tilt_position to 100 (fully open)
        if (this._config.safe_tilt_position == null) {
          updates.safe_tilt_position = 100;
        }
        // Default max_tilt_allowed_position to 0 (fully closed)
        if (this._config.max_tilt_allowed_position == null) {
          updates.max_tilt_allowed_position = 0;
        }
      } else if (mode === "inline") {
        // Clear dual-motor fields when switching to inline
        updates.safe_tilt_position = null;
        updates.max_tilt_allowed_position = null;
        updates.tilt_open_switch = null;
        updates.tilt_close_switch = null;
        updates.tilt_stop_switch = null;
      }
      // Default close_includes_tilt for modes where closing tilts slats closed
      if (mode === "sequential_close" || mode === "dual_motor") {
        if (this._config.close_includes_tilt == null) {
          updates.close_includes_tilt = true;
        }
      } else {
        // inline and sequential_open do not use close_includes_tilt
        updates.close_includes_tilt = null;
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

    // Don't send an explicit direction — the server derives the correct
    // direction from the attribute name (e.g. travel_time_close → close,
    // tilt_time_open → open).  The position-based guess here was redundant
    // for travel and actively wrong for tilt from closed_tilt_open.

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

  _hasTiltMotor() {
    const c = this._config;
    if (!c || c.tilt_mode !== "dual_motor") return false;
    if (c.control_mode === "wrapped") return true;
    if (c.control_mode === "pulse")
      return !!(c.tilt_open_switch && c.tilt_close_switch && c.tilt_stop_switch);
    return !!(c.tilt_open_switch && c.tilt_close_switch);
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
    this._knownPosition = "unknown";
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
        // Position+tilt both closed
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
        <div class="card-header">${this._t("header")}</div>
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
                <ha-icon icon="mdi:loading" class="spin"></ha-icon> ${this._t("loading")}
              </div>`
            : ""}
        </div>
        ${this._openHelp
          ? html`<div
              class="popover-backdrop"
              @click=${this._closeHelp}
            ></div>`
          : ""}
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
              if (!confirm(this._t("confirm_cancel_calibration"))) {
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
        }}>${this._t("create_new")}</a>
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
        </div>
      </div>

      <div class="tabs">
        <button
          class="tab ${this._activeTab === "device" ? "active" : ""}"
          @click=${() => { this._activeTab = "device"; }}
        >${this._t("tabs.device")}</button>
        <button
          class="tab ${this._activeTab === "timing" ? "active" : ""}"
          ?disabled=${!this._hasRequiredEntities(c)}
          @click=${() => { this._activeTab = "timing"; }}
        >${this._t("tabs.calibration")}</button>
      </div>

      ${this._activeTab === "device"
        ? html`
            <fieldset ?disabled=${disabled}>
              ${this._renderControlMode(c)} ${this._renderInputEntities(c)}
              ${this._renderTiltSupport(c)}
              ${this._renderTiltMotorSection(c)}
            </fieldset>
          `
        : html`
            ${calibrating ? "" : this._renderPositionReset()}
            ${this._renderCalibration(calibrating)}
            ${this._renderTimingTable(c)}
          `}

      ${this._saving
        ? html`<div class="save-bar"><span class="saving-indicator">${this._t("saving")}</span></div>`
        : ""}
      ${this._saveError
        ? html`<div class="save-bar"><span class="save-error">${this._t("save_failed")}</span></div>`
        : ""}
    `;
  }

  _renderControlMode(c) {
    const mode = c.control_mode || "switch";
    const showPulseTime = showsPulseTime(mode);

    return html`
      <div class="section">
        <div class="field-label">${this._t("control_mode.label")}</div>
        <select class="ha-select" @change=${this._onControlModeChange}>
          <option value="wrapped" ?selected=${mode === "wrapped"}>
            ${this._t("control_mode.wrapped")}
          </option>
          <option value="switch" ?selected=${mode === "switch"}>
            ${this._t("control_mode.switch")}
          </option>
          <option value="pulse" ?selected=${mode === "pulse"}>
            ${this._t("control_mode.pulse")}
          </option>
          <option value="toggle" ?selected=${mode === "toggle"}>
            ${this._t("control_mode.toggle")}
          </option>
        </select>
        ${showPulseTime
          ? html`
              <div class="inline-field">
                ${renderTextfield({
                  type: "number",
                  min: "0.1",
                  max: "10",
                  step: "0.1",
                  suffix: "s",
                  label: this._t("control_mode.pulse_time"),
                  value: String(c.pulse_time || 1.0),
                  onChange: this._onPulseTimeChange,
                })}
              </div>
            `
          : ""}
      </div>
    `;
  }

  _toggleHelp(helperKey) {
    this._openHelp = this._openHelp === helperKey ? null : helperKey;
  }

  _closeHelp() {
    this._openHelp = null;
  }

  _renderToggleWithHelp(labelKey, helperKey, checked, onChange) {
    const open = this._openHelp === helperKey;
    return html`
      <div class="toggle-with-help">
        <span class="toggle-label">${this._t(labelKey)}</span>
        <span class="help-anchor">
          <ha-icon
            class="help-icon"
            icon="mdi:help-circle-outline"
            role="button"
            tabindex="0"
            aria-label=${this._t("more_info")}
            aria-expanded=${open ? "true" : "false"}
            @click=${(e) => {
              e.stopPropagation();
              this._toggleHelp(helperKey);
            }}
            @keydown=${(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                this._toggleHelp(helperKey);
              } else if (e.key === "Escape") {
                this._closeHelp();
              }
            }}
          ></ha-icon>
          ${open
            ? html`<div class="info-popover" role="tooltip">
                ${this._t(helperKey)}
              </div>`
            : ""}
        </span>
        <ha-switch
          class="toggle-switch"
          .checked=${checked}
          @change=${onChange}
        ></ha-switch>
      </div>
    `;
  }

  _renderInputEntities(c) {
    if (c.control_mode === "wrapped") {
      return html`
        <div class="section">
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.cover_entity_id || ""}
            .includeDomains=${["cover"]}
            .entityFilter=${this._filterNonTimeBased}
            label=${this._t("entities.cover_entity")}
            @value-changed=${this._onCoverEntityChange}
          ></ha-entity-picker>
          ${this._renderToggleWithHelp(
            "entities.ignore_reported_position",
            "entities.ignore_reported_position_helper",
            !!c.ignore_reported_position,
            (e) =>
              this._updateLocal({ ignore_reported_position: e.target.checked }),
          )}
          ${this._renderToggleWithHelp(
            "entities.force_time_based_position",
            "entities.force_time_based_position_helper",
            !!c.force_time_based_position,
            (e) =>
              this._updateLocal({ force_time_based_position: e.target.checked }),
          )}
          ${this._renderToggleWithHelp(
            "assumed_state.label",
            "assumed_state.helper",
            c.assumed_state !== false,
            (e) => this._updateLocal({ assumed_state: e.target.checked }),
          )}
        </div>
      `;
    }

    return html`
      <div class="section">
        <div class="field-label">${this._switchLabel("entities.switch_entities", c.control_mode)}</div>
        <div class="entity-grid">
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.open_switch_entity_id || ""}
            .includeDomains=${switchPickerDomains(c.control_mode)}
            label=${this._switchLabel("entities.open_switch", c.control_mode)}
            @value-changed=${(e) =>
              this._onSwitchEntityChange("open_switch_entity_id", e)}
          ></ha-entity-picker>
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.close_switch_entity_id || ""}
            .includeDomains=${switchPickerDomains(c.control_mode)}
            label=${this._switchLabel("entities.close_switch", c.control_mode)}
            @value-changed=${(e) =>
              this._onSwitchEntityChange("close_switch_entity_id", e)}
          ></ha-entity-picker>
          ${c.control_mode === "pulse" ? html`
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.stop_switch_entity_id || ""}
            .includeDomains=${switchPickerDomains(c.control_mode)}
            label=${this._switchLabel("entities.stop_switch", c.control_mode)}
            @value-changed=${(e) =>
              this._onSwitchEntityChange("stop_switch_entity_id", e)}
          ></ha-entity-picker>
          ` : ""}
        </div>
        ${this._renderToggleWithHelp(
          "assumed_state.label",
          "assumed_state.helper",
          c.assumed_state !== false,
          (e) => this._updateLocal({ assumed_state: e.target.checked }),
        )}
      </div>
    `;
  }

  _renderTiltSupport(c) {
    const tiltMode = c.tilt_mode || "none";

    // Dual-motor tilt on a wrapped cover delegates the tilt commands to the
    // underlying entity, so it requires that cover to support tilt natively.
    // Inline and sequential modes drive the main open/close motor, so they
    // work on any wrapped cover and stay available regardless.
    const allowDualMotor =
      c.control_mode !== "wrapped" ||
      this._coverSupportsNativeTilt(c.cover_entity_id);
    // The handlers reset dual_motor when it stops being backable, so in normal
    // UI flow allowDualMotor already covers it. Keep showing it when it is the
    // stored mode as a safety net for hand-edited configs or a wrapped cover
    // that is momentarily unavailable (features read as 0) — otherwise the
    // select would have a selected value missing from its options.
    const showDualMotor = allowDualMotor || tiltMode === "dual_motor";

    return html`
      <div class="section">
        <div class="field-label">${this._t("tilt.label")}</div>
        <select class="ha-select" @change=${this._onTiltModeChange}>
          <option value="none" ?selected=${tiltMode === "none"}>
            ${this._t("tilt.none")}
          </option>
          <option value="sequential_close" ?selected=${tiltMode === "sequential_close"}>
            ${this._t("tilt.sequential_close")}
          </option>
          <option value="sequential_open" ?selected=${tiltMode === "sequential_open"}>
            ${this._t("tilt.sequential_open")}
          </option>
          ${showDualMotor
            ? html`
                <option value="dual_motor" ?selected=${tiltMode === "dual_motor"}>
                  ${this._t("tilt.dual_motor")}
                </option>
              `
            : ""}
          <option value="inline" ?selected=${tiltMode === "inline"}>
            ${this._t("tilt.inline")}
          </option>
        </select>
        ${tiltMode === "sequential_close" || tiltMode === "dual_motor"
          ? html`
              <div class="inline-field">
                <ha-formfield .label=${this._t("tilt.close_includes_tilt")}>
                  <ha-switch
                    .checked=${c.close_includes_tilt !== false}
                    @change=${(e) =>
                      this._updateLocal({ close_includes_tilt: e.target.checked })}
                  ></ha-switch>
                </ha-formfield>
              </div>
            `
          : ""}
      </div>
    `;
  }

  _renderTiltMotorSection(c) {
    if (c.tilt_mode !== "dual_motor") return "";

    return html`
      <div class="section">
        <div class="field-label">${this._switchLabel("tilt_motor.label", c.control_mode)}</div>
        ${c.control_mode !== "wrapped" ? html`
        <div class="entity-grid">
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.tilt_open_switch || ""}
            .includeDomains=${switchPickerDomains(c.control_mode)}
            label=${this._switchLabel("tilt_motor.open_switch", c.control_mode)}
            @value-changed=${(e) =>
              this._onSwitchEntityChange("tilt_open_switch", e)}
          ></ha-entity-picker>
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.tilt_close_switch || ""}
            .includeDomains=${switchPickerDomains(c.control_mode)}
            label=${this._switchLabel("tilt_motor.close_switch", c.control_mode)}
            @value-changed=${(e) =>
              this._onSwitchEntityChange("tilt_close_switch", e)}
          ></ha-entity-picker>
          ${c.control_mode === "pulse" ? html`
          <ha-entity-picker
            .hass=${this.hass}
            .value=${c.tilt_stop_switch || ""}
            .includeDomains=${switchPickerDomains(c.control_mode)}
            label=${this._switchLabel("tilt_motor.stop_switch", c.control_mode)}
            @value-changed=${(e) =>
              this._onSwitchEntityChange("tilt_stop_switch", e)}
          ></ha-entity-picker>
          ` : ""}
        </div>
        ` : ""}
        <div class="dual-motor-config">
          ${renderTextfield({
            type: "number",
            min: "0",
            max: "100",
            step: "1",
            label: this._t("tilt_motor.safe_position"),
            hint: this._t("tilt_motor.safe_position_helper"),
            value: String(c.safe_tilt_position ?? 100),
            onChange: (e) => {
              const v = parseInt(e.target.value);
              if (!isNaN(v) && v >= 0 && v <= 100) {
                this._updateLocal({ safe_tilt_position: v });
              }
            },
          })}
          ${renderTextfield({
            type: "number",
            min: "0",
            max: "100",
            step: "1",
            label: this._t("tilt_motor.max_allowed_position"),
            hint: this._t("tilt_motor.max_allowed_helper"),
            value:
              c.max_tilt_allowed_position != null
                ? String(c.max_tilt_allowed_position)
                : "",
            onChange: (e) => {
              const v = e.target.value.trim();
              this._updateLocal({
                max_tilt_allowed_position: v === "" ? null : parseInt(v),
              });
            },
          })}
        </div>
      </div>
    `;
  }

  _renderTimingRow([labelKey, key, value, min = 0]) {
    return html`
      <tr>
        <td>${this._t(labelKey)}</td>
        <td class="value-cell">
          <input
            type="number"
            class="timing-input"
            .value=${value != null ? String(value) : ""}
            placeholder=${this._t("timing.not_set")}
            step="0.1"
            min="${min}"
            max="600"
            @change=${(e) => {
              const v = e.target.value.trim();
              this._updateLocal({ [key]: v === "" ? null : parseFloat(v) });
            }}
          /><span class="unit">s</span>
        </td>
      </tr>
    `;
  }

  _renderTimingTable(c) {
    const hasTiltTimes = c.tilt_mode === "sequential_close" || c.tilt_mode === "sequential_open" || c.tilt_mode === "dual_motor" || c.tilt_mode === "inline";

    const travelRows = [
      ["timing.travel_time_close", "travel_time_close", c.travel_time_close, 0.1],
      ["timing.travel_time_open", "travel_time_open", c.travel_time_open, 0.1],
      ["timing.travel_startup_delay", "travel_startup_delay", c.travel_startup_delay],
      ["timing.min_movement_time", "min_movement_time", c.min_movement_time],
    ];
    // Endpoint run-on only applies to switch mode (its latched relay must be
    // de-energized at the endpoint). Pulse/toggle/wrapped covers self-stop at
    // their limit switches, so the setting has no effect there.
    if ((c.control_mode || "switch") === "switch") {
      travelRows.push([
        "timing.endpoint_runon_time",
        "endpoint_runon_time",
        c.endpoint_runon_time,
      ]);
    }

    const tiltRows = [
      ["timing.tilt_time_close", "tilt_time_close", c.tilt_time_close, 0.1],
      ["timing.tilt_time_open", "tilt_time_open", c.tilt_time_open, 0.1],
      ["timing.tilt_startup_delay", "tilt_startup_delay", c.tilt_startup_delay],
    ];

    return html`
      <div class="section">
        <table class="timing-table">
          <thead>
            <tr>
              <th>${this._t("timing.travel_attribute_header")}</th>
              <th>${this._t("timing.value_header")}</th>
            </tr>
          </thead>
          <tbody>
            ${travelRows.map((row) => this._renderTimingRow(row))}
          </tbody>
        </table>
        ${hasTiltTimes ? html`
        <table class="timing-table" style="margin-top: 8px;">
          <thead>
            <tr>
              <th>${this._t("timing.tilt_attribute_header")}</th>
              <th>${this._t("timing.value_header")}</th>
            </tr>
          </thead>
          <tbody>
            ${tiltRows.map((row) => this._renderTimingRow(row))}
          </tbody>
        </table>
        ` : ""}
      </div>
    `;
  }

  _renderPositionReset() {
    const tiltMode = this._config?.tilt_mode || "none";
    const hasIndependentTilt = tiltMode === "sequential_close" || tiltMode === "sequential_open" || tiltMode === "dual_motor" || tiltMode === "inline";

    return html`
      <div class="section">
        <div class="field-label">${this._t("position.label")}</div>
        <div class="helper-text">
          ${this._t("position.helper")}
        </div>
        ${!this._hasTiltMotor() ? html`
          <div class="cover-controls">
            <ha-button title=${this._t("controls.open")} @click=${() => this._onCoverCommand("open_cover")}>
              <ha-icon icon="mdi:window-shutter-open" style="--mdc-icon-size: 18px;"></ha-icon>
            </ha-button>
            <ha-button title=${this._t("controls.stop")} @click=${() => this._onCoverCommand("stop_cover")}>
              <ha-icon icon="mdi:stop" style="--mdc-icon-size: 18px;"></ha-icon>
            </ha-button>
            <ha-button title=${this._t("controls.close")} @click=${() => this._onCoverCommand("close_cover")}>
              <ha-icon icon="mdi:window-shutter" style="--mdc-icon-size: 18px;"></ha-icon>
            </ha-button>
          </div>
        ` : html`
          <div class="cover-controls-wrapper">
            <div class="cover-controls">
              <span class="controls-label">${this._t("controls.cover_label")}</span>
              <ha-button title=${this._t("controls.open")} @click=${() => this._onCoverCommand("open_cover")}>
                <ha-icon icon="mdi:window-shutter-open" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
              <ha-button title=${this._t("controls.stop")} @click=${() => this._onCoverCommand("stop_cover")}>
                <ha-icon icon="mdi:stop" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
              <ha-button title=${this._t("controls.close")} @click=${() => this._onCoverCommand("close_cover")}>
                <ha-icon icon="mdi:window-shutter" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
            </div>
            <div class="cover-controls">
              <span class="controls-label">${this._t("controls.tilt_label")}</span>
              <ha-button title=${this._t("controls.tilt_open")} @click=${() => this._onCoverCommand("tilt_open")}>
                <ha-icon icon="mdi:arrow-top-right" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
              <ha-button title=${this._t("controls.tilt_stop")} @click=${() => this._onCoverCommand("tilt_stop")}>
                <ha-icon icon="mdi:stop" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
              <ha-button title=${this._t("controls.tilt_close")} @click=${() => this._onCoverCommand("tilt_close")}>
                <ha-icon icon="mdi:arrow-bottom-left" style="--mdc-icon-size: 18px;"></ha-icon>
              </ha-button>
            </div>
          </div>
        `}
        <div class="cal-form">
          <div class="cal-field">
            <select
              class="ha-select"
              id="position-select"
              @change=${(e) => this._onPositionPresetChange(e.target.value)}
            >
              <option value="unknown" ?selected=${this._knownPosition === "unknown"}>${this._t("position.unknown")}</option>
              <option value="open" ?selected=${this._knownPosition === "open"}>${this._t("position.open")}</option>
              ${hasIndependentTilt
                ? html`
                    <option value="closed_tilt_open" ?selected=${this._knownPosition === "closed_tilt_open"}>${this._t("position.closed_tilt_open")}</option>
                    <option value="closed_tilt_closed" ?selected=${this._knownPosition === "closed_tilt_closed"}>${this._t("position.closed_tilt_closed")}</option>
                  `
                : html`
                    <option value="closed" ?selected=${this._knownPosition === "closed"}>${this._t("position.closed")}</option>
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
    const hasTiltCalibration = tiltMode === "sequential_close" || tiltMode === "sequential_open" || tiltMode === "dual_motor" || tiltMode === "inline";

    const availableAttributes = TIMING_ATTRIBUTES.filter(
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
      // Position closed (tilt matches)
      disabledKeys.add("travel_time_close");
      disabledKeys.add("tilt_time_close");
    } else if (this._knownPosition === "closed_tilt_open") {
      // tilt=100, cover closed. For sequential_close this is the "rest" state
      // (slats at implicit-during-travel value), so travel_time_open and
      // tilt_time_close are measurable. For sequential_open this is the
      // "articulated" extreme (slats pushed open past cover-closed), so only
      // tilt_time_close (restore slats to rest via motor up) is measurable.
      disabledKeys.add("travel_time_close");
      disabledKeys.add("tilt_time_open");
      if (tiltMode === "sequential_open") {
        disabledKeys.add("travel_time_open");
        disabledKeys.add("travel_startup_delay");
        disabledKeys.add("min_movement_time");
      }
    } else if (this._knownPosition === "closed_tilt_closed") {
      // tilt=0, cover closed. For sequential_close this is the "articulated"
      // extreme — only tilt_time_open (restore slats) is measurable. For
      // sequential_open this is the "rest" state (slats at implicit), so
      // travel_time_open and tilt_time_open (articulate further down) are
      // measurable.
      disabledKeys.add("travel_time_close");
      disabledKeys.add("tilt_time_close");
      if (tiltMode !== "sequential_open") {
        disabledKeys.add("travel_time_open");
        disabledKeys.add("travel_startup_delay");
        disabledKeys.add("min_movement_time");
      }
    }

    // Startup delay requires the corresponding time to be calibrated first
    if (!hasTravel) disabledKeys.add("travel_startup_delay");
    if (!hasTilt) disabledKeys.add("tilt_startup_delay");
    if (!hasTravel) disabledKeys.add("min_movement_time");

    if (calibrating) {
      const calAttr = attrs.calibration_attribute || this._calibratingAttribute;
      const calLabel = this._t(`timing.${calAttr}`);
      return html`
        <div class="section calibration-active">
          <div class="field-label cal-label">
            <ha-icon icon="mdi:tune" style="--mdc-icon-size: 20px;"></ha-icon>
            ${this._t("calibration.active")}
          </div>
          <div class="cal-active-body">
            <strong>${calLabel}</strong>
            ${attrs.calibration_final_step
              ? html`<span class="cal-step"
                  >${this._t("calibration.final_step")}</span
                >`
              : attrs.calibration_step
                ? html`<span class="cal-step"
                    >${this._t("calibration.step", { step: attrs.calibration_step })}</span
                  >`
                : ""}
            <div class="cal-active-buttons">
              <ha-button @click=${() => this._onStopCalibration(true)}
                >${this._t("calibration.cancel")}</ha-button
              >
              <ha-button unelevated @click=${() => this._onStopCalibration(false)}
                >${this._t("calibration.finish")}</ha-button
              >
            </div>
          </div>
        </div>
      `;
    }

    return html`
      <div class="section">
        <div class="field-label">${this._t("calibration.label")}</div>
        <div class="cal-form">
          <div class="cal-field">
            <label class="sub-label" for="cal-attribute">${this._t("calibration.attribute_label")}</label>
            <select class="ha-select" id="cal-attribute"
              @change=${() => this.requestUpdate()}
            >
              ${availableAttributes.map(
                ([key, labelKey]) =>
                  html`<option value=${key} ?disabled=${disabledKeys.has(key)}>${this._t(labelKey)}</option>`
              )}
            </select>
          </div>
          <ha-button unelevated ?disabled=${this._knownPosition === "unknown"} @click=${this._onStartCalibration}
            >${this._t("calibration.start")}</ha-button
          >
        </div>
        ${this._knownPosition === "unknown"
          ? html`<div class="helper-text" style="margin-top: 8px;">
              ${this._t("calibration.set_position_first")}
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

      .toggle-with-help {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-top: 8px;
      }

      .toggle-label {
        font-size: 14px;
        color: var(--primary-text-color);
      }

      .toggle-with-help .toggle-switch {
        margin-left: auto;
      }

      .help-anchor {
        position: relative;
        display: inline-flex;
        align-items: center;
      }

      .help-icon {
        cursor: pointer;
        color: var(--secondary-text-color, #727272);
        --mdc-icon-size: 18px;
      }

      .help-icon:hover {
        color: var(--primary-color);
      }

      /* Transparent full-screen catcher so any outside tap dismisses the
         popover (works on touch devices, which have no hover/blur). */
      .popover-backdrop {
        position: fixed;
        inset: 0;
        z-index: 8;
      }

      .info-popover {
        position: absolute;
        top: calc(100% + 6px);
        left: 0;
        z-index: 9;
        width: max-content;
        max-width: 260px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 8px;
        padding: 10px 12px;
        font-size: 13px;
        line-height: 1.4;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
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
        flex-direction: column;
        gap: 4px;
        margin: 8px 0;
      }

      .cover-controls-wrapper .cover-controls {
        margin: 0;
      }

      .cover-controls {
        display: flex;
        align-items: center;
        gap: 4px;
        margin: 8px 0;
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

      .dual-motor-config ha-textfield,
      .dual-motor-config ha-input {
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
        table-layout: fixed;
        font-size: var(--paper-font-body1_-_font-size, 14px);
      }

      .timing-table th:first-child,
      .timing-table td:first-child {
        width: 65%;
      }

      .timing-table th:last-child,
      .timing-table td:last-child {
        width: 35%;
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
        text-align: right;
        white-space: nowrap;
      }

      .timing-input {
        box-sizing: content-box;
        width: 14ch;
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

      .cal-active-body {
        display: flex;
        flex-direction: column;
        gap: 4px;
        padding: 8px 0 0;
        font-size: var(--paper-font-body1_-_font-size, 14px);
      }

      .cal-active-buttons {
        display: flex;
        gap: 8px;
        padding-top: 4px;
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

      .save-error {
        font-size: 12px;
        color: var(--error-color, #db4437);
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

// Guard the define: now that the card loads via a Lovelace resource (after HA
// swaps in the scoped-custom-element-registry polyfill) a double-evaluation
// would otherwise throw "already defined".
if (!customElements.get("cover-time-based-card")) {
  customElements.define("cover-time-based-card", CoverTimeBasedCard);
}

// Register with Lovelace card picker, guarded against double-evaluation so the
// picker doesn't list the card twice.
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "cover-time-based-card")) {
  window.customCards.push({
    type: "cover-time-based-card",
    name: "Cover Time Based Configuration",
    description:
      "Configure device type, input entities, timing, and run calibration tests for cover_time_based entities.",
  });
}
