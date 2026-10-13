/**
 * reverse_on_opposite_command ("reverse on an opposite open/close") UI.
 *
 * Toggle for every control mode, default on, hidden once a tilt mode is set
 * (the option is ignored on covers with tilt). Single-button covers have no
 * tilt, so they always show it. card_render.test.mjs covers the tilt hiding
 * for switch and wrapped mode.
 *
 * Run: npm run test:fe -- tests/frontend/reverse_on_opposite_command.test.mjs
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

const LABEL = "Reverse on an opposite open/close";

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

const mount = (config) =>
  mountCard(makeHass(), { selectedEntity: "cover.x", config, activeTab: "device" });

for (const mode of ["switch", "pulse", "toggle", "toggle_opposite", "wrapped", "single_button"]) {
  test(`reverse_on_opposite_command toggle renders for ${mode} mode without tilt`, async () => {
    card = await mount(cfg(mode));
    expect(row(card)).toBeTruthy();
  });
}

for (const mode of ["pulse", "toggle", "toggle_opposite"]) {
  test(`the toggle is hidden when a tilt mode is set (${mode} mode)`, async () => {
    card = await mount(cfg(mode, { tilt_mode: "sequential_close" }));
    expect(row(card)).toBeUndefined();
  });
}

for (const mode of ["switch", "wrapped", "single_button"]) {
  test(`the toggle reflects a stored false (${mode} mode)`, async () => {
    card = await mount(cfg(mode, { reverse_on_opposite_command: false }));
    expect(row(card).querySelector("ha-switch").checked).toBe(false);
  });

  test(`the toggle defaults to on (${mode} mode)`, async () => {
    card = await mount(cfg(mode));
    expect(row(card).querySelector("ha-switch").checked).toBe(true);
  });

  test(`toggling off calls _updateLocal with false (${mode} mode)`, async () => {
    card = await mount(cfg(mode));
    const captured = [];
    card._updateLocal = (u) => captured.push(u);

    const toggle = row(card).querySelector("ha-switch");
    toggle.checked = false;
    toggle.dispatchEvent(new Event("change"));

    expect(captured).toEqual([{ reverse_on_opposite_command: false }]);
  });
}
