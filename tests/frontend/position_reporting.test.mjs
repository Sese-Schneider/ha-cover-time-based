/**
 * Position reporting dropdown (wrapped covers) — issue #238.
 *
 * One "Position reporting" <select> replaces the ignore_reported_position and
 * reports_command_not_endpoint toggles and adds the new ignore_endpoint_states
 * profile. The select derives its value from the stored booleans and writes a
 * mutually-exclusive combination of them.
 *
 * Run: npm run test:fe -- tests/frontend/position_reporting.test.mjs
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

const wrappedCfg = (over = {}) => ({
  control_mode: "wrapped",
  cover_entity_id: "cover.real",
  ...over,
});
const switchCfg = (over = {}) => ({
  control_mode: "switch",
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  ...over,
});

const select = (card) => card.shadowRoot.querySelector("#position-reporting-select");
const selectedValue = (sel) => [...sel.options].find((o) => o.hasAttribute("selected"))?.value;

test("dropdown renders for wrapped mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  expect(select(card)).not.toBeNull();
});

test("dropdown does NOT render for switch mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "device",
  });
  expect(select(card)).toBeNull();
});

test("defaults to the reliable profile", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  expect(selectedValue(select(card))).toBe("reliable");
});

test("derives unreliable from ignore_reported_position", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ ignore_reported_position: true }),
    activeTab: "device",
  });
  expect(selectedValue(select(card))).toBe("unreliable");
});

test("derives no_endpoints from ignore_endpoint_states", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ ignore_reported_position: true, ignore_endpoint_states: true }),
    activeTab: "device",
  });
  expect(selectedValue(select(card))).toBe("no_endpoints");
});

test("derives command_echo from reports_command_not_endpoint", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ reports_command_not_endpoint: true }),
    activeTab: "device",
  });
  expect(selectedValue(select(card))).toBe("command_echo");
});

test("selecting no_endpoints writes the ignore_endpoint_states combination", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  const captured = [];
  card._updateLocal = (u) => captured.push(u);
  const sel = select(card);
  sel.value = "no_endpoints";
  sel.dispatchEvent(new Event("change"));
  expect(captured).toContainEqual({
    ignore_reported_position: true,
    ignore_endpoint_states: true,
    reports_command_not_endpoint: false,
  });
});

test("selecting command_echo writes only reports_command_not_endpoint", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ ignore_endpoint_states: true, ignore_reported_position: true }),
    activeTab: "device",
  });
  const captured = [];
  card._updateLocal = (u) => captured.push(u);
  const sel = select(card);
  sel.value = "command_echo";
  sel.dispatchEvent(new Event("change"));
  expect(captured).toContainEqual({
    ignore_reported_position: false,
    ignore_endpoint_states: false,
    reports_command_not_endpoint: true,
  });
});

test("selecting reliable clears every report-interpretation flag", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ ignore_endpoint_states: true, ignore_reported_position: true }),
    activeTab: "device",
  });
  const captured = [];
  card._updateLocal = (u) => captured.push(u);
  const sel = select(card);
  sel.value = "reliable";
  sel.dispatchEvent(new Event("change"));
  expect(captured).toContainEqual({
    ignore_reported_position: false,
    ignore_endpoint_states: false,
    reports_command_not_endpoint: false,
  });
});
