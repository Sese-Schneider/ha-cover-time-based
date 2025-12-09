## 3.0.0

### Features

- **Motor startup delay compensation (`travel_startup_delay`, `tilt_startup_delay`)**: Optional parameters to compensate for motor inertia by delaying position tracking after relay activation, improving position accuracy for short movements
- **Default values (`defaults`)**: Optional section to define default timing parameters for all devices, reducing configuration duplication

### Bug Fixes

- Fixed endpoint delay not properly stopping relay when starting new movement in opposite direction
- Fixed position calculation using stale data after stopping movement during direction change


## X.X.X (TBD)

### Features

- **Synchronized travel and tilt movements**: Travel and tilt now move proportionally on the same motor, accurately simulating real blind mechanism behavior
- **Automatic position constraints**: Tilt automatically resets to correct position at travel endpoints (0% horizontal at fully open, 100% vertical at fully closed)
- **Optional endpoint delay (`travel_delay_at_end`)**: Configurable relay delay at endpoint positions for covers with mechanical endstops, allowing position reset through endstop contact
- **Minimum movement time (`min_movement_time`)**: Optional parameter to prevent position drift by blocking relay activations too brief to physically move the cover
- **Polish translation**: Added Polish language support

### Improvements

- Travel and tilt movements are now time-synchronized and stop simultaneously
- Movements to endpoint positions (0% or 100%) always allowed regardless of minimum movement time constraint
- Delay task properly cancelled when new movements initiated
- Enhanced position accuracy through mechanical constraint enforcement

### Bug Fixes

- Fixed simultaneous travel and tilt operations not properly stopping each other when needed
- Improved mutual exclusion between travel and tilt movements


## 2.3.2 (2025-07-09)

### Bug Fixes

- Bump xknx (@bernardesarthur)


## 2.3.1 (2025-05-01)

### Bug Fixes

- Internal position flipped after restart (@gbasile)


## 2.3.0 (2025-03-27)

### Features

- Add support for existing cover entities

### Bug Fixes

- Internal position state is flipped after `xnkx` update


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