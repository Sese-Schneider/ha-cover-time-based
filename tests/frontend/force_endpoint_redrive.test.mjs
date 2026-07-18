/**
 * force_endpoint_redrive (all-mode "re-drive at endpoints") UI — issue #167.
 *
 * The toggle renders for every control mode (like assumed_state), default off.
 *
 * Run: npm run test:fe -- tests/frontend/force_endpoint_redrive.test.mjs
 */

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

const LABEL = "Always re-send open/close at the endpoints";

const cfg = (mode, over = {}) => ({
  control_mode: mode,
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  stop_switch_entity_id: "switch.s",
  cover_entity_id: "cover.real",
  ...over,
});

function row(card) {
  return [...card.shadowRoot.querySelectorAll(".toggle-with-help")].find(
    (el) => el.querySelector(".toggle-label")?.textContent.trim() === LABEL,
  );
}

for (const mode of ["switch", "pulse", "toggle", "wrapped"]) {
  test(`force_endpoint_redrive toggle renders for ${mode} mode`, async () => {
    card = await mountCard(makeHass(), {
      selectedEntity: "cover.x",
      config: cfg(mode),
      activeTab: "device",
    });
    expect(row(card)).toBeTruthy();
  });
}

test("toggling force_endpoint_redrive calls _updateLocal with true", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: cfg("switch"),
    activeTab: "device",
  });
  const captured = [];
  card._updateLocal = (u) => captured.push(u);

  const toggle = row(card).querySelector("ha-switch");
  toggle.checked = true;
  toggle.dispatchEvent(new Event("change"));

  expect(captured).toEqual([{ force_endpoint_redrive: true }]);
});
