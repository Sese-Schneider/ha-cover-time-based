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

- **Control the position of your cover based on time**.
- **External state monitoring:** Detects physical switch presses and keeps the position tracker in sync.
- **Multiple input modes:** Latching switches, momentary pulse buttons, or toggle-style relays.
- **Wrap an existing cover:** Add time-based position tracking to any cover entity.
- **Control the tilt of your cover based on time** with three tilt modes: inline, sequential (closes then tilts), or separate tilt motor.
- **Built-in configuration and calibration:** Calibrate travel times directly from the UI, including finer parameters to compensate for the time it takes the motor to startup.
- **Resyncs position at endpoints:** The motor can be configured to run-on at the 0%/100% endpoints to resync the position tracker with the physical cover.

## Install

### HACS

_This repo is available for install through HACS._

- Go to HACS
- Search for "Cover time based"

_or_

Click here:

[![](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sese-Schneider&repository=ha-cover-time-based&category=integration)

## Setup

### Creating a cover via the UI

1. Go to **Settings → Devices & Services → Helpers**
2. Click **Create Helper → Cover Time Based**
3. Enter a name for your cover

### Setup the configuration card

The configuration card provides a visual interface for all settings and supports built-in calibration to measure timing parameters automatically.

1. Go to **Settings → Dashboards**.
2. Click **Add dashboard → New dashboard from scratch**.
3. Fill in a name and make sure **Add to sidebar** is selected.
4. Click **Create**.
5. Click the new dashboard icon in the Home Assistant side bar.
6. Click the **Edit dashboard** icon in the top right corner.
7. Under **New section** click the **+** icon to add a new card.
8. Search for and select the **Cover time based configuration** card and click **Save**.
9. Click **Done** to stop editing the dashboard.

### Configuration and Calibration Card

The configuration card provides a visual interface for all settings and supports built-in calibration to measure timing parameters automatically.

The configuration card has two tabs: **Device** and **Calibration**. The Device tab must be fully configured before accessing the Calibration tab.

The main items on the **Device** configure how to interface with the
physical cover:

- **Device type**: whether this helper talks to the cover via open/close switches or via an existing cover entity
- **Switch type**: whether the switches are latching, pulsed, or toggled.
- **Tilting**: what type of tilt, if any, is supported.

The **Calibration** tab is used to configure:

- **Position**: sync the position tracker with the physical cover and slat position.
- **Travel**: how long it takes to open and close the cover, and how much time it takes to start the motor.
- **Tilt**: how long it takes to open and close the slats, and how much time it takes to start the motor.

## Device

First configure the **Device type**. A cover-time-based helper can either:

- wrap an existing cover entity to add time-based position tracking, or
- use relay switches to control cover movement, and optionally to
  control tilt movement.

### Wrapped covers

Wrap an existing cover entity to add time-based position tracking. Useful for covers that already have basic open/close/stop functionality but lack position tracking.

Specify the **Cover entity**.

### Switch-based covers

Control a cover using two relay switches (one for open, one for close), with an optional third stop switch.

Specify the **Open switch**, **Close switch**, and optionally the **Stop switch** entities.

### Input Mode for switch-based covers

Three input modes are available to describe how the switch entities for switch-based covers function:

| Mode       | Description                                                                                                                                                            |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Switch** | Latching relays. The direction switch stays ON for the entire movement. Movement stops when the switch is turned OFF                                                   |
| **Pulse**  | Momentary pulse buttons. A brief ON-OFF pulse latches the motor on. Requires a stop button to stop movement, or movement stops when the hardware reaches its endpoint. |
| **Toggle** | Toggle-style relays. A brief ON-OFF pulse latches the motor on. A second pulse on the same direction button stops the motor.                                           |

#### Pulse time

With the **Pulse** and **Toggle** input modes, the **Pulse time** configures how long the switch should send the ON signal before it turns OFF. Defaults to **2s**.

## Tilt Mode

The **Tilt Mode** setting controls how tilt and travel interact:

- **None:** Tilt is disabled. Only position tracking is used.
- **Inline:** Tilt and travel use the same motor. Tilting can happen with the cover in any position. When closing the cover, the closing movement first causes the slats to tilt closed before the cover starts closing. When opening the cover, the opening movement first causes the slats to tilt open before the cover starts opening.
- **Sequential (closes then tilts):** Tilting can only happen in the fully closed position. First the cover closes then the slats tilt closed. When opening, first the slats tilt open then the cover opens.
- **Separate tilt motor (dual_motor):** A separate motor controls the tilt. Requires dedicated tilt open/close/stop switches. Tilt is only allowed when the cover is in a safe position (configurable).

### Tilt Motor

For covers with a dedicated tilt motor, configure:

- **Tilt open/close/stop switches:** The relay switches controlling the tilt motor (unless this is a wrapped cover entity which doesn't require extra switches).
- **Safe tilt position:** The tilt moves to this position before travel starts (default: 100 = fully open).
- **Max tilt allowed position:** Tilt is only allowed when the cover position is at or below this value (e.g., 0 = only when fully closed).

## Calibration

The **Calibration** tab is used to synchronise the position tracker with the position of the physical cover and slats, and to configure the timings that allow this integration to track the physical hardware.

### Current Position

Use the buttons in the blue header bar to move the cover (and slats, if tilting is enabled) into a known position and then change the **Current Position** dropdown from `Unknown` to that position. The position must be specified in order to access the calibration tests further down the page.

### Timing Calibration

Select the attribute that you wish to calibrate. The available attributes depend on the current position of the cover and slats, and which other attributes have already been configured. For instance, in position **Fully open** you can only calibrate **Travel time (close)** and **Minimum movement time**. **Travel startup delay** becomes configurable once **Travel time (open)** or **Travel time (close)** has been configured.

1. Set the **Current position** of the cover and slats.
2. Select the attribute you wish to configure.
3. Read the description of what needs to be measured.
4. Click **Start**.
5. Once the cover or slats reach the position described in the description, click **Finish**. Alternatively, click **Cancel** to abort the calibration.

### Calibration Attributes for Travel

| Option               | Description                                                           | Default |
| -------------------- | --------------------------------------------------------------------- | ------- |
| Travel time (close)  | Time in seconds for the cover to fully close                          |         |
| Travel time (open)   | Time in seconds for the cover to fully open                           |         |
| Travel startup delay | Motor startup compensation for travel (see below)                     | None    |
| Endpoint run-on time | Extra relay time at endpoints (0%/100%) to reset position             | 2.0     |
| Min movement time    | Minimum movement duration - blocks shorter movements to prevent drift | None    |

### Calibration Attributes for Tilt

| Option             | Description                                    | Default |
| ------------------ | ---------------------------------------------- | ------- |
| Tilt time (close)  | Time in seconds to tilt the cover fully closed | None    |
| Tilt time (open)   | Time in seconds to tilt the cover fully open   | None    |
| Tilt startup delay | Motor startup compensation for tilt            | None    |

#### Travel/Tilt startup delay

Compensates for motor inertia by delaying position tracking after relay activation. This improves position accuracy, especially for short movements.

**The problem:** Motors have startup inertia. After the relay turns ON, there's a brief delay before the cover starts moving. For long movements (e.g., 30s) this is negligible, but for short movements (e.g. 0.5s) it can cause 20-30% position error that accumulates over time.

**How it works:**

1. Relay turns ON immediately
2. Waits for the configured startup delay (motor is starting up)
3. Only then starts counting position change
4. Can be cancelled at any time (stop or direction change)

Recommended values: 0.05 - 0.15 seconds. Can be configured separately for travel and tilt.

#### Endpoint Run-on Time

Position tracking is not exact and can drift over time. To reduce drift, the position tracker resyncs itself whenever the cover is sent to the 0% or 100% endpoints. The motor continues running for the number of seconds specified in the **Endpoint Run-on Time** in case the physical cover hasn't quite reached the endpoint. Defaults to 2s.

#### Min movement time

Prevents position drift by blocking relay activations too brief to physically move the cover. Movements to 0% or 100% are always allowed. Recommended values: 0.5 - 1.5 seconds.

## Services

### `cover_time_based.set_known_position`

Manually set the internal position of a cover. Useful for correcting drift.

| Field     | Description                 |
| --------- | --------------------------- |
| entity_id | The cover entity            |
| position  | The position to set (0-100) |

### `cover_time_based.set_known_tilt_position`

Manually set the internal tilt position of a cover.

| Field         | Description                      |
| ------------- | -------------------------------- |
| entity_id     | The cover entity                 |
| tilt_position | The tilt position to set (0-100) |

### `cover_time_based.start_calibration`

Start a calibration test to measure a timing parameter.

| Field     | Description                                                                    |
| --------- | ------------------------------------------------------------------------------ |
| entity_id | The cover entity                                                               |
| attribute | The timing parameter to calibrate                                              |
| timeout   | Safety timeout in seconds - motor auto-stops if stop_calibration is not called |
| direction | Direction to move (`open` or `close`). Auto-detects if not set                 |

### `cover_time_based.stop_calibration`

Stop an active calibration test and save the result.

| Field     | Description                                   |
| --------- | --------------------------------------------- |
| entity_id | The cover entity                              |
| cancel    | If `true`, discard the results without saving |

## YAML configuration (deprecated)

> **Note:** YAML configuration is deprecated and will be removed in a future version. Please use the UI method described above instead. Existing YAML configurations will continue to work, and a deprecation notice will appear in your Home Assistant repairs panel.

<details>
<summary>Show YAML configuration (deprecated)</summary>

### Basic configuration with individual device settings:

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

### YAML options

| Name                   | Type    | Requirement                                     | Description                                                             | Default |
| ---------------------- | ------- | ----------------------------------------------- | ----------------------------------------------------------------------- | ------- |
| name                   | string  | **Required**                                    | Name of the created entity                                              |         |
| open_switch_entity_id  | entity  | **Required** or `cover_entity_id`               | Entity ID of the switch for opening the cover                           |         |
| close_switch_entity_id | entity  | **Required** or `cover_entity_id`               | Entity ID of the switch for closing the cover                           |         |
| stop_switch_entity_id  | entity  | _Optional_                                      | Entity ID of the switch for stopping the cover                          | None    |
| cover_entity_id        | entity  | **Required** or `open_\|close_switch_entity_id` | Entity ID of an existing cover entity                                   |         |
| is_button              | boolean | _Optional_                                      | Set to `true` for momentary pulse buttons (same as `input_mode: pulse`) | false   |
| travelling_time_down   | float   | _Optional_                                      | Time in seconds to close the cover                                      | 30      |
| travelling_time_up     | float   | _Optional_                                      | Time in seconds to open the cover                                       | 30      |
| tilting_time_down      | float   | _Optional_                                      | Time in seconds to tilt the cover fully closed                          | None    |
| tilting_time_up        | float   | _Optional_                                      | Time in seconds to tilt the cover fully open                            | None    |
| travel_moves_with_tilt | boolean | _Optional_                                      | Whether tilt movements also cause proportional travel changes           | false   |
| travel_delay_at_end    | float   | _Optional_                                      | Additional relay time (seconds) at endpoints for position reset         | None    |
| min_movement_time      | float   | _Optional_                                      | Minimum movement duration (seconds) - blocks shorter movements          | None    |
| travel_startup_delay   | float   | _Optional_                                      | Motor startup time compensation (seconds) for travel movements          | None    |
| tilt_startup_delay     | float   | _Optional_                                      | Motor startup time compensation (seconds) for tilt movements            | None    |
| pulse_time             | float   | _Optional_                                      | Duration in seconds for button press in pulse mode                      | 1.0     |

</details>

[commits-shield]: https://img.shields.io/github/commit-activity/y/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[commits]: https://github.com/Sese-Schneider/ha-cover-time-based/commits/main
[license-shield]: https://img.shields.io/github/license/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/maintenance/yes/2026.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[releases]: https://github.com/Sese-Schneider/ha-cover-time-based/releases
