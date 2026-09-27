import { DOMAIN } from "./constants.js";

/** The downloadable snapshot of one cover, shaped for attaching to a bug report. */
export function buildConfigExport({
  entityId,
  config,
  stateObj,
  integrationVersion,
  haVersion,
  now,
}) {
  const { entry_id: _entryId, ...fields } = config;
  return {
    integration_version: integrationVersion || "unknown",
    home_assistant_version: haVersion || "unknown",
    exported_at: now.toISOString(),
    entity_id: entityId,
    name: stateObj?.attributes?.friendly_name ?? null,
    state: stateObj ? { state: stateObj.state, attributes: stateObj.attributes } : null,
    config: fields,
  };
}

export function exportFilename(entityId, now) {
  const objectId = entityId.split(".").slice(1).join(".");
  const pad = (n) => String(n).padStart(2, "0");
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  return `${DOMAIN}-${objectId}-${date}.json`;
}

export function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
