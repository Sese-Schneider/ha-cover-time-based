/**
 * The startup-delay ("overhead") calibration runs a stepped phase before a
 * final continuous phase; only the final phase produces a real measurement.
 * Finishing during the stepped phase returns a hard-coded 0, so the card gates
 * the Finish button until the calibration reports its final step. Simple
 * travel/tilt-time tests have no stepped phase, so their Finish stays enabled.
 *
 * Run: npm run test:fe -- tests/frontend/calibration_finish_gate.test.mjs
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

const switchCfg = (over = {}) => ({
  control_mode: "switch",
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  ...over,
});

const calibratingHass = (attrs) =>
  makeHass({
    states: {
      "cover.x": {
        state: "open",
        attributes: { calibration_active: true, ...attrs },
      },
    },
  });

// The Finish button is the "unelevated" one in the active-calibration panel
// (Cancel is not unelevated; the non-calibrating Start button is not shown).
const finishButton = (c) =>
  c.shadowRoot.querySelector(".cal-active-buttons ha-button[unelevated]");

async function mountCalibrating(attrs) {
  return mountCard(calibratingHass(attrs), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
  });
}

test("startup-delay calibration: Finish is disabled during the stepped phase", async () => {
  card = await mountCalibrating({
    calibration_attribute: "travel_startup_delay",
    calibration_step: 3,
  });
  const finish = finishButton(card);
  expect(finish).not.toBeNull();
  expect(finish.hasAttribute("disabled")).toBe(true);
});

test("startup-delay calibration: Finish is enabled once the final step is reached", async () => {
  card = await mountCalibrating({
    calibration_attribute: "travel_startup_delay",
    calibration_final_step: true,
  });
  expect(finishButton(card).hasAttribute("disabled")).toBe(false);
});

test("tilt startup-delay calibration: Finish is disabled during the stepped phase", async () => {
  card = await mountCalibrating({
    calibration_attribute: "tilt_startup_delay",
    calibration_step: 1,
  });
  expect(finishButton(card).hasAttribute("disabled")).toBe(true);
});

test("simple travel-time calibration: Finish is enabled immediately (no stepped phase)", async () => {
  card = await mountCalibrating({ calibration_attribute: "travel_time_close" });
  expect(finishButton(card).hasAttribute("disabled")).toBe(false);
});
