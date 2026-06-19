import { beforeEach, vi } from "vitest";

beforeEach(() => {
  // window-level APIs the card calls; default to harmless no-ops/spies.
  window.loadCardHelpers = vi.fn(async () => ({
    createCardElement: async () => ({
      constructor: {
        getConfigElement: async () => {
          // Mirrors production: loadCardHelpers → getConfigElement registers ha-entity-picker.
          // This prevents the connectedCallback's second `if` from creating a 10s real timer.
          if (!customElements.get("ha-entity-picker")) {
            customElements.define("ha-entity-picker", class extends HTMLElement {});
          }
        },
      },
    }),
  }));
  window.confirm = vi.fn(() => true);
  window.alert = vi.fn();
  document.body.innerHTML = "";
});
