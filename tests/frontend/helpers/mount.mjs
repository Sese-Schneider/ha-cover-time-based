import "../../../custom_components/cover_time_based/frontend/cover-time-based-card.js";

const HA_STUBS = [
  "ha-card", "ha-entity-picker", "ha-switch", "ha-icon", "ha-input", "ha-textfield",
];

export function defineHaStubs() {
  for (const tag of HA_STUBS) {
    if (!customElements.get(tag)) {
      customElements.define(tag, class extends HTMLElement {});
    }
  }
}

export async function mountCard(
  hass,
  { config = null, selectedEntity = "", activeTab, knownPosition } = {}
) {
  const el = document.createElement("cover-time-based-card");
  el._config = config;
  el._selectedEntity = selectedEntity;
  if (activeTab !== undefined) el._activeTab = activeTab;
  if (knownPosition !== undefined) el._knownPosition = knownPosition;
  el.hass = hass;
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}
