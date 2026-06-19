import { vi } from "vitest";

const DEFAULT_WS = {
  "config/entity_registry/list": () => [],
  "config_entries/get": () => [],
  "cover_time_based/get_config": () => ({ control_mode: "switch" }),
  "cover_time_based/update_config": () => ({}),
  "cover_time_based/start_calibration": () => ({}),
  "cover_time_based/stop_calibration": () => ({}),
  "cover_time_based/raw_command": () => ({}),
};

export function makeHass({
  states = {},
  entities = {},
  language = "en",
  ws = {},
  service,
} = {}) {
  const routes = { ...DEFAULT_WS, ...ws };
  return {
    states,
    entities,
    language,
    callWS: vi.fn(async ({ type, ...params }) => {
      const handler = routes[type];
      if (handler === undefined) {
        throw new Error(`makeHass: unhandled callWS type "${type}"`);
      }
      return typeof handler === "function" ? handler(params) : handler;
    }),
    callService: vi.fn(service ?? (async () => ({}))),
  };
}
