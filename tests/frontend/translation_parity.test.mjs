/**
 * Guards language parity in the card's translation table.
 *
 * Every non-English language must define exactly the keys English defines,
 * each with a real value. A key that is missing — or present but blank —
 * silently falls back to English, so a new option added in English only ships
 * an untranslated label to every other locale without anything failing. That
 * is the drift this test exists to catch. A key present in a language but not
 * in English is dead weight, usually a rename left behind.
 *
 * Run: npm run test:fe -- tests/frontend/translation_parity.test.mjs
 */

import { test, expect } from "vitest";
import {
  EN,
  TRANSLATIONS,
} from "../../custom_components/cover_time_based/frontend/translations.js";

const OTHER_LANGS = Object.keys(TRANSLATIONS).filter((l) => l !== "en");
const EN_KEYS = Object.keys(EN);

test("the translation table exposes English plus at least one other language", () => {
  expect(TRANSLATIONS.en).toBe(EN);
  expect(OTHER_LANGS.length).toBeGreaterThan(0);
});

test.each(OTHER_LANGS)("%s translates every English key", (lang) => {
  const missing = EN_KEYS.filter((k) => !Object.hasOwn(TRANSLATIONS[lang], k));
  expect(missing).toEqual([]);
});

// Key presence alone is not enough: translate() resolves a string as
// `strings[key] || EN[key] || key`, so an empty or blank value is falsy and
// silently falls back to English — untranslated in every way that matters to
// the user, while a presence-only check reports the language as complete.
test.each(OTHER_LANGS)("%s has a non-blank value for every key", (lang) => {
  const blank = EN_KEYS.filter((k) => {
    const value = TRANSLATIONS[lang][k];
    return typeof value !== "string" || value.trim() === "";
  });
  expect(blank).toEqual([]);
});

test.each(OTHER_LANGS)("%s defines no key English lacks", (lang) => {
  const stale = Object.keys(TRANSLATIONS[lang]).filter(
    (k) => !Object.hasOwn(EN, k),
  );
  expect(stale).toEqual([]);
});
