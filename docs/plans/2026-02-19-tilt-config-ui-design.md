# Tilt Strategy Configuration UI Design

## Goal

Update the Lovelace configuration card and backend to support the three new tilt strategies (sequential, proportional, dual_motor), including strategy-aware position presets, calibration test filtering, and dual-motor entity/config fields.

## 1. Tilt Mode Dropdown

The Device tab dropdown gets 4 options:

| Value | Label |
|---|---|
| `none` | Not supported |
| `sequential` | Closes then tilts |
| `proportional` | Tilts with movement |
| `dual_motor` | Separate tilt motor |

Replaces the old `before_after`/`during` values.

## 2. Conditional Field Visibility

| Field | none | sequential | proportional | dual_motor |
|---|---|---|---|---|
| Tilt time (close/open) | hidden | shown | hidden | shown |
| Tilt startup delay | hidden | shown | hidden | shown |
| Tilt Motor section | hidden | hidden | hidden | **shown** |

Proportional hides tilt timing because tilt is derived from position.

## 3. Tilt Motor Section (dual_motor only)

A separate labeled section shown only when `tilt_mode=dual_motor`:

- **Tilt open switch** — entity picker (required)
- **Tilt close switch** — entity picker (required)
- **Tilt stop switch** — entity picker (optional)
- **Safe tilt position** — number input, 0-100, default 0
- **Min tilt allowed position** — number input, 0-100, optional (blank = disabled)

## 4. Position Reset Presets

Strategy-aware presets in the Calibration tab "Current Position" section:

**`none` mode:**

| Preset | Position | Tilt |
|---|---|---|
| Unknown | — | — |
| Fully open | 0 | — |
| Fully closed | 100 | — |

**`proportional` mode:**

| Preset | Position | Tilt |
|---|---|---|
| Unknown | — | — |
| Fully open | 0 | 0 |
| Fully closed | 100 | 100 |

**`sequential` and `dual_motor` modes:**

| Preset | Position | Tilt |
|---|---|---|
| Unknown | — | — |
| Fully open | 0 | 0 |
| Fully closed, tilt open | 100 | 0 |
| Fully closed, tilt closed | 100 | 100 |

## 5. Calibration Attribute Disabling After Reset

Based on the selected position preset:

- **Fully open (pos=0):** disables `travel_time_open`, `tilt_time_open`
- **Fully closed, tilt open (pos=100, tilt=0):** disables `travel_time_close`, `tilt_time_open`
- **Fully closed, tilt closed (pos=100, tilt=100):** disables `travel_time_close`, `tilt_time_close`

## 6. Calibration Test Availability per Mode

| Attribute | none | sequential | proportional | dual_motor |
|---|---|---|---|---|
| travel_time_close | yes | yes | yes | yes |
| travel_time_open | yes | yes | yes | yes |
| travel_startup_delay | yes | yes | yes | yes |
| tilt_time_close | — | yes | — | yes |
| tilt_time_open | — | yes | — | yes |
| tilt_startup_delay | — | yes | — | yes |
| min_movement_time | yes | yes | yes | yes |

Proportional mode has no tilt calibration tests.

## 7. Calibration Hints (Mode-Specific)

### Sequential

- **travel_time_close:** "Start with slats fully open. Click Finish when the cover is fully closed, before the slats start tilting."
- **travel_time_open:** "Start with slats fully open. Click Finish when the cover is fully open."
- **tilt_time_close:** "Cover must be fully closed. Click Finish when the slats are fully closed."
- **tilt_time_open:** "Cover must be fully closed with slats closed. Click Finish when the slats are fully open."

### Proportional

- **travel_time_close:** "Click Finish when the cover is fully closed and slats are fully tilted."
- **travel_time_open:** "Click Finish when the cover is fully open and slats are fully open."

### Dual-Motor

- **travel_time_close:** "Ensure tilt is in safe position. Click Finish when the cover is fully closed."
- **travel_time_open:** "Ensure tilt is in safe position. Click Finish when the cover is fully open."
- **tilt_time_close:** "Cover must be in tilt-allowed position. Click Finish when the slats are fully closed."
- **tilt_time_open:** "Cover must be in tilt-allowed position. Click Finish when the slats are fully open."

### All modes

- **travel_startup_delay / tilt_startup_delay:** Automated stepped test, no mode-specific hint needed beyond existing hints.
- **min_movement_time:** Automated pulse test, generic hint.

## 8. Backend Changes

### WebSocket API

- Validate `tilt_open_switch` and `tilt_close_switch` required when `tilt_mode=dual_motor`
- Clear dual-motor fields when switching away from `dual_motor`

### Calibration Module

- Add `get_calibratable_attributes(tilt_mode: str) -> list[str]` function
- Used by card JS to filter dropdown, and by `start_calibration` for validation

### Strings/Translations

- Tilt mode option labels
- Tilt Motor section heading
- safe_tilt_position, min_tilt_allowed_position field labels
- Position preset labels
- Updated calibration hints

### No Changes Needed

- Strategy implementations (already complete)
- cover_base.py movement logic
- cover.py factory (already handles dual_motor)
