/**
 * Text-field element shim — picker only.
 *
 * HA 2026.4 introduced <ha-input> as the successor to <ha-textfield>;
 * <ha-textfield> is scheduled for removal in 2026.5. Prefer ha-input
 * when the custom element is registered, fall back to ha-textfield on
 * older HA versions.
 *
 * Kept lit-free so it can be unit-tested under plain Node without a DOM.
 * The lit-rendering counterpart lives in textfield-render.js.
 */

export function textfieldTagName(
  registry = typeof customElements !== "undefined" ? customElements : null,
) {
  if (registry && registry.get("ha-input")) return "ha-input";
  return "ha-textfield";
}
