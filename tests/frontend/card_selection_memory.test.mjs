/**
 * The card remembers its last-selected device across reloads.
 *
 * Restore happens after _loadEntityList resolves, so the remembered id can be
 * validated against the live entity list; tests await card._entityListReady.
 *
 * Run: npm run test:fe -- tests/frontend/card_selection_memory.test.mjs
 */

import { test, expect, afterEach } from "vitest";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard, defineHaStubs } from "./helpers/mount.mjs";
import {
  saveSelectedEntity,
  loadSelectedEntity,
} from "../../custom_components/cover_time_based/frontend/selection-storage.js";

defineHaStubs();

let card;
afterEach(() => {
  card?.remove();
  card = null;
});

/**
 * hass whose registry exposes `entityIds` as live cover_time_based entities.
 *
 * `delayRegistry` makes the registry lookup resolve on a macrotask instead of
 * synchronously, so a test can act while _loadEntityList is genuinely in
 * flight. Without it the restore has already finished by the time mountCard
 * returns, and any "mid-flight" assertion passes vacuously.
 */
function hassWithEntities(entityIds, { delayRegistry = false } = {}) {
  const registry = () =>
    entityIds.map((id) => ({
      entity_id: id,
      platform: "cover_time_based",
      config_entry_id: "e1",
    }));
  return makeHass({
    ws: {
      "config/entity_registry/list": delayRegistry
        ? () => new Promise((r) => setTimeout(() => r(registry()), 0))
        : registry,
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

test("a selection made while the entity list is in flight is not clobbered", async () => {
  saveSelectedEntity("cover.remembered");
  // Registry resolves on a macrotask, so the pick below genuinely lands
  // mid-flight rather than after the restore has already run.
  const hass = hassWithEntities(["cover.remembered", "cover.chosen"], {
    delayRegistry: true,
  });
  card = await mountCard(hass);
  expect(card._selectedEntity).toBe(""); // restore has not run yet
  card._setSelectedEntity("cover.chosen");
  await card._entityListReady;

  expect(card._selectedEntity).toBe("cover.chosen");
  // Asserting the selection alone proves nothing here: the pick also rewrote
  // storage, so a restore that ignored the guard would land on the same id.
  // What distinguishes them is that the guarded restore bows out entirely and
  // never drives a config load of its own — loading is the picker's job.
  expect(hass.callWS).not.toHaveBeenCalledWith(
    expect.objectContaining({ type: "cover_time_based/get_config" })
  );
});

test("a card detached mid-lookup does not restore or call out", async () => {
  saveSelectedEntity("cover.remembered");
  const hass = hassWithEntities(["cover.remembered"], { delayRegistry: true });
  card = await mountCard(hass);
  card.remove(); // HA tears the card down before the registry lands
  await card._entityListReady;

  expect(card._selectedEntity).toBe("");
  expect(hass.callWS).not.toHaveBeenCalledWith(
    expect.objectContaining({ type: "cover_time_based/get_config" })
  );
});

test("re-connecting does not adopt a selection the user cleared in this card", async () => {
  // A second tab (or another card) remembers a device this card didn't choose.
  card = await mountCard(hassWithEntities(["cover.elsewhere"]));
  await card._entityListReady;
  expect(card._selectedEntity).toBe("");
  saveSelectedEntity("cover.elsewhere");

  // HA re-parents the card (view re-render / DOM move).
  card.remove();
  document.body.appendChild(card);
  await card._entityListReady;

  expect(card._selectedEntity).toBe("");
});

test("a config response arriving after the device changed is discarded", async () => {
  let releaseFirst;
  const hass = makeHass({
    ws: {
      "config/entity_registry/list": () => [],
      "config_entries/get": () => [],
      "cover_time_based/get_config": ({ entity_id }) =>
        entity_id === "cover.slow"
          ? new Promise((r) => {
              releaseFirst = () => r({ control_mode: "switch", marker: "slow" });
            })
          : { control_mode: "switch", marker: "fast" },
    },
  });
  card = await mountCard(hass);
  await card._entityListReady;

  card._setSelectedEntity("cover.slow");
  const slowLoad = card._loadConfig();
  card._setSelectedEntity("cover.fast");
  await card._loadConfig();
  releaseFirst();
  await slowLoad;

  // The late response for cover.slow must not overwrite cover.fast's config,
  // or the next autosave writes one device's settings onto another.
  expect(card._selectedEntity).toBe("cover.fast");
  expect(card._config?.marker).toBe("fast");
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
