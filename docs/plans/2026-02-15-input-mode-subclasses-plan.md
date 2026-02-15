# Input Mode Subclasses Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the monolithic `CoverTimeBased` class (~1400 lines) into a class hierarchy split by device type and input mode, with each subclass in its own file.

**Architecture:** Two-level inheritance — device type first (wrapped cover vs switch-based), then input mode (switch/pulse/toggle). Abstract `_send_open`/`_send_close`/`_send_stop` methods replace the monolithic `_async_handle_command`. "Stop before direction change" moves to the base class for all modes; "same direction = stop" stays toggle-only.

**Tech Stack:** Python, Home Assistant CoverEntity/RestoreEntity, xknx TravelCalculator, pytest with unittest.mock

**Important:** Do NOT use `ruff format` — only `ruff check --fix`.

---

## Task 1: Set Up Test Infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_relay_commands.py`

**Step 1: Create test directory and conftest**

```python
# tests/__init__.py
# (empty)
```

```python
# tests/conftest.py
"""Shared test fixtures for cover_time_based tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.cover_time_based.cover import (
    CoverTimeBased,
    CONF_DEVICE_TYPE,
    CONF_INPUT_MODE,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_COVER_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_TRAVELLING_TIME_DOWN,
    CONF_TRAVELLING_TIME_UP,
    DEFAULT_PULSE_TIME,
    DEFAULT_TRAVEL_TIME,
    DEVICE_TYPE_COVER,
    DEVICE_TYPE_SWITCH,
    INPUT_MODE_PULSE,
    INPUT_MODE_SWITCH,
    INPUT_MODE_TOGGLE,
)


def make_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.async_create_task = lambda coro: asyncio.ensure_future(coro)
    return hass


import asyncio


def make_cover(
    input_mode=INPUT_MODE_SWITCH,
    cover_entity_id=None,
    open_switch="switch.open",
    close_switch="switch.close",
    stop_switch=None,
    pulse_time=DEFAULT_PULSE_TIME,
    travel_time_down=DEFAULT_TRAVEL_TIME,
    travel_time_up=DEFAULT_TRAVEL_TIME,
):
    """Create a CoverTimeBased instance for testing."""
    return CoverTimeBased(
        device_id="test_cover",
        name="Test Cover",
        travel_moves_with_tilt=False,
        travel_time_down=travel_time_down,
        travel_time_up=travel_time_up,
        tilt_time_down=None,
        tilt_time_up=None,
        travel_delay_at_end=None,
        min_movement_time=None,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        open_switch_entity_id=open_switch if cover_entity_id is None else None,
        close_switch_entity_id=close_switch if cover_entity_id is None else None,
        stop_switch_entity_id=stop_switch if cover_entity_id is None else None,
        input_mode=input_mode,
        pulse_time=pulse_time,
        cover_entity_id=cover_entity_id,
    )
```

**Step 2: Write characterization tests for relay commands**

```python
# tests/test_relay_commands.py
"""Characterization tests for _async_handle_command relay behavior.

These tests capture the existing behavior of each input mode
so we can verify the refactor doesn't change anything.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER, SERVICE_STOP_COVER

from tests.conftest import make_cover, make_hass


@pytest.fixture
def hass():
    return make_hass()


# --- Switch Mode (latching relays) ---

class TestSwitchModeRelays:
    """Switch mode: relays stay on/off until explicitly changed."""

    @pytest.mark.asyncio
    async def test_close_turns_off_open_turns_on_close(self, hass):
        cover = make_cover(input_mode="switch")
        cover.hass = hass
        await cover._async_handle_command(SERVICE_CLOSE_COVER)
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_off", {"entity_id": "switch.open"}, False) in calls
        assert call("homeassistant", "turn_on", {"entity_id": "switch.close"}, False) in calls

    @pytest.mark.asyncio
    async def test_open_turns_off_close_turns_on_open(self, hass):
        cover = make_cover(input_mode="switch")
        cover.hass = hass
        await cover._async_handle_command(SERVICE_OPEN_COVER)
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_off", {"entity_id": "switch.close"}, False) in calls
        assert call("homeassistant", "turn_on", {"entity_id": "switch.open"}, False) in calls

    @pytest.mark.asyncio
    async def test_stop_turns_off_both(self, hass):
        cover = make_cover(input_mode="switch")
        cover.hass = hass
        await cover._async_handle_command(SERVICE_STOP_COVER)
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_off", {"entity_id": "switch.close"}, False) in calls
        assert call("homeassistant", "turn_off", {"entity_id": "switch.open"}, False) in calls

    @pytest.mark.asyncio
    async def test_stop_with_stop_switch_turns_it_on(self, hass):
        cover = make_cover(input_mode="switch", stop_switch="switch.stop")
        cover.hass = hass
        await cover._async_handle_command(SERVICE_STOP_COVER)
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_on", {"entity_id": "switch.stop"}, False) in calls

    @pytest.mark.asyncio
    async def test_close_with_stop_switch_turns_it_off(self, hass):
        cover = make_cover(input_mode="switch", stop_switch="switch.stop")
        cover.hass = hass
        await cover._async_handle_command(SERVICE_CLOSE_COVER)
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_off", {"entity_id": "switch.stop"}, False) in calls


# --- Pulse Mode (momentary press) ---

class TestPulseModeRelays:
    """Pulse mode: press button briefly, then release."""

    @pytest.mark.asyncio
    async def test_close_pulses_close_switch(self, hass):
        cover = make_cover(input_mode="pulse", pulse_time=0.01)
        cover.hass = hass
        await cover._async_handle_command(SERVICE_CLOSE_COVER)
        calls = hass.services.async_call.call_args_list
        # Should turn on close, then turn it off after pulse
        assert call("homeassistant", "turn_on", {"entity_id": "switch.close"}, False) in calls
        assert call("homeassistant", "turn_off", {"entity_id": "switch.close"}, False) in calls

    @pytest.mark.asyncio
    async def test_open_pulses_open_switch(self, hass):
        cover = make_cover(input_mode="pulse", pulse_time=0.01)
        cover.hass = hass
        await cover._async_handle_command(SERVICE_OPEN_COVER)
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_on", {"entity_id": "switch.open"}, False) in calls
        assert call("homeassistant", "turn_off", {"entity_id": "switch.open"}, False) in calls

    @pytest.mark.asyncio
    async def test_stop_with_stop_switch_pulses_it(self, hass):
        cover = make_cover(input_mode="pulse", stop_switch="switch.stop", pulse_time=0.01)
        cover.hass = hass
        await cover._async_handle_command(SERVICE_STOP_COVER)
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_on", {"entity_id": "switch.stop"}, False) in calls
        assert call("homeassistant", "turn_off", {"entity_id": "switch.stop"}, False) in calls


# --- Toggle Mode (same button starts and stops) ---

class TestToggleModeRelays:
    """Toggle mode: press direction button to start, press again to stop."""

    @pytest.mark.asyncio
    async def test_close_pulses_close_switch(self, hass):
        cover = make_cover(input_mode="toggle", pulse_time=0.01)
        cover.hass = hass
        await cover._async_handle_command(SERVICE_CLOSE_COVER)
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_on", {"entity_id": "switch.close"}, False) in calls
        assert call("homeassistant", "turn_off", {"entity_id": "switch.close"}, False) in calls

    @pytest.mark.asyncio
    async def test_stop_after_close_pulses_close_switch(self, hass):
        """In toggle mode, stop re-presses the last direction button."""
        cover = make_cover(input_mode="toggle", pulse_time=0.01)
        cover.hass = hass
        cover._last_command = SERVICE_CLOSE_COVER
        await cover._async_handle_command(SERVICE_STOP_COVER)
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_on", {"entity_id": "switch.close"}, False) in calls
        assert call("homeassistant", "turn_off", {"entity_id": "switch.close"}, False) in calls

    @pytest.mark.asyncio
    async def test_stop_after_open_pulses_open_switch(self, hass):
        cover = make_cover(input_mode="toggle", pulse_time=0.01)
        cover.hass = hass
        cover._last_command = SERVICE_OPEN_COVER
        await cover._async_handle_command(SERVICE_STOP_COVER)
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_on", {"entity_id": "switch.open"}, False) in calls
        assert call("homeassistant", "turn_off", {"entity_id": "switch.open"}, False) in calls

    @pytest.mark.asyncio
    async def test_stop_with_no_last_command_does_nothing(self, hass):
        cover = make_cover(input_mode="toggle", pulse_time=0.01)
        cover.hass = hass
        cover._last_command = None
        await cover._async_handle_command(SERVICE_STOP_COVER)
        hass.services.async_call.assert_not_called()


# --- Wrapped Cover Mode ---

class TestWrappedCoverRelays:
    """Wrapped cover: delegates to underlying cover entity."""

    @pytest.mark.asyncio
    async def test_close_calls_cover_close(self, hass):
        cover = make_cover(cover_entity_id="cover.bedroom")
        cover.hass = hass
        await cover._async_handle_command(SERVICE_CLOSE_COVER)
        hass.services.async_call.assert_called_with(
            "cover", "close_cover", {"entity_id": "cover.bedroom"}, False
        )

    @pytest.mark.asyncio
    async def test_open_calls_cover_open(self, hass):
        cover = make_cover(cover_entity_id="cover.bedroom")
        cover.hass = hass
        await cover._async_handle_command(SERVICE_OPEN_COVER)
        hass.services.async_call.assert_called_with(
            "cover", "open_cover", {"entity_id": "cover.bedroom"}, False
        )

    @pytest.mark.asyncio
    async def test_stop_calls_cover_stop(self, hass):
        cover = make_cover(cover_entity_id="cover.bedroom")
        cover.hass = hass
        await cover._async_handle_command(SERVICE_STOP_COVER)
        hass.services.async_call.assert_called_with(
            "cover", "stop_cover", {"entity_id": "cover.bedroom"}, False
        )
```

**Step 3: Run tests to verify they pass against current code**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_relay_commands.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/
git commit -m "test: add characterization tests for relay command behavior"
```

---

## Task 2: Write Toggle Behavior Tests

**Files:**
- Create: `tests/test_toggle_behavior.py`

**Step 1: Write tests for toggle-specific behavior**

```python
# tests/test_toggle_behavior.py
"""Characterization tests for toggle-specific open/close/stop behavior."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER, SERVICE_STOP_COVER

from tests.conftest import make_cover, make_hass


@pytest.fixture
def hass():
    return make_hass()


class TestToggleCloseWhileMoving:
    """Toggle mode: close while already closing = stop."""

    @pytest.mark.asyncio
    async def test_close_while_closing_stops(self, hass):
        cover = make_cover(input_mode="toggle", pulse_time=0.01)
        cover.hass = hass
        # Simulate cover currently closing
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER

        with patch.object(cover, "async_stop_cover", new_callable=AsyncMock) as mock_stop:
            await cover.async_close_cover()
            mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_open_while_opening_stops(self, hass):
        cover = make_cover(input_mode="toggle", pulse_time=0.01)
        cover.hass = hass
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_stop_cover", new_callable=AsyncMock) as mock_stop:
            await cover.async_open_cover()
            mock_stop.assert_called_once()


class TestToggleStopGuard:
    """Toggle mode: stop only sends relay command if something was active."""

    @pytest.mark.asyncio
    async def test_stop_when_idle_no_relay_command(self, hass):
        """Toggle mode: calling stop when idle should NOT send relay command."""
        cover = make_cover(input_mode="toggle", pulse_time=0.01)
        cover.hass = hass
        # Nothing active — idle state
        await cover.async_stop_cover()
        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_switch_mode_stop_when_idle_sends_relay_command(self, hass):
        """Switch mode: calling stop when idle SHOULD send relay command."""
        cover = make_cover(input_mode="switch")
        cover.hass = hass
        await cover.async_stop_cover()
        assert hass.services.async_call.called


class TestStopBeforeDirectionChange:
    """All modes: stop before reversing direction (new base class behavior)."""

    @pytest.mark.asyncio
    async def test_close_while_opening_stops_first_toggle(self, hass):
        cover = make_cover(input_mode="toggle", pulse_time=0.01)
        cover.hass = hass
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER

        with patch.object(cover, "async_stop_cover", new_callable=AsyncMock) as mock_stop:
            await cover.async_close_cover()
            mock_stop.assert_called_once()
```

**Step 2: Run tests**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_toggle_behavior.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_toggle_behavior.py
git commit -m "test: add characterization tests for toggle-specific behavior"
```

---

## Task 3: Extract Base Class to cover_base.py

**Files:**
- Create: `custom_components/cover_time_based/cover_base.py`
- Modify: `custom_components/cover_time_based/cover.py`

**Step 1: Create cover_base.py**

Move the `CoverTimeBased` class from `cover.py` to `cover_base.py`. Add abstract `_send_open`, `_send_close`, `_send_stop` methods. Refactor `_async_handle_command` to dispatch to them.

Key changes to `_async_handle_command`:
```python
async def _async_handle_command(self, command, *args):
    if command == SERVICE_CLOSE_COVER:
        self._state = False
        await self._send_close()
    elif command == SERVICE_OPEN_COVER:
        self._state = True
        await self._send_open()
    elif command == SERVICE_STOP_COVER:
        self._state = True
        await self._send_stop()
    _LOGGER.debug("_async_handle_command :: %s", command)
    self.async_write_ha_state()
```

Abstract methods added:
```python
from abc import abstractmethod

@abstractmethod
async def _send_open(self) -> None:
    """Send the open command to the underlying device."""

@abstractmethod
async def _send_close(self) -> None:
    """Send the close command to the underlying device."""

@abstractmethod
async def _send_stop(self) -> None:
    """Send the stop command to the underlying device."""
```

The base class keeps ALL existing logic: position tracking, tilt, auto-updater, delayed stops, startup delays, toggle guards in async_close_cover/async_open_cover/async_stop_cover. Constants, schemas, and YAML functions stay in `cover.py`.

**Step 2: Update cover.py**

Remove the class body from cover.py. Import `CoverTimeBased` from `cover_base`. Keep constants, schemas, `devices_from_config`, `async_setup_platform`, `async_setup_entry` in cover.py. The `CoverTimeBased` import from cover_base needs to be re-exported for backward compat.

**Step 3: Run tests**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/ -v`
Expected: Tests fail because CoverTimeBased is now abstract (can't instantiate directly)

**Step 4: Create a concrete test subclass in conftest**

Update `tests/conftest.py` to create a concrete subclass for testing that implements the abstract methods with the current behavior:

```python
class ConcreteTestCover(CoverTimeBased):
    """Concrete subclass for testing — reimplements original _async_handle_command relay logic."""

    async def _send_open(self):
        if self._cover_entity_id is not None:
            await self.hass.services.async_call("cover", "open_cover", {"entity_id": self._cover_entity_id}, False)
        else:
            await self.hass.services.async_call("homeassistant", "turn_off", {"entity_id": self._close_switch_entity_id}, False)
            await self.hass.services.async_call("homeassistant", "turn_on", {"entity_id": self._open_switch_entity_id}, False)
            if self._stop_switch_entity_id:
                await self.hass.services.async_call("homeassistant", "turn_off", {"entity_id": self._stop_switch_entity_id}, False)
            if self._input_mode in ("pulse", "toggle"):
                await asyncio.sleep(self._pulse_time)
                await self.hass.services.async_call("homeassistant", "turn_off", {"entity_id": self._open_switch_entity_id}, False)

    async def _send_close(self):
        # Mirror of original close logic
        ...

    async def _send_stop(self):
        # Mirror of original stop logic
        ...
```

Update `make_cover` to return `ConcreteTestCover` instead of `CoverTimeBased`.

**Step 5: Run tests again**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add custom_components/cover_time_based/cover_base.py custom_components/cover_time_based/cover.py tests/conftest.py
git commit -m "refactor: extract CoverTimeBased base class with abstract relay methods"
```

---

## Task 4: Create WrappedCoverTimeBased

**Files:**
- Create: `custom_components/cover_time_based/cover_wrapped.py`
- Create: `tests/test_cover_wrapped.py`

**Step 1: Write failing tests**

```python
# tests/test_cover_wrapped.py
"""Tests for WrappedCoverTimeBased."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.cover_time_based.cover_wrapped import WrappedCoverTimeBased


@pytest.fixture
def hass():
    from tests.conftest import make_hass
    return make_hass()


def make_wrapped_cover(cover_entity_id="cover.bedroom"):
    return WrappedCoverTimeBased(
        device_id="test_wrapped",
        name="Test Wrapped",
        travel_moves_with_tilt=False,
        travel_time_down=30,
        travel_time_up=30,
        tilt_time_down=None,
        tilt_time_up=None,
        travel_delay_at_end=None,
        min_movement_time=None,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        cover_entity_id=cover_entity_id,
    )


class TestWrappedCover:
    @pytest.mark.asyncio
    async def test_send_close_delegates(self, hass):
        cover = make_wrapped_cover()
        cover.hass = hass
        await cover._send_close()
        hass.services.async_call.assert_called_with(
            "cover", "close_cover", {"entity_id": "cover.bedroom"}, False
        )

    @pytest.mark.asyncio
    async def test_send_open_delegates(self, hass):
        cover = make_wrapped_cover()
        cover.hass = hass
        await cover._send_open()
        hass.services.async_call.assert_called_with(
            "cover", "open_cover", {"entity_id": "cover.bedroom"}, False
        )

    @pytest.mark.asyncio
    async def test_send_stop_delegates(self, hass):
        cover = make_wrapped_cover()
        cover.hass = hass
        await cover._send_stop()
        hass.services.async_call.assert_called_with(
            "cover", "stop_cover", {"entity_id": "cover.bedroom"}, False
        )
```

**Step 2: Run tests to verify they fail**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_cover_wrapped.py -v`
Expected: FAIL — `cover_wrapped` module doesn't exist

**Step 3: Implement WrappedCoverTimeBased**

```python
# custom_components/cover_time_based/cover_wrapped.py
"""Wrapped cover — delegates open/close/stop to an underlying cover entity."""

from .cover_base import CoverTimeBased


class WrappedCoverTimeBased(CoverTimeBased):
    """Cover that wraps an existing cover entity with time-based positioning."""

    def __init__(
        self,
        device_id,
        name,
        travel_moves_with_tilt,
        travel_time_down,
        travel_time_up,
        tilt_time_down,
        tilt_time_up,
        travel_delay_at_end,
        min_movement_time,
        travel_startup_delay,
        tilt_startup_delay,
        cover_entity_id,
    ):
        super().__init__(
            device_id=device_id,
            name=name,
            travel_moves_with_tilt=travel_moves_with_tilt,
            travel_time_down=travel_time_down,
            travel_time_up=travel_time_up,
            tilt_time_down=tilt_time_down,
            tilt_time_up=tilt_time_up,
            travel_delay_at_end=travel_delay_at_end,
            min_movement_time=min_movement_time,
            travel_startup_delay=travel_startup_delay,
            tilt_startup_delay=tilt_startup_delay,
        )
        self._cover_entity_id = cover_entity_id

    async def _send_open(self) -> None:
        await self.hass.services.async_call(
            "cover", "open_cover", {"entity_id": self._cover_entity_id}, False
        )

    async def _send_close(self) -> None:
        await self.hass.services.async_call(
            "cover", "close_cover", {"entity_id": self._cover_entity_id}, False
        )

    async def _send_stop(self) -> None:
        await self.hass.services.async_call(
            "cover", "stop_cover", {"entity_id": self._cover_entity_id}, False
        )
```

Note: The base class constructor signature must be updated to remove switch/toggle-specific params. The base class should only accept the common timing/position params. Switch entity IDs, input_mode, pulse_time, and cover_entity_id move to their respective subclasses.

**Step 4: Run tests**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_cover_wrapped.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/cover_time_based/cover_wrapped.py tests/test_cover_wrapped.py
git commit -m "feat: add WrappedCoverTimeBased subclass"
```

---

## Task 5: Create SwitchCoverTimeBased (Abstract Mid-Level)

**Files:**
- Create: `custom_components/cover_time_based/cover_switch.py`

**Step 1: Implement SwitchCoverTimeBased**

```python
# custom_components/cover_time_based/cover_switch.py
"""Abstract base for switch-controlled covers."""

from .cover_base import CoverTimeBased


class SwitchCoverTimeBased(CoverTimeBased):
    """Abstract base for covers controlled via switch entities."""

    def __init__(
        self,
        device_id,
        name,
        travel_moves_with_tilt,
        travel_time_down,
        travel_time_up,
        tilt_time_down,
        tilt_time_up,
        travel_delay_at_end,
        min_movement_time,
        travel_startup_delay,
        tilt_startup_delay,
        open_switch_entity_id,
        close_switch_entity_id,
        stop_switch_entity_id,
    ):
        super().__init__(
            device_id=device_id,
            name=name,
            travel_moves_with_tilt=travel_moves_with_tilt,
            travel_time_down=travel_time_down,
            travel_time_up=travel_time_up,
            tilt_time_down=tilt_time_down,
            tilt_time_up=tilt_time_up,
            travel_delay_at_end=travel_delay_at_end,
            min_movement_time=min_movement_time,
            travel_startup_delay=travel_startup_delay,
            tilt_startup_delay=tilt_startup_delay,
        )
        self._open_switch_entity_id = open_switch_entity_id
        self._close_switch_entity_id = close_switch_entity_id
        self._stop_switch_entity_id = stop_switch_entity_id
```

This is still abstract — `_send_open`/`_send_close`/`_send_stop` are not implemented.

**Step 2: Commit**

```bash
git add custom_components/cover_time_based/cover_switch.py
git commit -m "refactor: add SwitchCoverTimeBased abstract mid-level class"
```

---

## Task 6: Create SwitchModeCover

**Files:**
- Create: `custom_components/cover_time_based/cover_switch_mode.py`
- Create: `tests/test_cover_switch_mode.py`

**Step 1: Write failing tests**

```python
# tests/test_cover_switch_mode.py
"""Tests for SwitchModeCover — latching relay behavior."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from custom_components.cover_time_based.cover_switch_mode import SwitchModeCover
from tests.conftest import make_hass


def make_switch_cover(stop_switch=None):
    return SwitchModeCover(
        device_id="test_switch",
        name="Test Switch",
        travel_moves_with_tilt=False,
        travel_time_down=30,
        travel_time_up=30,
        tilt_time_down=None,
        tilt_time_up=None,
        travel_delay_at_end=None,
        min_movement_time=None,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        open_switch_entity_id="switch.open",
        close_switch_entity_id="switch.close",
        stop_switch_entity_id=stop_switch,
    )


@pytest.fixture
def hass():
    return make_hass()


class TestSwitchModeCover:
    @pytest.mark.asyncio
    async def test_send_close(self, hass):
        cover = make_switch_cover()
        cover.hass = hass
        await cover._send_close()
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_off", {"entity_id": "switch.open"}, False) in calls
        assert call("homeassistant", "turn_on", {"entity_id": "switch.close"}, False) in calls

    @pytest.mark.asyncio
    async def test_send_open(self, hass):
        cover = make_switch_cover()
        cover.hass = hass
        await cover._send_open()
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_off", {"entity_id": "switch.close"}, False) in calls
        assert call("homeassistant", "turn_on", {"entity_id": "switch.open"}, False) in calls

    @pytest.mark.asyncio
    async def test_send_stop_no_stop_switch(self, hass):
        cover = make_switch_cover()
        cover.hass = hass
        await cover._send_stop()
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_off", {"entity_id": "switch.close"}, False) in calls
        assert call("homeassistant", "turn_off", {"entity_id": "switch.open"}, False) in calls
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_send_stop_with_stop_switch(self, hass):
        cover = make_switch_cover(stop_switch="switch.stop")
        cover.hass = hass
        await cover._send_stop()
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_on", {"entity_id": "switch.stop"}, False) in calls
```

**Step 2: Run tests to verify they fail**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_cover_switch_mode.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement SwitchModeCover**

```python
# custom_components/cover_time_based/cover_switch_mode.py
"""Switch mode cover — latching relays stay on/off."""

from .cover_switch import SwitchCoverTimeBased


class SwitchModeCover(SwitchCoverTimeBased):
    """Cover controlled via latching relays (switch mode)."""

    async def _send_open(self) -> None:
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._close_switch_entity_id}, False
        )
        await self.hass.services.async_call(
            "homeassistant", "turn_on", {"entity_id": self._open_switch_entity_id}, False
        )
        if self._stop_switch_entity_id is not None:
            await self.hass.services.async_call(
                "homeassistant", "turn_off", {"entity_id": self._stop_switch_entity_id}, False
            )

    async def _send_close(self) -> None:
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._open_switch_entity_id}, False
        )
        await self.hass.services.async_call(
            "homeassistant", "turn_on", {"entity_id": self._close_switch_entity_id}, False
        )
        if self._stop_switch_entity_id is not None:
            await self.hass.services.async_call(
                "homeassistant", "turn_off", {"entity_id": self._stop_switch_entity_id}, False
            )

    async def _send_stop(self) -> None:
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._close_switch_entity_id}, False
        )
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._open_switch_entity_id}, False
        )
        if self._stop_switch_entity_id is not None:
            await self.hass.services.async_call(
                "homeassistant", "turn_on", {"entity_id": self._stop_switch_entity_id}, False
            )
```

**Step 4: Run tests**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_cover_switch_mode.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/cover_time_based/cover_switch_mode.py tests/test_cover_switch_mode.py
git commit -m "feat: add SwitchModeCover subclass for latching relays"
```

---

## Task 7: Create PulseModeCover

**Files:**
- Create: `custom_components/cover_time_based/cover_pulse_mode.py`
- Create: `tests/test_cover_pulse_mode.py`

**Step 1: Write failing tests**

```python
# tests/test_cover_pulse_mode.py
"""Tests for PulseModeCover — momentary pulse behavior."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from custom_components.cover_time_based.cover_pulse_mode import PulseModeCover
from tests.conftest import make_hass


def make_pulse_cover(stop_switch=None, pulse_time=0.01):
    return PulseModeCover(
        device_id="test_pulse",
        name="Test Pulse",
        travel_moves_with_tilt=False,
        travel_time_down=30,
        travel_time_up=30,
        tilt_time_down=None,
        tilt_time_up=None,
        travel_delay_at_end=None,
        min_movement_time=None,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        open_switch_entity_id="switch.open",
        close_switch_entity_id="switch.close",
        stop_switch_entity_id=stop_switch,
        pulse_time=pulse_time,
    )


@pytest.fixture
def hass():
    return make_hass()


class TestPulseModeCover:
    @pytest.mark.asyncio
    async def test_send_close_pulses(self, hass):
        cover = make_pulse_cover()
        cover.hass = hass
        await cover._send_close()
        calls = hass.services.async_call.call_args_list
        # Turn on close, then turn off close (after pulse)
        assert call("homeassistant", "turn_on", {"entity_id": "switch.close"}, False) in calls
        assert call("homeassistant", "turn_off", {"entity_id": "switch.close"}, False) in calls

    @pytest.mark.asyncio
    async def test_send_open_pulses(self, hass):
        cover = make_pulse_cover()
        cover.hass = hass
        await cover._send_open()
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_on", {"entity_id": "switch.open"}, False) in calls
        assert call("homeassistant", "turn_off", {"entity_id": "switch.open"}, False) in calls

    @pytest.mark.asyncio
    async def test_send_stop_with_stop_switch_pulses(self, hass):
        cover = make_pulse_cover(stop_switch="switch.stop")
        cover.hass = hass
        await cover._send_stop()
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_on", {"entity_id": "switch.stop"}, False) in calls
        assert call("homeassistant", "turn_off", {"entity_id": "switch.stop"}, False) in calls

    @pytest.mark.asyncio
    async def test_send_stop_without_stop_switch(self, hass):
        """Without stop switch, stop just turns off both direction switches."""
        cover = make_pulse_cover()
        cover.hass = hass
        await cover._send_stop()
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_off", {"entity_id": "switch.close"}, False) in calls
        assert call("homeassistant", "turn_off", {"entity_id": "switch.open"}, False) in calls
```

**Step 2: Run tests to verify they fail**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_cover_pulse_mode.py -v`
Expected: FAIL

**Step 3: Implement PulseModeCover**

```python
# custom_components/cover_time_based/cover_pulse_mode.py
"""Pulse mode cover — momentary button press with separate stop."""

from asyncio import sleep

from .cover_switch import SwitchCoverTimeBased


class PulseModeCover(SwitchCoverTimeBased):
    """Cover controlled via momentary pulse buttons."""

    def __init__(self, *, pulse_time, **kwargs):
        super().__init__(**kwargs)
        self._pulse_time = pulse_time

    async def _send_open(self) -> None:
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._close_switch_entity_id}, False
        )
        await self.hass.services.async_call(
            "homeassistant", "turn_on", {"entity_id": self._open_switch_entity_id}, False
        )
        if self._stop_switch_entity_id is not None:
            await self.hass.services.async_call(
                "homeassistant", "turn_off", {"entity_id": self._stop_switch_entity_id}, False
            )
        await sleep(self._pulse_time)
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._open_switch_entity_id}, False
        )

    async def _send_close(self) -> None:
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._open_switch_entity_id}, False
        )
        await self.hass.services.async_call(
            "homeassistant", "turn_on", {"entity_id": self._close_switch_entity_id}, False
        )
        if self._stop_switch_entity_id is not None:
            await self.hass.services.async_call(
                "homeassistant", "turn_off", {"entity_id": self._stop_switch_entity_id}, False
            )
        await sleep(self._pulse_time)
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._close_switch_entity_id}, False
        )

    async def _send_stop(self) -> None:
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._close_switch_entity_id}, False
        )
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._open_switch_entity_id}, False
        )
        if self._stop_switch_entity_id is not None:
            await self.hass.services.async_call(
                "homeassistant", "turn_on", {"entity_id": self._stop_switch_entity_id}, False
            )
            await sleep(self._pulse_time)
            await self.hass.services.async_call(
                "homeassistant", "turn_off", {"entity_id": self._stop_switch_entity_id}, False
            )
```

**Step 4: Run tests**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_cover_pulse_mode.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/cover_time_based/cover_pulse_mode.py tests/test_cover_pulse_mode.py
git commit -m "feat: add PulseModeCover subclass for momentary buttons"
```

---

## Task 8: Create ToggleModeCover

**Files:**
- Create: `custom_components/cover_time_based/cover_toggle_mode.py`
- Create: `tests/test_cover_toggle_mode.py`

**Step 1: Write failing tests**

```python
# tests/test_cover_toggle_mode.py
"""Tests for ToggleModeCover — same button starts and stops."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from custom_components.cover_time_based.cover_toggle_mode import ToggleModeCover
from tests.conftest import make_hass


def make_toggle_cover(pulse_time=0.01):
    return ToggleModeCover(
        device_id="test_toggle",
        name="Test Toggle",
        travel_moves_with_tilt=False,
        travel_time_down=30,
        travel_time_up=30,
        tilt_time_down=None,
        tilt_time_up=None,
        travel_delay_at_end=None,
        min_movement_time=None,
        travel_startup_delay=None,
        tilt_startup_delay=None,
        open_switch_entity_id="switch.open",
        close_switch_entity_id="switch.close",
        stop_switch_entity_id=None,
        pulse_time=pulse_time,
    )


@pytest.fixture
def hass():
    return make_hass()


class TestToggleModeRelays:
    @pytest.mark.asyncio
    async def test_send_close_pulses_close(self, hass):
        cover = make_toggle_cover()
        cover.hass = hass
        await cover._send_close()
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_on", {"entity_id": "switch.close"}, False) in calls
        assert call("homeassistant", "turn_off", {"entity_id": "switch.close"}, False) in calls

    @pytest.mark.asyncio
    async def test_send_stop_after_close_pulses_close(self, hass):
        cover = make_toggle_cover()
        cover.hass = hass
        cover._last_command = SERVICE_CLOSE_COVER
        await cover._send_stop()
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_on", {"entity_id": "switch.close"}, False) in calls

    @pytest.mark.asyncio
    async def test_send_stop_after_open_pulses_open(self, hass):
        cover = make_toggle_cover()
        cover.hass = hass
        cover._last_command = SERVICE_OPEN_COVER
        await cover._send_stop()
        calls = hass.services.async_call.call_args_list
        assert call("homeassistant", "turn_on", {"entity_id": "switch.open"}, False) in calls

    @pytest.mark.asyncio
    async def test_send_stop_no_last_command_does_nothing(self, hass):
        cover = make_toggle_cover()
        cover.hass = hass
        cover._last_command = None
        await cover._send_stop()
        hass.services.async_call.assert_not_called()


class TestToggleModeOverrides:
    """Toggle-specific: same direction while moving = stop."""

    @pytest.mark.asyncio
    async def test_close_while_closing_stops(self, hass):
        cover = make_toggle_cover()
        cover.hass = hass
        cover.travel_calc.start_travel_down()
        cover._last_command = SERVICE_CLOSE_COVER
        with patch.object(cover, "async_stop_cover", new_callable=AsyncMock) as mock_stop:
            await cover.async_close_cover()
            mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_open_while_opening_stops(self, hass):
        cover = make_toggle_cover()
        cover.hass = hass
        cover.travel_calc.start_travel_up()
        cover._last_command = SERVICE_OPEN_COVER
        with patch.object(cover, "async_stop_cover", new_callable=AsyncMock) as mock_stop:
            await cover.async_open_cover()
            mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_when_idle_no_relay(self, hass):
        """Toggle: stop when idle should NOT send relay command."""
        cover = make_toggle_cover()
        cover.hass = hass
        await cover.async_stop_cover()
        hass.services.async_call.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_cover_toggle_mode.py -v`
Expected: FAIL

**Step 3: Implement ToggleModeCover**

```python
# custom_components/cover_time_based/cover_toggle_mode.py
"""Toggle mode cover — same button starts and stops movement."""

import logging
from asyncio import sleep

from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER

from .cover_switch import SwitchCoverTimeBased

_LOGGER = logging.getLogger(__name__)


class ToggleModeCover(SwitchCoverTimeBased):
    """Cover where same button starts and stops movement."""

    def __init__(self, *, pulse_time, **kwargs):
        super().__init__(**kwargs)
        self._pulse_time = pulse_time

    async def _send_open(self) -> None:
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._close_switch_entity_id}, False
        )
        await self.hass.services.async_call(
            "homeassistant", "turn_on", {"entity_id": self._open_switch_entity_id}, False
        )
        if self._stop_switch_entity_id is not None:
            await self.hass.services.async_call(
                "homeassistant", "turn_off", {"entity_id": self._stop_switch_entity_id}, False
            )
        await sleep(self._pulse_time)
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._open_switch_entity_id}, False
        )

    async def _send_close(self) -> None:
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._open_switch_entity_id}, False
        )
        await self.hass.services.async_call(
            "homeassistant", "turn_on", {"entity_id": self._close_switch_entity_id}, False
        )
        if self._stop_switch_entity_id is not None:
            await self.hass.services.async_call(
                "homeassistant", "turn_off", {"entity_id": self._stop_switch_entity_id}, False
            )
        await sleep(self._pulse_time)
        await self.hass.services.async_call(
            "homeassistant", "turn_off", {"entity_id": self._close_switch_entity_id}, False
        )

    async def _send_stop(self) -> None:
        if self._last_command == SERVICE_CLOSE_COVER:
            await self.hass.services.async_call(
                "homeassistant", "turn_on", {"entity_id": self._close_switch_entity_id}, False
            )
            await sleep(self._pulse_time)
            await self.hass.services.async_call(
                "homeassistant", "turn_off", {"entity_id": self._close_switch_entity_id}, False
            )
        elif self._last_command == SERVICE_OPEN_COVER:
            await self.hass.services.async_call(
                "homeassistant", "turn_on", {"entity_id": self._open_switch_entity_id}, False
            )
            await sleep(self._pulse_time)
            await self.hass.services.async_call(
                "homeassistant", "turn_off", {"entity_id": self._open_switch_entity_id}, False
            )
        else:
            _LOGGER.debug("_send_stop :: toggle mode with no last command, skipping")

    async def async_close_cover(self, **kwargs):
        """Close: if already closing, treat as stop."""
        if self.is_closing:
            _LOGGER.debug("async_close_cover :: toggle mode, already closing, treating as stop")
            await self.async_stop_cover()
            return
        await super().async_close_cover(**kwargs)

    async def async_open_cover(self, **kwargs):
        """Open: if already opening, treat as stop."""
        if self.is_opening:
            _LOGGER.debug("async_open_cover :: toggle mode, already opening, treating as stop")
            await self.async_stop_cover()
            return
        await super().async_open_cover(**kwargs)

    async def async_stop_cover(self, **kwargs):
        """Stop: only send relay command if something was actually active."""
        was_active = (
            self.is_opening or self.is_closing
            or (self._startup_delay_task and not self._startup_delay_task.done())
            or (self._delay_task and not self._delay_task.done())
        )
        self._cancel_startup_delay_task()
        self._cancel_delay_task()
        self._handle_stop()
        self._enforce_tilt_constraints()
        if was_active:
            await self._send_stop()
        self.async_write_ha_state()
        self._last_command = None
```

**Step 4: Run tests**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/test_cover_toggle_mode.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/cover_time_based/cover_toggle_mode.py tests/test_cover_toggle_mode.py
git commit -m "feat: add ToggleModeCover subclass with same-direction-stops"
```

---

## Task 9: Update cover.py with Factory and Clean Up Base Class

**Files:**
- Modify: `custom_components/cover_time_based/cover.py`
- Modify: `custom_components/cover_time_based/cover_base.py`

**Step 1: Update cover.py**

Replace `async_setup_entry` to use the factory function. Replace `devices_from_config` to use the factory. Remove the old `CoverTimeBased` class (now in `cover_base.py`). Keep constants, schemas, YAML deprecation.

```python
# In cover.py, the factory function:
def _create_cover_from_options(options, hass_or_none=None, device_id="", name=""):
    """Create the appropriate cover subclass based on options."""
    from .cover_wrapped import WrappedCoverTimeBased
    from .cover_switch_mode import SwitchModeCover
    from .cover_pulse_mode import PulseModeCover
    from .cover_toggle_mode import ToggleModeCover

    device_type = options.get(CONF_DEVICE_TYPE, DEVICE_TYPE_SWITCH)

    common = dict(
        device_id=device_id,
        name=name,
        travel_moves_with_tilt=options.get(CONF_TRAVEL_MOVES_WITH_TILT, False),
        travel_time_down=options.get(CONF_TRAVELLING_TIME_DOWN, DEFAULT_TRAVEL_TIME),
        travel_time_up=options.get(CONF_TRAVELLING_TIME_UP, DEFAULT_TRAVEL_TIME),
        tilt_time_down=options.get(CONF_TILTING_TIME_DOWN),
        tilt_time_up=options.get(CONF_TILTING_TIME_UP),
        travel_delay_at_end=options.get(CONF_TRAVEL_DELAY_AT_END),
        min_movement_time=options.get(CONF_MIN_MOVEMENT_TIME),
        travel_startup_delay=options.get(CONF_TRAVEL_STARTUP_DELAY),
        tilt_startup_delay=options.get(CONF_TILT_STARTUP_DELAY),
    )

    if device_type == DEVICE_TYPE_COVER:
        return WrappedCoverTimeBased(
            cover_entity_id=options[CONF_COVER_ENTITY_ID],
            **common,
        )

    switch_args = dict(
        open_switch_entity_id=options[CONF_OPEN_SWITCH_ENTITY_ID],
        close_switch_entity_id=options[CONF_CLOSE_SWITCH_ENTITY_ID],
        stop_switch_entity_id=options.get(CONF_STOP_SWITCH_ENTITY_ID),
        **common,
    )

    input_mode = options.get(CONF_INPUT_MODE, INPUT_MODE_SWITCH)
    if input_mode == INPUT_MODE_PULSE:
        return PulseModeCover(
            pulse_time=options.get(CONF_PULSE_TIME, DEFAULT_PULSE_TIME),
            **switch_args,
        )
    elif input_mode == INPUT_MODE_TOGGLE:
        return ToggleModeCover(
            pulse_time=options.get(CONF_PULSE_TIME, DEFAULT_PULSE_TIME),
            **switch_args,
        )
    else:
        return SwitchModeCover(**switch_args)
```

Update `async_setup_entry`:
```python
async def async_setup_entry(hass, config_entry, async_add_entities):
    entity = _create_cover_from_options(
        config_entry.options,
        device_id=config_entry.entry_id,
        name=config_entry.title,
    )
    async_add_entities([entity])
    # ... register services
```

Update `devices_from_config` similarly to build an options dict and pass to factory.

**Step 2: Clean up base class**

Remove toggle/switch-specific code from `cover_base.py`:
- Remove `self._input_mode`, `self._pulse_time`, `self._cover_entity_id`, `self._open_switch_entity_id`, etc. from base constructor
- Remove toggle guard from `async_close_cover` and `async_open_cover` (toggle checks now in `ToggleModeCover`)
- Simplify `async_stop_cover` — always send stop, toggle override handles the guard
- Remove toggle guard from `set_known_position` and `set_known_tilt_position`

Base class `async_stop_cover` becomes:
```python
async def async_stop_cover(self, **kwargs):
    self._cancel_startup_delay_task()
    self._cancel_delay_task()
    self._handle_stop()
    self._enforce_tilt_constraints()
    await self._send_stop()
    self.async_write_ha_state()
    self._last_command = None
```

Base class `async_close_cover` — remove toggle block at top, add universal stop-before-direction-change:
```python
async def async_close_cover(self, **kwargs):
    _LOGGER.debug("async_close_cover")

    # Stop before direction change (all modes)
    if self.is_opening:
        _LOGGER.debug("async_close_cover :: currently opening, stopping first")
        await self.async_stop_cover()

    # ... rest of close logic unchanged
```

Same for `async_open_cover`:
```python
async def async_open_cover(self, **kwargs):
    _LOGGER.debug("async_open_cover")

    if self.is_closing:
        _LOGGER.debug("async_open_cover :: currently closing, stopping first")
        await self.async_stop_cover()

    # ... rest of open logic unchanged
```

**Step 3: Update conftest.py and characterization tests**

Update `tests/conftest.py` — remove the `ConcreteTestCover` monolith, update `make_cover` to use the factory or specific subclasses.

Update `tests/test_relay_commands.py` to use specific subclasses instead of the generic `_async_handle_command`. Tests should still pass with the same assertions.

**Step 4: Run all tests**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/ -v`
Expected: All PASS

**Step 5: Run ruff check**

Run: `cd /workspaces/ha-cover-time-based && ruff check .`
Expected: No errors (fix any that appear with `ruff check --fix .`)

**Step 6: Commit**

```bash
git add custom_components/cover_time_based/ tests/
git commit -m "refactor: wire up factory function and clean up base class

- Replace monolithic _async_handle_command with subclass _send_open/_send_close/_send_stop
- Move stop-before-direction-change to base class for all modes
- Move same-direction-stops to ToggleModeCover override
- Factory function creates correct subclass from options dict
- Both UI config and YAML use same factory path"
```

---

## Task 10: Update config_flow.py Imports

**Files:**
- Modify: `custom_components/cover_time_based/config_flow.py`

**Step 1: Update imports**

The config_flow currently imports constants from `cover.py`. Verify these still work after the refactor (constants should remain in `cover.py`). No code changes expected unless constants were moved.

**Step 2: Run ruff check**

Run: `cd /workspaces/ha-cover-time-based && ruff check .`

**Step 3: Run pyright**

Run: `cd /workspaces/ha-cover-time-based && npx pyright`
Fix any new type errors in the refactored code.

**Step 4: Run all tests one final time**

Run: `cd /workspaces/ha-cover-time-based && python -m pytest tests/ -v`
Expected: All PASS

**Step 5: Commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: resolve lint and type errors from refactor"
```

---

## Task 11: Deploy and Manual Test

**Step 1: Copy to HA**

Run: `rm -Rf /workspaces/homeassistant-core/config/custom_components/fado && cp -r /workspaces/ha-cover-time-based/custom_components/cover_time_based /workspaces/homeassistant-core/config/custom_components/`

Wait — this is the wrong copy command. The correct one for cover_time_based:

Run: `rm -Rf /workspaces/homeassistant-core/config/custom_components/cover_time_based && cp -r /workspaces/ha-cover-time-based/custom_components/cover_time_based /workspaces/homeassistant-core/config/custom_components/`

**Step 2: Restart HA and verify**

- Check HA logs for errors on startup
- Verify existing covers still work
- Test each mode: switch, pulse, toggle, wrapped cover
