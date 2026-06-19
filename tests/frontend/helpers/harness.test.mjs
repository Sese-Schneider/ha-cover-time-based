import { test, expect, afterEach } from "vitest";
import { makeHass } from "./hass.mjs";
import { mountCard, defineHaStubs } from "./mount.mjs";

defineHaStubs();
let card;
afterEach(() => card?.remove());

test("card mounts and renders its header into the shadow root", async () => {
  card = await mountCard(makeHass());
  const header = card.shadowRoot.querySelector(".card-header");
  expect(header).not.toBeNull();
  expect(header.textContent.trim()).toBe("Cover Time Based Configuration");
});

test("render() returns empty when hass is unset", async () => {
  card = await mountCard(undefined);
  expect(card.shadowRoot.querySelector("ha-card")).toBeNull();
});
