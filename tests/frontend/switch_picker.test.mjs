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
  clearedEntitiesForMode,
} from "../../custom_components/cover_time_based/frontend/entity-filter.js";

test("pulse mode allows switch and script domains", () => {
  assert.deepEqual(switchPickerDomains("pulse"), ["switch", "script"]);
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
