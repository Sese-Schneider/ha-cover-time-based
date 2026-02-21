# Inline Tilt Strategy Design

## Overview

Add an "inline" tilt mode for single-motor roller shutters where tilt is physically
embedded in the travel mechanism. The same motor controls both travel and tilt — at
the start of any movement there is a fixed time window where only slats change, then
travel continues.

## Physical Model

- Single motor, shared open/close switches (like sequential, unlike dual_motor)
- Tilt works at any position in the travel range, including fully open
- Each direction has a fixed tilt phase duration (`tilt_time_close` / `tilt_time_open`)
- During the tilt phase, cover position changes negligibly (less than one slat) — ignored for tracking
- Closing from fully open: slats close first, then cover closes
- Opening from fully closed: slats open first, then cover opens

## Strategy Class: InlineTilt

New file: `tilt_strategies/inline.py`

Properties:
- `name` → `"inline"`
- `uses_tilt_motor` → `False` (shared motor)
- `can_calibrate_tilt` → `True`
- `restores_tilt` → `True` (new property on TiltStrategy)

### plan_move_position(target, current_pos, current_tilt)

Determine the tilt pre-step needed before travel:

1. Direction: closing if `target < current_pos`, opening otherwise
2. Tilt endpoint for direction: 0 if closing, 100 if opening
3. If current tilt already at direction's endpoint → `[TravelTo(target)]`
4. Otherwise → `[TiltTo(direction_endpoint), TravelTo(target)]`

The existing `_calculate_pre_step_delay` mechanism handles timing — it computes the
tilt phase duration and offsets the travel calculator start. The motor runs continuously
through both phases (same as sequential).

### plan_move_tilt(target_tilt, current_pos, current_tilt)

Simply `[TiltTo(target_tilt)]` — no travel coupling. The tiny position drift during
tilt-only commands is ignored.

### snap_trackers_to_physical(travel_calc, tilt_calc)

Endpoint constraints:
- travel at 0% (fully closed) → force tilt to 0%
- travel at 100% (fully open) → force tilt to 100%

## Tilt Restore Generalization

### New property: `restores_tilt`

Added to `TiltStrategy` base class. Indicates whether the strategy wants tilt restored
to its pre-movement position after a position change completes.

| Strategy     | uses_tilt_motor | restores_tilt |
|-------------|----------------|---------------|
| Sequential   | False          | False         |
| DualMotor    | True           | True          |
| Inline       | False          | True          |

### Changes to cover_base.py

Currently, tilt restore is only triggered for `uses_tilt_motor=True` (dual_motor).
With inline, we need restore for a shared-motor strategy.

**Setting `_tilt_restore_target`**: Change the condition from checking `uses_tilt_motor`
to checking `restores_tilt`. Additionally, skip restore when target is an endpoint
(0 or 100) — at endpoints, tilt is forced to match by `snap_trackers_to_physical`.

**`_start_tilt_restore`**: Branch on `uses_tilt_motor`:
- `True` (dual_motor): stop travel motor, start tilt motor (current behavior)
- `False` (inline): reverse the main motor direction — send the opposite open/close
  command to restore tilt

**`auto_stop_if_necessary` — restore complete**: Branch on `uses_tilt_motor`:
- `True`: send `_send_tilt_stop()` (current behavior)
- `False`: send `_async_handle_command(SERVICE_STOP_COVER)`, clear `_last_command`

**`async_stop_cover` — stop during restore**: Branch on `uses_tilt_motor`:
- `True`: send `_send_tilt_stop()` (current behavior)
- `False`: main motor stop already handled by `_send_stop()`, no extra action needed

## Config / Frontend / API

- `websocket_api.py`: Add `"inline"` to tilt_mode validation
- `cover.py`: Add `InlineTilt` to factory — `"inline"` → `InlineTilt()`
- Frontend card: Add `<option value="inline">Tilts inline with travel</option>`
- No extra config fields needed (no tilt motor switches, no safe position, no boundary)
- Translations: Add inline label to `strings.json` / `en.json`
