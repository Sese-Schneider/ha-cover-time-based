/** The selected cover's name at the top of the configuration card. */

import { test, expect, afterEach, vi } from "vitest";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard, defineHaStubs } from "./helpers/mount.mjs";

defineHaStubs();
let card;
afterEach(() => {
  vi.restoreAllMocks();
  card?.remove();
  card = null;
});

const STATE = {
  entity_id: "cover.x",
  state: "open",
  attributes: { friendly_name: "Friendly" },
};

async function mountTitle(hass) {
  card = await mountCard(hass, {
    selectedEntity: "cover.x",
    config: { control_mode: "switch" },
  });
  return card.shadowRoot.querySelector(".entity-info strong").textContent.trim();
}

test("uses Home Assistant's own entity name when it offers one", async () => {
  const formatEntityName = vi.fn(() => "Lounge blind motor Lounge shade");
  const hass = { ...makeHass({ states: { "cover.x": STATE } }), formatEntityName };

  expect(await mountTitle(hass)).toBe("Lounge blind motor Lounge shade");
  expect(formatEntityName).toHaveBeenCalledWith(STATE);
});

test("falls back to the friendly name on an older Home Assistant", async () => {
  expect(await mountTitle(makeHass({ states: { "cover.x": STATE } }))).toBe("Friendly");
});

test("falls back to the friendly name when Home Assistant returns no name", async () => {
  const hass = {
    ...makeHass({ states: { "cover.x": STATE } }),
    formatEntityName: () => "",
  };

  expect(await mountTitle(hass)).toBe("Friendly");
});

test("shows the entity id when the entity has no state", async () => {
  const formatEntityName = vi.fn();
  const hass = { ...makeHass(), formatEntityName };

  expect(await mountTitle(hass)).toBe("cover.x");
  expect(formatEntityName).not.toHaveBeenCalled();
});
