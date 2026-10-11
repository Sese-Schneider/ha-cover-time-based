/**
 * link_to_device (show a wrapped cover on its device's page) UI — issue #304.
 * The toggle renders ONLY for wrapped mode, is off unless stored true, and
 * drives _updateLocal({ link_to_device }).
 *
 * Run: npm run test:fe -- tests/frontend/link_to_device.test.mjs
 */
import { test, expect, afterEach, vi } from "vitest";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard, defineHaStubs, toggleByLabel } from "./helpers/mount.mjs";

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

test("link_to_device toggle renders for wrapped mode, off by default", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  const toggle = toggleByLabel(card, LABEL);
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
    expect(toggleByLabel(card, LABEL)).toBeNull();
  });
}

test("link_to_device toggle sits right after the invert toggle", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  const toggles = [...card.shadowRoot.querySelectorAll("ha-switch.toggle-switch")];
  const invert = toggleByLabel(card, "Invert position");
  expect(toggles.indexOf(toggleByLabel(card, LABEL))).toBe(toggles.indexOf(invert) + 1);
});

test("link_to_device toggle reflects stored true", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ link_to_device: true }),
    activeTab: "device",
  });
  expect(toggleByLabel(card, LABEL).checked).toBe(true);
});

test("toggling link_to_device calls _updateLocal({ link_to_device })", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  const captured = [];
  card._updateLocal = (u) => captured.push(u);
  const toggle = toggleByLabel(card, LABEL);
  toggle.checked = true;
  toggle.dispatchEvent(new Event("change"));
  expect(captured).toContainEqual({ link_to_device: true });
});
