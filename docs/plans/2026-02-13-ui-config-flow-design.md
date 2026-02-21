# UI Config Flow Design

## Overview

Add UI-based configuration to the cover_time_based integration using Home Assistant's config entry + subentry pattern. YAML configuration remains fully supported for backward compatibility.

## Architecture

### Config Entry (one per integration instance)

- `entry.data` — empty (no credentials or connection info needed)
- `entry.options` — default timing values (travel times, tilt times, startup delays, etc.)
- Options flow lets the user edit these defaults at any time

### Subentries (one per cover entity)

- `subentry.subentry_type` = `"cover"`
- `subentry.data` — the cover's full config: name, entity IDs, input mode, and any timing overrides
- Values not set in subentry data fall back to the integration defaults

### YAML (backward compatibility)

- `async_setup_platform()` remains unchanged — existing YAML configs keep working
- YAML-created entities are completely independent of config entry entities
- No migration path needed — users can use either or both

### Default Resolution

When creating a `CoverTimeBased` entity from a subentry:

```
subentry.data[key]  →  entry.options[key]  →  schema default
```

This mirrors the existing YAML pattern: `device config → defaults → schema default`.

## Entity Form (Subentry Flow)

Single form with three sections:

### Main section (always visible)

- **Name** — text field (required)
- **Device type** — selector: "Control via switches" or "Wrap existing cover"
- If switches: **Open switch**, **Close switch**, **Stop switch** (optional) — entity selectors filtered to switch/input_boolean domains
- If existing cover: **Cover entity** — entity selector filtered to cover domain
- **Input mode** — dropdown: switch / pulse / toggle (only shown for switch-based, not for cover_entity_id mode)
- **Pulse time** — float (only shown when input mode is pulse or toggle)

### Travel timing section (collapsed)

- Travel time down, Travel time up
- Tilt time down, Tilt time up
- Travel moves with tilt (boolean)

### Advanced section (collapsed)

- Travel startup delay, Tilt startup delay
- Min movement time
- Travel delay at end

Timing fields left blank in the subentry fall back to the integration defaults. The form shows the current default as placeholder text.

## Options Flow (Integration Defaults)

Single form with two collapsed sections (no name, entity IDs, or input mode):

### Travel timing section

- Travel time down (default: 30), Travel time up (default: 30)
- Tilt time down, Tilt time up
- Travel moves with tilt (default: false)

### Advanced section

- Travel startup delay, Tilt startup delay
- Min movement time
- Travel delay at end

## Files

### New files

- `__init__.py` — `async_setup_entry`, forwards to cover platform
- `config_flow.py` — ConfigFlow, OptionsFlow, SubentryFlow

### Modified files

- `manifest.json` — add `"config_flow": true`
- `cover.py` — add `async_setup_entry` alongside existing `async_setup_platform`
- `strings.json` — add config/options/subentry flow translations

## Constraints

- Do NOT use `ruff format` on existing files — only `ruff check`
- Keep diffs to existing files minimal
- `is_button` deprecation is YAML-only — the UI only exposes `input_mode`
