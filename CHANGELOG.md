## 4.8.0 (2026-07-06)

### Features

- **New "Toggle (opposite button)" control mode** ([#153](https://github.com/Sese-Schneider/ha-cover-time-based/issues/153)): some momentary toggle relays have no dedicated stop button and instead stop the motor when the *opposite* direction is pressed while it's moving (a same-direction press just keeps it moving); reversing then takes two presses — opposite (stop), then press again to move. The existing **Toggle** mode assumes a same-button stop, and **Pulse** mode needs a dedicated stop relay, so hardware wired this way (e.g. an **Aqara T2** in momentary-pulse mode) had no matching option. **Toggle (opposite button)** shares Toggle's state machine and options — including **Relay reports its own OFF** — differing only in which button press is read as stop, and is configurable from the config card (EN/PT/PL) and as the `input_mode: toggle_opposite` YAML value. The docs now also make clear that **Pulse** mode's stop switch is required, not optional, and point covers with no stop relay at this new mode instead.
- **Native tilt & position forwarding for wrapped covers** ([#157](https://github.com/Sese-Schneider/ha-cover-time-based/issues/157)): a wrapped cover whose firmware positions its own slats — for example a Z-Wave venetian shutter such as a **Shelly Wave Shutter** — is now driven by forwarding its native tilt and position commands, with the time-based tracker kept only as a live display overlay. The earlier wrapped-tilt support ([#87](https://github.com/Sese-Schneider/ha-cover-time-based/issues/87)) simulates tilt by pulsing the main motor for a timed burst, which is right for covers that fake tilt that way but wrong for one that positions its slats itself: a tilt-close at a travel endpoint became a no-op, intermediate angles were unreachable, and the tracker drifted because nothing read back the angle the cover reported. For an **Inline**-tilt wrapped cover whose underlying entity advertises `set_cover_tilt_position` (and `set_cover_position`), set-/open-/close-tilt are now forwarded straight to the device — the display animates during the move and snaps to the cover's reported angle on settle — `set_cover_position` is forwarded too for device-accurate positioning, the tilt display sweeps to the direction endpoint during travel (venetian slats close going down, open going up) before syncing to the reported angle, and no relay stop is issued since the device holds itself at the target. This is auto-detected from the wrapped entity's supported features — no new configuration — and the existing opt-outs (`force_time_based_position`, `ignore_reported_position`, `reports_command_not_endpoint`) still force the timed path. Covers without native tilt support, and the **Sequential** / **Separate tilt motor** strategies, keep their existing timed behaviour unchanged.

### Fixes

- **Dual-motor covers: a travel press no longer disturbs a moving tilt motor** ([#156](https://github.com/Sese-Schneider/ha-cover-time-based/issues/156)): in **dual-motor** tilt mode the slats have their own motor that runs independently of travel. The open/close reversal guards (and the same-button **Toggle** external handler) decided whether an incoming travel command was a stop or a reversal from the cover-level opening/closing state, which folds in tilt motion — so pressing a travel button while the *tilt* motor happened to be moving read as "the cover is already moving that way" and stopped it, or inserted the direction-change settle delay before travel. On a wall-switch (externally triggered) press that stop is tracker-only — no relay is fired — so the tilt position tracker froze while the physical tilt motor kept running, desyncing the two, plus travel started a second late. Requires the rare combination of a separate tilt motor mid-move and a simultaneous cross-axis travel press, so it was easy to miss. These decisions now key off the **travel axis** only, so an independently moving tilt motor is left alone (a travel command's own tilt-to-safe pre-step still counts, keeping the in-motion-click and reverse behaviour there). **Inline** and **sequential** tilt — where the slats share the travel motor, so a tilt phase *is* the travel motor running — are unchanged and still settle before reversing.
- **Wrapped command-echo covers now stop cleanly at both endpoints** ([#152](https://github.com/Sese-Schneider/ha-cover-time-based/issues/152)): a wrapped cover with **Reports commands, not endpoints** enabled typically drives an *endstop-less* motor — one with no limit switches that simply stalls against the mechanical stop while powered (e.g. a Shelly 2PM Gen4 in cover profile driving a plain tubular motor). Wrapped mode inherited the base assumption that the motor self-stops at its limits, so at the 0%/100% endpoints it skipped the stop and let the motor run — stalling for seconds until the device's own max-time cutoff on every full open/close, and running to max-time when commanded to an endpoint it was already at. It now sends the endpoint stop for these command-echo covers, exactly as **Switch** mode already de-energizes its latched relay (set **Endpoint run-on time** to 0 to cut power the instant the endpoint is reached). Separately, `open_cover` while the cover is already parked fully open now no-ops instead of re-driving to the endpoint — mirroring `close_cover` at fully closed — so it no longer re-energizes the motor with a redundant relay pulse. Wrapped covers that report a real position, and the **Switch** / **Toggle** / **Pulse** relay modes, are unchanged — they keep resyncing the tracker at the endpoints as before.

## 4.7.2 (2026-07-01)

### Fixes

- **Inline tilt restore no longer overruns on short reversals** ([#147](https://github.com/Sese-Schneider/ha-cover-time-based/issues/147)): in **inline** tilt mode the slats share the main travel motor, so restoring tilt after a travel move (the integration overdrives tilt to an endpoint, travels, then reverses to the requested tilt) reverses that motor. The restore issued the opposite-direction command *instantly*, while the motor was still running from the travel phase — with no settling stop and no reversal delay. For a short restore pulse the follow-up stop then arrived while the relay was still mid-reversal and was dropped, so the motor ran on to its physical endpoint instead of stopping at the restored tilt (long restores completed correctly). The restore now stops the motor and waits out the direction-change settle delay before commanding the reverse direction — the same reversal handling a normal travel direction-change already uses — so the stop is honoured and the cover holds the restored tilt. A stop (or a new movement command) issued *while a tilt restore is starting up* — during the inline settle delay, or during the dual-motor restore's stop-travel / tilt-motor-start step — now cancels the pending restore instead of being overridden when the restore resumes and re-starts the motor.

## 4.7.1 (2026-06-30)

### Fixes

- **Inline tilt at a parked endpoint no longer rolls the cover fully open/closed** ([#142](https://github.com/Sese-Schneider/ha-cover-time-based/issues/142)): the companion to [#125](https://github.com/Sese-Schneider/ha-cover-time-based/issues/125). In **inline** tilt mode the slats are articulated by the main travel motor, so a tilt move adjusting the slats while the cover is parked at a travel endpoint (fully open or fully closed) drives the motor *off* its limit switch. #125 fixed the run-on overshoot for **Switch** mode, but the self-stopping modes (**Toggle**, **Pulse** and **wrapped** covers) took a different branch: at an endpoint they skip the stop entirely, assuming the motor is still seated against its physical limit and self-stops there. For a tilt move that assumption is wrong — the motor has just been driven off the limit — so the stop was never sent and the cover ran on to the full endpoint (e.g. tilting the slats open while fully closed rolled the blind all the way up). The stop is now sent for tilt moves at an endpoint in these modes (mirroring the run-on exclusion #125 added), so the motor stops at the requested tilt; real *travel* moves to an endpoint still skip the redundant stop as before.

## 4.7.0 (2026-06-29)

### Features

- **Wrapped covers: new "Reports commands, not endpoints" option for command-echo devices** ([#137](https://github.com/Sese-Schneider/ha-cover-time-based/issues/137)): some underlying covers report their state as the *last command* rather than the actual position — notably single-DP Tuya roller-shutter modules (a `control` enum of open/close/stop, with no `current_position` and no `opening`/`closing` transition). They report `open` when open was commanded, `closed` when close was commanded, and `unknown` when stopped. The integration read that `closed` as the 0% endpoint and snapped the position to 0 on the close *press*, so a manual stop mid-travel was recorded as fully closed — a cover parked at ~70% jumped to closed (the issue's symptom). A new per-cover wrapped-cover option, **Reports commands, not endpoints** (default **off**, the unchanged behaviour), treats the wrapped entity's reported state as an open/close/stop *command* and tracks position purely by time, never snapping to an endpoint: `open`/`opening` → timed open, `closed`/`closing` → timed close, `unknown` → stop (freeze at the current time-based position), and `unavailable`/other → ignored. So a close press starts a timed close and a stop press freezes the cover where it is instead of snapping to 0. It is a deliberate opt-in rather than auto-detected: whether a device reports real transient moving states cannot be read from `supported_features`, and a runtime heuristic can't tell a command-echo device from an honest binary cover that only reports `closed` at the end of travel. Configurable from the config card (EN/PT/PL) and as the `reports_command_not_endpoint` YAML option.

## 4.6.0 (2026-06-28)

### Features

- **New per-cover setting — "Send stop signal at endpoints" (Pulse mode)** ([#133](https://github.com/Sese-Schneider/ha-cover-time-based/issues/133)): "Pulse" mode actually serves two physically opposite momentary controllers, and the 4.5.3 fix for [#129](https://github.com/Sese-Schneider/ha-cover-time-based/issues/129) — which made the endpoint stop **unconditional** — is right for one and wrong for the other. A **latching** controller keeps running until it receives a dedicated stop pulse, so it *needs* the endpoint stop or it gets stuck "moving" (the #129 case). An **auto-stop** controller halts itself at its 0%/100% limit switches, and a stop pulse received *while already stopped* is read as "go to favourite/preset position" (classic Somfy "my" behaviour) — so for that hardware every limit hit silently repositioned the cover (the #133 regression). Tuning the run-on delay can't help: the motor has already self-stopped, so *any* stop pulse arrives "while stopped". A new per-cover option, **Send stop signal at endpoints** (default **on**, the unchanged 4.5.3 behaviour), can be turned **off** for auto-stop controllers so the endpoint stop pulse is not sent at all; the same flag also governs a separate **tilt motor**'s endpoint stop. Configurable from the config card (EN/PT/PL) and as the `send_endpoint_stop` YAML option. As a related cleanup, the **Endpoint run-on time** field is now also shown for pulse covers that send the endpoint stop (it was silently using the 2.0s default and was unconfigurable from the card). **Switch**, **Toggle** and **wrapped-cover** modes are unchanged; the default keeps #129 fixed out of the box.

## 4.5.3 (2026-06-27)

### Fixes

- **Pulse mode sends the endpoint stop again** ([#129](https://github.com/Sese-Schneider/ha-cover-time-based/issues/129)): the 4.4.0 "no endpoint stop for self-stopping motors" change was too broad — it lumped **Pulse** mode in with Toggle, but the two are not the same. Toggle's "stop" re-pulses the *direction* relay (which would restart the motor), so skipping it there is correct; Pulse mode has a **dedicated stop relay** (a stop switch is required), and its momentary controller *latches* the direction command and keeps running until it receives that stop pulse. With the stop skipped at 0%/100%, the controller was left stuck "moving" — the cover only responded after several clicks, the Stop was never delivered, and the physical wall/PLC buttons appeared blocked while the controller thought it was still running. Pulse mode now pulses its stop relay at the endpoints again (deferred by **Endpoint run-on time** if configured), exactly as it did in 4.3.0; because the stop is a separate relay, it can never restart the motor. The same applies to a **separate tilt motor** — its tilt-stop relay is pulsed at the tilt endpoints too. **Toggle** and **wrapped-cover** modes are unchanged.

## 4.5.2 (2026-06-24)

### Fixes

- **Inline tilt no longer overshoots when the cover is parked at an endpoint** ([#125](https://github.com/Sese-Schneider/ha-cover-time-based/issues/125)): in **inline** tilt mode the slats are articulated by the main travel motor, so a tilt move drives the same relay as travel. When the cover was parked at a travel endpoint (fully open or fully closed) — the usual case when adjusting slats — a tilt move that finished there was wrongly given the **endpoint run-on**, a *travel* concept that keeps a latched relay energized so the shutter seats against its physical limit. The result: a 50% tilt that should take 0.75s (half of a 1.5s tilt time) ran for ~2s, the run-on default, overdriving the slats and starting to move the cover off the endpoint. Run-on is now suppressed for tilt moves, so the relay de-energizes as soon as the tilt target is reached. **Switch** mode is the only mode affected (it is the only one that runs on at an endpoint); travel moves to an endpoint still run on as before so the shutter seats correctly.

## 4.5.1 (2026-06-22)

### Fixes

- **Toggle mode with “Relay reports its own OFF” off: restart no longer phantom-opens the cover** ([#105](https://github.com/Sese-Schneider/ha-cover-time-based/issues/105)): a relay configured as not self-reporting its OFF (an **Aqara T2** in hardware-pulse mode, the case the 4.5.0 option addresses) pulses and physically releases but never tells Home Assistant, so its switch entity stays stuck `on`. On a restart — or a Zigbee/Z2M reconnect — the entity reappeared as `unavailable → on`, which the integration mistook for a fresh button press and started a phantom movement: tracked all the way to an endpoint but with **no relay actually fired**, so the reported position silently diverged from the physical cover (for example showing fully open while the cover is closed). That stale-reappearance edge is no longer treated as a command for these relays, since there is no way to reconstruct whether or when a real press happened while Home Assistant was down. Only this configuration is affected — relays that report their OFF come back `off` on restart, so every other mode and the default toggle behaviour are unchanged.

## 4.5.0 (2026-06-22)

### Features

- **Toggle mode: option for relays that pulse but never report their OFF** ([#105](https://github.com/Sese-Schneider/ha-cover-time-based/issues/105)): the 4.4.0 toggle-mode change drives a still-reported-ON relay OFF before pulsing it ON, to guarantee a clean rising edge. On hardware-managed pulse modules — for example an **Aqara T2** in its 200 ms internal-pulse mode — that pulse the contact themselves but never report the OFF back to Home Assistant, the switch entity stays stuck `on`, so a `turn_off` is not an idempotent "off" but another activation pulse. The integration's clean-edge attempt then lands as a doubled command and the motor's toggle counter drifts — the symptom is Stop reversing the cover and Up driving it down. A new per-cover toggle-mode option, **Relay reports its own OFF** (default **on**, the unchanged 4.4.0 behaviour), can be turned **off** for such modules: toggle mode then only ever sends a single `turn_on` per command and never a `turn_off`, giving exactly one clean activation per press. Configurable from the config card (EN/PT/PL) and as the `relay_reports_off` YAML option.

## 4.4.0 (2026-06-18)

### ⚠ Breaking changes

- **No endpoint stop or run-on for self-stopping motors** ([#105](https://github.com/Sese-Schneider/ha-cover-time-based/issues/105)): in **Pulse**, **Toggle** and **wrapped-cover** modes the integration no longer sends a relay stop — nor applies endpoint run-on — when a cover reaches the 0%/100% endpoints. These motors stop themselves at their internal limit switches, so the stop was redundant; in **Toggle** mode it was actively wrong, re-pulsing the direction relay and restarting the just-stopped motor (the movement-after-every-full-open/close some users saw). The same now applies to a **separate tilt motor** at its tilt endpoints. **Switch** mode is unchanged — its direction relay is latched ON for the whole movement, so it is still switched off (with run-on) at the endpoint.

  **Migration:** no action is required and no settings are lost. The **Endpoint run-on time** option now applies to **Switch mode only**; it is hidden in the config card for the other modes, and any value previously set on a pulse/toggle/wrapped cover is simply ignored. Mid-travel and mid-tilt stops are unaffected. Sequential closes-then-tilts modes still stop at the closed (0%) endpoint, where the motor is deliberately driven past cover-closed to articulate the slats.

### Features

- **Up/down interlock for switch mode** ([#99](https://github.com/Sese-Schneider/ha-cover-time-based/issues/99)): in switch (latching relay) mode, when the integration observes one direction relay turn ON from outside Home Assistant — for example a decoupled wall switch, or the physical switch wired straight to the relays — it now turns the opposite direction relay OFF. This covers both the travel (up/down) relays and, on dual-motor covers, the tilt relays, so two opposing relays are never energized at once even on motors with no hardware interlock. The integration already did this when *it* drove the relays; this extends the same protection to externally-triggered changes. Pulse and toggle modes are unaffected, since they don't hold a direction relay on.

### Fixes

- **Switch mode de-energizes after an external open/close** ([#99](https://github.com/Sese-Schneider/ha-cover-time-based/issues/99)): in switch (latching relay) mode, a movement started from outside Home Assistant — for example toggling the relay's own switch entity, or a wall switch wired straight to it — was tracked to the endpoint but its latched direction relay was never switched off, leaving the motor energized at the limit. Reaching the endpoint now turns that relay off (only the direction still on, never the opposite — and the dual-motor tilt relay likewise), matching what the integration already did for moves it drives itself. Pulse, toggle and wrapped-cover modes are unaffected, since their relays self-release.
- **Dual-motor switch mode: reversing the tilt no longer swallows the next press** ([#99](https://github.com/Sese-Schneider/ha-cover-time-based/issues/99)): with a separate tilt motor in switch mode, reversing the tilt from outside HA (e.g. tilt-open then tilt-close on the switch entities) left a stale state-change echo queued on the just-released relay, so the *next* external tilt command in the original direction was silently ignored. Externally-triggered tilt-motor moves now only track the motion — the relay is already driven from outside HA — instead of re-firing it, so every press is honoured.
- **Dual-motor switch mode: external cover-open from closed completes in one press** ([#99](https://github.com/Sese-Schneider/ha-cover-time-based/issues/99)): opening the cover from fully closed via the external switch entity ran the tilt-to-safe pre-step and then stalled, needing a second press to actually travel. Externally-triggered multi-phase moves now continue from the pre-step into the travel phase (and travel pre-step into tilt) the same way UI-initiated moves do.
- **Switch mode: re-driving an already-on relay no longer swallows the next switch event** ([#99](https://github.com/Sese-Schneider/ha-cover-time-based/issues/99)): the open/close relay senders queued a state-change echo even when the relay was already on — so no event actually fired and the orphaned echo silently swallowed the *next* real switch event. The visible symptom: after an externally-started open continued into travel, switching the relay back off to stop the cover did nothing and it kept opening. The senders now queue an echo only when the relay will actually change state (matching the tilt senders).
- **Separate tilt motor no longer nudges the travel motor** ([#105](https://github.com/Sese-Schneider/ha-cover-time-based/issues/105)): completing a tilt-only move on a separate-tilt-motor cover previously fell through to the travel stop and re-pulsed the *travel* relay (off a stale last-command), while never issuing a proper tilt stop. Tilt completions now settle the tilt motor directly.
- **Toggle mode no longer uses Pulse time** ([#105](https://github.com/Sese-Schneider/ha-cover-time-based/issues/105)): toggle-style relays are momentary — a brief press latches the motor and the relay releases itself — so holding the relay ON for the configured **Pulse time** served no purpose. Toggle covers now send a single switch-on per command (briefly switching the relay off first only when it is still reported ON, to guarantee a clean rising edge) and the **Pulse time** option is hidden for toggle mode. **Pulse** mode is unchanged and still uses Pulse time. If you had set a pulse time on a toggle cover it was doing nothing useful, so no action is needed.

## 4.3.0 (2026-06-17)

### Features

- **Configurable assumed state per cover** ([#97](https://github.com/Sese-Schneider/ha-cover-time-based/issues/97)): a time-based cover dead-reckons its position from travel time with no feedback from the hardware, so Home Assistant treated it as an *assumed state* device — keeping both the open and close controls active at all times. A new device-level **Assumed state** option lets you turn that off when you trust your calibration (for example a wrapped Shelly that reports no position), so Home Assistant greys out actions that can't apply, such as *close* when the cover is already closed. It defaults to **on** for every existing cover, so there's no change unless you opt out, and it's configurable from the config card in all control modes (switch, pulse, toggle, and wrapped). The device-tab toggles also gained click-to-open info tooltips (touch-friendly) behind a `(?)` icon.

### Fixes

- **Rapid toggle presses no longer desync the position** ([#100](https://github.com/Sese-Schneider/ha-cover-time-based/issues/100)): on toggle-mode covers, pressing open/close/stop faster than the configured pulse time apart could leave the physical motor untouched while the integration began tracking a movement — the reported position then drifted away from where the cover actually was. Each pulse now guarantees a real relay edge (briefly driving the relay off first when a previous pulse is still in flight) so the motor reliably acts on every press.

## 4.2.0 (2026-06-02)

### Features

- **Tilt support for wrapped covers without native tilt** ([#85](https://github.com/Sese-Schneider/ha-cover-time-based/issues/85)): the **Inline** and **Sequential** tilt modes are now available when wrapping an existing cover, even if that cover only exposes open/close/stop. These modes drive the wrapped cover's normal open/close commands, so they work on any cover — previously the tilt options were hidden unless the wrapped cover reported native tilt support. The **Separate tilt motor** mode still requires native tilt support (it delegates the tilt commands to the wrapped entity), so it remains hidden until the selected cover advertises it.
- **Ignore reported position (wrapped covers)**: a new option to track position purely by time and ignore the `current_position` the wrapped cover reports. Enable it for covers that report an unreliable position (the fully-closed endpoint is still trusted).
- **Forward set-position to wrapped covers with native position support** ([#93](https://github.com/Sese-Schneider/ha-cover-time-based/issues/93)): when a wrapped cover supports `set_cover_position`, the integration now sends the set-position command straight to it instead of approximating it with timed open/close/stop — so the cover stops at the requested position even when the underlying device has no `stop` service. The time-based tracker still animates during the move so the position updates live for covers that only report their position once they settle. **Stop** on such a cover is implemented by setting the underlying cover to the integration's calculated position. A new **Force time-based positioning** option keeps the old timed behaviour for covers whose native set-position is unreliable.
- **Detect unavailable relays / targets** ([#89](https://github.com/Sese-Schneider/ha-cover-time-based/issues/89)): the cover now reports as **unavailable** whenever any of its underlying target entities (the switches, buttons, scripts, or wrapped cover that drive it) is unavailable — for example an MQTT relay going offline. Commands that would *start* movement in a direction whose target is unavailable are rejected instead of silently running the time-based simulation and drifting the reported position. Stopping is always allowed, so a cover can still be halted even while a target is offline.

### Fixes

- A wrapped cover configured with **Separate tilt motor** but whose underlying entity doesn't support tilt (e.g. a stored or hand-edited config, or a cover that dropped tilt support) no longer fires `*_cover_tilt` services at it; the unsupported command is skipped and logged instead.
- Selecting the separate-tilt-motor mode is no longer reset when the chosen wrapped cover is merely unavailable — the tilt config is only cleared once the cover is confirmed available without tilt support.

## 4.1.0 (2026-05-30)

### Features

- **Use scripts as open/close/stop switches in Pulse mode** ([#82](https://github.com/Sese-Schneider/ha-cover-time-based/issues/82)): the open, close, and stop targets (and the dual-motor tilt targets) can now be `script` entities as well as `switch` entities when the control mode is **Pulse** — handy for covers driven by IR remotes, where each script fires an open/close/stop command. Switch and Toggle modes still require `switch` entities, since they rely on a held on-state a script can't provide. Note that a script still running when the configured **Pulse time** elapses will be stopped.

## 4.0.0 (2026-05-23)

If you're coming from v2.3.2, this is essentially a new integration.

Cover Time Based controls any motor-driven cover from Home Assistant, even when the cover hardware itself can't report its position. It tracks where the cover is by timing how long the motor has been running — and v4 makes that a lot more capable, and a lot easier to live with.

What you get:

- **Configure everything from a dashboard card.** No more YAML. Add a cover under **Settings → Devices & Services → Helpers**, then tune every setting from a built-in card on your dashboard.
- **Calibrate at the click of a button.** Start the motor, let it run, hit stop — the card figures out your travel and tilt times for you.
- **Works with whatever hardware you have.** Latching relays, momentary push-buttons with a separate stop switch, single-button "toggle" controllers, or any existing cover entity you'd like to add position tracking to.
- **Real tilt support.** Venetian blinds, conventional shutters, inverted shutters, and covers with a separate tilt motor — pick the mode that matches your hardware.
- **Stays in sync with physical buttons.** Wall switches and automations driving the motor outside Home Assistant don't throw the position tracker off any more.
- **Survives restarts.** Positions are saved properly and reloaded — even after unexpected shutdowns.
- **Lots of fine-tuning options** for awkward motors: startup delays, minimum movement times, endpoint resync, and more.
- **Translated** into English, Portuguese, and Polish.

### Upgrading from v2.3.2

Your existing YAML configuration still works with a deprecation warning. When you have a moment, recreate your covers via the helper flow so you can manage them through the UI from then on.

This release also includes a long list of smaller fixes, especially around wrapped covers, sequential tilt strategies, and toggle-mode button handling.

## 3.0.0 (2025-12-10)

### Features

- **Synchronized travel and tilt movements**: Travel and tilt now move proportionally on the same motor, accurately simulating real blind mechanism behavior
- **Automatic position constraints**: Tilt automatically resets to correct position at travel endpoints (0% horizontal at fully open, 100% vertical at fully closed)
- **Optional endpoint delay (`travel_delay_at_end`)**: Configurable relay delay at endpoint positions for covers with mechanical endstops, allowing position reset through endstop contact
- **Minimum movement time (`min_movement_time`)**: Optional parameter to prevent position drift by blocking relay activations too brief to physically move the cover
- **Polish translation**: Added Polish language support
- **Motor startup delay compensation (`travel_startup_delay`, `tilt_startup_delay`)**: Optional parameters to compensate for motor inertia by delaying position tracking after relay activation, improving position accuracy for short movements
- **Default values (`defaults`)**: Optional section to define default timing parameters for all devices, reducing configuration duplication

### Improvements

- Travel and tilt movements are now time-synchronized and stop simultaneously
- Movements to endpoint positions (0% or 100%) always allowed regardless of minimum movement time constraint
- Delay task properly cancelled when new movements initiated
- Enhanced position accuracy through mechanical constraint enforcement

### Bug Fixes

- Fixed simultaneous travel and tilt operations not properly stopping each other when needed
- Improved mutual exclusion between travel and tilt movements
- Fixed endpoint delay not properly stopping relay when starting new movement in opposite direction
- Fixed position calculation using stale data after stopping movement during direction change

## 2.3.2 (2025-07-09)

### Bug Fixes

- Bump xknx (@bernardesarthur)


## 2.3.1 (2025-05-01)

### Bug Fixes

- Internal position flipped after restart (@gbasile)


## 2.3.0 (2025-03-27)

### Features

- Add support for existing cover entities

### Bug Fixes

- Internal position state is flipped after `xnkx` update


## 2.2.0 (2025-03-24)

### Features

- Add support for button based cover controls (#17)

### Bug Fixes

- current_position is None comparison exceptions (#18)
- Update `xknx` to latest version
- Update service schema for 2025.09


## 2.1.1 (2024-04-17)

### Bug Fixes

- Fix `stop_switch_entity_id` not being present causing the integration to crash


## 2.1.0 (2024-04-11)

### Features

- Add optional `stop_switch_entity_id` for stopping the cover

### Bug Fixes

- Fix an issue where the integration would not load when the tilting entities were not present
- Fix check for tilt support when stopping (#7)


## 2.0.1 (2024-01-05)

### Bug Fixes

- Fix `hacs.json` & `manifest.json` for HACS support


## 2.0.0 (2023-10-06)

### Features

- Add tilt support
- HACS support

## 1.0.0 (2023-10-02)

### Features


- Initial Release based on [davidramosweb/home-assistant-custom-components-cover-time-based](https://github.com/davidramosweb/home-assistant-custom-components-cover-time-based)
