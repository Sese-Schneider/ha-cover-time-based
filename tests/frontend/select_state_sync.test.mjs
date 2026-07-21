/**
 * F3 (narrow variant): native <select>s bound via Lit's `?selected` on
 * <option> use the HTML spec's per-option "dirtiness" model — once an
 * option has been explicitly selected (by the user, or by the spec-faithful
 * stand-in `select.value = x`), later toggling the `selected` *attribute* on
 * it no longer moves the browser's displayed selection; only another
 * explicit `.value`/`.selected` assignment does. `?selected` alone can
 * therefore get a select stuck once its target option has been dirtied.
 *
 * Adapted from docs/audit/2026-07-21-audit-probes/f3_select.probe.mjs
 * (upstream repo), whose "narrow dirty-target case" is the scenario these
 * tests exercise: the option being reverted TO must itself have been
 * dirtied earlier in the session, not just the option being reverted FROM.
 *
 * Concrete real-world trigger (control-mode select): the user has, at some
 * point this session, explicitly (re-)selected the mode that is currently
 * stored server-side — that option is now dirty. They then pick a different
 * mode; autosave rejects it; the card reloads config from the server and
 * _config.control_mode reverts back to the dirty option. Pre-fix, the DOM
 * stays stuck on the rejected mode while the rest of the form (which reads
 * reactive state, not select.value) shows the reverted one.
 *
 * Run: npx vitest run tests/frontend/select_state_sync.test.mjs
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

// Device tab renders exactly two <select class="ha-select">s: control-mode
// first, tilt-mode second (see tests/frontend/card_render.test.mjs).
function controlModeSelect(el) {
  return el.shadowRoot.querySelectorAll("select.ha-select")[0];
}
function tiltModeSelect(el) {
  return el.shadowRoot.querySelectorAll("select.ha-select")[1];
}
function positionSelect(el) {
  return el.shadowRoot.querySelector("#position-select");
}

function pick(select, value) {
  select.value = value;
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

// ---------------------------------------------------------------------------
// control-mode select — concrete save-error-revert case
// ---------------------------------------------------------------------------

test("control-mode select follows a save-error revert back to a previously-dirtied mode", async () => {
  vi.useFakeTimers();
  vi.spyOn(console, "error").mockImplementation(() => {});

  const hass = makeHass({
    states: { "cover.x": { state: "closed", attributes: {} } },
    ws: {
      "cover_time_based/update_config": () => {
        throw new Error("rejected");
      },
      "cover_time_based/get_config": () => ({
        control_mode: "switch",
        open_switch_entity_id: "switch.o",
        close_switch_entity_id: "switch.c",
      }),
    },
  });

  card = await mountCard(hass, {
    selectedEntity: "cover.x",
    config: {
      control_mode: "switch",
      open_switch_entity_id: "switch.o",
      close_switch_entity_id: "switch.c",
    },
    activeTab: "device",
  });

  const select = controlModeSelect(card);
  expect(select).toBeTruthy();

  // User re-affirms "switch" — dirties the option they'll later revert to.
  pick(select, "switch");
  await card.updateComplete;

  // User picks "pulse" — dirties it; it's also the mode the mocked save rejects.
  pick(select, "pulse");
  await card.updateComplete;
  expect(card._config.control_mode).toBe("pulse");

  // Save fails -> _autoSave's catch path reloads config, reverting
  // _config.control_mode back to the server's (dirtied) "switch".
  await card._autoSave();
  await card.updateComplete;

  expect(card._config.control_mode).toBe("switch");
  // THE BUG: select.value should follow reactive state, not stay stuck on
  // the rejected "pulse" pick.
  expect(select.value).toBe("switch");
});

// ---------------------------------------------------------------------------
// tilt-mode select — programmatic revert to a previously-dirtied mode
// ---------------------------------------------------------------------------

test("tilt-mode select follows a programmatic revert back to a previously-dirtied mode", async () => {
  const hass = makeHass({
    states: { "cover.x": { state: "closed", attributes: {} } },
  });
  card = await mountCard(hass, {
    selectedEntity: "cover.x",
    config: {
      control_mode: "switch",
      open_switch_entity_id: "switch.o",
      close_switch_entity_id: "switch.c",
      tilt_mode: "none",
    },
    activeTab: "device",
  });

  const select = tiltModeSelect(card);
  expect(select).toBeTruthy();

  // User re-affirms "none" — dirties it.
  pick(select, "none");
  await card.updateComplete;

  // User picks "sequential_close" — dirties it.
  pick(select, "sequential_close");
  await card.updateComplete;
  expect(card._config.tilt_mode).toBe("sequential_close");

  // Something programmatically reverts tilt_mode back to the previously
  // dirtied "none" (e.g. a save-error reload — exercised end-to-end for
  // control-mode above; mirrored directly here for the tilt-mode select).
  card._config = { ...card._config, tilt_mode: "none" };
  card.requestUpdate();
  await card.updateComplete;

  expect(card._config.tilt_mode).toBe("none");
  expect(select.value).toBe("none");
});

// ---------------------------------------------------------------------------
// position-select — programmatic _knownPosition reset to a dirtied preset
// ---------------------------------------------------------------------------

test("position-select follows a programmatic _knownPosition reset back to a previously-dirtied preset", async () => {
  const hass = makeHass({
    states: { "cover.x": { state: "open", attributes: {} } },
  });
  card = await mountCard(hass, {
    selectedEntity: "cover.x",
    config: {
      control_mode: "switch",
      open_switch_entity_id: "switch.o",
      close_switch_entity_id: "switch.c",
      tilt_mode: "none",
    },
    activeTab: "timing",
  });

  const select = positionSelect(card);
  expect(select).toBeTruthy();
  expect(select.value).toBe("unknown");

  // User explicitly picks "Set position..." (unknown) — dirties it.
  pick(select, "unknown");
  await card.updateComplete;

  // User then picks "Fully open".
  pick(select, "open");
  await card.updateComplete;
  expect(card._knownPosition).toBe("open");

  // A raw cover command resets _knownPosition to "unknown" programmatically —
  // and "unknown" is the option dirtied above.
  await card._onCoverCommand("stop_cover");
  await card.updateComplete;

  expect(card._knownPosition).toBe("unknown");
  expect(select.value).toBe("unknown");
});
