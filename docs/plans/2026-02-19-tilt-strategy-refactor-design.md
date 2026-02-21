# Tilt Strategy Refactor — Design

## Goal

Extract tilt mode logic from `cover_base.py` into a Strategy pattern, mirroring how input modes (switch/pulse/toggle) are factored into separate classes. Rename `"during"` → `"proportional"` and `"before_after"` → `"sequential"` to match the physical mechanisms they model. Preserve all current behavior exactly.

## Background

The integration supports four tilt linkage types in the real world (see GitHub issue for full spec):

1. **Sequential** — single motor, tilt phase before/after travel phase
2. **Proportional** — single geared motor, tilt locked to position
3. **Boundary-Locked** — tilt only at a specific position (future)
4. **Independent** — dual motor, fully separate (future)

Currently only Sequential and Proportional are implemented. Boundary-Locked and Independent will need separate tilt switch entities and are out of scope.

## Current State

Tilt mode is checked in exactly 4 places in `cover_base.py`:

1. `_async_move_tilt_to_endpoint()` — couples travel only if `"during"`
2. `set_tilt_position()` — couples travel only if `"during"`
3. `_enforce_tilt_constraints()` — only applies in `"during"`
4. `start_calibration()` — blocks tilt calibration in `"during"`

Supporting methods that contain tilt-mode-specific logic:
- `_calc_coupled_target()` — calculates proportional coupling between travel and tilt
- `_enforce_tilt_constraints()` — forces tilt to match at travel boundaries

## Approach: Strategy Composition

### Why not inheritance?

Input modes use inheritance (SwitchModeCover, PulseModeCover, etc.) because they're mutually exclusive with the class hierarchy. Tilt modes are orthogonal to input modes — using inheritance would create a combinatorial explosion (3 input modes x N tilt modes = many classes). Composition avoids this.

### Strategy Interface

New file: `tilt_strategy.py`

```python
class TiltStrategy:
    """Strategy for how tilt and travel interact."""

    def calc_tilt_for_travel(
        self, movement_time, closing, tilt_calc, tilt_time_close, tilt_time_open
    ) -> int | None:
        """When travel moves, what tilt target? None = no coupling."""

    def calc_travel_for_tilt(
        self, movement_time, closing, travel_calc, travel_time_close, travel_time_open
    ) -> int | None:
        """When tilt moves, what travel target? None = no coupling."""

    def enforce_constraints(self, travel_calc, tilt_calc) -> None:
        """Enforce constraints after movement stops."""

    def can_calibrate_tilt(self) -> bool:
        """Whether independent tilt calibration is allowed."""
```

### Concrete Strategies

**SequentialTilt** (current `"before_after"` behavior):
- `calc_tilt_for_travel()` → proportional target (preserving current behavior)
- `calc_travel_for_tilt()` → `None` (no coupling)
- `enforce_constraints()` → no-op
- `can_calibrate_tilt()` → `True`

**ProportionalTilt** (current `"during"` behavior):
- `calc_tilt_for_travel()` → proportional target
- `calc_travel_for_tilt()` → proportional target
- `enforce_constraints()` → force tilt to match at travel boundaries (0%/100%)
- `can_calibrate_tilt()` → `False`

Both strategies share the same proportional calculation (extracted from `_calc_coupled_target`). The difference is whether tilt→travel coupling exists and whether constraints are enforced.

## Changes by File

### `tilt_strategy.py` (new)
- `TiltStrategy` protocol
- `SequentialTilt` class
- `ProportionalTilt` class
- Shared `_calc_coupled_target()` helper (moved from base class)

### `cover_base.py`
- Constructor: accept `tilt_strategy: TiltStrategy | None` instead of `tilt_mode: str`
- Remove: `_tilt_mode` property, `_tilt_mode_config` attribute
- Remove: `_calc_coupled_target()` (moved to strategy)
- Remove: `_enforce_tilt_constraints()` (moved to strategy)
- Replace 4 mode checks with strategy method calls
- `_has_tilt_support()` now checks `self._tilt_strategy is not None`

### `cover.py` (factory)
- `_create_cover_from_options()`: map config string → strategy instance, pass to constructor
- Config string mapping: `"proportional"` → `ProportionalTilt()`, `"sequential"` → `SequentialTilt()`, `"none"` → `None`

### `__init__.py` (migration)
- Bump config version v2 → v3
- Migration: `"during"` → `"proportional"`, `"before_after"` → `"sequential"`
- Existing v1→v2 migration (`travel_moves_with_tilt` → tilt_mode) outputs new names

### `websocket_api.py`
- Update validation to accept `"sequential"`, `"proportional"`, `"none"`

### `cover_toggle_mode.py`
- `async_stop_cover()` calls `self._tilt_strategy.enforce_constraints(...)` instead of `self._enforce_tilt_constraints()`

## Config Migration

| v1 (legacy) | v2 (current) | v3 (new) |
|---|---|---|
| `travel_moves_with_tilt: true` | `tilt_mode: "during"` | `tilt_mode: "proportional"` |
| `travel_moves_with_tilt: false` | `tilt_mode: "before_after"` | `tilt_mode: "sequential"` |
| *(not set)* | `tilt_mode: "none"` | `tilt_mode: "none"` |

YAML `_migrate_yaml_keys` also maps old value names to new.

## Testing

- **New:** `tests/test_tilt_strategy.py` — unit tests for each strategy in isolation
- **Existing:** Update config values from `"during"`/`"before_after"` to `"proportional"`/`"sequential"` in any tests that reference them
- All existing tests must pass with no behavior changes

## Future Extensibility

Adding Boundary-Locked or Independent tilt:
1. Create new strategy class implementing `TiltStrategy`
2. Add config string mapping in factory
3. Add new config options for tilt switch entities (only these modes need them)
4. No changes to base class needed
