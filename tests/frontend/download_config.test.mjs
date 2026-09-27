/**
 * Download-config button: the card exports the displayed cover's settings,
 * plus the context a bug report needs, as a JSON file.
 *
 * Run: npm run test:fe -- tests/frontend/download_config.test.mjs
 */

import { test, expect, afterEach, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard, defineHaStubs } from "./helpers/mount.mjs";
import {
  buildConfigExport,
  exportFilename,
} from "../../custom_components/cover_time_based/frontend/config-export.js";

defineHaStubs();
let card;
afterEach(() => {
  vi.restoreAllMocks();
  card?.remove();
  card = null;
});

const NOW = new Date(2026, 8, 27, 14, 3, 11);

const stateObj = {
  state: "open",
  attributes: { friendly_name: "Living room", current_position: 100 },
};

// ---------------------------------------------------------------------------
// buildConfigExport / exportFilename
// ---------------------------------------------------------------------------

test("buildConfigExport carries versions, identity, live state and the config", () => {
  const data = buildConfigExport({
    entityId: "cover.living_room",
    config: { entry_id: "abc123", control_mode: "switch", travel_time_open: 23.4 },
    stateObj,
    integrationVersion: "4.13.0",
    haVersion: "2026.9.2",
    now: NOW,
  });
  expect(data).toEqual({
    integration_version: "4.13.0",
    home_assistant_version: "2026.9.2",
    exported_at: NOW.toISOString(),
    entity_id: "cover.living_room",
    name: "Living room",
    state: stateObj,
    config: { control_mode: "switch", travel_time_open: 23.4 },
  });
});

test("buildConfigExport drops the internal entry_id from the config", () => {
  const data = buildConfigExport({
    entityId: "cover.x",
    config: { entry_id: "abc123", control_mode: "switch" },
    now: NOW,
  });
  expect(data.config).not.toHaveProperty("entry_id");
});

test("buildConfigExport writes unknown/null when versions or state are missing", () => {
  const data = buildConfigExport({
    entityId: "cover.x",
    config: { control_mode: "switch" },
    stateObj: undefined,
    now: NOW,
  });
  expect(data.integration_version).toBe("unknown");
  expect(data.home_assistant_version).toBe("unknown");
  expect(data.name).toBeNull();
  expect(data.state).toBeNull();
});

test("exportFilename is domain, object id and local date", () => {
  expect(exportFilename("cover.living_room", NOW)).toBe(
    "cover_time_based-living_room-2026-09-27.json",
  );
});

// ---------------------------------------------------------------------------
// Card button
// ---------------------------------------------------------------------------

const cfg = { entry_id: "abc123", control_mode: "switch", travel_time_open: 23.4 };

function hassWith(ws = {}) {
  const hass = makeHass({
    states: { "cover.living_room": stateObj },
    ws: { "manifest/get": () => ({ domain: "cover_time_based", version: "4.13.0" }), ...ws },
    config: { version: "2026.9.2" },
  });
  return hass;
}

// Captures what the card hands the browser to save: the anchor's filename
// and the JSON inside the Blob behind its object URL.
function captureDownload() {
  const captured = {};
  vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => {
    captured.blob = blob;
    return "blob:fake";
  });
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function () {
    captured.filename = this.download;
    captured.href = this.href;
  });
  return captured;
}

test("no download button before a config has loaded", async () => {
  card = await mountCard(hassWith(), { selectedEntity: "cover.living_room", config: null });
  expect(card.shadowRoot.querySelector(".download-config")).toBeNull();
});

test("clicking the download button saves the export as a JSON file", async () => {
  const captured = captureDownload();
  card = await mountCard(hassWith(), { selectedEntity: "cover.living_room", config: cfg });

  const button = card.shadowRoot.querySelector(".download-config");
  expect(button).not.toBeNull();
  button.click();
  await vi.waitFor(() => expect(captured.filename).toBeDefined());

  expect(captured.filename).toMatch(/^cover_time_based-living_room-\d{4}-\d{2}-\d{2}\.json$/);
  expect(captured.href).toBe("blob:fake");
  const data = JSON.parse(await captured.blob.text());
  expect(data).toMatchObject({
    integration_version: "4.13.0",
    home_assistant_version: "2026.9.2",
    entity_id: "cover.living_room",
    name: "Living room",
    state: stateObj,
    config: { control_mode: "switch", travel_time_open: 23.4 },
  });
  expect(data.config).not.toHaveProperty("entry_id");
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake");
});

test("a failed version lookup still downloads, with the version marked unknown", async () => {
  const captured = captureDownload();
  vi.spyOn(console, "warn").mockImplementation(() => {});
  card = await mountCard(
    hassWith({
      "manifest/get": () => {
        throw new Error("nope");
      },
    }),
    { selectedEntity: "cover.living_room", config: cfg },
  );

  card.shadowRoot.querySelector(".download-config").click();
  await vi.waitFor(() => expect(captured.blob).toBeDefined());

  const data = JSON.parse(await captured.blob.text());
  expect(data.integration_version).toBe("unknown");
});

test.each(["Enter", " "])("the download button responds to %j like a click", async (key) => {
  const captured = captureDownload();
  card = await mountCard(hassWith(), { selectedEntity: "cover.living_room", config: cfg });

  card.shadowRoot
    .querySelector(".download-config")
    .dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
  await vi.waitFor(() => expect(captured.filename).toBeDefined());
});

// ---------------------------------------------------------------------------
// Pending edits are saved before the download
// ---------------------------------------------------------------------------

function deferred() {
  let resolve;
  const promise = new Promise((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

test("a pending edit is saved before the download, and the file holds it", async () => {
  const captured = captureDownload();
  const hass = hassWith();
  HTMLAnchorElement.prototype.click.mockImplementation(function () {
    captured.filename = this.download;
    captured.callsAtDownload = hass.callWS.mock.calls.map(([msg]) => msg.type);
  });
  card = await mountCard(hass, { selectedEntity: "cover.living_room", config: cfg });

  card._updateLocal({ travel_time_open: 30 });
  card.shadowRoot.querySelector(".download-config").click();
  await vi.waitFor(() => expect(captured.filename).toBeDefined());

  expect(captured.callsAtDownload).toContain("cover_time_based/update_config");
  expect(hass.callWS).toHaveBeenCalledWith(
    expect.objectContaining({ type: "cover_time_based/update_config", travel_time_open: 30 }),
  );
  const data = JSON.parse(await captured.blob.text());
  expect(data.config.travel_time_open).toBe(30);
});

test("a pending edit the server rejects is left out of the file", async () => {
  const captured = captureDownload();
  vi.spyOn(console, "error").mockImplementation(() => {});
  card = await mountCard(
    hassWith({
      "cover_time_based/update_config": () => {
        throw new Error("rejected");
      },
      "cover_time_based/get_config": () => cfg,
    }),
    { selectedEntity: "cover.living_room", config: cfg },
  );

  card._updateLocal({ travel_time_open: 999 });
  card.shadowRoot.querySelector(".download-config").click();
  await vi.waitFor(() => expect(captured.blob).toBeDefined());

  const data = JSON.parse(await captured.blob.text());
  expect(data.config.travel_time_open).toBe(23.4);
});

test("a save already in flight is waited for before the download", async () => {
  const captured = captureDownload();
  const save = deferred();
  card = await mountCard(hassWith({ "cover_time_based/update_config": () => save.promise }), {
    selectedEntity: "cover.living_room",
    config: cfg,
  });

  card._updateLocal({ travel_time_open: 30 });
  card._flushAutoSave();
  card.shadowRoot.querySelector(".download-config").click();
  await new Promise((r) => setTimeout(r, 20));
  expect(captured.filename).toBeUndefined();

  save.resolve({});
  await vi.waitFor(() => expect(captured.filename).toBeDefined());
});

test("switching covers while the save runs cancels the download", async () => {
  const captured = captureDownload();
  const save = deferred();
  card = await mountCard(hassWith({ "cover_time_based/update_config": () => save.promise }), {
    selectedEntity: "cover.living_room",
    config: cfg,
  });

  card._updateLocal({ travel_time_open: 30 });
  card.shadowRoot.querySelector(".download-config").click();
  await new Promise((r) => setTimeout(r, 0));
  card._selectedEntity = "cover.other";
  save.resolve({});
  await new Promise((r) => setTimeout(r, 20));

  expect(captured.filename).toBeUndefined();
});

// While calibrating, _autoSave re-arms instead of saving, so the edit is still
// pending when the file is written. Cleanup cancels that re-arming timer and
// the override, so removal neither saves nor stops a calibration.
function endCalibrationWithoutSaving(card) {
  clearTimeout(card._autoSaveTimer);
  card._autoSaveTimer = null;
  card._calibratingOverride = undefined;
}

test("while calibrating, the file holds the server's config and the pending edit stays unsaved", async () => {
  const captured = captureDownload();
  const hass = hassWith({ "cover_time_based/get_config": () => cfg });
  card = await mountCard(hass, { selectedEntity: "cover.living_room", config: cfg });

  try {
    card._updateLocal({ travel_time_open: 30 });
    card._calibratingOverride = true;
    card.shadowRoot.querySelector(".download-config").click();
    await vi.waitFor(() => expect(captured.blob).toBeDefined());

    const data = JSON.parse(await captured.blob.text());
    expect(data.config.travel_time_open).toBe(23.4);
    expect(hass.callWS).not.toHaveBeenCalledWith(
      expect.objectContaining({ type: "cover_time_based/update_config" }),
    );
    expect(card._config.travel_time_open).toBe(30);
    expect(card._autoSaveTimer).toBeTruthy();
  } finally {
    endCalibrationWithoutSaving(card);
  }
});

test("while calibrating, a save already in flight is waited for before the server's config is read", async () => {
  const captured = captureDownload();
  const save = deferred();
  const hass = hassWith({
    "cover_time_based/update_config": () => save.promise,
    "cover_time_based/get_config": () => ({ ...cfg, travel_time_open: 30 }),
  });
  card = await mountCard(hass, { selectedEntity: "cover.living_room", config: cfg });

  try {
    card._updateLocal({ travel_time_open: 30 });
    card._flushAutoSave();
    card._calibratingOverride = true;
    const callsBeforeClick = hass.callWS.mock.calls.length;
    const typesAfterClick = () =>
      hass.callWS.mock.calls.slice(callsBeforeClick).map(([msg]) => msg.type);

    card.shadowRoot.querySelector(".download-config").click();
    await new Promise((r) => setTimeout(r, 20));
    expect(typesAfterClick()).not.toContain("cover_time_based/get_config");
    expect(captured.filename).toBeUndefined();

    save.resolve({});
    await vi.waitFor(() => expect(captured.blob).toBeDefined());

    const types = hass.callWS.mock.calls.map(([msg]) => msg.type);
    expect(types.lastIndexOf("cover_time_based/get_config")).toBeGreaterThan(
      types.indexOf("cover_time_based/update_config"),
    );
    const data = JSON.parse(await captured.blob.text());
    expect(data.config.travel_time_open).toBe(30);
  } finally {
    endCalibrationWithoutSaving(card);
  }
});

test("while calibrating, a failed read of the server's config produces no file", async () => {
  const captured = captureDownload();
  const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  card = await mountCard(
    hassWith({
      "cover_time_based/get_config": () => {
        throw new Error("offline");
      },
    }),
    { selectedEntity: "cover.living_room", config: cfg },
  );

  try {
    card._calibratingOverride = true;
    card.shadowRoot.querySelector(".download-config").click();
    await vi.waitFor(() => expect(errorSpy).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));

    expect(captured.filename).toBeUndefined();
  } finally {
    endCalibrationWithoutSaving(card);
  }
});

test("the download icon is highlighted on hover and keyboard focus", () => {
  const styles = readFileSync(
    path.join(
      path.dirname(fileURLToPath(import.meta.url)),
      "../../custom_components/cover_time_based/frontend/card-styles.js",
    ),
    "utf8",
  );
  expect(styles).toMatch(
    /\.download-config:hover,\s*\.download-config:focus-visible\s*\{[^}]*\bbackground\s*:/,
  );
});
