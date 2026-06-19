/**
 * Characterization test for the connectedCallback already-registered branch.
 *
 * defineHaStubs() is called at module top level so that "ha-entity-picker" IS
 * registered when connectedCallback runs.  Because ha-entity-picker is already
 * defined, the lazy-load block (window.loadCardHelpers) is skipped entirely.
 *
 * Vitest runs each test file in its own happy-dom environment, so registering
 * ha-entity-picker here does NOT affect card_lifecycle.test.mjs (which
 * deliberately leaves ha-entity-picker unregistered to test the other branch).
 *
 * Run: npm run test:fe -- tests/frontend/card_lifecycle_registered.test.mjs
 */

import { test, expect, afterEach } from "vitest";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard, defineHaStubs } from "./helpers/mount.mjs";

// Register ha-entity-picker (and siblings) for this file's environment only.
defineHaStubs();

let card;
afterEach(() => {
  card?.remove();
  card = null;
});

// ---------------------------------------------------------------------------
// connectedCallback — already-registered branch
// ---------------------------------------------------------------------------

test("connectedCallback skips loadCardHelpers when ha-entity-picker is already registered", async () => {
  // ha-entity-picker IS registered (defineHaStubs() was called above).
  // The card's connectedCallback should NOT call window.loadCardHelpers().
  const hass = makeHass();
  card = await mountCard(hass);
  expect(window.loadCardHelpers).not.toHaveBeenCalled();
});
