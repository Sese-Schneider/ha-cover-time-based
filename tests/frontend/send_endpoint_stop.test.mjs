/**
 * send_endpoint_stop (pulse-mode endpoint stop) UI — issue #133.
 *
 * The toggle renders ONLY for pulse mode (mirroring how relay_reports_off
 * renders only for toggle mode). The endpoint run-on timing row shows for
 * switch mode, pulse-with-stop-on and wrapped covers whose state mirrors the
 * last command, and is hidden for pulse-with-stop-off / toggle / every other
 * wrapped cover.
 *
 * Run: npm run test:fe -- tests/frontend/send_endpoint_stop.test.mjs
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

const SEND_STOP_LABEL = "Send stop signal at endpoints";

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

function hasSendStopToggle(card) {
  const labels = [...card.shadowRoot.querySelectorAll(".toggle-label")];
  return labels.some((el) => el.textContent.trim() === SEND_STOP_LABEL);
}

function timingInputCount(card) {
  return card.shadowRoot.querySelectorAll("input.timing-input").length;
}

function runonInput(card) {
  const row = [...card.shadowRoot.querySelectorAll(".timing-table tr")].find((tr) =>
    tr.textContent.includes("Endpoint run-on time"),
  );
  return row.querySelector("input.timing-input");
}

// ---------------------------------------------------------------------------
// The toggle renders only for pulse mode
// ---------------------------------------------------------------------------

test("send_endpoint_stop toggle renders for pulse mode (default on)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: pulseCfg(),
    activeTab: "device",
  });
  expect(hasSendStopToggle(card)).toBe(true);
});

test("send_endpoint_stop toggle still renders for pulse mode when stored false", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: pulseCfg({ send_endpoint_stop: false }),
    activeTab: "device",
  });
  expect(hasSendStopToggle(card)).toBe(true);
});

test("send_endpoint_stop toggle does NOT render for switch mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "device",
  });
  expect(hasSendStopToggle(card)).toBe(false);
});

test("send_endpoint_stop toggle does NOT render for toggle mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: toggleCfg(),
    activeTab: "device",
  });
  expect(hasSendStopToggle(card)).toBe(false);
});

test("send_endpoint_stop toggle does NOT render for wrapped mode", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });
  expect(hasSendStopToggle(card)).toBe(false);
});

// ---------------------------------------------------------------------------
// Endpoint run-on row gating
//   switch mode  → 5 rows (incl. endpoint_runon_time)
//   pulse w/stop-on (default) → 5 rows (endpoint_runon_time shown)
//   pulse w/stop-off → 4 rows (endpoint_runon_time hidden)
//   single button → 5 rows (endpoint_runon_time shown, as the settle margin)
//   toggle → 4 rows (endpoint_runon_time hidden)
//   wrapped, state mirrors the last command → 5 rows (it is sent a stop)
//   any other wrapped cover → 4 rows (it is sent no stop at an endpoint)
// ---------------------------------------------------------------------------

test("switch mode shows the endpoint run-on row (5 travel rows)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: switchCfg(),
    activeTab: "timing",
  });
  expect(timingInputCount(card)).toBe(5);
});

test("pulse mode with stop on (default) shows the endpoint run-on row (5 travel rows)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: pulseCfg(),
    activeTab: "timing",
  });
  expect(timingInputCount(card)).toBe(5);
});

test("pulse mode with stop OFF hides the endpoint run-on row (4 travel rows)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: pulseCfg({ send_endpoint_stop: false }),
    activeTab: "timing",
  });
  expect(timingInputCount(card)).toBe(4);
});

test("toggle mode hides the endpoint run-on row (4 travel rows)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: toggleCfg(),
    activeTab: "timing",
  });
  expect(timingInputCount(card)).toBe(4);
});

test("wrapped cover with no stored position reporting hides the endpoint run-on row (4 travel rows)", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "timing",
  });
  expect(timingInputCount(card)).toBe(4);
});

test.each(["reliable", "unreliable", "no_endpoints", "ignore_all"])(
  "wrapped cover with %s position reporting hides the endpoint run-on row",
  async (position_reporting) => {
    card = await mountCard(makeHass(), {
      selectedEntity: "cover.x",
      config: wrappedCfg({ position_reporting }),
      activeTab: "timing",
    });
    expect(timingInputCount(card)).toBe(4);
  },
);

test("wrapped cover whose state mirrors the last command shows the endpoint run-on row", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg({ position_reporting: "command_echo", endpoint_runon_time: 2 }),
    activeTab: "timing",
  });
  expect(timingInputCount(card)).toBe(5);
  expect(runonInput(card).value).toBe("2");
});

test("choosing 'State mirrors the last command' reveals the endpoint run-on row", async () => {
  card = await mountCard(makeHass(), {
    selectedEntity: "cover.x",
    config: wrappedCfg(),
    activeTab: "device",
  });

  const select = card.shadowRoot.querySelector("#position-reporting-select");
  select.value = "command_echo";
  select.dispatchEvent(new Event("change"));
  card._activeTab = "timing";
  await card.updateComplete;

  expect(timingInputCount(card)).toBe(5);
});

test("a run-on typed for a mirroring wrapped cover is saved", async () => {
  const hass = makeHass();
  card = await mountCard(hass, {
    selectedEntity: "cover.x",
    config: wrappedCfg({ position_reporting: "command_echo", endpoint_runon_time: 2 }),
    activeTab: "timing",
  });
  vi.useFakeTimers();
  try {
    const input = runonInput(card);
    input.value = "0.5";
    input.dispatchEvent(new Event("change", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(600);
  } finally {
    vi.useRealTimers();
  }

  expect(hass.callWS).toHaveBeenCalledWith(
    expect.objectContaining({
      type: "cover_time_based/update_config",
      entity_id: "cover.x",
      endpoint_runon_time: 0.5,
    }),
  );
});
