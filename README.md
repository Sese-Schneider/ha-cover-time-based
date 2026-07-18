# Cover time based integration by [@Sese-Schneider](https://www.github.com/Sese-Schneider)

A Home Assistant integration to control your cover based on time.

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sese-Schneider&repository=ha-cover-time-based&category=integration)
[![Active Installations][installations-shield]](https://analytics.home-assistant.io/)
[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)

![Project Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]

This integration is based on [davidramosweb/home-assistant-custom-components-cover-time-based](https://github.com/davidramosweb/home-assistant-custom-components-cover-time-based/).

It improves the original integration by adding tilt control, synchronized travel/tilt movements, and a visual configuration card.

### Features:

- **Control the position of your cover based on time**.
- **External state monitoring:** Detects physical switch presses and keeps the position tracker in sync.
- **Up/down interlock (Switch mode):** Never energizes both direction relays at once — when one direction relay turns on, even from outside Home Assistant (a wall switch wired straight to the relays), the opposite relay is switched off — protecting motors with no hardware interlock.
- **Multiple input modes:** Latching switches, momentary pulse buttons, or toggle-style relays.
- **Wrap an existing cover:** Add time-based position tracking to any cover entity.
- **Control the tilt of your cover based on time** with four tilt modes: inline, sequential closes-then-tilts-closed, sequential closes-then-tilts-open, or separate tilt motor.
- **Built-in configuration and calibration:** Calibrate travel times directly from the UI, including finer parameters to compensate for the time it takes the motor to startup.
- **Resyncs position at endpoints:** Motors with internal limit switches self-stop at the 0%/100% endpoints, which resyncs the position tracker with the physical cover. For latching (Switch-mode) relays a configurable run-on keeps the relay energized until the motor reaches the endpoint.

## Install

### HACS

_This repo is available for install through HACS._

- Go to HACS
- Search for "Cover time based"

_or_

Click here:

[![](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sese-Schneider&repository=ha-cover-time-based&category=integration)

## Setup

### Creating a cover via the UI

1. Go to **Settings → Devices & Services → Helpers**
2. Click **Create Helper → Cover Time Based**
3. Enter a name for your cover

### Setup the configuration card

The configuration card provides a visual interface for all settings and supports built-in calibration to measure timing parameters automatically.

> **Create at least one cover first.** The configuration card is delivered as a frontend asset of this integration, and Home Assistant only loads an integration's frontend assets once the integration is loaded — which requires at least one config entry to exist. If you add the card to a dashboard before creating any cover, Lovelace will show a red **Configuration error** ("custom element doesn't exist: cover-time-based-card"). Create a cover via the steps above, then add the card.
>
> **Hard-refresh your browser after the first install.** Home Assistant loads dashboard resources only when the page first loads, so the card is missing from any browser session that was already open when you installed the integration — and because Home Assistant's service worker caches the app, often only a _hard_ refresh brings it in (`Ctrl`/`Cmd`+`Shift`+`R`). A dismissible notice in **Settings → Repairs** prompts you to do this after a first install; it does not appear on version updates or ordinary restarts.

1. Go to **Settings → Dashboards**.
2. Click **Add dashboard → New dashboard from scratch**.
3. Fill in a name and make sure **Add to sidebar** is selected.
4. Click **Create**.
5. Click the new dashboard icon in the Home Assistant side bar.
6. Click the **Edit dashboard** icon in the top right corner.
7. Under **New section** click the **+** icon to add a new card.
8. Select the **By card** tab (in Home Assistant 2026.6+ the card picker
   opens on the **By entity** tab, where this configuration card does not
   appear), then search for and select the **Cover time based
   configuration** card and click **Save**.
9. Click **Done** to stop editing the dashboard.

### Configuration and Calibration Card

The configuration card provides a visual interface for all settings and supports built-in calibration to measure timing parameters automatically.

The configuration card has two tabs: **Device** and **Calibration**. The Device tab must be fully configured before accessing the Calibration tab.

The card remembers the device you last selected and restores it the next time the dashboard loads, so you don't have to re-pick the cover you were configuring. The selection is remembered per browser rather than per Home Assistant user, and a cover that has since been deleted is simply not restored.

The main items on the **Device** configure how to interface with the
physical cover:

- **Device type**: whether this helper talks to the cover via open/close switches or via an existing cover entity
- **Switch type**: whether the switches are latching, pulsed, or toggled.
- **Tilting**: what type of tilt, if any, is supported.

The **Calibration** tab is used to configure:

- **Position**: sync the position tracker with the physical cover and slat position.
- **Travel**: how long it takes to open and close the cover, and how much time it takes to start the motor.
- **Tilt**: how long it takes to open and close the slats, and how much time it takes to start the motor.

## Device

First configure the **Device type**. A cover-time-based helper can either:

- wrap an existing cover entity to add time-based position tracking, or
- use relay switches to control cover movement, and optionally to
  control tilt movement.

### Wrapped covers

Wrap an existing cover entity to add time-based position tracking. Useful for covers that already have basic open/close/stop functionality but lack position tracking.

Specify the **Cover entity**.

**Reacting to physical wall switches.** When the wrapped cover is operated externally (physical wall switch, remote, or another integration), the time-based tracker can only follow the movement if the wrapped entity emits an `opening` / `closing` state during travel. Some wrapped entities — notably certain Tuya / ZHA cover modules — stay in their current `open` or `closed` state the entire time the motor runs, only reporting the final settled state once the movement completes. In that case the time-based position cannot be tracked *during* the physical movement, but it will snap to the wrapped entity's reported position once it settles (or once you click the wrapped cover's stop button, if the wrapped entity reports its current position at that point). If your device instead reports `closed` (or `unknown`) the *moment* a command is issued — so a manual stop mid-travel is wrongly reported as fully closed — enable **Reports commands, not endpoints** (below) to track it purely by time.

**Ignore reported position.** Enable this option when the wrapped cover reports an unreliable position. The integration then tracks the position purely by time and ignores the `current_position` the wrapped entity reports (the fully-closed endpoint is still trusted). This is also what lets time-based tilt work cleanly on a wrapped cover whose reported position would otherwise interfere.

**Reports commands, not endpoints.** Some covers (for example single-DP Tuya shutters) have no position feedback and never emit an `opening` / `closing` state — their reported state simply echoes the last command: `open` when opening was commanded, `closed` when closing was commanded, and `unknown` when stopped. For these, a `closed` state does *not* mean the cover reached the bottom; pressing **stop** halfway is reported identically to a full close, so the default behaviour wrongly snaps the position to 0%. Enable this option to treat the wrapped entity's state as an open / close / stop **command** and track the position entirely by time: `open` starts a timed open, `closed` starts a timed close, and `unknown` (stop) freezes the cover at its current time-based position. Leave it **off** for any cover that reports a real position or a genuine `opening` / `closing` transition.

Because a command-echo cover has no endpoint feedback — and in practice drives an endstop-less motor that only stalls against its mechanical stop while powered — the integration also sends an explicit **stop** when the cover reaches the 0% / 100% endpoints (rather than assuming the motor self-stops there, as it does for other wrapped covers), and treats an `open` / `close` command issued while already parked at that endpoint as a no-op. Set **Endpoint Run-on Time** to 0 for such a motor so it is de-energized the instant it reaches the endpoint. If the cover can also be moved by an external remote — so "already parked there" may not be true — enable [Always re-send open/close at the endpoints](#always-re-send-openclose-at-the-endpoints) to drive the command through anyway.

**Setting a position.** If the wrapped cover natively supports `set_cover_position`, the integration forwards the set-position command straight to it, so the cover stops at the requested position even if the underlying device has no `stop` service. The time-based tracker still animates the position live during the move (handy for covers that only report their position once they finish moving). On such a cover, the integration's **Stop** is implemented by setting the wrapped cover to the current calculated position. If the wrapped cover doesn't support `set_cover_position`, the integration falls back to driving it with timed open / close / stop. The **Force time-based positioning** option forces that timed behaviour even when native set-position is available — use it if the wrapped cover's own set-position is unreliable.

**Invert position.** Some covers run backwards relative to a standard cover — an overhanging awning, say, whose underlying entity reports *open* when the awning is fully extended (shading) and *closed* when it is rolled away. Enable this option to flip the position axis: the time-based cover reports `100 −` the wrapped entity's position and swaps the open / close commands (and `set_cover_position(p)` is forwarded as `100 − p`), so *open* means retracted and *closed* means extended, the right way round. This flips the position axis only; the tilt logic itself is unchanged. Invert is intended for position-only covers such as awnings and shutters — not tilting venetians, where a timed tilt mode simulates the slats by driving the same (now-inverted) motor. Leave it **off** for a normally-oriented cover.

**Tilt on a wrapped cover.** The **Inline** and **Sequential** tilt modes drive the wrapped cover's normal open / close commands, so they work on any wrapped cover regardless of whether it reports tilt support. Only the **Separate tilt motor** mode requires the wrapped cover to expose its own tilt commands, so it is offered only when the wrapped entity reports native tilt support.

**Native tilt forwarding.** If the wrapped cover natively supports `set_cover_tilt_position` — for example a Z-Wave venetian shutter whose firmware positions its own slats — and you use the **Inline** tilt mode, the integration forwards the tilt commands (set-tilt, open-tilt, close-tilt) straight to the wrapped cover instead of simulating them by pulsing the main motor. The device positions its slats itself, precisely and at any travel position, and the integration snaps its tilt tracker to the angle the cover reports once it settles. On such a cover the integration also drives **position** natively (forwarding `set_cover_position`) even though tilt is configured, and animates the tilt display sweeping toward the direction endpoint during travel — venetian slats close on the way down, open on the way up — before syncing to the reported angle. This is auto-detected from the wrapped entity's supported features; no extra configuration is needed. A cover that does not advertise native tilt keeps the timed simulation described above, and the Sequential / Separate-tilt-motor modes always use their existing behaviour.

### Switch-based covers

Control a cover using two relay switches (one for open, one for close), with an optional third stop switch (required in **Pulse** mode).

Specify the **Open switch**, **Close switch**, and optionally the **Stop switch** entities (required in **Pulse** mode).

### Input Mode for switch-based covers

Four input modes are available to describe how the switch entities for switch-based covers function:

| Mode                         | Description                                                                                                                                                                                                                                                                                                                                                                                |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Switch**                   | Latching relays. The direction switch stays ON for the entire movement. Movement stops when the switch is turned OFF                                                                                                                                                                                                                                                                       |
| **Pulse**                    | Momentary pulse buttons. A brief ON-OFF pulse latches the motor on. **Requires a dedicated stop button** (or script) to stop movement mid-travel. If your hardware has no stop signal and instead stops when the opposite button is pressed, use **Toggle (opposite button)** instead.                                                                                                     |
| **Toggle (same button)**     | Toggle-style relays. A brief ON-OFF pulse latches the motor on. A second pulse on the same direction button stops the motor.                                                                                                                                                                                                                                                               |
| **Toggle (opposite button)** | Momentary toggle relays with no dedicated stop button, where pressing the _opposite_ direction while moving stops the motor (a same-direction press keeps it moving). Reversing takes two presses: opposite (stop), then press again to move. Choose this over **Toggle (same button)** when your controller stops on the opposite button, and over **Pulse** when you have no stop relay. |

> **Scripts in Pulse mode.** In **Pulse** mode the Open / Close / Stop entities (and the dual-motor tilt entities) may be `script` entities as well as `switch` entities — for example, IR-remote-controlled covers where each script fires an open / close / stop IR command. **Switch** and both **Toggle** modes require `switch` entities: they rely on the entity reporting a held/latched on-state, which a script (which auto-returns to `off`) cannot provide. Keep the scripts short: after **Pulse time** elapses the integration turns the entity off again, which cancels any script still running — so a script whose own internal `delay` is longer than the pulse time would be cut short.

#### Pulse time

With the **Pulse** input mode, the **Pulse time** configures how long the switch should send the ON signal before it turns OFF. Defaults to **1s**. Neither **Toggle** mode uses it — toggle relays are momentary, so the integration sends a single ON pulse and lets the relay release itself.

#### Relay reports its own OFF (Toggle modes)

Applies to both Toggle modes (same-button and opposite-button). Leave it **on** (the default) for normal toggle relays — they switch themselves off after the pulse and report that OFF back to Home Assistant, so the integration can drive a still-ON relay OFF first to guarantee a clean ON edge.

Turn it **off** for hardware-managed pulse modules — for example an **Aqara T2** in its 200 ms internal-pulse mode — that pulse the contact themselves but **never report the OFF** to Home Assistant, leaving the switch entity stuck `on`. On such hardware a `turn_off` is not an idempotent "off" but another activation pulse, so the integration's attempt to force a clean edge (`turn_off` then `turn_on`) lands as a doubled command and the motor's toggle counter drifts — the symptom is Stop reversing the cover and Up driving it down. With the option off, toggle mode only ever sends a **single `turn_on` per command and never a `turn_off`**, giving exactly one clean activation per press. A repeated `turn_on` still pulses the motor even while the entity reads `on`.

#### Send stop signal at endpoints (Pulse mode)

Pulse mode only. Leave it **on** (the default) for controllers that **latch** the direction command and keep running until they receive a separate stop pulse. Without the endpoint stop they stay stuck "moving" — the cover only responds after several clicks and the physical wall/PLC buttons appear blocked. With the option on, the integration pulses the dedicated stop relay when the cover reaches an endpoint (deferred by the **Endpoint run-on time**, see below); because the stop is a separate relay it can never restart the motor.

Turn it **off** for controllers with **automatic end-stop detection**: the motor halts itself at its 0%/100% limit switches, and a stop pulse received _while it is already stopped_ is read as "go to favourite/preset position" (the classic Somfy _my_ behaviour), repositioning the cover on every limit hit. With the option off, no stop is sent at the endpoints. The same flag governs a **separate tilt motor**'s tilt-stop relay at the tilt endpoints. **Switch**, **Toggle**, **Toggle (opposite button)** and wrapped-cover modes are unaffected.

### Assumed state

Available for every device type. A time-based cover calculates its position from travel time without feedback, so by default it reports an _assumed_ state and Home Assistant keeps both the open and close buttons active at all times. Turn **Assumed state** off if you trust the time-based calculation and want the UI to behave like a position-aware cover — greying out actions that can't apply (for example the close button once the cover is already fully closed). Leave it on if the calculation can drift (motor slip, manual operation, power loss mid-travel), since the always-active buttons let you re-issue a command to re-converge.

### Always re-send open/close at the endpoints

Available for every device type. Normally, an open (or close) command issued while the tracker already believes the cover is settled at that endpoint is treated as redundant — the movement is skipped, or reduced to a short resync pulse — since the motor is thought to already be there.

Turn this option **on** for a cover that has **no position feedback** and can _also_ be moved by an external remote or wall button. Such a remote moves the cover without telling Home Assistant, so the tracker can believe the cover is closed while it is physically open — and the close command that would fix that is exactly the one skipped as redundant, making the cover appear unresponsive until you nudge it off the endpoint by hand. With the option on, an endpoint command is always driven for the **full travel time** (modelled as starting from the opposite endpoint, so each mode's tilt phases run too), guaranteeing it reaches the motor.

Leave it **off** (the default) for covers that report their own position: there the skip is correct, and forcing a re-drive would run the motor into its limit on every redundant press.

Note that a forced re-drive deliberately models the move as starting from the opposite endpoint, so if you **stop it part-way** the reported position is derived from that assumed start and can be well off — stopping a forced close halfway reports roughly 50% even if the cover started at the bottom. Let a re-drive run to the endpoint, where the position resyncs, rather than stopping it mid-travel.

## Tilt Mode

The **Tilt Mode** setting controls how tilt and travel interact:

- **None:** Tilt is disabled. Only position tracking is used.
- **Inline:** Tilt and travel use the same motor. Tilting can happen with the cover in any position. When closing the cover, the closing movement first causes the slats to tilt closed before the cover starts closing. When opening the cover, the opening movement first causes the slats to tilt open before the cover starts opening.
- **Sequential (closes then tilts closed):** Tilting can only happen in the fully closed position. First the cover closes then the slats tilt closed (motor drives further down past cover-closed to close the slats). When opening, the slats first tilt open (motor up) then the cover opens.
- **Sequential (closes then tilts open):** Mirror image of the above — for covers where slats articulate *open* when the motor drives further down past cover-closed, not closed. First the cover closes then the slats tilt open (motor continues down). When opening, the slats first tilt closed (motor up) then the cover opens.
- **Separate tilt motor (dual_motor):** A separate motor controls the tilt. Requires dedicated tilt open/close/stop switches. Tilt is only allowed when the cover is in a safe position (configurable).

### How close/open behaves under sequential tilt modes

HA's cover entity exposes close/open for travel and close-tilt/open-tilt for articulation. The integration handles each slightly differently depending on who invoked it:

- **HA UI close** (`cover.close_cover`): drives travel only — the cover closes and slats remain at the resting position. Use the tilt-close button separately to articulate.
- **HA UI open** (`cover.open_cover`): restores slats to the resting position if needed, then travels to fully open. This is a single motor motion.
- **HA UI close-tilt / open-tilt**: drives tilt only (with a travel pre-step if tilt is only allowed at travel=0).
- **External close** (physical switch or automation firing the close relay): the integration assumes the motor runs the **full journey** — it closes the cover and then continues to articulate the slats past cover-closed to the opposite extreme. Tracking follows both phases.
- **External open**: the integration restores slats to the resting position and then travels to fully open (same as the HA UI open path).

**External-switch assumption.** External close on sequential modes assumes a motor controller that latches on a pulse and runs to a mechanical end without stopping at the cover-closed position (common with pulse-mode relays and many off-the-shelf blind motors). If your external switch stops the motor at cover-closed instead — for example a latching switch that you release partway, or a motor that naturally halts at travel=0 — the reported tilt position will drift until the next sync. Please [open an issue](https://github.com/clintongormley/ha-cover-time-based/issues) describing your hardware so we can support it.

### Tilt Motor

For covers with a dedicated tilt motor, configure:

- **Tilt open/close/stop switches:** The relay switches controlling the tilt motor (unless this is a wrapped cover entity which doesn't require extra switches).
- **Safe tilt position:** The tilt moves to this position before travel starts (default: 100 = fully open).
- **Max tilt allowed position:** Tilt is only allowed when the cover position is at or below this value (e.g., 0 = only when fully closed).

## Calibration

The **Calibration** tab is used to synchronise the position tracker with the position of the physical cover and slats, and to configure the timings that allow this integration to track the physical hardware.

### Current Position

Use the open/stop/close buttons to move the cover (and slats, if tilting is enabled) into a known position and then change the **Current Position** dropdown from `Unknown` to that position. The position must be specified in order to access the calibration tests further down the page.

### Timing Calibration

Select the attribute that you wish to calibrate. The available attributes depend on the current position of the cover and slats, and which other attributes have already been configured. For instance, in position **Fully open** you can only calibrate **Travel time (close)** and **Minimum movement time**. **Travel startup delay** becomes configurable once **Travel time (open)** or **Travel time (close)** has been configured.

1. Set the **Current position** of the cover and slats.
2. Select the attribute you wish to configure.
3. Read the description of what needs to be measured.
4. Click **Start**.
5. Once the cover or slats reach the position described in the description, click **Finish**. Alternatively, click **Cancel** to abort the calibration.

### Calibration Attributes for Travel

| Option               | Description                                                           | Default |
| -------------------- | --------------------------------------------------------------------- | ------- |
| Travel time (close)  | Time in seconds for the cover to fully close                          |         |
| Travel time (open)   | Time in seconds for the cover to fully open                           |         |
| Travel startup delay | Motor startup compensation for travel (see below)                     | None    |
| Direction change delay | Settle time between stopping and driving the other way when reversing (see below) | 1.0     |
| Endpoint run-on time | Extra relay time at endpoints to reset position (Switch mode; Pulse when it sends the stop) | 2.0     |
| Min movement time    | Minimum movement duration - blocks shorter movements to prevent drift | None    |

### Calibration Attributes for Tilt

| Option             | Description                                    | Default |
| ------------------ | ---------------------------------------------- | ------- |
| Tilt time (close)  | Time in seconds to tilt the cover fully closed | None    |
| Tilt time (open)   | Time in seconds to tilt the cover fully open   | None    |
| Tilt startup delay | Motor startup compensation for tilt            | None    |

#### Travel/Tilt startup delay

Compensates for motor inertia by delaying position tracking after relay activation. This improves position accuracy, especially for short movements.

**The problem:** Motors have startup inertia. After the relay turns ON, there's a brief delay before the cover starts moving. For long movements (e.g., 30s) this is negligible, but for short movements (e.g. 0.5s) it can cause 20-30% position error that accumulates over time.

**How it works:**

1. Relay turns ON immediately
2. Waits for the configured startup delay (motor is starting up)
3. Only then starts counting position change
4. Can be cancelled at any time (stop or direction change)

Recommended values: 0.05 - 0.15 seconds. Can be configured separately for travel and tilt.

#### Endpoint Run-on Time

Position tracking is not exact and can drift over time, so the tracker resyncs itself whenever the cover is sent fully to the 0% or 100% endpoint.

Most cover motors have internal limit switches and stop themselves at the endpoints. In **Toggle**, **Toggle (opposite button)** and (most) wrapped-cover modes the integration therefore sends **no stop command at an endpoint** — it lets the motor run into its own limit. This avoids an unwanted extra movement (in Toggle mode a stop pulse on an already-stopped motor would restart it) and resyncs the tracker for free, as the motor always reaches its true endpoint. The exception is a wrapped cover with **[Reports commands, not endpoints](#wrapped-covers)** enabled: it has no endpoint feedback and typically an endstop-less motor, so it *is* sent an explicit stop at the endpoint (and re-commanding it to an endpoint it already sits at is a no-op rather than a re-drive, unless [Always re-send open/close at the endpoints](#always-re-send-openclose-at-the-endpoints) is on). **Pulse** mode is configurable (see [Send stop signal at endpoints](#send-stop-signal-at-endpoints-pulse-mode) above): by default it pulses its dedicated stop relay at the endpoint, which a latching controller needs, but that can be turned off for controllers that self-stop at their own limits.

In **Switch** mode the direction relay is latched ON for the whole movement, so it must be actively switched off at the endpoint. Because tracking is approximate, the relay is held on for an extra **Endpoint Run-on Time** (default 2s) so the motor reaches the physical endpoint before power is cut. **This setting applies to Switch mode, and to Pulse mode when it sends the endpoint stop** (it defers that stop pulse by the run-on so the motor seats against its limit first).

The same self-stop handling applies to a **separate tilt motor** (separate-tilt-motor mode): no stop is sent when tilt reaches its 0%/100% endpoints — the tilt motor self-stops on its own limit — except in **Switch** mode (which de-energizes the latched tilt relay) and in **Pulse** mode when _Send stop signal at endpoints_ is on (which pulses the tilt-stop relay). Mid-tilt positions are always stopped (nothing self-stops there).

The self-stop skip is about **travel** reaching an endpoint. Where the slats share the travel motor — **inline** tilt — a tilt move made while the cover is parked at a travel endpoint drives that motor _off_ its limit switch, so it will not self-stop there; the stop is sent in that case even in the modes that normally skip it. The two cases that settle themselves are unaffected: a dedicated **tilt motor** skips the stop at its own tilt endpoints (as described above), and a wrapped cover tilting **natively** holds itself at the target, so neither is sent an extra stop.

Under the **sequential closes-then-tilts-closed** and **sequential closes-then-tilts-open** tilt modes, run-on is skipped at the closed (0%) endpoint, because the motor is already driven past cover-closed for the tilt phase. Run-on still applies at the open (100%) endpoint.

#### Min movement time

Prevents position drift by blocking relay activations too brief to physically move the cover. Movements to 0% or 100% are always allowed. Recommended values: 0.5 - 1.5 seconds.

#### Direction change delay

Reversing a moving cover is never a single step: the motor is stopped, given a moment to come to rest, and only then driven the other way. This setting is that pause, and it defaults to **1.0 second**.

**The problem:** motors differ in how long they take to stop. If the pause is shorter than yours needs, the reverse command arrives while the motor is still settling and is simply **ignored** — but the integration has already started counting the new movement. The result is a cover sitting motionless while its position ticks along to the target, leaving the entity out of sync with reality.

**Symptom:** you send the cover to a position that requires a reversal — for example it is opening towards 75% and you select 25% — and the cover stops where it is while Home Assistant animates down to 25%.

**The fix:** raise this value until reversals take reliably. Try 2 - 3 seconds; a good test is to stop the cover mid-travel by hand, count how long it takes to come to a complete rest, and use at least that. Leave it at 1.0 unless you see the symptom above.

Note this pause also applies to the tilt-restore reversal on covers whose slats share the travel motor, so raising it lengthens that step too.

## Services

### `cover_time_based.set_known_position`

Manually set the internal position of a cover. Useful for correcting drift.

| Field     | Description                 |
| --------- | --------------------------- |
| entity_id | The cover entity            |
| position  | The position to set (0-100) |

### `cover_time_based.set_known_tilt_position`

Manually set the internal tilt position of a cover.

| Field         | Description                      |
| ------------- | -------------------------------- |
| entity_id     | The cover entity                 |
| tilt_position | The tilt position to set (0-100) |

### `cover_time_based.start_calibration`

Start a calibration test to measure a timing parameter.

| Field     | Description                                                                    |
| --------- | ------------------------------------------------------------------------------ |
| entity_id | The cover entity                                                               |
| attribute | The timing parameter to calibrate                                              |
| timeout   | Safety timeout in seconds - motor auto-stops if stop_calibration is not called |
| direction | Direction to move (`open` or `close`). Auto-detects if not set                 |

### `cover_time_based.stop_calibration`

Stop an active calibration test and save the result.

| Field     | Description                                   |
| --------- | --------------------------------------------- |
| entity_id | The cover entity                              |
| cancel    | If `true`, discard the results without saving |

## Debugging

If something isn't working as expected, you can enable debug logging to see detailed information about what the integration is doing.

### Via Developer Tools

1. Go to **Developer Tools → Actions**.
2. Search for **Logger: Set level** and select it.
3. Switch to YAML mode and enter:

```yaml
action: logger.set_level
data:
  custom_components.cover_time_based: debug
```

4. Click **Perform action**.
5. Reproduce the issue — debug messages will appear in the Home Assistant log.

To turn off debug logging, repeat the steps above but change `debug` to `info`.

### Via YAML

Add the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.cover_time_based: debug
```

Restart Home Assistant to apply.

## Reporting Issues

If you encounter a bug or have a feature request, please open an issue on [GitHub](https://github.com/clintongormley/ha-cover-time-based/issues). Include debug logs if possible — they help diagnose problems much faster.

## YAML configuration (deprecated)

> **Note:** YAML configuration is deprecated and will be removed in a future version. Please use the UI method described above instead. Existing YAML configurations will continue to work, and a deprecation notice will appear in your Home Assistant repairs panel.

<details>
<summary>Show YAML configuration (deprecated)</summary>

### Basic configuration with individual device settings:

```yaml
cover:
  - platform: cover_time_based
    devices:
      room_rolling_shutter:
        name: Room Rolling Shutter
        open_switch_entity_id: switch.wall_switch_right
        close_switch_entity_id: switch.wall_switch_left
        travel_moves_with_tilt: false
        travelling_time_down: 23
        travelling_time_up: 25
        tilting_time_down: 2.3
        tilting_time_up: 2.7
        travel_delay_at_end: 2.0
        min_movement_time: 0.5
        travel_startup_delay: 0.1
        tilt_startup_delay: 0.08
```

### YAML options

| Name                   | Type    | Requirement                                     | Description                                                             | Default |
| ---------------------- | ------- | ----------------------------------------------- | ----------------------------------------------------------------------- | ------- |
| name                   | string  | **Required**                                    | Name of the created entity                                              |         |
| open_switch_entity_id  | entity  | **Required** or `cover_entity_id`               | Entity ID of the switch for opening the cover. Accepts a `script` entity when `is_button: true` |         |
| close_switch_entity_id | entity  | **Required** or `cover_entity_id`               | Entity ID of the switch for closing the cover. Accepts a `script` entity when `is_button: true` |         |
| stop_switch_entity_id  | entity  | Required when `is_button: true`; not used by other modes | Entity ID of the switch for stopping the cover. Accepts a `script` entity when `is_button: true` | None    |
| cover_entity_id        | entity  | **Required** or `open_\|close_switch_entity_id` | Entity ID of an existing cover entity                                   |         |
| is_button              | boolean | _Optional_                                      | Set to `true` for momentary pulse buttons (the only control mode selectable from YAML; the rest are card-only) | false   |
| travelling_time_down   | float   | _Optional_                                      | Time in seconds to close the cover                                      | 30      |
| travelling_time_up     | float   | _Optional_                                      | Time in seconds to open the cover                                       | 30      |
| tilting_time_down      | float   | _Optional_                                      | Time in seconds to tilt the cover fully closed                          | None    |
| tilting_time_up        | float   | _Optional_                                      | Time in seconds to tilt the cover fully open                            | None    |
| travel_moves_with_tilt | boolean | _Optional_                                      | Whether tilt movements also cause proportional travel changes           | false   |
| travel_delay_at_end    | float   | _Optional_                                      | Additional relay time (seconds) at endpoints for position reset         | None    |
| min_movement_time      | float   | _Optional_                                      | Minimum movement duration (seconds) - blocks shorter movements          | None    |
| travel_startup_delay   | float   | _Optional_                                      | Motor startup time compensation (seconds) for travel movements          | None    |
| tilt_startup_delay     | float   | _Optional_                                      | Motor startup time compensation (seconds) for tilt movements            | None    |
| direction_change_delay | float   | _Optional_                                      | Settle gap (seconds) between stopping and driving the other way when reversing. Raise it if a reversal leaves the cover parked while the position keeps counting. Also applies to the tilt-restore reversal on shared-motor covers | 1.0     |
| pulse_time             | float   | _Optional_                                      | Duration in seconds for button press in pulse mode                      | 1.0     |
| relay_reports_off      | boolean | _Optional_                                      | Toggle mode: set false for pulse modules that never report their OFF    | true    |
| send_endpoint_stop     | boolean | _Optional_                                      | Pulse mode: set false for auto-stop controllers that reposition on a stop received while stopped | true    |

</details>

[commits-shield]: https://img.shields.io/github/commit-activity/y/Sese-Schneider/ha-cover-time-based?style=for-the-badge
[commits]: https://github.com/Sese-Schneider/ha-cover-time-based/commits/main
[installations-shield]: https://img.shields.io/badge/dynamic/json?url=https://analytics.home-assistant.io/custom_integrations.json&query=$.cover_time_based.total&label=Active%20installations&color=41BDF5&style=for-the-badge
[license-shield]: https://img.shields.io/github/license/Sese-Schneider/ha-cover-time-based?style=for-the-badge
[maintenance-shield]: https://img.shields.io/maintenance/yes/2026.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/v/release/Sese-Schneider/ha-cover-time-based?style=for-the-badge
[releases]: https://github.com/Sese-Schneider/ha-cover-time-based/releases
