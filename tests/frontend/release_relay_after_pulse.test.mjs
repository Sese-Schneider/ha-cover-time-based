/**
 * release_relay_after_pulse ("Turn the relay off after the pulse") UI.
 *
 * The toggle renders for the two toggle modes, and only while the relay is
 * trusted to report its OFF. Turning it on brings up the pulse time, which the
 * toggle modes otherwise have no use for.
 *
 * Run: npm run test:fe -- tests/frontend/release_relay_after_pulse.test.mjs
 */

import { test, expect, afterEach, vi } from "vitest";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard, defineHaStubs, toggleByLabel } from "./helpers/mount.mjs";
import {
  offersRelayRelease,
  releasesRelayAfterPulse,
  showsPulseTime,
} from "../../custom_components/cover_time_based/frontend/entity-filter.js";

defineHaStubs();
let card;
afterEach(() => {
  vi.restoreAllMocks();
  card?.remove();
  card = null;
});

const LABEL = "Turn the relay off after the pulse";

const cfg = (control_mode, over = {}) => ({
  control_mode,
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  ...over,
});

async function mount(config) {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config,
    activeTab: "device",
  });
  return card;
}

const pulseTimeField = (c) =>
  [...c.shadowRoot.querySelectorAll("ha-input, ha-textfield")].find(
    (el) => el.getAttribute("label") === "Pulse time",
  );

test.each(["toggle", "toggle_opposite"])("renders for %s mode, off by default", async (mode) => {
  await mount(cfg(mode));
  expect(toggleByLabel(card, LABEL).checked).toBe(false);
});

test.each(["switch", "pulse", "single_button"])("does NOT render for %s mode", async (mode) => {
  await mount(cfg(mode));
  expect(toggleByLabel(card, LABEL)).toBeNull();
});

test("does NOT render for wrapped mode", async () => {
  await mount({ control_mode: "wrapped", cover_entity_id: "cover.real" });
  expect(toggleByLabel(card, LABEL)).toBeNull();
});

test("is hidden while the relay does not report its own OFF", async () => {
  await mount(cfg("toggle", { relay_reports_off: false, release_relay_after_pulse: true }));
  expect(toggleByLabel(card, LABEL)).toBeNull();
  expect(pulseTimeField(card)).toBeUndefined();
});

test("toggling it on calls _updateLocal({ release_relay_after_pulse: true })", async () => {
  await mount(cfg("toggle"));
  const captured = [];
  card._updateLocal = (u) => captured.push(u);

  const sw = toggleByLabel(card, LABEL);
  sw.checked = true;
  sw.dispatchEvent(new Event("change"));

  expect(captured).toEqual([{ release_relay_after_pulse: true }]);
});

test("the pulse time appears only once the relay is released", async () => {
  await mount(cfg("toggle"));
  expect(pulseTimeField(card)).toBeUndefined();

  card.remove();
  await mount(cfg("toggle", { release_relay_after_pulse: true, pulse_time: 0.5 }));
  expect(pulseTimeField(card).value).toBe("0.5");
});

test("the helpers agree on when the option applies", () => {
  const on = { control_mode: "toggle", release_relay_after_pulse: true };
  expect(offersRelayRelease(on)).toBe(true);
  expect(releasesRelayAfterPulse(on)).toBe(true);
  expect(showsPulseTime("toggle", on)).toBe(true);

  expect(releasesRelayAfterPulse({ control_mode: "toggle" })).toBe(false);
  expect(releasesRelayAfterPulse({ ...on, relay_reports_off: false })).toBe(false);
  expect(releasesRelayAfterPulse({ ...on, control_mode: "pulse" })).toBe(false);
  expect(showsPulseTime("toggle")).toBe(false);
  expect(offersRelayRelease(undefined)).toBe(false);
});
