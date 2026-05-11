/**
 * Tests for textfield.js — picks ha-input (HA 2026.4+) or falls back to
 * ha-textfield (removed in 2026.5).
 *
 * Run: node --test tests/frontend/textfield.test.mjs
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { textfieldTagName } from "../../custom_components/cover_time_based/frontend/textfield.js";

const registry = (names) => ({
  get: (name) => (names.includes(name) ? class {} : undefined),
});

test("prefers ha-input when registered", () => {
  assert.equal(
    textfieldTagName(registry(["ha-input", "ha-textfield"])),
    "ha-input",
  );
});

test("returns ha-input even if ha-textfield is absent", () => {
  assert.equal(textfieldTagName(registry(["ha-input"])), "ha-input");
});

test("falls back to ha-textfield when ha-input is not registered", () => {
  assert.equal(textfieldTagName(registry(["ha-textfield"])), "ha-textfield");
});

test("falls back to ha-textfield when neither is registered", () => {
  // We have to render *something*; ha-textfield is the safer guess on
  // older HA versions where ha-input does not exist yet.
  assert.equal(textfieldTagName(registry([])), "ha-textfield");
});
