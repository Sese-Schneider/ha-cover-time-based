/**
 * Task 27 (F5 + F7): disconnectedCallback must not silently drop a pending
 * debounced edit, and must not treat a synchronous HA re-parent (masonry
 * re-layout / dashboard edit / phone rotation triggers disconnect+reconnect
 * on the SAME element) as "the user left" while a calibration is running.
 * The device-picker handler (card-render.js) must also flush a pending edit
 * for the OLD entity before switching _config/_selectedEntity to the new one.
 *
 * Adapted from docs/audit/2026-07-21-audit-probes/f5_debounce.probe.mjs and
 * f1_f6_f7.probe.mjs (F7 case) into the repo-fixture test style.
 *
 * Run: npm run test:fe -- tests/frontend/disconnect_reparent.test.mjs
 */

import { test, expect, afterEach, vi } from "vitest";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard, defineHaStubs } from "./helpers/mount.mjs";

defineHaStubs();
let card;
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  card?.remove();
  card = null;
});

const CONFIG_A = {
  control_mode: "switch",
  open_switch_entity_id: "switch.ao",
  close_switch_entity_id: "switch.ac",
  travel_time_close: 5,
};
const CONFIG_B = {
  control_mode: "switch",
  open_switch_entity_id: "switch.bo",
  close_switch_entity_id: "switch.bc",
  travel_time_close: 7,
};

const CAL_STATES = {
  "cover.x": {
    state: "opening",
    attributes: { calibration_active: true, calibration_attribute: "travel_time_close" },
  },
};

function updateConfigCalls(hass) {
  return hass.callWS.mock.calls
    .map(([arg]) => arg)
    .filter((a) => a.type === "cover_time_based/update_config");
}

function stopCalibrationCalls(hass) {
  return hass.callWS.mock.calls
    .map(([arg]) => arg)
    .filter((a) => a.type === "cover_time_based/stop_calibration");
}

// ---------------------------------------------------------------------------
// (i) edit then remove() within the debounce window: the edit is flushed,
// not dropped.
// ---------------------------------------------------------------------------

test("(i) disconnect within the debounce window flushes the pending edit instead of dropping it", async () => {
  const hass = makeHass();
  card = await mountCard(hass, { selectedEntity: "cover.a", config: { ...CONFIG_A } });
  vi.useFakeTimers();

  card._updateLocal({ travel_time_close: 42 }); // schedules autosave in 500ms
  card.remove(); // disconnectedCallback: must flush synchronously, not drop
  await vi.advanceTimersByTimeAsync(2000);

  const saves = updateConfigCalls(hass);
  expect(saves).toHaveLength(1);
  expect(saves[0].entity_id).toBe("cover.a");
  expect(saves[0].travel_time_close).toBe(42);
  card = null;
});

// ---------------------------------------------------------------------------
// (ii) a synchronous remove()+append() (HA re-parent) while calibrating must
// NOT cancel the calibration.
// ---------------------------------------------------------------------------

test("(ii) synchronous re-parent (remove+append) while calibrating sends zero stop_calibration calls", async () => {
  const hass = makeHass({ states: CAL_STATES });
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { control_mode: "switch" } });
  card._calibratingOverride = true;

  document.body.removeChild(card); // disconnect
  document.body.appendChild(card); // reconnect, synchronously, same tick

  // Let the deferred check's setTimeout(..., 0) actually run and find
  // isConnected === true - otherwise this only proves "no synchronous
  // cancel", not that the reconnect suppressed the deferred one too.
  await new Promise((r) => setTimeout(r, 0));

  expect(stopCalibrationCalls(hass)).toHaveLength(0);
});

// ---------------------------------------------------------------------------
// (iii) detached for a full tick while calibrating: exactly one
// stop_calibration({cancel: true}).
// ---------------------------------------------------------------------------

test("(iii) detached for a full tick while calibrating sends exactly one stop_calibration(cancel: true)", async () => {
  const hass = makeHass({ states: CAL_STATES });
  card = await mountCard(hass, { selectedEntity: "cover.x", config: { control_mode: "switch" } });
  card._calibratingOverride = true;

  document.body.removeChild(card); // disconnect and stay gone

  // Let the deferred check's setTimeout(..., 0) run.
  await new Promise((r) => setTimeout(r, 0));

  const cancels = stopCalibrationCalls(hass);
  expect(cancels).toHaveLength(1);
  expect(cancels[0].cancel).toBe(true);
  card = null;
});

// ---------------------------------------------------------------------------
// (iv) edit then picker-switch: the edit must be saved for the OLD entity
// before the switch swaps _config/_selectedEntity.
// ---------------------------------------------------------------------------

test("(iv) editing then switching the device picker flushes the pending edit for the OLD entity before the switch", async () => {
  const hass = makeHass({
    states: { "cover.a": { attributes: {} }, "cover.b": { attributes: {} } },
    ws: {
      "cover_time_based/get_config": ({ entity_id }) =>
        entity_id === "cover.b" ? { ...CONFIG_B } : { ...CONFIG_A },
    },
  });
  card = await mountCard(hass, { selectedEntity: "cover.a", config: { ...CONFIG_A } });
  vi.useFakeTimers();

  card._updateLocal({ travel_time_close: 42 }); // pending edit to A, not yet debounced out

  const picker = card.shadowRoot.querySelector("ha-entity-picker");
  picker.dispatchEvent(new CustomEvent("value-changed", { detail: { value: "cover.b" } }));

  // The flush happens synchronously inside the handler (before _config is
  // swapped), so the update_config call is queued the instant the handler
  // runs - no timer advance needed to observe it.
  const saves = updateConfigCalls(hass);
  expect(saves).toHaveLength(1);
  expect(saves[0].entity_id).toBe("cover.a");
  expect(saves[0].travel_time_close).toBe(42);

  // The switch itself still proceeds.
  expect(card._selectedEntity).toBe("cover.b");

  await vi.advanceTimersByTimeAsync(600);
  await card.updateComplete;
  expect(card._config.travel_time_close).toBe(7); // B's own config, not A's edit
});
