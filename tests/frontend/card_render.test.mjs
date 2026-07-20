/**
 * Characterization tests for cover-time-based-card.js render methods.
 *
 * These tests LOCK IN the card's current render output. The 4 source files
 * under custom_components/cover_time_based/frontend/ are off-limits for edits.
 *
 * Run: npm run test:fe -- tests/frontend/card_render.test.mjs
 */

import { test, expect, afterEach, vi } from "vitest";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard, defineHaStubs } from "./helpers/mount.mjs";

defineHaStubs();
let card;
afterEach(() => {
  vi.restoreAllMocks();
  card?.remove();
  card = null;
});

// ---------------------------------------------------------------------------
// Config factory helpers
// ---------------------------------------------------------------------------

const switchCfg = (over = {}) => ({
  control_mode: "switch",
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  ...over,
});

const pulseCfg = (over = {}) => ({
  control_mode: "pulse",
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  stop_switch_entity_id: "switch.s",
  ...over,
});

const toggleCfg = (over = {}) => ({
  control_mode: "toggle",
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  ...over,
});

const toggleOppositeCfg = (over = {}) => ({
  control_mode: "toggle_opposite",
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  ...over,
});

const wrappedCfg = (over = {}) => ({
  control_mode: "wrapped",
  cover_entity_id: "cover.real",
  ...over,
});

// ---------------------------------------------------------------------------
// render() — top-level
// ---------------------------------------------------------------------------

test("render() returns empty when hass is null", async () => {
  card = document.createElement("cover-time-based-card");
  document.body.appendChild(card);
  await card.updateComplete;
  // No ha-card rendered when hass is absent
  expect(card.shadowRoot.querySelector("ha-card")).toBeNull();
});

test("render() with hass renders ha-card + .card-header with the header text", async () => {
  card = await mountCard(makeHass());
  const haCard = card.shadowRoot.querySelector("ha-card");
  expect(haCard).not.toBeNull();
  const header = card.shadowRoot.querySelector(".card-header");
  expect(header).not.toBeNull();
  expect(header.textContent.trim()).toBe("Cover Time Based Configuration");
});

test("render() _loadError renders .yaml-warning div", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg() });
  card._loadError = "uses YAML";
  card.requestUpdate();
  await card.updateComplete;
  const warning = card.shadowRoot.querySelector(".yaml-warning");
  expect(warning).not.toBeNull();
  expect(warning.textContent).toContain("uses YAML");
});

test("render() _loading renders .loading div with ha-icon", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x" });
  card._loading = true;
  card.requestUpdate();
  await card.updateComplete;
  const loading = card.shadowRoot.querySelector(".loading");
  expect(loading).not.toBeNull();
  expect(loading.querySelector("ha-icon")).not.toBeNull();
});

test("render() _openHelp renders .popover-backdrop div", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg() });
  card._openHelp = "assumed_state.helper";
  card.requestUpdate();
  await card.updateComplete;
  expect(card.shadowRoot.querySelector(".popover-backdrop")).not.toBeNull();
});

test("render() without _openHelp has no .popover-backdrop", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg() });
  expect(card.shadowRoot.querySelector(".popover-backdrop")).toBeNull();
});

// ---------------------------------------------------------------------------
// _renderEntityPicker
// ---------------------------------------------------------------------------

test("_renderEntityPicker always renders ha-entity-picker + .create-new-link", async () => {
  card = await mountCard(makeHass());
  expect(card.shadowRoot.querySelector("ha-entity-picker")).not.toBeNull();
  expect(card.shadowRoot.querySelector(".create-new-link")).not.toBeNull();
});

test("with no entity selected, .tabs is absent (no config sections)", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "" });
  expect(card.shadowRoot.querySelector("ha-entity-picker")).not.toBeNull();
  expect(card.shadowRoot.querySelector(".tabs")).toBeNull();
});

test("with entity + config, config sections (.tabs) are rendered", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  expect(card.shadowRoot.querySelector(".tabs")).not.toBeNull();
});

test("with entity but null config, .tabs is absent", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: null });
  expect(card.shadowRoot.querySelector(".tabs")).toBeNull();
});

// ---------------------------------------------------------------------------
// _renderConfigSections — tabs / save bar / entity info
// ---------------------------------------------------------------------------

test("_renderConfigSections renders device tab as active by default", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg() });
  const tabs = card.shadowRoot.querySelectorAll(".tab");
  expect(tabs.length).toBe(2);
  // First tab = "Device", has 'active' class
  expect(tabs[0].classList.contains("active")).toBe(true);
  expect(tabs[1].classList.contains("active")).toBe(false);
});

test("_renderConfigSections with activeTab=timing shows timing tab as active", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "timing" });
  const tabs = card.shadowRoot.querySelectorAll(".tab");
  expect(tabs[0].classList.contains("active")).toBe(false);
  expect(tabs[1].classList.contains("active")).toBe(true);
});

test("calibration tab is disabled when required entities are missing", async () => {
  // wrapped config without cover_entity_id → _hasRequiredEntities = false
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: { control_mode: "wrapped" }, // missing cover_entity_id
    activeTab: "device",
  });
  const tabs = card.shadowRoot.querySelectorAll(".tab");
  // Second tab = Calibration, should be disabled
  expect(tabs[1].disabled).toBe(true);
});

test("calibration tab is NOT disabled when required entities are present", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  const tabs = card.shadowRoot.querySelectorAll(".tab");
  expect(tabs[1].disabled).toBe(false);
});

test("_saving=true renders .save-bar with .saving-indicator", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  card._saving = true;
  card.requestUpdate();
  await card.updateComplete;
  const saveBar = card.shadowRoot.querySelector(".save-bar");
  expect(saveBar).not.toBeNull();
  expect(saveBar.querySelector(".saving-indicator")).not.toBeNull();
  expect(saveBar.textContent).toContain("Saving");
});

test("_saveError=true renders .save-bar with .save-error", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  card._saveError = true;
  card.requestUpdate();
  await card.updateComplete;
  const saveBar = card.shadowRoot.querySelector(".save-bar");
  expect(saveBar).not.toBeNull();
  expect(saveBar.querySelector(".save-error")).not.toBeNull();
  expect(saveBar.textContent).toContain("Save failed");
});

test("no save-bar when neither _saving nor _saveError", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  expect(card.shadowRoot.querySelector(".save-bar")).toBeNull();
});

test("device tab renders a fieldset, timing tab does not", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  expect(card.shadowRoot.querySelector("fieldset")).not.toBeNull();

  card.remove();
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "timing" });
  expect(card.shadowRoot.querySelector("fieldset")).toBeNull();
});

test("entity info row shows the selectedEntity string", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.my_cover", config: switchCfg() });
  const entityId = card.shadowRoot.querySelector(".entity-id");
  expect(entityId).not.toBeNull();
  expect(entityId.textContent.trim()).toBe("cover.my_cover");
});

// ---------------------------------------------------------------------------
// _renderControlMode — four option values; pulse-time field
// ---------------------------------------------------------------------------

test("control mode select has five options: wrapped/switch/pulse/toggle/toggle_opposite", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  const select = card.shadowRoot.querySelector("select.ha-select");
  expect(select).not.toBeNull();
  const values = [...select.options].map((o) => o.value);
  expect(values).toEqual(["wrapped", "switch", "pulse", "toggle", "toggle_opposite"]);
});

// Note: happy-dom does not sync the `selected` HTML attribute to the native
// select `.selected` property correctly when set via Lit's ?selected binding.
// We therefore assert on hasAttribute("selected") — the attribute Lit writes —
// not on opt.selected (the DOM property the native select manages internally).

test("switch mode: 'switch' option has the selected attribute", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  const select = card.shadowRoot.querySelector("select.ha-select");
  const selectedOpt = [...select.options].find((o) => o.hasAttribute("selected"));
  expect(selectedOpt?.value).toBe("switch");
});

test("pulse mode: 'pulse' option has the selected attribute", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: pulseCfg(), activeTab: "device" });
  const select = card.shadowRoot.querySelector("select.ha-select");
  const selectedOpt = [...select.options].find((o) => o.hasAttribute("selected"));
  expect(selectedOpt?.value).toBe("pulse");
});

test("toggle mode: 'toggle' option has the selected attribute", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: toggleCfg(), activeTab: "device" });
  const select = card.shadowRoot.querySelector("select.ha-select");
  const selectedOpt = [...select.options].find((o) => o.hasAttribute("selected"));
  expect(selectedOpt?.value).toBe("toggle");
});

test("toggle_opposite mode: its option has the selected attribute", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: toggleOppositeCfg(), activeTab: "device" });
  const select = card.shadowRoot.querySelector("select.ha-select");
  const selectedOpt = [...select.options].find((o) => o.hasAttribute("selected"));
  expect(selectedOpt?.value).toBe("toggle_opposite");
});

test("toggle_opposite mode shows the relay_reports_off toggle", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: toggleOppositeCfg(), activeTab: "device" });
  const labels = [...card.shadowRoot.querySelectorAll(".toggle-label")].map((n) => n.textContent);
  // The relay_reports_off toggle label is present (same as toggle mode).
  expect(labels.some((t) => /report/i.test(t))).toBe(true);
});

test("wrapped mode: 'wrapped' option has the selected attribute", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: wrappedCfg(), activeTab: "device" });
  const select = card.shadowRoot.querySelector("select.ha-select");
  const selectedOpt = [...select.options].find((o) => o.hasAttribute("selected"));
  expect(selectedOpt?.value).toBe("wrapped");
});

test("pulse mode renders .inline-field (pulse-time) in control mode section", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: pulseCfg({ pulse_time: 1.5 }),
    activeTab: "device",
  });
  expect(card.shadowRoot.querySelector(".inline-field")).not.toBeNull();
});

test("switch mode has no .inline-field (pulse-time absent)", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  expect(card.shadowRoot.querySelector(".inline-field")).toBeNull();
});

test("toggle mode has no .inline-field", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: toggleCfg(), activeTab: "device" });
  expect(card.shadowRoot.querySelector(".inline-field")).toBeNull();
});

// ---------------------------------------------------------------------------
// _renderToggleWithHelp — popover open vs closed
// ---------------------------------------------------------------------------

test("_renderToggleWithHelp: .info-popover absent when _openHelp is null", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  expect(card._openHelp).toBeNull();
  expect(card.shadowRoot.querySelector(".info-popover")).toBeNull();
});

test("_renderToggleWithHelp: .info-popover present when _openHelp matches the helper key", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  card._openHelp = "assumed_state.helper";
  card.requestUpdate();
  await card.updateComplete;
  expect(card.shadowRoot.querySelector(".info-popover")).not.toBeNull();
});

test("_renderToggleWithHelp: .info-popover absent when _openHelp is a different key", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  card._openHelp = "some.other.key";
  card.requestUpdate();
  await card.updateComplete;
  // "some.other.key" is not used in the rendered toggle-with-help helpers for switch mode
  expect(card.shadowRoot.querySelector(".info-popover")).toBeNull();
});

test("wrapped mode: _openHelp=ignore_reported_position_helper shows the popover", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: wrappedCfg(), activeTab: "device" });
  card._openHelp = "entities.ignore_reported_position_helper";
  card.requestUpdate();
  await card.updateComplete;
  expect(card.shadowRoot.querySelector(".info-popover")).not.toBeNull();
});

// ---------------------------------------------------------------------------
// _renderInputEntities — mode-specific pickers
// ---------------------------------------------------------------------------

test("wrapped mode renders cover entity-picker (with includeDomains cover)", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: wrappedCfg(), activeTab: "device" });
  const pickers = card.shadowRoot.querySelectorAll("ha-entity-picker");
  // Exactly: top entity-picker + cover entity picker
  expect(pickers.length).toBe(2);
  // At least one picker has includeDomains containing "cover" (check property)
  const coverPicker = [...pickers].find((p) => {
    const domains = p.includeDomains;
    return Array.isArray(domains) && domains.includes("cover");
  });
  expect(coverPicker).not.toBeUndefined();
});

test("wrapped mode renders ha-switch toggles (ignore-reported-position, force-time-based, reports-command-not-endpoint, invert, assumed-state, force-endpoint-redrive)", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: wrappedCfg(), activeTab: "device" });
  const toggles = card.shadowRoot.querySelectorAll("ha-switch.toggle-switch");
  // Exactly 6 toggles: ignore_reported_position, force_time_based_position,
  // reports_command_not_endpoint, invert, assumed_state, force_endpoint_redrive
  expect(toggles.length).toBe(6);
});

test("wrapped mode: toggling reports-command-not-endpoint calls _updateLocal", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: wrappedCfg(), activeTab: "device" });
  const captured = [];
  card._updateLocal = (u) => captured.push(u);
  // Order in renderInputEntities: [0] ignore_reported_position,
  // [1] force_time_based_position, [2] reports_command_not_endpoint, [3] invert,
  // [4] assumed_state, [5] force_endpoint_redrive
  const toggle = card.shadowRoot.querySelectorAll("ha-switch.toggle-switch")[2];
  toggle.checked = true;
  toggle.dispatchEvent(new Event("change"));
  expect(captured).toContainEqual({ reports_command_not_endpoint: true });
});

test("wrapped mode: _openHelp=reports_command_not_endpoint_helper shows the popover", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: wrappedCfg(), activeTab: "device" });
  card._openHelp = "entities.reports_command_not_endpoint_helper";
  card.requestUpdate();
  await card.updateComplete;
  expect(card.shadowRoot.querySelector(".info-popover")).not.toBeNull();
});

test("switch mode renders open + close switch pickers (no stop switch)", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  const pickers = card.shadowRoot.querySelectorAll("ha-entity-picker");
  // top picker + open switch + close switch = 3
  expect(pickers.length).toBe(3);
});

test("pulse mode renders open + close + stop switch pickers (3 extra + top picker = 4)", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: pulseCfg(), activeTab: "device" });
  const pickers = card.shadowRoot.querySelectorAll("ha-entity-picker");
  // top picker + open + close + stop = 4
  expect(pickers.length).toBe(4);
});

test("toggle mode renders open + close switch pickers (no stop switch)", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: toggleCfg(), activeTab: "device" });
  const pickers = card.shadowRoot.querySelectorAll("ha-entity-picker");
  // top picker + open + close = 3
  expect(pickers.length).toBe(3);
});

test("switch mode renders .entity-grid div", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  expect(card.shadowRoot.querySelector(".entity-grid")).not.toBeNull();
});

test("wrapped mode has no .entity-grid", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: wrappedCfg(), activeTab: "device" });
  expect(card.shadowRoot.querySelector(".entity-grid")).toBeNull();
});

test("switch mode shows assumed-state toggle", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  const toggles = card.shadowRoot.querySelectorAll("ha-switch.toggle-switch");
  // Exactly 2 toggles: assumed-state and force-endpoint-redrive (switch mode has
  // no other toggle-with-help)
  expect(toggles.length).toBe(2);
});

// ---------------------------------------------------------------------------
// _renderTiltSupport — tilt mode options and inline-field toggle
// ---------------------------------------------------------------------------

test("tilt select always renders with at least 4 options (none/sequential_close/sequential_open/inline)", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  const selects = card.shadowRoot.querySelectorAll("select.ha-select");
  // First select = control_mode, second = tilt mode
  expect(selects.length).toBeGreaterThanOrEqual(2);
  const tiltSelect = selects[1];
  const values = [...tiltSelect.options].map((o) => o.value);
  expect(values).toContain("none");
  expect(values).toContain("sequential_close");
  expect(values).toContain("sequential_open");
  expect(values).toContain("inline");
});

test("tilt select shows dual_motor option for non-wrapped mode", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "device" });
  const selects = card.shadowRoot.querySelectorAll("select.ha-select");
  const tiltSelect = selects[1];
  const values = [...tiltSelect.options].map((o) => o.value);
  expect(values).toContain("dual_motor");
});

// Tilt option selection: use hasAttribute("selected") (Lit attribute) rather than
// .selected property (native select state), for the same happy-dom reason as above.

test("tilt mode none: 'none' option has the selected attribute", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg({ tilt_mode: "none" }), activeTab: "device" });
  const selects = card.shadowRoot.querySelectorAll("select.ha-select");
  const tiltSelect = selects[1];
  const selectedOpt = [...tiltSelect.options].find((o) => o.hasAttribute("selected"));
  expect(selectedOpt?.value).toBe("none");
});

test("tilt mode sequential_close: correct option selected; inline-field (close_includes_tilt) shown", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "sequential_close" }),
    activeTab: "device",
  });
  const selects = card.shadowRoot.querySelectorAll("select.ha-select");
  const tiltSelect = selects[1];
  const selectedOpt = [...tiltSelect.options].find((o) => o.hasAttribute("selected"));
  expect(selectedOpt?.value).toBe("sequential_close");
  // sequential_close shows the close_includes_tilt toggle in an inline-field
  expect(card.shadowRoot.querySelector(".inline-field")).not.toBeNull();
});

test("tilt mode sequential_open: correct option selected; no inline-field", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "sequential_open" }),
    activeTab: "device",
  });
  const selects = card.shadowRoot.querySelectorAll("select.ha-select");
  const tiltSelect = selects[1];
  const selectedOpt = [...tiltSelect.options].find((o) => o.hasAttribute("selected"));
  expect(selectedOpt?.value).toBe("sequential_open");
  // sequential_open does NOT show close_includes_tilt toggle
  expect(card.shadowRoot.querySelector(".inline-field")).toBeNull();
});

test("tilt mode dual_motor: correct option selected; inline-field shown", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "dual_motor" }),
    activeTab: "device",
  });
  const selects = card.shadowRoot.querySelectorAll("select.ha-select");
  const tiltSelect = selects[1];
  const selectedOpt = [...tiltSelect.options].find((o) => o.hasAttribute("selected"));
  expect(selectedOpt?.value).toBe("dual_motor");
  // dual_motor also shows close_includes_tilt
  expect(card.shadowRoot.querySelector(".inline-field")).not.toBeNull();
});

test("tilt mode inline: correct option selected; no inline-field", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "inline" }),
    activeTab: "device",
  });
  const selects = card.shadowRoot.querySelectorAll("select.ha-select");
  const tiltSelect = selects[1];
  const selectedOpt = [...tiltSelect.options].find((o) => o.hasAttribute("selected"));
  expect(selectedOpt?.value).toBe("inline");
  expect(card.shadowRoot.querySelector(".inline-field")).toBeNull();
});

// ---------------------------------------------------------------------------
// _renderTiltMotorSection — dual_motor shows extra section, others don't
// ---------------------------------------------------------------------------

test("tilt_mode=dual_motor renders .dual-motor-config section (switch mode)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "dual_motor" }),
    activeTab: "device",
  });
  expect(card.shadowRoot.querySelector(".dual-motor-config")).not.toBeNull();
});

test("tilt_mode=dual_motor renders tilt motor pickers for non-wrapped mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "dual_motor" }),
    activeTab: "device",
  });
  // Two entity-grids: one for the main switch entities, one for tilt motor entities
  const grids = card.shadowRoot.querySelectorAll(".entity-grid");
  expect(grids.length).toBe(2);
  // Should have more pickers: top + open + close + tilt_open + tilt_close = 5
  const pickers = card.shadowRoot.querySelectorAll("ha-entity-picker");
  expect(pickers.length).toBe(5);
});

test("tilt_mode=dual_motor + pulse renders tilt stop switch picker (6 pickers total)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: pulseCfg({ tilt_mode: "dual_motor" }),
    activeTab: "device",
  });
  // top + open + close + stop + tilt_open + tilt_close + tilt_stop = 7
  const pickers = card.shadowRoot.querySelectorAll("ha-entity-picker");
  expect(pickers.length).toBe(7);
});

test("tilt_mode=none has no .dual-motor-config", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg({ tilt_mode: "none" }), activeTab: "device" });
  expect(card.shadowRoot.querySelector(".dual-motor-config")).toBeNull();
});

test("tilt_mode=sequential_close has no .dual-motor-config", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg({ tilt_mode: "sequential_close" }), activeTab: "device" });
  expect(card.shadowRoot.querySelector(".dual-motor-config")).toBeNull();
});

test("tilt_mode=dual_motor + wrapped: shows .dual-motor-config but NO .entity-grid (no tilt switches needed)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ tilt_mode: "dual_motor" }),
    activeTab: "device",
  });
  expect(card.shadowRoot.querySelector(".dual-motor-config")).not.toBeNull();
  // Wrapped mode has no entity-grid in the tilt motor section
  expect(card.shadowRoot.querySelector(".entity-grid")).toBeNull();
});

// ---------------------------------------------------------------------------
// _renderTimingTable + _renderTimingRow
// ---------------------------------------------------------------------------

test("timing tab renders .timing-table", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "timing" });
  expect(card.shadowRoot.querySelector(".timing-table")).not.toBeNull();
});

test("switch mode timing table includes endpoint_runon_time row (5 travel rows: travel_time_close, travel_time_open, travel_startup_delay, min_movement_time, endpoint_runon_time)", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "timing" });
  const inputs = card.shadowRoot.querySelectorAll("input.timing-input");
  // switch mode: travel_time_close, travel_time_open, travel_startup_delay, min_movement_time, endpoint_runon_time
  expect(inputs.length).toBe(5);
});

test("pulse mode with send_endpoint_stop off timing table does NOT include endpoint_runon_time (5 travel rows)", async () => {
  // Pulse covers that send the endpoint stop (default) DO show the run-on row;
  // only when send_endpoint_stop is off does pulse self-stop at endpoints and
  // hide it. See send_endpoint_stop.test.mjs for the full gating matrix.
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: pulseCfg({ send_endpoint_stop: false }),
    activeTab: "timing",
  });
  const inputs = card.shadowRoot.querySelectorAll("input.timing-input");
  // pulse w/stop-off: travel_time_close, travel_time_open, travel_startup_delay, min_movement_time (no endpoint_runon)
  expect(inputs.length).toBe(4);
});

test("direction_change_delay row is gone, even for an entry that still stores it", async () => {
  // The settle gap is fixed at 1.0s and no longer user-configurable, so the
  // Timing tab must not offer it — including for a config entry written by a
  // 4.9.0 release candidate, whose options still carry the key. One case is
  // enough: the row was deleted from a static array that is not mode-gated,
  // and per-mode row counts are covered in send_endpoint_stop.test.mjs.
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ direction_change_delay: 3.5 }),
    activeTab: "timing",
  });
  const row = [...card.shadowRoot.querySelectorAll("tr")].find(
    (tr) => tr.querySelector("td")?.textContent.trim() === "Direction change delay",
  );
  expect(row).toBeUndefined();
});

test("timing row input has min attribute set (travel_time_close has min=0.1)", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "timing" });
  const inputs = card.shadowRoot.querySelectorAll("input.timing-input");
  // First input = travel_time_close, min should be "0.1"
  expect(inputs[0].getAttribute("min")).toBe("0.1");
});

test("timing row input shows existing value when config has travel_time_close", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ travel_time_close: 45 }),
    activeTab: "timing",
  });
  const inputs = card.shadowRoot.querySelectorAll("input.timing-input");
  expect(inputs[0].value).toBe("45");
});

test("timing table with tilt mode (inline) renders a second tilt timing table", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "inline" }),
    activeTab: "timing",
  });
  const tables = card.shadowRoot.querySelectorAll(".timing-table");
  // Travel table + tilt table
  expect(tables.length).toBe(2);
});

test("timing table without tilt mode renders only one timing table", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", config: switchCfg(), activeTab: "timing" });
  const tables = card.shadowRoot.querySelectorAll(".timing-table");
  expect(tables.length).toBe(1);
});

// ---------------------------------------------------------------------------
// _renderPositionReset — present on timing tab (not calibrating), absent while calibrating
// ---------------------------------------------------------------------------

test("timing tab (not calibrating) renders position section with #position-select", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
    knownPosition: "unknown",
  });
  expect(card.shadowRoot.querySelector("#position-select")).not.toBeNull();
});

test("position-select has 'Unknown' and 'Fully open' options without tilt", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "none" }),
    activeTab: "timing",
    knownPosition: "unknown",
  });
  const select = card.shadowRoot.querySelector("#position-select");
  const values = [...select.options].map((o) => o.value);
  expect(values).toContain("unknown");
  expect(values).toContain("open");
  expect(values).toContain("closed");
  // No tilt options
  expect(values).not.toContain("closed_tilt_open");
  expect(values).not.toContain("closed_tilt_closed");
});

test("position-select has tilt position options with sequential_close tilt mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "sequential_close" }),
    activeTab: "timing",
    knownPosition: "unknown",
  });
  const select = card.shadowRoot.querySelector("#position-select");
  const values = [...select.options].map((o) => o.value);
  expect(values).toContain("closed_tilt_open");
  expect(values).toContain("closed_tilt_closed");
  // No plain 'closed' option when tilt has independent positions
  expect(values).not.toContain("closed");
});

test("position-select 'open' option has selected attribute when knownPosition=open", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
    knownPosition: "open",
  });
  const select = card.shadowRoot.querySelector("#position-select");
  // Use hasAttribute('selected') since Lit's ?selected binding sets the attribute
  const selectedOpt = [...select.options].find((o) => o.hasAttribute("selected"));
  expect(selectedOpt?.value).toBe("open");
});

test("position reset shows simple cover controls (no tilt motor) when tilt_mode=none", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "none" }),
    activeTab: "timing",
  });
  // Simple controls: one .cover-controls div (not wrapped)
  const coverControls = card.shadowRoot.querySelectorAll(".cover-controls");
  expect(coverControls.length).toBe(1);
});

test("position reset shows cover + tilt controls when _hasTiltMotor() is true (dual_motor+switch)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({
      tilt_mode: "dual_motor",
      tilt_open_switch: "switch.to",
      tilt_close_switch: "switch.tc",
    }),
    activeTab: "timing",
  });
  // Tilt motor: .cover-controls-wrapper wraps two .cover-controls groups
  expect(card.shadowRoot.querySelector(".cover-controls-wrapper")).not.toBeNull();
  const coverControls = card.shadowRoot.querySelectorAll(".cover-controls");
  expect(coverControls.length).toBe(2);
});

test("position section absent while calibrating", async () => {
  card = await mountCard(makeHass({
    states: { "cover.x": { state: "open", attributes: { calibration_active: true } } },
  }), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
  });
  // _isCalibrating() returns true → _renderPositionReset is NOT called
  expect(card.shadowRoot.querySelector("#position-select")).toBeNull();
});

// ---------------------------------------------------------------------------
// _renderCalibration — calibrating vs not
// ---------------------------------------------------------------------------

test("not calibrating: calibration section shows #cal-attribute select + start button", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
    knownPosition: "open",
  });
  expect(card.shadowRoot.querySelector("#cal-attribute")).not.toBeNull();
  // Start button is rendered
  const haButtons = card.shadowRoot.querySelectorAll("ha-button");
  const startBtn = [...haButtons].find((b) => b.textContent.includes("Start"));
  expect(startBtn).not.toBeUndefined();
});

test("not calibrating: start button has disabled attribute when knownPosition=unknown", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
    knownPosition: "unknown",
  });
  const haButtons = card.shadowRoot.querySelectorAll("ha-button");
  const startBtn = [...haButtons].find((b) => b.textContent.includes("Start"));
  expect(startBtn).not.toBeUndefined();
  // Lit's ?disabled binding sets the attribute when true
  expect(startBtn.hasAttribute("disabled")).toBe(true);
});

test("not calibrating + knownPosition=open: start button does NOT have disabled attribute", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
    knownPosition: "open",
  });
  const haButtons = card.shadowRoot.querySelectorAll("ha-button");
  const startBtn = [...haButtons].find((b) => b.textContent.includes("Start"));
  expect(startBtn).not.toBeUndefined();
  expect(startBtn.hasAttribute("disabled")).toBe(false);
});

test("not calibrating: shows helper text 'set_position_first' when knownPosition=unknown", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
    knownPosition: "unknown",
  });
  // helper-text div should contain "Set position to start calibration"
  const helperTexts = card.shadowRoot.querySelectorAll(".helper-text");
  const setPositionText = [...helperTexts].find((el) =>
    el.textContent.includes("Set position")
  );
  expect(setPositionText).not.toBeUndefined();
});

test("not calibrating: cal-attribute select shows only non-tilt attributes when tilt_mode=none", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "none" }),
    activeTab: "timing",
  });
  const calSelect = card.shadowRoot.querySelector("#cal-attribute");
  expect(calSelect).not.toBeNull();
  const values = [...calSelect.options].map((o) => o.value);
  expect(values).not.toContain("tilt_time_close");
  expect(values).not.toContain("tilt_time_open");
  expect(values).not.toContain("tilt_startup_delay");
  expect(values).toContain("travel_time_close");
  expect(values).toContain("travel_time_open");
});

test("not calibrating: cal-attribute select shows tilt attributes when tilt_mode=dual_motor", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "dual_motor" }),
    activeTab: "timing",
  });
  const calSelect = card.shadowRoot.querySelector("#cal-attribute");
  const values = [...calSelect.options].map((o) => o.value);
  expect(values).toContain("tilt_time_close");
  expect(values).toContain("tilt_time_open");
  expect(values).toContain("tilt_startup_delay");
});

test("calibrating: shows .calibration-active section with Cancel + Finish buttons", async () => {
  card = await mountCard(makeHass({
    states: { "cover.x": { state: "open", attributes: { calibration_active: true, calibration_attribute: "travel_time_close" } } },
  }), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
  });
  const calActive = card.shadowRoot.querySelector(".calibration-active");
  expect(calActive).not.toBeNull();
  // Cancel + Finish buttons
  const haButtons = calActive.querySelectorAll("ha-button");
  const cancelBtn = [...haButtons].find((b) => b.textContent.includes("Cancel"));
  const finishBtn = [...haButtons].find((b) => b.textContent.includes("Finish"));
  expect(cancelBtn).not.toBeUndefined();
  expect(finishBtn).not.toBeUndefined();
});

test("calibrating: shows the calibrating attribute label", async () => {
  card = await mountCard(makeHass({
    states: { "cover.x": { state: "open", attributes: { calibration_active: true, calibration_attribute: "travel_time_close" } } },
  }), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
  });
  const calActive = card.shadowRoot.querySelector(".calibration-active");
  // The label "Travel time (close)" should appear in the calibration section body
  expect(calActive.textContent).toContain("Travel time");
});

test("calibrating: shows .cal-step for calibration_step attribute", async () => {
  card = await mountCard(makeHass({
    states: {
      "cover.x": {
        state: "open",
        attributes: { calibration_active: true, calibration_attribute: "travel_time_close", calibration_step: "2" },
      },
    },
  }), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
  });
  const calStep = card.shadowRoot.querySelector(".cal-step");
  expect(calStep).not.toBeNull();
  expect(calStep.textContent).toContain("Step 2");
});

test("calibrating: shows final_step span when calibration_final_step is truthy", async () => {
  card = await mountCard(makeHass({
    states: {
      "cover.x": {
        state: "open",
        attributes: { calibration_active: true, calibration_attribute: "travel_time_close", calibration_final_step: true },
      },
    },
  }), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
  });
  const calStep = card.shadowRoot.querySelector(".cal-step");
  expect(calStep).not.toBeNull();
  expect(calStep.textContent).toContain("Final step");
});

test("calibrating: no #cal-attribute select (start form is absent)", async () => {
  card = await mountCard(makeHass({
    states: { "cover.x": { state: "open", attributes: { calibration_active: true, calibration_attribute: "travel_time_close" } } },
  }), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
  });
  expect(card.shadowRoot.querySelector("#cal-attribute")).toBeNull();
});

test("calibrating via _calibratingOverride=true: shows calibration-active", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
  });
  card._calibratingOverride = true;
  card._calibratingAttribute = "travel_time_open";
  card.requestUpdate();
  await card.updateComplete;
  expect(card.shadowRoot.querySelector(".calibration-active")).not.toBeNull();
});

// ---------------------------------------------------------------------------
// Additional coverage: _renderConfigSections calibrating=true disables fieldset
// ---------------------------------------------------------------------------

test("device tab fieldset is disabled while calibrating", async () => {
  card = await mountCard(makeHass({
    states: { "cover.x": { state: "open", attributes: { calibration_active: true } } },
  }), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "device",
  });
  const fieldset = card.shadowRoot.querySelector("fieldset");
  expect(fieldset).not.toBeNull();
  expect(fieldset.disabled).toBe(true);
});

test("device tab fieldset is NOT disabled when not saving and not calibrating", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "device",
  });
  const fieldset = card.shadowRoot.querySelector("fieldset");
  expect(fieldset).not.toBeNull();
  expect(fieldset.disabled).toBe(false);
});

test("device tab fieldset is disabled while _saving=true", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "device",
  });
  card._saving = true;
  card.requestUpdate();
  await card.updateComplete;
  const fieldset = card.shadowRoot.querySelector("fieldset");
  expect(fieldset.disabled).toBe(true);
});

// ---------------------------------------------------------------------------
// _renderCalibration disabledKeys branches: knownPosition variants
// These cover lines 1517-1548 in the source.
// ---------------------------------------------------------------------------

test("cal-attribute options: knownPosition=open disables travel_time_open; sequential_close tilt disables tilt_time_close", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "sequential_close" }),
    activeTab: "timing",
    knownPosition: "open",
  });
  const calSelect = card.shadowRoot.querySelector("#cal-attribute");
  const opts = [...calSelect.options];
  const travelTimeOpenOpt = opts.find((o) => o.value === "travel_time_open");
  const tiltTimeCloseOpt = opts.find((o) => o.value === "tilt_time_close");
  expect(travelTimeOpenOpt?.hasAttribute("disabled")).toBe(true);
  expect(tiltTimeCloseOpt?.hasAttribute("disabled")).toBe(true);
});

test("cal-attribute options: knownPosition=open with tilt_mode=none does NOT disable tilt rows (they are absent)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "none" }),
    activeTab: "timing",
    knownPosition: "open",
  });
  const calSelect = card.shadowRoot.querySelector("#cal-attribute");
  const opts = [...calSelect.options];
  const values = opts.map((o) => o.value);
  // tilt options not present for tilt_mode=none
  expect(values).not.toContain("tilt_time_close");
  // travel_time_open is still disabled for open position
  const travelOpenOpt = opts.find((o) => o.value === "travel_time_open");
  expect(travelOpenOpt?.hasAttribute("disabled")).toBe(true);
});

test("cal-attribute options: knownPosition=closed disables travel_time_close", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "none" }),
    activeTab: "timing",
    knownPosition: "closed",
  });
  const calSelect = card.shadowRoot.querySelector("#cal-attribute");
  const opts = [...calSelect.options];
  const travelCloseOpt = opts.find((o) => o.value === "travel_time_close");
  expect(travelCloseOpt?.hasAttribute("disabled")).toBe(true);
  // travel_time_open should be enabled (not disabled)
  const travelOpenOpt = opts.find((o) => o.value === "travel_time_open");
  expect(travelOpenOpt?.hasAttribute("disabled")).toBe(false);
});

test("cal-attribute options: knownPosition=closed_tilt_open disables travel_time_close and tilt_time_open", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "sequential_close" }),
    activeTab: "timing",
    knownPosition: "closed_tilt_open",
  });
  const calSelect = card.shadowRoot.querySelector("#cal-attribute");
  const opts = [...calSelect.options];
  const travelCloseOpt = opts.find((o) => o.value === "travel_time_close");
  expect(travelCloseOpt?.hasAttribute("disabled")).toBe(true);
  const tiltTimeOpenOpt = opts.find((o) => o.value === "tilt_time_open");
  expect(tiltTimeOpenOpt?.hasAttribute("disabled")).toBe(true);
  // travel_time_open should be measurable (not disabled) for sequential_close
  const travelOpenOpt = opts.find((o) => o.value === "travel_time_open");
  expect(travelOpenOpt?.hasAttribute("disabled")).toBe(false);
});

test("cal-attribute options: knownPosition=closed_tilt_open with sequential_open additionally disables travel_time_open", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "sequential_open" }),
    activeTab: "timing",
    knownPosition: "closed_tilt_open",
  });
  const calSelect = card.shadowRoot.querySelector("#cal-attribute");
  const opts = [...calSelect.options];
  const travelOpenOpt = opts.find((o) => o.value === "travel_time_open");
  expect(travelOpenOpt?.hasAttribute("disabled")).toBe(true);
});

test("cal-attribute options: knownPosition=closed_tilt_closed disables travel_time_close and tilt_time_close", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "sequential_close" }),
    activeTab: "timing",
    knownPosition: "closed_tilt_closed",
  });
  const calSelect = card.shadowRoot.querySelector("#cal-attribute");
  const opts = [...calSelect.options];
  const travelCloseOpt = opts.find((o) => o.value === "travel_time_close");
  expect(travelCloseOpt?.hasAttribute("disabled")).toBe(true);
  const tiltTimeCloseOpt = opts.find((o) => o.value === "tilt_time_close");
  expect(tiltTimeCloseOpt?.hasAttribute("disabled")).toBe(true);
  // For sequential_close (not sequential_open), travel_time_open is also disabled
  const travelOpenOpt = opts.find((o) => o.value === "travel_time_open");
  expect(travelOpenOpt?.hasAttribute("disabled")).toBe(true);
});

test("cal-attribute options: knownPosition=closed_tilt_closed with sequential_open leaves travel_time_open enabled", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "sequential_open" }),
    activeTab: "timing",
    knownPosition: "closed_tilt_closed",
  });
  const calSelect = card.shadowRoot.querySelector("#cal-attribute");
  const opts = [...calSelect.options];
  // For sequential_open, travel_time_open is measurable from closed_tilt_closed
  const travelOpenOpt = opts.find((o) => o.value === "travel_time_open");
  expect(travelOpenOpt?.hasAttribute("disabled")).toBe(false);
});

// ---------------------------------------------------------------------------
// _renderTiltSupport — wrapped cover without native tilt omits dual_motor option
// ---------------------------------------------------------------------------

test("tilt select omits dual_motor option for wrapped mode when cover lacks native tilt bits", async () => {
  // cover.real has supported_features=3 (no OPEN_TILT=16 or CLOSE_TILT=32 bits)
  // and state="open" (available), so _coverSupportsNativeTilt returns false.
  const hass = makeHass({
    states: {
      "cover.real": { state: "open", attributes: { supported_features: 3 } },
    },
  });
  card = await mountCard(hass, {
    selectedEntity: "cover.x",
    config: wrappedCfg({ tilt_mode: "none" }),
    activeTab: "device",
  });
  const selects = card.shadowRoot.querySelectorAll("select.ha-select");
  const tiltSelect = selects[1];
  const values = [...tiltSelect.options].map((o) => o.value);
  // allowDualMotor is false (wrapped + cover has no tilt bits) → dual_motor absent
  expect(values).not.toContain("dual_motor");
  // Other options are still present
  expect(values).toContain("none");
  expect(values).toContain("sequential_close");
  expect(values).toContain("inline");
});

test("tilt select shows dual_motor for wrapped mode when cover HAS native tilt bits", async () => {
  // cover.real has OPEN_TILT=16 + CLOSE_TILT=32 → supported_features=48
  const hass = makeHass({
    states: {
      "cover.real": { state: "open", attributes: { supported_features: 48 } },
    },
  });
  card = await mountCard(hass, {
    selectedEntity: "cover.x",
    config: wrappedCfg({ tilt_mode: "none" }),
    activeTab: "device",
  });
  const selects = card.shadowRoot.querySelectorAll("select.ha-select");
  const tiltSelect = selects[1];
  const values = [...tiltSelect.options].map((o) => o.value);
  // allowDualMotor is true (wrapped + cover has tilt bits) → dual_motor present
  expect(values).toContain("dual_motor");
});

// ---------------------------------------------------------------------------
// Inline event handler coverage: timing-input @change (L1350-1351)
// ---------------------------------------------------------------------------

test("timing input @change updates config via _updateLocal (covers L1350-1351 inline lambda)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
  });
  const updates = [];
  vi.spyOn(card, "_updateLocal").mockImplementation((u) => {
    updates.push(u);
    card._config = { ...card._config, ...u };
  });

  const inputs = card.shadowRoot.querySelectorAll("input.timing-input");
  // First input = travel_time_close (min=0.1); set a value then fire change
  const input = inputs[0];
  input.value = "25.5";
  input.dispatchEvent(new Event("change", { bubbles: true }));

  // The lambda: const v = e.target.value.trim(); _updateLocal({ [key]: parseFloat(v) })
  expect(updates.length).toBeGreaterThan(0);
  expect(updates[0]).toMatchObject({ travel_time_close: 25.5 });
});

test("timing input @change with empty value sets field to null", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ travel_time_close: 30 }),
    activeTab: "timing",
  });
  const updates = [];
  vi.spyOn(card, "_updateLocal").mockImplementation((u) => {
    updates.push(u);
    card._config = { ...card._config, ...u };
  });

  const inputs = card.shadowRoot.querySelectorAll("input.timing-input");
  const input = inputs[0];
  input.value = "";
  input.dispatchEvent(new Event("change", { bubbles: true }));

  expect(updates.length).toBeGreaterThan(0);
  expect(updates[0]).toMatchObject({ travel_time_close: null });
});

// ---------------------------------------------------------------------------
// Inline event handler coverage: max_tilt_allowed_position onChange (L1325-1328)
// ---------------------------------------------------------------------------

test("max_tilt_allowed_position ha-input @change updates config via _updateLocal (covers L1325-1328)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "dual_motor", max_tilt_allowed_position: 0 }),
    activeTab: "device",
  });
  const updates = [];
  vi.spyOn(card, "_updateLocal").mockImplementation((u) => {
    updates.push(u);
    card._config = { ...card._config, ...u };
  });

  // The dual-motor-config section renders two ha-input elements:
  // [0] = safe_tilt_position, [1] = max_tilt_allowed_position
  const haInputs = card.shadowRoot.querySelectorAll(".dual-motor-config ha-input");
  expect(haInputs.length).toBe(2);
  const maxTiltInput = haInputs[1];
  maxTiltInput.value = "80";
  maxTiltInput.dispatchEvent(new Event("change", { bubbles: true }));

  expect(updates.length).toBeGreaterThan(0);
  expect(updates[0]).toMatchObject({ max_tilt_allowed_position: 80 });
});

test("max_tilt_allowed_position ha-input @change with empty string sets field to null", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg({ tilt_mode: "dual_motor", max_tilt_allowed_position: 50 }),
    activeTab: "device",
  });
  const updates = [];
  vi.spyOn(card, "_updateLocal").mockImplementation((u) => {
    updates.push(u);
    card._config = { ...card._config, ...u };
  });

  const haInputs = card.shadowRoot.querySelectorAll(".dual-motor-config ha-input");
  const maxTiltInput = haInputs[1];
  maxTiltInput.value = "  ";  // whitespace-only → trims to ""
  maxTiltInput.dispatchEvent(new Event("change", { bubbles: true }));

  expect(updates.length).toBeGreaterThan(0);
  expect(updates[0]).toMatchObject({ max_tilt_allowed_position: null });
});
