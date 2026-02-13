# Cover time based integration by [@Sese-Schneider](https://www.github.com/Sese-Schneider)

A Home Assistant integration to control your cover based on time.

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sese-Schneider&repository=ha-cover-time-based&category=integration)
[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)

![Project Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]

This integration is based on [davidramosweb/home-assistant-custom-components-cover-time-based](https://github.com/davidramosweb/home-assistant-custom-components-cover-time-based/).

It improves the original integration by adding tilt control and synchronized travel/tilt movements.

### Features:

- **Control the height of your cover based on time**.
- **Control the tilt of your cover based on time**.
- **Synchronized movement:** Travel and tilt move proportionally on the same motor.
- **Optional endpoint delay:** Configurable relay delay at endpoints for covers with mechanical endstops.
- **Minimum movement time:** Prevents position drift from very short relay activations.
- **Motor startup compensation:** Optional delay compensation for motor inertia to improve position accuracy.

_To enable tilt control you need to add the `tilting_time_down` and `tilting_time_up` options to your configuration.yaml._

## Install

### HACS

_This repo is available for install through the HACS._

- Go to HACS → Integrations
- Use the FAB "Explore and download repositories" to search "cover-time-based".

_or_

Click here:

[![](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sese-Schneider&repository=ha-cover-time-based&category=integration)

## Setup

### Example configuration.yaml entry

#### Basic configuration with individual device settings:

```yaml
cover:
  - platform: cover_time_based
    devices:
      room_rolling_shutter:
        name: Room Rolling Shutter
        open_switch_entity_id: switch.wall_switch_right
        close_switch_entity_id: switch.wall_switch_left
        travel_moves_with_tilt: false
        travelling_time_down: 23
        travelling_time_up: 25
        tilting_time_down: 2.3
        tilting_time_up: 2.7
        travel_delay_at_end: 2.0
        min_movement_time: 0.5
        travel_startup_delay: 0.1
        tilt_startup_delay: 0.08
```

#### Configuration with shared defaults:

```yaml
cover:
  - platform: cover_time_based
    # Optional: Default values for all devices
    defaults:
      travelling_time_down: 49.2
      travelling_time_up: 50.7
      tilting_time_down: 1.5
      tilting_time_up: 1.5
      travel_delay_at_end: 1.5
      min_movement_time: 0.5
      travel_startup_delay: 0.1
      tilt_startup_delay: 0.08

    devices:
      # This device uses all defaults
      bedroom_left:
        name: Bedroom Left
        open_switch_entity_id: switch.bedroom_left_open
        close_switch_entity_id: switch.bedroom_left_close

      # This device overrides some defaults
      bedroom_right:
        name: Bedroom Right
        travelling_time_down: 52.0 # Override default
        open_switch_entity_id: switch.bedroom_right_open
        close_switch_entity_id: switch.bedroom_right_close

      # This device explicitly disables startup delay
      kitchen:
        name: Kitchen
        travel_startup_delay: null # Override to disable
        open_switch_entity_id: switch.kitchen_open
        close_switch_entity_id: switch.kitchen_close
```

### Options

| Name                   | Type         | Requirement                                     | Description                                                               | Default |
| ---------------------- | ------------ | ----------------------------------------------- | ------------------------------------------------------------------------- | ------- |
| name                   | string       | **Required**                                    | Name of the created entity                                                |         |
| open_switch_entity_id  | state entity | **Required** or `cover_entity_id`               | Entity ID of the switch for opening the cover                             |         |
| close_switch_entity_id | state entity | **Required** or `cover_entity_id`               | Entity ID of the switch for closing the cover                             |         |
| stop_switch_entity_id  | state entity | _Optional_ or `cover_entity_id`                 | Entity ID of the switch for stopping the cover                            | None    |
| cover_entity_id        | state entity | **Required** or `open_\|close_switch_entity_id` | Entity ID of a existing cover entity                                      |         |
| travel_moves_with_tilt | boolean      | _Optional_                                      | Whether tilt movements also cause proportional travel changes             | False   |
| travelling_time_down   | int          | _Optional_                                      | Time it takes in seconds to close the cover                               | 30      |
| travelling_time_up     | int          | _Optional_                                      | Time it takes in seconds to open the cover                                | 30      |
| tilting_time_down      | float        | _Optional_                                      | Time it takes in seconds to tilt the cover all the way down               | None    |
| tilting_time_up        | float        | _Optional_                                      | Time it takes in seconds to tilt the cover all the way up                 | None    |
| travel_delay_at_end    | float        | _Optional_                                      | Additional relay time (seconds) at endpoints (0%/100%) for position reset | None    |
| min_movement_time      | float        | _Optional_                                      | Minimum movement duration (seconds) - blocks shorter movements            | None    |
| travel_startup_delay   | float        | _Optional_                                      | Motor startup time compensation (seconds) for travel movements            | None    |
| tilt_startup_delay     | float        | _Optional_                                      | Motor startup time compensation (seconds) for tilt movements              | None    |
| input_mode             | string       | _Optional_ (`cover_entity_id` not supported)    | `switch` (latching), `pulse` (momentary+stop), `toggle` (same btn stops)  | switch  |
| is_button              | boolean      | _Deprecated_                                    | Use `input_mode: pulse` instead                                           | False   |

## Advanced Features

### Default Values (defaults)

You can define default values for timing parameters that will be used by all devices unless explicitly overridden. This reduces configuration duplication when you have multiple covers with similar characteristics.

**How it works:**

- Values in `defaults` section apply to all devices
- Device-specific values override defaults
- Explicit `null` in device config overrides defaults (disables feature)
- If neither defaults nor device config specify a value, schema defaults are used

**Priority order:**

1. Device-specific value (highest priority)
2. Defaults value
3. Schema default (lowest priority)

### Synchronized Travel and Tilt

When both `tilting_time_down/up` are configured, the integration simulates realistic blind behavior:

- **Travel movements** always adjust tilt proportionally
- **Tilt movements** affect travel only when `travel_moves_with_tilt: true`
- Movements are time-synchronized and stop simultaneously

**Example:** With `travelling_time=10s` and `tilting_time=5s`, moving travel 50% changes tilt 100%.

### Travel Moves With Tilt (travel_moves_with_tilt)

Controls whether tilt adjustments cause proportional travel movement.

- **`false` (default):** Only travel movements affect tilt. Tilt can be adjusted independently.
- **`true`:** Both travel and tilt movements are synchronized on the same motor.

```yaml
travel_moves_with_tilt: true
```

### Automatic Position Constraints

At endpoint positions, tilt is automatically constrained to prevent drift:

- **At 0% (fully open):** Tilt is set to 0% (horizontal)
- **At 100% (fully closed):** Tilt is set to 100% (vertical)

### Endpoint Delay (travel_delay_at_end)

For covers with mechanical endstops, keeps the relay active for additional time after reaching endpoints to reset position.

```yaml
travel_delay_at_end: 2.0
```

Recommended values: 1.0 - 3.0 seconds

### Minimum Movement Time (min_movement_time)

Prevents position drift by blocking relay activations too brief to physically move the cover. Movements to 0% or 100% are always allowed.

```yaml
min_movement_time: 0.5
```

Recommended values: 0.5 - 1.5 seconds

### Motor Startup Delay (travel_startup_delay, tilt_startup_delay)

Optional feature to compensate for **motor inertia** by delaying position tracking after relay activation. This improves position accuracy, especially for short movements.

**The problem:**

- Motors have startup inertia - after relay turns ON, there's a brief delay before the cover actually starts moving
- This delay (typically 0.05-0.15s) is counted in timing but doesn't move the cover
- For long movements (e.g., 30s), this is negligible (0.3% error)
- For short movements (e.g., 0.5s), this is significant (20-30% error)
- Multiple short movements accumulate drift

**How it works:**

1. Relay turns ON immediately
2. Waits for `startup_delay` (motor is starting up)
3. Only then starts counting position change in Home Assistant
4. Can be cancelled at any time (STOP or direction change)

**Example:**

```yaml
travel_startup_delay: 0.1 # 100ms startup delay for travel
tilt_startup_delay: 0.08 # 80ms startup delay for tilt

# User command: Tilt 1% (normally 0.03s)
# Actual timing: Relay ON for 0.11s total (0.08s startup + 0.03s movement)
# Result: Cover actually moves 1%
```

**Recommended values:** 0.05 - 0.15 seconds

**Important notes:**

- This is a fixed time per relay activation, not a percentage
- Works best when calibrated for your specific motor
- Can be different for travel and tilt if needed
- Compatible with `min_movement_time` and `travel_delay_at_end`

[commits-shield]: https://img.shields.io/github/commit-activity/y/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[commits]: https://github.com/Sese-Schneider/ha-cover-time-based/commits/main
[license-shield]: https://img.shields.io/github/license/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/maintenance/yes/2025.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[releases]: https://github.com/Sese-Schneider/ha-cover-time-based/releases
