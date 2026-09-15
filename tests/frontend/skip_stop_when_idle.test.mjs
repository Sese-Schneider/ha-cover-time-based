/**
 * skip_stop_when_idle ("Don't send Stop when already stopped") UI — issue #251.
 *
 * The toggle renders for wrapped and pulse modes (the two that can drive a
 * shutter to a hardware "my"/favourite preset on a redundant stop), and for no
 * other mode. Toggling it updates the config.
 *
 * Run: npm run test:fe -- tests/frontend/skip_stop_when_idle.test.mjs
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

const LABEL = "Don't send Stop when already stopped";

const switchCfg = (over = {}) => ({
  control_mode: "switch",
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  ...over,
});

const pulseCfg = (over = {}) => ({
  control_mode: "pulse",
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  stop_switch_entity_id: "switch.s",
  ...over,
});

const toggleCfg = (over = {}) => ({
  control_mode: "toggle",
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  ...over,
});

const wrappedCfg = (over = {}) => ({
  control_mode: "wrapped",
  cover_entity_id: "cover.real",
  ...over,
});

function toggleEl(card) {
  const labels = [...card.shadowRoot.querySelectorAll(".toggle-label")];
  const label = labels.find((el) => el.textContent.trim() === LABEL);
  return label ? label.closest(".toggle-with-help").querySelector("ha-switch") : null;
}

function hasToggle(card) {
  return toggleEl(card) !== null;
}

test("renders for pulse mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: pulseCfg(),
    activeTab: "device",
  });
  expect(hasToggle(card)).toBe(true);
});

test("renders for wrapped mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  expect(hasToggle(card)).toBe(true);
});

test("does NOT render for switch mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "device",
  });
  expect(hasToggle(card)).toBe(false);
});

test("does NOT render for toggle mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: toggleCfg(),
    activeTab: "device",
  });
  expect(hasToggle(card)).toBe(false);
});

test("toggling it on calls _updateLocal({ skip_stop_when_idle: true })", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: pulseCfg(),
    activeTab: "device",
  });
  const captured = [];
  card._updateLocal = (u) => captured.push(u);

  const sw = toggleEl(card);
  sw.checked = true;
  sw.dispatchEvent(new Event("change"));

  expect(captured).toEqual([{ skip_stop_when_idle: true }]);
});
