/**
 * wait_for_relay_feedback ("wait for relay confirmation") UI.
 *
 * The toggle renders for every relay-driven mode — switch (the default),
 * toggle, toggle_opposite and pulse — and is hidden only for wrapped covers,
 * which drive an underlying cover entity rather than a relay. Default off.
 *
 * Run: npm run test:fe -- tests/frontend/wait_for_relay_feedback.test.mjs
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

const LABEL = "Wait for relay confirmation before tracking";

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

// Every relay-driven mode renders it; switch is the default, so an unset
// control_mode must render it too.
for (const mode of ["switch", undefined, "toggle", "toggle_opposite", "pulse"]) {
  test(`wait_for_relay_feedback toggle renders for ${mode ?? "unset"} mode`, async () => {
    card = await mountCard(makeHass(), {
      selectedEntity: "cover.x",
      config: cfg(mode),
      activeTab: "device",
    });
    expect(row(card)).toBeTruthy();
  });
}

// Hidden only for wrapped covers (no relay to confirm).
for (const mode of ["wrapped"]) {
  test(`wait_for_relay_feedback toggle does not render for ${mode} mode`, async () => {
    card = await mountCard(makeHass(), {
      selectedEntity: "cover.x",
      config: cfg(mode),
      activeTab: "device",
    });
    expect(row(card)).toBeFalsy();
  });
}

test("toggling wait_for_relay_feedback calls _updateLocal with true", async () => {
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

  expect(captured).toEqual([{ wait_for_relay_feedback: true }]);
});
