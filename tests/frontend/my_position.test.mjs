/**
 * my_position ("My position (%)") field.
 *
 * Renders only for control modes that can be repositioned by a hardware
 * "my"/favourite preset button: wrapped covers (which delegate to an
 * underlying cover entity that may itself have such a preset) and pulse
 * controllers (which drive a dedicated stop input, matching a hardware
 * favourite button). Hidden for switch/toggle/toggle_opposite, which have
 * no such concept. Nullable — empty clears the field to null.
 *
 * Run: npm run test:fe -- tests/frontend/my_position.test.mjs
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

const cfg = (mode, over = {}) => ({
  control_mode: mode,
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  stop_switch_entity_id: "switch.s",
  cover_entity_id: "cover.real",
  ...over,
});

function field(card) {
  const label = card._t("my_position.label");
  return [...card.shadowRoot.querySelectorAll("ha-input")].find(
    (el) => el.getAttribute("label") === label,
  );
}

for (const mode of ["wrapped", "pulse"]) {
  test(`my_position field renders for ${mode} mode`, async () => {
    card = await mountCard(makeHass(), {
      selectedEntity: "cover.x",
      config: cfg(mode),
      activeTab: "device",
    });
    expect(field(card)).toBeTruthy();
  });
}

for (const mode of ["switch", "toggle", "toggle_opposite"]) {
  test(`my_position field does not render for ${mode} mode`, async () => {
    card = await mountCard(makeHass(), {
      selectedEntity: "cover.x",
      config: cfg(mode),
      activeTab: "device",
    });
    expect(field(card)).toBeFalsy();
  });
}

test("typing 90 into my_position calls _updateLocal with my_position: 90", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: cfg("wrapped"),
    activeTab: "device",
  });
  const updates = [];
  card._updateLocal = (u) => updates.push(u);

  const input = field(card);
  input.value = "90";
  input.dispatchEvent(new Event("change", { bubbles: true }));

  expect(updates).toEqual([{ my_position: 90 }]);
});

test("clearing my_position calls _updateLocal with my_position: null", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: cfg("pulse", { my_position: 50 }),
    activeTab: "device",
  });
  const updates = [];
  card._updateLocal = (u) => updates.push(u);

  const input = field(card);
  input.value = "";
  input.dispatchEvent(new Event("change", { bubbles: true }));

  expect(updates).toEqual([{ my_position: null }]);
});
