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

const LINES = STYLES.split("\n").map((line, i) => ({ line: line.trim(), n: i + 1 }));

test("card styles use no physical left/right properties", () => {
  const physical = LINES.filter(({ line }) =>
    /^(left|right|(margin|padding|border)-(left|right)[\w-]*|float)\s*:|text-align\s*:\s*(left|right)\b/.test(
      line,
    ),
  ).map(({ line, n }) => `${n}: ${line}`);
  expect(physical).toEqual([]);
});

test("box shorthands give the left and right sides the same value", () => {
  // The fourth value of a four-value shorthand is the left side and the second
  // is the right; if they differ the rule does not mirror.
  const lopsided = LINES.filter(({ line }) => {
    const m = /^(margin|padding|inset|border-width|border-style|border-color)\s*:\s*([^;]+);/.exec(
      line,
    );
    if (!m) return false;
    const parts = m[2].trim().split(/\s+(?![^(]*\))/);
    return parts.length === 4 && parts[1] !== parts[3];
  }).map(({ line, n }) => `${n}: ${line}`);
  expect(lopsided).toEqual([]);
});
