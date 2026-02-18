# Manual Position Reset for Calibration

## Summary

Add a "Current Position" section above the calibration form that lets the user declare the cover's endpoint position before running calibration tests. This replaces the direction dropdown (removed earlier) with implicit direction inference, removes the timeout field (hardcoded to 300s), and gates calibration behind a known position.

## UI Layout

### Current Position section (new)

Placed above the Timing Calibration section, separated by a divider line.

- Heading: "Current Position"
- Helper text: "Move cover to a known endpoint, then set position."
- Dropdown: `Unknown` (default) / `Fully open` / `Fully closed`
- Reset button: right-aligned, same row as dropdown
- Reset disabled when Unknown is selected

### Timing Calibration section (simplified)

- Attribute dropdown (unchanged, but with disabled options based on position)
- Start button (right-aligned, same row)
- Timeout field removed — hardcoded to 300s
- When Start is disabled, show hint: "Set position to start calibration"

## State Transitions

| Event                    | Position state | Effect                                             |
|--------------------------|---------------|----------------------------------------------------|
| Page load / entity switch | Unknown       | All attributes disabled, Start disabled            |
| Reset with "Fully open"  | Open          | Disable travel_time_open, tilt_time_open           |
| Reset with "Fully closed" | Closed       | Disable travel_time_close, tilt_time_close         |
| Start calibration         | → Unknown    | Calibration active UI shown                        |
| Finish calibration        | Unknown      | All disabled until next Reset                      |
| Cancel calibration        | Unknown      | All disabled until next Reset                      |

## Direction Inference

Direction is derived from position — no user input needed:

- Fully open → direction = "close"
- Fully closed → direction = "open"

This replaces the removed Direction dropdown.

## Reset Action

When user clicks Reset with open or closed selected:

1. Call `set_known_position` service with position 100 (open) or 0 (closed)
2. Call `set_known_tilt_position` service with position 100 (open) or 0 (closed)
3. Update frontend `_knownPosition` state

## Attribute Filtering

Unavailable attributes shown as disabled (greyed out) in the dropdown, not hidden:

- Position Unknown → all attributes disabled
- Fully open → `travel_time_open` and `tilt_time_open` disabled (already at open endpoint)
- Fully closed → `travel_time_close` and `tilt_time_close` disabled (already at closed endpoint)

## Backend Changes

- No new services or WebSocket commands
- Default timeout changes from 120 to 300 in the `_onStartCalibration` call

## Approach

Pure frontend state management. The `_knownPosition` property tracks the position in JS only. The Reset button's backend effect is calling existing `set_known_position` / `set_known_tilt_position` services to sync the internal travel calculator.
