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
