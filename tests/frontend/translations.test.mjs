/**
 * Tests for translations.js — locale resolution and string lookup.
 *
 * Run: npm run test:fe -- tests/frontend/translations.test.mjs
 */

import { test, expect } from "vitest";
import {
  resolveLocale,
  isLanguageSupported,
  translate,
} from "../../custom_components/cover_time_based/frontend/translations.js";

test("resolveLocale matches a shipped language exactly", () => {
  expect(resolveLocale("pt")).toBe("pt");
});

test("resolveLocale falls back to the base language for a region variant", () => {
  // HA's canonical spelling, plus the underscore form, plus a region we do not
  // ship — all covered by the European Portuguese catalogue.
  expect(resolveLocale("pt-BR")).toBe("pt");
  expect(resolveLocale("pt_BR")).toBe("pt");
  expect(resolveLocale("pt-PT")).toBe("pt");
});

test("resolveLocale returns empty string for an unshipped language", () => {
  expect(resolveLocale("de")).toBe("");
  expect(resolveLocale("de-AT")).toBe("");
});

test("resolveLocale returns empty string when the language is missing", () => {
  expect(resolveLocale("")).toBe("");
  expect(resolveLocale(undefined)).toBe("");
});

test("isLanguageSupported treats a missing language as supported", () => {
  // Undeterminable language: render English and never nudge.
  expect(isLanguageSupported(undefined)).toBe(true);
  expect(isLanguageSupported("")).toBe(true);
});

test("isLanguageSupported reflects whether a catalogue covers the locale", () => {
  expect(isLanguageSupported("pl")).toBe(true);
  expect(isLanguageSupported("pt-BR")).toBe(true);
  expect(isLanguageSupported("de")).toBe(false);
});

test("translate renders a region variant in its base catalogue", () => {
  // The bug this fixes: pt-BR used to fall through to English.
  expect(translate("pt-BR", "loading")).toBe("A carregar...");
});

test("translate falls back to English for an unshipped language", () => {
  expect(translate("de", "loading")).toBe("Loading...");
});

test("translate returns the key itself when no catalogue defines it", () => {
  expect(translate("pt", "definitely.not.a.real.key")).toBe(
    "definitely.not.a.real.key"
  );
});

test("translate substitutes placeholders", () => {
  expect(translate("en", "calibration.step", { step: 2 })).toBe("Step 2");
});

test("resolveLocale does not treat inherited Object properties as catalogues", () => {
  // `in` walks the prototype chain; only own keys are real catalogues.
  expect(resolveLocale("constructor")).toBe("");
  expect(resolveLocale("toString")).toBe("");
});

test("isLanguageSupported is true for English so English users are never nudged", () => {
  // The highest-consequence regression this feature could ship: if `en` ever
  // stopped resolving, every English user would be told English is untranslated.
  expect(isLanguageSupported("en")).toBe(true);
  expect(isLanguageSupported("en-GB")).toBe(true);
});

test("translate substitutes every occurrence of a repeated placeholder", () => {
  expect(translate("en", "language_request.message", { language: "X" })).not.toContain(
    "{language}"
  );
  // A string repeating a placeholder must not leave the later ones raw.
  expect(translate("en", "no.such.key.{a}.and.{a}", { a: "Z" })).toBe(
    "no.such.key.Z.and.Z"
  );
});

test("translate treats $-patterns in a replacement value as literal text", () => {
  // String.replace interprets $&, $` and $' in the replacement — a display name
  // containing one must not be able to splice the surrounding string into itself.
  expect(translate("en", "no.such.key.{a}", { a: "$& $` $'" })).toBe(
    "no.such.key.$& $` $'"
  );
});
