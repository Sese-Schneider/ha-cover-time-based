/**
 * Filter entity registry entries to those backed by a live config entry.
 *
 * HA can retain entity registry records after a config entry is deleted
 * (the "this device is no longer provided by this integration" state).
 * Such orphans still carry the deleted entry's id, so a naive filter that
 * only checks `config_entry_id` truthiness lists phantom covers.  This
 * helper additionally requires the id to appear in the live config-entry
 * set passed by the caller.
 */

export function filterEntitiesByValidEntries(
  entityRegistry,
  validConfigEntryIds,
  platform
) {
  const valid = new Set(validConfigEntryIds);
  return entityRegistry
    .filter(
      (e) =>
        e.platform === platform &&
        e.config_entry_id &&
        valid.has(e.config_entry_id)
    )
    .map((e) => e.entity_id);
}

/**
 * Entity-picker domains for switch-based control modes.
 *
 * Pulse mode commands via homeassistant.turn_on/off and ignores the OFF
 * edge, so `script` entities (e.g. IR-remote open/close/stop scripts) work
 * there. Switch and toggle modes rely on a latched/held state a script
 * cannot provide, so they stay switch-only.
 */
export function switchPickerDomains(controlMode) {
  return controlMode === "pulse" ? ["switch", "script"] : ["switch"];
}

/**
 * Translation-key selector for switch/script picker labels.
 *
 * In pulse mode the picker accepts switches OR scripts, so labels use a
 * "<base>_pulse" variant (e.g. "Open switch or script"). Other modes use
 * the base key.
 */
export function switchLabelKey(baseKey, controlMode) {
  return controlMode === "pulse" ? `${baseKey}_pulse` : baseKey;
}
