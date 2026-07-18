/**
 * Persistence for the config card's selected device.
 *
 * The card resets its picker on every load, so the last-selected device is
 * remembered in localStorage and restored on connect. This is per-browser
 * rather than per-HA-user by design: reading it is synchronous, so the
 * selection is restored without a websocket round-trip and the picker never
 * renders empty and then jumps.
 *
 * Every access is guarded: Safari private mode and storage-disabled browsers
 * throw on localStorage access, and a forgotten selection is far better than a
 * broken picker.
 */

export const SELECTION_STORAGE_KEY = "cover_time_based_card.selected_entity";

/** Returns the remembered entity id, or "" if absent or unreadable. */
export function loadSelectedEntity() {
  try {
    return window.localStorage.getItem(SELECTION_STORAGE_KEY) || "";
  } catch (_) {
    return "";
  }
}

/** Remembers `entityId`, or forgets the selection when it is falsy. */
export function saveSelectedEntity(entityId) {
  try {
    if (entityId) {
      window.localStorage.setItem(SELECTION_STORAGE_KEY, entityId);
    } else {
      window.localStorage.removeItem(SELECTION_STORAGE_KEY);
    }
  } catch (_) {
    // storage unavailable — the selection simply isn't remembered
  }
}
