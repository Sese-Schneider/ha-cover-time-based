/**
 * The close-includes-tilt switch and its label, on a Home Assistant without
 * ha-formfield (removed in 2026.11).
 */

import { test, expect, afterEach, vi } from "vitest";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard, defineHaStubs, toggleByLabel } from "./helpers/mount.mjs";
import { translate } from "../../custom_components/cover_time_based/frontend/translations.js";

defineHaStubs();
let card;
afterEach(() => {
  vi.restoreAllMocks();
  card?.remove();
  card = null;
});

const LABEL = translate("en", "tilt.close_includes_tilt");

async function mountTiltCard(over = {}) {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: {
      control_mode: "switch",
      open_switch_entity_id: "switch.o",
      close_switch_entity_id: "switch.c",
      tilt_mode: "sequential_close",
      ...over,
    },
    activeTab: "device",
  });
  return card;
}

const labelEl = () => card.shadowRoot.querySelector(".inline-field .toggle-label");

test.each(["sequential_close", "dual_motor"])(
  "%s: the label renders next to the switch with no ha-formfield",
  async (tilt_mode) => {
    await mountTiltCard({ tilt_mode });
    expect(card.shadowRoot.querySelector("ha-formfield")).toBeNull();
    expect(labelEl().textContent.trim()).toBe(LABEL);
    expect(toggleByLabel(card, LABEL)).not.toBeNull();
  },
);

test("the switch carries the label for screen readers", async () => {
  await mountTiltCard();
  expect(toggleByLabel(card, LABEL).getAttribute("aria-label")).toBe(LABEL);
});

test("one click on the label flips the value exactly once", async () => {
  await mountTiltCard({ close_includes_tilt: true });
  const update = vi.spyOn(card, "_updateLocal");

  labelEl().click();
  await card.updateComplete;

  expect(update).toHaveBeenCalledTimes(1);
  expect(update).toHaveBeenCalledWith({ close_includes_tilt: false });
  expect(toggleByLabel(card, LABEL).checked).toBe(false);
});

test("a second click on the label flips it back", async () => {
  await mountTiltCard({ close_includes_tilt: false });
  expect(toggleByLabel(card, LABEL).checked).toBe(false);

  labelEl().click();
  await card.updateComplete;
  expect(toggleByLabel(card, LABEL).checked).toBe(true);

  labelEl().click();
  await card.updateComplete;
  expect(toggleByLabel(card, LABEL).checked).toBe(false);
});

test("an unset value reads as on, so a label click turns it off", async () => {
  await mountTiltCard({ close_includes_tilt: null });
  expect(toggleByLabel(card, LABEL).checked).toBe(true);

  labelEl().click();
  await card.updateComplete;
  expect(toggleByLabel(card, LABEL).checked).toBe(false);
});

test("using the switch itself still writes its value once", async () => {
  await mountTiltCard({ close_includes_tilt: true });
  const update = vi.spyOn(card, "_updateLocal");

  const toggle = toggleByLabel(card, LABEL);
  toggle.checked = false;
  toggle.dispatchEvent(new Event("change"));

  expect(update).toHaveBeenCalledTimes(1);
  expect(update).toHaveBeenCalledWith({ close_includes_tilt: false });
});
