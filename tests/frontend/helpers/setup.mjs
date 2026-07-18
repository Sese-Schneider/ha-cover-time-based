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
  document.body.replaceChildren();
  // happy-dom under vitest exposes sessionStorage but leaves window.localStorage
  // undefined, so install a fresh Storage per test. Fresh (rather than cleared)
  // also drops any spies a previous test installed on it.
  Object.defineProperty(window, "localStorage", {
    value: new Storage(),
    configurable: true,
    writable: true,
  });
});
