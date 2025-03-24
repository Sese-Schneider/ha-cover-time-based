## 2.2.0 (2025-03-24)

### Features

- Add support for button based cover controls (#17)

### Bug Fixes

- current_position is None comparison exceptions (#18)
- Update `xknx` to latest version
- Update service schema for 2025.09

## 2.1.1 (2024-04-17)

### Bug Fixes

- Fix `stop_switch_entity_id` not being present causing the integration to crash


## 2.1.0 (2024-04-11)

### Features

- Add optional `stop_switch_entity_id` for stopping the cover

### Bug Fixes

- Fix an issue where the integration would not load when the tilting entities were not present
- Fix check for tilt support when stopping (#7)


## 2.0.1 (2024-01-05)

### Bug Fixes

- Fix `hacs.json` & `manifest.json` for HACS support


## 2.0.0 (2023-10-06)

### Features

- Add tilt support
- HACS support

## 1.0.0 (2023-10-02)

### Features

- Initial Release based on [davidramosweb/home-assistant-custom-components-cover-time-based](https://github.com/davidramosweb/home-assistant-custom-components-cover-time-based)
