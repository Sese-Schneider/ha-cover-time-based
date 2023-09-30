# Cover time based integration by [@Sese-Schneider](https://www.github.com/Sese-Schneider)

A Home Assistant integration to control your cover based on time.
This integration is based on https://github.com/davidramosweb/home-assistant-custom-components-cover-time-based


[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sese-Schneider&repository=ha-cover-time-based&category=integration)
[![GitHub Release][releases-shield]][releases]
![GitHub Downloads][downloads-shield]

[![License][license-shield]](LICENSE)
![Project Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]

**Features:**

- Control the height of your cover based on time.
- control the tilt of your cover based on time.

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
	   travelling_time_down: 23
	   travelling_time_up: 25
	   open_switch_entity_id: switch.wall_switch_right
	   close_switch_entity_id: switch.wall_switch_left
	   aliases:
	    - room_rolling_shutter
```

[commits-shield]: https://img.shields.io/github/commit-activity/y/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[commits]: https://github.com/Sese-Schneider/ha-cover-time-based/commits/master
[downloads-shield]: https://img.shields.io/github/downloads/Sese-Schneider/ha-cover-time-based/total.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/maintenance/yes/2023.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/Sese-Schneider/ha-cover-time-based.svg?style=for-the-badge
[releases]: https://github.com/Sese-Schneider/ha-cover-time-based/releases
