/**
 * Favourite position UI — issue #329.
 *
 * The section holds a position and, for covers with slats, a tilt. Once a
 * favourite is set it offers the gesture that recalls it; the gesture's own
 * fields (trigger entity, hold time, action) appear only when they apply.
 *
 * Run: npm run test:fe -- tests/frontend/favourite.test.mjs
 */

import { test, expect, afterEach, vi } from "vitest";
import { makeHass } from "./helpers/hass.mjs";
import { mountCard, defineHaStubs } from "./helpers/mount.mjs";

defineHaStubs();
let card;
afterEach(() => {
  vi.restoreAllMocks();
  card?.remove();
  card = null;
});

const toggleCfg = (over = {}) => ({
  control_mode: "toggle",
  open_switch_entity_id: "switch.o",
  close_switch_entity_id: "switch.c",
  ...over,
});

const wrappedCfg = (over = {}) => ({
  control_mode: "wrapped",
  cover_entity_id: "cover.real",
  ...over,
});

async function mount(config, hass = makeHass()) {
  card = await mountCard(hass, { selectedEntity: "cover.x", config, activeTab: "device" });
  return card;
}

const section = (c) => c.shadowRoot.querySelector(".favourite");
const fields = (c) => [...section(c).querySelectorAll(".favourite-fields > *")];
const fieldByLabel = (c, label) =>
  [...section(c).querySelectorAll("ha-input, ha-textfield")].find(
    (el) => el.getAttribute("label") === label,
  );
const gestureSelect = (c) => section(c).querySelector("#favourite-gesture-select");
const actionSelect = (c) => section(c).querySelector("#favourite-action-select");
const optionValues = (select) => [...select.options].map((o) => o.value);

function capture(c) {
  const captured = [];
  c._updateLocal = (u) => captured.push(u);
  return captured;
}

function change(el, value) {
  el.value = value;
  el.dispatchEvent(new Event("change"));
}

test("with no favourite only the position is offered", async () => {
  await mount(toggleCfg());
  expect(fields(card)).toHaveLength(1);
  expect(section(card).textContent).not.toContain("or both");
  expect(gestureSelect(card)).toBeNull();
  expect(actionSelect(card)).toBeNull();
});

test("a cover with slats also offers the tilt", async () => {
  await mount(toggleCfg({ tilt_mode: "sequential_open" }));
  expect(fields(card)).toHaveLength(2);
  expect(section(card).textContent).toContain("Set the position, the tilt, or both.");
});

test("the tilt alone is a favourite too", async () => {
  await mount(toggleCfg({ tilt_mode: "sequential_open", favourite_tilt_position: 30 }));
  expect(gestureSelect(card)).not.toBeNull();
  expect(section(card).querySelector("#favourite-clear").hasAttribute("disabled")).toBe(false);
});

test("typing a position stores it, clearing it removes the favourite", async () => {
  await mount(toggleCfg({ favourite_position: 20 }));
  const captured = capture(card);
  const position = fieldByLabel(card, "Position");

  change(position, "35");
  change(position, "");
  change(position, "140");

  expect(captured).toEqual([{ favourite_position: 35 }, { favourite_position: null }]);
});

test("a favourite brings up the gesture, off by default", async () => {
  await mount(toggleCfg({ favourite_position: 0 }));
  expect(gestureSelect(card).value).toBe("none");
  expect(optionValues(gestureSelect(card))).toEqual(["none", "both_inputs", "entity"]);
  expect(actionSelect(card)).toBeNull();
});

test("a wrapped cover has no pair of inputs to hold", async () => {
  await mount(wrappedCfg({ favourite_position: 0, favourite_gesture: "both_inputs" }));
  expect(optionValues(gestureSelect(card))).toEqual(["none", "entity"]);
  expect(gestureSelect(card).value).toBe("none");
  expect(actionSelect(card)).toBeNull();
});

test("switch mode does not offer both inputs: its relays are never on together", async () => {
  await mount(
    toggleCfg({ control_mode: "switch", favourite_position: 0, favourite_gesture: "both_inputs" }),
  );
  expect(optionValues(gestureSelect(card))).toEqual(["none", "entity"]);
  expect(gestureSelect(card).value).toBe("none");
});

test("the gesture fields are captioned fields, not headings of their own", async () => {
  await mount(toggleCfg({ favourite_position: 0, favourite_gesture: "both_inputs" }));
  const headings = [...section(card).querySelectorAll(".field-label")];
  expect(headings.map((el) => el.textContent.trim())).toEqual(["Favourite position"]);
  const captions = [...section(card).querySelectorAll("label.favourite-caption")];
  expect(captions.map((el) => el.textContent.trim())).toEqual(["Recalled by", "On the gesture"]);
  expect(captions.map((el) => el.getAttribute("for"))).toEqual([
    "favourite-gesture-select",
    "favourite-action-select",
  ]);
});

test("choosing a gesture stores it", async () => {
  await mount(toggleCfg({ favourite_position: 0 }));
  const captured = capture(card);
  change(gestureSelect(card), "both_inputs");
  expect(captured).toEqual([{ favourite_gesture: "both_inputs" }]);
});

test("both inputs shows the hold time and the action, not a trigger entity", async () => {
  await mount(toggleCfg({ favourite_position: 0, favourite_gesture: "both_inputs" }));
  expect(fieldByLabel(card, "Hold time").value).toBe("3");
  expect(actionSelect(card).value).toBe("track");
  expect(section(card).querySelector("#favourite-trigger-entity")).toBeNull();
});

test("the entity gesture asks which entity and which state", async () => {
  await mount(
    wrappedCfg({
      favourite_position: 0,
      favourite_gesture: "entity",
      favourite_trigger_entity_id: "sensor.buttons",
      favourite_trigger_state: "stop",
      favourite_action: "drive",
      favourite_hold_time: 2,
    }),
  );
  expect(section(card).querySelector("#favourite-trigger-entity").value).toBe("sensor.buttons");
  expect(fieldByLabel(card, "State").value).toBe("stop");
  expect(fieldByLabel(card, "Hold time").value).toBe("2");
  expect(actionSelect(card).value).toBe("drive");
});

test("the trigger entity and its state are stored when changed", async () => {
  await mount(wrappedCfg({ favourite_position: 0, favourite_gesture: "entity" }));
  const captured = capture(card);
  card._onSwitchEntityChange = (field, e) => captured.push({ [field]: e.detail.value });

  section(card)
    .querySelector("#favourite-trigger-entity")
    .dispatchEvent(new CustomEvent("value-changed", { detail: { value: "sensor.buttons" } }));
  change(fieldByLabel(card, "State"), " stop ");
  change(fieldByLabel(card, "State"), "");

  expect(captured).toEqual([
    { favourite_trigger_entity_id: "sensor.buttons" },
    { favourite_trigger_state: "stop" },
    { favourite_trigger_state: null },
  ]);
});

test("the hold time and the action are stored when changed", async () => {
  await mount(toggleCfg({ favourite_position: 0, favourite_gesture: "both_inputs" }));
  const captured = capture(card);

  change(fieldByLabel(card, "Hold time"), "4.5");
  change(fieldByLabel(card, "Hold time"), "0");
  change(actionSelect(card), "drive");

  expect(captured).toEqual([{ favourite_hold_time: 4.5 }, { favourite_action: "drive" }]);
});

test("use current position copies what the cover reports", async () => {
  const hass = makeHass({
    states: {
      "cover.x": {
        entity_id: "cover.x",
        state: "open",
        attributes: { current_position: 42, current_tilt_position: 10 },
      },
    },
  });
  await mount(toggleCfg({ tilt_mode: "sequential_open" }), hass);
  const captured = capture(card);

  section(card).querySelector("#favourite-use-current").click();

  expect(captured).toEqual([{ favourite_position: 42, favourite_tilt_position: 10 }]);
});

test("remove the favourite clears the position and the tilt", async () => {
  await mount(
    toggleCfg({
      tilt_mode: "sequential_open",
      favourite_position: 0,
      favourite_tilt_position: 0,
    }),
  );
  const captured = capture(card);

  section(card).querySelector("#favourite-clear").click();

  expect(captured).toEqual([{ favourite_position: null, favourite_tilt_position: null }]);
});

test("there is nothing to remove while no favourite is set", async () => {
  await mount(toggleCfg());
  expect(section(card).querySelector("#favourite-clear").hasAttribute("disabled")).toBe(true);
});

test("use current position is unavailable while the position is unknown", async () => {
  await mount(toggleCfg());
  expect(section(card).querySelector("#favourite-use-current").hasAttribute("disabled")).toBe(true);
});

test("a separate tilt motor is flagged when the gesture only follows", async () => {
  const dual = {
    tilt_mode: "dual_motor",
    favourite_position: 0,
    favourite_gesture: "both_inputs",
  };
  await mount(toggleCfg(dual));
  expect(section(card).textContent).toContain("tracks the travel only");

  card.remove();
  await mount(toggleCfg({ ...dual, favourite_action: "drive" }));
  expect(section(card).textContent).not.toContain("tracks the travel only");
});
