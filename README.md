# Cover Time Based

A Home Assistant integration that controls and tracks a cover's position using travel time.

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sese-Schneider&repository=ha-cover-time-based&category=integration)
[![Active Installations][installations-shield]](https://analytics.home-assistant.io/)
[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)

![Project Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]

Many covers have no way of reporting where they are: a roller shutter on a plain
relay knows only "open" and "closed", if that. This integration works out the
position from how long the motor has been running, so a cover with no position
sensor of its own can still report where it is and be sent to any point in
between. It adds tilt control on top, and a visual card for setting everything
up and calibrating the timings.

It is maintained by [@Sese-Schneider](https://www.github.com/Sese-Schneider) and
builds on the original
[cover-time-based](https://github.com/davidramosweb/home-assistant-custom-components-cover-time-based/)
component by davidramosweb.

## Contents

- [Features](#features)
- [Installation](#installation)
- [Quick start](#quick-start)
- [The configuration card](#the-configuration-card)
- [Configuration](#configuration)
  - [Control Mode](#control-mode)
  - [Wrapping an existing cover](#wrapping-an-existing-cover)
  - [Controlling a cover with switches](#controlling-a-cover-with-switches)
  - [Controlling a cover with a single button](#controlling-a-cover-with-a-single-button)
  - [Tilt](#tilt)
  - [Options for every cover](#options-for-every-cover)
- [Calibration](#calibration)
- [Services](#services)
- [Troubleshooting](#troubleshooting)
- [Advanced hardware notes](#advanced-hardware-notes)
- [YAML configuration (deprecated)](#yaml-configuration-deprecated)

## Features

- **Time-based position tracking.** Estimates the position from how long the
  cover has been moving, so covers with no position feedback can still be sent
  to any position.
- **Follows physical operation.** Notices when a wall switch, remote, or another
  integration moves the cover, and keeps its own estimate in step.
- **Motor-safe interlock.** In Switch mode it never energises both direction
  relays at once. Turning one direction on, even from a wall switch wired
  straight to the relays, switches the other off, which protects motors that
  have no hardware interlock of their own.
- **Works with many kinds of hardware.** Latching switches, momentary pulse
  buttons, and toggle-style relays are all supported.
- **Wraps an existing cover.** Adds time-based position, and optional tilt, to
  any cover entity that lacks it.
- **Tilt control.** Drives venetian-style slats using either the main travel
  motor or a separate tilt motor.
- **Built-in calibration.** Measures travel and tilt times from the card,
  including a fine startup adjustment that keeps short movements accurate.
- **Self-correcting at the endpoints.** Every time the cover is sent fully open
  or closed it reaches a known position, which resyncs the estimate.

## Installation

This integration is available through [HACS](https://hacs.xyz/). In HACS, search
for **Cover time based** and install it, then restart Home Assistant.

Alternatively, click the button below:

[![Open the Cover Time Based repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sese-Schneider&repository=ha-cover-time-based&category=integration)

## Quick start

1. **Create a cover.** In Home Assistant, open **Settings → Devices & Services →
   Helpers**, click **Create Helper**, pick **Cover Time Based**, and give it a
   name.
2. **Add the configuration card** to a dashboard (see
   [The configuration card](#the-configuration-card) for the steps).
3. **Describe your hardware.** On the card's **Device** tab, choose a
   [Control Mode](#control-mode) and select the switches or cover entity it uses.
4. **Calibrate.** On the **Calibration** tab, set the current position and
   [measure the travel times](#calibration).

That is enough to get a working cover. The sections below cover every option in
detail.

## The configuration card

The configuration card is a visual interface for every setting, and it can
measure your cover's timings for you. You need an administrator account to use
it; for anyone else its commands are rejected. It has two tabs, **Device** and
**Calibration**; fill in the Device tab first, as the Calibration tab depends on
it. The card remembers the last cover you were working on and reselects it next
time the dashboard loads. (That memory is kept per browser rather than per Home
Assistant user, and a cover you have since deleted is simply not restored.)

To add the card to a dashboard:

1. Open **Settings → Dashboards** and either open an existing dashboard or create
   a new one.
2. Click the **Edit dashboard** (pencil) icon in the top right, then add a new
   card.
3. In the card picker, switch to the **By card** tab. (In Home Assistant 2026.6
   and later the picker opens on **By entity**, where this card does not appear.)
4. Search for **Cover time based configuration**, select it, and click **Save**.
5. Click **Done** to stop editing.

> [!IMPORTANT]
> **Create a cover before you add the card.** The card ships as a frontend asset
> of the integration, and Home Assistant only loads that asset once at least one
> cover exists. If you add the card first, the dashboard shows a red
> **Configuration error** instead. See
> [the card does not appear](#the-card-does-not-appear) if you hit this.

## Configuration

Every setting lives on the configuration card's **Device** tab. The first
choice, **Control Mode**, tells the integration how it drives your cover, and
the rest of the options on the tab change to match it.

### Control Mode

| Control Mode | Choose it when |
| --- | --- |
| **Wrap an existing cover entity** | You already have a working cover entity and want to add time-based position, and optionally tilt, on top of it. |
| **Switch (latching)** | Two relays, one to open and one to close, that stay on for the whole movement and stop when switched off. |
| **Pulse (momentary)** | Push-button relays, where a brief on/off pulse starts the motor. Needs a separate stop button. |
| **Toggle (same button)** | A brief pulse starts the motor, and a second pulse on the same button stops it. |
| **Toggle (opposite button)** | A brief pulse starts the motor, and pressing the opposite direction stops it. There is no separate stop button. |
| **Single button (cycling)** | One input drives the whole motor: each press advances a fixed down → stop → up → stop cycle, and the motor stops itself at its limits. There is no separate open, close, or stop control. |

The card only ever shows the options that apply to the mode you pick, so this
table is the quickest way to see what each mode offers. Follow a link for the
detail. A blank cell means the option is not shown for that mode.

| Option | Wrapped | Switch | Pulse | Toggle | Toggle (opp.) | Single button |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| [Cover entity](#wrapping-an-existing-cover) | ✓ | | | | | |
| [Open and Close switch](#controlling-a-cover-with-switches) | | ✓ | ✓ | ✓ | ✓ | |
| [Stop switch](#controlling-a-cover-with-switches) | | | ✓ | | | |
| [Button](#controlling-a-cover-with-a-single-button) | | | | | | ✓ |
| [Position reporting](#position-reporting) | ✓ | | | | | |
| [Force time-based positioning](#force-time-based-positioning) | ✓ | | | | | |
| [Invert position](#invert-position) | ✓ | | | | | |
| [Pulse time](#pulse-time) | | | ✓ | | | ✓ |
| [Relay reports its own OFF](#relay-reports-its-own-off) | | | | ✓ | ✓ | |
| [Send stop signal at endpoints](#send-stop-signal-at-endpoints) | | | ✓ | | | |
| [Wait for relay confirmation](#wait-for-relay-confirmation-before-tracking) | | ✓ | ✓ | ✓ | ✓ | ✓ |
| [Resync](#cover_time_basedresync) | | | | | | ✓ |
| [Assumed state](#assumed-state) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| [Always re-send at the endpoints](#always-re-send-openclose-at-the-endpoints) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| [Fully open before position (Beta)](#fully-open-before-moving-to-a-position-beta) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| [Tilt](#tilt) | ✓ | ✓ | ✓ | ✓ | ✓ | |

The switch-based modes (Switch, Pulse, and the two Toggle modes) are described
together under
[Controlling a cover with switches](#controlling-a-cover-with-switches).
The single-button mode is different enough — one input, no independent
direction — that it gets its own section:
[Controlling a cover with a single button](#controlling-a-cover-with-a-single-button).

### Wrapping an existing cover

Choose **Wrap an existing cover entity** and select the **Cover Entity** you
want to extend. This suits covers that can already open, close, and stop but do
not report their position.

#### Position reporting

A wrapped cover may report a position you can trust, a position you cannot, or
nothing useful at all. The **Position reporting** setting tells the integration
how much to believe it. Pick the profile that matches your hardware.

| Profile | Choose it when |
| --- | --- |
| **Reliable position feedback** _(default)_ | The cover reports a trustworthy position and reaches its real open and closed endpoints. Leave it here unless the tracked position drifts from where the cover actually is. |
| **Position unreliable — track by time** | The cover reports a position, but you cannot trust it. The reported position is ignored and everything is tracked by time, although a reported "closed" is still trusted as the fully-closed point. |
| **No real endpoints — reports open/closed when stopped** | The cover has no real position feedback and reports "open" or "closed" whenever the motor stops anywhere, not only at the ends. Those reports are ignored, so stopping mid-travel does not snap the position to 0%. |
| **State mirrors the last command** | The cover has no position feedback and simply echoes the last command: "open" while opening, "closed" while closing, and "unknown" when stopped, as some single-channel Tuya shutters do. Each state is read as an open, close, or stop command and tracked by time. |
| **Ignore all device reports** | The cover reports nothing you can trust. It sends a false position as well as spurious open, closed, opening, or closing states while sitting idle, so that even _No real endpoints_ still snaps to the bogus position it believes. Every report from the device is ignored and the position is tracked purely by the timers. Home Assistant becomes the only way to move the cover, and operating it from a wall switch or remote is not tracked. |

<details>
<summary><strong>Choosing between no-real-endpoints and state-mirrors-last-command</strong></summary>

The last two profiles both suit covers with no position feedback, but they treat
the device's reports very differently.

**No real endpoints** _ignores_ the device's open/closed reports and relies
entirely on its own timers. Choose it for modules that periodically re-send a
stale or false "open" or "closed" while sitting idle: the spurious report is
dropped rather than triggering a phantom move.

**State mirrors the last command** does the opposite: it reads _every_ reported
state as a command. That is exactly right for a device whose state is only ever a
command echo, but it means an unsolicited "open" or "closed" sent while the cover
is idle would start a phantom move in that direction. If your module sends
periodic or false updates when nothing is moving, use **No real endpoints**
instead.

If even **No real endpoints** still snaps the position, the device is also
reporting a false position number alongside its state. **Ignore all device
reports** is the strictest profile for that case: it ignores everything the
device sends, the reported position included, and drives the cover purely from
the timers.

Because a **State mirrors the last command** cover has no endpoint feedback, and
in practice drives a motor with no internal limit switch, the integration also
sends an explicit **stop** when the cover reaches 0% or 100% rather than assuming
the motor stops itself there. It treats an open or close command issued while the
cover is already parked at that endpoint as doing nothing. Set
[Endpoint run-on time](#endpoint-run-on-time) to 0 for such a motor, so it is
de-energised the instant it reaches the endpoint. If the cover can also be moved
by an external remote, so "already parked there" may not be true, turn on
[Always re-send open/close at the endpoints](#always-re-send-openclose-at-the-endpoints)
to drive the command through anyway.

</details>

#### Force time-based positioning

If the wrapped cover supports setting a position of its own, the integration
normally passes a set-position command straight through to it, so the cover
stops exactly where you asked even if it has no stop service. Turn **Force
time-based positioning** on to ignore that native support and drive the cover
with timed open, close, and stop movements instead. Use it when the cover's own
set-position is unreliable.

#### Invert position

Some covers run backwards compared with a normal cover. An awning is the classic
example: its underlying entity reports "open" when the awning is fully extended
and shading, and "closed" when it is rolled away. Turn **Invert position** on to
flip the axis, so the time-based cover reports the opposite position and swaps
its open and close commands. This affects position only, not tilt, and is meant
for position-only covers such as awnings and shutters. Leave it off for a
normally-oriented cover.

Wrapped covers have a few more behaviours worth knowing about, such as how they
follow physical wall switches and when a cover positions itself natively. Those
are covered under [Advanced hardware notes](#advanced-hardware-notes).

### Controlling a cover with switches

Choose one of the four switch modes, then select the relays that drive the
motor: an **Open switch** and a **Close switch**, plus a **Stop switch** in Pulse
mode.

In Pulse mode these entities may be `script` entities as well as switches, which
suits IR-controlled covers where each script fires an open, close, or stop
command. The other modes need real `switch` entities, because they rely on the
switch reporting a held, latched on-state that a script (which returns to `off`
by itself) cannot provide.

#### Pulse time

In **Pulse** mode, **Pulse time** is how long the switch is held on before it is
turned off again; in **Single button** mode it is how long each press holds the
button. It defaults to **1 second**. The Toggle modes do not use it, since a
toggle relay releases itself after its own brief pulse.

> [!NOTE]
> Keep any Pulse-mode scripts short. When the pulse time elapses the integration
> turns the entity off, which cancels a script still running, so a script whose
> own internal delay is longer than the pulse time would be cut off partway.

#### Relay reports its own OFF

Applies to both Toggle modes. Leave it **on** for normal toggle relays, which
switch themselves off after a pulse and report that off back to Home Assistant.
Turn it **off** for hardware-managed pulse modules, such as an **Aqara T2** in
its internal-pulse mode, that pulse the contact themselves but never report the
off, leaving the switch entity stuck on. On that hardware a "turn off" is really
another activation pulse, so with the option off the integration only ever sends
a single on command per press, giving exactly one clean activation each time.

#### Wait for relay confirmation before tracking

Available in every switch mode. Normally the position timer starts the moment a
command is sent. On a slow or cold Zigbee or Z-Wave mesh the command can take a
second or two to actually reach the relay, and that delay is then wrongly counted
as travel, so the tracked position runs ahead of the cover. Turn this **on** to
start the timer only when the relay reports that it has switched on. If the
relay never confirms at all, the timer starts anyway, counted from when the
command was sent. Leave it **off** unless the position drifts on a cover whose
relay responds slowly.

> [!NOTE]
> On the two **Toggle** modes a stop is a tap on the driving relay rather than a
> guaranteed off, so a stop you press before the relay confirms is held back
> until the confirmation arrives — or until the wait times out — and only then
> tapped out. It is no longer swallowed. A *reversal* is not held back: if you
> send the cover the other way before the confirmation has arrived, the relay
> is tapped immediately.

#### Send stop signal at endpoints

Applies to **Pulse** mode. Leave it **on** for controllers that keep the motor
running until they receive a separate stop pulse; without a stop at the endpoint
they stay stuck "moving", and the cover only responds after several clicks while
the physical buttons appear blocked. Turn it **off** for controllers that stop
themselves at their own limit switches, where a stop pulse arriving after the
motor has already stopped is instead read as "go to the favourite position" (the
classic Somfy _my_ behaviour) and repositions the cover on every limit hit. The
same setting governs a [separate tilt motor's](#tilt) stop relay at its tilt
endpoints.

### Controlling a cover with a single button

Choose **Single button (cycling)** for a motor with only one control input — no
separate open and close relays, just one line to pulse. Select the switch or
`script` entity that drives it as the **Button**. Each press advances a fixed
cycle, and the motor stops itself at its physical limits:

| The cover is... | The next press... |
| --- | --- |
| at the closed limit | starts it opening |
| opening | stops it |
| stopped, was opening | reverses it and starts closing |
| at the open limit | starts it closing |
| closing | stops it |
| stopped, was closing | reverses it and starts opening |

This suits motors with an "impulse" or "button" input rather than independent
open/close relays — for example a **Jarolift TDEF** shutter driven through its
external button line by a Shelly relay, or a **Hörmann** garage door operator's
impulse trigger. The integration turns an open, close, or stop command into
however many presses the cycle needs, a second apart. Reversing part-way
through a movement sometimes means one brief press the wrong way before the
motor stops and turns around, which is quicker than driving all the way to the
far end.

> [!WARNING]
> **This mode has no position or direction feedback.** The integration works
> out where the cover is only from what it last told the motor to do, and
> cannot see whether the cover actually got there. Read the notes below before
> relying on it, especially if the cover can also be moved by an RF remote or
> the button itself.

#### Setting the starting position

Every press is planned from where the integration believes the cover is, so
that has to be right to begin with. The first time you set up a cover in this
mode, either **fully close it** before using it — the assumed starting point —
or call the [`resync`](#cover_time_basedresync) action to tell the integration
its true state. Skip this and it is guessing from the start.

#### What to expect

- **Every position is an estimate.** With no feedback, the integration counts
  time rather than reading the cover.
- **A full open or close corrects timing drift** by snapping the position to
  the endpoint once the motor has had time to get there. How long it waits past
  the estimated arrival is the [Endpoint run-on time](#endpoint-run-on-time),
  which here acts as a settle margin rather than a relay hold.
- **Only [`resync`](#cover_time_basedresync) fixes a wrong starting point.** If
  the integration has the cover wrong to start with — thinks it is closed when
  it is open — every command afterwards is planned backwards and the positions
  come out inverted. A full open or close will not straighten this out; it just
  anchors the wrong end with confidence. Run `resync` to set it right.
- **Moving the cover outside Home Assistant throws it out of sync.** An RF
  remote or a press of the physical button advances the motor where Home
  Assistant cannot see it, so the tracked position is then wrong. It cannot
  correct itself — call [`resync`](#cover_time_basedresync) afterwards to line
  it back up.
- **A partial position is approximate.** Anything between fully open and fully
  closed is reached with a timed stop, and drifts until the next full open or
  close corrects it.
- **Only the travel times can be measured.** The startup-delay and
  minimum-movement tests restart the motor in the same direction after a
  stop, which on a cycling button is a reversal, so the card does not offer
  them for this mode. Type those values in by hand if you need them.
- **Tilt is not available.** Tilting needs a pulse in a chosen direction, which
  a single button cannot give, so the option is off for this mode.

#### The `resync` action

Use the [`cover_time_based.resync`](#cover_time_basedresync) action — or the
**Resync** control on the configuration card — to tell the integration the
cover's true state after it was moved outside Home Assistant, whether by an RF
remote, the physical button, or anything else it could not see. Pick **Fully
closed** or **Fully open** to match where the cover actually is, and the
integration sets its tracked state and position (0% or 100%) to match. If a
press sequence is still in flight, resync cancels it rather than pressing the
button, so nothing is left running against the position you just declared. Wire
it into an automation triggered by your remote to keep the tracker in sync
automatically.

### Tilt

The **Tilt Mode** setting controls whether the cover has tilting slats and how
tilt and travel interact.

| Tilt Mode | Behaviour |
| --- | --- |
| **Not supported** _(default)_ | Tilt is disabled. Only position is tracked. |
| **Closes then tilts closed** | The slats can only tilt at the fully closed position. Closing first travels the cover down, then drives the motor further to tilt the slats closed; opening tilts the slats back first, then travels up. |
| **Closes then tilts open** | The mirror image, for covers whose slats tilt _open_ when the motor drives past the closed point. Closing travels down, then drives further to tilt the slats open; opening tilts them closed first, then travels up. |
| **Separate tilt motor** | A dedicated motor drives the tilt, using its own switches. Tilt is allowed only when the cover is in a safe position that you set. |
| **Tilts inline with travel** | Tilt and travel share one motor and tilt can happen at any position. Closing tilts the slats closed before the cover starts moving; opening tilts them open first. |

#### Close cover also closes slats

Shown for the **Closes then tilts closed** and **Separate tilt motor** modes,
and **on** by default. With it on, pressing close in the Home Assistant UI closes
the cover and then closes the slats, leaving both fully shut. Turn it **off** if
you would rather have a close move the cover only and leave the slats where they
are, so you can articulate them separately with the tilt-close button.

#### Tilt motor

For the **Separate tilt motor** mode, configure the relays and limits for the
tilt motor. (A wrapped cover with its own tilt does not need these switches.)

- **Tilt open switch**, **Tilt close switch**, **Tilt stop switch**: the relays
  that drive the tilt motor.
- **Safe tilt position**: the tilt moves here before the cover travels. Defaults
  to **100**, fully open.
- **Max tilt allowed position** _(optional)_: tilt is only allowed when the cover
  is at or below this position, where 0 is closed and 100 is open.

How a physical switch or automation firing the tilt relay is interpreted under
the sequential modes is described under
[Advanced hardware notes](#advanced-hardware-notes).

### Options for every cover

These three options are available whatever the Control Mode.

#### Assumed state

A time-based cover works out its position without feedback, so by default it
reports an _assumed_ state and Home Assistant keeps both the open and close
buttons active at all times. Turn **Assumed state** off if you trust the
calculation and want the UI to behave like a position-aware cover, greying out
actions that cannot apply, such as close when the cover is already closed. Leave
it **on** if the calculation can drift, for example through motor slip, manual
operation, or a power cut mid-travel, because the always-active buttons let you
re-issue a command to bring things back into line.

#### Always re-send open/close at the endpoints

Normally an open or close command is skipped when the tracker already believes
the cover is settled at that endpoint, since there is nothing to do. Turn this
**on** for a cover that has **no position feedback and can also be moved by an
external remote or wall button**. Such a remote moves the cover without telling
Home Assistant, so the tracker can believe the cover is closed while it is
physically open, and the very command that would fix it is the one being skipped.
With the option on, an endpoint command is always driven for the full travel
time, which guarantees it reaches the motor. Leave it **off** for covers that
report their own position, where the skip is correct.

> [!NOTE]
> A forced re-drive is modelled as starting from the opposite endpoint, so if you
> stop it partway the reported position is derived from that assumed start and can
> be well off. Let a re-drive run all the way to the endpoint, where the position
> resyncs, rather than stopping it mid-travel.

#### Fully open before moving to a position (Beta)

The companion to the option above, for the same hardware, but for **set
position** rather than open and close. A cover with no feedback that a remote can
also move drifts out of sync, so a "go to 40%" command based on a stale guess can
send it somewhere you did not intend, such as onto an obstruction below. With
this **on**, every set-position command first drives the cover fully open, the
one position it can be sure of because the motor stalls against its limit, and
only then moves to the position you asked for.

It is **off** by default because it is expensive: each move costs a full open
plus the run back down, up to roughly twice the full travel time however small
the change. On the inline and sequential tilt modes, where the slats share the
travel motor, it also means adjusting the slats moves the whole cover. This
feature is new and its behaviour may still change.

## Calibration

The **Calibration** tab is where you tell the integration where the cover is now
and how long its movements take. Fill in the Device tab first.

### Set the current position

Use the open, stop, and close buttons on the card to move the cover, and the
slats if tilt is enabled, to a known position. These buttons drive the motor
without tracking it, so the position stays unknown — across a restart too —
until you set it. Then set **Current Position** to match: fully open, fully
closed, or one of the tilt positions. You must set this before you can measure
any timing.

### Measure a timing

Most timings can be measured for you:

1. Set the current position.
2. Choose the value to measure. The list offers only the values that make sense
   from where the cover currently is. For example, when fully open you can
   measure the close time but not the open time.
3. Read the on-screen description of what to watch for.
4. Click **Start**, and click **Finish** the moment the cover reaches the
   position the description asks for. Click **Cancel** to abort instead.

### Travel timings

| Timing | What it is | Default |
| --- | --- | --- |
| **Travel time (close)** | Seconds for the cover to close fully. | — |
| **Travel time (open)** | Seconds for the cover to open fully. | — |
| **Travel startup delay** | Compensates for the motor's start-up lag. See [Startup delay](#startup-delay). | not set |
| **Minimum movement time** | Blocks movements too short to physically move the cover. See [Minimum movement time](#minimum-movement-time). | not set |
| **Endpoint run-on time** | Extra relay time at the endpoints so the motor reaches its limit. Typed in rather than measured. See [Endpoint run-on time](#endpoint-run-on-time). | 2.0 |

### Tilt timings

| Timing | What it is | Default |
| --- | --- | --- |
| **Tilt time (close)** | Seconds to tilt the slats fully closed. | not set |
| **Tilt time (open)** | Seconds to tilt the slats fully open. | not set |
| **Tilt startup delay** | Start-up compensation for the tilt motor. | not set |

### Startup delay

A motor does not start moving the instant its relay switches on; there is a brief
delay while it gets going. Over a long movement this is negligible, but over a
short one (say half a second) it can cause a large position error that builds up
over time. The startup delay tells the integration to wait that long after
switching the relay on before it starts counting position, which keeps short
movements accurate. Values between **0.05 and 0.15 seconds** are typical, and
travel and tilt can be set separately.

### Endpoint run-on time

Time-based tracking is never exact and can drift, so the tracker resyncs itself
whenever the cover is sent fully to an endpoint. Most motors have internal limit
switches and stop themselves there, so most modes send no stop at an endpoint and
simply let the motor run into its own limit, which resyncs the position for free.

In **Switch** mode, though, the direction relay is latched on for the whole
movement and has to be switched off at the endpoint. Because tracking is
approximate, the relay is held on for an extra **Endpoint run-on time** (default
**2 seconds**) so the motor reaches the limit before power is cut. This value
applies in Switch mode, and in Pulse mode when
[Send stop signal at endpoints](#send-stop-signal-at-endpoints) is on, where it
delays the stop pulse by the same amount. You type it in on the Calibration tab;
it is not one of the measured timings.

[Single button](#controlling-a-cover-with-a-single-button) mode reuses the same
value differently: there is no relay to hold, since the motor self-stops, so
this becomes the **settle margin** — how long the integration keeps treating
the motor as still travelling past its estimated arrival time before it locks
in the endpoint, snapping the tracked position to 0 or 100 and marking the
phase settled. It is a wait, not a relay hold. If the presses that started the
move are still being sent when the estimated arrival time passes, the wait
starts once the last press has gone out.

### Minimum movement time

This blocks relay activations too brief to physically move the cover, which
prevents them nudging the tracked position out of true. Movements all the way to
0% or 100% are always allowed. Values between **0.5 and 1.5 seconds** work well.

## Services

### `cover_time_based.set_known_position`

Manually set a cover's tracked position, which is useful for correcting drift.
Aim it at any entity, device, area, floor or label; every matching Cover Time
Based cover is set.

If Home Assistant is still driving the cover it stops the motor first, so the
relay is released rather than left on while the tracker shows the position you
declared. In
[Single button (cycling)](#controlling-a-cover-with-a-single-button) mode,
giving it an endpoint also re-anchors the tracked phase.

| Field | Description |
| --- | --- |
| `position` | The position to set (0–100). |

### `cover_time_based.set_known_tilt_position`

Manually set a cover's tracked tilt position.
Aim it at any entity, device, area, floor or label; every matching Cover Time
Based cover is set.

| Field | Description |
| --- | --- |
| `tilt_position` | The tilt position to set (0–100). |

### `cover_time_based.start_calibration`

Start a calibration test to measure a timing.

| Field | Description |
| --- | --- |
| `entity_id` | The cover entity. |
| `attribute` | The timing to calibrate. |
| `timeout` | Safety timeout in seconds; the motor auto-stops if `stop_calibration` is not called. |
| `direction` | Direction to move, `open` or `close`. Auto-detected if not set. |

### `cover_time_based.stop_calibration`

Stop a running calibration test and save the result.

| Field | Description |
| --- | --- |
| `entity_id` | The cover entity. |
| `cancel` | If `true`, discard the result instead of saving it. |

### `cover_time_based.resync`

Works for every control mode. Re-anchors the reported position to fully
closed (0%) or fully open (100%) after the cover was moved outside Home
Assistant — an RF remote, a physical button, or anything else the
integration could not observe. Tell it what the cover actually is right now;
it does not sense anything on its own. In
[Single button (cycling)](#controlling-a-cover-with-a-single-button) mode it
additionally re-anchors the tracked phase, which is how resync or
`set_known_position` at an endpoint restores a phase that has drifted (see the
honest limits above).

| Field | Description |
| --- | --- |
| `state` | The cover's true current state: `closed` or `open`. |

`resync` is the closed/open shortcut of
[`set_known_position`](#cover_time_basedset_known_position), which can set any
position (not just the two endpoints) and re-anchors the phase in the same way
when you give it an endpoint. Both stop the motor first if Home Assistant is
still driving it, so the relay is released rather than left on while the
tracker shows the declared position — except in
[Single button (cycling)](#controlling-a-cover-with-a-single-button) mode, where
the in-flight press plan is cancelled instead, because a press there would start
a parked motor rather than stop it. `resync` is the friendlier one to wire into
an automation.

A single button is enough to trigger it — the action needs only the fixed
`state` field, so a dashboard control does not need a two-button stack:

```yaml
type: button
name: Mark closed
icon: mdi:arrow-collapse-down
tap_action:
  action: perform-action
  perform_action: cover_time_based.resync
  target:
    entity_id: cover.garage_single_button
  data:
    state: closed
```

Add a second button with `state: open` (and an "open" icon) for the other
direction. Older Home Assistant versions use `action: call-service` and
`service: cover_time_based.resync` in place of `perform-action`/`perform_action`
— the current names are aliases of those legacy ones, so either form works.

## Troubleshooting

### The card does not appear

If a dashboard shows a red **Configuration error** ("custom element doesn't
exist: cover-time-based-card"), the card's code has not loaded. Two things cause
this:

- **No cover exists yet.** Home Assistant only loads the card once at least one
  Cover Time Based cover has been created. Create one (see
  [Quick start](#quick-start)), then add the card.
- **The browser has a stale copy.** After the first install, a browser tab that
  was already open will not have the card's code. A **hard refresh**
  (`Ctrl`/`Cmd`+`Shift`+`R`) loads it. Home Assistant shows a dismissible
  reminder in **Settings → Repairs** after a first install; it does not appear on
  ordinary updates or restarts.

### Enable debug logging

Detailed logs make problems much easier to diagnose. The quickest way is from the
UI:

1. Open **Developer Tools → Actions**.
2. Find **Logger: Set logger level** and switch to YAML mode.
3. Enter the following and run it:

   ```yaml
   action: logger.set_level
   data:
     custom_components.cover_time_based: debug
   ```

4. Reproduce the problem. Debug messages appear in the Home Assistant log.

To turn logging off again, repeat the steps with `info` in place of `debug`.

You can also set the level permanently in `configuration.yaml`, which takes
effect after a restart:

```yaml
logger:
  default: info
  logs:
    custom_components.cover_time_based: debug
```

### Report an issue

Please open bugs and feature requests on
[GitHub](https://github.com/Sese-Schneider/ha-cover-time-based/issues). Including
debug logs helps a great deal.

## Advanced hardware notes

Most people can skip this section. It covers behaviour that only matters for
particular hardware.

<details>
<summary><strong>Wrapped covers and external control</strong></summary>

**Following physical wall switches.** When a wrapped cover is operated from
outside Home Assistant (a wall switch, a
remote, or another integration), the tracker can only follow the movement live if
the wrapped entity reports an `opening` or `closing` state while it runs. Some
wrapped entities, notably certain Tuya and ZHA cover modules, stay in their
current `open` or `closed` state the whole time the motor runs and only report
the final state once it settles. In that case the position cannot be tracked
during the movement, but it snaps to the wrapped entity's reported position once
it settles.

If instead your device reports `closed` or `unknown` the moment a command is
issued, so that a manual stop mid-travel is wrongly reported as fully closed, set
[Position reporting](#position-reporting) to **State mirrors the last command** to
track it purely by time.

**Native position and tilt.** If the wrapped cover supports `set_cover_position`,
the integration forwards the
set-position command straight to it, so the cover stops at the requested position
even when the underlying device has no stop service. The tracker still animates
the position live during the move, which is handy for covers that only report
their position once they finish. On such a cover, the integration's **Stop** sets
the wrapped cover to its current calculated position. To override this and always
use timed movements, turn on
[Force time-based positioning](#force-time-based-positioning).

Tilt works similarly. The **Tilts inline with travel** and sequential modes drive
the wrapped cover's normal open and close commands, so they work on any wrapped
cover. The **Separate tilt motor** mode needs the wrapped cover to expose its own
tilt commands, so it is only offered when the wrapped entity reports native tilt
support. If the wrapped cover supports `set_cover_tilt_position` and you use the
inline mode, the integration forwards the tilt commands straight through, letting
the device position its own slats and snapping the tilt tracker to the reported
angle once it settles. This is auto-detected; no extra configuration is needed.

</details>

<details>
<summary><strong>How endpoints stop in each mode</strong></summary>

The tracker resyncs whenever the cover reaches an endpoint, but how the motor is
stopped there depends on the mode:

- **Switch** mode holds the latched relay on for the
  [Endpoint run-on time](#endpoint-run-on-time), then switches it off.
- **Pulse** mode sends its dedicated stop pulse (deferred by the run-on time) when
  [Send stop signal at endpoints](#send-stop-signal-at-endpoints) is on, and sends
  nothing when it is off.
- **Toggle**, **Toggle (opposite button)**, and most wrapped covers send **no
  stop**. The motor runs into its own limit switch, which both avoids an unwanted
  extra movement and resyncs the tracker for free. (In Toggle mode a stop pulse on
  an already-stopped motor would restart it.)
- A wrapped cover set to **State mirrors the last command** is the exception among
  wrapped covers: it _is_ sent an explicit stop, as described above.

A **separate tilt motor** is handled the same way at its own tilt endpoints: no
stop except in Switch mode, and in Pulse mode when the send-stop option is on.
Mid-tilt positions are always stopped, since nothing self-stops there.

One subtlety with shared-motor tilt: a tilt move made while the cover is parked at
a travel endpoint drives the motor _off_ its limit switch, so it will not
self-stop, and the stop is sent in that case even in the modes that normally skip
it. Under the two sequential modes, the endpoint run-on is skipped at the closed
(0%) endpoint, because the motor is already driven past cover-closed for the tilt
phase; it still applies at the open (100%) endpoint.

</details>

<details>
<summary><strong>Reversing a moving cover</strong></summary>

Reversing is never a single step. The motor is stopped, given a moment to come to
rest, and only then driven the other way. That pause is a fixed **1 second** and
is not configurable.

If reversals do not take on your hardware, the setting to change is on the device,
not here: a momentary relay's own pulse length must be comfortably under a
second, and a few hundred milliseconds is typical (for example `pulse_length` on
a Zigbee2MQTT relay). A device pulse approaching or exceeding one second leaves
the relay still closed when the reverse command arrives, and no integration
setting can compensate for that.

> [!WARNING]
> In **Toggle (opposite button)** mode, "stop" is a pulse of the opposite relay.
> That stops a moving motor, but on a motor that has already stopped it is simply
> a movement command. So if the tracker and the cover ever disagree, the next
> stop can drive the cover to its endpoint. This is inherent to the mode on
> hardware with no position feedback.

</details>

<details>
<summary><strong>Tilt under sequential modes and external switches</strong></summary>

Home Assistant's cover entity exposes close and open for travel, and close-tilt
and open-tilt for the slats. Under the sequential tilt modes the integration
handles each depending on who invoked it:

- **Close from the UI** (`cover.close_cover`): closes the cover, and then
  articulates the slats closed when
  [Close cover also closes slats](#close-cover-also-closes-slats) is on (the
  default for the modes that offer it). Turn that option off for a travel-only
  close.
- **Open from the UI** (`cover.open_cover`): restores the slats to their resting
  position if needed, then travels fully open, as one motion.
- **Close-tilt or open-tilt from the UI**: drives the slats only, with a short
  travel pre-step first if tilt is only allowed at the closed position.
- **Close from an external switch or automation**: the integration assumes the
  motor runs the full journey, closing the cover and then continuing to
  articulate the slats past cover-closed. Tracking follows both phases.
- **Open from an external switch**: restores the slats to the resting position,
  then travels fully open.

The external-close behaviour assumes a controller that latches on a pulse and runs
to a mechanical end without stopping at cover-closed, which is common with
pulse-mode relays and many off-the-shelf blind motors. If your external switch
stops the motor at cover-closed instead, the reported tilt position will drift
until the next sync. If that describes your hardware, please
[open an issue](https://github.com/Sese-Schneider/ha-cover-time-based/issues) with
the details.

</details>

## YAML configuration (deprecated)

> [!NOTE]
> YAML configuration is deprecated and will be removed in a future version.
> Please use the card instead. Existing YAML keeps working, and a deprecation
> notice appears in the Home Assistant repairs panel.

<details>
<summary>Show YAML configuration</summary>

### Example

```yaml
cover:
  - platform: cover_time_based
    devices:
      room_rolling_shutter:
        name: Room Rolling Shutter
        open_switch_entity_id: switch.wall_switch_right
        close_switch_entity_id: switch.wall_switch_left
        travelling_time_down: 23
        travelling_time_up: 25
        tilting_time_down: 2.3
        tilting_time_up: 2.7
        endpoint_runon_time: 2.0
        min_movement_time: 0.5
        travel_startup_delay: 0.1
        tilt_startup_delay: 0.08
```

### Options

Only a subset of the card's settings are available from YAML. For anything not
listed here, use the card.

| Name | Type | Requirement | Description | Default |
| --- | --- | --- | --- | --- |
| `name` | string | **Required** | Name of the created entity. | |
| `open_switch_entity_id` | entity | **Required**, or `cover_entity_id` | Switch that opens the cover. May be a `script` entity in pulse mode. | |
| `close_switch_entity_id` | entity | **Required**, or `cover_entity_id` | Switch that closes the cover. May be a `script` entity in pulse mode. | |
| `stop_switch_entity_id` | entity | Required in pulse mode | Switch that stops the cover. May be a `script` entity in pulse mode. | None |
| `cover_entity_id` | entity | **Required**, or the open/close switches | Existing cover entity to wrap. | |
| `input_mode` | string | _Optional_ | Control mode for switch-based covers: `switch`, `pulse`, `toggle`, or `toggle_opposite`. | `switch` |
| `travelling_time_down` | float | _Optional_ | Seconds to close the cover. Minimum 0.1 s. | unset |
| `travelling_time_up` | float | _Optional_ | Seconds to open the cover. Minimum 0.1 s. | unset |
| `tilting_time_down` | float | _Optional_ | Seconds to tilt the cover fully closed. Minimum 0.1 s. | None |
| `tilting_time_up` | float | _Optional_ | Seconds to tilt the cover fully open. Minimum 0.1 s. | None |
| `travel_moves_with_tilt` | boolean | _Optional_ | Whether tilt movements also change travel proportionally. | false |
| `endpoint_runon_time` | float | _Optional_ | Extra relay time at the endpoints. Also accepted under its old name `travel_delay_at_end`. | 2.0 |
| `min_movement_time` | float | _Optional_ | Minimum movement duration; blocks shorter movements. | None |
| `travel_startup_delay` | float | _Optional_ | Startup compensation for travel movements. | None |
| `tilt_startup_delay` | float | _Optional_ | Startup compensation for tilt movements. | None |
| `pulse_time` | float | _Optional_ | Pulse duration in pulse mode. Minimum 0.1 s. | 1.0 |
| `relay_reports_off` | boolean | _Optional_ | Toggle mode: set `false` for pulse modules that never report their off. | true |
| `send_endpoint_stop` | boolean | _Optional_ | Pulse mode: set `false` for auto-stop controllers that reposition on a stop received while stopped. | true |
| `direction_change_delay` | float | _Deprecated_ | No longer configurable. Accepted and ignored; the reversing pause is fixed at 1.0s. | — |

</details>

[commits-shield]: https://img.shields.io/github/commit-activity/y/Sese-Schneider/ha-cover-time-based?style=for-the-badge
[commits]: https://github.com/Sese-Schneider/ha-cover-time-based/commits/main
[installations-shield]: https://img.shields.io/badge/dynamic/json?url=https://analytics.home-assistant.io/custom_integrations.json&query=$.cover_time_based.total&label=Active%20installations&color=41BDF5&style=for-the-badge
[license-shield]: https://img.shields.io/github/license/Sese-Schneider/ha-cover-time-based?style=for-the-badge
[maintenance-shield]: https://img.shields.io/maintenance/yes/2026.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/v/release/Sese-Schneider/ha-cover-time-based?style=for-the-badge
[releases]: https://github.com/Sese-Schneider/ha-cover-time-based/releases
