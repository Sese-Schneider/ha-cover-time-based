/**
 * recalibrate_before_position ("fully open before a position move") UI — #179.
 *
 * All-mode toggle, default off, sitting beside force_endpoint_redrive.
 *
 * Run: npm run test:fe -- tests/frontend/recalibrate_before_position.test.mjs
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

const LABEL = "Fully open before moving to a position";

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
  test(`recalibrate_before_position toggle renders for ${mode} mode`, async () => {
    card = await mountCard(makeHass(), {
      selectedEntity: "cover.x",
      config: cfg(mode),
      activeTab: "device",
    });
    expect(row(card)).toBeTruthy();
  });
}

for (const mode of ["switch", "wrapped"]) {
  test(`the toggle reflects a stored true (${mode} mode)`, async () => {
    card = await mountCard(makeHass(), {
      selectedEntity: "cover.x",
      config: cfg(mode, { recalibrate_before_position: true }),
      activeTab: "device",
    });
    expect(row(card).querySelector("ha-switch").checked).toBe(true);
  });

  test(`the toggle defaults to off (${mode} mode)`, async () => {
    card = await mountCard(makeHass(), {
      selectedEntity: "cover.x",
      config: cfg(mode),
      activeTab: "device",
    });
    expect(row(card).querySelector("ha-switch").checked).toBe(false);
  });

  test(`toggling calls _updateLocal with true (${mode} mode)`, async () => {
    card = await mountCard(makeHass(), {
      selectedEntity: "cover.x",
      config: cfg(mode),
      activeTab: "device",
    });
    const captured = [];
    card._updateLocal = (u) => captured.push(u);

    const toggle = row(card).querySelector("ha-switch");
    toggle.checked = true;
    toggle.dispatchEvent(new Event("change"));

    expect(captured).toEqual([{ recalibrate_before_position: true }]);
  });
}
