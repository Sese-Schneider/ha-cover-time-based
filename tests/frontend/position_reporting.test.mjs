/**
 * Position reporting dropdown (wrapped covers) — issue #238.
 *
 * One "Position reporting" <select> reads and writes the single persisted
 * `position_reporting` enum (reliable/unreliable/no_endpoints/command_echo/
 * ignore_all) — no derivation from booleans.
 *
 * Run: npm run test:fe -- tests/frontend/position_reporting.test.mjs
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

const select = (card) => card.shadowRoot.querySelector("#position-reporting-select");
const selectedValue = (sel) => [...sel.options].find((o) => o.hasAttribute("selected"))?.value;

test("dropdown renders for wrapped mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  expect(select(card)).not.toBeNull();
});

test("dropdown does NOT render for switch mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "device",
  });
  expect(select(card)).toBeNull();
});

test("defaults to the reliable profile", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  expect(selectedValue(select(card))).toBe("reliable");
});

for (const value of ["unreliable", "no_endpoints", "command_echo", "ignore_all"]) {
  test(`shows ${value} from position_reporting`, async () => {
    card = await mountCard(makeHass(), {
      selectedEntity: "cover.x",
      config: wrappedCfg({ position_reporting: value }),
      activeTab: "device",
    });
    expect(selectedValue(select(card))).toBe(value);
  });
}

for (const value of ["reliable", "no_endpoints", "ignore_all", "command_echo"]) {
  test(`selecting ${value} writes position_reporting only`, async () => {
    card = await mountCard(makeHass(), {
      selectedEntity: "cover.x",
      config: wrappedCfg({ position_reporting: "unreliable" }),
      activeTab: "device",
    });
    const captured = [];
    card._updateLocal = (u) => captured.push(u);
    const sel = select(card);
    sel.value = value;
    sel.dispatchEvent(new Event("change"));
    expect(captured).toContainEqual({ position_reporting: value });
  });
}
