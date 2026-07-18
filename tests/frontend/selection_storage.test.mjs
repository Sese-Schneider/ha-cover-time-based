/**
 * Tests for selection-storage.js — persisting the card's last-selected device.
 *
 * Run: npm run test:fe -- tests/frontend/selection_storage.test.mjs
 */

import { test, expect, afterEach, vi } from "vitest";
import {
  loadSelectedEntity,
  saveSelectedEntity,
  SELECTION_STORAGE_KEY,
} from "../../custom_components/cover_time_based/frontend/selection-storage.js";

afterEach(() => {
  vi.restoreAllMocks();
});

test("saveSelectedEntity then loadSelectedEntity round-trips an entity id", () => {
  saveSelectedEntity("cover.living_room");
  expect(loadSelectedEntity()).toBe("cover.living_room");
});

test("loadSelectedEntity returns empty string when nothing was saved", () => {
  expect(loadSelectedEntity()).toBe("");
});

test("saveSelectedEntity with an empty id removes the stored key", () => {
  saveSelectedEntity("cover.living_room");
  saveSelectedEntity("");
  expect(window.localStorage.getItem(SELECTION_STORAGE_KEY)).toBe(null);
  expect(loadSelectedEntity()).toBe("");
});

test("loadSelectedEntity returns empty string when storage access throws", () => {
  // Safari private mode / storage-disabled browsers throw on access.
  vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
    throw new Error("storage disabled");
  });
  expect(loadSelectedEntity()).toBe("");
});

test("saveSelectedEntity is a silent no-op when storage access throws", () => {
  vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
    throw new Error("storage disabled");
  });
  expect(() => saveSelectedEntity("cover.living_room")).not.toThrow();
});

test("saveSelectedEntity is a silent no-op when clearing and storage throws", () => {
  vi.spyOn(window.localStorage, "removeItem").mockImplementation(() => {
    throw new Error("storage disabled");
  });
  expect(() => saveSelectedEntity("")).not.toThrow();
});
