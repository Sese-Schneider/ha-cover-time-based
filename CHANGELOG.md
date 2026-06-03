## 4.2.0 (2026-06-02)

### Features

- **Tilt support for wrapped covers without native tilt** ([#85](https://github.com/Sese-Schneider/ha-cover-time-based/issues/85)): the **Inline** and **Sequential** tilt modes are now available when wrapping an existing cover, even if that cover only exposes open/close/stop. These modes drive the wrapped cover's normal open/close commands, so they work on any cover — previously the tilt options were hidden unless the wrapped cover reported native tilt support. The **Separate tilt motor** mode still requires native tilt support (it delegates the tilt commands to the wrapped entity), so it remains hidden until the selected cover advertises it.
- **Ignore reported position (wrapped covers)**: a new option to track position purely by time and ignore the `current_position` the wrapped cover reports. Enable it for covers that report an unreliable position (the fully-closed endpoint is still trusted).
- **Detect unavailable relays / targets** ([#89](https://github.com/Sese-Schneider/ha-cover-time-based/issues/89)): the cover now reports as **unavailable** whenever any of its underlying target entities (the switches, buttons, scripts, or wrapped cover that drive it) is unavailable — for example an MQTT relay going offline. Commands that would *start* movement in a direction whose target is unavailable are rejected instead of silently running the time-based simulation and drifting the reported position. Stopping is always allowed, so a cover can still be halted even while a target is offline.

### Fixes

- A wrapped cover configured with **Separate tilt motor** but whose underlying entity doesn't support tilt (e.g. a stored or hand-edited config, or a cover that dropped tilt support) no longer fires `*_cover_tilt` services at it; the unsupported command is skipped and logged instead.
- Selecting the separate-tilt-motor mode is no longer reset when the chosen wrapped cover is merely unavailable — the tilt config is only cleared once the cover is confirmed available without tilt support.

## 4.1.0 (2026-05-30)

### Features

- **Use scripts as open/close/stop switches in Pulse mode** ([#82](https://github.com/Sese-Schneider/ha-cover-time-based/issues/82)): the open, close, and stop targets (and the dual-motor tilt targets) can now be `script` entities as well as `switch` entities when the control mode is **Pulse** — handy for covers driven by IR remotes, where each script fires an open/close/stop command. Switch and Toggle modes still require `switch` entities, since they rely on a held on-state a script can't provide. Note that a script still running when the configured **Pulse time** elapses will be stopped.

## 4.0.0 (2026-05-23)

If you're coming from v2.3.2, this is essentially a new integration.

Cover Time Based controls any motor-driven cover from Home Assistant, even when the cover hardware itself can't report its position. It tracks where the cover is by timing how long the motor has been running — and v4 makes that a lot more capable, and a lot easier to live with.

What you get:

- **Configure everything from a dashboard card.** No more YAML. Add a cover under **Settings → Devices & Services → Helpers**, then tune every setting from a built-in card on your dashboard.
- **Calibrate at the click of a button.** Start the motor, let it run, hit stop — the card figures out your travel and tilt times for you.
- **Works with whatever hardware you have.** Latching relays, momentary push-buttons with a separate stop switch, single-button "toggle" controllers, or any existing cover entity you'd like to add position tracking to.
- **Real tilt support.** Venetian blinds, conventional shutters, inverted shutters, and covers with a separate tilt motor — pick the mode that matches your hardware.
- **Stays in sync with physical buttons.** Wall switches and automations driving the motor outside Home Assistant don't throw the position tracker off any more.
- **Survives restarts.** Positions are saved properly and reloaded — even after unexpected shutdowns.
- **Lots of fine-tuning options** for awkward motors: startup delays, minimum movement times, endpoint resync, and more.
- **Translated** into English, Portuguese, and Polish.

### Upgrading from v2.3.2

Your existing YAML configuration still works with a deprecation warning. When you have a moment, recreate your covers via the helper flow so you can manage them through the UI from then on.

This release also includes a long list of smaller fixes, especially around wrapped covers, sequential tilt strategies, and toggle-mode button handling.

## 3.0.0 (2025-12-10)

### Features

- **Synchronized travel and tilt movements**: Travel and tilt now move proportionally on the same motor, accurately simulating real blind mechanism behavior
- **Automatic position constraints**: Tilt automatically resets to correct position at travel endpoints (0% horizontal at fully open, 100% vertical at fully closed)
- **Optional endpoint delay (`travel_delay_at_end`)**: Configurable relay delay at endpoint positions for covers with mechanical endstops, allowing position reset through endstop contact
- **Minimum movement time (`min_movement_time`)**: Optional parameter to prevent position drift by blocking relay activations too brief to physically move the cover
- **Polish translation**: Added Polish language support
- **Motor startup delay compensation (`travel_startup_delay`, `tilt_startup_delay`)**: Optional parameters to compensate for motor inertia by delaying position tracking after relay activation, improving position accuracy for short movements
- **Default values (`defaults`)**: Optional section to define default timing parameters for all devices, reducing configuration duplication

### Improvements

- Travel and tilt movements are now time-synchronized and stop simultaneously
- Movements to endpoint positions (0% or 100%) always allowed regardless of minimum movement time constraint
- Delay task properly cancelled when new movements initiated
- Enhanced position accuracy through mechanical constraint enforcement

### Bug Fixes

- Fixed simultaneous travel and tilt operations not properly stopping each other when needed
- Improved mutual exclusion between travel and tilt movements
- Fixed endpoint delay not properly stopping relay when starting new movement in opposite direction
- Fixed position calculation using stale data after stopping movement during direction change

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
