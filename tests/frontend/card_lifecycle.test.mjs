/**
 * Characterization tests for cover-time-based-card.js lifecycle & data-loading methods.
 *
 * IMPORTANT: defineHaStubs() is NOT called in this file. This keeps "ha-entity-picker"
 * unregistered so that the connectedCallback lazy-load branch (calling window.loadCardHelpers)
 * is exercised. Custom elements cannot be un-defined, so registering ha-entity-picker here
 * would prevent testing that branch for the rest of the file.
 *
 * Run: npm run test:fe -- tests/frontend/card_lifecycle.test.mjs
 */

import { test, expect, afterEach, vi } from "vitest";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard } from "./helpers/mount.mjs";   // NOTE: no defineHaStubs in this file

let card;
afterEach(() => {
  vi.restoreAllMocks();
  card?.remove();
  card = null;
});

// ---------------------------------------------------------------------------
// connectedCallback — lazy-load branch
// ---------------------------------------------------------------------------

test("connectedCallback triggers loadCardHelpers when ha-entity-picker is unregistered", async () => {
  // ha-entity-picker is NOT registered in this file (no defineHaStubs() call).
  // The card's connectedCallback should call window.loadCardHelpers().
  // setup.mjs wires window.loadCardHelpers as a vi.fn() spy before each test.
  const hass = makeHass();
  card = await mountCard(hass);
  expect(window.loadCardHelpers).toHaveBeenCalled();
});

// ---------------------------------------------------------------------------
// _loadEntityList — success path
// ---------------------------------------------------------------------------

test("_loadEntityList filters to entities whose config_entry_id is in live config entries", async () => {
  const hass = makeHass({
    ws: {
      "config/entity_registry/list": () => [
        { entity_id: "cover.live", platform: "cover_time_based", config_entry_id: "e1" },
        { entity_id: "cover.dead", platform: "cover_time_based", config_entry_id: "gone" },
        { entity_id: "cover.other_domain", platform: "light", config_entry_id: "e1" },
      ],
      "config_entries/get": () => [{ entry_id: "e1" }],
    },
  });
  card = await mountCard(hass);
  // Reset after initial mount so we can observe a fresh call
  card._configEntryEntities = undefined;
  await card._loadEntityList();
  // Only cover.live matches: platform=cover_time_based AND config_entry_id in live entries
  expect(card._configEntryEntities).toEqual(["cover.live"]);
});

// ---------------------------------------------------------------------------
// _loadEntityList — error path
// ---------------------------------------------------------------------------

test("_loadEntityList swallows errors and sets _configEntryEntities to []", async () => {
  // The card intentionally calls console.error on this path — that is expected behavior.
  const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const hass = makeHass({
    ws: {
      "config/entity_registry/list": () => { throw new Error("boom"); },
    },
  });
  card = await mountCard(hass);
  card._configEntryEntities = undefined;
  await card._loadEntityList();
  expect(card._configEntryEntities).toEqual([]);
  expect(errSpy).toHaveBeenCalled();
});

// ---------------------------------------------------------------------------
// _loadConfig — success path
// ---------------------------------------------------------------------------

test("_loadConfig sets _config and clears _loading/_loadError on success", async () => {
  const fakeConfig = { control_mode: "switch", entry_id: "e1", travel_time_up: 30 };
  const hass = makeHass({
    ws: {
      "cover_time_based/get_config": () => fakeConfig,
    },
  });
  card = await mountCard(hass);
  card._selectedEntity = "cover.my_cover";
  card._loadError = "stale error";
  await card._loadConfig();
  expect(card._config).toEqual(fakeConfig);
  expect(card._loading).toBe(false);
  expect(card._loadError).toBeNull();
});

// ---------------------------------------------------------------------------
// _loadConfig — failure path
// ---------------------------------------------------------------------------

test("_loadConfig sets _loadError to yaml_warning string and nulls _config on failure", async () => {
  // The card intentionally calls console.error on this path — that is expected behavior.
  const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const hass = makeHass({
    ws: {
      "cover_time_based/get_config": () => { throw new Error("network fail"); },
    },
  });
  card = await mountCard(hass);
  card._selectedEntity = "cover.my_cover";
  card._config = { some: "data" };
  await card._loadConfig();
  expect(card._config).toBeNull();
  expect(card._loadError).toBe(card._t("yaml_warning"));
  expect(card._loading).toBe(false);
  expect(errSpy).toHaveBeenCalled();
});

// ---------------------------------------------------------------------------
// _loadConfig — early-return (no _selectedEntity)
// ---------------------------------------------------------------------------

test("_loadConfig returns early without calling callWS when _selectedEntity is empty", async () => {
  const hass = makeHass();
  card = await mountCard(hass);
  // Reset call count after mount
  hass.callWS.mockClear();
  card._selectedEntity = "";   // ensure no entity is selected
  await card._loadConfig();
  // callWS should NOT have been called for get_config (or at all)
  const getConfigCalls = hass.callWS.mock.calls.filter(
    ([arg]) => arg?.type === "cover_time_based/get_config"
  );
  expect(getConfigCalls).toHaveLength(0);
});

// ---------------------------------------------------------------------------
// disconnectedCallback — timer cleared + calibration cancelled
// ---------------------------------------------------------------------------

test("disconnectedCallback clears autoSaveTimer and calls _onStopCalibration(true) when calibrating", async () => {
  const hass = makeHass();
  card = await mountCard(hass);

  // Plant a real timer so clearTimeout has something to find
  const timer = setTimeout(() => {}, 9999);
  card._autoSaveTimer = timer;

  // Force the calibrating state via the override flag
  card._calibratingOverride = true;

  // Spy on the methods we want to assert
  const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout");
  const stopCalSpy = vi.spyOn(card, "_onStopCalibration");

  card.disconnectedCallback();

  expect(clearTimeoutSpy).toHaveBeenCalledWith(timer);
  expect(stopCalSpy).toHaveBeenCalledWith(true);

  // Clean up the real timer
  clearTimeout(timer);
});

// ---------------------------------------------------------------------------
// performUpdate — scroll-preservation path does not throw
// ---------------------------------------------------------------------------

test("performUpdate completes without throwing (scroll-preservation path)", async () => {
  const hass = makeHass();
  card = await mountCard(hass);
  // Should resolve cleanly; the scroll parent walk runs but no real scroll parent exists
  await expect(card.performUpdate()).resolves.toBeUndefined();
});

// ---------------------------------------------------------------------------
// updated — no-op, does not throw
// ---------------------------------------------------------------------------

test("updated(new Map()) returns undefined and does not throw", async () => {
  const hass = makeHass();
  card = await mountCard(hass);
  const result = card.updated(new Map());
  expect(result).toBeUndefined();
});
