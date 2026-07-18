/**
 * Guards language parity in the card's translation table.
 *
 * Every non-English language must define exactly the keys English defines.
 * A key missing from a language silently falls back to English, so a new
 * option added in English only ships an untranslated label to every other
 * locale without anything failing — the drift this test exists to catch.
 * A key present in a language but not in English is dead weight, usually a
 * rename left behind.
 *
 * Run: npm run test:fe -- tests/frontend/translation_parity.test.mjs
 */

import { test, expect } from "vitest";
import {
  EN,
  TRANSLATIONS,
} from "../../custom_components/cover_time_based/frontend/translations.js";

const OTHER_LANGS = Object.keys(TRANSLATIONS).filter((l) => l !== "en");

test("the translation table exposes English plus at least one other language", () => {
  expect(TRANSLATIONS.en).toBe(EN);
  expect(OTHER_LANGS.length).toBeGreaterThan(0);
});

test.each(OTHER_LANGS)("%s translates every English key", (lang) => {
  const missing = Object.keys(EN).filter((k) => !(k in TRANSLATIONS[lang]));
  expect(missing).toEqual([]);
});

test.each(OTHER_LANGS)("%s defines no key English lacks", (lang) => {
  const stale = Object.keys(TRANSLATIONS[lang]).filter((k) => !(k in EN));
  expect(stale).toEqual([]);
});
