/**
 * Tests for language-banner.js — the "request a translation" nudge.
 *
 * Run: npm run test:fe -- tests/frontend/language_banner.test.mjs
 */

import { test, expect, afterEach, vi } from "vitest";
import {
  GITHUB_REPO_URL,
  LANG_DISMISSED_STORAGE_KEY,
  buildTranslationRequestUrl,
  languageDisplayName,
  isLangDismissed,
  persistLangDismissed,
} from "../../custom_components/cover_time_based/frontend/language-banner.js";
import { defineHaStubs, mountCard } from "./helpers/mount.mjs";
import { makeHass } from "./helpers/hass.mjs";

defineHaStubs();

const banner = (el) => el.shadowRoot.querySelector(".lang-banner");

afterEach(() => {
  vi.restoreAllMocks();
  try {
    window.localStorage.removeItem(LANG_DISMISSED_STORAGE_KEY);
  } catch (_) {
    // storage unavailable — nothing to clean up
  }
});

test("buildTranslationRequestUrl points at the upstream repo's new-issue form", () => {
  const url = buildTranslationRequestUrl("de", "Deutsch");
  expect(url.startsWith(`${GITHUB_REPO_URL}/issues/new?`)).toBe(true);
});

test("buildTranslationRequestUrl prefills an English title and body naming the language", () => {
  const params = new URL(buildTranslationRequestUrl("de", "Deutsch")).searchParams;
  expect(params.get("title")).toBe("Translation request: Deutsch (de)");
  expect(params.get("body")).toContain("Deutsch");
  expect(params.get("body")).toContain("de");
});

test("buildTranslationRequestUrl requests no labels", () => {
  // The upstream repo has no "translation" label; asking for one achieves nothing.
  const params = new URL(buildTranslationRequestUrl("de", "Deutsch")).searchParams;
  expect(params.get("labels")).toBe(null);
});

test("languageDisplayName returns a human-readable name for a real code", () => {
  // Exact wording is Intl/ICU-dependent, so assert it is resolved, not echoed.
  const name = languageDisplayName("de");
  expect(name).not.toBe("de");
  expect(name.length).toBeGreaterThan(0);
});

test("languageDisplayName echoes the raw code for an unrecognised tag", () => {
  // Intl.DisplayNames defaults to fallback:"code" — the guard must not let that
  // echo masquerade as a real display name, and must not throw either.
  expect(languageDisplayName("zzz")).toBe("zzz");
});

test("languageDisplayName returns the input unchanged when it is empty", () => {
  expect(languageDisplayName("")).toBe("");
});

test("isLangDismissed is false before anything is dismissed", () => {
  expect(isLangDismissed("de")).toBe(false);
});

test("persistLangDismissed then isLangDismissed round-trips a locale", () => {
  persistLangDismissed("de");
  expect(isLangDismissed("de")).toBe(true);
});

test("dismissing a second locale preserves the first", () => {
  // A scalar store would forget "de": dismiss de, switch to fr, switch back,
  // and the nudge would reappear.
  persistLangDismissed("de");
  persistLangDismissed("fr");
  expect(isLangDismissed("de")).toBe(true);
  expect(isLangDismissed("fr")).toBe(true);
});

test("persistLangDismissed does not duplicate an already-dismissed locale", () => {
  persistLangDismissed("de");
  persistLangDismissed("de");
  const stored = JSON.parse(window.localStorage.getItem(LANG_DISMISSED_STORAGE_KEY));
  expect(stored).toEqual(["de"]);
});

test("isLangDismissed is false when storage access throws", () => {
  vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
    throw new Error("storage disabled");
  });
  expect(isLangDismissed("de")).toBe(false);
});

test("isLangDismissed is false when the stored value is corrupt", () => {
  window.localStorage.setItem(LANG_DISMISSED_STORAGE_KEY, "not json");
  expect(isLangDismissed("de")).toBe(false);
});

test("persistLangDismissed is a silent no-op when storage access throws", () => {
  vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
    throw new Error("storage disabled");
  });
  expect(() => persistLangDismissed("de")).not.toThrow();
});

test("the banner renders for a language with no shipped translation", async () => {
  const el = await mountCard(makeHass({ language: "de" }));
  expect(banner(el)).not.toBe(null);
});

test("the banner does not render for a shipped language", async () => {
  const el = await mountCard(makeHass({ language: "pl" }));
  expect(banner(el)).toBe(null);
});

test("the banner does not render for a region variant covered by its base", async () => {
  // pt-BR reads European Portuguese, so there is nothing to request.
  const el = await mountCard(makeHass({ language: "pt-BR" }));
  expect(banner(el)).toBe(null);
});

test("the banner does not render when the language is undeterminable", async () => {
  const el = await mountCard(makeHass({ language: "" }));
  expect(banner(el)).toBe(null);
});

test("the banner names the language and links to a prefilled issue", async () => {
  const el = await mountCard(makeHass({ language: "de" }));
  const text = banner(el).textContent;
  expect(text).toContain(languageDisplayName("de"));
  const href = banner(el).querySelector("a").getAttribute("href");
  expect(href).toBe(buildTranslationRequestUrl("de", languageDisplayName("de")));
});

test("the banner does not render for a locale already dismissed in storage", async () => {
  persistLangDismissed("de");
  const el = await mountCard(makeHass({ language: "de" }));
  expect(banner(el)).toBe(null);
});

test("clicking dismiss hides the banner and persists the locale", async () => {
  const el = await mountCard(makeHass({ language: "de" }));
  banner(el).querySelector("ha-icon-button").click();
  await el.updateComplete;
  expect(banner(el)).toBe(null);
  expect(isLangDismissed("de")).toBe(true);
});

test("dismissal sticks for the session when storage is unavailable", async () => {
  // Persistence silently no-ops, but the in-memory set must still hide it.
  vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
    throw new Error("storage disabled");
  });
  const el = await mountCard(makeHass({ language: "de" }));
  banner(el).querySelector("ha-icon-button").click();
  await el.updateComplete;
  expect(banner(el)).toBe(null);
});
