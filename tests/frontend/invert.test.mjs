/**
 * invert (wrapped-cover position inversion) UI — issue #160.
 * The toggle renders ONLY for wrapped mode and drives _updateLocal({ invert }).
 *
 * Run: npm run test:fe -- tests/frontend/invert.test.mjs
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

const INVERT_LABEL = "Invert position";

const wrappedCfg = (over = {}) => ({
  control_mode: "wrapped",
  cover_entity_id: "cover.real",
  ...over,
});
const switchCfg = (over = {}) => ({
  control_mode: "switch",
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  ...over,
});

function hasInvertToggle(card) {
  const labels = [...card.shadowRoot.querySelectorAll(".toggle-label")];
  return labels.some((el) => el.textContent.trim() === INVERT_LABEL);
}

test("invert toggle renders for wrapped mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  expect(hasInvertToggle(card)).toBe(true);
});

test("invert toggle does NOT render for switch mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "device",
  });
  expect(hasInvertToggle(card)).toBe(false);
});

test("invert toggle reflects stored true", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ invert: true }),
    activeTab: "device",
  });
  const toggles = [...card.shadowRoot.querySelectorAll("ha-switch.toggle-switch")];
  // Wrapped order (post #238 dropdown): [0] force_time_based_position,
  // [1] invert, [2] assumed_state, [3] force_endpoint_redrive,
  // [4] recalibrate_before_position
  expect(toggles[1].checked).toBe(true);
});

test("toggling invert calls _updateLocal({ invert })", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  const captured = [];
  card._updateLocal = (u) => captured.push(u);
  const toggle = card.shadowRoot.querySelectorAll("ha-switch.toggle-switch")[1];
  toggle.checked = true;
  toggle.dispatchEvent(new Event("change"));
  expect(captured).toContainEqual({ invert: true });
});
