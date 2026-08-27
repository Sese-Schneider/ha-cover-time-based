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

# Retained only so configs written while the gap was briefly configurable keep
# loading — the key is accepted and ignored. See DIRECTION_CHANGE_DELAY.
CONF_DIRECTION_CHANGE_DELAY = "direction_change_delay"
# Gap between the stop and the new direction when reversing a moving cover, so
# the motor comes to rest before being driven the other way. Fixed, and equal
# to the value every release has used.
#
# It was briefly per-cover configurable (4.9.0 release candidates only, never a
# promoted release) on the theory that 1.0s was too short for some motors. That
# did not survive the reporter's own hardware: it reverses correctly at 1.0s,
# the value earlier versions already used. The knob's only demonstrated effect
# was allowing values *below* 1.0s, which desync the cover — and in
# toggle-opposite mode the desync is amplified, because a "stop" there is a
# pulse of the opposite relay, which on an already-stopped motor is a movement
# command that runs the cover to its endpoint (issue #153).
#
# 1.0s also dominates any legitimate relay pulse window: momentary-relay
# firmware is documented to hold for well under a second, so whether a rapid
# re-pulse fails because the relay has not released or because the motor has
# not settled, this gap covers both.
DIRECTION_CHANGE_DELAY = 1.0

CONF_CLOSE_INCLUDES_TILT = "close_includes_tilt"
DEFAULT_CLOSE_INCLUDES_TILT = True

CONF_IGNORE_REPORTED_POSITION = "ignore_reported_position"
DEFAULT_IGNORE_REPORTED_POSITION = False

CONF_FORCE_TIME_BASED_POSITION = "force_time_based_position"
DEFAULT_FORCE_TIME_BASED_POSITION = False

CONF_REPORTS_COMMAND_NOT_ENDPOINT = "reports_command_not_endpoint"
DEFAULT_REPORTS_COMMAND_NOT_ENDPOINT = False

CONF_IGNORE_ENDPOINT_STATES = "ignore_endpoint_states"
DEFAULT_IGNORE_ENDPOINT_STATES = False

CONF_IGNORE_ALL_REPORTS = "ignore_all_reports"
DEFAULT_IGNORE_ALL_REPORTS = False

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

# All modes. When True, an open_cover / close_cover commanded while the tracker
# already believes it is settled at that endpoint is re-driven for the full
# travel time (modeled from the opposite endpoint) instead of being skipped as a
# no-op / short resync. For covers with no position feedback that are also moved
# by an external remote (issue #167), HA's belief is untrustworthy, so the
# endpoint command must actually reach the underlying device.
CONF_FORCE_ENDPOINT_REDRIVE = "force_endpoint_redrive"
DEFAULT_FORCE_ENDPOINT_REDRIVE = False

# When True, movement commands wait for the underlying relay to confirm its state
# change before proceeding. Behaviour is implemented elsewhere; this constant is
# the plumbed per-cover config option.
CONF_WAIT_FOR_RELAY_FEEDBACK = "wait_for_relay_feedback"
DEFAULT_WAIT_FOR_RELAY_FEEDBACK = False

# All modes. When True, a set_cover_position command first drives the cover
# fully open — a physical datum, since the motor stalls against its limit — and
# only then moves to the requested position. For a cover with no position
# feedback that an external remote may also have moved (issue #179), the
# believed position is untrustworthy, so a timed move from it lands anywhere;
# the reporter's case is a shutter that must never be driven into an
# obstruction below it. Every move costs a full open plus the run back down
# to the target — between one and two times the cover's full travel time,
# however small the change — which is why it is off by default.
#
# Endpoint targets (0/100) have no separate leg to arm: forcing the drive
# straight to that endpoint (modeled from the opposite one, like
# CONF_FORCE_ENDPOINT_REDRIVE) already recalibrates it, so it just runs once
# instead of a leg A + leg B pair. That carve-out is asymmetric for tilt —
# see CoverTimeBased._recalibration_plan.
CONF_RECALIBRATE_BEFORE_POSITION = "recalibrate_before_position"
DEFAULT_RECALIBRATE_BEFORE_POSITION = False
