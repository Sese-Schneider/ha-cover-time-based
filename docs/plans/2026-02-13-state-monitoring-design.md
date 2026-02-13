# State Monitoring Design

## Problem

The cover_time_based integration is purely one-directional: it sends commands to switch entities but never listens to their state. If someone presses a physical button (or uses the Shelly app), the integration has no idea the cover is moving. The travel calculator stays out of sync with reality.

## Goal

Detect when switches are toggled externally (physical button, app, automation) and update the travel calculator accordingly, achieving full parity with HA-initiated commands. Physical button presses always target fully open (0%) or fully closed (100%).

## Approach: State Change Listeners with Echo Filtering

### Event Registration

In `async_added_to_hass`, register `async_track_state_change_event` listeners on:
- `_open_switch_entity_id`
- `_close_switch_entity_id`
- `_stop_switch_entity_id` (if present)

Store unsubscribe callbacks. Clean up in `async_will_remove_from_hass`.

### Echo Filtering

When the integration sends a command, the hardware echoes back state changes. We must distinguish echoes from genuine external events.

**Mechanism**: `_pending_switch: dict[str, bool]` tracks which switches have pending echoes.

- Before `_async_handle_command` toggles a switch, set `_pending_switch[entity_id] = True`
- When a state change fires for that entity and the flag is set, clear the flag and ignore the event
- For pulse/toggle modes (ON then OFF), the flag persists across both transitions; cleared after the OFF echo
- For switch mode (latching), cleared after the first echo
- Safety net: clear pending flags after a timeout (3 seconds) in case an echo is lost

### State Change Handler

`_handle_switch_state_change(entity_id, old_state, new_state)` handles non-echo state changes per mode:

**Switch mode** (latching):
- `open_switch` ON: start opening (fully open)
- `open_switch` OFF: stop
- `close_switch` ON: start closing (fully closed)
- `close_switch` OFF: stop
- `stop_switch` ON: stop

**Pulse mode** (momentary):
- `open_switch` ON->OFF: start opening (fully open)
- `close_switch` ON->OFF: start closing (fully closed)
- `stop_switch` ON->OFF: stop

**Toggle mode** (same button stops):
- `open_switch` ON->OFF while not traveling: start opening (fully open)
- `open_switch` ON->OFF while traveling up: stop
- `open_switch` ON->OFF while traveling down: stop, then start opening
- Same logic mirrored for `close_switch`

### Skipping Hardware Commands for External Events

When reacting to an external event, we must NOT send commands back to the switches (the hardware already toggled them). Use a `_triggered_externally` flag:

- Handler sets `self._triggered_externally = True` before calling `async_open/close/stop_cover`
- Those methods check the flag and skip `_async_handle_command` if set
- Flag is cleared after the call completes

This reuses all existing travel calculator logic (startup delays, direction changes, auto-stopping) without duplication.

## Scope

Applies to all input modes (switch, pulse, toggle). Only affects switch-based configurations (not `cover_entity_id`).
