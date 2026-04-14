"""Constants for the cover_time_based integration."""

DOMAIN = "cover_time_based"

CONF_TILT_MODE = "tilt_mode"
CONF_TRAVEL_TIME_CLOSE = "travel_time_close"
CONF_TRAVEL_TIME_OPEN = "travel_time_open"
CONF_TILT_TIME_CLOSE = "tilt_time_close"
CONF_TILT_TIME_OPEN = "tilt_time_open"
CONF_TRAVEL_STARTUP_DELAY = "travel_startup_delay"
CONF_TILT_STARTUP_DELAY = "tilt_startup_delay"
CONF_ENDPOINT_RUNON_TIME = "endpoint_runon_time"
CONF_MIN_MOVEMENT_TIME = "min_movement_time"
DEFAULT_ENDPOINT_RUNON_TIME = 2.0

# How the close/open buttons behave under sequential tilt modes.
#
# - "never" (default): the buttons only drive travel. Slats stay at their
#   implicit-during-travel value; use the tilt buttons to articulate.
# - "on_repeat": two-press UX. The first close/open click behaves like
#   "never". A second click from the resting closed/articulated state
#   articulates (close) or restores (open) the slats in a separate motor
#   motion.
# - "one_press": the close button runs travel+articulate in a single motor
#   motion, ending at the fully-closed (travel=0, tilt=articulated) state.
#   For open, "one_press" is equivalent to "never" — the default plan
#   already combines tilt restoration with travel.
#
# Ignored for tilt modes other than sequential_close / sequential_open.
CONF_SEQUENTIAL_BUTTON_BEHAVIOR = "sequential_button_behavior"
SEQUENTIAL_BUTTON_BEHAVIOR_NEVER = "never"
SEQUENTIAL_BUTTON_BEHAVIOR_ON_REPEAT = "on_repeat"
SEQUENTIAL_BUTTON_BEHAVIOR_ONE_PRESS = "one_press"
SEQUENTIAL_BUTTON_BEHAVIOR_VALUES = (
    SEQUENTIAL_BUTTON_BEHAVIOR_NEVER,
    SEQUENTIAL_BUTTON_BEHAVIOR_ON_REPEAT,
    SEQUENTIAL_BUTTON_BEHAVIOR_ONE_PRESS,
)
DEFAULT_SEQUENTIAL_BUTTON_BEHAVIOR = SEQUENTIAL_BUTTON_BEHAVIOR_NEVER
