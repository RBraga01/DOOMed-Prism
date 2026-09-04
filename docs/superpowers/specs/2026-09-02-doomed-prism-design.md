# DOOMed Prism / PewPew Engine — Design Specification

Date: 2026-09-02  
Status: Approved design, awaiting specification review  
Initial target: Raven Simulator  
Future target: Raven Prism v1 hardware

## 1. Purpose

DOOMed Prism is a local, offline port of classic DOOM for Raven Prism. It uses Crispy Doom as the game engine and PewPew Engine as the adaptation layer for Raven input, waveguide presentation, resource control, and simulator support.

The project has two equal goals:

1. Deliver a recognizable, faithful, and playable DOOM experience on Raven glasses.
2. Explore the maximum sustainable workload that Raven Prism can run without degrading RavenOS responsiveness.

The first release is a local prototype for the Raven Simulator. It must not claim hardware compatibility or publish Prism performance results until tested on physical glasses.

Working tagline: **Push the Prism until it’s DOOMed.**

## 2. Scope

### Publication-readiness rule

The repository may remain private during prototyping, but every commit must be
safe to publish later. Privacy must not be used to temporarily store Raven
Framework source, commercial IWADs, incompatible third-party code, restricted
models, credentials, or other material that would later need to be removed from
Git history.

DOOMed Prism contains only original project code and dependencies whose licences
permit the intended use and distribution. Proprietary dependencies are installed
separately and accessed only through their documented public interfaces.

### Included in the prototype

- Crispy Doom running as a separate native process.
- A Raven application that launches, controls, monitors, pauses, and stops the game.
- A simulator adapter and a future Prism adapter behind one input interface.
- Gaze-zone movement with progressive turning.
- Double-blink activation on hardware when the Raven API permits it; click simulation on desktop.
- Offline voice commands in English.
- Simultaneous fire inputs from double blink and the spoken sound “piu piu”.
- Authentic and Waveguide Boost visual profiles.
- Authentic, Smooth, Adaptive, and Benchmark performance modes.
- Measurements that distinguish game-engine performance from simulator composition performance.
- User-provided IWAD loading.

### Excluded from the prototype

- Distribution of commercial DOOM or DOOM II IWADs.
- Claims about Prism battery life, temperature, frame rate, gaze accuracy, or RavenOS impact.
- Online services, cloud speech recognition, accounts, telemetry uploads, multiplayer, camera-based AR, and IMU head steering.
- Modification of RavenOS itself.

## 3. Platform Facts and Constraints

The design is based on Raven Framework alpha v1.0.4 and inspection of `core/raven_simulator.py` and `config.json`.

### Prism-facing constraints

- RavenOS is Linux-based on ARM64.
- The Prism display is a 720×720 full-colour additive waveguide.
- Black pixels emit no light and therefore appear transparent. Software cannot produce real black, opacity, or environmental dimming.
- The public hardware specification lists a quad-core ARM CPU and OpenGL ES 2.0 GPU support.
- The public eye-control API exposes gaze coordinates. Framework controls support dwell and evolving double-blink activation of focused elements, but the public peripheral API does not document a raw blink event.
- Sensor access and publishing may require Raven developer entitlements.

### Simulator constraints

- The simulator is an optical preview, not a RavenOS emulator.
- The display canvas is 720×720, while the app surface is 640×640. The app is composited with the framework-defined offset; the current inspected implementation uses `(40, 50)`.
- Mouse position represents gaze position.
- Click represents focused-element activation; the app cannot distinguish simulated dwell from double blink.
- Enter represents the physical ClickButton.
- Eye tracking, real blinking, battery, thermal behaviour, RavenOS scheduling, and real device latency are not simulated.
- The optical compositor runs at 20 FPS, independently of the game engine.
- The compositor uses calibrated linear-light blending, point-spread simulation, transmission, and a perceptual “demand” approximation. The demand step does not mean real hardware can darken the environment.
- A depth-one frame queue drops frames when composition falls behind, avoiding latency accumulation.
- Raw mode is for geometry and widget debugging. Night, day, outdoors, and camera modes are for optical legibility evaluation.

## 4. Architecture

DOOMed Prism uses two processes so that the Raven-specific layer remains isolated from the game engine.

### Crispy Doom process

Responsibilities:

- Load a user-provided compatible IWAD.
- Preserve classic DOOM rules, assets, timing, and appearance in Authentic mode.
- Render at the selected frame-rate mode while maintaining 35 game tics per second.
- Accept normalized game actions through a small local IPC protocol.
- Export performance samples and health status.
- Shut down cleanly when requested or when its controlling process disappears.

### PewPew Engine process

Responsibilities:

- Run as the Raven application and follow Raven lifecycle calls.
- Select the Simulator or Prism input adapter.
- Convert gaze, activation, physical-button, and microphone events into normalized actions.
- Recognize a constrained English command grammar completely offline.
- Detect “piu piu” through a dedicated low-cost keyword detector.
- Apply visual and performance profiles.
- Launch and supervise Crispy Doom.
- Display calibration, settings, performance, pause, and recovery UI.
- Preserve a safe route back to RavenOS.

### IPC boundary

The processes communicate locally through a Unix domain socket on Raven/Linux and an equivalent local transport on development platforms. Messages are versioned and limited to:

- button press and release actions;
- discrete commands;
- configuration changes;
- engine readiness and health;
- performance samples;
- controlled shutdown.

No network socket is required. If PewPew Engine stops, all held movement and fire inputs must be released before Crispy Doom exits or pauses.

## 5. Display and Waveguide Design

### Geometry

- App surface: 640×640.
- Default DOOM viewport: 640×480, preserving the intended 4:3 presentation of the original 320×200 content.
- Remaining app area: 80 pixels above and 80 pixels below the viewport.
- The design does not treat the surrounding 720×720 canvas as writable app space.

The upper app margin contains only intentional system/game state such as mode, pause, or a temporary warning. The lower margin contains short-lived command feedback and calibration status. Normal gameplay keeps both areas visually quiet.

### Additive-display behaviour

- No feature is described as a black background, opacity layer, or environmental dimmer.
- Unlit pixels are transparent.
- Dark areas inside DOOM allow the real scene to remain visible.
- Calibration zones use emitted outlines, markers, or arrows rather than simulated dark panels.
- Brightness control changes emitted HUD light only.

### Visual profiles

**Authentic** preserves the classic palette and rendering as closely as the selected IWAD and Crispy Doom allow.

**Waveguide Boost** selectively raises mid-tones, improves enemy and pickup separation, and tunes emitted colour for additive display legibility. It must not imply that the environment can be darkened. Settings are evaluated in night, day, outdoors, and live-camera simulator modes.

## 6. Input Design

All sources produce normalized actions such as `MOVE_FORWARD`, `TURN_LEFT`, `FIRE`, `USE`, and `PAUSE`. The game bridge does not depend directly on Raven APIs.

### Gaze movement

The 640×640 app surface is divided into large, configurable regions:

- a generous central dead zone for observation;
- left and right turning regions;
- upper and lower forward/reverse regions;
- upper corner regions for forward movement combined with turning.

Movement begins after a short default dwell of approximately 150 ms. Turning speed increases as gaze moves farther from the central dead zone. Transitions are filtered to prevent jitter. Leaving a region immediately releases its action.

During calibration, regions are visible. During gameplay, they are invisible, with optional brief directional feedback when the active command changes.

### Fire

Two inputs remain active simultaneously:

- double blink on compatible Prism input;
- spoken “piu piu”.

Both feed the same fire action and share debounce/cooldown logic so that one intended shot does not become duplicate events. Because the current public API does not expose raw blink data, hardware implementation may rely on activation of a focused element until lower-level access exists.

In the simulator, click substitutes for double-blink/focused activation. The simulator cannot validate real blink accuracy or latency.

### Voice commands

The runtime language is English. The closed offline grammar includes:

- `piu piu` → fire;
- `open` or `use` → use/open;
- `next weapon` → next weapon;
- `weapon one` through `weapon seven` → direct weapon selection;
- `map` → toggle automap;
- `pause` and `resume`;
- `save game` and `load game`;
- `exit Doom` followed by confirmation.

“Piu piu” uses a dedicated lightweight detector calibrated with several user samples. Other commands use a restricted offline recognizer. Load and exit require confirmation. Recognition confidence and cooldowns are configurable. Recent recognized commands may be retained locally for debugging, without retaining continuous audio by default.

### Physical fallback

The Prism ClickButton opens pause/emergency controls. Enter provides the simulator equivalent. A voice failure must never prevent pause or exit.

## 7. Performance Modes and Governor

DOOM game logic remains at 35 tics per second in every mode.

- **Authentic:** render target of 35 FPS.
- **Smooth:** render target of 60 FPS using the engine’s supported interpolation.
- **Adaptive:** selects the highest sustainable target between 35 and 60 FPS while protecting system responsiveness.
- **Benchmark:** temporarily removes the render limit to characterize available headroom. It is not the normal play mode.

The initial prototype records:

- average, minimum, and percentile FPS;
- frame-time distribution;
- process CPU and resident memory;
- dropped or late engine frames;
- command-to-action latency;
- voice recognition latency;
- optical-compositor timing when exposed by the simulator.

Simulator reports must label engine FPS separately from the fixed 20 FPS optical compositor. Desktop results are simulator-development measurements and must not be presented as Prism performance.

On hardware, the governor first records an idle RavenOS baseline. Relative guardrails are preferred over guessed fixed limits. The starting policy aims to retain at least 35% free RAM, avoid sustained saturation beyond one CPU core by the application, and preserve immediate RavenOS interaction. These thresholds remain provisional until hardware testing.

When sustained pressure is detected, the governor acts in this order:

1. reduce nonessential metrics sampling and UI feedback;
2. reduce voice-analysis frequency where safe;
3. lower the render target from 60 toward 35 FPS;
4. pause the game and expose recovery controls if RavenOS responsiveness or process health is at risk.

## 8. Lifecycle, Failure Handling, and Safety

- PewPew Engine follows `start_hidden`, reveal/conceal, sleep, and wake behaviour expected by Raven apps.
- Sleep or conceal releases held inputs and pauses or throttles the game.
- A lost IPC connection releases all actions and pauses or terminates Crispy Doom safely.
- A crashed voice worker disables voice while preserving click/blink and the physical fallback.
- Missing or invalid IWAD files produce instructions rather than a crash.
- Configuration corruption falls back to conservative defaults.
- Benchmark mode has a visible exit route and configurable time limit.
- Logs remain local and avoid continuous microphone recordings by default.

## 9. IWAD, Licensing, and Future Publication

The prototype does not include commercial IWAD data. The user supplies `DOOM.WAD`, `DOOM2.WAD`, or another supported IWAD obtained lawfully.

The Raven Framework is proprietary. DOOMed Prism may depend on a separately
installed copy and import its public API, but must not copy, vendor, redistribute,
or commit Raven-owned source. Simulator improvements remain in Raven-authorized
fork branches and upstream pull requests rather than being copied into this
repository.

Crispy Doom and any modified engine code must be handled under its GPL terms,
including notices, licence text, source availability, and corresponding-source
obligations for distributed binaries. Development and CI may use a freely
redistributable compatible IWAD such as Freedoom after its current licence is
recorded and verified.

Offline speech libraries, acoustic models, fonts, media, and build tools must
pass a licence review before being committed or packaged. The core automated
test suite uses project-owned fakes and adapters, so it can run without Raven's
proprietary framework. Optional local integration tests may run when a developer
has installed Raven Framework separately.

Before public release:

- preserve all Crispy Doom upstream notices and GPL obligations;
- publish corresponding source for distributed GPL binaries and modifications;
- verify the exact redistribution conditions before bundling any shareware IWAD;
- document installation without encouraging unauthorized WAD downloads;
- state clearly that DOOMed Prism is an independent community project and is not endorsed by Raven Resonance or the DOOM rights holders;
- avoid presenting the project name or visual identity as an official Raven product.
- run an automated repository scan for credentials, commercial IWAD signatures,
  Raven-owned source, unapproved binaries, and missing third-party notices;
- verify the entire Git history is publication-safe, not only the current tree.

## 10. Validation Strategy

### Phase A — desktop and Raven Simulator

The prototype is successful when it:

- starts and stops through the Raven application lifecycle;
- launches Crispy Doom with a user-provided IWAD;
- presents the 640×480 game correctly inside the 640×640 app surface;
- maps mouse gaze regions to stable movement without keyboard gameplay input;
- maps click to simulated blink/fire activation;
- recognizes “piu piu” and the closed English grammar offline;
- keeps both fire mechanisms active without duplicate events;
- remains recoverable through Enter/ClickButton fallback;
- exposes all visual and performance modes;
- remains responsive while the simulator drops excess composition frames rather than accumulating latency;
- evaluates legibility in Raw, night, day, outdoors, and camera modes;
- clearly separates engine metrics from simulator-compositor metrics;
- can produce or validate an ARM64 build artifact without asserting physical-device success.

Automated tests cover action mapping, gaze zones, debounce, grammar routing, IPC messages, configuration fallback, governor state transitions, and process-failure recovery. Integration tests launch a test engine process and verify end-to-end commands. Visual checks use captured frames from each simulator background mode.

### Phase B — physical Raven Prism

Hardware validation is required for:

- real gaze-zone comfort, accuracy, jitter, and latency;
- double-blink behaviour and access route;
- microphone pickup, speaker leakage, and “piu piu” false positives;
- waveguide legibility and Waveguide Boost tuning;
- ARM64/OpenGL ES compatibility;
- RavenOS lifecycle and entitlement behaviour;
- sustained CPU, memory, temperature, battery, and system responsiveness;
- true 35/60 FPS capability and the safe Adaptive thresholds;
- ClickButton fallback.

The first hardware tester should use a conservative profile, short sessions, and benchmark time limits. Results must identify the hardware/software build and distinguish observation from confirmed specification.

## 11. Delivery Sequence

1. Establish the project skeleton, IPC contract, input abstractions, and test harness.
2. Launch and control an unmodified desktop Crispy Doom build.
3. Implement simulator gaze zones, click fire, and physical-button fallback.
4. Add offline “piu piu” detection, then the closed English grammar.
5. Integrate the Raven 640×640 surface and lifecycle.
6. Add Authentic and Waveguide Boost profiles and evaluate simulator backgrounds.
7. Add performance modes, measurement, governor, and failure recovery.
8. Produce and validate the ARM64 build path.
9. Prepare public documentation and licensing review only after the local prototype succeeds.
10. Seek physical Prism validation through Raven or the community before claiming device support.

## 12. Open Hardware-Validation Items

These are explicit phase boundaries rather than unresolved prototype requirements:

- availability of a raw or app-level double-blink event suitable for continuous gameplay;
- exact mechanism for placing a native SDL/OpenGL surface within or alongside the Raven app surface;
- device display refresh rate and whether 60 FPS presentation is meaningful;
- sensor entitlements and peripheral socket interfaces on production RavenOS;
- reliable device-side CPU, thermal, power, and RavenOS responsiveness metrics;
- final microphone topology and acoustic echo behaviour;
- final ARM64 library/runtime versions shipped on Prism.

The adapters and IPC boundary exist so these hardware details can change without rewriting the game-control design.
