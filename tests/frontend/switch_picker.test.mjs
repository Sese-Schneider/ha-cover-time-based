/**
 * Tests for switchPickerDomains / switchLabelKey — pulse-mode picker helpers.
 *
 * Run: node --test tests/frontend/switch_picker.test.mjs
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { switchPickerDomains } from "../../custom_components/cover_time_based/frontend/entity-filter.js";

test("pulse mode allows switch and script domains", () => {
  assert.deepEqual(switchPickerDomains("pulse"), ["switch", "script"]);
});

test("non-pulse modes allow only the switch domain", () => {
  assert.deepEqual(switchPickerDomains("switch"), ["switch"]);
  assert.deepEqual(switchPickerDomains("toggle"), ["switch"]);
  assert.deepEqual(switchPickerDomains("wrapped"), ["switch"]);
  assert.deepEqual(switchPickerDomains(undefined), ["switch"]);
});
