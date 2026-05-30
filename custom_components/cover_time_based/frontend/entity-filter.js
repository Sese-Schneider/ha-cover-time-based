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

/**
 * Entity fields to null out when the control mode changes, so entities from
 * the previous mode don't linger as stale config.
 *
 * Wrapped mode uses an inner cover and none of the switch/tilt slots, so all
 * six are cleared — including tilt_open/tilt_close, which would otherwise
 * survive and trip the backend script guard. Switch/toggle keep the direction
 * switches but drop the wrapped cover and the pulse-only stop slots. Pulse
 * only drops the wrapped cover.
 */
export function clearedEntitiesForMode(mode) {
  const updates = {};
  if (mode === "wrapped") {
    updates.open_switch_entity_id = null;
    updates.close_switch_entity_id = null;
    updates.stop_switch_entity_id = null;
    updates.tilt_open_switch = null;
    updates.tilt_close_switch = null;
    updates.tilt_stop_switch = null;
  } else {
    updates.cover_entity_id = null;
  }
  if (mode !== "pulse") {
    updates.stop_switch_entity_id = null;
    updates.tilt_stop_switch = null;
  }
  return updates;
}
