/**
 * single_button control mode — one cycling button (down/stop/up/stop), #245.
 *
 * The card labels the reused open_switch_entity_id slot "Button", hides
 * close_switch, stop_switch and every tilt field (the backend has no tilt
 * support at all in this mode), and surfaces a Resync control that lets the
 * user re-anchor the tracked phase/position after the physical button or an
 * RF remote moved the cover outside Home Assistant.
 *
 * Run: npm run test:fe -- tests/frontend/single_button_mode.test.mjs
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

const singleButtonCfg = (over = {}) => ({
  control_mode: "single_button",
  open_switch_entity_id: "switch.button",
  ...over,
});

const switchCfg = (over = {}) => ({
  control_mode: "switch",
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  ...over,
});

function captureUpdates(c) {
  const updates = [];
  vi.spyOn(c, "_updateLocal").mockImplementation((u) => {
    updates.push(u);
    c._config = { ...c._config, ...u };
  });
  return updates;
}

// ---------------------------------------------------------------------------
// Mode option + field visibility (device tab)
// ---------------------------------------------------------------------------

test("single_button mode: its option has the selected attribute", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: singleButtonCfg(),
    activeTab: "device",
  });
  const select = card.shadowRoot.querySelector("select.ha-select");
  const selectedOpt = [...select.options].find((o) => o.hasAttribute("selected"));
  expect(selectedOpt?.value).toBe("single_button");
});

test("single_button mode: field-label reads 'Button' and exactly one entity picker (the button) is shown besides the top device picker", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: singleButtonCfg(),
    activeTab: "device",
  });
  const labels = [...card.shadowRoot.querySelectorAll(".field-label")].map((n) =>
    n.textContent.trim(),
  );
  expect(labels).toContain("Button");

  const pickers = card.shadowRoot.querySelectorAll("ha-entity-picker");
  // top device picker + the single button picker = 2
  expect(pickers.length).toBe(2);
  expect(pickers[1].getAttribute("label")).toBe("Button");
  expect(pickers[1].value).toBe("switch.button");
});

test("single_button mode: close_switch and stop_switch pickers are absent", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: singleButtonCfg(),
    activeTab: "device",
  });
  const labels = [...card.shadowRoot.querySelectorAll("ha-entity-picker")].map((p) =>
    p.getAttribute("label"),
  );
  expect(labels).not.toContain("Close switch");
  expect(labels).not.toContain("Stop switch");
});

test("single_button mode: entering a value in the button picker updates open_switch_entity_id", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: singleButtonCfg(),
    activeTab: "device",
  });
  const updates = captureUpdates(card);
  const pickers = card.shadowRoot.querySelectorAll("ha-entity-picker");
  const buttonPicker = pickers[1];
  buttonPicker.dispatchEvent(
    new CustomEvent("value-changed", { detail: { value: "switch.new_button" } }),
  );
  expect(updates[0]).toEqual({ open_switch_entity_id: "switch.new_button" });
});

test("single_button mode: no tilt-mode select at all (tilt is entirely unsupported)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: singleButtonCfg(),
    activeTab: "device",
  });
  expect(card.shadowRoot.querySelector("#tilt-mode-select")).toBeNull();
  expect(card.shadowRoot.querySelector(".dual-motor-config")).toBeNull();
});

test("single_button mode: tilt select is absent even for a stale dual_motor tilt_mode (hand-edited entry)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: singleButtonCfg({ tilt_mode: "dual_motor" }),
    activeTab: "device",
  });
  expect(card.shadowRoot.querySelector("#tilt-mode-select")).toBeNull();
  expect(card.shadowRoot.querySelector(".dual-motor-config")).toBeNull();
});

test("single_button mode still shows exactly the four all-mode toggles (assumed_state, force_endpoint_redrive, wait_for_relay_feedback, recalibrate_before_position)", async () => {
  // Same count as switch mode (card_render.test.mjs) — confirms only
  // close/stop/tilt were hidden, nothing else was accidentally dropped.
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: singleButtonCfg(),
    activeTab: "device",
  });
  const toggles = card.shadowRoot.querySelectorAll("ha-switch.toggle-switch");
  expect(toggles.length).toBe(4);
});

test("other modes are unaffected: switch mode still shows the close switch picker and no Resync control", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "device",
  });
  const labels = [...card.shadowRoot.querySelectorAll("ha-entity-picker")].map((p) =>
    p.getAttribute("label"),
  );
  expect(labels).toContain("Close switch");
  const fieldLabels = [...card.shadowRoot.querySelectorAll(".field-label")].map((n) =>
    n.textContent.trim(),
  );
  expect(fieldLabels).not.toContain("Resync");
});

// ---------------------------------------------------------------------------
// _hasRequiredEntities — single_button only needs the button entity
// ---------------------------------------------------------------------------

test("_hasRequiredEntities single_button: requires only open_switch_entity_id", async () => {
  card = await mountCard(makeHass());
  expect(card._hasRequiredEntities({ control_mode: "single_button" })).toBe(false);
  expect(
    card._hasRequiredEntities({
      control_mode: "single_button",
      open_switch_entity_id: "switch.button",
    }),
  ).toBe(true);
});

test("_hasRequiredEntities single_button ignores a stale dual_motor tilt_mode (hand-edited entry) as long as the button is set", async () => {
  card = await mountCard(makeHass());
  expect(
    card._hasRequiredEntities({
      control_mode: "single_button",
      open_switch_entity_id: "switch.button",
      tilt_mode: "dual_motor",
      // No tilt_open_switch/tilt_close_switch — would fail the dual_motor
      // check for every other non-wrapped mode.
    }),
  ).toBe(true);
});

test("calibration tab is enabled for single_button once the button entity is set", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: singleButtonCfg(),
    activeTab: "device",
  });
  const tabs = card.shadowRoot.querySelectorAll(".tab");
  expect(tabs[1].disabled).toBe(false);
});

test("calibration tab is disabled for single_button without the button entity", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: { control_mode: "single_button" },
    activeTab: "device",
  });
  const tabs = card.shadowRoot.querySelectorAll(".tab");
  expect(tabs[1].disabled).toBe(true);
});

// ---------------------------------------------------------------------------
// _onControlModeChange — clearing stale config on entry to single_button
// ---------------------------------------------------------------------------

test("_onControlModeChange to single_button keeps open_switch_entity_id but clears close/stop/tilt-motor switches", async () => {
  card = await mountCard(makeHass(), {
    config: {
      control_mode: "switch",
      open_switch_entity_id: "switch.o",
      close_switch_entity_id: "switch.c",
    },
  });
  const updates = captureUpdates(card);
  card._onControlModeChange({ target: { value: "single_button" } });
  expect(updates[0].control_mode).toBe("single_button");
  expect(updates[0].close_switch_entity_id).toBeNull();
  expect(updates[0].stop_switch_entity_id).toBeNull();
  expect(updates[0].tilt_stop_switch).toBeNull();
  expect(updates[0].tilt_open_switch).toBeNull();
  expect(updates[0].tilt_close_switch).toBeNull();
  // The reused button slot must survive the switch.
  expect(updates[0].open_switch_entity_id).toBeUndefined();
  expect(card._config.open_switch_entity_id).toBe("switch.o");
});

test("_onControlModeChange to single_button resets a non-none tilt_mode inherited from the previous mode", async () => {
  card = await mountCard(makeHass(), {
    config: { control_mode: "switch", tilt_mode: "sequential_close" },
  });
  const updates = captureUpdates(card);
  card._onControlModeChange({ target: { value: "single_button" } });
  expect(updates[0].tilt_mode).toBe("none");
  expect(updates[0].tilt_time_close).toBeNull();
  expect(updates[0].tilt_time_open).toBeNull();
  expect(updates[0].safe_tilt_position).toBeNull();
  expect(updates[0].max_tilt_allowed_position).toBeNull();
  expect(updates[0].close_includes_tilt).toBeNull();
});

test("_onControlModeChange to single_button resets dual_motor tilt too (not just sequential/inline)", async () => {
  card = await mountCard(makeHass(), {
    config: { control_mode: "switch", tilt_mode: "dual_motor" },
  });
  const updates = captureUpdates(card);
  card._onControlModeChange({ target: { value: "single_button" } });
  expect(updates[0].tilt_mode).toBe("none");
});

test("_onControlModeChange to single_button with tilt_mode already 'none' is an idempotent no-op on the effective config", async () => {
  // clearedTiltConfig() is unconditional now (no guard), so the update
  // re-asserts tilt_mode: "none" and re-nulls the already-null tilt fields
  // rather than omitting them — but the resulting config is unchanged.
  card = await mountCard(makeHass(), {
    config: { control_mode: "switch", tilt_mode: "none" },
  });
  const updates = captureUpdates(card);
  card._onControlModeChange({ target: { value: "single_button" } });
  expect(updates[0].tilt_mode).toBe("none");
  expect(card._config.tilt_mode).toBe("none");
  expect(card._config.tilt_time_close).toBeNull();
});

// ---------------------------------------------------------------------------
// Resync control
// ---------------------------------------------------------------------------

test("Resync section renders only for single_button mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: singleButtonCfg(),
    activeTab: "device",
  });
  const fieldLabels = [...card.shadowRoot.querySelectorAll(".field-label")].map((n) =>
    n.textContent.trim(),
  );
  expect(fieldLabels).toContain("Resync");

  const buttons = [...card.shadowRoot.querySelectorAll("ha-button")].map((b) =>
    b.textContent.trim(),
  );
  expect(buttons).toContain("Fully closed");
  expect(buttons).toContain("Fully open");
});

function resyncButton(card, text) {
  return [...card.shadowRoot.querySelectorAll("ha-button")].find(
    (b) => b.textContent.trim() === text,
  );
}

test("clicking 'Fully closed' calls the resync service with state=closed", async () => {
  const hass = makeHass();
  card = await mountCard(hass, {
    selectedEntity: "cover.x",
    config: singleButtonCfg(),
    activeTab: "device",
  });
  resyncButton(card, "Fully closed").dispatchEvent(new Event("click"));
  await Promise.resolve();
  expect(hass.callService).toHaveBeenCalledWith("cover_time_based", "resync", {
    entity_id: "cover.x",
    state: "closed",
  });
});

test("clicking 'Fully open' calls the resync service with state=open", async () => {
  const hass = makeHass();
  card = await mountCard(hass, {
    selectedEntity: "cover.x",
    config: singleButtonCfg(),
    activeTab: "device",
  });
  resyncButton(card, "Fully open").dispatchEvent(new Event("click"));
  await Promise.resolve();
  expect(hass.callService).toHaveBeenCalledWith("cover_time_based", "resync", {
    entity_id: "cover.x",
    state: "open",
  });
});

test("_onResync is a no-op without a selected entity", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { config: singleButtonCfg(), selectedEntity: "" });
  await card._onResync("closed");
  expect(hass.callService).not.toHaveBeenCalled();
});

test("_onResync logs and does not throw when the service call rejects", async () => {
  const hass = makeHass({ service: async () => Promise.reject(new Error("boom")) });
  card = await mountCard(hass, { selectedEntity: "cover.x", config: singleButtonCfg() });
  const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  await expect(card._onResync("open")).resolves.toBeUndefined();
  expect(errSpy).toHaveBeenCalled();
});
