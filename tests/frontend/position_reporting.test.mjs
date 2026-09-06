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

test("derives no_endpoints from ignore_endpoint_states alone", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ ignore_endpoint_states: true }),
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

test("derives ignore_all from ignore_all_reports", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ ignore_all_reports: true }),
    activeTab: "device",
  });
  expect(selectedValue(select(card))).toBe("ignore_all");
});

test("selecting no_endpoints writes ignore_endpoint_states only (strict inverse of the read)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ ignore_reported_position: true }),
    activeTab: "device",
  });
  const captured = [];
  card._updateLocal = (u) => captured.push(u);
  const sel = select(card);
  sel.value = "no_endpoints";
  sel.dispatchEvent(new Event("change"));
  expect(captured).toContainEqual({
    ignore_reported_position: false,
    ignore_endpoint_states: true,
    reports_command_not_endpoint: false,
    ignore_all_reports: false,
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
    ignore_all_reports: false,
  });
});

test("selecting ignore_all writes only ignore_all_reports", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ ignore_endpoint_states: true }),
    activeTab: "device",
  });
  const captured = [];
  card._updateLocal = (u) => captured.push(u);
  const sel = select(card);
  sel.value = "ignore_all";
  sel.dispatchEvent(new Event("change"));
  expect(captured).toContainEqual({
    ignore_reported_position: false,
    ignore_endpoint_states: false,
    reports_command_not_endpoint: false,
    ignore_all_reports: true,
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
    ignore_all_reports: false,
  });
});

// ---------------------------------------------------------------------------
// Legacy entries written before the dropdown replaced the four independent
// booleans can carry both `ignore_reported_position` and
// `reports_command_not_endpoint`. The dropdown shows them as command_echo, and
// writing that profile clears the other flag — lossless, because a command-echo
// cover ignores the reported position on every channel anyway.
// ---------------------------------------------------------------------------

const legacyCombinedCfg = (over = {}) =>
  wrappedCfg({
    ignore_reported_position: true,
    reports_command_not_endpoint: true,
    ignore_endpoint_states: false,
    ignore_all_reports: false,
    travel_time_open: 20,
    travel_time_close: 20,
    ...over,
  });

const mountLegacy = (hass = makeHass(), over = {}) =>
  mountCard(hass, {
    selectedEntity: "cover.x",
    config: legacyCombinedCfg(over),
    activeTab: "device",
  });

test("both legacy flags render as command_echo", async () => {
  card = await mountLegacy();
  expect(selectedValue(select(card))).toBe("command_echo");
  // There is deliberately no option expressing "command echo AND position
  // unreliable": command_echo already implies it.
  expect([...select(card).options].map((o) => o.value)).toEqual([
    "reliable",
    "unreliable",
    "no_endpoints",
    "command_echo",
    "ignore_all",
  ]);
});

test("mounting the card does not rewrite the booleans", async () => {
  const hass = makeHass();
  card = await mountLegacy(hass);
  expect(card._config.ignore_reported_position).toBe(true);
  expect(card._config.reports_command_not_endpoint).toBe(true);
  expect(hass.callWS).not.toHaveBeenCalledWith(
    expect.objectContaining({ type: "cover_time_based/update_config" }),
  );
});

test("saving an unrelated field round-trips both legacy flags intact", async () => {
  const hass = makeHass();
  card = await mountLegacy(hass);

  card._updateLocal({ travel_time_open: 25 }); // an unrelated edit
  await card._autoSave();

  expect(hass.callWS).toHaveBeenCalledWith(
    expect.objectContaining({
      type: "cover_time_based/update_config",
      travel_time_open: 25,
      ignore_reported_position: true,
      reports_command_not_endpoint: true,
    }),
  );
});

test("re-selecting command_echo on a legacy entry drops ignore_reported_position", async () => {
  const hass = makeHass();
  card = await mountLegacy(hass);
  const sel = select(card);
  sel.value = "command_echo"; // the profile already shown
  sel.dispatchEvent(new Event("change"));
  await card.updateComplete;
  await card._autoSave();

  // Intentional: the backend treats command-echo as a superset of "position
  // unreliable" — it ignores a reported position on both live channels and at
  // startup — so normalising the pair to the single profile loses nothing.
  expect(hass.callWS).toHaveBeenCalledWith(
    expect.objectContaining({
      type: "cover_time_based/update_config",
      reports_command_not_endpoint: true,
      ignore_reported_position: false,
    }),
  );
});

test("ignore_endpoint_states + ignore_reported_position collapses to no_endpoints", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ ignore_endpoint_states: true, ignore_reported_position: true }),
    activeTab: "device",
  });
  expect(selectedValue(select(card))).toBe("no_endpoints");
});
