/**
 * send_endpoint_stop (pulse-mode endpoint stop) UI — issue #133.
 *
 * The toggle renders ONLY for pulse mode (mirroring how relay_reports_off
 * renders only for toggle mode). The endpoint run-on timing row shows for
 * switch mode and for pulse-with-stop-on, and is hidden for
 * pulse-with-stop-off / toggle / wrapped.
 *
 * Run: npm run test:fe -- tests/frontend/send_endpoint_stop.test.mjs
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

const SEND_STOP_LABEL = "Send stop signal at endpoints";

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

const wrappedCfg = (over = {}) => ({
  control_mode: "wrapped",
  cover_entity_id: "cover.real",
  ...over,
});

function hasSendStopToggle(card) {
  const labels = [...card.shadowRoot.querySelectorAll(".toggle-label")];
  return labels.some((el) => el.textContent.trim() === SEND_STOP_LABEL);
}

function timingInputCount(card) {
  return card.shadowRoot.querySelectorAll("input.timing-input").length;
}

// ---------------------------------------------------------------------------
// The toggle renders only for pulse mode
// ---------------------------------------------------------------------------

test("send_endpoint_stop toggle renders for pulse mode (default on)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: pulseCfg(),
    activeTab: "device",
  });
  expect(hasSendStopToggle(card)).toBe(true);
});

test("send_endpoint_stop toggle still renders for pulse mode when stored false", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: pulseCfg({ send_endpoint_stop: false }),
    activeTab: "device",
  });
  expect(hasSendStopToggle(card)).toBe(true);
});

test("send_endpoint_stop toggle does NOT render for switch mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "device",
  });
  expect(hasSendStopToggle(card)).toBe(false);
});

test("send_endpoint_stop toggle does NOT render for toggle mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: toggleCfg(),
    activeTab: "device",
  });
  expect(hasSendStopToggle(card)).toBe(false);
});

test("send_endpoint_stop toggle does NOT render for wrapped mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  expect(hasSendStopToggle(card)).toBe(false);
});

// ---------------------------------------------------------------------------
// Endpoint run-on row gating
//   switch mode  → 5 rows (incl. endpoint_runon_time)
//   pulse w/stop-on (default) → 5 rows (endpoint_runon_time shown)
//   pulse w/stop-off → 4 rows (endpoint_runon_time hidden)
//   toggle / wrapped → 4 rows (endpoint_runon_time hidden)
// ---------------------------------------------------------------------------

test("switch mode shows the endpoint run-on row (5 travel rows)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
  });
  expect(timingInputCount(card)).toBe(5);
});

test("pulse mode with stop on (default) shows the endpoint run-on row (5 travel rows)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: pulseCfg(),
    activeTab: "timing",
  });
  expect(timingInputCount(card)).toBe(5);
});

test("pulse mode with stop OFF hides the endpoint run-on row (4 travel rows)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: pulseCfg({ send_endpoint_stop: false }),
    activeTab: "timing",
  });
  expect(timingInputCount(card)).toBe(4);
});

test("toggle mode hides the endpoint run-on row (4 travel rows)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: toggleCfg(),
    activeTab: "timing",
  });
  expect(timingInputCount(card)).toBe(4);
});

test("wrapped mode hides the endpoint run-on row (4 travel rows)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "timing",
  });
  expect(timingInputCount(card)).toBe(4);
});
