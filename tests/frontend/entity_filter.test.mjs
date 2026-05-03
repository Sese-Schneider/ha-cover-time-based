/**
 * Tests for entity-filter.js — the cover-time-based-card's entity filter.
 *
 * Run: node --test tests/frontend/entity_filter.test.mjs
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { filterEntitiesByValidEntries } from "../../custom_components/cover_time_based/frontend/entity-filter.js";

const PLATFORM = "cover_time_based";

test("includes entities backed by a live config entry", () => {
  const registry = [
    { entity_id: "cover.live", platform: PLATFORM, config_entry_id: "live_entry" },
  ];
  const result = filterEntitiesByValidEntries(registry, ["live_entry"], PLATFORM);
  assert.deepEqual(result, ["cover.live"]);
});

test("excludes orphaned entities whose config_entry_id no longer exists", () => {
  // Reproduces the bug where an entity registry entry is retained after
  // its config entry was deleted, causing the card to list a phantom cover.
  const registry = [
    { entity_id: "cover.live", platform: PLATFORM, config_entry_id: "live_entry" },
    { entity_id: "cover.orphaned", platform: PLATFORM, config_entry_id: "deleted_entry" },
  ];
  const result = filterEntitiesByValidEntries(registry, ["live_entry"], PLATFORM);
  assert.deepEqual(result, ["cover.live"]);
});

test("excludes entities with no config_entry_id (YAML-configured)", () => {
  const registry = [
    { entity_id: "cover.yaml", platform: PLATFORM, config_entry_id: null },
    { entity_id: "cover.ui", platform: PLATFORM, config_entry_id: "abc" },
  ];
  const result = filterEntitiesByValidEntries(registry, ["abc"], PLATFORM);
  assert.deepEqual(result, ["cover.ui"]);
});

test("excludes entities from other platforms", () => {
  const registry = [
    { entity_id: "cover.ours", platform: PLATFORM, config_entry_id: "abc" },
    { entity_id: "cover.theirs", platform: "other_platform", config_entry_id: "abc" },
  ];
  const result = filterEntitiesByValidEntries(registry, ["abc"], PLATFORM);
  assert.deepEqual(result, ["cover.ours"]);
});

test("returns empty array when no valid entries exist", () => {
  const registry = [
    { entity_id: "cover.orphaned", platform: PLATFORM, config_entry_id: "deleted_entry" },
  ];
  const result = filterEntitiesByValidEntries(registry, [], PLATFORM);
  assert.deepEqual(result, []);
});

test("returns empty array for empty registry", () => {
  const result = filterEntitiesByValidEntries([], ["abc"], PLATFORM);
  assert.deepEqual(result, []);
});
