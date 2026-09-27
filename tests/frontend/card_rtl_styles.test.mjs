/**
 * The card must mirror in right-to-left languages (Hebrew). Home Assistant sets
 * dir="rtl" on the page, which flips flow-relative CSS (margin-inline-start,
 * text-align: start) but not physical left/right, so any physical rule pins
 * an element to the wrong side.
 *
 * Run: npm run test:fe -- tests/frontend/card_rtl_styles.test.mjs
 */

import { test, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const STYLES = readFileSync(
  path.join(
    path.dirname(fileURLToPath(import.meta.url)),
    "../../custom_components/cover_time_based/frontend/card-styles.js",
  ),
  "utf8",
);

test("card styles use no physical left/right properties", () => {
  const physical = STYLES.split("\n")
    .map((line, i) => ({ line: line.trim(), n: i + 1 }))
    .filter(({ line }) =>
      /^(left|right|(margin|padding|border)-(left|right)[\w-]*|float)\s*:|text-align\s*:\s*(left|right)\b/.test(
        line,
      ),
    )
    .map(({ line, n }) => `${n}: ${line}`);
  expect(physical).toEqual([]);
});
