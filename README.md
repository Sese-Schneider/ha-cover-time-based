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
- **Synchronized movement:** Travel and tilt move proportionally on the same motor (realistic blind mechanism simulation).
- **Automatic position constraints:** Tilt automatically resets to correct position at travel endpoints (0% and 100%).
- **Optional endpoint delay:** Configurable relay delay at endpoints for covers with mechanical endstops.

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
        travelling_time_down: 23
        travelling_time_up: 25
        tilting_time_down: 2.3
        tilting_time_up: 2.7
        travel_delay_at_end: 2.0  # Optional: 2 seconds additional relay time at endpoints
```

### Options

| Name                   | Type         | Requirement                                     | Description                                                                     | Default |
|------------------------|--------------|-------------------------------------------------|---------------------------------------------------------------------------------|---------|
| name                   | string       | **Required**                                    | Name of the created entity                                                      |         |
| open_switch_entity_id  | state entity | **Required** or `cover_entity_id`               | Entity ID of the switch for opening the cover                                   |         |
| close_switch_entity_id | state entity | **Required** or `cover_entity_id`               | Entity ID of the switch for closing the cover                                   |         |
| stop_switch_entity_id  | state entity | *Optional* or `cover_entity_id`                 | Entity ID of the switch for stopping the cover                                  | None    |
| cover_entity_id        | state entity | **Required** or `open_\|close_switch_entity_id` | Entity ID of a existing cover entity                                            |         |
| travelling_time_down   | int          | *Optional*                                      | Time it takes in seconds to close the cover                                     | 30      |
| travelling_time_up     | int          | *Optional*                                      | Time it takes in seconds to open the cover                                      | 30      |
| tilting_time_down      | float        | *Optional*                                      | Time it takes in seconds to tilt the cover all the way down                     | None    |
| tilting_time_up        | float        | *Optional*                                      | Time it takes in seconds to tilt the cover all the way up                       | None    |
| travel_delay_at_end    | float        | *Optional*                                      | Additional relay time (seconds) at endpoints (0%/100%) for position reset       | None    |
| is_button              | boolean      | *Optional* (`cover_entity_id` not supported)    | Treats the switches as buttons, only pressing them for 1s                       | False   |

## Advanced Features

### Synchronized Travel and Tilt

When both `tilting_time_down/up` are configured, the integration simulates realistic blind behavior where travel and tilt occur on the same motor:

- **Moving the cover** automatically adjusts tilt proportionally based on movement duration
- **Adjusting tilt** causes proportional travel movement (as would happen with a real motor)
- Movements are time-synchronized and stop simultaneously

**Example:** With `travelling_time=10s` and `tilting_time=5s`:
- Moving travel 50% → tilt changes 100% (twice as fast)
- Moving tilt 50% → travel changes 25% (half as fast)

### Automatic Position Constraints

The integration enforces mechanical constraints at endpoint positions:

- **At 0% (fully open):** Tilt is automatically set to 0% (horizontal)
- **At 100% (fully closed):** Tilt is automatically set to 100% (vertical)

This prevents position drift and ensures consistency after full open/close operations.

### Endpoint Delay (travel_delay_at_end)

Optional feature for covers with **mechanical endstops**. Keeps the relay active for additional time after reaching 0% or 100% position.

**Use cases:**
- Covers with mechanical endstops that need position reset
- Compensating for accumulated timing errors
- Systems where relay delays cause position drift

**How it works:**
- Position in HA updates immediately (no UI delay)
- Relay continues running for configured time
- Motor presses against endstop, resetting position
- Any new movement cancels the delay immediately

**Example:**
```yaml
travel_delay_at_end: 2.0  # 2 seconds additional press at endpoints
```

**Recommended values:** 1.0 - 3.0 seconds

**Not recommended for:**
- Covers without mechanical endstops
- Covers with position encoders
- Systems with perfect time-based positioning


[commits-shield]: https://img.shields.io/github/commit-activity/y/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[commits]: https://github.com/Sese-Schneider/ha-cover-time-based/commits/main
[downloads-shield]: https://img.shields.io/github/downloads/Sese-Schneider/ha-cover-time-based/total.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/maintenance/yes/2025.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[releases]: https://github.com/Sese-Schneider/ha-cover-time-based/releases
