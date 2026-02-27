# feat/ui-sync-rewrite Branch Summary

## Overview

The `feat/ui-sync-rewrite` branch is a major rewrite of the `cover_time_based` integration. The main changes are:

- **UI configuration** — config flow with subentries replaces YAML-only setup, plus a custom Lovelace card for live configuration and calibration
- **Calibration system** — services to measure travel times, motor overhead, and minimum movement time by physically testing covers
- **Tilt strategies** — pluggable strategy pattern supporting sequential, inline, proportional, and dual-motor tilt mechanisms
- **Architecture refactor** — monolithic cover class split into a base class + input-mode subclasses (switch/pulse/toggle/wrapped), with a local travel calculator replacing the xknx dependency
- **State monitoring** — detects external switch changes (physical buttons, apps) and syncs the travel calculator

## Architecture Changes

### Class Hierarchy Refactor

The monolithic `CoverTimeBased` class (~1,400 lines in `cover.py`) was decomposed into a base class + mode-specific subclasses:

```
CoverTimeBased (abstract base, cover_base.py — 1,788 lines)
├── WrappedCoverTimeBased (cover_wrapped.py — 78 lines)
│     Delegates open/close/stop to an underlying cover entity
└── SwitchCoverTimeBased (abstract mid-level, cover_switch.py — 55 lines)
      Holds switch entity IDs, still abstract
    ├── SwitchModeCover (cover_switch_mode.py — 152 lines)
    │     Latching relays (on/off stay in position)
    ├── PulseModeCover (cover_pulse_mode.py — 113 lines)
    │     Momentary pulse with separate stop
    └── ToggleModeCover (cover_toggle_mode.py — 257 lines)
          Same button starts and stops movement
```

Key design decisions:
- Abstract `_send_open()` / `_send_close()` / `_send_stop()` replace the monolithic `_async_handle_command()`
- "Stop before direction change" moved to the base class (all modes)
- "Same direction = stop" stays toggle-only as an override in `ToggleModeCover`
- Factory function in `cover.py` picks the right subclass based on config
- Both UI config entries and YAML use the same factory path

### Local Travel Calculator

The external `xknx` dependency for `TravelCalculator` was replaced with a local implementation (`travel_calculator.py` — 199 lines), removing the only third-party runtime dependency.

### Tilt Strategy System

Tilt mode logic was extracted from `cover_base.py` into a Strategy pattern (`tilt_strategies/` package — 5 files, 322 lines):

```
tilt_strategies/
├── __init__.py      — package exports
├── base.py          — TiltStrategy ABC + MovementStep dataclasses (TiltTo, TravelTo)
├── sequential.py    — "Closes then tilts" (standard venetian blinds)
├── inline.py        — "Tilt embedded in travel" (roller shutters)
└── dual_motor.py    — "Separate tilt motor" (independent tilt switch entities)
```

Strategies return `list[MovementStep]` plans. The cover entity executes steps sequentially, grouping consecutive same-motor steps. Each strategy declares `uses_tilt_motor`, `can_calibrate_tilt`, and `restores_tilt` properties.

A planning helpers module (`tilt_strategies/planning.py`) was later extracted to deduplicate shared tilt planning logic.

Proportional tilt (previously `"during"`) was renamed and retained in the base class since it's just position-coupled rather than a separate strategy.

## New Features

### UI Configuration (Config Flow + Subentries)

- `__init__.py` (58 lines) — integration setup, entry forwarding, frontend/WS registration
- `config_flow.py` (40 lines) — ConfigFlow, OptionsFlow, SubentryFlow for adding/reconfiguring covers via HA UI
- YAML backward compatibility fully retained

### Calibration System

- `calibration.py` (43 lines) — `CalibrationState` dataclass, constants, `get_calibratable_attributes()` filtered by tilt mode
- Three calibration test types:
  - **Simple timing** — user starts cover, clicks stop, elapsed time saved
  - **Motor overhead** — automated 1/10th stepped test to measure startup/stop loss
  - **Minimum movement time** — incremental pulses until movement detected
- `start_calibration` / `stop_calibration` entity services
- Strategy-aware: filters available attributes by tilt mode

### WebSocket API

- `websocket_api.py` (372 lines) — `cover_time_based/get_config` and `cover_time_based/update_config` commands
- Entity ID → config entry resolution via entity registry
- Partial update support (only send changed fields)
- Full dual-motor field round-tripping

### Lovelace Configuration Card

- `frontend/cover-time-based-card.js` (1,599 lines) — zero-build LitElement card
- Two-tab layout: Device configuration + Timing/Calibration
- Features:
  - Entity picker filtered to cover_time_based entities
  - Device type (switch vs cover entity), input mode, switch entity pickers
  - Tilt mode dropdown (none/sequential/proportional/dual_motor/inline)
  - Dual-motor section with tilt switch pickers and config fields
  - Read-only timing attributes table
  - Position reset presets (strategy-aware: different presets per tilt mode)
  - Calibration controls with live status, mode-specific hints
  - Save-on-change pattern (no "Save All" button)

### State Monitoring

- External switch state change detection (physical buttons, Shelly app, automations)
- Echo filtering to distinguish HA-initiated vs external state changes
- Mode-specific handlers (switch/pulse/toggle) that update the travel calculator

## Config/Translation Changes

- `manifest.json` — added `config_flow: true`, `dependencies: ["http"]`, bumped version
- `services.yaml` — added `start_calibration`, `stop_calibration` service definitions
- `strings.json` — full translations for config flow, options flow, subentry flow, calibration services, tilt modes, selector labels
- `translations/en.json` — synced with strings.json
- `translations/pt.json` — Portuguese translation (171 lines, new)
- `translations/pl.json` — Polish translation (171 lines, new)

## Refactoring Highlights

- Shared constants extracted to `const.py`
- Entity resolution extracted to `helpers.py`
- Calibration methods extracted into `CalibrationMixin`
- `travel_startup_delay` + `travel_delay_at_end` merged into `travel_motor_overhead`
- `tilt_startup_delay` became `tilt_motor_overhead`
- Tilt mode values renamed: `"during"` → `"proportional"`, `"before_after"` → `"sequential"`

## Stats

| Metric | Value |
|---|---|
| Files changed | 24 |
| Lines added | +6,201 |
| Lines removed | -1,233 |
| Net new lines | +4,968 |
| Total lines (main) | 1,484 |
| Total lines (feat/ui-sync-rewrite) | 6,454 |
| Lines untouched | ~251 (17%) |
| Commits | 17 |
| New Python files | 12 |
| New JS files | 1 |
| New translation files | 2 |

## Development Timeline

| Date | Focus |
|---|---|
| Feb 13 | State monitoring, UI config flow |
| Feb 15 | Input mode subclass refactor |
| Feb 17 | Calibration APIs, configuration card, motor overhead merge |
| Feb 18 | Manual position reset for calibration |
| Feb 19 | Tilt strategies (sequential/proportional/dual_motor), tilt config UI, strategy refactor |
| Feb 21 | Inline tilt strategy |
