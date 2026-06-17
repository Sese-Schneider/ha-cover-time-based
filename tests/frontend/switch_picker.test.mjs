/**
 * Tests for switchPickerDomains / switchLabelKey — pulse-mode picker helpers.
 *
 * Run: node --test tests/frontend/switch_picker.test.mjs
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  switchPickerDomains,
  switchLabelKey,
  showsPulseTime,
  clearedEntitiesForMode,
  clearedTiltConfig,
  coverHasNativeTilt,
  coverConfirmedWithoutTilt,
} from "../../custom_components/cover_time_based/frontend/entity-filter.js";

test("pulse mode allows switch and script domains", () => {
  assert.deepEqual(switchPickerDomains("pulse"), ["switch", "script"]);
});

test("the pulse-time field shows only for pulse mode", () => {
  // Toggle relays are momentary/self-releasing and no longer use pulse_time,
  // so only pulse mode configures it.
  assert.equal(showsPulseTime("pulse"), true);
  assert.equal(showsPulseTime("toggle"), false);
  assert.equal(showsPulseTime("switch"), false);
  assert.equal(showsPulseTime("wrapped"), false);
  assert.equal(showsPulseTime(undefined), false);
});

test("non-pulse modes allow only the switch domain", () => {
  assert.deepEqual(switchPickerDomains("switch"), ["switch"]);
  assert.deepEqual(switchPickerDomains("toggle"), ["switch"]);
  assert.deepEqual(switchPickerDomains("wrapped"), ["switch"]);
  assert.deepEqual(switchPickerDomains(undefined), ["switch"]);
});

test("pulse mode maps a label key to its _pulse variant", () => {
  assert.equal(
    switchLabelKey("entities.open_switch", "pulse"),
    "entities.open_switch_pulse"
  );
});

test("non-pulse modes use the base label key unchanged", () => {
  assert.equal(switchLabelKey("entities.open_switch", "switch"), "entities.open_switch");
  assert.equal(switchLabelKey("entities.open_switch", undefined), "entities.open_switch");
});

test("switching to wrapped clears every switch-based entity slot", () => {
  const cleared = clearedEntitiesForMode("wrapped");
  // All six switch/tilt slots nulled — including tilt_open/tilt_close, which
  // are otherwise stale leftovers that would trip the backend script guard.
  assert.deepEqual(cleared, {
    open_switch_entity_id: null,
    close_switch_entity_id: null,
    stop_switch_entity_id: null,
    tilt_open_switch: null,
    tilt_close_switch: null,
    tilt_stop_switch: null,
  });
});

test("switching to switch/toggle clears the cover and the pulse-only stop slots", () => {
  for (const mode of ["switch", "toggle"]) {
    assert.deepEqual(clearedEntitiesForMode(mode), {
      cover_entity_id: null,
      stop_switch_entity_id: null,
      tilt_stop_switch: null,
    });
  }
});

test("switching to pulse only clears the wrapped cover slot", () => {
  assert.deepEqual(clearedEntitiesForMode("pulse"), {
    cover_entity_id: null,
  });
});

test("clearedTiltConfig resets tilt mode and every tilt field", () => {
  // Used when tilt is set to "none", and when a context change (control mode
  // or wrapped cover entity) invalidates a dual_motor selection.
  assert.deepEqual(clearedTiltConfig(), {
    tilt_mode: "none",
    tilt_time_close: null,
    tilt_time_open: null,
    tilt_startup_delay: null,
    safe_tilt_position: null,
    max_tilt_allowed_position: null,
    tilt_open_switch: null,
    tilt_close_switch: null,
    tilt_stop_switch: null,
    close_includes_tilt: null,
  });
});

// OPEN_TILT=16, CLOSE_TILT=32
test("coverHasNativeTilt reads the tilt feature bits", () => {
  assert.equal(coverHasNativeTilt({ attributes: { supported_features: 16 } }), true);
  assert.equal(coverHasNativeTilt({ attributes: { supported_features: 32 } }), true);
  assert.equal(
    coverHasNativeTilt({ attributes: { supported_features: 1 | 2 | 8 } }),
    false
  );
  assert.equal(coverHasNativeTilt({ attributes: {} }), false);
  assert.equal(coverHasNativeTilt(null), false);
  assert.equal(coverHasNativeTilt(undefined), false);
});

test("coverConfirmedWithoutTilt only confirms for an available, tilt-less cover", () => {
  // Positively lacks tilt and is available → safe to reset dual_motor.
  assert.equal(
    coverConfirmedWithoutTilt({ state: "open", attributes: { supported_features: 11 } }),
    true
  );
  // Has tilt → not "without tilt".
  assert.equal(
    coverConfirmedWithoutTilt({ state: "open", attributes: { supported_features: 16 } }),
    false
  );
  // Unavailable / unknown / missing → can't confirm; must NOT reset a valid config.
  assert.equal(
    coverConfirmedWithoutTilt({ state: "unavailable", attributes: {} }),
    false
  );
  assert.equal(coverConfirmedWithoutTilt({ state: "unknown", attributes: {} }), false);
  assert.equal(coverConfirmedWithoutTilt(null), false);
  assert.equal(coverConfirmedWithoutTilt(undefined), false);
});
