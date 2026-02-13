# State Monitoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect when switches are toggled externally (physical button, Shelly app, automation) and update the travel calculator, achieving full parity with HA-initiated commands.

**Architecture:** Register `async_track_state_change_event` listeners on the open/close/stop switch entities. Use a `_pending_switch` dict to filter echoes from HA-initiated commands. When an external state change is detected, delegate to the existing `async_open/close/stop_cover` methods but skip the hardware command (the switch already toggled). Physical presses always target fully open/closed.

**Tech Stack:** Home Assistant `async_track_state_change_event`, existing `TravelCalculator` from xknx.

**Working directory:** `/workspaces/ha-cover-time-based`

**File to modify:** `custom_components/cover_time_based/cover.py`

**No test framework exists in this repo** — this is a HA custom component without unit tests. Testing is done manually by deploying to HA. After each task, deploy with:
```bash
rm -Rf /workspaces/homeassistant-core/config/custom_components/cover_time_based && cp -r /workspaces/ha-cover-time-based/custom_components/cover_time_based /workspaces/homeassistant-core/config/custom_components/
```

---

### Task 1: Add imports and instance variables

**Files:**
- Modify: `custom_components/cover_time_based/cover.py:28-30` (imports)
- Modify: `custom_components/cover_time_based/cover.py:307-310` (instance variables)

**Step 1: Add `async_track_state_change_event` to imports**

At line 28, the existing import block is:
```python
from homeassistant.helpers.event import (
    async_track_time_interval,
)
```

Change it to:
```python
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
```

**Step 2: Add instance variables in `__init__`**

After line 310 (`self._last_command = None`), add:
```python
        self._triggered_externally = False
        self._pending_switch = {}
        self._pending_switch_timers = {}
        self._state_listener_unsubs = []
```

- `_triggered_externally`: flag to skip `_async_handle_command` when reacting to external events
- `_pending_switch`: `dict[str, int]` tracking expected echo count per switch entity_id
- `_pending_switch_timers`: `dict[str, callable]` timeout cleanup handles per switch entity_id
- `_state_listener_unsubs`: list of unsubscribe callbacks for state listeners

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/cover.py
git commit -m "feat(state-monitoring): add imports and instance variables"
```

---

### Task 2: Register state listeners in `async_added_to_hass`

**Files:**
- Modify: `custom_components/cover_time_based/cover.py:322-341` (async_added_to_hass)

**Step 1: Add listener registration at the end of `async_added_to_hass`**

After the existing tilt restoration code (line 341), add:
```python

        # Register state change listeners for switch entities
        if self._open_switch_entity_id:
            self._state_listener_unsubs.append(
                async_track_state_change_event(
                    self.hass,
                    [self._open_switch_entity_id],
                    self._async_switch_state_changed,
                )
            )
        if self._close_switch_entity_id:
            self._state_listener_unsubs.append(
                async_track_state_change_event(
                    self.hass,
                    [self._close_switch_entity_id],
                    self._async_switch_state_changed,
                )
            )
        if self._stop_switch_entity_id:
            self._state_listener_unsubs.append(
                async_track_state_change_event(
                    self.hass,
                    [self._stop_switch_entity_id],
                    self._async_switch_state_changed,
                )
            )
```

**Step 2: Add `async_will_remove_from_hass` cleanup method**

Add a new method after `async_added_to_hass` (after line 341):
```python

    async def async_will_remove_from_hass(self):
        """Clean up state listeners."""
        for unsub in self._state_listener_unsubs:
            unsub()
        self._state_listener_unsubs.clear()
        for timer in self._pending_switch_timers.values():
            timer()
        self._pending_switch_timers.clear()
```

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/cover.py
git commit -m "feat(state-monitoring): register state listeners on switch entities"
```

---

### Task 3: Add echo filtering to `_async_handle_command`

**Files:**
- Modify: `custom_components/cover_time_based/cover.py:1148-1307` (_async_handle_command)

**Context:** When `_async_handle_command` turns a switch ON or OFF, the hardware will echo back state changes. We need to mark those switches as "pending echo" so the state listener ignores them.

**Step 1: Add a helper method `_mark_switch_pending`**

Add this method somewhere before `_async_handle_command` (e.g., after `set_known_tilt_position` at line 1147):
```python

    def _mark_switch_pending(self, entity_id, expected_transitions):
        """Mark a switch as having pending echo transitions to ignore.

        Args:
            entity_id: The switch entity ID.
            expected_transitions: Number of state transitions to ignore (e.g., 2 for ON+OFF pulse).
        """
        self._pending_switch[entity_id] = self._pending_switch.get(entity_id, 0) + expected_transitions
        _LOGGER.debug("_mark_switch_pending :: %s pending=%d", entity_id, self._pending_switch[entity_id])

        # Cancel any existing timeout for this switch
        if entity_id in self._pending_switch_timers:
            self._pending_switch_timers[entity_id]()

        # Safety timeout: clear pending after 5 seconds
        @callback
        def _clear_pending(_now):
            if entity_id in self._pending_switch:
                _LOGGER.debug("_mark_switch_pending :: timeout clearing %s", entity_id)
                del self._pending_switch[entity_id]
            if entity_id in self._pending_switch_timers:
                del self._pending_switch_timers[entity_id]

        self._pending_switch_timers[entity_id] = async_track_time_interval(
            self.hass, _clear_pending, timedelta(seconds=5)
        )
```

Note: We use `async_track_time_interval` as a one-shot timer (it fires after 5s, clears the pending state, and then we should cancel the timer in `_clear_pending`). Actually, `async_track_time_interval` repeats. Instead, use `self.hass.async_call_later`:

```python

    def _mark_switch_pending(self, entity_id, expected_transitions):
        """Mark a switch as having pending echo transitions to ignore."""
        self._pending_switch[entity_id] = self._pending_switch.get(entity_id, 0) + expected_transitions
        _LOGGER.debug("_mark_switch_pending :: %s pending=%d", entity_id, self._pending_switch[entity_id])

        # Cancel any existing timeout for this switch
        if entity_id in self._pending_switch_timers:
            self._pending_switch_timers[entity_id]()

        # Safety timeout: clear pending after 5 seconds
        @callback
        def _clear_pending(_now):
            if entity_id in self._pending_switch:
                _LOGGER.debug("_mark_switch_pending :: timeout clearing %s", entity_id)
                del self._pending_switch[entity_id]
            if entity_id in self._pending_switch_timers:
                del self._pending_switch_timers[entity_id]

        self._pending_switch_timers[entity_id] = self.hass.helpers.event.async_call_later(
            5, _clear_pending
        )
```

Actually, the simplest HA approach is `async_call_later` from the hass object:

```python
    def _mark_switch_pending(self, entity_id, expected_transitions):
        """Mark a switch as having pending echo transitions to ignore."""
        self._pending_switch[entity_id] = self._pending_switch.get(entity_id, 0) + expected_transitions
        _LOGGER.debug("_mark_switch_pending :: %s pending=%d", entity_id, self._pending_switch[entity_id])

        # Cancel any existing timeout for this switch
        if entity_id in self._pending_switch_timers:
            self._pending_switch_timers[entity_id]()

        # Safety timeout: clear pending after 5 seconds
        @callback
        def _clear_pending(_now):
            if entity_id in self._pending_switch:
                _LOGGER.debug("_mark_switch_pending :: timeout clearing %s", entity_id)
                del self._pending_switch[entity_id]
            self._pending_switch_timers.pop(entity_id, None)

        self._pending_switch_timers[entity_id] = self.hass.loop.call_later(
            5, lambda: self.hass.async_create_task(_wrap_clear_pending())
        )
```

Hmm, let's keep it simple. Use `asyncio.get_event_loop().call_later` or just use HA's built-in `async_call_later`:

```python
from homeassistant.helpers.event import async_call_later
```

Then:
```python
    def _mark_switch_pending(self, entity_id, expected_transitions):
        """Mark a switch as having pending echo transitions to ignore."""
        self._pending_switch[entity_id] = self._pending_switch.get(entity_id, 0) + expected_transitions
        _LOGGER.debug("_mark_switch_pending :: %s pending=%d", entity_id, self._pending_switch[entity_id])

        # Cancel any existing timeout for this switch
        if entity_id in self._pending_switch_timers:
            self._pending_switch_timers[entity_id]()

        # Safety timeout: clear pending after 5 seconds
        @callback
        def _clear_pending(_now):
            if entity_id in self._pending_switch:
                _LOGGER.debug("_mark_switch_pending :: timeout clearing %s", entity_id)
                del self._pending_switch[entity_id]
            self._pending_switch_timers.pop(entity_id, None)

        self._pending_switch_timers[entity_id] = async_call_later(
            self.hass, 5, _clear_pending
        )
```

**Step 2: Add `_mark_switch_pending` calls in `_async_handle_command`**

In the CLOSE command section (lines 1159-1188), after the `else:` block that handles switch entities, add pending markers. The logic differs by input mode:

For **SERVICE_CLOSE_COVER** (line 1149):
- `turn_off(open_switch)` → 1 transition (OFF, but might already be off = 0 transitions). Mark 1 to be safe.
- `turn_on(close_switch)` → 1 transition (ON)
- If pulse/toggle: `turn_off(close_switch)` → 1 more transition (OFF). Total = 2 for close_switch.

Add right after `else:` at line 1159 (before the service calls):
```python
                self._mark_switch_pending(self._open_switch_entity_id, 1)
                if self._input_mode in (INPUT_MODE_PULSE, INPUT_MODE_TOGGLE):
                    self._mark_switch_pending(self._close_switch_entity_id, 2)
                else:
                    self._mark_switch_pending(self._close_switch_entity_id, 1)
                if self._stop_switch_entity_id is not None:
                    self._mark_switch_pending(self._stop_switch_entity_id, 1)
```

For **SERVICE_OPEN_COVER** (line 1190): same pattern mirrored:
```python
                self._mark_switch_pending(self._close_switch_entity_id, 1)
                if self._input_mode in (INPUT_MODE_PULSE, INPUT_MODE_TOGGLE):
                    self._mark_switch_pending(self._open_switch_entity_id, 2)
                else:
                    self._mark_switch_pending(self._open_switch_entity_id, 1)
                if self._stop_switch_entity_id is not None:
                    self._mark_switch_pending(self._stop_switch_entity_id, 1)
```

For **SERVICE_STOP_COVER** (line 1230): depends on sub-branch:
- Toggle mode with last_command = close: `turn_on` + `turn_off` on close_switch = 2 transitions
- Toggle mode with last_command = open: `turn_on` + `turn_off` on open_switch = 2 transitions
- Switch/pulse mode: `turn_off` on both switches (1 each), `turn_on` (+ maybe `turn_off`) on stop_switch

Add `_mark_switch_pending` calls before each group of service calls in the STOP section.

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/cover.py
git commit -m "feat(state-monitoring): add echo filtering to _async_handle_command"
```

---

### Task 4: Add the `_triggered_externally` flag check

**Files:**
- Modify: `custom_components/cover_time_based/cover.py` — `async_close_cover`, `async_open_cover`, `async_stop_cover`

**Step 1: In `async_close_cover` (line 529), skip `_async_handle_command` when triggered externally**

Find line 578:
```python
            await self._async_handle_command(SERVICE_CLOSE_COVER)
```

Replace with:
```python
            if not self._triggered_externally:
                await self._async_handle_command(SERVICE_CLOSE_COVER)
```

Also need to handle the STOP commands that are sent during direction changes (lines 548, 556). These should also be skipped when external. But since those are called via `async_stop_cover` (line 536, 540) which will check the flag itself, that's handled.

Wait — lines 548 and 556 call `_async_handle_command(SERVICE_STOP_COVER)` directly, not through `async_stop_cover`. These also need the flag check:

Line 548:
```python
                    await self._async_handle_command(SERVICE_STOP_COVER)
```
→
```python
                    if not self._triggered_externally:
                        await self._async_handle_command(SERVICE_STOP_COVER)
```

Line 556:
```python
                await self._async_handle_command(SERVICE_STOP_COVER)
```
→
```python
                if not self._triggered_externally:
                    await self._async_handle_command(SERVICE_STOP_COVER)
```

**Step 2: Same changes in `async_open_cover` (line 596)**

Apply the same pattern to all `_async_handle_command` calls in `async_open_cover`.

**Step 3: In `async_stop_cover` (line 737), skip `_async_handle_command`**

Find line 746:
```python
        await self._async_handle_command(SERVICE_STOP_COVER)
```

Replace with:
```python
        if not self._triggered_externally:
            await self._async_handle_command(SERVICE_STOP_COVER)
```

**Step 4: Also check in tilt methods**

Apply the same pattern to `async_close_cover_tilt` and `async_open_cover_tilt` — all their `_async_handle_command` calls should check `_triggered_externally`.

**Step 5: Commit**

```bash
git add custom_components/cover_time_based/cover.py
git commit -m "feat(state-monitoring): skip hardware commands when triggered externally"
```

---

### Task 5: Implement the state change handler

**Files:**
- Modify: `custom_components/cover_time_based/cover.py` — add new method `_async_switch_state_changed`

**Step 1: Add the handler method**

Add after the `_mark_switch_pending` method:

```python

    async def _async_switch_state_changed(self, event):
        """Handle state changes on monitored switch entities."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if new_state is None or old_state is None:
            return

        new_val = new_state.state
        old_val = old_state.state

        _LOGGER.debug(
            "_async_switch_state_changed :: %s: %s -> %s (pending=%s)",
            entity_id, old_val, new_val,
            self._pending_switch.get(entity_id, 0),
        )

        # Echo filtering: if this switch has pending echoes, decrement and skip
        if self._pending_switch.get(entity_id, 0) > 0:
            self._pending_switch[entity_id] -= 1
            if self._pending_switch[entity_id] <= 0:
                del self._pending_switch[entity_id]
                # Cancel the safety timeout
                timer = self._pending_switch_timers.pop(entity_id, None)
                if timer:
                    timer()
            _LOGGER.debug(
                "_async_switch_state_changed :: echo filtered, remaining=%s",
                self._pending_switch.get(entity_id, 0),
            )
            return

        # External state change detected — handle per mode
        self._triggered_externally = True
        try:
            if self._input_mode == INPUT_MODE_SWITCH:
                await self._handle_switch_mode_state_change(entity_id, old_val, new_val)
            elif self._input_mode in (INPUT_MODE_PULSE, INPUT_MODE_TOGGLE):
                await self._handle_pulse_toggle_state_change(entity_id, old_val, new_val)
        finally:
            self._triggered_externally = False
```

**Step 2: Add switch mode handler**

```python

    async def _handle_switch_mode_state_change(self, entity_id, old_val, new_val):
        """Handle external state change in switch (latching) mode."""
        if entity_id == self._open_switch_entity_id:
            if new_val == "on":
                _LOGGER.debug("_handle_switch_mode_state_change :: external open detected")
                await self.async_open_cover()
            elif new_val == "off":
                _LOGGER.debug("_handle_switch_mode_state_change :: external open-stop detected")
                await self.async_stop_cover()
        elif entity_id == self._close_switch_entity_id:
            if new_val == "on":
                _LOGGER.debug("_handle_switch_mode_state_change :: external close detected")
                await self.async_close_cover()
            elif new_val == "off":
                _LOGGER.debug("_handle_switch_mode_state_change :: external close-stop detected")
                await self.async_stop_cover()
        elif entity_id == self._stop_switch_entity_id:
            if new_val == "on":
                _LOGGER.debug("_handle_switch_mode_state_change :: external stop detected")
                await self.async_stop_cover()
```

**Step 3: Add pulse/toggle mode handler**

```python

    async def _handle_pulse_toggle_state_change(self, entity_id, old_val, new_val):
        """Handle external state change in pulse or toggle mode.

        In pulse/toggle mode, a physical press produces ON->OFF.
        We react on the OFF transition (pulse complete).
        """
        if old_val != "on" or new_val != "off":
            return

        if entity_id == self._open_switch_entity_id:
            _LOGGER.debug("_handle_pulse_toggle_state_change :: external open pulse detected")
            await self.async_open_cover()
        elif entity_id == self._close_switch_entity_id:
            _LOGGER.debug("_handle_pulse_toggle_state_change :: external close pulse detected")
            await self.async_close_cover()
        elif entity_id == self._stop_switch_entity_id:
            _LOGGER.debug("_handle_pulse_toggle_state_change :: external stop pulse detected")
            await self.async_stop_cover()
```

Note: In toggle mode, `async_open_cover` and `async_close_cover` already handle the "already traveling same direction = stop" and "traveling opposite = stop first" logic, so this works correctly.

**Step 4: Commit**

```bash
git add custom_components/cover_time_based/cover.py
git commit -m "feat(state-monitoring): implement state change handler with mode-specific logic"
```

---

### Task 6: Add `async_call_later` import and verify

**Files:**
- Modify: `custom_components/cover_time_based/cover.py:28-30` (imports)

**Step 1: Add `async_call_later` to the event import**

```python
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
```

**Step 2: Verify the full file has no syntax errors**

Deploy to HA and check logs:
```bash
rm -Rf /workspaces/homeassistant-core/config/custom_components/cover_time_based && cp -r /workspaces/ha-cover-time-based/custom_components/cover_time_based /workspaces/homeassistant-core/config/custom_components/
```

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/cover.py
git commit -m "feat(state-monitoring): add async_call_later import"
```

---

### Task 7: Deploy and manual test

**Step 1: Deploy to HA**
```bash
rm -Rf /workspaces/homeassistant-core/config/custom_components/cover_time_based && cp -r /workspaces/ha-cover-time-based/custom_components/cover_time_based /workspaces/homeassistant-core/config/custom_components/
```

**Step 2: Restart HA and test**
- Open cover via HA UI → verify travel calc works, switches toggle, no double-trigger from echo
- Press physical button → verify travel calc starts tracking, cover shows as opening/closing in HA
- Press physical button again while moving → verify cover stops and travel calc stops
- Check HA logs for `_async_switch_state_changed` debug messages
- Verify echo filtering: HA-initiated commands should show "echo filtered" in logs
- Verify external events: physical button presses should show "external open/close detected"
