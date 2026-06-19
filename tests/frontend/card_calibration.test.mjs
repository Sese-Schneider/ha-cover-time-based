/**
 * Characterization tests for cover-time-based-card.js calibration,
 * raw-command, and position-preset logic.
 *
 * These tests LOCK IN the card's current behavior. The 4 source files under
 * custom_components/cover_time_based/frontend/ are off-limits for edits.
 *
 * ATTRIBUTE_TO_CONFIG (module-level map, ~L385 in card source):
 *   travel_time_close  → "travel_time_close"
 *   travel_time_open   → "travel_time_open"
 *   tilt_time_close    → "tilt_time_close"
 *   tilt_time_open     → "tilt_time_open"
 *   travel_startup_delay → "travel_startup_delay"
 *   tilt_startup_delay → "tilt_startup_delay"
 *   min_movement_time  → "min_movement_time"
 *
 * Run: npm run test:fe -- tests/frontend/card_calibration.test.mjs
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
// _onStartCalibration
// ---------------------------------------------------------------------------

test("_onStartCalibration sends start_calibration and flips _calibratingOverride on success", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x" });
  card.shadowRoot.querySelector = () => ({ value: "travel_time_close" });
  await card._onStartCalibration();
  expect(hass.callWS).toHaveBeenCalledWith(expect.objectContaining({
    type: "cover_time_based/start_calibration",
    entity_id: "cover.x",
    attribute: "travel_time_close",
    timeout: 300,
  }));
  expect(card._calibratingOverride).toBe(true);
});

test("_onStartCalibration sets _knownPosition to 'unknown' on success", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x", knownPosition: "open" });
  card.shadowRoot.querySelector = () => ({ value: "travel_time_open" });
  await card._onStartCalibration();
  expect(card._knownPosition).toBe("unknown");
});

test("_onStartCalibration sends the attribute from the #cal-attribute select", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.y" });
  card.shadowRoot.querySelector = () => ({ value: "tilt_time_open" });
  await card._onStartCalibration();
  expect(hass.callWS).toHaveBeenCalledWith(expect.objectContaining({
    attribute: "tilt_time_open",
    entity_id: "cover.y",
  }));
});

test("_onStartCalibration alerts on WS failure (window.alert is expected behavior)", async () => {
  const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const hass = makeHass({
    ws: {
      "cover_time_based/start_calibration": () => {
        throw new Error("server rejected");
      },
    },
  });
  card = await mountCard(hass, { selectedEntity: "cover.x" });
  card.shadowRoot.querySelector = () => ({ value: "travel_time_close" });
  await card._onStartCalibration();
  expect(window.alert).toHaveBeenCalled();
  expect(errSpy).toHaveBeenCalled();
  // _calibratingOverride must NOT be set to true on failure
  expect(card._calibratingOverride).not.toBe(true);
});

test("_onStartCalibration alert message contains the error text", async () => {
  const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const hass = makeHass({
    ws: {
      "cover_time_based/start_calibration": () => {
        throw new Error("calibration refused");
      },
    },
  });
  card = await mountCard(hass, { selectedEntity: "cover.x" });
  card.shadowRoot.querySelector = () => ({ value: "travel_time_close" });
  await card._onStartCalibration();
  expect(window.alert).toHaveBeenCalledWith(expect.stringContaining("calibration refused"));
  expect(errSpy).toHaveBeenCalled();
});

// ---------------------------------------------------------------------------
// _onStopCalibration
// ---------------------------------------------------------------------------

// All 7 ATTRIBUTE_TO_CONFIG entries (attribute → config key):
test.each([
  ["travel_time_close",   "travel_time_close"],
  ["tilt_time_open",      "tilt_time_open"],
  ["travel_time_open",    "travel_time_open"],
  ["tilt_time_close",     "tilt_time_close"],
  ["travel_startup_delay","travel_startup_delay"],
  ["tilt_startup_delay",  "tilt_startup_delay"],
  ["min_movement_time",   "min_movement_time"],
])("_onStopCalibration(false) applies %s → _config.%s via ATTRIBUTE_TO_CONFIG", async (attr, key) => {
  const hass = makeHass({
    ws: {
      "cover_time_based/stop_calibration": () => ({ attribute: attr, value: 7.7 }),
    },
  });
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { control_mode: "switch" } });
  const spy = vi.spyOn(card, "_updateLocal").mockImplementation(() => {});
  await card._onStopCalibration(false);
  expect(spy).toHaveBeenCalledWith(expect.objectContaining({ [key]: 7.7 }));
});

test("_onStopCalibration(false) sets _calibratingOverride to false", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x" });
  card._calibratingOverride = true;
  await card._onStopCalibration(false);
  expect(card._calibratingOverride).toBe(false);
});

test("_onStopCalibration(false) sets _knownPosition to 'unknown'", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x", knownPosition: "open" });
  await card._onStopCalibration(false);
  expect(card._knownPosition).toBe("unknown");
});

test("_onStopCalibration(true) cancels: sends stop_calibration with cancel:true", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x" });
  await card._onStopCalibration(true);
  expect(hass.callWS).toHaveBeenCalledWith(expect.objectContaining({
    type: "cover_time_based/stop_calibration",
    entity_id: "cover.x",
    cancel: true,
  }));
});

test("_onStopCalibration(true) sets _calibratingOverride to false", async () => {
  card = await mountCard(makeHass(), { selectedEntity: "cover.x" });
  card._calibratingOverride = true;
  await card._onStopCalibration(true);
  expect(card._calibratingOverride).toBe(false);
});

test("_onStopCalibration(true) does NOT apply value even when WS returns one", async () => {
  const hass = makeHass({
    ws: {
      "cover_time_based/stop_calibration": () => ({
        attribute: "travel_time_close",
        value: 99.9,
      }),
    },
  });
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { control_mode: "switch" } });
  const spy = vi.spyOn(card, "_updateLocal").mockImplementation(() => {});
  await card._onStopCalibration(true);
  expect(spy).not.toHaveBeenCalled();
});

test("_onStopCalibration error path swallows the error (console.error is expected)", async () => {
  const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const hass = makeHass({
    ws: {
      "cover_time_based/stop_calibration": () => {
        throw new Error("ws down");
      },
    },
  });
  card = await mountCard(hass, { selectedEntity: "cover.x" });
  // Must NOT throw
  await expect(card._onStopCalibration(false)).resolves.toBeUndefined();
  expect(errSpy).toHaveBeenCalled();
});

// ---------------------------------------------------------------------------
// _onCoverCommand
// ---------------------------------------------------------------------------

test.each([
  ["open_cover",  "open"],
  ["close_cover", "close"],
  ["stop_cover",  "stop"],
  ["tilt_open",   "tilt_open"],
  ["tilt_close",  "tilt_close"],
  ["tilt_stop",   "tilt_stop"],
])("_onCoverCommand maps %s → '%s'", async (action, command) => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x" });
  await card._onCoverCommand(action);
  expect(hass.callWS).toHaveBeenCalledWith({
    type: "cover_time_based/raw_command",
    entity_id: "cover.x",
    command,
  });
});

test("_onCoverCommand sets _knownPosition to 'unknown'", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x", knownPosition: "open" });
  await card._onCoverCommand("open_cover");
  expect(card._knownPosition).toBe("unknown");
});

test("_onCoverCommand error path swallows the error (console.error is expected)", async () => {
  const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const hass = makeHass({
    ws: {
      "cover_time_based/raw_command": () => {
        throw new Error("command failed");
      },
    },
  });
  card = await mountCard(hass, { selectedEntity: "cover.x" });
  // Must NOT throw
  await expect(card._onCoverCommand("open_cover")).resolves.toBeUndefined();
  expect(errSpy).toHaveBeenCalled();
});

// ---------------------------------------------------------------------------
// _onPositionPresetChange
// ---------------------------------------------------------------------------

test("_onPositionPresetChange='unknown' sets _knownPosition and makes no service calls", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x", knownPosition: "open" });
  await card._onPositionPresetChange("unknown");
  expect(card._knownPosition).toBe("unknown");
  expect(hass.callService).not.toHaveBeenCalled();
});

test("_onPositionPresetChange='open' sets known position 100 (no tilt when tilt_mode:none)", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { tilt_mode: "none" } });
  await card._onPositionPresetChange("open");
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_position",
    { entity_id: "cover.x", position: 100 }
  );
  expect(hass.callService).not.toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_tilt_position",
    expect.anything()
  );
});

test("_onPositionPresetChange='open' sets position 100 + tilt 100 when tilt is on", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { tilt_mode: "inline" } });
  await card._onPositionPresetChange("open");
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_position",
    { entity_id: "cover.x", position: 100 }
  );
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_tilt_position",
    { entity_id: "cover.x", tilt_position: 100 }
  );
});

test("_onPositionPresetChange='open' sets position 100 + tilt 100 for dual_motor tilt mode", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { tilt_mode: "dual_motor" } });
  await card._onPositionPresetChange("open");
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_position",
    { entity_id: "cover.x", position: 100 }
  );
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_tilt_position",
    { entity_id: "cover.x", tilt_position: 100 }
  );
});

test("_onPositionPresetChange='closed' sets position 0, no tilt when tilt_mode:none", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { tilt_mode: "none" } });
  await card._onPositionPresetChange("closed");
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_position",
    { entity_id: "cover.x", position: 0 }
  );
  expect(hass.callService).not.toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_tilt_position",
    expect.anything()
  );
});

test("_onPositionPresetChange='closed' sets position 0 + tilt 0 when tilted", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { tilt_mode: "sequential_close" } });
  await card._onPositionPresetChange("closed");
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_position",
    { entity_id: "cover.x", position: 0 }
  );
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_tilt_position",
    { entity_id: "cover.x", tilt_position: 0 }
  );
});

test("_onPositionPresetChange='closed_tilt_open' sets position 0 + tilt 100", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { tilt_mode: "inline" } });
  await card._onPositionPresetChange("closed_tilt_open");
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_position",
    { entity_id: "cover.x", position: 0 }
  );
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_tilt_position",
    { entity_id: "cover.x", tilt_position: 100 }
  );
});

test("_onPositionPresetChange='closed_tilt_closed' sets position 0 + tilt 0", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { tilt_mode: "inline" } });
  await card._onPositionPresetChange("closed_tilt_closed");
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_position",
    { entity_id: "cover.x", position: 0 }
  );
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_tilt_position",
    { entity_id: "cover.x", tilt_position: 0 }
  );
});

test("_onPositionPresetChange='closed_tilt_open' sends tilt 100 regardless of config tilt_mode", async () => {
  // closed_tilt_open hardcodes tiltPosition = 100 unconditionally (no hasTilt check)
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { tilt_mode: "none" } });
  await card._onPositionPresetChange("closed_tilt_open");
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_tilt_position",
    { entity_id: "cover.x", tilt_position: 100 }
  );
});

test("_onPositionPresetChange='closed_tilt_closed' sends tilt 0 regardless of config tilt_mode", async () => {
  // closed_tilt_closed hardcodes tiltPosition = 0 unconditionally (no hasTilt check)
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { tilt_mode: "none" } });
  await card._onPositionPresetChange("closed_tilt_closed");
  expect(hass.callService).toHaveBeenCalledWith(
    "cover_time_based",
    "set_known_tilt_position",
    { entity_id: "cover.x", tilt_position: 0 }
  );
});

test("_onPositionPresetChange sets _knownPosition to the preset value", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { tilt_mode: "none" } });
  await card._onPositionPresetChange("open");
  expect(card._knownPosition).toBe("open");
});

test("_onPositionPresetChange error path swallows the error (console.error is expected)", async () => {
  const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const hass = makeHass({
    service: async () => { throw new Error("service failed"); },
  });
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { tilt_mode: "none" } });
  // Must NOT throw
  await expect(card._onPositionPresetChange("open")).resolves.toBeUndefined();
  expect(errSpy).toHaveBeenCalled();
});
