/**
 * Characterization tests for cover-time-based-card.js autosave + save-failure revert logic.
 *
 * Tests lock in CURRENT behavior and must PASS. Source files under
 * custom_components/cover_time_based/frontend/ are read-only.
 *
 * Key behaviors characterized here:
 *   - _autoSave strips entry_id from _config and sends update_config
 *   - _autoSave on failure sets _saveError, calls _loadConfig (reload), then clears after 3s
 *   - _autoSave early-returns when _selectedEntity or _config is missing
 *
 * Note: the failure-path test triggers card._autoSave()'s own console.error("Failed to save
 * config:", err) — this is expected by design and not suppressed here.
 *
 * Run: npm run test:fe -- tests/frontend/card_save.test.mjs
 */

import { test, expect, afterEach, vi } from "vitest";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard, defineHaStubs } from "./helpers/mount.mjs";

defineHaStubs();

let card;
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  card?.remove();
  card = null;
});

// ---------------------------------------------------------------------------
// Success path: entry_id stripped, update_config sent, _saving ends false
// ---------------------------------------------------------------------------

test("_autoSave sends update_config with entry_id stripped and other fields included", async () => {
  const hass = makeHass();
  card = await mountCard(hass, {
    selectedEntity: "cover.test",
    config: { entry_id: "abc123", control_mode: "switch", pulse_time: 2 },
  });

  await card._autoSave();

  expect(hass.callWS).toHaveBeenCalledWith({
    type: "cover_time_based/update_config",
    control_mode: "switch",
    pulse_time: 2,
    entity_id: "cover.test",
  });
  // entry_id must NOT appear in the payload
  expect(hass.callWS).not.toHaveBeenCalledWith(
    expect.objectContaining({ entry_id: expect.anything() })
  );
  expect(card._saving).toBe(false);
});

test("_autoSave leaves _saveError false on success", async () => {
  const hass = makeHass();
  card = await mountCard(hass, {
    selectedEntity: "cover.test",
    config: { control_mode: "switch" },
  });

  await card._autoSave();

  expect(card._saveError).toBe(false);
  expect(card._saving).toBe(false);
});

// ---------------------------------------------------------------------------
// Failure path: _saveError set, config reloaded, error cleared after 3s
// ---------------------------------------------------------------------------

test("_autoSave on failure sets _saveError, reloads config, then clears _saveError after 3s", async () => {
  vi.useFakeTimers();
  const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  let getConfigCalls = 0;

  const hass = makeHass({
    ws: {
      "cover_time_based/update_config": () => {
        throw new Error("save failed");
      },
      "cover_time_based/get_config": () => {
        getConfigCalls++;
        return { control_mode: "switch" };
      },
    },
  });

  card = await mountCard(hass, {
    selectedEntity: "cover.test",
    config: { control_mode: "switch" },
  });

  // Capture baseline: mountCard may already have triggered get_config calls
  // (connectedCallback calls _loadEntityList(), not _loadConfig directly, but
  // rendering with a pre-set _selectedEntity can trigger _loadConfig).
  // We record the count here so we only count the reload triggered by the failure.
  const callsBefore = getConfigCalls;

  await card._autoSave();

  expect(card._saveError).toBe(true);
  expect(errSpy).toHaveBeenCalled();
  // Exactly one get_config call should have occurred since before the _autoSave call
  expect(getConfigCalls - callsBefore).toBe(1);

  // After 3 seconds the error banner should clear
  vi.advanceTimersByTime(3000);
  expect(card._saveError).toBe(false);
});

test("_autoSave on failure still ends with _saving false", async () => {
  vi.useFakeTimers();
  const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});

  const hass = makeHass({
    ws: {
      "cover_time_based/update_config": () => {
        throw new Error("save failed");
      },
    },
  });

  card = await mountCard(hass, {
    selectedEntity: "cover.test",
    config: { control_mode: "switch" },
  });

  await card._autoSave();

  expect(card._saving).toBe(false);
  expect(errSpy).toHaveBeenCalled();
});

// ---------------------------------------------------------------------------
// Early-return: no selected entity → update_config never called
// ---------------------------------------------------------------------------

test("_autoSave early-returns without a selected entity", async () => {
  const hass = makeHass();
  // mountCard with no selectedEntity (defaults to empty string — falsy)
  card = await mountCard(hass, { config: { control_mode: "switch" } });

  await card._autoSave();

  expect(hass.callWS).not.toHaveBeenCalledWith(
    expect.objectContaining({ type: "cover_time_based/update_config" })
  );
});

test("_autoSave early-returns when _config is null", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.test", config: null });

  await card._autoSave();

  expect(hass.callWS).not.toHaveBeenCalledWith(
    expect.objectContaining({ type: "cover_time_based/update_config" })
  );
});
