# Inverted Sequential Tilt Mode — Design

## Background

Issue [#61](https://github.com/Sese-Schneider/ha-cover-time-based/issues/61) reports a cover design where slats articulate by the motor driving *further down* past the cover-closed position, rather than the conventional direction (motor briefly reversing up). The mechanical sequence is:

1. **Top** — cover fully open
2. **Middle** — cover closed, slats closed (a mechanical latch the motor does not stop at by itself)
3. **Bottom** — cover closed, slats open (motor pushed past the middle latch)

The existing `sequential` tilt mode assumes the opposite: at the closed position, tilt-open sends OPEN (motor up), tilt-close sends CLOSE (motor down). No existing configuration supports the reporter's hardware.

## Goal

Add a new tilt mode — display label "Closes then tilts open" — in which tilt direction is inverted relative to the existing sequential mode. Rename the existing mode to "Closes then tilts closed" for symmetry. Scope is limited to sequential; inline and dual-motor are unaffected.

## Non-goals

- No inverted variant for inline tilt (no reported hardware matches).
- No changes to dual-motor, wrapped-cover, or control-mode (switch/pulse/toggle) code paths beyond the tilt direction abstraction.
- No UI changes beyond the dropdown label and calibration hints.

## Naming and config values

| Internal `tilt_mode` | Display label (en)            | Status                                                  |
| -------------------- | ----------------------------- | ------------------------------------------------------- |
| `none`               | "Not supported"               | Unchanged                                               |
| `sequential_close`   | "Closes then tilts closed"    | **Renamed from `sequential`**; behavior unchanged       |
| `sequential_open`    | "Closes then tilts open"      | **New**; tilt direction inverted                        |
| `inline`             | "Tilts inline with travel"    | Unchanged                                               |
| `dual_motor`         | "Separate tilt motor"         | Unchanged                                               |

## Config migration

- Bump `ConfigEntry.VERSION` from `1` to `2`.
- Add `async_migrate_entry` in `custom_components/cover_time_based/__init__.py` that rewrites `options[CONF_TILT_MODE] == "sequential"` → `"sequential_close"` and updates the entry version.
- In `_resolve_tilt_strategy` ([cover.py:247](custom_components/cover_time_based/cover.py#L247)), accept `"sequential"` as a legacy alias for `"sequential_close"`. This protects YAML users and any migration edge case.

## Strategy class hierarchy

```
TiltStrategy (base.py)
├── InlineTilt
├── DualMotorTilt
└── SequentialTilt                 (abstract — shared planning & snap logic)
    ├── SequentialCloseTilt        (implicit_tilt_during_travel = 100)
    └── SequentialOpenTilt         (implicit_tilt_during_travel = 0)
```

`SequentialTilt` becomes an abstract base holding the shared logic. The two concrete subclasses differ only in two data points:

- `name` — `"sequential_close"` or `"sequential_open"`
- `implicit_tilt_during_travel` — `100` or `0` respectively

`SequentialOpenTilt` also overrides `tilt_command_for` (see below).

## Tilt direction abstraction

Add a method to `TiltStrategy`:

```python
def tilt_command_for(self, closing_tilt: bool) -> str:
    """Return the HA cover service to send for this tilt direction."""
    return SERVICE_CLOSE_COVER if closing_tilt else SERVICE_OPEN_COVER
```

`SequentialOpenTilt` overrides it to return the inverted command. `InlineTilt`, `DualMotorTilt`, and `SequentialCloseTilt` inherit the default.

**Call sites updated to consult the strategy:**

| Location                                                                                     | Current logic                                                    |
| -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| [cover_base.py:582-589](custom_components/cover_time_based/cover_base.py#L582-L589)          | `_async_move_tilt_to_endpoint` single-motor branch               |
| [cover_base.py:692-695](custom_components/cover_time_based/cover_base.py#L692-L695)          | `set_tilt_position` single-motor branch                          |
| [cover_base.py:1371-1373](custom_components/cover_time_based/cover_base.py#L1371-L1373)      | `_start_tilt_restore` shared-motor branch                        |
| [cover_calibration.py:116-125](custom_components/cover_time_based/cover_calibration.py#L116-L125) | `_start_simple_time_test` dispatch for `tilt_time_*` attributes |

Each call site replaces `SERVICE_CLOSE_COVER if closing_tilt else SERVICE_OPEN_COVER` with `self._tilt_strategy.tilt_command_for(closing_tilt)`. The `dual_motor` branch (which uses `_send_tilt_open`/`_send_tilt_close` against dedicated tilt switches) is unaffected.

## Physical-state semantics (`implicit_tilt_during_travel`)

In sequential modes, the slats are physically constrained to a single tilt value while the cover is not at the closed position. For `sequential_close`, that value is 100 (slats open). For `sequential_open`, it is 0 (slats closed).

The shared `SequentialTilt` base uses the `implicit_tilt_during_travel` property in two places:

### `plan_move_position`

Before starting travel, if `current_tilt != implicit_tilt_during_travel`, insert a `TiltTo(implicit_tilt_during_travel)` pre-step.

```python
def plan_move_position(self, target_pos, current_pos, current_tilt):
    steps = []
    if current_tilt != self.implicit_tilt_during_travel:
        steps.append(TiltTo(self.implicit_tilt_during_travel))
    steps.append(TravelTo(target_pos))
    return steps
```

### `snap_trackers_to_physical`

When the cover stops at `travel != 0`, force tilt to the implicit value to correct tracker drift:

```python
def snap_trackers_to_physical(self, travel_calc, tilt_calc):
    current_travel = travel_calc.current_position()
    current_tilt_pos = tilt_calc.current_position()
    if current_travel is None or current_tilt_pos is None:
        return
    implicit = self.implicit_tilt_during_travel
    if current_travel != 0 and current_tilt_pos != implicit:
        tilt_calc.set_position(implicit)
```

`plan_move_tilt` is unchanged and identical in both variants (travel to 0, then TiltTo target).

## Frontend / translations

All strings live in [cover-time-based-card.js](custom_components/cover_time_based/frontend/cover-time-based-card.js).

**Renamed keys** (5 per language × 3 languages = 15 total):
- `tilt.sequential` → `tilt.sequential_close`
- `hints.sequential.travel_time_close` → `hints.sequential_close.travel_time_close`
- `hints.sequential.travel_time_open` → `hints.sequential_close.travel_time_open`
- `hints.sequential.tilt_time_close` → `hints.sequential_close.tilt_time_close`
- `hints.sequential.tilt_time_open` → `hints.sequential_close.tilt_time_open`

**New keys** (5 per language × 3 languages = 15 total):
- `tilt.sequential_open` — display label.
- `hints.sequential_open.travel_time_close` — "Start with cover fully open and slats closed. Click Finish when the cover is fully closed, before the slats start tilting open."
- `hints.sequential_open.travel_time_open` — "Start with cover closed and slats closed. Click Finish when the cover is fully open."
- `hints.sequential_open.tilt_time_close` — "Start with cover closed but slats open. Click Finish when the slats are fully closed." (same wording as `sequential_close`)
- `hints.sequential_open.tilt_time_open` — "Start with cover and slats closed. Click Finish when the slats are fully open." (same wording as `sequential_close`)

**Dropdown updates** ([card.js:1028](custom_components/cover_time_based/frontend/cover-time-based-card.js#L1028)): replace the single `sequential` `<option>` with two options for `sequential_close` and `sequential_open`.

**`_onTiltModeChange` handler** ([card.js:610](custom_components/cover_time_based/frontend/cover-time-based-card.js#L610)): the existing `mode === "sequential"` branch becomes `mode === "sequential_close" || mode === "sequential_open"` (same field-clearing logic applies to both).

## Testing

New tests live alongside the existing `test_tilt_strategy.py`, `test_config_flow.py`, and `test_calibration.py` tests.

### Unit — `SequentialOpenTilt` behavior

- `plan_move_position` with `current_tilt != 0` inserts `TiltTo(0)` pre-step; with `current_tilt == 0` skips it.
- `plan_move_tilt` identical to `SequentialCloseTilt` (travel to 0 then TiltTo target).
- `snap_trackers_to_physical` forces tilt to 0 when travel != 0.
- `tilt_command_for(True)` returns `SERVICE_OPEN_COVER` (inverted from default).
- `tilt_command_for(False)` returns `SERVICE_CLOSE_COVER` (inverted from default).
- `implicit_tilt_during_travel == 0`.

### Unit — `SequentialCloseTilt` parity

- Assert that renaming did not change behavior: `implicit_tilt_during_travel == 100`, planning and snap match the current `SequentialTilt` tests.

### Integration — calibration direction

- With `tilt_strategy = SequentialOpenTilt()`, calling `start_calibration(attribute="tilt_time_open")` dispatches `SERVICE_CLOSE_COVER` (asserting the call-site change routes through `tilt_command_for`).
- With `tilt_strategy = SequentialOpenTilt()`, `tilt_time_close` dispatches `SERVICE_OPEN_COVER`.
- With `tilt_strategy = SequentialCloseTilt()`, existing behavior preserved (parity test).

### Integration — config migration

- `ConfigEntry(version=1, options={"tilt_mode": "sequential", ...})` goes through `async_migrate_entry` and ends up with `version=2` and `options["tilt_mode"] == "sequential_close"`.
- Idempotency: a v2 entry is not modified.

### Integration — legacy alias

- `_resolve_tilt_strategy("sequential", tilt_time_close=1, tilt_time_open=1)` returns a `SequentialCloseTilt` instance.

## Out of scope / follow-ups

- Inline-inverted variant (`inline_open`) for covers where slats articulate mid-travel. Revisit if a user reports such hardware.
- UI consolidation (grouping the two sequential variants under a single dropdown with a sub-toggle) — not worth the extra surface for two options.
