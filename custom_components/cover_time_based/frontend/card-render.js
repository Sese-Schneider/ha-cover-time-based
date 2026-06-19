import { html } from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";
import { renderTextfield } from "./textfield-render.js";
import { switchPickerDomains, showsPulseTime } from "./entity-filter.js";
import { TIMING_ATTRIBUTES } from "./constants.js";

export function renderCard(card) {
  if (!card.hass) return html``;
  return html`
    <ha-card>
      <div class="card-header">${card._t("header")}</div>
      <div class="card-content">
        ${renderEntityPicker(card)}
        ${card._selectedEntity && card._config
          ? renderConfigSections(card)
          : ""}
        ${card._loadError
          ? html`<div class="yaml-warning">${card._loadError}</div>`
          : ""}
        ${card._loading
          ? html`<div class="loading">
              <ha-icon icon="mdi:loading" class="spin"></ha-icon> ${card._t("loading")}
            </div>`
          : ""}
      </div>
      ${card._openHelp
        ? html`<div
            class="popover-backdrop"
            @click=${card._closeHelp}
          ></div>`
        : ""}
    </ha-card>
  `;
}

export function renderEntityPicker(card) {
  return html`
    <div class="section">
      <ha-entity-picker
        .hass=${card.hass}
        .value=${card._selectedEntity}
        .includeEntities=${card._configEntryEntities || []}
        label=""
        @value-changed=${(e) => {
          const newEntity = e.detail?.value || "";
          if (newEntity === card._selectedEntity) return;
          if (card._isCalibrating()) {
            if (!confirm(card._t("confirm_cancel_calibration"))) {
              const current = card._selectedEntity;
              const picker = e.target;
              picker.value = current;
              requestAnimationFrame(() => {
                picker.value = current;
              });
              card.requestUpdate();
              return;
            }
            if (card._isCalibrating()) {
              card._onStopCalibration(true);
            }
          }
          card._selectedEntity = newEntity;
          card._config = null;
          card._loadError = null;
          card._knownPosition = "unknown";
          card._calibratingOverride = undefined;
          card._activeTab = "device";
          if (card._selectedEntity) card._loadConfig();
        }}
      ></ha-entity-picker>
      <a class="create-new-link" href="#" @click=${(e) => {
        e.preventDefault();
        card._onCreateNew();
      }}>${card._t("create_new")}</a>
    </div>
  `;
}

export function renderConfigSections(card) {
  const c = card._config;
  const calibrating = card._isCalibrating();
  const disabled = card._saving || calibrating;

  return html`
    <div class="entity-info">
      <div class="entity-info-row">
        <div>
          <strong>
            ${card._getEntityState()?.attributes?.friendly_name ||
            card._selectedEntity}
          </strong>
          <span class="entity-id">${card._selectedEntity}</span>
        </div>
      </div>
    </div>

    <div class="tabs">
      <button
        class="tab ${card._activeTab === "device" ? "active" : ""}"
        @click=${() => { card._activeTab = "device"; }}
      >${card._t("tabs.device")}</button>
      <button
        class="tab ${card._activeTab === "timing" ? "active" : ""}"
        ?disabled=${!card._hasRequiredEntities(c)}
        @click=${() => { card._activeTab = "timing"; }}
      >${card._t("tabs.calibration")}</button>
    </div>

    ${card._activeTab === "device"
      ? html`
          <fieldset ?disabled=${disabled}>
            ${renderControlMode(card, c)} ${renderInputEntities(card, c)}
            ${renderTiltSupport(card, c)}
            ${renderTiltMotorSection(card, c)}
          </fieldset>
        `
      : html`
          ${calibrating ? "" : renderPositionReset(card)}
          ${renderCalibration(card, calibrating)}
          ${renderTimingTable(card, c)}
        `}

    ${card._saving
      ? html`<div class="save-bar"><span class="saving-indicator">${card._t("saving")}</span></div>`
      : ""}
    ${card._saveError
      ? html`<div class="save-bar"><span class="save-error">${card._t("save_failed")}</span></div>`
      : ""}
  `;
}

export function renderControlMode(card, c) {
  const mode = c.control_mode || "switch";
  const showPulseTime = showsPulseTime(mode);

  return html`
    <div class="section">
      <div class="field-label">${card._t("control_mode.label")}</div>
      <select class="ha-select" @change=${card._onControlModeChange}>
        <option value="wrapped" ?selected=${mode === "wrapped"}>
          ${card._t("control_mode.wrapped")}
        </option>
        <option value="switch" ?selected=${mode === "switch"}>
          ${card._t("control_mode.switch")}
        </option>
        <option value="pulse" ?selected=${mode === "pulse"}>
          ${card._t("control_mode.pulse")}
        </option>
        <option value="toggle" ?selected=${mode === "toggle"}>
          ${card._t("control_mode.toggle")}
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
                label: card._t("control_mode.pulse_time"),
                value: String(c.pulse_time || 1.0),
                onChange: card._onPulseTimeChange,
              })}
            </div>
          `
        : ""}
    </div>
  `;
}

export function renderToggleWithHelp(card, labelKey, helperKey, checked, onChange) {
  const open = card._openHelp === helperKey;
  return html`
    <div class="toggle-with-help">
      <span class="toggle-label">${card._t(labelKey)}</span>
      <span class="help-anchor">
        <ha-icon
          class="help-icon"
          icon="mdi:help-circle-outline"
          role="button"
          tabindex="0"
          aria-label=${card._t("more_info")}
          aria-expanded=${open ? "true" : "false"}
          @click=${(e) => {
            e.stopPropagation();
            card._toggleHelp(helperKey);
          }}
          @keydown=${(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              card._toggleHelp(helperKey);
            } else if (e.key === "Escape") {
              card._closeHelp();
            }
          }}
        ></ha-icon>
        ${open
          ? html`<div class="info-popover" role="tooltip">
              ${card._t(helperKey)}
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

export function renderInputEntities(card, c) {
  if (c.control_mode === "wrapped") {
    return html`
      <div class="section">
        <ha-entity-picker
          .hass=${card.hass}
          .value=${c.cover_entity_id || ""}
          .includeDomains=${["cover"]}
          .entityFilter=${card._filterNonTimeBased}
          label=${card._t("entities.cover_entity")}
          @value-changed=${card._onCoverEntityChange}
        ></ha-entity-picker>
        ${renderToggleWithHelp(
          card,
          "entities.ignore_reported_position",
          "entities.ignore_reported_position_helper",
          !!c.ignore_reported_position,
          (e) =>
            card._updateLocal({ ignore_reported_position: e.target.checked }),
        )}
        ${renderToggleWithHelp(
          card,
          "entities.force_time_based_position",
          "entities.force_time_based_position_helper",
          !!c.force_time_based_position,
          (e) =>
            card._updateLocal({ force_time_based_position: e.target.checked }),
        )}
        ${renderToggleWithHelp(
          card,
          "assumed_state.label",
          "assumed_state.helper",
          c.assumed_state !== false,
          (e) => card._updateLocal({ assumed_state: e.target.checked }),
        )}
      </div>
    `;
  }

  return html`
    <div class="section">
      <div class="field-label">${card._switchLabel("entities.switch_entities", c.control_mode)}</div>
      <div class="entity-grid">
        <ha-entity-picker
          .hass=${card.hass}
          .value=${c.open_switch_entity_id || ""}
          .includeDomains=${switchPickerDomains(c.control_mode)}
          label=${card._switchLabel("entities.open_switch", c.control_mode)}
          @value-changed=${(e) =>
            card._onSwitchEntityChange("open_switch_entity_id", e)}
        ></ha-entity-picker>
        <ha-entity-picker
          .hass=${card.hass}
          .value=${c.close_switch_entity_id || ""}
          .includeDomains=${switchPickerDomains(c.control_mode)}
          label=${card._switchLabel("entities.close_switch", c.control_mode)}
          @value-changed=${(e) =>
            card._onSwitchEntityChange("close_switch_entity_id", e)}
        ></ha-entity-picker>
        ${c.control_mode === "pulse" ? html`
        <ha-entity-picker
          .hass=${card.hass}
          .value=${c.stop_switch_entity_id || ""}
          .includeDomains=${switchPickerDomains(c.control_mode)}
          label=${card._switchLabel("entities.stop_switch", c.control_mode)}
          @value-changed=${(e) =>
            card._onSwitchEntityChange("stop_switch_entity_id", e)}
        ></ha-entity-picker>
        ` : ""}
      </div>
      ${renderToggleWithHelp(
        card,
        "assumed_state.label",
        "assumed_state.helper",
        c.assumed_state !== false,
        (e) => card._updateLocal({ assumed_state: e.target.checked }),
      )}
    </div>
  `;
}

export function renderTiltSupport(card, c) {
  const tiltMode = c.tilt_mode || "none";

  // Dual-motor tilt on a wrapped cover delegates the tilt commands to the
  // underlying entity, so it requires that cover to support tilt natively.
  // Inline and sequential modes drive the main open/close motor, so they
  // work on any wrapped cover and stay available regardless.
  const allowDualMotor =
    c.control_mode !== "wrapped" ||
    card._coverSupportsNativeTilt(c.cover_entity_id);
  // The handlers reset dual_motor when it stops being backable, so in normal
  // UI flow allowDualMotor already covers it. Keep showing it when it is the
  // stored mode as a safety net for hand-edited configs or a wrapped cover
  // that is momentarily unavailable (features read as 0) — otherwise the
  // select would have a selected value missing from its options.
  const showDualMotor = allowDualMotor || tiltMode === "dual_motor";

  return html`
    <div class="section">
      <div class="field-label">${card._t("tilt.label")}</div>
      <select class="ha-select" @change=${card._onTiltModeChange}>
        <option value="none" ?selected=${tiltMode === "none"}>
          ${card._t("tilt.none")}
        </option>
        <option value="sequential_close" ?selected=${tiltMode === "sequential_close"}>
          ${card._t("tilt.sequential_close")}
        </option>
        <option value="sequential_open" ?selected=${tiltMode === "sequential_open"}>
          ${card._t("tilt.sequential_open")}
        </option>
        ${showDualMotor
          ? html`
              <option value="dual_motor" ?selected=${tiltMode === "dual_motor"}>
                ${card._t("tilt.dual_motor")}
              </option>
            `
          : ""}
        <option value="inline" ?selected=${tiltMode === "inline"}>
          ${card._t("tilt.inline")}
        </option>
      </select>
      ${tiltMode === "sequential_close" || tiltMode === "dual_motor"
        ? html`
            <div class="inline-field">
              <ha-formfield .label=${card._t("tilt.close_includes_tilt")}>
                <ha-switch
                  .checked=${c.close_includes_tilt !== false}
                  @change=${(e) =>
                    card._updateLocal({ close_includes_tilt: e.target.checked })}
                ></ha-switch>
              </ha-formfield>
            </div>
          `
        : ""}
    </div>
  `;
}

export function renderTiltMotorSection(card, c) {
  if (c.tilt_mode !== "dual_motor") return "";

  return html`
    <div class="section">
      <div class="field-label">${card._switchLabel("tilt_motor.label", c.control_mode)}</div>
      ${c.control_mode !== "wrapped" ? html`
      <div class="entity-grid">
        <ha-entity-picker
          .hass=${card.hass}
          .value=${c.tilt_open_switch || ""}
          .includeDomains=${switchPickerDomains(c.control_mode)}
          label=${card._switchLabel("tilt_motor.open_switch", c.control_mode)}
          @value-changed=${(e) =>
            card._onSwitchEntityChange("tilt_open_switch", e)}
        ></ha-entity-picker>
        <ha-entity-picker
          .hass=${card.hass}
          .value=${c.tilt_close_switch || ""}
          .includeDomains=${switchPickerDomains(c.control_mode)}
          label=${card._switchLabel("tilt_motor.close_switch", c.control_mode)}
          @value-changed=${(e) =>
            card._onSwitchEntityChange("tilt_close_switch", e)}
        ></ha-entity-picker>
        ${c.control_mode === "pulse" ? html`
        <ha-entity-picker
          .hass=${card.hass}
          .value=${c.tilt_stop_switch || ""}
          .includeDomains=${switchPickerDomains(c.control_mode)}
          label=${card._switchLabel("tilt_motor.stop_switch", c.control_mode)}
          @value-changed=${(e) =>
            card._onSwitchEntityChange("tilt_stop_switch", e)}
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
          label: card._t("tilt_motor.safe_position"),
          hint: card._t("tilt_motor.safe_position_helper"),
          value: String(c.safe_tilt_position ?? 100),
          onChange: (e) => {
            const v = parseInt(e.target.value);
            if (!isNaN(v) && v >= 0 && v <= 100) {
              card._updateLocal({ safe_tilt_position: v });
            }
          },
        })}
        ${renderTextfield({
          type: "number",
          min: "0",
          max: "100",
          step: "1",
          label: card._t("tilt_motor.max_allowed_position"),
          hint: card._t("tilt_motor.max_allowed_helper"),
          value:
            c.max_tilt_allowed_position != null
              ? String(c.max_tilt_allowed_position)
              : "",
          onChange: (e) => {
            const v = e.target.value.trim();
            card._updateLocal({
              max_tilt_allowed_position: v === "" ? null : parseInt(v),
            });
          },
        })}
      </div>
    </div>
  `;
}

export function renderTimingRow(card, [labelKey, key, value, min = 0]) {
  return html`
    <tr>
      <td>${card._t(labelKey)}</td>
      <td class="value-cell">
        <input
          type="number"
          class="timing-input"
          .value=${value != null ? String(value) : ""}
          placeholder=${card._t("timing.not_set")}
          step="0.1"
          min="${min}"
          max="600"
          @change=${(e) => {
            const v = e.target.value.trim();
            card._updateLocal({ [key]: v === "" ? null : parseFloat(v) });
          }}
        /><span class="unit">s</span>
      </td>
    </tr>
  `;
}

export function renderTimingTable(card, c) {
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
            <th>${card._t("timing.travel_attribute_header")}</th>
            <th>${card._t("timing.value_header")}</th>
          </tr>
        </thead>
        <tbody>
          ${travelRows.map((row) => renderTimingRow(card, row))}
        </tbody>
      </table>
      ${hasTiltTimes ? html`
      <table class="timing-table" style="margin-top: 8px;">
        <thead>
          <tr>
            <th>${card._t("timing.tilt_attribute_header")}</th>
            <th>${card._t("timing.value_header")}</th>
          </tr>
        </thead>
        <tbody>
          ${tiltRows.map((row) => renderTimingRow(card, row))}
        </tbody>
      </table>
      ` : ""}
    </div>
  `;
}

export function renderPositionReset(card) {
  const tiltMode = card._config?.tilt_mode || "none";
  const hasIndependentTilt = tiltMode === "sequential_close" || tiltMode === "sequential_open" || tiltMode === "dual_motor" || tiltMode === "inline";

  return html`
    <div class="section">
      <div class="field-label">${card._t("position.label")}</div>
      <div class="helper-text">
        ${card._t("position.helper")}
      </div>
      ${!card._hasTiltMotor() ? html`
        <div class="cover-controls">
          <ha-button title=${card._t("controls.open")} @click=${() => card._onCoverCommand("open_cover")}>
            <ha-icon icon="mdi:window-shutter-open" style="--mdc-icon-size: 18px;"></ha-icon>
          </ha-button>
          <ha-button title=${card._t("controls.stop")} @click=${() => card._onCoverCommand("stop_cover")}>
            <ha-icon icon="mdi:stop" style="--mdc-icon-size: 18px;"></ha-icon>
          </ha-button>
          <ha-button title=${card._t("controls.close")} @click=${() => card._onCoverCommand("close_cover")}>
            <ha-icon icon="mdi:window-shutter" style="--mdc-icon-size: 18px;"></ha-icon>
          </ha-button>
        </div>
      ` : html`
        <div class="cover-controls-wrapper">
          <div class="cover-controls">
            <span class="controls-label">${card._t("controls.cover_label")}</span>
            <ha-button title=${card._t("controls.open")} @click=${() => card._onCoverCommand("open_cover")}>
              <ha-icon icon="mdi:window-shutter-open" style="--mdc-icon-size: 18px;"></ha-icon>
            </ha-button>
            <ha-button title=${card._t("controls.stop")} @click=${() => card._onCoverCommand("stop_cover")}>
              <ha-icon icon="mdi:stop" style="--mdc-icon-size: 18px;"></ha-icon>
            </ha-button>
            <ha-button title=${card._t("controls.close")} @click=${() => card._onCoverCommand("close_cover")}>
              <ha-icon icon="mdi:window-shutter" style="--mdc-icon-size: 18px;"></ha-icon>
            </ha-button>
          </div>
          <div class="cover-controls">
            <span class="controls-label">${card._t("controls.tilt_label")}</span>
            <ha-button title=${card._t("controls.tilt_open")} @click=${() => card._onCoverCommand("tilt_open")}>
              <ha-icon icon="mdi:arrow-top-right" style="--mdc-icon-size: 18px;"></ha-icon>
            </ha-button>
            <ha-button title=${card._t("controls.tilt_stop")} @click=${() => card._onCoverCommand("tilt_stop")}>
              <ha-icon icon="mdi:stop" style="--mdc-icon-size: 18px;"></ha-icon>
            </ha-button>
            <ha-button title=${card._t("controls.tilt_close")} @click=${() => card._onCoverCommand("tilt_close")}>
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
            @change=${(e) => card._onPositionPresetChange(e.target.value)}
          >
            <option value="unknown" ?selected=${card._knownPosition === "unknown"}>${card._t("position.unknown")}</option>
            <option value="open" ?selected=${card._knownPosition === "open"}>${card._t("position.open")}</option>
            ${hasIndependentTilt
              ? html`
                  <option value="closed_tilt_open" ?selected=${card._knownPosition === "closed_tilt_open"}>${card._t("position.closed_tilt_open")}</option>
                  <option value="closed_tilt_closed" ?selected=${card._knownPosition === "closed_tilt_closed"}>${card._t("position.closed_tilt_closed")}</option>
                `
              : html`
                  <option value="closed" ?selected=${card._knownPosition === "closed"}>${card._t("position.closed")}</option>
                `}
          </select>
        </div>
      </div>
    </div>
  `;
}

export function renderCalibration(card, calibrating) {
  const state = card._getEntityState();
  const attrs = state?.attributes || {};
  const tiltMode = card._config?.tilt_mode || "none";
  const hasTiltCalibration = tiltMode === "sequential_close" || tiltMode === "sequential_open" || tiltMode === "dual_motor" || tiltMode === "inline";

  const availableAttributes = TIMING_ATTRIBUTES.filter(
    ([key]) => {
      if (!hasTiltCalibration && key.startsWith("tilt_")) return false;
      return true;
    }
  );

  const c = card._config;
  const hasTravel = c?.travel_time_close || c?.travel_time_open;
  const hasTilt = c?.tilt_time_close || c?.tilt_time_open;

  const disabledKeys = new Set();
  if (card._knownPosition === "unknown") {
    availableAttributes.forEach(([key]) => disabledKeys.add(key));
  } else if (card._knownPosition === "open") {
    disabledKeys.add("travel_time_open");
    disabledKeys.add("tilt_time_open");
    if (hasTiltCalibration) {
      // Tilt only changes when cover is closed — can't test from open
      disabledKeys.add("tilt_time_close");
      disabledKeys.add("tilt_startup_delay");
    }
  } else if (card._knownPosition === "closed") {
    // Position closed (tilt matches)
    disabledKeys.add("travel_time_close");
    disabledKeys.add("tilt_time_close");
  } else if (card._knownPosition === "closed_tilt_open") {
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
  } else if (card._knownPosition === "closed_tilt_closed") {
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
    const calAttr = attrs.calibration_attribute || card._calibratingAttribute;
    const calLabel = card._t(`timing.${calAttr}`);
    return html`
      <div class="section calibration-active">
        <div class="field-label cal-label">
          <ha-icon icon="mdi:tune" style="--mdc-icon-size: 20px;"></ha-icon>
          ${card._t("calibration.active")}
        </div>
        <div class="cal-active-body">
          <strong>${calLabel}</strong>
          ${attrs.calibration_final_step
            ? html`<span class="cal-step"
                >${card._t("calibration.final_step")}</span
              >`
            : attrs.calibration_step
              ? html`<span class="cal-step"
                  >${card._t("calibration.step", { step: attrs.calibration_step })}</span
                >`
              : ""}
          <div class="cal-active-buttons">
            <ha-button @click=${() => card._onStopCalibration(true)}
              >${card._t("calibration.cancel")}</ha-button
            >
            <ha-button unelevated @click=${() => card._onStopCalibration(false)}
              >${card._t("calibration.finish")}</ha-button
            >
          </div>
        </div>
      </div>
    `;
  }

  return html`
    <div class="section">
      <div class="field-label">${card._t("calibration.label")}</div>
      <div class="cal-form">
        <div class="cal-field">
          <label class="sub-label" for="cal-attribute">${card._t("calibration.attribute_label")}</label>
          <select class="ha-select" id="cal-attribute"
            @change=${() => card.requestUpdate()}
          >
            ${availableAttributes.map(
              ([key, labelKey]) =>
                html`<option value=${key} ?disabled=${disabledKeys.has(key)}>${card._t(labelKey)}</option>`
            )}
          </select>
        </div>
        <ha-button unelevated ?disabled=${card._knownPosition === "unknown"} @click=${card._onStartCalibration}
          >${card._t("calibration.start")}</ha-button
        >
      </div>
      ${card._knownPosition === "unknown"
        ? html`<div class="helper-text" style="margin-top: 8px;">
            ${card._t("calibration.set_position_first")}
          </div>`
        : html`<div class="helper-text" style="margin-top: 8px;">
            ${card._getCalibrationHint()}
          </div>`}
    </div>
  `;
}
