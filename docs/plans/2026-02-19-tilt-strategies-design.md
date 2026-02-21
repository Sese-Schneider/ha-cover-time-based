# Tilt Strategies Design

## Context

The cover_time_based integration needs three tilt strategies to support different physical blind/cover mechanisms. This design replaces the current reactive coupling interface with a command-based approach where strategies return movement plans.

## Position Convention

- **Position 0** = fully open (cover raised/retracted)
- **Position 100** = fully closed (cover lowered/extended)
- **Tilt 0** = fully open (slats flat/horizontal)
- **Tilt 100** = fully closed (slats angled shut)
- `travel_time` = time for cover to travel full range (excludes tilt)
- `tilt_time` = time for slats to rotate full range

## Strategies

### 1. Sequential (Standard Venetian)

Single motor. Tilt mechanism only engages at position 100% (fully closed). The motor rotates slats first, then engages lift cords.

- **Opening from closed:** tilt phase (slats open to 0) then travel phase (cover lifts)
- **Closing to closed:** travel phase (cover drops) then tilt phase (slats close)
- **Tilt command from non-100% position:** travel to 100% first, then tilt
- **Total motor time** = `tilt_time + travel_time`
- **Tilt calibration:** allowed

### 2. Proportional (Architectural / Sun-Tracking)

Single motor with gear system. Tilt is derived from position — one degree of freedom.

- Tilt and travel are fully coupled bidirectionally
- At travel boundaries (0% / 100%), tilt is forced to match
- **Tilt calibration:** not allowed (tilt derived from position)

### 3. Dual-Motor (Independent / Boundary-Locked)

Separate tilt motor with its own switch entities. Configurable boundary lock and safety threshold.

- **Position change sequence:** tilt to safe position, travel, then user can tilt to desired angle
- **Tilt boundary (optional):** `min_tilt_allowed_position` — tilt only allowed when position >= this value
- **Safe tilt position:** configurable (default 0) — slats must be here before travel
- **Tilt calibration:** allowed

## Interface Design

### MovementStep Types

Strategies return a list of logical steps. The cover entity handles motor activation.

```python
@dataclass
class TiltTo:
    target: int                         # tilt position 0-100
    coupled_travel: int | None = None   # also move travel to this (proportional)

@dataclass
class TravelTo:
    target: int                         # travel position 0-100
    coupled_tilt: int | None = None     # also move tilt to this (proportional)

MovementStep = TiltTo | TravelTo
```

### TiltStrategy ABC

```python
class TiltStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for config/state ('sequential', 'proportional', 'dual_motor')."""

    @property
    @abstractmethod
    def uses_tilt_motor(self) -> bool:
        """Whether TiltTo steps require a separate tilt motor."""

    @abstractmethod
    def plan_move_position(self, target_pos, current_pos, current_tilt) -> list[MovementStep]:
        """Plan steps to move cover to target_pos."""

    @abstractmethod
    def plan_move_tilt(self, target_tilt, current_pos, current_tilt) -> list[MovementStep]:
        """Plan steps to move tilt to target_tilt."""

    @abstractmethod
    def snap_trackers_to_physical(self, travel_calc, tilt_calc) -> None:
        """Correct tracker drift after stop to match physical reality."""

    @abstractmethod
    def can_calibrate_tilt(self) -> bool:
        """Whether tilt calibration is allowed."""
```

### Strategy Implementations

**Sequential:**
```python
def plan_move_position(self, target_pos, current_pos, current_tilt):
    steps = []
    if current_tilt != 0:
        steps.append(TiltTo(0))
    steps.append(TravelTo(target_pos))
    return steps

def plan_move_tilt(self, target_tilt, current_pos, current_tilt):
    steps = []
    if current_pos != 100:
        steps.append(TravelTo(100))
    steps.append(TiltTo(target_tilt))
    return steps
```

**Proportional:**
```python
def plan_move_position(self, target_pos, current_pos, current_tilt):
    return [TravelTo(target_pos, coupled_tilt=target_pos)]

def plan_move_tilt(self, target_tilt, current_pos, current_tilt):
    return [TiltTo(target_tilt, coupled_travel=target_tilt)]
```

**Dual-Motor:**
```python
def __init__(self, safe_tilt_position=0, min_tilt_allowed_position=None): ...

def plan_move_position(self, target_pos, current_pos, current_tilt):
    steps = []
    if current_tilt != self.safe_tilt_position:
        steps.append(TiltTo(self.safe_tilt_position))
    steps.append(TravelTo(target_pos))
    return steps

def plan_move_tilt(self, target_tilt, current_pos, current_tilt):
    steps = []
    if self.min_tilt_allowed_position is not None and current_pos < self.min_tilt_allowed_position:
        steps.append(TravelTo(self.min_tilt_allowed_position))
    steps.append(TiltTo(target_tilt))
    return steps
```

## Cover Entity Execution Model

The cover entity receives a `list[MovementStep]` and executes it:

1. **Same-motor grouping:** Consecutive steps on the same motor become a single continuous motor run with phased targets. For sequential, `[TiltTo(0), TravelTo(30)]` is one motor run — tilt target set first, travel target set after tilt completes.

2. **Different-motor transitions:** When consecutive steps use different motors (dual-motor), the first motor completes and stops, then the second activates.

3. **Motor selection:** `TravelTo` always uses the travel motor. `TiltTo` uses the tilt motor if `strategy.uses_tilt_motor` is True, otherwise the travel motor.

4. **Coupled targets:** When a step has `coupled_tilt` or `coupled_travel`, both calculator targets are set simultaneously on the same motor activation.

5. **Stop cancels remaining steps:** User stop mid-plan stops the current step, discards remaining steps, and calls `snap_trackers_to_physical`.

## snap_trackers_to_physical (Post-Stop Tracker Correction)

Called after stop to correct internal position trackers to match physical reality. Does NOT activate motors.

- **Sequential:** If position != 100, force tilt to 0 (slats must be flat away from closed endpoint)
- **Proportional:** Force tilt to 0 at position 0, force tilt to 100 at position 100
- **Dual-Motor:** If position < `min_tilt_allowed_position`, force tilt to `safe_tilt_position`

## Config Options

Existing options unchanged. New additions for dual-motor:

| Option | Type | Required | Default |
|---|---|---|---|
| `tilt_mode: "dual_motor"` | string | - | - |
| `tilt_open_switch` | entity ID | yes (when dual_motor) | - |
| `tilt_close_switch` | entity ID | yes (when dual_motor) | - |
| `tilt_stop_switch` | entity ID | no | - |
| `safe_tilt_position` | int 0-100 | no | 0 |
| `min_tilt_allowed_position` | int 0-100 | no | None (tilt anywhere) |

Validation: if `strategy.uses_tilt_motor` is True but tilt switch entities aren't configured, raise a config error.

No config version bump needed — `dual_motor` is a new tilt_mode value, not a rename.

## Strategy Summary

| | Sequential | Proportional | Dual-Motor |
|---|---|---|---|
| `name` | `"sequential"` | `"proportional"` | `"dual_motor"` |
| `uses_tilt_motor` | False | False | True |
| `can_calibrate_tilt` | True | False | True |
| `plan_move_position` | TiltTo(0) then TravelTo(x) | TravelTo(x, coupled_tilt=x) | TiltTo(safe) then TravelTo(x) |
| `plan_move_tilt` | TravelTo(100) then TiltTo(x) | TiltTo(x, coupled_travel=x) | TravelTo(min_pos) then TiltTo(x) |
| `snap_trackers_to_physical` | Tilt=0 when pos!=100 | Tilt matches at boundaries | Tilt=safe when pos < min |
