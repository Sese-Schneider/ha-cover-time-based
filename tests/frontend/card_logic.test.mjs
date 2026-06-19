/**
 * Characterization tests for cover-time-based-card.js pure & derived-state methods.
 *
 * These tests LOCK IN the card's current behavior. The 4 source files under
 * custom_components/cover_time_based/frontend/ are off-limits for edits.
 *
 * Run: npm run test:fe -- tests/frontend/card_logic.test.mjs
 */

import { test, expect, afterEach, vi } from "vitest";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard, defineHaStubs } from "./helpers/mount.mjs";

defineHaStubs();
let card;
afterEach(() => {
  vi.useRealTimers();
  card?.remove();
  card = null;
});

// ---------------------------------------------------------------------------
// _t — translation
// ---------------------------------------------------------------------------

test("_t falls back through language → EN → raw key", async () => {
  card = await mountCard(makeHass({ language: "de" }));
  // A key present in EN renders the English string, never the raw key.
  expect(card._t("header")).not.toBe("header");
  expect(card._t("header")).toBe("Cover Time Based Configuration");
  // An unknown key returns the key itself.
  expect(card._t("totally.unknown.key")).toBe("totally.unknown.key");
});

test("_t uses language-specific translation when available", async () => {
  card = await mountCard(makeHass({ language: "pt" }));
  // Portuguese has a "header" override — must differ from EN
  expect(card._t("header")).toBe("Configuração de Estore Baseado em Tempo");
  expect(card._t("header")).not.toBe("Cover Time Based Configuration");
});

test("_t interpolates {placeholders}", async () => {
  card = await mountCard(makeHass());
  // "calibration.step" = "Step {step}" — substitute step
  const out = card._t("calibration.step", { step: "2" });
  expect(out).toBe("Step 2");
  expect(out).not.toContain("{step}");
});

test("_t leaves unknown placeholders alone", async () => {
  card = await mountCard(makeHass());
  // passing a replacement for an unused key — template stays intact
  const out = card._t("header", { unused: "x" });
  expect(out).not.toContain("{unused}");
});

// ---------------------------------------------------------------------------
// _switchLabel
// ---------------------------------------------------------------------------

test("_switchLabel returns pulse variant for pulse mode", async () => {
  card = await mountCard(makeHass());
  // "entities.open_switch" in pulse → "entities.open_switch_pulse"
  const pulseLbl = card._switchLabel("entities.open_switch", "pulse");
  const baseLbl = card._switchLabel("entities.open_switch", "switch");
  expect(pulseLbl).toBe("Open switch or script");
  expect(baseLbl).toBe("Open switch");
  expect(pulseLbl).not.toBe(baseLbl);
});

// ---------------------------------------------------------------------------
// _hasRequiredEntities
// ---------------------------------------------------------------------------

test("_hasRequiredEntities returns false for null config", async () => {
  card = await mountCard(makeHass());
  expect(card._hasRequiredEntities(null)).toBe(false);
});

test("_hasRequiredEntities wrapped: requires cover_entity_id", async () => {
  card = await mountCard(makeHass());
  expect(card._hasRequiredEntities({ control_mode: "wrapped" })).toBe(false);
  expect(card._hasRequiredEntities({ control_mode: "wrapped", cover_entity_id: "cover.x" })).toBe(true);
});

test("_hasRequiredEntities switch: requires open + close switches", async () => {
  card = await mountCard(makeHass());
  expect(card._hasRequiredEntities({ control_mode: "switch", open_switch_entity_id: "s.o" })).toBe(false);
  expect(card._hasRequiredEntities({
    control_mode: "switch",
    open_switch_entity_id: "s.o",
    close_switch_entity_id: "s.c",
  })).toBe(true);
});

test("_hasRequiredEntities pulse: additionally requires stop switch", async () => {
  card = await mountCard(makeHass());
  // open + close but no stop → false
  expect(card._hasRequiredEntities({
    control_mode: "pulse",
    open_switch_entity_id: "o",
    close_switch_entity_id: "c",
  })).toBe(false);
  // all three → true
  expect(card._hasRequiredEntities({
    control_mode: "pulse",
    open_switch_entity_id: "o",
    close_switch_entity_id: "c",
    stop_switch_entity_id: "s",
  })).toBe(true);
});

test("_hasRequiredEntities dual_motor (non-wrapped): requires tilt_open + tilt_close", async () => {
  card = await mountCard(makeHass());
  // switch + dual_motor but no tilt switches → false
  expect(card._hasRequiredEntities({
    control_mode: "switch",
    open_switch_entity_id: "o",
    close_switch_entity_id: "c",
    tilt_mode: "dual_motor",
  })).toBe(false);
  // with tilt_open + tilt_close → true
  expect(card._hasRequiredEntities({
    control_mode: "switch",
    open_switch_entity_id: "o",
    close_switch_entity_id: "c",
    tilt_mode: "dual_motor",
    tilt_open_switch: "to",
    tilt_close_switch: "tc",
  })).toBe(true);
});

test("_hasRequiredEntities dual_motor + pulse: also requires tilt_stop", async () => {
  card = await mountCard(makeHass());
  // pulse + dual_motor with tilt_open + tilt_close but no tilt_stop → false
  expect(card._hasRequiredEntities({
    control_mode: "pulse",
    open_switch_entity_id: "o",
    close_switch_entity_id: "c",
    stop_switch_entity_id: "s",
    tilt_mode: "dual_motor",
    tilt_open_switch: "to",
    tilt_close_switch: "tc",
  })).toBe(false);
  // with tilt_stop → true
  expect(card._hasRequiredEntities({
    control_mode: "pulse",
    open_switch_entity_id: "o",
    close_switch_entity_id: "c",
    stop_switch_entity_id: "s",
    tilt_mode: "dual_motor",
    tilt_open_switch: "to",
    tilt_close_switch: "tc",
    tilt_stop_switch: "ts",
  })).toBe(true);
});

// ---------------------------------------------------------------------------
// _updateLocal / _scheduleAutoSave
// ---------------------------------------------------------------------------

test("_updateLocal merges config and schedules a 500ms autosave", async () => {
  vi.useFakeTimers();
  card = await mountCard(makeHass(), {
    config: { control_mode: "switch" },
    selectedEntity: "cover.x",
  });
  const spy = vi.spyOn(card, "_autoSave").mockResolvedValue(undefined);
  card._updateLocal({ pulse_time: 2 });
  // Config must be merged immediately
  expect(card._config.pulse_time).toBe(2);
  // Debounced — should not fire yet
  expect(spy).not.toHaveBeenCalled();
  vi.advanceTimersByTime(499);
  expect(spy).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1);
  expect(spy).toHaveBeenCalledTimes(1);
});

test("_scheduleAutoSave debounces: only fires once after multiple rapid updates", async () => {
  vi.useFakeTimers();
  card = await mountCard(makeHass(), {
    config: { control_mode: "switch" },
    selectedEntity: "cover.x",
  });
  const spy = vi.spyOn(card, "_autoSave").mockResolvedValue(undefined);
  card._updateLocal({ pulse_time: 1 });
  card._updateLocal({ pulse_time: 2 });
  card._updateLocal({ pulse_time: 3 });
  vi.advanceTimersByTime(500);
  expect(spy).toHaveBeenCalledTimes(1);
  expect(card._config.pulse_time).toBe(3);
});

// ---------------------------------------------------------------------------
// _getEntityState
// ---------------------------------------------------------------------------

test("_getEntityState returns null when no selectedEntity", async () => {
  card = await mountCard(makeHass({ states: { "cover.x": { state: "open" } } }), {
    selectedEntity: "",
  });
  expect(card._getEntityState()).toBeNull();
});

test("_getEntityState returns null when no hass", async () => {
  card = await mountCard(makeHass());
  card.hass = null;
  expect(card._getEntityState()).toBeNull();
});

test("_getEntityState returns hass.states[selectedEntity]", async () => {
  const stateObj = { state: "open", attributes: { position: 100 } };
  card = await mountCard(makeHass({ states: { "cover.x": stateObj } }), {
    selectedEntity: "cover.x",
  });
  expect(card._getEntityState()).toBe(stateObj);
});

// ---------------------------------------------------------------------------
// _isCalibrating
// ---------------------------------------------------------------------------

test("_isCalibrating returns true when _calibratingOverride === true", async () => {
  card = await mountCard(makeHass());
  card._calibratingOverride = true;
  expect(card._isCalibrating()).toBe(true);
});

test("_isCalibrating returns false when _calibratingOverride === false", async () => {
  card = await mountCard(makeHass({
    states: { "cover.x": { state: "open", attributes: { calibration_active: true } } },
  }), { selectedEntity: "cover.x" });
  card._calibratingOverride = false;
  // Even though entity says calibration_active, override wins
  expect(card._isCalibrating()).toBe(false);
});

test("_isCalibrating reads entity calibration_active when override is undefined", async () => {
  card = await mountCard(makeHass({
    states: {
      "cover.x": { state: "open", attributes: { calibration_active: true } },
    },
  }), { selectedEntity: "cover.x" });
  // No _calibratingOverride set → should read from entity state
  expect(card._isCalibrating()).toBe(true);
});

test("_isCalibrating returns false when entity calibration_active is not true", async () => {
  card = await mountCard(makeHass({
    states: {
      "cover.x": { state: "open", attributes: {} },
    },
  }), { selectedEntity: "cover.x" });
  expect(card._isCalibrating()).toBe(false);
});

// ---------------------------------------------------------------------------
// _getCalibrationHint
// ---------------------------------------------------------------------------

test("_getCalibrationHint min_movement_time returns hints.min_movement_time", async () => {
  card = await mountCard(makeHass(), {
    config: { tilt_mode: "none" },
  });
  // Stub the shadowRoot query to return a fake select
  card.shadowRoot.querySelector = () => ({ value: "min_movement_time" });
  const hint = card._getCalibrationHint();
  expect(hint).toBe("Click Finish as soon as you notice the cover moving.");
});

test("_getCalibrationHint travel_startup_delay maps to travel_time_close when knownPosition=open", async () => {
  card = await mountCard(makeHass(), {
    config: { tilt_mode: "none" },
    knownPosition: "open",
  });
  card.shadowRoot.querySelector = () => ({ value: "travel_startup_delay" });
  const hint = card._getCalibrationHint();
  // effectiveAttr = travel_time_close, tiltMode = none
  expect(hint).toBe("Click Finish when the cover is fully closed.");
});

test("_getCalibrationHint travel_startup_delay maps to travel_time_open when knownPosition=closed", async () => {
  card = await mountCard(makeHass(), {
    config: { tilt_mode: "none" },
    knownPosition: "closed",
  });
  card.shadowRoot.querySelector = () => ({ value: "travel_startup_delay" });
  const hint = card._getCalibrationHint();
  expect(hint).toBe("Click Finish when the cover is fully open.");
});

test("_getCalibrationHint tilt_startup_delay maps to tilt_time_close when knownPosition=closed_tilt_open", async () => {
  card = await mountCard(makeHass(), {
    config: { tilt_mode: "dual_motor" },
    knownPosition: "closed_tilt_open",
  });
  card.shadowRoot.querySelector = () => ({ value: "tilt_startup_delay" });
  const hint = card._getCalibrationHint();
  // effectiveAttr = tilt_time_close, tiltMode = dual_motor
  expect(hint).toBe("Start with cover closed and slats open. Click Finish when the slats are fully closed.");
});

test("_getCalibrationHint tilt_startup_delay maps to tilt_time_open when knownPosition=closed", async () => {
  card = await mountCard(makeHass(), {
    config: { tilt_mode: "dual_motor" },
    knownPosition: "closed",
  });
  card.shadowRoot.querySelector = () => ({ value: "tilt_startup_delay" });
  const hint = card._getCalibrationHint();
  // effectiveAttr = tilt_time_open, tiltMode = dual_motor
  expect(hint).toBe("Start with both cover and slats closed. Click Finish when the slats are fully open.");
});

test("_getCalibrationHint returns tiltMode-specific hint for direct attributes", async () => {
  card = await mountCard(makeHass(), {
    config: { tilt_mode: "sequential_close" },
  });
  card.shadowRoot.querySelector = () => ({ value: "travel_time_close" });
  const hint = card._getCalibrationHint();
  expect(hint).toBe(
    "Start with cover fully open. Click Finish when the cover is fully closed, before the slats start tilting."
  );
});

test("_getCalibrationHint differs across tilt modes for same attribute", async () => {
  // same attribute, different tilt modes → different hints
  card = await mountCard(makeHass(), { config: { tilt_mode: "none" } });
  card.shadowRoot.querySelector = () => ({ value: "travel_time_close" });
  const hintNone = card._getCalibrationHint();

  card._config = { tilt_mode: "dual_motor" };
  const hintDual = card._getCalibrationHint();

  expect(hintNone).not.toBe(hintDual);
});

// ---------------------------------------------------------------------------
// _coverSupportsNativeTilt
// ---------------------------------------------------------------------------

test("_coverSupportsNativeTilt returns false for undefined entityId", async () => {
  card = await mountCard(makeHass());
  expect(card._coverSupportsNativeTilt(undefined)).toBe(false);
});

test("_coverSupportsNativeTilt returns false for entityId not in states", async () => {
  card = await mountCard(makeHass({ states: {} }));
  expect(card._coverSupportsNativeTilt("cover.missing")).toBe(false);
});

test("_coverSupportsNativeTilt returns true when bit 16 (OPEN_TILT) is set", async () => {
  card = await mountCard(makeHass({
    states: {
      "cover.tilt16": { state: "open", attributes: { supported_features: 16 } },
    },
  }));
  expect(card._coverSupportsNativeTilt("cover.tilt16")).toBe(true);
});

test("_coverSupportsNativeTilt returns true when bit 32 (CLOSE_TILT) is set", async () => {
  card = await mountCard(makeHass({
    states: {
      "cover.tilt32": { state: "open", attributes: { supported_features: 32 } },
    },
  }));
  expect(card._coverSupportsNativeTilt("cover.tilt32")).toBe(true);
});

test("_coverSupportsNativeTilt returns true when both tilt bits set", async () => {
  card = await mountCard(makeHass({
    states: {
      "cover.tilts": { state: "open", attributes: { supported_features: 48 } },
    },
  }));
  expect(card._coverSupportsNativeTilt("cover.tilts")).toBe(true);
});

test("_coverSupportsNativeTilt returns false when no tilt bits set", async () => {
  card = await mountCard(makeHass({
    states: {
      "cover.notilt": { state: "open", attributes: { supported_features: 15 } },
    },
  }));
  expect(card._coverSupportsNativeTilt("cover.notilt")).toBe(false);
});

// ---------------------------------------------------------------------------
// _hasTiltMotor
// ---------------------------------------------------------------------------

test("_hasTiltMotor returns false when no config", async () => {
  card = await mountCard(makeHass(), { config: null });
  expect(card._hasTiltMotor()).toBe(false);
});

test("_hasTiltMotor returns false when tilt_mode is not dual_motor", async () => {
  card = await mountCard(makeHass(), {
    config: { control_mode: "switch", tilt_mode: "sequential_close" },
  });
  expect(card._hasTiltMotor()).toBe(false);
});

test("_hasTiltMotor returns true for wrapped + dual_motor (no extra entities needed)", async () => {
  card = await mountCard(makeHass(), {
    config: { control_mode: "wrapped", tilt_mode: "dual_motor" },
  });
  expect(card._hasTiltMotor()).toBe(true);
});

test("_hasTiltMotor returns false for pulse + dual_motor without tilt switches", async () => {
  card = await mountCard(makeHass(), {
    config: {
      control_mode: "pulse",
      tilt_mode: "dual_motor",
      tilt_open_switch: "to",
      tilt_close_switch: "tc",
      // tilt_stop_switch missing
    },
  });
  expect(card._hasTiltMotor()).toBe(false);
});

test("_hasTiltMotor returns true for pulse + dual_motor with all three tilt switches", async () => {
  card = await mountCard(makeHass(), {
    config: {
      control_mode: "pulse",
      tilt_mode: "dual_motor",
      tilt_open_switch: "to",
      tilt_close_switch: "tc",
      tilt_stop_switch: "ts",
    },
  });
  expect(card._hasTiltMotor()).toBe(true);
});

test("_hasTiltMotor returns false for switch + dual_motor without tilt switches", async () => {
  card = await mountCard(makeHass(), {
    config: {
      control_mode: "switch",
      tilt_mode: "dual_motor",
      // tilt switches missing
    },
  });
  expect(card._hasTiltMotor()).toBe(false);
});

test("_hasTiltMotor returns true for switch + dual_motor with tilt_open + tilt_close", async () => {
  card = await mountCard(makeHass(), {
    config: {
      control_mode: "switch",
      tilt_mode: "dual_motor",
      tilt_open_switch: "to",
      tilt_close_switch: "tc",
    },
  });
  expect(card._hasTiltMotor()).toBe(true);
});

// ---------------------------------------------------------------------------
// getCardSize / getGridOptions / setConfig
// ---------------------------------------------------------------------------

test("getCardSize returns 8", async () => {
  card = await mountCard(makeHass());
  expect(card.getCardSize()).toBe(8);
});

test("getGridOptions returns the expected options object", async () => {
  card = await mountCard(makeHass());
  expect(card.getGridOptions()).toEqual({ columns: "full", min_columns: 6, min_rows: 4 });
});

test("setConfig does not throw", async () => {
  card = await mountCard(makeHass());
  expect(() => card.setConfig({})).not.toThrow();
  expect(() => card.setConfig({ some: "config" })).not.toThrow();
});
