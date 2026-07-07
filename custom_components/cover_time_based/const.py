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

CONF_CLOSE_INCLUDES_TILT = "close_includes_tilt"
DEFAULT_CLOSE_INCLUDES_TILT = True

CONF_IGNORE_REPORTED_POSITION = "ignore_reported_position"
DEFAULT_IGNORE_REPORTED_POSITION = False

CONF_FORCE_TIME_BASED_POSITION = "force_time_based_position"
DEFAULT_FORCE_TIME_BASED_POSITION = False

CONF_REPORTS_COMMAND_NOT_ENDPOINT = "reports_command_not_endpoint"
DEFAULT_REPORTS_COMMAND_NOT_ENDPOINT = False

CONF_INVERT = "invert"
DEFAULT_INVERT = False

CONF_ASSUMED_STATE = "assumed_state"
DEFAULT_ASSUMED_STATE = True

# Toggle mode only. When True (default) the relay is trusted to report its own
# OFF, so a relay still reporting ON is driven OFF first to force a clean edge.
# When False (hardware-managed pulse modules that self-release but never report
# the OFF, e.g. Aqara T2 — see issue #105), toggle mode only ever sends turn_on
# and never turn_off, since a turn_off is itself an activation pulse there.
CONF_RELAY_REPORTS_OFF = "relay_reports_off"
DEFAULT_RELAY_REPORTS_OFF = True

# Pulse mode only. When True (default) the integration sends the dedicated stop
# pulse when the cover reaches an endpoint (0%/100%) — required by latching
# controllers that keep running until they receive a stop (issue #129).
# When False, the endpoint stop is skipped: for auto-stop controllers that have
# already halted at their limit switch, a stop pulse received "while stopped"
# triggers a go-to-favourite reposition (classic Somfy "my" behaviour, issue
# #133), so the stop must not be sent at all.
CONF_SEND_ENDPOINT_STOP = "send_endpoint_stop"
DEFAULT_SEND_ENDPOINT_STOP = True
