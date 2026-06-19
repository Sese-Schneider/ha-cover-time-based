/**
 * Cover Time Based Configuration Card
 *
 * A Lovelace card for configuring and calibrating cover_time_based entities.
 * Uses HA built-in elements (ha-entity-picker, ha-input/ha-textfield, ha-checkbox,
 * ha-button) for consistent look and feel.
 *
 * This element holds the card's logic (lifecycle, data fetching, event handlers).
 * Its presentation, styles, translations, and constants live in sibling modules:
 * card-render.js, card-styles.js, translations.js, and constants.js. All
 * user-visible strings are translatable (see translations.js).
 */

import { LitElement } from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";
import {
  filterEntitiesByValidEntries,
  switchLabelKey,
  clearedEntitiesForMode,
  clearedTiltConfig,
  coverHasNativeTilt,
  coverConfirmedWithoutTilt,
} from "./entity-filter.js";
import { DOMAIN, ATTRIBUTE_TO_CONFIG } from "./constants.js";
import { translate } from "./translations.js";
import { cardStyles } from "./card-styles.js";
import { renderCard } from "./card-render.js";

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
    return renderCard(this);
  }

  _toggleHelp(helperKey) {
    this._openHelp = this._openHelp === helperKey ? null : helperKey;
  }

  _closeHelp() {
    this._openHelp = null;
  }

  // --- Styles ---

  static get styles() {
    return cardStyles;
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
