# Design: `close_includes_tilt` option and `is_closed` redefinition

**Date:** 2026-05-17
**Branch:** `toggle` (based on `main` — supersedes the abandoned PR #74)
**Addresses:** issue #70 (cover.toggle stuck on covers with sequential tilt strategies)

## Problem

On a cover that uses `sequential_close` or `dual_motor` tilt, `cover.toggle` gets stuck after the first close press. Two underlying issues:

1. **Toggle needs two presses to close on `sequential_close`.** After one press of `cover.toggle` (which calls `close_cover`), the cover lands at travel=0 with slats still at the implicit-open tilt=100. HA reads `is_closed=False` (because tilt!=0) and pressing toggle again calls `close_cover` once more — which today emits a wasted "resync" motor pulse without closing the slats.
2. **Toggle is completely broken on `dual_motor`.** After `close_cover`, the cover lands at travel=0 with tilt parked at `safe_tilt_position` (default 100). `is_closed=False`. A second `close_cover` is a no-op (travel already at 0). The user has no way to reach a "closed" state via toggle.

PR #74 attempted a fix specific to sequential modes: detect the articulated state on a second `close_cover` press and close the slats instead of resyncing. The maintainer (sebschub) accepted that it works but objected to the design: HA convention is that `close_cover` re-applied should be a no-op, and `close_cover` should not couple travel with tilt by default. This spec abandons PR #74 in favour of a different approach that fits HA conventions.

## Root cause

`is_closed` at [cover_base.py:311-316](../../custom_components/cover_time_based/cover_base.py#L311-L316):

```python
def is_closed(self):
    if not self._has_tilt_support():
        return self.travel_calc.is_closed()
    return self.travel_calc.is_closed() and self.tilt_calc.is_closed()
```

HA's built-in `async_toggle` reads `is_closed` to decide open vs close. The "AND tilt" branch conflates the cover (travel) with the slats (tilt) — so the articulated state `(travel=0, tilt=implicit)` is reported as "not closed" even though the cover itself is at its closed endpoint. That's what makes toggle ping-pong on the close side.

## Design

Two coordinated changes.

### Change 1: Redefine `is_closed` as travel-only

```python
@property
def is_closed(self):
    return self.travel_calc.is_closed()
```

A cover is "closed" when its travel is at 0, regardless of slat position. From `(0, 100)`, `is_closed=True` → toggle calls `open_cover` → travels up. This matches user intuition ("the cover is closed, even if the slats happen to be open") and aligns with how other HA cover integrations report state.

Tilt state remains observable via `current_cover_tilt_position` for templates / automations that care.

### Change 2: New `close_includes_tilt` option

A per-cover boolean, default `true`, exposed in the integration's UI for `sequential_close` and `dual_motor` only (no-op for `inline` and `sequential_open`, whose `close_cover` already lands at tilt=0).

The option affects ONLY `async_close_cover`:
- **`true` (default):** `close_cover` does travel→0 followed by tilt→0. End state `(0, 0)`.
- **`false`:** `close_cover` does travel→0 only. End state `(0, implicit)` for sequential_close, `(0, safe)` for dual_motor. Slats handled separately by `close_cover_tilt`.

`async_open_cover`, `async_set_cover_position`, `async_open_cover_tilt`, and `async_close_cover_tilt` are unchanged. Each strategy's existing pre-step logic (mechanical for sequential, safety for dual_motor) stays exactly as it is.

### Change 3: Implementation in `async_close_cover`

Strategy-agnostic — check the resulting tilt position rather than the strategy class:

```python
async def async_close_cover(self, **kwargs):
    self._require_configured()
    self._log("async_close_cover")
    if self.is_opening:
        await self.async_stop_cover()
        await self._direction_change_delay()

    # Skip the travel "resync pulse" when already settled at 0. The
    # default _async_move_to_endpoint(0) re-sends a CLOSE motor command
    # at target==current (see cover_base.py:531-544), which contradicts
    # the HA convention that close_cover re-applied should be a no-op.
    # Gate on travel_direction==STOPPED so the skip only kicks in once
    # the motor has actually settled, not during the final 1% of an
    # active close where current_position() can briefly read 0 while
    # the motor is still finishing.
    settled_at_zero = (
        self.travel_calc.current_position() == 0
        and self.travel_calc.travel_direction == TravelStatus.STOPPED
    )
    if not settled_at_zero:
        await self._async_move_to_endpoint(target=0)

    if (
        self._close_includes_tilt
        and self._has_tilt_support()
        and self.tilt_calc.current_position() not in (None, 0)
    ):
        await self._async_move_tilt_to_endpoint(target=0)
```

This naturally handles "close from articulated state" (settled at 0, tilt!=0 → goes straight to the tilt-close branch when option=true; no-op when option=false). inline and sequential_open are no-ops at the trailing tilt step (their tilt is already 0 after travel close), so no isinstance branching is needed.

**Scope note:** the skip-resync-when-at-0 behavior applies to all strategies (not just sequential). For non-tilt covers and for inline / sequential_open, this means `close_cover` at-0 becomes a no-op instead of emitting a brief resync pulse. This matches HA's general convention. Users who relied on the resync pulse for physical drift correction can use the `set_known_position` service or recalibrate.

`async_open_cover` is intentionally NOT changed — it still emits a resync pulse if called at travel=100. The asymmetry is acceptable for this iteration; opens are a much less common "redundant call" pattern and changing them is out of scope.

## Resulting behavior matrix

| State | Action | `close_includes_tilt=true` (default) | `close_includes_tilt=false` |
|---|---|---|---|
| (100, 100) | close_cover | → (0, 0) | → (0, implicit) |
| (100, 100) | toggle | close_cover → (0, 0) | close_cover → (0, implicit) |
| (0, implicit) | close_cover | → (0, 0) | no-op |
| (0, implicit) | toggle | open_cover → (100, fully-open) | open_cover → (100, fully-open) |
| (0, 0) | toggle | open_cover → (100, fully-open) | open_cover → (100, fully-open) |
| (0, 0) | close_cover | no-op | no-op |
| any | set_cover_position(0) | strategy default (travel→0, tilt unchanged) | same |
| any | set_cover_position(100) | strategy default (existing pre-steps preserved) | same |
| any | open_cover | strategy's "fully open" (existing behavior) | same |

"implicit" = the strategy's `implicit_tilt_during_travel` (100 for sequential_close, 0 for sequential_open) or `safe_tilt_position` (default 100 for dual_motor). "fully-open" = (100, 100) for inline/sequential_close/dual_motor, (100, 0) for sequential_open.

## Files changed

1. **`const.py`** — add `CONF_CLOSE_INCLUDES_TILT = "close_includes_tilt"` and `DEFAULT_CLOSE_INCLUDES_TILT = True`.
2. **`cover_base.py`** —
   - Change `is_closed` to `return self.travel_calc.is_closed()`.
   - Store `self._close_includes_tilt` from constructor arg.
   - Rewrite `async_close_cover` per Change 3.
3. **`cover.py`** — read `close_includes_tilt` from config in entry setup and pass to `CoverTimeBased.__init__`.
4. **`websocket_api.py`** — expose the option in the config schema; only relevant for `tilt_mode in ("sequential_close", "dual_motor")` but harmless to store for others.
5. **Tests** — add `tests/test_close_includes_tilt.py` (or extend an existing test module) with:
   - Full state matrix above × both option values × `sequential_close` + `dual_motor`.
   - Regression test confirming `is_closed` returns True at `(0, 100)` with tilt support.
   - Tests confirming inline + sequential_open behavior is unchanged regardless of option value.
   - Test that `close_cover` at settled `(0, 0)` is a no-op (no resync pulse) for all strategies.

### Change 5: UI-initiated close_cover / open_cover stops the cover when in motion

A UI click of `cover.close_cover` or `cover.open_cover` on a cover that is currently moving (in either direction) now **stops** the cover instead of either re-issuing the same direction or reversing. Reversing direction requires a second click, or a `set_cover_position` call (which keeps its existing stop-then-reverse behavior).

External triggers (wall switches and wrapped underlying covers, detected via `_triggered_externally`) keep the legacy "stop and reverse if needed" behavior to honor the physical user intent.

Rationale: when the cover is moving and the user clicks close/open, the most common intent is "stop here", not "keep going" or "go the other way". This aligns close/open with HA's built-in `cover.toggle` which already dispatches stop when `is_closing or is_opening`.

Implementation: in both `async_close_cover` and `async_open_cover`, before any movement logic:

```python
if not self._triggered_externally and (self.is_opening or self.is_closing):
    await self.async_stop_cover()
    return
```

For external triggers in the opposite direction, the legacy `async_stop_cover()` + `_direction_change_delay()` flow is preserved.

## What is explicitly NOT changing

- All `set_cover_position` calls — no new tilt coupling.
- `async_open_cover` — strategies' existing pre-steps preserved (mechanically required for sequential, safety constraint for dual_motor). The resync-at-100 pulse is kept.
- `async_open_cover_tilt` and `async_close_cover_tilt` — unchanged.
- External-close redirect at [cover_base.py:494-506](../../custom_components/cover_time_based/cover_base.py#L494-L506) — handles physical switch reconciliation, not user intent.
- Calibration paths — bypass `async_close_cover` and `plan_move_position` entirely.
- Strategy classes — `SequentialCloseTilt`, `DualMotorTilt`, etc. unchanged. The option logic lives in `cover_base.py`, not in the strategy.
- Run-on suppression at sequential closed endpoint ([sequential.py:75-81](../../custom_components/tilt_strategies/sequential.py#L75-L81)) — already on main and continues to apply.

## Migration

None. The default `close_includes_tilt=true` gives the desired "one-press full close" behavior for `sequential_close` and `dual_motor` out of the box. Users who want strict HA convention can set the option to `false`. Existing installations get the default automatically; no config migration required.

## Open questions

None.
