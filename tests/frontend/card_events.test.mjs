/**
 * Characterization tests for cover-time-based-card.js event handlers.
 *
 * These tests LOCK IN the card's current behavior. The 4 source files under
 * custom_components/cover_time_based/frontend/ are off-limits for edits.
 *
 * Run: npm run test:fe -- tests/frontend/card_events.test.mjs
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

/**
 * Spy on _updateLocal so tests can inspect what the handler passes in
 * without triggering real autosave timers. The mock also keeps _config
 * in sync so handlers that read _config (e.g. dual_motor defaults) work
 * correctly across multiple calls.
 */
function captureUpdates(c) {
  const updates = [];
  vi.spyOn(c, "_updateLocal").mockImplementation((u) => {
    updates.push(u);
    c._config = { ...c._config, ...u };
  });
  return updates;
}

// ---------------------------------------------------------------------------
// Device picker — the real @value-changed handler inline in card-render.js's
// renderEntityPicker(). (There is no _onEntityChange method on the card class
// any more — it was dead code nothing wired up; these tests exercise the
// live, rendered picker instead, the way
// "live entity picker: switching device clears..." in card_calibration.test.mjs
// already does.)
// ---------------------------------------------------------------------------

function firePickerValueChanged(card, detail) {
  const picker = card.shadowRoot.querySelector("ha-entity-picker");
  picker.dispatchEvent(new CustomEvent("value-changed", { detail }));
  return picker;
}

test("picker value-changed with a value sets _selectedEntity, nulls _config, calls _loadConfig", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "switch" } });
  const loadSpy = vi.spyOn(card, "_loadConfig").mockResolvedValue(undefined);
  firePickerValueChanged(card, { value: "cover.living_room" });
  expect(card._selectedEntity).toBe("cover.living_room");
  expect(card._config).toBeNull();
  expect(loadSpy).toHaveBeenCalledTimes(1);
});

test("picker value-changed with empty value sets _selectedEntity but does NOT call _loadConfig", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "switch" }, selectedEntity: "cover.x" });
  const loadSpy = vi.spyOn(card, "_loadConfig").mockResolvedValue(undefined);
  firePickerValueChanged(card, { value: "" });
  expect(card._selectedEntity).toBe("");
  expect(card._config).toBeNull();
  expect(loadSpy).not.toHaveBeenCalled();
});

test("picker value-changed with the currently-selected entity is a no-op", async () => {
  // The live handler short-circuits when the picker fires with the value it
  // already has (e.g. a spurious change event) — the dead _onEntityChange
  // method never had this guard at all.
  card = await mountCard(makeHass(), { config: { control_mode: "switch" }, selectedEntity: "cover.x" });
  const loadSpy = vi.spyOn(card, "_loadConfig").mockResolvedValue(undefined);
  const flushSpy = vi.spyOn(card, "_flushAutoSave");
  firePickerValueChanged(card, { value: "cover.x" });
  expect(card._selectedEntity).toBe("cover.x");
  expect(loadSpy).not.toHaveBeenCalled();
  expect(flushSpy).not.toHaveBeenCalled();
});

test("picker value-changed to a new entity flushes the outgoing edit and resets load error/position/tab/calibration latches", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "switch" }, selectedEntity: "cover.old" });
  const loadSpy = vi.spyOn(card, "_loadConfig").mockResolvedValue(undefined);
  const flushSpy = vi.spyOn(card, "_flushAutoSave").mockImplementation(() => {});
  card._loadError = "stale error";
  card._knownPosition = "open";
  card._activeTab = "calibration";
  card._calibratingOverride = false;
  card._sawCalibrationActive = true;

  firePickerValueChanged(card, { value: "cover.new" });

  expect(flushSpy).toHaveBeenCalledTimes(1);
  expect(card._selectedEntity).toBe("cover.new");
  expect(card._config).toBeNull();
  expect(card._loadError).toBeNull();
  expect(card._knownPosition).toBe("unknown");
  expect(card._calibratingOverride).toBeUndefined();
  expect(card._sawCalibrationActive).toBe(false);
  expect(card._activeTab).toBe("device");
  expect(loadSpy).toHaveBeenCalledTimes(1);
});

test("picker value-changed while calibrating and the user cancels the confirm reverts the picker and leaves the selection untouched", async () => {
  window.confirm = vi.fn(() => false);
  card = await mountCard(makeHass(), { config: { control_mode: "switch" }, selectedEntity: "cover.x" });
  const stopSpy = vi.spyOn(card, "_onStopCalibration").mockResolvedValue(undefined);
  const loadSpy = vi.spyOn(card, "_loadConfig").mockResolvedValue(undefined);
  card._calibratingOverride = true; // _isCalibrating() === true

  const picker = firePickerValueChanged(card, { value: "cover.new" });

  expect(window.confirm).toHaveBeenCalled();
  expect(picker.value).toBe("cover.x"); // reverted
  expect(card._selectedEntity).toBe("cover.x"); // unchanged
  expect(stopSpy).not.toHaveBeenCalled();
  expect(loadSpy).not.toHaveBeenCalled();
});

test("picker value-changed while calibrating and the user confirms stops calibration and proceeds with the swap", async () => {
  window.confirm = vi.fn(() => true);
  card = await mountCard(makeHass(), { config: { control_mode: "switch" }, selectedEntity: "cover.x" });
  const stopSpy = vi.spyOn(card, "_onStopCalibration").mockResolvedValue(undefined);
  const loadSpy = vi.spyOn(card, "_loadConfig").mockResolvedValue(undefined);
  card._calibratingOverride = true; // _isCalibrating() === true

  firePickerValueChanged(card, { value: "cover.new" });

  expect(window.confirm).toHaveBeenCalled();
  expect(stopSpy).toHaveBeenCalledWith(true);
  expect(card._selectedEntity).toBe("cover.new");
  expect(loadSpy).toHaveBeenCalledTimes(1);
});

// ---------------------------------------------------------------------------
// _onControlModeChange
// ---------------------------------------------------------------------------

test("_onControlModeChange to wrapped clears switch slots and resets dual_motor tilt", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "switch", tilt_mode: "dual_motor" } });
  const updates = captureUpdates(card);
  card._onControlModeChange({ target: { value: "wrapped" } });
  expect(updates[0].control_mode).toBe("wrapped");
  expect(updates[0].open_switch_entity_id).toBeNull();   // cleared by clearedEntitiesForMode
  expect(updates[0].close_switch_entity_id).toBeNull();
  expect(updates[0].stop_switch_entity_id).toBeNull();
  expect(updates[0].tilt_open_switch).toBeNull();
  expect(updates[0].tilt_close_switch).toBeNull();
  expect(updates[0].tilt_stop_switch).toBeNull();
  expect(updates[0].tilt_mode).toBe("none");             // dual_motor reset on wrapped
});

test("_onControlModeChange to wrapped with non-dual_motor tilt does NOT reset tilt", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "switch", tilt_mode: "sequential_close" } });
  const updates = captureUpdates(card);
  card._onControlModeChange({ target: { value: "wrapped" } });
  expect(updates[0].control_mode).toBe("wrapped");
  // tilt_mode should NOT be cleared since it wasn't dual_motor
  expect(updates[0].tilt_mode).toBeUndefined();
});

test("_onControlModeChange to switch clears cover_entity_id and stop_switch_entity_id", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "wrapped" } });
  const updates = captureUpdates(card);
  card._onControlModeChange({ target: { value: "switch" } });
  expect(updates[0].control_mode).toBe("switch");
  expect(updates[0].cover_entity_id).toBeNull();        // cleared by clearedEntitiesForMode
  expect(updates[0].stop_switch_entity_id).toBeNull();   // non-pulse clears stop
  expect(updates[0].tilt_stop_switch).toBeNull();
});

test("_onControlModeChange to pulse clears cover_entity_id but keeps stop_switch", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "switch" } });
  const updates = captureUpdates(card);
  card._onControlModeChange({ target: { value: "pulse" } });
  expect(updates[0].control_mode).toBe("pulse");
  expect(updates[0].cover_entity_id).toBeNull();
  // pulse mode does NOT clear stop_switch_entity_id
  expect(updates[0].stop_switch_entity_id).toBeUndefined();
});

test("_onControlModeChange to toggle clears cover_entity_id and stop_switch_entity_id", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "switch" } });
  const updates = captureUpdates(card);
  card._onControlModeChange({ target: { value: "toggle" } });
  expect(updates[0].control_mode).toBe("toggle");
  expect(updates[0].cover_entity_id).toBeNull();
  expect(updates[0].stop_switch_entity_id).toBeNull();
});

// F4: leaving pulse mode must not let a script entity survive in a switch
// slot — every subsequent save is silently rejected by the backend otherwise.
test("_onControlModeChange from pulse to toggle nulls a script-valued switch slot", async () => {
  card = await mountCard(makeHass(), {
    config: { control_mode: "pulse", open_switch_entity_id: "script.ir_open" },
  });
  const updates = captureUpdates(card);
  card._onControlModeChange({ target: { value: "toggle" } });
  expect(updates[0].control_mode).toBe("toggle");
  expect(updates[0].open_switch_entity_id).toBeNull();
});

test("_onControlModeChange from pulse to toggle leaves a switch-valued slot alone", async () => {
  card = await mountCard(makeHass(), {
    config: { control_mode: "pulse", open_switch_entity_id: "switch.open" },
  });
  const updates = captureUpdates(card);
  card._onControlModeChange({ target: { value: "toggle" } });
  expect(updates[0].control_mode).toBe("toggle");
  // switch.open is a valid value everywhere — must survive the mode switch
  expect(updates[0].open_switch_entity_id).toBeUndefined();
});

test("_onControlModeChange staying on pulse does not touch script-valued slots", async () => {
  card = await mountCard(makeHass(), {
    config: { control_mode: "pulse", open_switch_entity_id: "script.ir_open" },
  });
  const updates = captureUpdates(card);
  card._onControlModeChange({ target: { value: "pulse" } });
  expect(updates[0].control_mode).toBe("pulse");
  expect(updates[0].open_switch_entity_id).toBeUndefined();
});

// ---------------------------------------------------------------------------
// _onPulseTimeChange
// ---------------------------------------------------------------------------

test("_onPulseTimeChange ignores sub-0.1 / NaN, accepts valid", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "pulse" } });
  const updates = captureUpdates(card);
  card._onPulseTimeChange({ target: { value: "0.05" } });   // rejected (< 0.1)
  card._onPulseTimeChange({ target: { value: "abc" } });    // rejected (NaN)
  card._onPulseTimeChange({ target: { value: "1.5" } });    // accepted
  expect(updates).toEqual([{ pulse_time: 1.5 }]);
});

test("_onPulseTimeChange accepts exactly 0.1", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "pulse" } });
  const updates = captureUpdates(card);
  card._onPulseTimeChange({ target: { value: "0.1" } });
  expect(updates).toEqual([{ pulse_time: 0.1 }]);
});

test("_onPulseTimeChange rejects 0", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "pulse" } });
  const updates = captureUpdates(card);
  card._onPulseTimeChange({ target: { value: "0" } });
  expect(updates).toHaveLength(0);
});

test("_onPulseTimeChange rejects negative", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "pulse" } });
  const updates = captureUpdates(card);
  card._onPulseTimeChange({ target: { value: "-1" } });
  expect(updates).toHaveLength(0);
});

// ---------------------------------------------------------------------------
// _onSwitchEntityChange
// ---------------------------------------------------------------------------

test("_onSwitchEntityChange with a value sets the named field", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "switch" } });
  const updates = captureUpdates(card);
  card._onSwitchEntityChange("open_switch_entity_id", { detail: { value: "switch.open" } });
  expect(updates[0]).toEqual({ open_switch_entity_id: "switch.open" });
});

test("_onSwitchEntityChange with empty value nulls the named field", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "switch", open_switch_entity_id: "switch.open" } });
  const updates = captureUpdates(card);
  card._onSwitchEntityChange("open_switch_entity_id", { detail: { value: "" } });
  expect(updates[0]).toEqual({ open_switch_entity_id: null });
});

test("_onSwitchEntityChange with no detail falls back to e.target.value", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "switch" } });
  const updates = captureUpdates(card);
  card._onSwitchEntityChange("close_switch_entity_id", { target: { value: "switch.close" } });
  expect(updates[0]).toEqual({ close_switch_entity_id: "switch.close" });
});

test("_onSwitchEntityChange works for arbitrary field names", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "switch" } });
  const updates = captureUpdates(card);
  card._onSwitchEntityChange("tilt_open_switch", { detail: { value: "switch.tilt_open" } });
  expect(updates[0]).toEqual({ tilt_open_switch: "switch.tilt_open" });
});

// ---------------------------------------------------------------------------
// _onCoverEntityChange
// ---------------------------------------------------------------------------

test("_onCoverEntityChange with dual_motor + confirmed-tilt-less cover resets tilt config", async () => {
  // A cover that is available with no tilt bits → coverConfirmedWithoutTilt returns true
  const hass = makeHass({
    states: {
      "cover.notilt": { state: "open", attributes: { supported_features: 0 } },
    },
  });
  card = await mountCard(hass, { config: { control_mode: "switch", tilt_mode: "dual_motor" } });
  const updates = captureUpdates(card);
  card._onCoverEntityChange({ detail: { value: "cover.notilt" } });
  expect(updates[0].cover_entity_id).toBe("cover.notilt");
  // clearedTiltConfig keys should be present
  expect(updates[0].tilt_mode).toBe("none");
  expect(updates[0].tilt_open_switch).toBeNull();
  expect(updates[0].tilt_close_switch).toBeNull();
  expect(updates[0].tilt_stop_switch).toBeNull();
  expect(updates[0].safe_tilt_position).toBeNull();
  expect(updates[0].max_tilt_allowed_position).toBeNull();
  expect(updates[0].tilt_time_close).toBeNull();
  expect(updates[0].tilt_time_open).toBeNull();
  expect(updates[0].close_includes_tilt).toBeNull();
});

test("_onCoverEntityChange with dual_motor + tilt-capable cover sets only cover_entity_id", async () => {
  // A cover with OPEN_TILT (bit 16) set → coverConfirmedWithoutTilt returns false
  const hass = makeHass({
    states: {
      "cover.withtilt": { state: "open", attributes: { supported_features: 16 } },
    },
  });
  card = await mountCard(hass, { config: { control_mode: "switch", tilt_mode: "dual_motor" } });
  const updates = captureUpdates(card);
  card._onCoverEntityChange({ detail: { value: "cover.withtilt" } });
  expect(updates[0]).toEqual({ cover_entity_id: "cover.withtilt" });
  expect(updates[0].tilt_mode).toBeUndefined();
});

test("_onCoverEntityChange with dual_motor + unavailable cover does NOT reset tilt", async () => {
  // An unavailable cover → coverConfirmedWithoutTilt returns false (protects config)
  const hass = makeHass({
    states: {
      "cover.offline": { state: "unavailable", attributes: { supported_features: 0 } },
    },
  });
  card = await mountCard(hass, { config: { control_mode: "switch", tilt_mode: "dual_motor" } });
  const updates = captureUpdates(card);
  card._onCoverEntityChange({ detail: { value: "cover.offline" } });
  expect(updates[0]).toEqual({ cover_entity_id: "cover.offline" });
  expect(updates[0].tilt_mode).toBeUndefined();
});

test("_onCoverEntityChange without dual_motor tilt just sets cover_entity_id", async () => {
  const hass = makeHass({
    states: {
      "cover.notilt": { state: "open", attributes: { supported_features: 0 } },
    },
  });
  card = await mountCard(hass, { config: { control_mode: "wrapped", tilt_mode: "sequential_close" } });
  const updates = captureUpdates(card);
  card._onCoverEntityChange({ detail: { value: "cover.notilt" } });
  expect(updates[0]).toEqual({ cover_entity_id: "cover.notilt" });
});

test("_onCoverEntityChange with empty value sets cover_entity_id to null", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "wrapped" } });
  const updates = captureUpdates(card);
  card._onCoverEntityChange({ detail: { value: "" } });
  expect(updates[0]).toEqual({ cover_entity_id: null });
});

// ---------------------------------------------------------------------------
// _onTiltModeChange
// ---------------------------------------------------------------------------

test("_onTiltModeChange='none' clears all tilt config", async () => {
  card = await mountCard(makeHass(), { config: { control_mode: "switch", tilt_mode: "dual_motor" } });
  const updates = captureUpdates(card);
  card._onTiltModeChange({ target: { value: "none" } });
  expect(updates[0].tilt_mode).toBe("none");
  expect(updates[0].tilt_open_switch).toBeNull();
  expect(updates[0].tilt_close_switch).toBeNull();
  expect(updates[0].tilt_stop_switch).toBeNull();
  expect(updates[0].tilt_time_close).toBeNull();
  expect(updates[0].tilt_time_open).toBeNull();
  expect(updates[0].tilt_startup_delay).toBeNull();
  expect(updates[0].safe_tilt_position).toBeNull();
  expect(updates[0].max_tilt_allowed_position).toBeNull();
  expect(updates[0].close_includes_tilt).toBeNull();
});

test("_onTiltModeChange='sequential_close' clears dual_motor fields, defaults close_includes_tilt true", async () => {
  card = await mountCard(makeHass(), {
    config: {
      control_mode: "switch",
      tilt_mode: "dual_motor",
      safe_tilt_position: 100,
      max_tilt_allowed_position: 0,
      tilt_open_switch: "switch.to",
      tilt_close_switch: "switch.tc",
      tilt_stop_switch: "switch.ts",
      close_includes_tilt: null,
    },
  });
  const updates = captureUpdates(card);
  card._onTiltModeChange({ target: { value: "sequential_close" } });
  expect(updates[0].tilt_mode).toBe("sequential_close");
  expect(updates[0].safe_tilt_position).toBeNull();
  expect(updates[0].max_tilt_allowed_position).toBeNull();
  expect(updates[0].tilt_open_switch).toBeNull();
  expect(updates[0].tilt_close_switch).toBeNull();
  expect(updates[0].tilt_stop_switch).toBeNull();
  expect(updates[0].close_includes_tilt).toBe(true);  // defaulted
});

test("_onTiltModeChange='sequential_close' does NOT override existing close_includes_tilt when set to false", async () => {
  // close_includes_tilt == null is the guard; false is not == null, so it's left alone
  card = await mountCard(makeHass(), {
    config: { control_mode: "switch", tilt_mode: "none", close_includes_tilt: false },
  });
  const updates = captureUpdates(card);
  card._onTiltModeChange({ target: { value: "sequential_close" } });
  // false != null so close_includes_tilt is NOT added to updates
  expect(updates[0].close_includes_tilt).toBeUndefined();
});

test("_onTiltModeChange='sequential_open' clears dual_motor fields, sets close_includes_tilt null", async () => {
  card = await mountCard(makeHass(), {
    config: {
      control_mode: "switch",
      tilt_mode: "dual_motor",
      safe_tilt_position: 100,
      max_tilt_allowed_position: 0,
      tilt_open_switch: "switch.to",
      tilt_close_switch: "switch.tc",
      tilt_stop_switch: "switch.ts",
    },
  });
  const updates = captureUpdates(card);
  card._onTiltModeChange({ target: { value: "sequential_open" } });
  expect(updates[0].tilt_mode).toBe("sequential_open");
  expect(updates[0].safe_tilt_position).toBeNull();
  expect(updates[0].max_tilt_allowed_position).toBeNull();
  expect(updates[0].tilt_open_switch).toBeNull();
  expect(updates[0].tilt_close_switch).toBeNull();
  expect(updates[0].tilt_stop_switch).toBeNull();
  expect(updates[0].close_includes_tilt).toBeNull();
});

test("_onTiltModeChange='dual_motor' defaults safe_tilt_position=100, max_tilt_allowed_position=0, close_includes_tilt=true when all null", async () => {
  card = await mountCard(makeHass(), {
    config: {
      control_mode: "switch",
      tilt_mode: "none",
      safe_tilt_position: null,
      max_tilt_allowed_position: null,
      close_includes_tilt: null,
    },
  });
  const updates = captureUpdates(card);
  card._onTiltModeChange({ target: { value: "dual_motor" } });
  expect(updates[0].tilt_mode).toBe("dual_motor");
  expect(updates[0].safe_tilt_position).toBe(100);
  expect(updates[0].max_tilt_allowed_position).toBe(0);
  expect(updates[0].close_includes_tilt).toBe(true);
});

test("_onTiltModeChange='dual_motor' does NOT override existing safe_tilt_position or max_tilt_allowed_position", async () => {
  card = await mountCard(makeHass(), {
    config: {
      control_mode: "switch",
      tilt_mode: "none",
      safe_tilt_position: 50,
      max_tilt_allowed_position: 25,
      close_includes_tilt: null,
    },
  });
  const updates = captureUpdates(card);
  card._onTiltModeChange({ target: { value: "dual_motor" } });
  expect(updates[0].tilt_mode).toBe("dual_motor");
  // Existing non-null values should NOT be overridden
  expect(updates[0].safe_tilt_position).toBeUndefined();
  expect(updates[0].max_tilt_allowed_position).toBeUndefined();
  // close_includes_tilt was null → defaulted
  expect(updates[0].close_includes_tilt).toBe(true);
});

test("_onTiltModeChange='dual_motor' does NOT override existing close_includes_tilt", async () => {
  card = await mountCard(makeHass(), {
    config: {
      control_mode: "switch",
      tilt_mode: "none",
      safe_tilt_position: null,
      max_tilt_allowed_position: null,
      close_includes_tilt: true,
    },
  });
  const updates = captureUpdates(card);
  card._onTiltModeChange({ target: { value: "dual_motor" } });
  // close_includes_tilt is already true (not null) → should not appear in updates
  expect(updates[0].close_includes_tilt).toBeUndefined();
});

test("_onTiltModeChange='inline' clears dual_motor fields, sets close_includes_tilt null", async () => {
  card = await mountCard(makeHass(), {
    config: {
      control_mode: "switch",
      tilt_mode: "dual_motor",
      safe_tilt_position: 100,
      max_tilt_allowed_position: 0,
      tilt_open_switch: "switch.to",
      tilt_close_switch: "switch.tc",
      tilt_stop_switch: "switch.ts",
    },
  });
  const updates = captureUpdates(card);
  card._onTiltModeChange({ target: { value: "inline" } });
  expect(updates[0].tilt_mode).toBe("inline");
  expect(updates[0].safe_tilt_position).toBeNull();
  expect(updates[0].max_tilt_allowed_position).toBeNull();
  expect(updates[0].tilt_open_switch).toBeNull();
  expect(updates[0].tilt_close_switch).toBeNull();
  expect(updates[0].tilt_stop_switch).toBeNull();
  expect(updates[0].close_includes_tilt).toBeNull();
});

// ---------------------------------------------------------------------------
// _onCreateNew
// ---------------------------------------------------------------------------

test("_onCreateNew pushes the helpers-add URL and fires location-changed", async () => {
  card = await mountCard(makeHass());
  const push = vi.spyOn(window.history, "pushState").mockImplementation(() => {});
  const dispatch = vi.spyOn(window, "dispatchEvent");
  card._onCreateNew();
  expect(push).toHaveBeenCalledWith(null, "", "/config/helpers/add?domain=cover_time_based");
  expect(dispatch).toHaveBeenCalled();
  // Verify the dispatched event is 'location-changed'
  const dispatchedEvent = dispatch.mock.calls[0][0];
  expect(dispatchedEvent.type).toBe("location-changed");
});

// ---------------------------------------------------------------------------
// _toggleHelp / _closeHelp
// ---------------------------------------------------------------------------

test("_toggleHelp toggles, _closeHelp clears", async () => {
  card = await mountCard(makeHass());
  card._toggleHelp("k");
  expect(card._openHelp).toBe("k");
  card._toggleHelp("k");
  expect(card._openHelp).toBeNull();
  card._toggleHelp("k");
  card._closeHelp();
  expect(card._openHelp).toBeNull();
});

test("_toggleHelp to a different key replaces the open key", async () => {
  card = await mountCard(makeHass());
  card._toggleHelp("key1");
  expect(card._openHelp).toBe("key1");
  card._toggleHelp("key2");
  expect(card._openHelp).toBe("key2");
});

test("_closeHelp nulls _openHelp even when already null", async () => {
  card = await mountCard(makeHass());
  expect(card._openHelp).toBeNull();
  card._closeHelp();
  expect(card._openHelp).toBeNull();
});

test("_toggleHelp with same key twice returns to null", async () => {
  card = await mountCard(makeHass());
  card._toggleHelp("help_section");
  card._toggleHelp("help_section");
  expect(card._openHelp).toBeNull();
});
