/**
 * Covers the ha-textfield fallback branch of renderTextfield().
 *
 * This file intentionally does NOT register ha-input, so textfieldTagName()
 * returns "ha-textfield" and renderTextfield() takes the else-branch
 * (HA <2026.4 fallback), covering those previously-ignored lines.
 *
 * Each Vitest test file gets its own fresh happy-dom environment, so
 * registering stubs here does not affect other test files.
 *
 * Run: npm run test:fe -- tests/frontend/textfield_render_fallback.test.mjs
 */

import { test, expect } from "vitest";
import { defineHaStubs } from "./helpers/mount.mjs";

// Register ha-* stubs but deliberately OMIT ha-input so textfieldTagName()
// falls back to ha-textfield and the else-branch of renderTextfield is exercised.
defineHaStubs({ exclude: ["ha-input"] });
import { render } from "lit-html";
import { renderTextfield } from "../../custom_components/cover_time_based/frontend/textfield-render.js";

test("renderTextfield falls back to ha-textfield when ha-input is not registered", () => {
  // ha-input is NOT registered in this file's environment, so textfieldTagName()
  // returns "ha-textfield" and the else-branch of renderTextfield is taken.
  const container = document.createElement("div");
  document.body.appendChild(container);

  render(
    renderTextfield({
      type: "number",
      min: 0.1,
      max: 999,
      step: 0.1,
      label: "Pulse time",
      hint: "seconds",
      suffix: "s",
      placeholder: "",
      value: 0.5,
      onChange: () => {},
    }),
    container,
  );

  expect(container.querySelector("ha-textfield")).not.toBeNull();
  expect(container.querySelector("ha-input")).toBeNull();

  container.remove();
});
