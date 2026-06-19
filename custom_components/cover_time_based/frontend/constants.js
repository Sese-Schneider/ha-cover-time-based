export const DOMAIN = "cover_time_based";

// Keys are config attribute names; values are translation keys.
export const TIMING_ATTRIBUTES = [
  ["travel_time_close", "timing.travel_time_close"],
  ["travel_time_open", "timing.travel_time_open"],
  ["travel_startup_delay", "timing.travel_startup_delay"],
  ["tilt_time_close", "timing.tilt_time_close"],
  ["tilt_time_open", "timing.tilt_time_open"],
  ["tilt_startup_delay", "timing.tilt_startup_delay"],
  ["min_movement_time", "timing.min_movement_time"],
];

export const ATTRIBUTE_TO_CONFIG = {
  travel_time_close: "travel_time_close",
  travel_time_open: "travel_time_open",
  tilt_time_close: "tilt_time_close",
  tilt_time_open: "tilt_time_open",
  travel_startup_delay: "travel_startup_delay",
  tilt_startup_delay: "tilt_startup_delay",
  min_movement_time: "min_movement_time",
};
