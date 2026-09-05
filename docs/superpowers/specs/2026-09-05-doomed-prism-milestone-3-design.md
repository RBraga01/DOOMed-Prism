# DOOMed Prism — Milestone 3 Design: Input and the IPC Boundary

Date: 2026-09-05
Status: Design proposed. Revised once after three separate auditor passes
(architecture/feasibility, spec-consistency, publication-safety). Not implemented.
Depends on:
- `2026-09-02-doomed-prism-design.md` (§4 architecture / IPC boundary, §6 input
  design, §8 lifecycle and safety, §9 licensing, §10 validation, §11 delivery).
- `2026-09-04-doomed-prism-milestone-2-design.md` — the shared-memory framebuffer
  path this milestone keeps unchanged and builds beside. M2 §8 explicitly names
  the removal of Crispy's SDL keyboard sink as Milestone 3 work.
Supersedes: nothing. M3 adds a subsystem; it changes no M2 interface.

---

## 0. Rulings

The user (RBraga01, sole project authority) authorised this milestone to be
designed, audited, planned, audited again, and implemented autonomously, and was
not available for interactive clarifying questions. Decisions an interactive
brainstorm would have surfaced as questions are recorded here with rationale and
the cost of being wrong, for the user's later review. Section references are to
`2026-09-02-doomed-prism-design.md` unless noted.

### R1 — Milestone 3 ships as two plans: 3a (input core) and 3b (offline voice)

One spec, two implementation plans, both under the Milestone 3 umbrella.

- **3a — input core and the IPC boundary.** The IPC protocol and transport, the
  Crispy Doom IPC-input patch, the normalized-action model, gaze-zone movement
  with progressive turning, fire fusion (deliberate action + spoken fire),
  the simulator input source, lifecycle wiring, CI, and the 3a decision gate.
- **3b — offline voice.** The closed English command grammar (menus, weapon
  switching, automap, save/load, exit) and a real acoustic "pew pew" keyword
  detector, plus the §9 offline-speech-library licence review, plus a 3b
  decision gate.

**Rationale.** §9 requires a licence review of offline speech libraries and
acoustic models before they are committed or packaged, and speech capture needs
an audio dependency that is unresolved. Neither may gate the input architecture,
which is the load-bearing part of Milestone 3. The fire-fusion unit built in 3a
already carries the `SpokenFireSource` interface (R7), so 3b adds a real detector
and the grammar without reworking 3a.

**Cost if wrong.** If a minimal permissively licensed keyword spotter is judged
small enough to keep in 3a, fold 3b's detector back in — the `SpokenFireSource`
protocol is unchanged. If voice must ship as one unit with 3a, merge the plans;
the spec already covers both.

**Note on 3a size.** 3a is large (protocol, server, the patch series, the build
script change, seven Python modules, engine + host changes, CI smoke, gate). If
`writing-plans` judges it beyond one plan, split the transport core — protocol,
server, C patch, build script, CI smoke — into its own plan ahead of the input
model. The spec's §16 sequence is written so that split is a clean cut after
task 4.

### R2 — IPC transport: `AF_UNIX` stream socket on POSIX, `127.0.0.1` TCP stream socket on Windows

Both are `SOCK_STREAM`, so message framing and parsing are shared code; only
bind/connect differ, guarded by `#ifdef _WIN32` in the C patch exactly as M2's
exporter guards `shm_open` against `CreateFileMappingA`.

**Rationale.** §4 specifies "a Unix domain socket on Raven/Linux and an
equivalent local transport on development platforms". CPython does not expose
`socket.AF_UNIX` on Windows (it is `#ifdef`-guarded out of `socketmodule.c`), so
a loopback TCP socket bound to `127.0.0.1:0` (OS-assigned port) is the pragmatic
desktop transport. It is not reachable off-host and carries no secret.
Raven/Linux — the only platform that matters for the device — uses a real Unix
domain socket.

**Cost if wrong.** If a reviewer later requires Windows named pipes, the C
`#ifdef _WIN32` branch and the Python server's Windows branch change; the
protocol module and everything above it do not.

### R3 — PewPew Engine is the IPC server; Crispy Doom is the client

PewPew binds and listens **before** `engine.start()`, passes the address to the
child through `DOOMED_PRISM_IPC_ADDR` (POSIX: the socket path; Windows:
`127.0.0.1:<port>`), and the patched engine connects during `I_InitGraphics`,
next to `FB_Export_Init()`.

**Rationale.** The supervisor owns the endpoint; this mirrors M2, where PewPew
generates `DOOMED_PRISM_FB_NAME` and the child consumes it. §4 requires that
"if PewPew Engine stops, all held movement and fire inputs must be released
before Crispy Doom exits or pauses" — with PewPew as server, the child observes
the disconnect as a socket EOF and runs its own release-all (R9, C side).

**Cost if wrong.** Reversing the roles would move the bind into the C patch;
low likelihood.

### R4 — The Crispy Doom modifications ship as an ordered patch *series* of two independently reviewable diffs

`patches/crispy-doom-fb-export.diff` (the shipped M2 patch, **unchanged**) is
patch 1. `patches/crispy-doom-ipc-input.diff` is patch 2, authored against the
tree with **patch 1 already applied**, so its context lines legitimately include
patch-1 additions (e.g. `FB_Export_Init();` in `i_video.c`). The two diffs may
share context but must not both *modify* the same line.

`scripts/build_crispy.py` holds an ordered `PATCHES` tuple and applies the whole
series in one `git apply <p1> <p2>` invocation (git applies multiple patch files
as one in-memory sequence); `--check` is the matching single
`git apply --check <p1> <p2>`. The `.doomed-prism-applied` marker is written
exactly once, only after the whole series applies. SDL keyboard input in Crispy
is **left untouched** — IPC is an *additional* event source.

**Rationale.** Two focused diffs stay independently reviewable GPL
corresponding-source artifacts; a single `git apply` of the series is atomic
enough (it validates all hunks before touching the tree) and sidesteps the
"patch 2 authored against pristine won't apply onto the patch-1 tree" and
"per-patch `--check` against a pristine clone" failures a per-patch loop causes.

**Cost if wrong.** If the series ever fails to compose, concatenate the two into
one `crispy-doom-prism.diff` and drop the tuple — a modest `build_crispy.py`
change the tests already cover.

### R5 — Discrete actions and forward/back are injected as key events; analog turning is injected as synthetic mouse-x motion

DOOM's keyboard turn is stepwise and cannot express "turning speed increases as
gaze moves farther from the central dead zone" (§6) without a duty-cycle hack. A
synthetic `ev_mouse` event with an x value is DOOM's native analog-turn path:
`G_Responder` accumulates `mousex += ev->data2 * (mouseSensitivity+5)/10` and
`G_BuildTiccmd` does `cmd->angleturn -= mousex * 0x8`.

- Events injected straight into the event queue by `IPC_Input_Pump()` **bypass**
  `AccelerateMouse()`, `mouse_threshold`, and `mouse_acceleration` entirely —
  those are applied in `I_ReadMouse()` before `D_PostEvent`, not in
  `G_Responder`/`G_BuildTiccmd`. So the C patch **does not touch Crispy's mouse
  config** (mutating those globals would corrupt the tester's SDL fallback and
  persist to `default.cfg` via `M_SaveDefaults()`). The Python side owns the
  entire turn-response shape; the C patch is a pure translator that also
  **clamps** the injected x value to `±IPC_TURN_CLAMP` before posting, to
  protect the 16-bit `cmd->angleturn` field.

**Cost if wrong.** If `ev_mouse` injection is unusable in the gate, fall back to
a keyboard duty-cycle turn. The normalized action — `TURN_LEFT` / `TURN_RIGHT`
with a magnitude `0.0–1.0` — is unchanged, so only the C translator changes.

### R6 — Normalized action set for Milestone 3

§6 gives a "such as" list; this makes it explicit. The concrete integer `code`
values are pinned in §5.

| Category | Actions (3a) | Wire behaviour | Later (3b / hardware) |
| --- | --- | --- | --- |
| Held on/off | `MOVE_FORWARD`, `MOVE_BACKWARD` | `ACTION` frame, `value` = `10000` on hold / `0` on release (no per-tic magnitude — DOOM movement is on/off; a future run/walk split is a `GazeZoneMap` change only) | — |
| Held analog | `TURN_LEFT`, `TURN_RIGHT` | `TURN` frame each tic, `value` = clamped mouse-x delta derived from the gaze magnitude (§5, R5) | — |
| Pulsed | `FIRE`, `USE` | `PULSE` frame; C side holds the key `PULSE_HOLD_TICS` built tics then releases (§10) | — |
| Discrete | `PAUSE` | `DISCRETE` frame; C side edge-posts the pause key | `WEAPON_1..7`, `NEXT_WEAPON`, `PREV_WEAPON`, `AUTOMAP`, `SAVE_GAME`, `LOAD_GAME`, `EXIT_DOOM`, `MENU_CONFIRM`, `MENU_CANCEL`, `MENU_UP`, `MENU_DOWN` (all 3b, with the voice grammar) |

Strafing is out of scope for M3. **There is no menu-navigation action in 3a** —
the 3a gate reaches a live game with `-warp` (§11), not by clicking through
Crispy's menu, so `MENU_*` moves entirely to 3b where the voice grammar needs
it.

**Cost if wrong.** Adding an action later is one row in the §5 table, one C
mapping entry, and one `Action` enum member; the `code` space reserves the room.

### R7 — Fire fusion has two abstract sources; only the deliberate-action source is real in 3a

`FireArbiter` consumes edges from a `DeliberateActionSource` (double-blink on
hardware, click in the simulator — §6) and a `SpokenFireSource` (spoken "pew
pew" — §6). 3a supplies a real `DeliberateActionSource` (simulator click) and a
`NullSpokenFireSource` that never fires. A separate
`pewpew.input.DebugKeySpokenFireSource` (env-gated, §9) drives the fusion path
in the 3a gate without real audio; `tests/fakes` carries a `FakeSpokenFireSource`
for unit tests. 3b supplies the real acoustic `SpokenFireSource`. Both sources
feed one `FIRE` pulse through shared debounce so a blink and a "pew pew" inside
the debounce window produce exactly one shot (§6).

**Cost if wrong.** None structural — the interface is designed for both sources
from the start.

### R8 — The Raven-facing input source sits behind an `InputSource` protocol; only `SimulatorInputSource` is implemented

`SimulatorInputSource` reads gaze position (mouse), focused-element activation
(click), the physical button (Enter → `PAUSE`), and — only when
`DOOMED_PRISM_DEBUG_FIRE` is set — an `F9` debug key that stands in for a spoken
"pew pew", all from Qt events on the host widget, never from Raven APIs directly
(§6: "The game bridge does not depend directly on Raven APIs"). `PrismInputSource`
is a documented stub raising `NotImplementedError`. Real gaze coordinates, a raw
double-blink event, and sensor entitlements are §12 hardware-phase items.

**Cost if wrong.** The protocol may need one more method for real gaze/blink
entitlements — a change §12 already anticipates.

### R9 — One `release_all()` covers sleep/conceal, IPC loss, and shutdown, on both sides

Python side: `InputPipeline.release_all()` clears the gaze filter, tells
`ActionRouter` to emit a `0`-value / key-up message for every currently held
action, and resets `FireArbiter`. `cleanup()` ordering:
stop the input tick → `pipeline.release_all()` → `IpcServer.close()` →
`reader.close()` → `engine.stop()`.

C side: on socket EOF the patch posts an `ev_keyup` for every `MOVE_*` key it is
currently holding (turn needs no key — stopping delta injection lets `mousex`
fall to 0 at the next `G_BuildTiccmd`), posts a defensive `ev_keyup` for
fire/use, disables itself, and closes the socket, so a dead supervisor never
leaves DOOM with a stuck key (§4, §8). DOOM keeps running on SDL input.

**Cost if wrong.** Ordering tweaks. The invariant — "no held key survives a
lifecycle transition" — is what the gate checks.

### R10 — Wire format: a fixed 8-byte little-endian frame

`version: u8`, `type: u8`, `code: u16`, `value: i32`, all little-endian (matching
M2's little-endian shared-memory header). Fixed size means the C reader fills
exactly 8 bytes per frame with a short-read loop and never parses a length
prefix. There is no on-wire magic — the fixed frame size and the `HELLO`
exchange are the framing and the sanity check (a stream socket with fixed frames
does not need M2's `magic`). `type` value `5` is reserved for a future `PING`
keepalive, not implemented in M3 (the socket EOF is the liveness signal).

**Cost if wrong.** If a variable-length message is ever needed (it is not for
M3's action set), add a `type` whose `value` is a follow-on byte count; existing
frames are unaffected.

### R11 — Input tunables are documented module constants, not `RuntimeConfig` fields

Exhaustive list. §6 calls the regions "configurable"; a user-facing config
surface is deferred until the manual gate shows tuning is needed, at which point
each constant becomes a `RuntimeConfig` field with the same name.
`GazeZoneMap` / `GazeFilter` / `FireArbiter` already accept these as constructor
arguments, so the seam exists.

| Constant | Module | Default | Unit | Meaning |
| --- | --- | --- | --- | --- |
| `DEAD_ZONE_HALF_W` | `pewpew.input.gaze` | `180` | px from centre | half-width of the central no-action rectangle |
| `DEAD_ZONE_HALF_H` | `pewpew.input.gaze` | `150` | px from centre | half-height of the same (360×300 total ≈ 25% of the 640×640 surface; larger than a first read of §6 "generous dead zone" might suggest is needed — flagged for the user's R-review against §6, but a narrow Prism gaze range argues for keeping turning reachable) |
| `TURN_RESPONSE_EXPONENT` | `pewpew.input.gaze` | `1.5` | — | shaping exponent: gentle turn near the dead zone, steep at the edge |
| `MAGNITUDE_STEPS` | `pewpew.input.actions` | `20` | — | quantisation of the smoothed turn magnitude before it is sent (the "quantum" is `1/MAGNITUDE_STEPS`) |
| `MAGNITUDE_EMA_ALPHA` | `pewpew.input.gaze` | `0.4` | — | EMA weight for the raw turn magnitude while a turn is held |
| `DWELL_S` | `pewpew.input.gaze` | `0.15` | s | continuous presence required before an action is emitted (§6 "~150 ms") |
| `JITTER_GRACE_S` | `pewpew.input.gaze` | `0.02` | s | a held action survives this long of a `raw_set` dropout before release |
| `TURN_MAX_MOUSE_DELTA` | `pewpew.input.actions` | `40` | mouse units | magnitude `1.0` maps to this signed per-tic x delta (gate-tunable) |
| `FIRE_DEBOUNCE_S` | `pewpew.input.fire` | `0.12` | s | minimum interval between fused shots |
| `PULSE_HOLD_TICS` | C `i_ipc_input.c` | `2` | game tics | how long a `PULSE` holds its key down before the paired keyup |
| `IPC_TURN_CLAMP` | C `i_ipc_input.c` | `40` | mouse units | C-side clamp on an injected turn x value |

Protocol constants (`IPC_PROTOCOL_VERSION`, `IPC_FRAME_SIZE`,
`IPC_HANDSHAKE_TIMEOUT_S`, `IPC_HELLO_TIMEOUT_S`) are protocol-governed, not R11
tunables.

### R12 — Out of scope for Milestone 3

Performance modes, the governor, engine-versus-compositor metrics, Waveguide
Boost, ARM64 build validation, the shared OpenGL ES / Qt rendering surface, real
microphone capture in 3a, real gaze/blink hardware access, RavenOS entitlement
work, and DOOM menu / weapon / automap / save / load navigation in 3a (that is
3b). Audio and hardware gaze/blink are §12 hardware-phase items.

### R13 — The §6 fire keyword `piu piu` is renamed `pew pew` for the runtime

`2026-09-02-doomed-prism-design.md` §6's closed grammar lists `piu piu → fire`.
The M3 spec and the public README use `pew pew`. This ruling records the rename:
the runtime grammar token and the 3b keyword detector's calibration target are
`pew pew`. A docs follow-up updates the base design §6 (not done in this
milestone — the base design is not rewritten here). The README already uses
`pew pew`; a §16 task adds one clarifying line that voice ships in 3b.

**Cost if wrong.** If `piu piu` is later preferred, the 3b detector is
recalibrated against `piu piu` user samples and one grammar string changes; no
3a code is affected.

---

## 1. Problem

After Milestone 2, DOOM renders live inside the Raven Simulator, but the only
way to play it is to click Crispy Doom's separate SDL development window and use
the keyboard. M2 §8: that window "is a temporary development-time input sink that
Milestone 3's IPC input path removes."

Milestone 3 makes DOOM playable through the Raven interaction model: gaze to move
and turn, a deliberate action (double blink on hardware, click in the simulator)
and a spoken "pew pew" to fire, and — in 3b — spoken commands for menus and
weapons. All input sources produce **normalized actions** (`MOVE_FORWARD`,
`TURN_LEFT`, `FIRE`, …) that travel to Crispy Doom over the local IPC boundary §4
describes, instead of synthetic keystrokes aimed at a window that must hold OS
focus.

The hard question for the 3a decision gate: **does IPC-only normalized input
drive real DOOM gameplay inside the Qt viewport — gaze steering, progressive
turn, debounced click-fire, fused spoken-fire, and Enter-pause — with Crispy's
SDL window unfocused, and does every lifecycle transition release all held
inputs with no stuck key and no orphan process?**

## 2. Scope

### In scope (3a)

- A versioned, fixed-frame IPC protocol module (pure Python, no I/O). It provides
  `IPC_PROTOCOL_VERSION` and `IPC_FRAME_SIZE`; it does not provide an on-wire
  magic constant.
- An `IpcServer` (PewPew side): dual transport per R2, single client, a
  **blocking** socket with a short send timeout, a disconnect callback. It
  writes action frames and reads only the child's `HELLO` and the EOF/reset
  signal — it never consumes action payload bytes from the child.
- A **patch series** (R4): patch 1 is the unchanged M2
  `crispy-doom-fb-export.diff`; patch 2 is a new `crispy-doom-ipc-input.diff`
  authored against the patch-1 tree. Patch 2 connects to `DOOMED_PRISM_IPC_ADDR`,
  decodes frames, `D_PostEvent`s key and mouse events, and releases-all on EOF.
  SDL keyboard input is untouched.
- `scripts/build_crispy.py`: an ordered `PATCHES` tuple, a single
  `git apply <series>` and a single `git apply --check <series>`, the marker
  written once after the series applies.
- The normalized action model and `ActionRouter` (held set, pulse, discrete,
  `release_all`), the sole owner of magnitude quantisation, draining to an
  injected sink that maps to IPC `Message` objects.
- `GazeZoneMap` + `GazeFilter`: the §6 region layout, ~150 ms entry dwell,
  progressive turn magnitude, jitter grace, immediate release on a region
  change.
- `FireArbiter` + the two source protocols (R7), with the real deliberate-action
  (simulator click) source and `NullSpokenFireSource` in 3a.
- `InputSource` protocol + `SimulatorInputSource` (Qt events on the host) +
  `PrismInputSource` stub + `DebugKeySpokenFireSource` (env-gated, gate only).
- `InputPipeline`: the one unit that wires source → gaze → fire → router →
  server, ticked from the host timer, with `release_all()`.
- `pewpew.engine` and `pewpew.host_widget` changes to own the server lifecycle,
  run the input tick, warp into a level for the gate/CI, release-all on sleep /
  IPC loss / shutdown, and drive a minimal `_PauseOverlay`.
- CI: a POSIX IPC runtime smoke test mirroring `ci_posix_smoke.py`, with a
  fixed CI socket path and templated summary text.
- `check_publication_safety.py` is confirmed still adequate for two text diffs
  **only under a diff-minimality gate** (§14); no scanner change is required for
  3a.
- The 3a decision gate: `docs/validation/milestone-3a-checklist.md` and
  `milestone-3a-result.md`.
- A README refresh (License names the two patches; Current status / What comes
  next updated; one line that voice is 3b).

### In scope (3b, gated behind the §9 licence review)

- **First:** extend `check_publication_safety.py` (audio + acoustic-model file
  suffixes into `FORBIDDEN_SUFFIXES`, matching `tests/test_publication_safety.py`
  cases) and `.gitignore` (`models/`, `calibration/`, `*.wav *.flac *.ogg *.mp3
  *.opus *.raw *.pcm`, `*.tflite *.onnx *.pt *.pb *.pbmm *.scorer *.gguf`) —
  before any 3b audio/model code lands.
- The §9 offline-speech-library licence review, recorded as committed text; the
  library and any model stay out of git, fetched or supplied like the IWAD.
- The closed offline English command grammar (§6, token `pew pew` per R13):
  `open`/`use`, `next weapon`, `weapon one`–`weapon seven`, `map`,
  `pause`/`resume`, `save game`/`load game` (confirm), `exit Doom` (confirm),
  plus `MENU_*` navigation.
- A real acoustic "pew pew" keyword detector behind 3a's `SpokenFireSource`
  protocol, calibrated with user samples that are never committed.
- A desktop audio-capture adapter behind an `AudioSource` protocol; the Raven
  microphone topology is a §12 hardware-phase item and stays stubbed.
- The R6 "later" discrete `code`s appended to `crispy-doom-ipc-input.diff`.
- A crashed voice worker disables voice and preserves click/blink and Enter (§8).
- `docs/validation/milestone-3b-checklist.md` / `milestone-3b-result.md`, whose
  objective checks include "no model or audio file committed" and both
  publication-safety scan invocations.

### Out of scope

Everything in R12.

## 3. Approaches considered (getting actions into Crispy Doom)

| Approach | Verdict |
| --- | --- |
| **A. Local socket + a small Crispy patch that `D_PostEvent`s translated events.** | **Chosen.** Implements §4 as written, keeps the two-process split, portable (`AF_UNIX` / loopback TCP), a minimal auditable second patch, reuses DOOM's own event queue and key bindings, and needs no OS window focus. |
| B. Synthesise OS-level keyboard / mouse events to Crispy's SDL window (`SendInput`, `XTEST`, `uinput`). | Rejected. Requires the SDL window to hold focus, is platform-specific and permission-gated, races the compositor, and is precisely the fragility §4's IPC boundary exists to avoid. |
| C. Link the engine in-process and call its input functions directly. | Rejected. Breaks the §4 process isolation the governor and lifecycle safety depend on; a much larger patch; no simulator benefit. |
| D. Extend the M2 shared-memory segment with an input ring buffer instead of a socket. | Rejected. Reinvents a socket with none of its backpressure or disconnect semantics, and §4 explicitly calls for a socket. A shared-memory input path has no clean "supervisor died" signal — the disconnect EOF in approach A is what drives R9's release-all on the C side. |

## 4. Architecture

Two processes, unchanged from §4 and M2. M3 adds a **control plane** beside M2's
frame plane. Of the six IPC message categories in the base §4 (button
press/release, discrete commands, configuration changes, engine readiness and
health, performance samples, controlled shutdown), M3 implements button
press/release (`ACTION` / `PULSE` / `TURN`), discrete commands (`DISCRETE`),
readiness (`HELLO`), and shutdown (`BYE`). Configuration-change messages are
deferred with the config surface (R11); health and performance-sample messages
are deferred with the governor (R12).

```
PewPew Engine process                              Crispy Doom process (patch series applied)
  SimulatorInputSource  (Qt mouse / click / Enter)   I_InitGraphics
    | InputSample(gaze_xy, activation_edge,             +- FB_Export_Init()          (patch 1, unchanged)
    |             pause_edge, debug_fire_edge)          +- IPC_Input_Init()          (patch 2) -- connects
    v                                                        DOOMED_PRISM_IPC_ADDR
  InputPipeline.tick(now)                             d_loop.c BuildNewTic()  (once per built tic)
    +- GazeZoneMap.resolve(x, y) -> {HeldAction}         +- IPC_Input_Pump()         (patch 2) -- decode
    +- GazeFilter (dwell, grace) -> stable set                frames, D_PostEvent(ev_keydown/up, ev_mouse)
    +- FireArbiter (click edge + spoken edge)          I_FinishUpdate
    +- ActionRouter (held set, quantise, diff)           +- FB_Export_Publish()      (patch 1, unchanged)
    v                                                   IPC EOF -> post keyup for held MOVE_*, stop
  IpcServer.send(Message)  --8-byte frames-->  socket  --> IPC_Input reader
  IpcServer.on_disconnect  <-- socket EOF
```

### New and changed units

| Unit | Language | Responsibility | Depends on |
| --- | --- | --- | --- |
| `pewpew.ipc.protocol` | Python | `Message` (frozen; `type`, `code: int`, `value: int`), `MessageType` enum, `encode(msg) -> bytes` (8 bytes), `decode(buf) -> (Message | None, bytes)`; `IpcProtocolError`; constants `IPC_PROTOCOL_VERSION = 1`, `IPC_FRAME_SIZE = 8`. Pure. Never imports `pewpew.input`. | `struct` (stdlib) |
| `pewpew.ipc.server` | Python | `IpcServer(*, address_factory=default)`: `start() -> str`, `poll() -> None`, `send(Message) -> None`, `is_connected: bool`, `on_disconnect: Callable`, `close()`. Blocking socket, short send timeout, single client. Sole owner of the socket path (bind + unlink). | `socket` (stdlib), `pewpew.ipc.protocol` |
| `pewpew.input.actions` | Python | `Action` enum (the sole `Action ↔ int` mapping, matching the §5 table), `HeldAction(action, magnitude)`, `ActionRouter(sink)`: `set_held(frozenset[HeldAction])`, `pulse(Action)`, `discrete(Action)`, `release_all()`. Quantises turn magnitude to `MAGNITUDE_STEPS`; emits a frame only when a quantised step or on/off state changes. Constants `MAGNITUDE_STEPS`, `TURN_MAX_MOUSE_DELTA`. Pure + sink. | `pewpew.ipc.protocol` |
| `pewpew.input.gaze` | Python | `GazeZoneMap(surface_w, surface_h, *, dead_zone=(180,150), turn_exponent=1.5)`: `resolve(x, y) -> frozenset[HeldAction]` (region → actions; raw float magnitude). `GazeFilter(*, dwell_s=0.15, grace_s=0.02, ema_alpha=0.4)`: `update(raw_set, now) -> frozenset[HeldAction]`. Pure; time via the `now` argument only. | `pewpew.input.actions` |
| `pewpew.input.fire` | Python | `FireArbiter(*, debounce_s=0.12)`: `deliberate_action()`, `spoken_fire()`, `poll(now) -> bool`, `reset()`. `DeliberateActionSource` / `SpokenFireSource` protocols; `NullSpokenFireSource`. Pure; time via `poll(now)` only. | — |
| `pewpew.input.source` | Python | `InputSource` protocol: `sample(now) -> InputSample`. `InputSample(gaze_xy: tuple[int,int] | None, activation_edge: bool, pause_edge: bool, debug_fire_edge: bool)`. `PrismInputSource` stub. `DebugKeySpokenFireSource` (implements `SpokenFireSource`; only armed when `DOOMED_PRISM_DEBUG_FIRE` is set). | — |
| `pewpew.input.simulator_source` | Python | `SimulatorInputSource(widget)`: a Qt event filter tracks mouse position, left-press edges, `Return`/`Enter` edges, and (env-gated) `F9` edges; `sample(now)` returns and clears the accumulated `InputSample`. `Leave` sets `gaze_xy = None`. | PySide6, `pewpew.input.source` |
| `pewpew.input.pipeline` | Python | `InputPipeline(source, server, *, spoken_fire=NullSpokenFireSource())`: builds `GazeZoneMap`, `GazeFilter`, `FireArbiter`, `ActionRouter(sink=server.send)`. `tick(now)`, `release_all()`, `paused: bool`. The single integration unit. Time via `tick(now)`. | all of the above |
| `pewpew.engine` (modified) | Python | `start(*, ipc_address: str | None = None)` injects `DOOMED_PRISM_IPC_ADDR`; when `DOOMED_PRISM_WARP` is set, appends `-warp <value> -skill <DOOMED_PRISM_SKILL or 3>` to argv; `ipc_address` property. `stop()` does **not** touch the socket path (the server owns it). Mirrors the existing `frame_segment_name` env handling. | existing |
| `pewpew.host_widget` (modified) | Python | `showEvent`: `IpcServer.start()`, `engine.start(ipc_address=…)`, build `InputPipeline`. `_on_tick`: **first** `server.poll()` + disconnect handling (before any early return), then, once past the M2 frame-wait, `pipeline.tick(now)`. `hideEvent` / child-disconnect / handshake-timeout wired per §12. `cleanup()` extended per R9. A `_PauseOverlay` child driven by `pipeline.paused`. | `pewpew.input.pipeline`, `pewpew.ipc.server` |
| `src/i_ipc_input.c` / `.h` (patch 2) | C | `IPC_Input_Init()` (connect, blocking then non-blocking; no-op if `DOOMED_PRISM_IPC_ADDR` unset), `IPC_Input_Pump()` (decode frames → `D_PostEvent`; per-key `PULSE_HOLD_TICS` release scheduler; EOF → release held → stop), `IPC_Input_Shutdown()`. GPL-2.0-or-later header matching Crispy's style. | BSD sockets / winsock; `d_event.h` |
| `src/d_loop.c`, `src/i_video.c` (patch 2) | C | ~8 lines: `IPC_Input_Init()` after `FB_Export_Init()`; `IPC_Input_Pump()` in `BuildNewTic()` once per built tic, immediately before `loop_interface->ProcessEvents()`; `IPC_Input_Shutdown()` before `FB_Export_Shutdown()`; extend the M2 signal handler to also call `IPC_Input_Shutdown()`. | the above |
| `scripts/build_crispy.py` (modified) | Python | `PATCHES` tuple; single `git apply <series>` / `git apply --check <series>`; marker written once. | existing |
| `patches/crispy-doom-ipc-input.diff` | diff | The complete IPC-input modification, authored against the patch-1 tree. GPL-2.0-or-later. Adds only `src/i_ipc_input.c` / `.h` plus small hunks in `d_loop.c` / `i_video.c` / `src/CMakeLists.txt`. | — |
| `scripts/ci_ipc_smoke.py` | Python | Build the patched engine, accept its IPC connection at a **fixed** CI socket path, handshake, stream a scripted action sequence, assert `frame_counter` keeps advancing, then clean teardown with no orphan and the socket removed. Prints only presence/absence + basename, never a resolved path. | `pewpew.ipc`, `pewpew.framebuffer` |

`crispy-doom.lock` is unchanged — both patches target the same pinned tag and
commit.

### Data flow, one host tick (`_on_tick`)

1. `server.poll()` — **runs before any early return**: accept a pending client;
   drive the `HELLO` handshake across ticks; detect EOF/reset and fire
   `on_disconnect` once.
2. If still in the M2 "waiting for framebuffer / first frame" window, return
   here (the input path needs the game running).
3. `sample = source.sample(now)`.
4. `raw = gaze_map.resolve(*sample.gaze_xy)` when `gaze_xy` is not `None`, else
   the empty set.
5. `held = gaze_filter.update(raw, now)` — dwell-gated, grace-smoothed;
   `GazeZoneMap` gave raw floats, `GazeFilter` EMA-smooths the turn magnitude.
6. `router.set_held(held)` — quantises each turn magnitude to `MAGNITUDE_STEPS`
   and emits an `ACTION`/`TURN` frame only when a quantised step or an on/off
   state changed.
7. `if sample.activation_edge: fire.deliberate_action()`;
   `if spoken_fire.spoken_fire_edge() or sample.debug_fire_edge:
   fire.spoken_fire()`; `if fire.poll(now): router.pulse(FIRE)`.
8. `if sample.pause_edge: pipeline.toggle_pause()` — sends one `DISCRETE PAUSE`,
   flips `pipeline.paused`, and the host shows/hides `_PauseOverlay`.
9. Each `router` emission calls `server.send(msg)`; when `not
   server.is_connected` the send is a no-op and the held state is still tracked
   so it re-sends or releases later.
10. `if engine.poll() is not None:` stop the timer, `pipeline.release_all()`
    (emits nothing — the socket is gone), `server.close()`. Full `cleanup()`
    still runs later via `closeEvent` / `aboutToQuit`.

## 5. The IPC protocol

`pewpew.ipc.protocol`, stdlib only.

### Frame (little-endian, fixed 8 bytes — `struct` format `"<BBHi"`)

| Offset | Field | Type | Notes |
| --- | --- | --- | --- |
| 0 | `version` | u8 | `IPC_PROTOCOL_VERSION` (`1`). Receiver rejects a mismatch. |
| 1 | `type` | u8 | `MessageType` |
| 2 | `code` | u16 | action id (table below) or, for `HELLO`, the sender's protocol version |
| 4 | `value` | i32 | `ACTION`: `10000` on hold, `0` on release. `TURN`: unsigned clamped mouse-x magnitude (direction is in `code`). `PULSE`/`DISCRETE`/`HELLO`/`BYE`: `0`. |

### `MessageType`

`HELLO = 0`, `ACTION = 1`, `PULSE = 2`, `DISCRETE = 3`, `TURN = 4`,
`BYE = 6`. Value `5` is reserved (R10). Any other value → `IpcProtocolError`.

### Action `code` table (pinned; the C `#define`s and `pewpew.input.actions.Action` both match this, asserted by a test)

| `code` | Action | Category | Milestone |
| --- | --- | --- | --- |
| `1` | `MOVE_FORWARD` | `ACTION` | 3a |
| `2` | `MOVE_BACKWARD` | `ACTION` | 3a |
| `3` | `TURN_LEFT` | `TURN` | 3a |
| `4` | `TURN_RIGHT` | `TURN` | 3a |
| `10` | `FIRE` | `PULSE` | 3a |
| `11` | `USE` | `PULSE` | 3a |
| `20` | `PAUSE` | `DISCRETE` | 3a |
| `21`–`24` | `MENU_CONFIRM`, `MENU_CANCEL`, `MENU_UP`, `MENU_DOWN` | `DISCRETE` | 3b |
| `40`–`79` | reserved: weapons, automap, save, load, exit | `DISCRETE` | 3b |

`HELLO` uses `code` for the protocol version, not an action id.

### Functions

- `encode(message: Message) -> bytes` — always 8 bytes.
- `decode(buffer: bytes) -> tuple[Message | None, bytes]` — consumes one whole
  frame from the front; returns `(None, buffer)` when fewer than 8 bytes are
  buffered; raises `IpcProtocolError` on a version mismatch or an unknown
  `type`. Two frames in one buffer decode in sequence.

`Message` always holds the **wire** `int` `value`, and every constructor takes
already-wire-form `int`s — `pewpew.ipc.protocol` does no unit scaling and never
imports `pewpew.input`. `Message.action(code, value)` (caller passes `10000` or
`0`), `Message.turn(code, value)` (caller passes the clamped mouse-x magnitude),
`Message.pulse(code)` / `Message.discrete(code)` / `Message.hello()` /
`Message.bye()` (`value = 0`). All take a plain `int` `code`. All the
magnitude→wire scaling (`round(magnitude * 10000)` for `MOVE_*`,
`round(magnitude * TURN_MAX_MOUSE_DELTA)` clamped to `[0, TURN_MAX_MOUSE_DELTA]`
for `TURN_*`) lives in `ActionRouter` (`pewpew.input.actions`, which owns
`TURN_MAX_MOUSE_DELTA`). The round-trip contract is `decode(encode(m)) == m`;
`ActionRouter`'s scaling is tested separately.

The C side mirrors `decode`: read into an 8-byte staging buffer, act, repeat.

## 6. The `IpcServer`

- **`start() -> str`.** POSIX: build a short unique path
  `${XDG_RUNTIME_DIR or /tmp}/doomed-prism-ipc-<pid>-<token>.sock`, assert
  `len(path) < 104` (the `sun_path` limit) and raise a clear error otherwise,
  `unlink` any stale path, `bind`, `listen(1)`, return the path. Windows:
  `bind(("127.0.0.1", 0))`, `listen(1)`, return `"127.0.0.1:<port>"`. The
  `address_factory` seam lets tests force either branch and a fixed path.
- **Socket mode.** The listening socket's `accept` is non-blocking (polled once
  per host tick). The accepted client socket is **blocking** with
  `settimeout(0.05)`; a send timeout is treated as a disconnect (a wedged peer
  must not stall the Qt UI thread). At M3's volume — a few hundred bytes/s over
  loopback / `AF_UNIX` — a blocking `sendall` never actually blocks.
- **`poll()`.** Never blocks. `accept()` a pending client (a second connection is
  accepted then immediately closed; the first client and `is_connected` are
  unaffected). After `accept()`, `is_connected` stays `False` until the child's
  `HELLO` has been received and version-matched on this or a later `poll()`;
  frames produced in between are dropped. A subsequent zero-length `recv` or
  `ConnectionResetError` means the child exited: set `is_connected = False` and
  call `on_disconnect()` exactly once. The server never reads action payload
  bytes from the child.
- **`send(message)`.** No-op when not connected. Otherwise `sendall(encode(...))`
  on the blocking client socket; `BrokenPipeError` / `ConnectionResetError` /
  `socket.timeout` → treat as a disconnect (fire `on_disconnect` once).
- **Handshake.** On `accept()` the server sends `Message.hello()`. On each later
  `poll()` it does a non-blocking read of up to 8 buffered bytes; once a full
  `HELLO` frame is decoded it version-checks: match → `is_connected = True`;
  mismatch → close the client socket, leave `is_connected = False`, and record a
  `protocol_mismatch` flag the host reads. `IPC_HANDSHAKE_TIMEOUT_S` (§12) bounds
  the wait across ticks.
- **`close()`.** Send `BYE` if connected, close the client and listening
  sockets, `unlink` the POSIX path. Idempotent. Never depends on the child — the
  M2 teardown lesson.

## 7. Gaze zones and the filter

`pewpew.input.gaze`, pure Python, time supplied by the `now` argument.

### `GazeZoneMap`

Surface 640×640 (§5). All regions measured from the centre `(320, 320)`, sized
by `dead_zone=(DEAD_ZONE_HALF_W=180, DEAD_ZONE_HALF_H=150)`:

- **Dead zone.** The centred `360×300` rectangle. Gaze inside → empty set.
- **Left / right turn bands.** `|dx| > DEAD_ZONE_HALF_W` **and** `|dy| ≤
  DEAD_ZONE_HALF_H`. `resolve` returns `HeldAction(TURN_LEFT or TURN_RIGHT,
  magnitude)` with `magnitude = ((|dx| - DEAD_ZONE_HALF_W) / (320 -
  DEAD_ZONE_HALF_W)) ** TURN_RESPONSE_EXPONENT`, a **raw float** in `[0, 1]`.
- **Upper / lower forward-reverse bands.** `|dy| > DEAD_ZONE_HALF_H` **and**
  `|dx| ≤ DEAD_ZONE_HALF_W`. `MOVE_FORWARD` (gaze above centre) or
  `MOVE_BACKWARD` (below), magnitude fixed at `1.0` (movement is on/off, R6).
- **Corners.** `|dx| > DEAD_ZONE_HALF_W` **and** `|dy| > DEAD_ZONE_HALF_H`.
  `MOVE_FORWARD` or `MOVE_BACKWARD` (fixed `1.0`) **and** the matching `TURN_*`
  with its own raw-float magnitude (§6 "forward movement combined with
  turning"). The three region families are mutually exclusive by the `dx`/`dy`
  qualifiers above.

### `GazeFilter`

`update(raw_set, now) -> frozenset[HeldAction]`, one release rule:

- **Entry dwell.** An action's *action id* must be present in `raw_set`
  continuously for `dwell_s` (default `0.15`, §6) before it is emitted. The
  dwell timer is per action id.
- **Release.** An emitted action is released once it has been absent from
  `raw_set` for `grace_s` (default `0.02` — one 60 Hz tick). A `raw_set` that
  still has some regions but not this action (a genuine region change) releases
  the outgoing action on the same tick, without waiting out `grace_s`. Net
  behaviour on a real region exit is ≤ 1 tick; the grace only rides out a
  single-sample gaze dropout.
- **Magnitude smoothing.** While a `TURN_*` action is held, the emitted
  magnitude is an EMA (`ema_alpha`, default `0.4`) of the raw magnitude, seeded
  with the first raw magnitude on (re-)acquisition after release. `MOVE_*`
  magnitudes are not smoothed (they are constant `1.0`).

Quantisation of the smoothed magnitude and the "emit only on change" decision
belong to `ActionRouter` (§4 step 6), not here — there is exactly one
quantisation point.

## 8. Fire fusion

`pewpew.input.fire`, pure Python, time supplied by `poll(now)`.

`FireArbiter(*, debounce_s=FIRE_DEBOUNCE_S (0.12))`:

- `deliberate_action()` and `spoken_fire()` each set an "edge pending" flag.
- `poll(now) -> bool`. If any edge is pending **and** `now - last_shot >=
  debounce_s`: clear all pending edges, set `last_shot = now`, return `True`
  (so a click and a "pew pew" 30 ms apart fire once). An edge that arrives while
  `now - last_shot < debounce_s` is **discarded, not queued** — it does not
  produce a delayed shot. Otherwise return `False`.
- `reset()` clears pending edges and `last_shot`; called by `release_all()`.

`debounce_s` alone defines the minimum inter-shot interval. (An earlier draft
carried a separate `cooldown_s` for a future auto-fire guard; cut as YAGNI.)

`DeliberateActionSource` protocol: `activation_edge() -> bool` (consumed each
tick). `SpokenFireSource` protocol: `spoken_fire_edge() -> bool`.
`NullSpokenFireSource` returns `False` forever (3a default).
`DebugKeySpokenFireSource` returns `True` once per `F9` press, and only when
`DOOMED_PRISM_DEBUG_FIRE` is set. `FakeSpokenFireSource` (test fakes) exposes
`trigger()`.

## 9. Input sources

`pewpew.input.source` / `pewpew.input.simulator_source`.

`InputSource` protocol: `sample(now) -> InputSample`. `InputSample` is a frozen
dataclass: `gaze_xy: tuple[int, int] | None`, `activation_edge: bool`,
`pause_edge: bool`, `debug_fire_edge: bool`. Edges mean "did this happen since
the last `sample()`" and are cleared by the call.

`SimulatorInputSource(widget)` installs a Qt event filter on the host widget and
enables mouse tracking:

- `MouseMove` → store the position in the widget's 640×640 coordinate space,
  clamped.
- `MouseButtonPress` (left) → `activation_edge`.
- `KeyPress` `Return` / `Enter` → `pause_edge` (§6 "Enter represents the
  physical ClickButton"; ClickButton opens pause / emergency).
- `KeyPress` `F9`, **only when `DOOMED_PRISM_DEBUG_FIRE` is set** →
  `debug_fire_edge` (gate scaffold for spoken-fire fusion without real audio;
  removed when 3b's real detector lands).
- `Leave` → `gaze_xy` becomes `None` until the pointer returns, so
  release-all-on-leave is automatic.

`PrismInputSource` raises `NotImplementedError("Prism gaze/blink input arrives
with the hardware phase")`.

## 10. The Crispy Doom IPC-input patch (patch 2 of the series)

`patches/crispy-doom-ipc-input.diff`, GPL-2.0-or-later, authored against the
tree with `crispy-doom-fb-export.diff` already applied, targeting the same
`crispy-doom-7.1` tag.

**New `src/i_ipc_input.c` / `.h`** (GPL-2.0-or-later header matching Crispy's
style; upstream notices in edited files preserved):

- `void IPC_Input_Init(void)` — read `DOOMED_PRISM_IPC_ADDR`; unset or empty →
  `ipc_enabled = 0`, return (upstream-identical build). **Both platforms:** open
  the socket, complete a **blocking** `connect()` first, then set the socket
  non-blocking. POSIX: `socket(AF_UNIX, SOCK_STREAM, 0)`, `connect` to the path.
  Windows: `WSAStartup`, `socket(AF_INET, SOCK_STREAM, 0)`, `connect` to
  `127.0.0.1:<port>`. Send `HELLO(IPC_PROTOCOL_VERSION)`. Spin-read the server's
  `HELLO` for at most `IPC_HELLO_TIMEOUT_S` (2 s); on timeout **or** a version
  mismatch, **close the socket** and set `ipc_enabled = 0` (so the server sees
  EOF and the host's "engine did not connect input" path fires) — never
  half-disable while leaving the socket open.
- `void IPC_Input_Pump(void)` — if disabled, return. Non-blocking `recv` into an
  8-byte staging buffer; for each complete frame, translate and `D_PostEvent`:
  - `ACTION` `MOVE_FORWARD` / `MOVE_BACKWARD`: `value != 0` → `ev_keydown` of
    `key_up` / `key_down` (Crispy's configured bindings) and set a `held[]` bit;
    `value == 0` → `ev_keyup` and clear the bit.
  - `TURN` `TURN_LEFT` / `TURN_RIGHT`: `int d = value; if (d > IPC_TURN_CLAMP) d
    = IPC_TURN_CLAMP;` then `D_PostEvent(&(event_t){ev_mouse, mousebuttons_now,
    (code == TURN_LEFT ? -d : d), 0})` — direction from `code`, magnitude from
    `value`, `data1` carries the current mouse-button bitmap (not `0`, so an
    injected turn does not clear `mousebuttons[]` for a tester using the SDL
    fallback). Post only when `d != 0`.
  - `PULSE` `FIRE` / `USE`: `ev_keydown` of `key_fire` / `key_use` now, and
    schedule the paired `ev_keyup` for `PULSE_HOLD_TICS` (2) pump calls later —
    a small per-key countdown array, decremented once per `IPC_Input_Pump()`.
    Holding the key across ≥ 1 built tic is required because `G_BuildTiccmd`
    level-polls `gamekeydown[key_fire]`; a same-pump keydown+keyup nets to
    "not pressed" and fires nothing. `PULSE_HOLD_TICS < FIRE_DEBOUNCE_S` in
    tics, so consecutive shots never overlap.
  - `DISCRETE` `PAUSE` → `ev_keydown` then (next pump) `ev_keyup` of the pause
    key. 3a handles exactly `{PAUSE}`; 3b appends `MENU_*` and
    weapon/automap/save/load/exit.
  - `BYE` → run the release-all below, keep the socket readable for EOF, set
    `ipc_enabled = 0`.
  - `recv` returns `0` (EOF) or errors non-`EWOULDBLOCK`/`EAGAIN` →
    **release-all**: for every set `held[]` bit post the matching `ev_keyup`;
    post a defensive `ev_keyup` for `key_fire` / `key_use`; `ipc_enabled = 0`;
    close the socket. DOOM continues on SDL input.
- `void IPC_Input_Shutdown(void)` — release-all, close the socket, `WSACleanup`
  on Windows. Idempotent (guarded by `ipc_enabled` plus a `socket >= 0` check).
  Does not `unlink` — the server owns the path.

**Call sites (patch 2 hunks):**

- `IPC_Input_Init();` immediately after `FB_Export_Init();` in `I_InitGraphics`
  (`src/i_video.c`) — that context line exists because patch 1 is applied first.
- `IPC_Input_Pump();` **once per built tic**, in `BuildNewTic()` in
  `src/d_loop.c`, immediately before `loop_interface->ProcessEvents()`, so
  injected and SDL events share one queue and one `G_BuildTiccmd`. **Binding
  invariant:** exactly one pump per game tic, after SDL events are drained and
  before `G_BuildTiccmd`. `BuildNewTic()` is expected to satisfy this at
  `crispy-doom-7.1`; the final function and line are recorded in the patch
  header comment (as M2 §0 did for its hook). Any hook that violates the
  once-per-tic-before-`BuildTiccmd` invariant is a design change, not an
  implementation detail. (`TryRunTics()` does **not** satisfy it — it can build
  0, 1, or several tics per call.)
- `IPC_Input_Shutdown();` immediately before `FB_Export_Shutdown();` in
  `I_ShutdownGraphics`.
- Extend patch 1's POSIX `fb_signal_handler` to also call
  `IPC_Input_Shutdown()`. This is the one place patch 2 modifies a patch-1 line;
  it is a single added call inside an existing function body, not a conflicting
  edit of the same line.

**`src/CMakeLists.txt`:** add `i_ipc_input.c i_ipc_input.h` to the source list
(a different line from patch 1's `i_framebuffer_export.*` insertion); `if(WIN32)
list(APPEND EXTRA_LIBS ws2_32)`.

**Constants** shared byte-for-byte with `pewpew.ipc.protocol` and the §5 table:
`IPC_FRAME_SIZE 8`, `IPC_PROTOCOL_VERSION 1`, the `MessageType` values, and the
action `code`s. `PULSE_HOLD_TICS` and `IPC_TURN_CLAMP` are C-side constants
(R11).

## 11. Reaching a live game for the gate

The 3a gate needs first-person gameplay without the SDL keyboard, and there is
no menu-navigation action in 3a (R6). Instead, `DoomProcess` appends
`-warp <DOOMED_PRISM_WARP> -skill <DOOMED_PRISM_SKILL or 3>` to Crispy's argv
whenever `DOOMED_PRISM_WARP` is set (Chocolate/Crispy boot straight into that
map with no menu). The gate checklist and `ci_ipc_smoke.py` set
`DOOMED_PRISM_WARP="1 1"` for a Freedoom Doom-1 IWAD. Normal desktop runs leave
it unset and get the usual title/menu (the tester may use the SDL keyboard once
to start a game — but the gate uses `-warp`, so the whole run is IPC-only).
Menu / weapon / save navigation via input returns in 3b with the voice grammar.

## 12. Error handling and lifecycle

- **Child not connected yet.** `server.is_connected` is `False`; `send` is a
  no-op; the host keeps ticking. M2's 10 s "engine did not export frames"
  deadline already covers a child that never starts.
- **IPC handshake never completes.** A child that exports frames but never
  completes the `HELLO` within `IPC_HANDSHAKE_TIMEOUT_S` (10 s, armed from
  `showEvent`), or whose `HELLO` version mismatches (`server.protocol_mismatch`
  set), runs `cleanup()` then raises — `RuntimeError("engine did not connect
  input")` for a timeout, `RuntimeError("input protocol mismatch")` for a
  version mismatch. Parallel to M2's `FrameSegmentError` handling. This strict
  behaviour is correct for the 3a gate ("does IPC-only input work"); a future
  non-gate build may choose to degrade to SDL-fallback instead of raising — a
  decision deferred with 3b.
- **Child disconnect (`on_disconnect` while the child is still polling as
  alive).** The host runs `pipeline.release_all()` (emits nothing — the socket
  is gone) and `server.close()`; it does **not** send `PAUSE`. Full `cleanup()`
  still runs later via `closeEvent` / `aboutToQuit` in R9 order.
- **Child process dies (`engine.poll()` not `None`).** §4 step 10: stop the
  timer, `release_all()`, `server.close()`.
- **Supervisor dies (Python gone).** The child's `recv` returns `0`; the C
  release-all posts `ev_keyup` for held `MOVE_*` keys and fire/use; DOOM keeps
  running on SDL input, then exits when its window closes (M2 lifecycle).
- **Raven sleep / conceal (`hideEvent`), guarded by `not
  _shutdown_requested`.** `pipeline.release_all()`, then if `not
  pipeline.paused` send one `DISCRETE PAUSE`, set `pipeline.paused = True`, show
  `_PauseOverlay`. **`showEvent` after start, same guard, is symmetric:** if
  `pipeline.paused` send one `DISCRETE PAUSE` (unpause), set `paused = False`,
  hide the overlay; `release_all()` for a fresh gaze acquire; restart the timer.
  A spurious hide (window covered) therefore pauses and the matching show
  unpauses — non-destructive and self-correcting.
- **`_PauseOverlay`.** A host-side indicator driven solely by `pipeline.paused`
  (a bool, not a press count), reset to `False` by `release_all()`. Crispy
  Doom's own pause stays authoritative; the indicator can drift if DOOM pauses
  by another route — acceptable for 3a. Emitted content, not a black panel
  (§5): the word `PAUSED` in an emitted-light colour. It exists because §6
  requires host-side pause feedback a voice failure cannot remove, and voice is
  3b.
- **IPC send.** Blocking socket, `settimeout(0.05)`. A `socket.timeout` or a
  reset is a disconnect, not a "transient drop" — there is no partial-frame
  path, so the C fixed-frame reader never desyncs.
- **Stale segment / socket.** The per-run random socket name plus the
  server-side `unlink` before `bind` make collisions negligible (M2 discipline).

## 13. Build and CI

- `scripts/build_crispy.py` gains
  `PATCHES = ("patches/crispy-doom-fb-export.diff",
  "patches/crispy-doom-ipc-input.diff")`. `plan_commands` emits **one**
  `git -C <dir> apply <p1> <p2>` (real build) or **one**
  `git -C <dir> apply --check <p1> <p2>` (under `--check`). `git apply`
  validates every hunk of the whole series before modifying the tree. The
  `.doomed-prism-applied` marker is written **once**, only after that single
  apply command succeeds; a failed series leaves no marker and the next run
  re-attempts the whole series. Tests: a series where the second patch fails →
  no marker → re-attempt; `--check` emits the single combined invocation.
- `crispy-doom.lock` unchanged.
- `.github/workflows/ci.yml`: add `feature/doomed-prism-m3` to `on.push.branches`
  (a push to the M3 branch otherwise runs no CI; PRs still trigger).
  `build_crispy.py --check` now covers the series with no other workflow change.
  The `linux-build-and-posix-smoke` job gains a step after the framebuffer
  smoke:

  ```
  DOOMED_PRISM_WARP="1 1" xvfb-run -a python scripts/ci_ipc_smoke.py "$EXE" /usr/share/games/doom/freedoom1.wad
  ```

- `ci_ipc_smoke.py`: bind an `IpcServer` at the **fixed** CI path
  `/tmp/doomed-prism-ipc-ci.sock` via the `address_factory` seam; launch the
  engine with `DOOMED_PRISM_FB_NAME`, `DOOMED_PRISM_IPC_ADDR`, and
  `DOOMED_PRISM_WARP`; `poll()` until connected; complete the handshake.
  **Fixed minimum assertion set (an exit criterion, §18):** `HELLO` handshake
  succeeds; a 500-frame action flood (`TURN_RIGHT` at varying magnitude, then a
  `PULSE FIRE` burst) is accepted; the framebuffer `frame_counter` keeps
  advancing throughout (engine alive and responsive under input load);
  `server.close()` then the engine exits within a bounded wait or on `SIGINT`;
  no orphan `crispy-doom`; the fixed socket path is gone. Any richer assertion
  (e.g. proving the view actually turned) may be added as an `xfail`-marked
  extra with a recorded reason, never removed silently. The script prints only
  the socket's basename and presence/absence, never a resolved path. A separate
  templated `$GITHUB_STEP_SUMMARY` block reports "IPC runtime validation"
  beside M2's "POSIX runtime validation" — templated `:white_check_mark:` lines
  only, it must **not** `cat` a log that could contain a resolved socket path.
  ARM64 stays annotated outstanding.
- Frame-level proof that a `TURN` actually turned the player stays in the
  Windows + Raven manual gate.

## 14. Publication safety and licensing

- New tracked files are original and GPL-2.0-or-later, matching the project:
  `patches/crispy-doom-ipc-input.diff`, `src/i_ipc_input.c` / `.h` **carrying
  GPL-2.0-or-later headers matching Crispy's style** with upstream notices in
  edited files preserved, the `pewpew.ipc` and `pewpew.input` modules and tests,
  `scripts/ci_ipc_smoke.py`, and the Milestone 3 documents.
- **Complete corresponding source** for the modified engine, post-M3, is
  **both** `.diff` files **plus** the unchanged `crispy-doom.lock` pin
  (repo / tag / commit / tarball_sha256). Each diff is independently reviewable;
  both ship beside any distributed patched binary, with Crispy's `COPYING` and
  notices.
- `scripts/check_publication_safety.py` needs **no change for 3a** (both new
  patches are text; no binary, IWAD, Raven source, or credential enters git),
  **but the scanner cannot detect vendored upstream C smuggled into a
  hand-authored `.diff`.** The 3a gate therefore adds a **diff-minimality
  check**: `git apply --stat patches/crispy-doom-ipc-input.diff` is recorded in
  `milestone-3a-checklist.md`; the diff must add only `src/i_ipc_input.c` / `.h`
  plus small hunks in `d_loop.c` / `i_video.c` / `src/CMakeLists.txt`; a stated
  net-added-line ceiling (e.g. ≤ 400) is checked by eye against the `--stat`
  output. A future scanner heuristic (flag any `patches/*.diff` that adds a
  complete `*.c` body over N lines) is noted as optional follow-up.
- The IPC address is a local socket path or `127.0.0.1:<port>`; it is not a
  secret and is passed by environment variable, never written to a tracked file
  (same discipline as `DOOMED_PRISM_FB_NAME`). Tracked gate docs record only
  presence/absence and the port, using the placeholders
  `<tempdir>/doomed-prism-ipc-<pid>-<token>.sock` and `127.0.0.1:<port>` —
  never a resolved path. `test_validation_docs_m3.py` asserts the placeholder
  form and the absence of `AppData\Local\Temp`, `/home/`, `/Users/` substrings.
- Any gameplay media promoted into tracked `docs/media/` for M3 uses **Freedoom
  only**, is reviewed frame-by-frame for usernames, file paths in title/URL
  bars, and commercial-IWAD identity, and — because the scanner does not decode
  media — this is a named manual gate item.
- **3b only:** `check_publication_safety.py` and `.gitignore` are extended for
  audio and acoustic-model files (§2 "In scope (3b)") **before** any 3b
  audio/model code lands. The §9 licence-review result is committed as text;
  the library, any model, and all calibration audio never enter git. The 3b
  decision-gate doc carries a "no model or audio file committed" objective check
  and both scan invocations.

## 15. Testing

All tests run without Crispy Doom, Raven Framework, an IWAD, a C toolchain, or a
display, using project-owned fakes, on the same pytest as M2. `IpcServer` tests
bind a **real in-process loopback listener** (`127.0.0.1:0` on any platform, or
`AF_UNIX` under `tmp_path` on POSIX) with **no external process** —
`tests/fakes/fake_ipc.py`'s `FakeIpcClient` connects to it in-process. The
`address_factory` seam only selects the platform branch and the path; it is not
a pre-connected `socketpair` injector.

- **`pewpew.ipc.protocol`.** `encode`/`decode` round-trip (`decode(encode(m)) ==
  m`) for every `MessageType` with wire-form ints; `decode` on a partial buffer
  returns `(None, buffer)`; two frames in one buffer decode in sequence; a bad
  `version` and an unknown `type` raise `IpcProtocolError`; every frame is
  exactly 8 bytes; little-endian order asserted against a hand-packed literal;
  a test asserts `Action` enum values equal the §5 `code` table.
- **`pewpew.ipc.server`.** Real in-process listener: `start()` returns the
  platform address shape and rejects an over-long POSIX path; `poll()` accepts
  one client and accepts-then-closes a second without disturbing the first;
  `send` before a connected/handshaken client is a no-op; the `HELLO` handshake
  flips `is_connected` on a match and sets `protocol_mismatch` + closes on a
  mismatch; a client close makes the next `poll()` fire `on_disconnect` exactly
  once; a `settimeout` send timeout is surfaced as a disconnect; `close()`
  unlinks the POSIX path and is idempotent.
- **`pewpew.input.actions`.** `set_held` quantises turn magnitude to
  `MAGNITUDE_STEPS` and emits a `TURN`/`ACTION` frame only when the quantised
  step or on/off state changed (a sub-quantum magnitude change emits nothing);
  the turn wire scaling (`round(magnitude * TURN_MAX_MOUSE_DELTA)`, clamped to
  `[0, TURN_MAX_MOUSE_DELTA]`) is asserted for representative magnitudes
  including `1.0` and an over-range guard; `MOVE_*` emit `value = 10000` on
  hold, `0` on release, no analog stream; `pulse` / `discrete` emit one frame;
  `release_all` emits a `0`-value frame for every held action and nothing for
  already-released ones; the sink receives `Message` objects whose `code`
  matches the §5 table.
- **`pewpew.input.gaze`.** `GazeZoneMap.resolve` for the dead-zone centre
  (empty), each band (correct action; magnitude monotonically increasing as the
  point moves outward), each corner (two actions), and the mutual exclusivity of
  the three families at an outside-both point. `GazeFilter` with an explicit
  `now`: an action needs `dwell_s` of continuous presence before it appears; a
  `grace_s` dropout is ridden out, a longer absence releases; a region *change*
  releases the outgoing action on the same tick; the turn-magnitude EMA ramps
  and re-seeds on re-acquisition.
- **`pewpew.input.fire`.** A single edge fires once; two edges inside
  `debounce_s` fire once; edges `debounce_s` apart fire twice; three edges at
  `t = 0, 0.05, 0.20` with `debounce_s = 0.12` → 2 shots (the mid edge is
  discarded, not queued); `deliberate` and `spoken` edges fuse; `reset()` drops
  pending edges. `NullSpokenFireSource` never fires; `FakeSpokenFireSource.
  trigger()` does; `DebugKeySpokenFireSource` is inert unless
  `DOOMED_PRISM_DEBUG_FIRE` is set.
- **`pewpew.input.pipeline`.** With a `FakeInputSource` and a `FakeIpcServer`
  recording sent `Message`s: a scripted gaze track produces the expected frame
  sequence; an `activation_edge` produces a `FIRE` pulse; a `pause_edge` toggles
  `paused` and sends one `DISCRETE PAUSE`; `release_all()` emits the full set of
  `0`-value frames and resets `paused`; a disconnect mid-track stops sends
  without raising.
- **`pewpew.input.simulator_source`** with `pytest-qt`: synthesised
  `QMouseEvent` / `QKeyEvent` produce the right `InputSample`; `Leave` clears
  `gaze_xy`; `F9` sets `debug_fire_edge` only when `DOOMED_PRISM_DEBUG_FIRE` is
  set; edges are one-shot.
- **`pewpew.engine`.** `start(ipc_address=…)` puts `DOOMED_PRISM_IPC_ADDR` in
  the child env (a fake `popen_factory` captures `env=`); `DOOMED_PRISM_WARP`
  set → argv gains `-warp 1 1 -skill 3`, unset → argv unchanged; `ipc_address`
  property; `stop()` does **not** touch the socket path. Existing
  `DOOMED_PRISM_FB_NAME` tests still pass.
- **`pewpew.host_widget`** with `pytest-qt` and injected fakes: `showEvent`
  starts the server before the engine and passes the address; `_on_tick` calls
  `server.poll()` **before** any early return and calls `pipeline.tick()` only
  past the frame-wait; `hideEvent` (not shutting down) runs `release_all()` +
  one `PAUSE` + shows the overlay, and `showEvent` after start is symmetric
  (unpause + hide overlay); a child disconnect runs `release_all()` +
  `server.close()` and **no** `PAUSE`; `cleanup()` runs stop-tick → release-all
  → server-close → reader-close → engine-stop in that order (recorded on fakes)
  and is idempotent; the handshake-timeout path raises `RuntimeError("engine did
  not connect input")` after cleanup and the version-mismatch path raises
  `RuntimeError("input protocol mismatch")` after cleanup.
- **`scripts/build_crispy.py`.** `plan_commands` emits a **single** combined
  `git apply` (and a single `git apply --check`) for the whole `PATCHES` tuple,
  in order; the marker is written once, only after that command; a run where the
  series apply fails writes no marker and the next run re-attempts. Existing
  single-patch tests updated to the tuple.
- **`tests/test_distribution_metadata.py`.** Expectations updated for the new
  modules, the new patch, and `scripts/ci_ipc_smoke.py`.
- **`tests/test_validation_docs_m3.py`** (new, mirroring
  `test_validation_docs.py`): the 3a checklist and result carry the four
  decision strings, the "IPC-only, SDL window unfocused" phrasing, the
  release-all lifecycle checks, both publication-safety scan invocations, the
  `git apply --stat` diff-minimality step, and only the placeholder IPC-address
  forms (no `AppData\Local\Temp` / `/home/` / `/Users/`).
- **`scripts/ci_ipc_smoke.py`** is exercised only in CI (Linux, real build); it
  is not a pytest module, prints `IPC runtime smoke: PASS/FAIL`, exits
  accordingly, and skips with exit 0 on non-POSIX.

## 16. Delivery sequence

Each plan uses the Milestone 2 plan structure — a Goal / Architecture / Tech
Stack / Spec header, a Global Constraints list (with the exact values from R6,
R11, §5), and per-task **Files** / **Interfaces** / failing-test-first
(RED → GREEN → commit) steps — and names its feature branch
(`feature/doomed-prism-m3`).

### Plan 3a — `docs/superpowers/plans/2026-09-05-doomed-prism-milestone-3a.md`

1. `pewpew.ipc.protocol` — frame encode/decode, `Message`, `MessageType`,
   `IpcProtocolError`, the §5 `code` table as `Action`-independent ints;
   `tests/test_ipc_protocol.py`.
2. `pewpew.ipc.server` — dual-transport `IpcServer`, blocking client socket with
   send timeout, cross-tick handshake, disconnect; `tests/fakes/fake_ipc.py`,
   `tests/test_ipc_server.py`.
3. `patches/crispy-doom-ipc-input.diff` — `i_ipc_input.c` / `.h`, the
   `BuildNewTic()` pump hook, the `PULSE_HOLD_TICS` scheduler, `CMakeLists.txt`,
   authored against the patch-1 tree; verified by a manual local build of the
   series.
4. `scripts/build_crispy.py` — `PATCHES` tuple, single combined apply /
   `--check`, marker-once semantics; `tests/test_build_crispy.py` updates.
   *(A clean split point: tasks 1–4 are the transport core, R1 note.)*
5. `pewpew.input.actions` — `Action` (values = §5 table), `HeldAction`,
   `ActionRouter` (sole quantiser); `tests/test_input_actions.py`.
6. `pewpew.input.gaze` — `GazeZoneMap`, `GazeFilter` (single release rule,
   `now`-argument time); `tests/test_input_gaze.py`.
7. `pewpew.input.fire` — `FireArbiter` (discard-in-window), source protocols,
   `NullSpokenFireSource`; `tests/test_input_fire.py`.
8. `pewpew.input.source` + `pewpew.input.simulator_source` — `InputSource`,
   `InputSample` (incl. `debug_fire_edge`), `SimulatorInputSource`,
   `PrismInputSource` stub, `DebugKeySpokenFireSource`;
   `tests/test_input_source.py` + a `pytest-qt` module.
9. `pewpew.input.pipeline` — `InputPipeline.tick` / `release_all` /
   `toggle_pause` / `paused`; `tests/test_input_pipeline.py`,
   `tests/fakes/fake_input.py`.
10. `pewpew.engine` — `start(ipc_address=…)`, `DOOMED_PRISM_WARP` argv,
    `ipc_address`; `tests/test_engine.py` updates.
11. `pewpew.host_widget` — server lifecycle, `server.poll()` before early
    returns, input tick, symmetric hide/show pause, `_PauseOverlay`,
    release-all wiring, `cleanup()` ordering; `tests/test_host_widget*.py`
    updates.
12. README refresh (License names the two patches; Current status / What comes
    next; one line that voice is 3b); `tests/test_distribution_metadata.py`;
    full `pytest -q` and both `check_publication_safety.py` scans green.
13. `scripts/ci_ipc_smoke.py` (fixed CI socket path, templated summary) and the
    `ci.yml` step + `feature/doomed-prism-m3` push trigger; new
    `tests/test_validation_docs_m3.py`.
14. `docs/validation/milestone-3a-checklist.md` (incl. the `git apply --stat`
    diff-minimality step and the placeholder-address discipline); run the 3a
    decision gate; record `docs/validation/milestone-3a-result.md`.

### Plan 3b — `docs/superpowers/plans/2026-09-05-doomed-prism-milestone-3b.md`

Written only after 3a's gate records PASS.

0. Extend `check_publication_safety.py` (audio + model suffixes) +
   `tests/test_publication_safety.py` + `.gitignore`, **before** any other 3b
   task.
1. §9 offline-speech-library licence review; commit the result as text; stop on
   a fail.
2. Desktop audio-capture adapter behind an `AudioSource` protocol; fake.
3. Real "pew pew" keyword detector implementing 3a's `SpokenFireSource`;
   calibration-sample handling (samples never committed).
4. Closed English command grammar (token `pew pew`, R13) + router → the R6
   "later" discrete actions incl. `MENU_*`; confirmation flow for
   `save`/`load`/`exit`.
5. Append the extra discrete `code`s and their DOOM-key mapping to
   `crispy-doom-ipc-input.diff` (mutating the 3a corresponding-source artifact —
   still one reviewable diff).
6. `host_widget` / `pipeline` wiring for the voice source; a crashed voice
   worker disables voice and preserves click/blink and Enter (§8).
7. `docs/validation/milestone-3b-checklist.md` (incl. "no model/audio
   committed" + both scans); run the 3b gate; record the result.

## 17. Milestone 3a decision gate

Run manually on Windows against a separately installed Raven Framework. Keep all
evidence under gitignored `artifacts/milestone-3/`. The M2 gate's rules apply
verbatim: no Raven source, credentials, private paths, or commercial IWAD
identity in the tracked checklist or result. Record the IPC address only as the
placeholders `<tempdir>/doomed-prism-ipc-<pid>-<token>.sock` and
`127.0.0.1:<port>`, and only its presence/absence plus the port number.

**The hard question.** Does IPC-only normalized input drive real DOOM gameplay
inside the Qt viewport — gaze steering, progressive turn, debounced click-fire,
fused spoken-fire (the `F9` debug source with `DOOMED_PRISM_DEBUG_FIRE=1`),
Enter-pause — with Crispy's SDL window unfocused the entire time, and does every
lifecycle transition release all held inputs with no stuck key and no orphan?

**Environment and launch.** `python scripts/build_crispy.py` builds the patched
engine from the series; `--check` passes for the series; record the pinned tag
and commit, compiler, and SDL2 versions. Record `git apply --stat
patches/crispy-doom-ipc-input.diff` and confirm it adds only
`src/i_ipc_input.c` / `.h` plus small hunks in `d_loop.c` / `i_video.c` /
`src/CMakeLists.txt`, within the stated line ceiling. `doomed-prism validate`
exits 0. `python -m pytest -q` green; `check_publication_safety.py --root .` and
`--history` exit 0. Establish the M2 before/after crispy-doom PID baseline. Set
`DOOMED_PRISM_WARP="1 1"` and `DOOMED_PRISM_DEBUG_FIRE=1`. Launch
`doomed-prism run-desktop`.

**Objective checks.**

- Exactly one new crispy-doom PID.
- The IPC socket is present while running (POSIX: the placeholder path exists;
  Windows: the PewPew process owns a listening `127.0.0.1:<port>`) and gone
  after close.
- A `FrameReader` probe still shows `frame_counter` advancing (M2 path
  unbroken).
- With **Crispy's SDL window minimised or behind the Raven Simulator** for the
  whole run:
  - Gaze into the left turn band turns the DOOM view left; right band, right;
    returning to the dead zone stops the turn within ~2 ticks.
  - Gaze farther from the dead zone turns visibly faster than gaze just outside
    it (progressive turn, §6).
  - Gaze into the upper band walks forward; lower band, backward; an upper
    corner walks forward while turning.
  - A click fires one shot; five fast clicks fire fewer than five shots
    (debounce, `PULSE_HOLD_TICS` hold understood).
  - `F9` fires a shot through the same path; a click and an `F9` within ~30 ms
    fire once (fusion).
  - `Enter` shows the `PAUSED` overlay and pauses; `Enter` again resumes. No
    SDL-window focus was used at any point.
- No `SetParent` anywhere (M2 regression check, still valid).

**Lifecycle checks.**

- Trigger Raven sleep/conceal (or hide the host): the game pauses, the overlay
  shows; on resume it unpauses and no key is stuck — a held turn from before the
  hide does not persist.
- Kill the PewPew process while a turn is held: DOOM stops turning (the injected
  `ev_mouse` deltas stop; the C-side release-all posts `ev_keyup` for held
  `MOVE_*` keys) and remains running on SDL input; no orphan after its window is
  closed.
- Normal close: `cleanup()` runs stop-tick → release-all → server-close →
  reader-close → engine-stop with no exception; one PID gone; socket path
  removed.

**Per-mode evidence.** Raw plus each available optical mode (Night, Day,
Outdoors, Camera): one short local video or two time-separated captures showing
gaze-driven view motion and a fired shot inside the composited viewport, with
the SDL window not focused. Night carries the full dynamic proof; the others may
be lighter, as in the M2 gate. Any clip promoted into tracked `docs/media/` is
Freedoom-only and reviewed frame-by-frame for usernames, paths, and IWAD
identity.

**Hard decision, recorded in the single final field of
`docs/validation/milestone-3a-result.md`.**

- **PASS — IPC input path viable.** Gaze movement and progressive turn,
  click-fire with debounce, spoken-fire fusion via the `F9` source, and
  Enter-pause all drive the composited DOOM with the SDL window unfocused; every
  lifecycle transition releases held input with no stuck key; one clean PID, no
  orphan, socket removed, no `cleanup()` exception; the M2 framebuffer path
  still advances.
- **FAIL — IPC input path insufficient.** The engine connects and the handshake
  completes, but injected events do not reliably drive gameplay (for example
  `ev_mouse` turning is unusable, or `D_PostEvent` from the pump races the tic
  and drops inputs). This opens a design task for the R5 keyboard-duty-cycle
  turn or a different injection point — it does not discard the §4 IPC boundary.
- **BLOCKED/RETRY — implementation or environment failure.** Build, launch,
  connection, handshake, geometry, lifecycle, or evidence collection fails. Fix
  the named issue and repeat with a fresh PID. Does not select an injection
  design.
- **PENDING — incomplete evidence.** Evidence incomplete or a named optical mode
  unavailable without a documented reason. Never a pass.

**Final automated verification and commit.** As in M2: `python -m pytest -q`,
`git diff --check`, an exact-path `git add` of only
`docs/validation/milestone-3a-checklist.md` and
`docs/validation/milestone-3a-result.md`, `check_publication_safety.py --root .`
and `--history`, then `git commit -m "docs: record IPC input path result"`. The
README refresh (§16 task 12) lands with the implementation commits, not this
decision-record commit.

## 18. Exit criteria

Milestone 3a is complete when all automated tests pass, both publication-safety
scans are clean, CI is green **including `ci_ipc_smoke.py` at its fixed minimum
assertion set (§13)**, and `milestone-3a-result.md` records a reproducible PASS
or FAIL. A FAIL is a valid engineering result: it keeps the §4 IPC boundary and
reopens only the event-injection method.

Milestone 3b is complete when `check_publication_safety.py` and `.gitignore`
cover audio/model files, the §9 licence review is recorded as a pass, the
offline grammar and the real spoken-fire detector work end-to-end with fakes in
CI and on the Windows gate, no model or audio file is tracked, and
`milestone-3b-result.md` records a reproducible PASS or FAIL.
