/**
 * The card remembers its last-selected device across reloads.
 *
 * Restore happens after _loadEntityList resolves, so the remembered id can be
 * validated against the live entity list; tests await card._entityListReady.
 *
 * Run: npm run test:fe -- tests/frontend/card_selection_memory.test.mjs
 */

import { test, expect, afterEach, vi } from "vitest";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard, defineHaStubs } from "./helpers/mount.mjs";
import {
  saveSelectedEntity,
  loadSelectedEntity,
} from "../../custom_components/cover_time_based/frontend/selection-storage.js";

defineHaStubs();

let card;
afterEach(() => {
  vi.restoreAllMocks();
  card?.remove();
  card = null;
});

/** hass whose registry exposes `entityIds` as live cover_time_based entities. */
function hassWithEntities(entityIds) {
  return makeHass({
    ws: {
      "config/entity_registry/list": () =>
        entityIds.map((id) => ({
          entity_id: id,
          platform: "cover_time_based",
          config_entry_id: "e1",
        })),
      "config_entries/get": () => [{ entry_id: "e1" }],
    },
  });
}

// ---------------------------------------------------------------------------
// Restore
// ---------------------------------------------------------------------------

test("a remembered device that still exists is restored on connect", async () => {
  saveSelectedEntity("cover.remembered");
  card = await mountCard(hassWithEntities(["cover.remembered", "cover.other"]));
  await card._entityListReady;
  expect(card._selectedEntity).toBe("cover.remembered");
});

test("restoring a remembered device loads its config", async () => {
  saveSelectedEntity("cover.remembered");
  const hass = hassWithEntities(["cover.remembered"]);
  card = await mountCard(hass);
  await card._entityListReady;
  expect(hass.callWS).toHaveBeenCalledWith(
    expect.objectContaining({
      type: "cover_time_based/get_config",
      entity_id: "cover.remembered",
    })
  );
});

test("a remembered device that no longer exists is not restored", async () => {
  saveSelectedEntity("cover.deleted");
  const hass = hassWithEntities(["cover.still_here"]);
  card = await mountCard(hass);
  await card._entityListReady;
  expect(card._selectedEntity).toBe("");
  expect(hass.callWS).not.toHaveBeenCalledWith(
    expect.objectContaining({ type: "cover_time_based/get_config" })
  );
});

test("with nothing remembered the picker stays empty", async () => {
  card = await mountCard(hassWithEntities(["cover.a"]));
  await card._entityListReady;
  expect(card._selectedEntity).toBe("");
});

test("a selection made before the entity list resolves is not clobbered", async () => {
  saveSelectedEntity("cover.remembered");
  card = await mountCard(hassWithEntities(["cover.remembered", "cover.chosen"]));
  // User picks a device while the registry lookup is still in flight.
  card._setSelectedEntity("cover.chosen");
  await card._entityListReady;
  expect(card._selectedEntity).toBe("cover.chosen");
});

// ---------------------------------------------------------------------------
// Persist
// ---------------------------------------------------------------------------

test("selecting a device through the picker remembers it", async () => {
  card = await mountCard(hassWithEntities(["cover.picked"]));
  await card._entityListReady;
  const picker = card.shadowRoot.querySelector("ha-entity-picker");
  picker.dispatchEvent(
    new CustomEvent("value-changed", { detail: { value: "cover.picked" } })
  );
  expect(loadSelectedEntity()).toBe("cover.picked");
});

test("clearing the selection through the picker forgets it", async () => {
  saveSelectedEntity("cover.picked");
  card = await mountCard(hassWithEntities(["cover.picked"]));
  await card._entityListReady;
  const picker = card.shadowRoot.querySelector("ha-entity-picker");
  picker.dispatchEvent(
    new CustomEvent("value-changed", { detail: { value: "" } })
  );
  expect(loadSelectedEntity()).toBe("");
});

test("_onEntityChange remembers the newly selected device", async () => {
  card = await mountCard(hassWithEntities(["cover.via_handler"]));
  await card._entityListReady;
  card._onEntityChange({ detail: { value: "cover.via_handler" } });
  expect(loadSelectedEntity()).toBe("cover.via_handler");
});
