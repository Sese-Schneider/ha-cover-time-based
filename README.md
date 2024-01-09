# Cover time based integration by [@Sese-Schneider](https://www.github.com/Sese-Schneider)
A Home Assistant integration to control your cover based on time.

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sese-Schneider&repository=ha-cover-time-based&category=integration)
[![GitHub Release][releases-shield]][releases]
![GitHub Downloads][downloads-shield]

[![License][license-shield]](LICENSE)
![Project Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]

This integration is based on [davidramosweb/home-assistant-custom-components-cover-time-based](https://github.com/davidramosweb/home-assistant-custom-components-cover-time-based/).

It improves the original integration by adding tilt control.

**Features:**

- Control the height of your cover based on time.
- Control the tilt of your cover based on time.

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

```
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
```

### Options

| Name                   | Type         | Requirement  | Description                                                 | Default |
| ---------------------- | ------------ | ------------ | ----------------------------------------------------------- | ------- |
| name                   | string       | **Required** | Name of the created entity                                  |         |
| open_switch_entity_id  | state entity | **Required** | Entity ID of the switch for opening the cover               |         |
| close_switch_entity_id | state entity | **Required** | Entity ID of the switch for closing the cover               |         |
| travelling_time_down   | int          | *Optional*   | Time it takes in seconds to close the cover                 | 30      |
| travelling_time_up     | int          | *Optional*   | Time it takes in seconds to open the cover                  | 30      |
| tilting_time_down      | float        | *Optional*   | Time it takes in seconds to tilt the cover all the way down | None    |
| tilting_time_up        | float        | *Optional*   | Time it takes in seconds to tilt the cover all the way up   | None    |


[commits-shield]: https://img.shields.io/github/commit-activity/y/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[commits]: https://github.com/Sese-Schneider/ha-cover-time-based/commits/master
[downloads-shield]: https://img.shields.io/github/downloads/Sese-Schneider/ha-cover-time-based/total.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/maintenance/yes/2024.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[releases]: https://github.com/Sese-Schneider/ha-cover-time-based/releases
