# Input Mode Subclasses Design

## Goal

Refactor `CoverTimeBased` into subclasses split by device type (switch vs cover entity) and input mode (switch/pulse/toggle) for both code clarity and extensibility.

## Class Hierarchy

```
CoverTimeBased (abstract base)
├── WrappedCoverTimeBased (cover entity delegation)
└── SwitchCoverTimeBased (abstract, owns switch entity IDs)
    ├── SwitchModeCover (latching relays)
    ├── PulseModeCover (momentary pulse)
    └── ToggleModeCover (same button stops)
```

- `CoverTimeBased`: Position/tilt tracking, timing, easing, startup delays. Defines abstract `_send_open()`, `_send_close()`, `_send_stop()`.
- `WrappedCoverTimeBased`: Delegates open/close/stop to an underlying cover entity.
- `SwitchCoverTimeBased`: Holds open/close/stop switch entity IDs. Still abstract — relay control differs per input mode.
- `SwitchModeCover`: Latching relays — open turns on open relay, off close relay; stop turns both off.
- `PulseModeCover`: Momentary pulse — pulses the appropriate switch for `pulse_time` seconds.
- `ToggleModeCover`: Same button starts and stops. Overrides `async_open_cover`/`async_close_cover` so "same direction while moving = stop".

## Base Class Behavior

- **Stop before direction change** moves to the base class for ALL modes, not just toggle. If the cover is opening and you call close (or vice versa), it stops first.
- **Same direction = stop** stays toggle-only, implemented as an override in `ToggleModeCover`.
- Base class `async_stop_cover` simplifies — the toggle-specific guard logic moves to the subclass.

## File Layout

```
custom_components/cover_time_based/
├── cover.py              → async_setup_entry, async_setup_platform, factory
├── cover_base.py         → CoverTimeBased (abstract base)
├── cover_wrapped.py      → WrappedCoverTimeBased
├── cover_switch.py       → SwitchCoverTimeBased (abstract mid-level)
├── cover_switch_mode.py  → SwitchModeCover
├── cover_pulse_mode.py   → PulseModeCover
├── cover_toggle_mode.py  → ToggleModeCover
```

## Factory Function

`cover.py` contains the factory that picks the right subclass based on config:

```python
def _create_cover(options: dict, hass: HomeAssistant, ...) -> CoverTimeBased:
    device_type = options.get(CONF_DEVICE_TYPE, DEVICE_TYPE_SWITCH)

    if device_type == DEVICE_TYPE_COVER:
        return WrappedCoverTimeBased(...)

    input_mode = options.get(CONF_INPUT_MODE, INPUT_MODE_SWITCH)
    if input_mode == INPUT_MODE_PULSE:
        return PulseModeCover(...)
    elif input_mode == INPUT_MODE_TOGGLE:
        return ToggleModeCover(...)
    else:
        return SwitchModeCover(...)
```

Both `async_setup_entry` and `async_setup_platform` (YAML) use this factory. The factory accepts an options dict directly — `async_setup_entry` passes `entry.options`, YAML builds the dict manually.

## YAML Backward Compatibility

YAML is already deprecated. The YAML path maps its config keys into the same options dict format and calls the same factory. No new features added to YAML. Since YAML is always switch-based, it maps `device_type` to `DEVICE_TYPE_SWITCH` and reads `input_mode` from config.

## Testing Approach

Each subclass gets its own test file:

```
tests/
├── test_cover_base.py         → shared behavior (stop-before-direction-change, position tracking)
├── test_cover_wrapped.py      → delegation to underlying cover entity
├── test_cover_switch_mode.py  → latching relay on/off
├── test_cover_pulse_mode.py   → momentary pulse timing
├── test_cover_toggle_mode.py  → same-direction-stops, stop-before-reverse
```

Existing tests run first against the new code to confirm no behavior change, then subclass-specific tests are added.
