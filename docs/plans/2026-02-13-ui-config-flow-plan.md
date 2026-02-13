# UI Config Flow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add UI-based configuration to cover_time_based using HA's config entry + subentry pattern, while keeping YAML backward compatibility.

**Architecture:** Single config entry holds integration-level defaults in `entry.options`. Each cover entity is a subentry with its own config in `subentry.data`. Values resolve: `subentry.data → entry.options → schema default`. YAML `async_setup_platform` remains unchanged.

**Tech Stack:** Home Assistant config entries, ConfigSubentryFlow, OptionsFlow, voluptuous selectors

**Constraints:** Do NOT use `ruff format` — only `ruff check`. Keep diffs to existing files minimal.

---

### Task 1: Update manifest.json

**Files:**
- Modify: `custom_components/cover_time_based/manifest.json`

**Step 1: Add config_flow to manifest**

Edit `manifest.json` to add `"config_flow": true`:

```json
{
  "domain": "cover_time_based",
  "name": "Cover Time Based",
  "codeowners": ["@Sese-Schneider"],
  "config_flow": true,
  "documentation": "https://github.com/Sese-Schneider/ha-cover-time-based",
  "integration_type": "helper",
  "iot_class": "calculated",
  "issue_tracker": "https://github.com/Sese-Schneider/ha-cover-time-based/issues",
  "requirements": [
    "xknx==3.11.0"
  ],
  "version": "3.0.0"
}
```

**Step 2: Commit**

```bash
git add custom_components/cover_time_based/manifest.json
git commit -m "feat: enable config flow in manifest"
```

---

### Task 2: Create __init__.py

**Files:**
- Create: `custom_components/cover_time_based/__init__.py`

**Step 1: Write __init__.py**

```python
"""Cover Time Based integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

PLATFORMS = ["cover"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cover Time Based from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)
```

**Step 2: Commit**

```bash
git add custom_components/cover_time_based/__init__.py
git commit -m "feat: add __init__.py for config entry support"
```

---

### Task 3: Create config_flow.py

**Files:**
- Create: `custom_components/cover_time_based/config_flow.py`

**Step 1: Write config_flow.py**

This file contains three flow handlers:
- `CoverTimeBasedConfigFlow` — creates the integration entry (trivial, no user input needed beyond confirmation)
- `CoverTimeBasedOptionsFlow` — edits integration-level defaults
- `CoverTimeBasedSubentryFlow` — adds/reconfigures individual cover entities

```python
"""Config flow for Cover Time Based integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .cover import (
    CONF_CLOSE_SWITCH_ENTITY_ID,
    CONF_COVER_ENTITY_ID,
    CONF_INPUT_MODE,
    CONF_MIN_MOVEMENT_TIME,
    CONF_OPEN_SWITCH_ENTITY_ID,
    CONF_PULSE_TIME,
    CONF_STOP_SWITCH_ENTITY_ID,
    CONF_TILT_STARTUP_DELAY,
    CONF_TILTING_TIME_DOWN,
    CONF_TILTING_TIME_UP,
    CONF_TRAVEL_DELAY_AT_END,
    CONF_TRAVEL_MOVES_WITH_TILT,
    CONF_TRAVEL_STARTUP_DELAY,
    CONF_TRAVELLING_TIME_DOWN,
    CONF_TRAVELLING_TIME_UP,
    DEFAULT_PULSE_TIME,
    DEFAULT_TRAVEL_TIME,
    DOMAIN,
    INPUT_MODE_PULSE,
    INPUT_MODE_SWITCH,
    INPUT_MODE_TOGGLE,
)

CONF_DEVICE_TYPE = "device_type"
DEVICE_TYPE_SWITCH = "switch"
DEVICE_TYPE_COVER = "cover"

SECTION_TRAVEL_TIMING = "travel_timing"
SECTION_ADVANCED = "advanced"

TIMING_NUMBER_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=600, step=0.1, mode=NumberSelectorMode.BOX)
)


def _travel_timing_schema() -> vol.Schema:
    """Return schema for travel timing section."""
    return vol.Schema(
        {
            vol.Optional(CONF_TRAVELLING_TIME_DOWN): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_TRAVELLING_TIME_UP): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_TILTING_TIME_DOWN): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_TILTING_TIME_UP): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_TRAVEL_MOVES_WITH_TILT): BooleanSelector(),
        }
    )


def _advanced_schema() -> vol.Schema:
    """Return schema for advanced section."""
    return vol.Schema(
        {
            vol.Optional(CONF_TRAVEL_STARTUP_DELAY): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_TILT_STARTUP_DELAY): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_MIN_MOVEMENT_TIME): TIMING_NUMBER_SELECTOR,
            vol.Optional(CONF_TRAVEL_DELAY_AT_END): TIMING_NUMBER_SELECTOR,
        }
    )


class CoverTimeBasedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cover Time Based."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step — just create the entry."""
        if user_input is not None:
            return self.async_create_entry(
                title="Cover Time Based",
                data={},
                options={
                    CONF_TRAVELLING_TIME_DOWN: DEFAULT_TRAVEL_TIME,
                    CONF_TRAVELLING_TIME_UP: DEFAULT_TRAVEL_TIME,
                    CONF_TRAVEL_MOVES_WITH_TILT: False,
                },
            )

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> CoverTimeBasedOptionsFlow:
        """Get the options flow for this handler."""
        return CoverTimeBasedOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {"cover": CoverTimeBasedSubentryFlow}


class CoverTimeBasedOptionsFlow(OptionsFlow):
    """Handle options flow for editing integration defaults."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the integration defaults."""
        if user_input is not None:
            # Merge section data into flat options dict
            options = {}
            travel = user_input.get(SECTION_TRAVEL_TIMING, {})
            advanced = user_input.get(SECTION_ADVANCED, {})
            options.update(travel)
            options.update(advanced)
            return self.async_create_entry(title="", data=options)

        # Build schema with current values as defaults
        current = dict(self.config_entry.options)

        schema = vol.Schema(
            {
                vol.Required(SECTION_TRAVEL_TIMING): section(
                    _travel_timing_schema(),
                    {"collapsed": False},
                ),
                vol.Required(SECTION_ADVANCED): section(
                    _advanced_schema(),
                    {"collapsed": True},
                ),
            }
        )

        # Build suggested values from current options
        suggested = {
            SECTION_TRAVEL_TIMING: {
                k: current[k]
                for k in (
                    CONF_TRAVELLING_TIME_DOWN,
                    CONF_TRAVELLING_TIME_UP,
                    CONF_TILTING_TIME_DOWN,
                    CONF_TILTING_TIME_UP,
                    CONF_TRAVEL_MOVES_WITH_TILT,
                )
                if k in current
            },
            SECTION_ADVANCED: {
                k: current[k]
                for k in (
                    CONF_TRAVEL_STARTUP_DELAY,
                    CONF_TILT_STARTUP_DELAY,
                    CONF_MIN_MOVEMENT_TIME,
                    CONF_TRAVEL_DELAY_AT_END,
                )
                if k in current
            },
        }

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )


class CoverTimeBasedSubentryFlow(ConfigSubentryFlow):
    """Handle subentry flow for adding/editing a cover entity."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle adding a new cover subentry."""
        return await self._async_handle_step(user_input, is_new=True)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguring an existing cover subentry."""
        return await self._async_handle_step(user_input, is_new=False)

    async def _async_handle_step(
        self, user_input: dict[str, Any] | None, *, is_new: bool
    ) -> SubentryFlowResult:
        """Handle the cover configuration form."""
        if user_input is not None:
            return self._save(user_input, is_new=is_new)

        # Build schema
        schema = self._build_schema(is_new=is_new)

        # Get suggested values for reconfigure
        suggested = {}
        if not is_new:
            suggested = self._get_suggested_values()

        step_id = "user" if is_new else "reconfigure"
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )

    def _build_schema(self, *, is_new: bool) -> vol.Schema:
        """Build the cover configuration schema."""
        fields: dict[vol.Marker, Any] = {}

        # Name (always required for new, shown for reconfigure too)
        fields[vol.Required("name")] = TextSelector()

        # Device type selector
        fields[vol.Required(CONF_DEVICE_TYPE, default=DEVICE_TYPE_SWITCH)] = (
            SelectSelector(
                SelectSelectorConfig(
                    options=[DEVICE_TYPE_SWITCH, DEVICE_TYPE_COVER],
                    translation_key="device_type",
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        )

        # Switch entity IDs
        switch_selector = EntitySelector(
            EntitySelectorConfig(domain=["switch", "input_boolean"])
        )
        fields[vol.Optional(CONF_OPEN_SWITCH_ENTITY_ID)] = switch_selector
        fields[vol.Optional(CONF_CLOSE_SWITCH_ENTITY_ID)] = switch_selector
        fields[vol.Optional(CONF_STOP_SWITCH_ENTITY_ID)] = switch_selector

        # Cover entity ID
        fields[vol.Optional(CONF_COVER_ENTITY_ID)] = EntitySelector(
            EntitySelectorConfig(domain="cover")
        )

        # Input mode
        fields[vol.Optional(CONF_INPUT_MODE, default=INPUT_MODE_SWITCH)] = (
            SelectSelector(
                SelectSelectorConfig(
                    options=[INPUT_MODE_SWITCH, INPUT_MODE_PULSE, INPUT_MODE_TOGGLE],
                    translation_key="input_mode",
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        )

        # Pulse time
        fields[vol.Optional(CONF_PULSE_TIME)] = NumberSelector(
            NumberSelectorConfig(
                min=0.1, max=10, step=0.1, mode=NumberSelectorMode.BOX
            )
        )

        # Travel timing section (collapsed)
        fields[vol.Required(SECTION_TRAVEL_TIMING)] = section(
            _travel_timing_schema(),
            {"collapsed": True},
        )

        # Advanced section (collapsed)
        fields[vol.Required(SECTION_ADVANCED)] = section(
            _advanced_schema(),
            {"collapsed": True},
        )

        return vol.Schema(fields)

    def _get_suggested_values(self) -> dict[str, Any]:
        """Get suggested values from existing subentry data."""
        data = dict(self._get_reconfigure_subentry().data)
        suggested = {}

        # Top-level fields
        for key in (
            "name",
            CONF_DEVICE_TYPE,
            CONF_OPEN_SWITCH_ENTITY_ID,
            CONF_CLOSE_SWITCH_ENTITY_ID,
            CONF_STOP_SWITCH_ENTITY_ID,
            CONF_COVER_ENTITY_ID,
            CONF_INPUT_MODE,
            CONF_PULSE_TIME,
        ):
            if key in data:
                suggested[key] = data[key]

        # Section fields
        travel_keys = (
            CONF_TRAVELLING_TIME_DOWN,
            CONF_TRAVELLING_TIME_UP,
            CONF_TILTING_TIME_DOWN,
            CONF_TILTING_TIME_UP,
            CONF_TRAVEL_MOVES_WITH_TILT,
        )
        advanced_keys = (
            CONF_TRAVEL_STARTUP_DELAY,
            CONF_TILT_STARTUP_DELAY,
            CONF_MIN_MOVEMENT_TIME,
            CONF_TRAVEL_DELAY_AT_END,
        )
        suggested[SECTION_TRAVEL_TIMING] = {
            k: data[k] for k in travel_keys if k in data
        }
        suggested[SECTION_ADVANCED] = {k: data[k] for k in advanced_keys if k in data}

        return suggested

    def _save(
        self, user_input: dict[str, Any], *, is_new: bool
    ) -> SubentryFlowResult:
        """Save the subentry data."""
        # Flatten sections into top-level data
        data = {}
        for key, value in user_input.items():
            if key in (SECTION_TRAVEL_TIMING, SECTION_ADVANCED):
                if isinstance(value, dict):
                    data.update(value)
            else:
                data[key] = value

        name = data.pop("name")

        if is_new:
            return self.async_create_entry(title=name, data=data)

        return self.async_update_reload_and_abort(
            self._get_entry(),
            self._get_reconfigure_subentry(),
            title=name,
            data=data,
        )
```

**Step 2: Run lint check**

Run: `ruff check custom_components/cover_time_based/config_flow.py`

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/config_flow.py
git commit -m "feat: add config flow with subentry support"
```

---

### Task 4: Add async_setup_entry to cover.py

**Files:**
- Modify: `custom_components/cover_time_based/cover.py`

This is the key change — add `async_setup_entry` alongside the existing `async_setup_platform`, and extract a helper function for creating `CoverTimeBased` from a flat config dict (used by both YAML and config entry).

**Step 1: Add async_setup_entry function**

After the existing `async_setup_platform` function (line 268), add:

```python
async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up cover entities from a config entry's subentries."""
    entities = []
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type != "cover":
            continue
        entity = _entity_from_subentry(
            config_entry, subentry
        )
        entities.append(entity)
    async_add_entities(entities)

    platform = entity_platform.current_platform.get()
    platform.async_register_entity_service(
        SERVICE_SET_KNOWN_POSITION, POSITION_SCHEMA, "set_known_position"
    )
    platform.async_register_entity_service(
        SERVICE_SET_KNOWN_TILT_POSITION, TILT_POSITION_SCHEMA, "set_known_tilt_position"
    )


def _get_subentry_value(key, subentry_data, entry_options, schema_default=None):
    """Get value with priority: subentry data > entry options > schema default."""
    if key in subentry_data:
        return subentry_data[key]
    if key in entry_options:
        return entry_options[key]
    return schema_default


def _entity_from_subentry(config_entry, subentry):
    """Create a CoverTimeBased entity from a config subentry."""
    data = dict(subentry.data)
    defaults = dict(config_entry.options)

    get = lambda key, default=None: _get_subentry_value(key, data, defaults, default)

    device_type = data.get("device_type", "switch")

    open_switch = data.get(CONF_OPEN_SWITCH_ENTITY_ID) if device_type == "switch" else None
    close_switch = data.get(CONF_CLOSE_SWITCH_ENTITY_ID) if device_type == "switch" else None
    stop_switch = data.get(CONF_STOP_SWITCH_ENTITY_ID) if device_type == "switch" else None
    cover_entity_id = data.get(CONF_COVER_ENTITY_ID) if device_type == "cover" else None
    input_mode = data.get(CONF_INPUT_MODE, INPUT_MODE_SWITCH) if device_type == "switch" else INPUT_MODE_SWITCH

    return CoverTimeBased(
        subentry.subentry_id,
        subentry.title,
        get(CONF_TRAVEL_MOVES_WITH_TILT, False),
        get(CONF_TRAVELLING_TIME_DOWN, DEFAULT_TRAVEL_TIME),
        get(CONF_TRAVELLING_TIME_UP, DEFAULT_TRAVEL_TIME),
        get(CONF_TILTING_TIME_DOWN, None),
        get(CONF_TILTING_TIME_UP, None),
        get(CONF_TRAVEL_DELAY_AT_END, None),
        get(CONF_MIN_MOVEMENT_TIME, None),
        get(CONF_TRAVEL_STARTUP_DELAY, None),
        get(CONF_TILT_STARTUP_DELAY, None),
        open_switch,
        close_switch,
        stop_switch,
        input_mode,
        get(CONF_PULSE_TIME, DEFAULT_PULSE_TIME),
        cover_entity_id,
    )
```

**Important:** Do NOT reformat any existing code. Only add new functions after line 268.

**Step 2: Run lint check**

Run: `ruff check custom_components/cover_time_based/cover.py`
Fix any issues reported (do NOT run `ruff format`).

**Step 3: Commit**

```bash
git add custom_components/cover_time_based/cover.py
git commit -m "feat: add async_setup_entry for config entry covers"
```

---

### Task 5: Update strings.json with translations

**Files:**
- Modify: `custom_components/cover_time_based/strings.json`

**Step 1: Rewrite strings.json**

The file must contain translations for: config flow steps, options flow, subentry flow steps, and the existing services. Structure:

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Cover Time Based",
        "description": "Set up the Cover Time Based integration. You can configure default timing values and then add individual covers."
      }
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Default timing settings",
        "description": "These defaults apply to all covers unless overridden in individual cover settings.",
        "sections": {
          "travel_timing": {
            "name": "Travel timing",
            "data": {
              "travelling_time_down": "Travel time down (seconds)",
              "travelling_time_up": "Travel time up (seconds)",
              "tilting_time_down": "Tilt time down (seconds)",
              "tilting_time_up": "Tilt time up (seconds)",
              "travel_moves_with_tilt": "Travel moves with tilt"
            }
          },
          "advanced": {
            "name": "Advanced settings",
            "data": {
              "travel_startup_delay": "Travel startup delay (seconds)",
              "tilt_startup_delay": "Tilt startup delay (seconds)",
              "min_movement_time": "Minimum movement time (seconds)",
              "travel_delay_at_end": "Travel delay at end (seconds)"
            }
          }
        }
      }
    }
  },
  "config_subentries": {
    "cover": {
      "entry_type": "Cover",
      "initiate_flow": {
        "user": "Add cover",
        "reconfigure": "Reconfigure cover"
      },
      "abort": {
        "reconfigure_successful": "[%key:common::config_flow::abort::reconfigure_successful%]"
      },
      "step": {
        "user": {
          "title": "Add a time-based cover",
          "data": {
            "name": "Name",
            "device_type": "Device type",
            "open_switch_entity_id": "Open switch",
            "close_switch_entity_id": "Close switch",
            "stop_switch_entity_id": "Stop switch",
            "cover_entity_id": "Cover entity",
            "input_mode": "Input mode",
            "pulse_time": "Pulse time (seconds)"
          },
          "data_description": {
            "device_type": "Choose 'switch' to control via switch entities, or 'cover' to wrap an existing cover entity.",
            "input_mode": "Switch: latching relays. Pulse: momentary with separate stop. Toggle: same button starts and stops.",
            "pulse_time": "Duration of button press for pulse/toggle modes."
          },
          "sections": {
            "travel_timing": {
              "name": "Travel timing",
              "data": {
                "travelling_time_down": "Travel time down (seconds)",
                "travelling_time_up": "Travel time up (seconds)",
                "tilting_time_down": "Tilt time down (seconds)",
                "tilting_time_up": "Tilt time up (seconds)",
                "travel_moves_with_tilt": "Travel moves with tilt"
              }
            },
            "advanced": {
              "name": "Advanced settings",
              "data": {
                "travel_startup_delay": "Travel startup delay (seconds)",
                "tilt_startup_delay": "Tilt startup delay (seconds)",
                "min_movement_time": "Minimum movement time (seconds)",
                "travel_delay_at_end": "Travel delay at end (seconds)"
              }
            }
          }
        },
        "reconfigure": {
          "title": "Reconfigure cover",
          "data": {
            "name": "Name",
            "device_type": "Device type",
            "open_switch_entity_id": "Open switch",
            "close_switch_entity_id": "Close switch",
            "stop_switch_entity_id": "Stop switch",
            "cover_entity_id": "Cover entity",
            "input_mode": "Input mode",
            "pulse_time": "Pulse time (seconds)"
          },
          "data_description": {
            "device_type": "Choose 'switch' to control via switch entities, or 'cover' to wrap an existing cover entity.",
            "input_mode": "Switch: latching relays. Pulse: momentary with separate stop. Toggle: same button starts and stops.",
            "pulse_time": "Duration of button press for pulse/toggle modes."
          },
          "sections": {
            "travel_timing": {
              "name": "Travel timing",
              "data": {
                "travelling_time_down": "Travel time down (seconds)",
                "travelling_time_up": "Travel time up (seconds)",
                "tilting_time_down": "Tilt time down (seconds)",
                "tilting_time_up": "Tilt time up (seconds)",
                "travel_moves_with_tilt": "Travel moves with tilt"
              }
            },
            "advanced": {
              "name": "Advanced settings",
              "data": {
                "travel_startup_delay": "Travel startup delay (seconds)",
                "tilt_startup_delay": "Tilt startup delay (seconds)",
                "min_movement_time": "Minimum movement time (seconds)",
                "travel_delay_at_end": "Travel delay at end (seconds)"
              }
            }
          }
        }
      }
    }
  },
  "selector": {
    "device_type": {
      "options": {
        "switch": "Control via switches",
        "cover": "Wrap existing cover"
      }
    },
    "input_mode": {
      "options": {
        "switch": "Switch (latching)",
        "pulse": "Pulse (momentary)",
        "toggle": "Toggle (same button stops)"
      }
    }
  },
  "services": {
    "set_known_position": {
      "name": "Set cover position",
      "description": "Sets a known position for the cover internally.",
      "fields": {
        "entity_id": {
          "name": "Entity ID",
          "description": "The entity ID of the cover to set the position for."
        },
        "position": {
          "name": "Position",
          "description": "The position of the cover, between 0 and 100."
        }
      }
    },
    "set_known_tilt_position": {
      "name": "Set cover tilt position",
      "description": "Sets a known tilt position for the cover internally.",
      "fields": {
        "entity_id": {
          "name": "Entity ID",
          "description": "The entity ID of the cover to set the tilt position for."
        },
        "position": {
          "name": "Position",
          "description": "The tilt position of the cover, between 0 and 100."
        }
      }
    }
  }
}
```

**Step 2: Commit**

```bash
git add custom_components/cover_time_based/strings.json
git commit -m "feat: add config flow and subentry translations"
```

---

### Task 6: Deploy and test

**Step 1: Run lint**

Run: `ruff check custom_components/cover_time_based/`
Fix any issues (do NOT run `ruff format`).

**Step 2: Run type checker**

Run: `npx pyright`
Fix any fixable type errors.

**Step 3: Deploy to HA**

```bash
rm -Rf /workspaces/homeassistant-core/config/custom_components/fado && cp -r /workspaces/ha-cover-time-based/custom_components/cover_time_based /workspaces/homeassistant-core/config/custom_components/
```

Wait — this is the wrong project. The deploy command for this project should be:

```bash
rm -Rf /workspaces/homeassistant-core/config/custom_components/cover_time_based && cp -r /workspaces/ha-cover-time-based/custom_components/cover_time_based /workspaces/homeassistant-core/config/custom_components/
```

**Step 4: Verify in HA**

- Restart HA
- Go to Settings → Devices & Services → Add Integration → "Cover Time Based"
- Verify the config flow shows up
- Create an integration entry
- Add a cover subentry via the UI
- Verify the cover entity appears
- Test the options flow (edit defaults)
- Test reconfigure on the subentry

---

### Task 7: Create PR

**Step 1: Push branch and create PR**

```bash
git push -u origin feat/ui-config-flow
```

Create PR with summary of changes:
- New config flow with subentry support
- Options flow for integration-level defaults
- YAML backward compatibility maintained
- Translations for all flow steps
