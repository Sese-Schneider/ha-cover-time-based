import { beforeEach, vi } from "vitest";

beforeEach(() => {
  // window-level APIs the card calls; default to harmless no-ops/spies.
  window.loadCardHelpers = vi.fn(async () => ({
    createCardElement: async () => ({ constructor: {} }),
  }));
  window.confirm = vi.fn(() => true);
  window.alert = vi.fn();
  document.body.innerHTML = "";
});
