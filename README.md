# Cover time based integration by [@Sese-Schneider](https://www.github.com/Sese-Schneider)

A Home Assistant integration to control your cover based on time.

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sese-Schneider&repository=ha-cover-time-based&category=integration)
[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)

![Project Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]

This integration is based on [davidramosweb/home-assistant-custom-components-cover-time-based](https://github.com/davidramosweb/home-assistant-custom-components-cover-time-based/).

It improves the original integration by adding tilt control, synchronized travel/tilt movements, and a visual configuration card.

### Features:

- **Control the height of your cover based on time**.
- **Control the tilt of your cover based on time**.
- **Synchronized movement:** Travel and tilt move proportionally on the same motor.
- **Multiple input modes:** Latching switches, momentary pulse buttons, or toggle-style relays.
- **Wrap an existing cover:** Add time-based position tracking to any cover entity.
- **Built-in calibration:** Measure timing parameters directly from the UI.
- **Optional endpoint delay:** Configurable relay delay at endpoints for covers with mechanical endstops.
- **Minimum movement time:** Prevents position drift from very short relay activations.
- **Motor startup compensation:** Optional delay compensation for motor inertia to improve position accuracy for travel and tilt.

## Install

### HACS

_This repo is available for install through the HACS._

- Go to HACS → Integrations
- Use the FAB "Explore and download repositories" to search "cover-time-based".

_or_

Click here:

[![](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sese-Schneider&repository=ha-cover-time-based&category=integration)

## Setup

### Creating a cover via the UI

1. Go to **Settings → Devices & Services → Helpers**
2. Click **Create Helper → Cover Time Based**
3. Enter a name for your cover
4. Add the **Cover Time Based** card to a Lovelace dashboard
5. Use the card to configure and calibrate all settings: device type, input entities, timing, tilt, and more

The configuration card provides a visual interface for all settings and supports built-in calibration to measure timing parameters automatically.

### YAML configuration (deprecated)

> **Note:** YAML configuration is deprecated and will be removed in a future version. Please use the UI method described above instead. Existing YAML configurations will continue to work, and a deprecation notice will appear in your Home Assistant repairs panel.

<details>
<summary>Show YAML configuration (deprecated)</summary>

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


#### YAML options

| Name                   | Type    | Requirement                                     | Description                                                               | Default |
| ---------------------- | ------- | ----------------------------------------------- | ------------------------------------------------------------------------- | ------- |
| name                   | string  | **Required**                                    | Name of the created entity                                                |         |
| open_switch_entity_id  | entity  | **Required** or `cover_entity_id`               | Entity ID of the switch for opening the cover                             |         |
| close_switch_entity_id | entity  | **Required** or `cover_entity_id`               | Entity ID of the switch for closing the cover                             |         |
| stop_switch_entity_id  | entity  | _Optional_                                      | Entity ID of the switch for stopping the cover                            | None    |
| cover_entity_id        | entity  | **Required** or `open_\|close_switch_entity_id` | Entity ID of an existing cover entity                                     |         |
| is_button              | boolean | _Optional_                                      | Set to `true` for momentary pulse buttons (same as `input_mode: pulse`)   | false   |
| travelling_time_down   | float   | _Optional_                                      | Time in seconds to close the cover                                        | 30      |
| travelling_time_up     | float   | _Optional_                                      | Time in seconds to open the cover                                         | 30      |
| tilting_time_down      | float   | _Optional_                                      | Time in seconds to tilt the cover fully closed                            | None    |
| tilting_time_up         | float   | _Optional_                                      | Time in seconds to tilt the cover fully open                              | None    |
| travel_moves_with_tilt | boolean | _Optional_                                      | Whether tilt movements also cause proportional travel changes             | false   |
| travel_delay_at_end    | float   | _Optional_                                      | Additional relay time (seconds) at endpoints for position reset           | None    |
| min_movement_time      | float   | _Optional_                                      | Minimum movement duration (seconds) - blocks shorter movements            | None    |
| travel_startup_delay   | float   | _Optional_                                      | Motor startup time compensation (seconds) for travel movements            | None    |
| tilt_startup_delay     | float   | _Optional_                                      | Motor startup time compensation (seconds) for tilt movements              | None    |
| pulse_time             | float   | _Optional_                                      | Duration in seconds for button press in pulse mode                        | 1.0     |

</details>

## Device types

### Switch-based covers

Control a cover using two relay switches (one for open, one for close), with an optional stop switch.

Three input modes are available:

| Mode       | Description                                                                                    |
| ---------- | ---------------------------------------------------------------------------------------------- |
| **Switch** | Latching relays. The direction switch stays ON for the entire movement. Default mode.           |
| **Pulse**  | Momentary pulse buttons. The switch is pulsed ON briefly, then turned OFF. The motor controller latches internally. |
| **Toggle** | Toggle-style relays. A second pulse on the same direction button stops the motor.               |

### Wrapped covers

Wrap an existing cover entity to add time-based position tracking. Useful for covers that already have basic open/close/stop functionality but lack position tracking.

## Configuration options

All settings are available through the configuration card. Here is the full reference:

### Timing

| Option                 | Description                                                                | Default |
| ---------------------- | -------------------------------------------------------------------------- | ------- |
| Travel time close      | Time in seconds for the cover to fully close                               |         |
| Travel time open       | Time in seconds for the cover to fully open                                |         |
| Endpoint run-on time   | Extra relay time at endpoints (0%/100%) to reset position                  | 2.0     |
| Min movement time      | Minimum movement duration - blocks shorter movements to prevent drift      | None    |
| Travel startup delay   | Motor startup compensation for travel (see below)                          | None    |

### Tilt

| Option               | Description                                                                        | Default |
| -------------------- | ---------------------------------------------------------------------------------- | ------- |
| Tilt mode            | `none` (no tilt), `before_after` (independent tilt), or `during` (tilt with travel) | none    |
| Tilt time close      | Time in seconds to tilt the cover fully closed                                      | None    |
| Tilt time open       | Time in seconds to tilt the cover fully open                                        | None    |
| Tilt startup delay   | Motor startup compensation for tilt                                                 | None    |

### Pulse/Toggle mode

| Option     | Description                                          | Default |
| ---------- | ---------------------------------------------------- | ------- |
| Pulse time | Duration in seconds for the momentary button pulse   | 1.0     |

## Advanced features

### Tilt modes

The **tilt mode** setting controls how tilt and travel interact:

- **None:** Tilt is disabled. Only position tracking is used.
- **Before/After:** Tilt is independent of travel. You can adjust tilt without affecting position, and travel commands adjust tilt proportionally but tilt commands do not move travel.
- **During:** Tilt and travel are synchronized on the same motor. Both tilt and travel movements affect each other proportionally.

### Synchronized travel and tilt

When tilt is enabled, travel movements always adjust tilt proportionally. With tilt mode set to **during**, tilt movements also cause proportional travel changes.

**Example:** With `travel_time=10s` and `tilt_time=5s`, moving travel 50% changes tilt 100%.

### Automatic position constraints

At endpoint positions, tilt is automatically constrained to prevent drift:

- **At 0% (fully open):** Tilt is set to 0% (horizontal)
- **At 100% (fully closed):** Tilt is set to 100% (vertical)

### Endpoint run-on time

For covers with mechanical endstops, keeps the relay active for additional time after reaching endpoints to reset position. Recommended values: 1.0 - 3.0 seconds.

### Minimum movement time

Prevents position drift by blocking relay activations too brief to physically move the cover. Movements to 0% or 100% are always allowed. Recommended values: 0.5 - 1.5 seconds.

### Motor startup delay

Compensates for motor inertia by delaying position tracking after relay activation. This improves position accuracy, especially for short movements.

**The problem:** Motors have startup inertia. After the relay turns ON, there's a brief delay before the cover starts moving. For long movements (e.g., 30s) this is negligible, but for short movements (e.g., 0.5s) it can cause 20-30% position error that accumulates over time.

**How it works:**

1. Relay turns ON immediately
2. Waits for the configured startup delay (motor is starting up)
3. Only then starts counting position change
4. Can be cancelled at any time (stop or direction change)

Recommended values: 0.05 - 0.15 seconds. Can be configured separately for travel and tilt.

### Calibration

The configuration card includes built-in calibration to measure timing parameters automatically. During calibration, the cover moves in a specified direction and you stop it when it reaches the desired endpoint. The measured time is saved directly to the configuration.

Calibratable parameters: `travel_time_close`, `travel_time_open`, `tilt_time_close`, `tilt_time_open`, `travel_startup_delay`, `tilt_startup_delay`, `min_movement_time`.

## Services

### `cover_time_based.set_known_position`

Manually set the internal position of a cover. Useful for correcting drift.

| Field     | Description                                    |
| --------- | ---------------------------------------------- |
| entity_id | The cover entity                               |
| position  | The position to set (0-100)                    |

### `cover_time_based.set_known_tilt_position`

Manually set the internal tilt position of a cover.

| Field         | Description                                    |
| ------------- | ---------------------------------------------- |
| entity_id     | The cover entity                               |
| tilt_position | The tilt position to set (0-100)               |

### `cover_time_based.start_calibration`

Start a calibration test to measure a timing parameter.

| Field     | Description                                                              |
| --------- | ------------------------------------------------------------------------ |
| entity_id | The cover entity                                                         |
| attribute | The timing parameter to calibrate                                        |
| timeout   | Safety timeout in seconds - motor auto-stops if stop_calibration is not called |
| direction | Direction to move (`open` or `close`). Auto-detects if not set           |

### `cover_time_based.stop_calibration`

Stop an active calibration test and save the result.

| Field     | Description                                        |
| --------- | -------------------------------------------------- |
| entity_id | The cover entity                                   |
| cancel    | If `true`, discard the results without saving      |

[commits-shield]: https://img.shields.io/github/commit-activity/y/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[commits]: https://github.com/Sese-Schneider/ha-cover-time-based/commits/main
[license-shield]: https://img.shields.io/github/license/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/maintenance/yes/2025.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[releases]: https://github.com/Sese-Schneider/ha-cover-time-based/releases
