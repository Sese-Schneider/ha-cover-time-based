/**
 * link_to_device (show a wrapped cover on its device's page) UI — issue #304.
 * The toggle renders ONLY for wrapped mode, is off unless stored true, and
 * drives _updateLocal({ link_to_device }).
 *
 * Run: npm run test:fe -- tests/frontend/link_to_device.test.mjs
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

const LABEL = "Show on the wrapped cover's device page";

const wrappedCfg = (over = {}) => ({
  control_mode: "wrapped",
  cover_entity_id: "cover.real",
  ...over,
});

function findToggle(card) {
  const rows = [...card.shadowRoot.querySelectorAll(".toggle-label")];
  const label = rows.find((el) => el.textContent.trim() === LABEL);
  if (!label) return null;
  const row = label.closest(".toggle-with-help");
  return row.querySelector("ha-switch.toggle-switch");
}

test("link_to_device toggle renders for wrapped mode, off by default", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  const toggle = findToggle(card);
  expect(toggle).not.toBeNull();
  expect(toggle.checked).toBe(false);
});

for (const mode of ["switch", "pulse", "toggle", "toggle_opposite", "single_button"]) {
  test(`link_to_device toggle does NOT render for ${mode} mode`, async () => {
    card = await mountCard(makeHass(), {
      selectedEntity: "cover.x",
      config: {
        control_mode: mode,
        open_switch_entity_id: "switch.o",
        close_switch_entity_id: "switch.c",
        link_to_device: true,
      },
      activeTab: "device",
    });
    expect(findToggle(card)).toBeNull();
  });
}

test("link_to_device toggle reflects stored true", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ link_to_device: true }),
    activeTab: "device",
  });
  expect(findToggle(card).checked).toBe(true);
});

test("toggling link_to_device calls _updateLocal({ link_to_device })", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  const captured = [];
  card._updateLocal = (u) => captured.push(u);
  const toggle = findToggle(card);
  toggle.checked = true;
  toggle.dispatchEvent(new Event("change"));
  expect(captured).toContainEqual({ link_to_device: true });
});
