# Cover time based integration by [@Sese-Schneider](https://www.github.com/Sese-Schneider)
A Home Assistant integration to control your cover based on time.

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sese-Schneider&repository=ha-cover-time-based&category=integration)
[![GitHub Release][releases-shield]][releases]
![GitHub Downloads][downloads-shield]

[![License][license-shield]](LICENSE)
![Project Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]

This integration is based on [davidramosweb/home-assistant-custom-components-cover-time-based](https://github.com/davidramosweb/home-assistant-custom-components-cover-time-based/).

It improves the original integration by adding tilt control and synchronized travel/tilt movements.

**Features:**

- Control the height of your cover based on time.
- Control the tilt of your cover based on time.
- **Synchronized movement:** Travel and tilt move proportionally on the same motor.
- **Optional endpoint delay:** Configurable relay delay at endpoints for covers with mechanical endstops.
- **Minimum movement time:** Prevents position drift from very short relay activations.

*To enable tilt control you need to add the `tilting_time_down` and `tilting_time_up` options to your configuration.yaml.*

## Install

### HACS

*This repo is available for install through the HACS.*

* Go to HACS → Integrations
* Use the FAB "Explore and download repositories" to search "cover-time-based".

_or_

Click here:

[![](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sese-Schneider&repository=ha-cover-time-based&category=integration)


## Setup

### Example configuration.yaml entry

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
```

### Options

| Name                     | Type         | Requirement                                     | Description                                                                     | Default |
|--------------------------|--------------|-------------------------------------------------|---------------------------------------------------------------------------------|---------|
| name                     | string       | **Required**                                    | Name of the created entity                                                      |         |
| open_switch_entity_id    | state entity | **Required** or `cover_entity_id`               | Entity ID of the switch for opening the cover                                   |         |
| close_switch_entity_id   | state entity | **Required** or `cover_entity_id`               | Entity ID of the switch for closing the cover                                   |         |
| stop_switch_entity_id    | state entity | *Optional* or `cover_entity_id`                 | Entity ID of the switch for stopping the cover                                  | None    |
| cover_entity_id          | state entity | **Required** or `open_\|close_switch_entity_id` | Entity ID of a existing cover entity                                            |         |
| travel_moves_with_tilt   | boolean      | *Optional*                                      | Whether tilt movements also cause proportional travel changes                   | False   |
| travelling_time_down     | int          | *Optional*                                      | Time it takes in seconds to close the cover                                     | 30      |
| travelling_time_up       | int          | *Optional*                                      | Time it takes in seconds to open the cover                                      | 30      |
| tilting_time_down        | float        | *Optional*                                      | Time it takes in seconds to tilt the cover all the way down                     | None    |
| tilting_time_up          | float        | *Optional*                                      | Time it takes in seconds to tilt the cover all the way up                       | None    |
| travel_delay_at_end      | float        | *Optional*                                      | Additional relay time (seconds) at endpoints (0%/100%) for position reset       | None    |
| min_movement_time        | float        | *Optional*                                      | Minimum movement duration (seconds) - blocks shorter movements                  | None    |
| is_button                | boolean      | *Optional* (`cover_entity_id` not supported)    | Treats the switches as buttons, only pressing them for 1s                       | False   |

## Advanced Features

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


[commits-shield]: https://img.shields.io/github/commit-activity/y/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[commits]: https://github.com/Sese-Schneider/ha-cover-time-based/commits/main
[downloads-shield]: https://img.shields.io/github/downloads/Sese-Schneider/ha-cover-time-based/total.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/maintenance/yes/2025.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[releases]: https://github.com/Sese-Schneider/ha-cover-time-based/releases

