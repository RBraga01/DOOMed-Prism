# DOOMed Prism — Milestone 3 Design: Input and the IPC Boundary

Date: 2026-09-05
Status: Design proposed. Not yet reviewed. Not implemented.
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
not available for interactive clarifying questions. The decisions that an
interactive brainstorm would have surfaced as questions are recorded here as
explicit rulings, each with its rationale and the cost of being wrong, for the
user's later review and for the separate auditor agents to challenge. Section
references are to `2026-09-02-doomed-prism-design.md` unless noted.

### R1 — Milestone 3 ships as two plans: 3a (input core) and 3b (offline voice)

One spec, two implementation plans, both under the Milestone 3 umbrella.

- **3a — input core and the IPC boundary.** The IPC protocol and transport, the
  Crispy Doom IPC-input patch, the normalized-action model, gaze-zone movement
  with progressive turning, fire fusion (deliberate action + spoken fire), the
  simulator input source, lifecycle wiring, CI, and the 3a decision gate.
- **3b — offline voice.** The closed English command grammar (menus, weapon
  switching, automap, save/load, exit) and a real acoustic "pew pew" keyword
  detector, plus the §9 offline-speech-library licence review, plus a 3b
  decision gate.

**Rationale.** §9 requires a licence review of "offline speech libraries,
acoustic models, fonts, media, and build tools" before they are committed or
packaged, and speech capture needs an audio dependency (the Raven microphone API
on device, a capture library on desktop) that is unresolved. Neither may gate
the input architecture, which is the load-bearing part of Milestone 3. Splitting
the plans lets 3a reach its decision gate and unblock the hardware-phase
questions while 3b's licence review proceeds in parallel. The fire-fusion unit
built in 3a already carries the spoken-fire source interface (R7), so 3b adds a
real detector and the grammar without reworking 3a.

**Cost if wrong.** If the auditors judge a minimal, permissively licensed
keyword spotter small enough to keep in 3a, fold 3b's detector back in; the
`SpokenFireSource` protocol is unchanged either way. If voice must ship as one
unit with 3a, merge the plans; the spec already covers both.

### R2 — IPC transport: `AF_UNIX` stream socket on POSIX, `127.0.0.1` TCP stream socket on Windows

Both are `SOCK_STREAM`, so message framing and parsing are shared code; only
bind/connect differ, guarded by `#ifdef _WIN32` in the C patch exactly as M2's
exporter guards `shm_open` against `CreateFileMappingA`.

**Rationale.** §4 specifies "a Unix domain socket on Raven/Linux and an
equivalent local transport on development platforms". CPython does not expose
`socket.AF_UNIX` on Windows, so a loopback TCP socket bound to `127.0.0.1:0`
(OS-assigned port) is the pragmatic desktop transport. It is not reachable
off-host and carries no secret. Raven/Linux — the only platform that matters for
the device — uses a real Unix domain socket.

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

### R4 — The Crispy Doom IPC-input patch is a second, separate patch file that injects `D_PostEvent` events

`patches/crispy-doom-ipc-input.diff` adds `src/i_ipc_input.c` / `.h` and small
call sites in the engine's input pump. SDL keyboard input in Crispy is **left
untouched** — IPC is an *additional* event source, not a replacement — so the
tester keeps a manual fallback and the patch stays minimal.
`scripts/build_crispy.py` grows an ordered `PATCHES` list; `--check` checks each;
the applied-marker means "all applied".

**Rationale.** Two focused diffs are each independently reviewable GPL
corresponding-source artifacts (the project's many-small-files preference).
Injecting through `D_PostEvent` reuses DOOM's own event queue and keeps game
logic, key bindings, and `G_BuildTiccmd` unchanged.

**Cost if wrong.** If a single combined diff is later preferred, concatenate the
two files and drop the `PATCHES` list — modest `build_crispy.py` churn.

### R5 — Discrete actions and forward/back are injected as key events; analog turning is injected as synthetic mouse-x motion

DOOM's keyboard turn is stepwise and cannot express "turning speed increases as
gaze moves farther from the central dead zone" (§6) without a duty-cycle hack. A
synthetic `ev_mouse` event with an x-delta is DOOM's native analog-turn path.
The PewPew side computes the per-tic x-delta from the gaze distance and sends it
as a `TURN` message with a magnitude; the C patch is a pure translator. The
patch neutralises mouse acceleration and threshold for the injected stream
(`mouse_acceleration = 1.0`, `mouse_threshold = 0` applied to the injected path,
or the fixed default curve documented so the Python side inverts it).

**Cost if wrong.** If `ev_mouse` injection is unstable in the gate, fall back to
a keyboard duty-cycle turn (documented as the alternative). The normalized
action — `TURN_LEFT` / `TURN_RIGHT` with a magnitude `0.0–1.0` — is unchanged
either way, so only the C translator changes.

### R6 — Normalized action set for Milestone 3

§6 gives a "such as" list; this makes it explicit.

| Category | Actions (3a) | Later (3b / hardware) |
| --- | --- | --- |
| Held / analog | `MOVE_FORWARD`, `MOVE_BACKWARD`, `TURN_LEFT`, `TURN_RIGHT` — each with `magnitude: float` in `0.0–1.0` | — |
| Pulsed | `FIRE`, `USE` | — |
| Discrete | `PAUSE`, `MENU_CONFIRM`, `MENU_CANCEL` | `WEAPON_1..7`, `NEXT_WEAPON`, `PREV_WEAPON`, `AUTOMAP`, `SAVE_GAME`, `LOAD_GAME`, `EXIT_DOOM` (3b, with the voice grammar) |

Strafing is out of scope for M3. `MENU_CONFIRM` / `MENU_CANCEL` / `MENU_UP` /
`MENU_DOWN` (the last two added in §11) exist in 3a because the simulator input
source needs them to reach a live game from the attract loop and to operate the
pause overlay; they are never emitted from gameplay gaze.

**Cost if wrong.** Adding an action later is one row in the C mapping table plus
one message `code`; the wire format (R10) reserves the code space.

### R7 — Fire fusion has two abstract sources; only the deliberate-action source is real in 3a

`FireArbiter` consumes edges from a `DeliberateActionSource` (double-blink on
hardware, click in the simulator — §6) and a `SpokenFireSource` (spoken "pew
pew" — §6). 3a supplies a real `DeliberateActionSource` (simulator click) and a
`NullSpokenFireSource` that never fires; a `FakeSpokenFireSource` in the test
fakes drives the fusion path in tests and, wired to a debug key, in the 3a gate.
3b supplies the real acoustic `SpokenFireSource`. Both sources feed one `FIRE`
pulse through shared debounce and cooldown so a blink and a "pew pew" inside the
debounce window produce exactly one shot (§6).

**Cost if wrong.** None structural — the interface is designed for both sources
from the start.

### R8 — The Raven-facing input source sits behind an `InputSource` protocol; only `SimulatorInputSource` is implemented

`SimulatorInputSource` reads gaze position (mouse), focused-element activation
(click), and the physical button (Enter → `PAUSE`) from Qt events on the host
widget, never from Raven APIs directly (§6: "The game bridge does not depend
directly on Raven APIs"). `PrismInputSource` is a documented stub raising
`NotImplementedError`. Real gaze coordinates, a raw double-blink event, and
sensor entitlements are §12 hardware-phase items.

**Cost if wrong.** The protocol may need one more method for real gaze/blink
entitlements — a change §12 already anticipates.

### R9 — One `release_all()` covers sleep/conceal, IPC loss, and shutdown, on both sides

Python side: `InputPipeline.release_all()` clears the gaze filter, tells
`ActionRouter` to emit a zero-magnitude / key-up message for every currently
held action, and resets `FireArbiter`. Sleep/conceal then also sends
`PAUSE`; shutdown then tears down. `cleanup()` ordering becomes: stop the input
tick → `pipeline.release_all()` → `IpcServer.close()` → `reader.close()` →
`engine.stop()`.

C side: on socket EOF the patch posts a key-up for every action it is currently
holding and stops pumping, so a dead supervisor never leaves DOOM with a stuck
key (§4, §8).

**Cost if wrong.** Ordering tweaks. The invariant — "no held key survives a
lifecycle transition" — is what the gate checks.

### R10 — Wire format: a fixed 8-byte little-endian frame

`version: u8`, `type: u8`, `code: u16`, `value: i32` (all little-endian, matching
M2's little-endian shared-memory header). `type` ∈ `{HELLO, ACTION, PULSE,
DISCRETE, TURN, PING, BYE}`. `code` is the action id from R6. `value` carries a
held magnitude scaled to `0–10000`, a turn x-delta in mouse units, or `0`.
Fixed size means the C reader fills exactly 8 bytes per frame with a short-read
loop and never parses a length prefix. The first frame each side sends is
`HELLO` with `code = IPC_PROTOCOL_VERSION`; a mismatch closes the connection and
is surfaced as a startup failure, exactly like M2's `FrameSegmentError`.

**Cost if wrong.** If a variable-length message is ever needed (it is not for
M3's action set), add a `type` whose `value` is a follow-on byte count; existing
frames are unaffected.

### R11 — Input tunables are documented module constants, not `RuntimeConfig` fields

Dead-zone half-extents, entry dwell (~150 ms, §6), the turn-response curve, fire
debounce and cooldown, and jitter hysteresis live as `UPPER_SNAKE_CASE`
constants in the modules that use them. §6 calls the regions "configurable"; a
user-facing config surface is deferred until the manual gate shows tuning is
actually needed, at which point the constants become `RuntimeConfig` fields with
the same names.

**Cost if wrong.** A later mechanical refactor from constants to config fields.

### R12 — Out of scope for Milestone 3

Carried from the M2 scope fence and the user's "keep it focused" instruction:
performance modes, the governor, engine-versus-compositor metrics, Waveguide
Boost, ARM64 build validation, the shared OpenGL ES / Qt rendering surface, real
microphone capture in 3a, real gaze/blink hardware access, and any RavenOS
entitlement work. Audio and hardware gaze/blink are §12 hardware-phase items;
3b adds only *desktop* offline voice.

---

## 1. Problem

After Milestone 2, DOOM renders live inside the Raven Simulator, but the only
way to play it is to click Crispy Doom's separate SDL development window and use
the keyboard. M2 §8 states plainly: that window "is a temporary development-time
input sink that Milestone 3's IPC input path removes."

Milestone 3 makes DOOM playable through the Raven interaction model: gaze to
move and turn, a deliberate action (double blink on hardware, click in the
simulator) and a spoken "pew pew" to fire, and — in 3b — spoken commands for
menus and weapons. All input sources produce **normalized actions**
(`MOVE_FORWARD`, `TURN_LEFT`, `FIRE`, …) that travel to Crispy Doom over the
local IPC boundary §4 describes, instead of synthetic keystrokes aimed at a
window that must hold OS focus.

The hard question for the 3a decision gate: **does IPC-only normalized input
drive real DOOM gameplay inside the Qt viewport — gaze steering, progressive
turn, debounced click-fire, fused spoken-fire, and Enter-pause — with Crispy's
SDL window unfocused, and does every lifecycle transition release all held
inputs with no stuck key and no orphan process?**

## 2. Scope

### In scope (3a)

- A versioned, fixed-frame IPC protocol module (pure Python, no I/O).
- An `IpcServer` (PewPew side): dual transport per R2, single client,
  non-blocking, send-only for M3, disconnect callback.
- A second Crispy Doom patch, `patches/crispy-doom-ipc-input.diff`: connect to
  `DOOMED_PRISM_IPC_ADDR`, decode frames, `D_PostEvent` key and mouse events,
  release-all on EOF. SDL keyboard input untouched.
- `scripts/build_crispy.py` multi-patch support; both patches applied in order;
  `--check` covers both.
- The normalized action model and `ActionRouter` (held set, pulse, discrete,
  `release_all`), draining to an injected sink that maps to IPC messages.
- `GazeZoneMap` + `GazeFilter`: the §6 region layout, ~150 ms entry dwell,
  progressive turn magnitude, jitter hysteresis, immediate release on region
  exit.
- `FireArbiter` + the two source protocols (R7), with the real deliberate-action
  (simulator click) source and a null spoken-fire source in 3a.
- `InputSource` protocol + `SimulatorInputSource` (Qt events on the host) +
  `PrismInputSource` stub.
- `InputPipeline`: the one unit that wires source → gaze → fire → router →
  server, ticked from the host timer, with `release_all()`.
- `pewpew.engine` and `pewpew.host_widget` changes to own the server lifecycle,
  run the input tick, and release-all on sleep / IPC loss / shutdown.
- A minimal in-app pause indicator driven by `PAUSE` (Enter / ClickButton),
  because "a voice failure must never prevent pause or exit" (§6) and voice is
  3b.
- CI: a POSIX IPC runtime smoke test mirroring `ci_posix_smoke.py`.
- The 3a decision gate: `docs/validation/milestone-3-checklist.md` and
  `milestone-3-result.md`.

### In scope (3b, gated behind the §9 licence review)

- The closed offline English command grammar (§6): `open`/`use`, `next weapon`,
  `weapon one`–`weapon seven`, `map`, `pause`/`resume`, `save game`/`load game`
  (confirm), `exit Doom` (confirm).
- A real acoustic "pew pew" keyword detector behind the 3a `SpokenFireSource`
  protocol, calibrated with user samples, retaining recent recognised commands
  locally but not continuous audio (§6, §8).
- A desktop audio-capture adapter. The Raven microphone topology is a §12
  hardware-phase item and stays stubbed.
- The 3b decision gate.

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

Two processes, unchanged from §4 and M2. What M3 adds is a **control plane**
beside M2's frame plane.

```
PewPew Engine process                              Crispy Doom process (doubly patched)
  SimulatorInputSource  (Qt mouse / click / Enter)   I_InitGraphics
    | InputSample(gaze_xy, activation_edge, pause)      +- FB_Export_Init()          (M2, unchanged)
    v                                                   +- IPC_Input_Init()          <-- connects
  InputPipeline.tick(now)                                     DOOMED_PRISM_IPC_ADDR
    +- GazeZoneMap.resolve(x, y) -> {HeldAction}       I_FinishUpdate
    +- GazeFilter (dwell, hysteresis) -> stable set      +- FB_Export_Publish()       (M2, unchanged)
    +- FireArbiter (click edge + spoken edge)          D_ProcessEvents / input pump
    +- ActionRouter (held set, pulse, discrete)          +- IPC_Input_Pump()          <-- reads frames,
    v                                                          D_PostEvent(ev_keydown/up, ev_mouse)
  IpcServer.send(Message)  --8-byte frames-->  socket  --> IPC_Input reader
  IpcServer.on_disconnect  <-- socket EOF                  IPC_Input EOF -> post key-up for held, stop
```

### New and changed units

| Unit | Language | Responsibility | Depends on |
| --- | --- | --- | --- |
| `pewpew.ipc.protocol` | Python | `Message`, `MessageType`, `encode(msg) -> bytes`, `decode(buf) -> (Message | None, bytes)`; constants `IPC_MAGIC`, `IPC_PROTOCOL_VERSION`, `FRAME_SIZE = 8`. Pure. | `struct` (stdlib) |
| `pewpew.ipc.server` | Python | `IpcServer(address_factory=…)`: `start() -> str`, `poll() -> None` (accept pending client), `send(Message) -> None`, `is_connected: bool`, `on_disconnect: Callable`, `close()`. Non-blocking, single client, send-only. | `socket`, `selectors` (stdlib), `pewpew.ipc.protocol` |
| `pewpew.input.actions` | Python | `Action` (enum), `HeldAction(action, magnitude)`, `ActionRouter(sink)`: `set_held(frozenset[HeldAction])`, `pulse(Action)`, `discrete(Action)`, `release_all()`. Diffs the held set and emits `Message`s through `sink`. Pure + sink. | `pewpew.ipc.protocol` |
| `pewpew.input.gaze` | Python | `GazeZoneMap(surface_w, surface_h, *, dead_zone, …)`: `resolve(x, y) -> frozenset[HeldAction]` (region → actions + magnitude). `GazeFilter(clock, *, dwell_s, hysteresis)`: `update(raw_set, now) -> frozenset[HeldAction]` (entry dwell, exit-immediate, jitter hysteresis). Pure + clock. | `pewpew.input.actions` |
| `pewpew.input.fire` | Python | `FireArbiter(clock, *, debounce_s, cooldown_s)`: `deliberate_action()`, `spoken_fire()`, `poll(now) -> bool`. `DeliberateActionSource` / `SpokenFireSource` protocols; `NullSpokenFireSource`. Pure + clock. | — |
| `pewpew.input.source` | Python | `InputSource` protocol: `sample(now) -> InputSample`. `InputSample(gaze_xy: tuple[int,int] | None, activation_edge: bool, pause_edge: bool)`. `PrismInputSource` stub. | — |
| `pewpew.input.simulator_source` | Python | `SimulatorInputSource(widget)`: tracks the widget's mouse position, mouse-press edges, and Return-key edges via an installed Qt event filter; `sample(now)` returns the accumulated `InputSample`. | PySide6, `pewpew.input.source` |
| `pewpew.input.pipeline` | Python | `InputPipeline(source, server, *, clock, spoken_fire=NullSpokenFireSource())`: builds `GazeZoneMap`, `GazeFilter`, `FireArbiter`, `ActionRouter(sink=server-backed)`. `tick(now)`, `release_all()`. The single integration unit. | all of the above |
| `pewpew.engine` (modified) | Python | `start(*, ipc_address: str | None = None)` injects `DOOMED_PRISM_IPC_ADDR` into the child env; `ipc_address` property; `stop()` best-effort unlinks a POSIX socket path. Mirrors the existing `frame_segment_name` handling. | existing |
| `pewpew.host_widget` (modified) | Python | `showEvent`: `IpcServer.start()`, `engine.start(ipc_address=…)`, build `InputPipeline` from a `SimulatorInputSource`. `_on_tick` also runs `server.poll()` and `pipeline.tick(now)`. `hideEvent` / disconnect → `pipeline.release_all()` + `PAUSE`. `cleanup()` extended per R9. A `_PauseOverlay` child shown on `PAUSE`. | `pewpew.input.pipeline`, `pewpew.ipc.server` |
| `src/i_ipc_input.c` / `.h` (in the new patch) | C | `IPC_Input_Init()` (connect, non-blocking; no-op if `DOOMED_PRISM_IPC_ADDR` unset), `IPC_Input_Pump()` (decode frames → `D_PostEvent`; EOF → release held → stop), `IPC_Input_Shutdown()`. | BSD sockets / winsock; `d_event.h` |
| `src/i_video.c` etc. (in the new patch) | C | ~8 lines: `IPC_Input_Init()` by `FB_Export_Init()`; `IPC_Input_Pump()` in the event pump; `IPC_Input_Shutdown()` by `FB_Export_Shutdown()`. | the above |
| `scripts/build_crispy.py` (modified) | Python | `PATCHES` list; apply each in order; `--check` per patch; marker = all applied. | existing |
| `patches/crispy-doom-ipc-input.diff` | diff | The complete IPC-input modification. GPL-2.0-or-later. | — |
| `scripts/ci_ipc_smoke.py` | Python | Build the doubly-patched engine, accept its IPC connection, handshake, stream a scripted action sequence, assert the engine stays alive with `frame_counter` advancing, then clean teardown with no orphan and the socket removed. | `pewpew.ipc`, `pewpew.framebuffer` |

`crispy-doom.lock` is unchanged — both patches target the same pinned tag and
commit.

### Data flow, one host tick

1. `server.poll()` — accept the child's connection if pending; detect EOF and
   fire `on_disconnect`.
2. `sample = source.sample(now)` — gaze xy, activation edge, pause edge since the
   last tick.
3. `raw = gaze_map.resolve(*sample.gaze_xy)` when gaze is present, else empty.
4. `held = gaze_filter.update(raw, now)` — dwell-gated, hysteresis-smoothed.
5. `router.set_held(held)` — emits `ACTION` / `TURN` frames only for entries that
   changed (a new hold, a released hold, a magnitude delta past a threshold).
6. `if sample.activation_edge: fire.deliberate_action()`; poll the spoken source;
   `if fire.poll(now): router.pulse(FIRE)`.
7. `if sample.pause_edge: router.discrete(PAUSE)` and toggle `_PauseOverlay`.
8. Each `router` emission calls `server.send(msg)`; if `not server.is_connected`,
   the send is dropped (the child is not up yet or is gone) and the held state is
   still tracked so it can be re-sent or released later.

## 5. The IPC protocol

`pewpew.ipc.protocol`, stdlib only.

### Frame (little-endian, fixed 8 bytes)

| Offset | Field | Type | Notes |
| --- | --- | --- | --- |
| 0 | `version` | u8 | `IPC_PROTOCOL_VERSION` (`1`). Receiver rejects a mismatch. |
| 1 | `type` | u8 | `MessageType` |
| 2 | `code` | u16 | action id (R6) or, for `HELLO`, the sender's protocol version |
| 4 | `value` | i32 | held magnitude `0–10000`, turn x-delta (mouse units, signed), or `0` |

`IPC_MAGIC` is not on the wire — the fixed frame size and the `HELLO` exchange
are the framing and the sanity check. (M2's shared-memory header keeps its
`magic`; a stream socket with fixed frames does not need one.)

`MessageType`: `HELLO = 0`, `ACTION = 1` (held down/up: `value > 0` is the
magnitude, `value == 0` is release), `PULSE = 2` (`FIRE`, `USE`), `DISCRETE = 3`
(`PAUSE`, `MENU_CONFIRM`, `MENU_CANCEL`, `MENU_UP`, `MENU_DOWN`), `TURN = 4`
(`code` is `TURN_LEFT` or `TURN_RIGHT`, `value` is the signed x-delta for this
tic), `BYE = 6` (graceful server shutdown; the child releases held input and
keeps running on SDL input). Value `5` is reserved (a keepalive `PING` is not
needed for M3 — the socket EOF is the liveness signal — and the code space is
kept stable so a later version can add it without renumbering).

### Functions

- `encode(message: Message) -> bytes` — always 8 bytes.
- `decode(buffer: bytes) -> tuple[Message | None, bytes]` — consumes one whole
  frame from the front of `buffer`; returns `(None, buffer)` when fewer than 8
  bytes are buffered; raises `IpcProtocolError` on a version mismatch or an
  unknown `type`. The C side is the mirror: read into an 8-byte staging buffer,
  act, repeat.

`Message` is a `@dataclass(frozen=True)` with `type: MessageType`, `code: int`,
`value: int`, plus constructors `Message.action(a, magnitude)`,
`Message.turn(a, delta)`, `Message.pulse(a)`, `Message.discrete(a)`,
`Message.hello()`, `Message.bye()`.

## 6. The `IpcServer`

- **`start() -> str`.** POSIX: create a unique path
  `<tempdir>/doomed-prism-ipc-<pid>-<token>.sock`, `bind`, `listen(1)`, set
  non-blocking, return the path. Windows: `bind(("127.0.0.1", 0))`, `listen(1)`,
  non-blocking, return `"127.0.0.1:<port>"`. An `address_factory` seam lets tests
  force either branch and inject a loopback pair.
- **`poll()`.** `accept()` a pending client (only the first; a second is
  accepted and immediately closed). After a client is connected, a
  zero-length `recv` or `ConnectionResetError` means the child exited: set
  `is_connected = False` and call `on_disconnect()` once. The server never
  expects payload bytes from the child in M3 beyond the `HELLO`.
- **`send(message)`.** No-op when not connected. Otherwise `sendall(encode(...))`;
  a `BrokenPipeError` / `ConnectionResetError` is treated as a disconnect.
- **Handshake.** On accept, the server sends `Message.hello()` and waits (bounded,
  non-blocking with a deadline) for the child's `HELLO`. A version mismatch
  closes the socket and leaves `is_connected = False`; the host surfaces this as
  a startup failure the same way M2 surfaces `FrameSegmentError`.
- **`close()`.** Send `BYE` if connected, close the client and listening sockets,
  unlink the POSIX path. Idempotent. Never depends on the child — the M2 teardown
  lesson.

## 7. Gaze zones and the filter

`pewpew.input.gaze`, pure Python.

### `GazeZoneMap`

The writable surface is 640×640 (§5). Regions, all measured from the centre
`(320, 320)` and configurable via constructor arguments defaulting to the R11
constants:

- **Dead zone.** A centred rectangle `2*DEAD_ZONE_HALF_W` by `2*DEAD_ZONE_HALF_H`
  (default 220×180). Gaze inside → no actions.
- **Left / right turn bands.** Outside the dead zone in x. `resolve` returns
  `TURN_LEFT` or `TURN_RIGHT` with `magnitude = clamp((|dx| - DEAD_ZONE_HALF_W) /
  (320 - DEAD_ZONE_HALF_W), 0, 1)` shaped by `TURN_RESPONSE_EXPONENT` (default
  `1.5`, so the curve is gentle near the dead zone and steep at the edge —
  "turning speed increases as gaze moves farther", §6).
- **Upper / lower forward-reverse bands.** Outside the dead zone in y, inside it
  in x. `MOVE_FORWARD` (gaze above centre) or `MOVE_BACKWARD` (below), magnitude
  shaped the same way. Movement is effectively on/off in DOOM, but the magnitude
  is still carried for a future run/walk split.
- **Upper corners.** Outside the dead zone in both x and y, y above centre →
  `MOVE_FORWARD` **and** the corresponding `TURN_*`, each with its own magnitude
  (§6 "forward movement combined with turning"). Lower corners →
  `MOVE_BACKWARD` + turn.

`resolve` returns a `frozenset[HeldAction]`. Magnitudes are quantised to
`MAGNITUDE_STEPS` (default 20) so tiny gaze tremor does not stream frames.

### `GazeFilter`

`update(raw_set, now) -> frozenset[HeldAction]`:

- **Entry dwell.** A `HeldAction`'s *action* must be present in `raw_set`
  continuously for `DWELL_S` (default `0.15`, §6) before it is emitted. The dwell
  timer is per action, keyed on the action, not the magnitude.
- **Exit is immediate.** An action absent from `raw_set` is dropped from the
  output on the same tick and its dwell timer resets (§6 "leaving a region
  immediately releases its action").
- **Hysteresis.** Once an action is emitted, it survives a single tick of
  absence (`JITTER_GRACE_TICKS`, default `1`) to ride out a one-sample gaze
  dropout, but a second consecutive absent tick releases it. This is the
  "transitions are filtered to prevent jitter" of §6 and does not delay a real
  region exit noticeably at a 60 Hz tick.
- **Magnitude smoothing.** The emitted magnitude is an exponential moving
  average (`MAGNITUDE_EMA_ALPHA`, default `0.4`) of the raw magnitude while the
  action is held, so turn speed ramps instead of stepping.

## 8. Fire fusion

`pewpew.input.fire`, pure Python.

`FireArbiter(clock, *, debounce_s=FIRE_DEBOUNCE_S (0.12),
cooldown_s=FIRE_COOLDOWN_S (0.0))`:

- `deliberate_action()` and `spoken_fire()` each record "an edge happened" with
  the current `clock()`.
- `poll(now) -> bool` returns `True` at most once per `debounce_s`: if either
  edge is pending and `now - last_shot >= debounce_s`, it consumes **all**
  pending edges (so a blink and a "pew pew" 30 ms apart fire once), sets
  `last_shot = now`, and returns `True`. `cooldown_s` is an additional floor for
  a future auto-fire guard; `0.0` by default keeps DOOM's own fire rate
  authoritative.
- `reset()` clears pending edges and is called by `release_all()`.

`DeliberateActionSource` protocol: `activation_edge() -> bool` (consumed each
tick). `SpokenFireSource` protocol: `spoken_fire_edge() -> bool`.
`NullSpokenFireSource` returns `False` forever and is the 3a default.
`FakeSpokenFireSource` (test fakes) exposes `trigger()` and is bound to a debug
key in the 3a gate.

## 9. Input sources

`pewpew.input.source` / `pewpew.input.simulator_source`.

`InputSource` protocol: `sample(now) -> InputSample`. `InputSample` is a frozen
dataclass: `gaze_xy: tuple[int, int] | None`, `activation_edge: bool`,
`pause_edge: bool`. Edges are "did this happen since the last `sample()`" and are
cleared by the call.

`SimulatorInputSource(widget)` installs a Qt event filter on the host widget
(and enables mouse tracking):

- `MouseMove` → store the position in the widget's 640×640 coordinate space,
  clamped.
- `MouseButtonPress` (left) → set `activation_edge` (feeds
  `FireArbiter.deliberate_action()` and, in a menu, `MENU_CONFIRM` — see §11).
- `KeyPress` `Return` / `Enter` → set `pause_edge` (§6 "Enter represents the
  physical ClickButton"; ClickButton opens pause / emergency controls).
- `Leave` → `gaze_xy` becomes `None` until the pointer returns, so
  `release_all`-on-leave is automatic.

`PrismInputSource` raises `NotImplementedError("Prism gaze/blink input arrives
with the hardware phase")`.

## 10. The Crispy Doom IPC-input patch

`patches/crispy-doom-ipc-input.diff`, GPL-2.0-or-later, targeting the same
`crispy-doom-7.1` tag as the M2 patch.

**New `src/i_ipc_input.c` / `.h`:**

- `void IPC_Input_Init(void)` — read `DOOMED_PRISM_IPC_ADDR`; unset or empty →
  `ipc_enabled = 0`, return (upstream-identical build). POSIX: `socket(AF_UNIX,
  SOCK_STREAM, 0)`, `connect` to the path, `fcntl` `O_NONBLOCK`. Windows:
  `WSAStartup`, `socket(AF_INET, SOCK_STREAM, 0)`, `connect` to
  `127.0.0.1:<port>`, non-blocking. Send `HELLO(version)`, read the server's
  `HELLO` (bounded spin), close and disable on a version mismatch.
- `void IPC_Input_Pump(void)` — if disabled, return. Non-blocking `recv` into an
  8-byte staging buffer; for each complete frame, translate and `D_PostEvent`:
  - `ACTION` `MOVE_FORWARD` / `MOVE_BACKWARD`: `ev_keydown` / `ev_keyup` of
    `key_up` / `key_down` (Crispy's configured bindings), tracked in a
    `held[]` bitset.
  - `TURN` `TURN_LEFT` / `TURN_RIGHT`: `D_PostEvent(&(event_t){ev_mouse, 0,
    -delta or +delta, 0})` — DOOM's analog turn axis. `value` is the per-tic x
    delta the Python side already scaled (R5).
  - `PULSE` `FIRE` / `USE`: a paired `ev_keydown` then `ev_keyup` of `key_fire`
    / `key_use` on the same pump.
  - `DISCRETE` `PAUSE` → `ev_keydown`/`up` of the pause key; `MENU_CONFIRM` →
    `KEY_ENTER`; `MENU_CANCEL` → `KEY_ESCAPE`.
  - `BYE` → run the release-all below, keep the socket, stay enabled == 0.
  - `recv` returns `0` (EOF) or errors non-`EWOULDBLOCK` → **release-all**: for
    every bit set in `held[]`, post the matching `ev_keyup`; post `ev_keyup` for
    fire/use defensively; `ipc_enabled = 0`; close the socket. DOOM keeps running
    on SDL input.
- `void IPC_Input_Shutdown(void)` — release-all, close the socket, POSIX
  `unlink` is the server's job, not the client's. `WSACleanup` on Windows.
  Idempotent (guarded by `ipc_enabled` plus a `socket >= 0` check).

**Call sites (`src/i_video.c`, `src/d_loop.c` or `src/d_main.c`):**

- `IPC_Input_Init();` immediately after `FB_Export_Init();` in `I_InitGraphics`.
- `IPC_Input_Pump();` once per tic, before the game builds its tic command.
  Primary hook: `TryRunTics()` in `src/d_loop.c`, immediately before the
  `I_StartTic()` / `D_ProcessEvents()` sequence, so injected events sit in the
  same queue SDL events do and are consumed by the same `G_BuildTiccmd`. Fallback
  hook if that call is not reachable at the tag: `D_ProcessEvents()` in
  `src/d_main.c`. The chosen function is confirmed against `crispy-doom-7.1`
  during implementation and recorded in the patch header comment — the M2 patch
  did the same for its own hook point (M2 spec §0).
- `IPC_Input_Shutdown();` immediately before `FB_Export_Shutdown();` in
  `I_ShutdownGraphics`.
- POSIX SIGINT/SIGTERM: extend the M2 patch's `fb_signal_handler` idea with an
  `IPC_Input_Shutdown()` call, or install a parallel handler. The two patches
  touching signal setup is a known small overlap; the implementation keeps them
  independent and idempotent, and the patch header comment says so.

**`src/CMakeLists.txt`:** add `i_ipc_input.c i_ipc_input.h` to the source list;
`if(WIN32) list(APPEND EXTRA_LIBS ws2_32)`.

**Constants** shared byte-for-byte with `pewpew.ipc.protocol`: `IPC_FRAME_SIZE
8`, `IPC_PROTOCOL_VERSION 1`, and the `MessageType` / action-`code` values.

## 11. Getting from the attract loop to a live game

The 3a gate has to reach first-person gameplay without touching the SDL
keyboard. `InputPipeline` therefore has two explicit host-side modes, and the
mode is host state — it never depends on Crispy Doom's internal game state,
which the host cannot observe:

- **`MENU` mode** is the default at startup. `activation_edge` sends
  `DISCRETE MENU_CONFIRM`; `pause_edge` sends `MENU_CANCEL`; a dwelt upper /
  lower gaze band sends a single `MENU_UP` / `MENU_DOWN` step (edge, not held —
  one step per dwell, re-armed on return to the dead zone); turn bands do
  nothing. The C patch maps these to `ev_keydown`/`up` of `KEY_ENTER`,
  `KEY_ESCAPE`, `KEY_UPARROW`, `KEY_DOWNARROW`.
- **`PLAY` mode** is the §6 gaze model: held movement, analog turn, click and
  spoken fire, Enter → `PAUSE`.
- The switch is a dedicated debug key (`F9`, handled by `SimulatorInputSource`)
  that toggles `MENU` ⇄ `PLAY`. `release_all()` runs on every switch. The tester
  clicks through the start menu in `MENU` mode, presses `F9`, and plays the
  gate in `PLAY` mode with the SDL window unfocused.

`MENU` mode and the `F9` toggle are a gate scaffold, not part of the §6 gaze
model. 3b's voice grammar replaces the menu clicks with `open` / weapon / `map`
commands and the toggle becomes unnecessary. `MENU_UP` / `MENU_DOWN` /
`MENU_CONFIRM` / `MENU_CANCEL` are the 3a discrete codes this needs; they are
never emitted in `PLAY` mode.

## 12. Error handling and lifecycle

- **Child not connected yet.** `server.is_connected` is `False`; `send` is a
  no-op; the host keeps ticking. The existing M2 10 s "engine did not export
  frames" deadline already covers a child that never starts. A child that
  exports frames but never completes the IPC `HELLO` within
  `IPC_HANDSHAKE_TIMEOUT_S` (default `10.0`) raises
  `RuntimeError("engine did not connect input")` and runs cleanup — parallel to
  the framebuffer deadline.
- **Version mismatch.** `IpcProtocolError` on either side closes the socket. The
  host treats it like `FrameSegmentError`: cleanup then raise
  `RuntimeError("input protocol mismatch")`.
- **Supervisor dies (Python side gone).** The child's `recv` returns `0`; the C
  release-all posts key-ups for everything held; DOOM continues on SDL input,
  then exits when its window is closed (M2 lifecycle, unchanged).
- **Child dies (`engine.poll()` not `None`).** `_on_tick` already stops the
  timer on this in M2. M3 also calls `pipeline.release_all()` (harmless — the
  socket is gone) and `server.close()`.
- **Raven sleep / conceal (`hideEvent`).** `pipeline.release_all()` then
  `router.discrete(PAUSE)`. `showEvent` after start re-arms the timer; held
  state was cleared, so gaze re-acquires from zero.
- **IPC send backpressure.** M3's frame rate is one tick's worth of small frames
  at ~60 Hz — a few hundred bytes per second. `sendall` on a loopback / `AF_UNIX`
  socket does not block at that rate. If a `send` ever raises `BlockingIOError`,
  it is treated as a transient drop (the held-state diff re-sends next tick).
- **Pause overlay.** `_PauseOverlay` is a host-side *indicator*, not the source
  of truth: a translucent child of the host drawn above the viewport, shown
  while the host believes it has sent an odd number of `PAUSE` presses. Crispy
  Doom's own pause state stays authoritative; the indicator can drift if DOOM
  pauses by another route, which is acceptable for 3a. It is emitted content,
  not a black panel (§5) — minimal: the word `PAUSED` in an emitted-light
  colour. It exists because §6 requires host-side pause/emergency feedback that
  a voice failure cannot take away, and voice is 3b.

## 13. Build and CI

- `scripts/build_crispy.py` gains
  `PATCHES = ("patches/crispy-doom-fb-export.diff",
  "patches/crispy-doom-ipc-input.diff")`. `plan_commands` emits one
  `git -C <dir> apply <patch>` per entry (and `git -C <dir> apply --check
  <patch>` per entry under `--check`). The `.doomed-prism-applied` marker is
  written only after every patch applies; `--check` returns non-zero if any
  patch fails. Tests updated for the list.
- `crispy-doom.lock` unchanged.
- `.github/workflows/ci.yml`: `build_crispy.py --check` now covers both patches
  with no workflow change. The `linux-build-and-posix-smoke` job gains a step
  after the framebuffer smoke:

  ```
  xvfb-run -a python scripts/ci_ipc_smoke.py "$EXE" /usr/share/games/doom/freedoom1.wad
  ```

  `ci_ipc_smoke.py`: bind an `IpcServer`, launch the engine with both
  `DOOMED_PRISM_FB_NAME` and `DOOMED_PRISM_IPC_ADDR`, `poll()` until connected,
  complete the handshake, send `HELLO` + a scripted sequence (a `MENU_CONFIRM`
  burst to leave the attract loop, then a `TURN_RIGHT` stream for 2 s), assert
  the framebuffer `frame_counter` keeps advancing throughout (engine alive and
  responsive), then `server.close()` and assert: engine exits on its own within
  a bounded wait *or* on `SIGINT`, no orphan `crispy-doom`, and the POSIX socket
  path is gone. A separate `$GITHUB_STEP_SUMMARY` block reports "IPC runtime
  validation" beside M2's "POSIX runtime validation". ARM64 stays annotated
  outstanding.
- The frame-level proof that a `TURN` message actually turned the player stays
  in the Windows + Raven manual gate. If driving past the attract loop is flaky
  in CI, `ci_ipc_smoke.py` is reduced to connect + handshake + a message flood +
  clean teardown, which is still the portable proof M2 established (R10 cost).

## 14. Publication safety and licensing

- New tracked files are original and GPL-2.0-or-later, matching the project:
  `patches/crispy-doom-ipc-input.diff`, the `pewpew.ipc` and `pewpew.input`
  modules and tests, `scripts/ci_ipc_smoke.py`, and the Milestone 3 documents.
- `scripts/check_publication_safety.py` is unchanged and still sufficient: the
  new patch is text, no binary, IWAD, Raven source, or credential enters git, and
  the socket paths are runtime-only temp paths, never tracked.
- The IPC address is a local socket path or `127.0.0.1:<port>`; it is not a
  secret and is passed by environment variable, never written to a tracked file
  (same discipline as `DOOMED_PRISM_FB_NAME`).
- **3b only:** the offline speech library and any acoustic model must pass the
  §9 licence review and be recorded before anything is committed or packaged.
  3b's plan starts with that review as its first task and does not proceed on a
  fail. Models and calibration audio are never committed — they are a
  user-supplied or separately-fetched runtime asset, like the IWAD.

## 15. Testing

All tests run without Crispy Doom, Raven Framework, an IWAD, a C toolchain, a
real socket peer, or a display, using project-owned fakes, on the same pytest as
M2.

- **`pewpew.ipc.protocol`.** `encode`/`decode` round-trip for every
  `MessageType`; `decode` on a partial buffer returns `(None, buffer)`; two
  frames in one buffer decode in sequence; a bad `version` and an unknown `type`
  raise `IpcProtocolError`; every frame is exactly 8 bytes; little-endian byte
  order is asserted against a hand-packed literal.
- **`pewpew.ipc.server`.** With an injected loopback `socketpair`
  `address_factory`: `start()` returns the address shape for the platform;
  `poll()` accepts one client and rejects a second; `send` before a client is a
  no-op; a client close makes `poll()` fire `on_disconnect` exactly once and
  flip `is_connected`; the `HELLO` handshake succeeds on a match and closes on a
  mismatch; `close()` unlinks the POSIX path and is idempotent. `tests/fakes/
  fake_ipc.py` provides `FakeIpcClient` (the child side) for these.
- **`pewpew.input.actions`.** `set_held` emits `ACTION`/`TURN` only for changed
  entries; a magnitude change below the quantum emits nothing; `pulse` and
  `discrete` emit one frame; `release_all` emits a zero-`value` frame for every
  held action and nothing for actions already released; the sink receives
  `Message` objects, asserted by field.
- **`pewpew.input.gaze`.** `GazeZoneMap.resolve` for dead-zone centre (empty),
  each band (correct action + monotonic magnitude as the point moves outward),
  and each corner (two actions). `GazeFilter` with a fake clock: an action needs
  `DWELL_S` of continuous presence before it appears; one absent tick is ridden
  out, two release it; exit is immediate on a full region change; magnitude EMA
  ramps.
- **`pewpew.input.fire`.** A single edge fires once; two edges inside
  `debounce_s` fire once; edges `debounce_s` apart fire twice; `deliberate` and
  `spoken` edges fuse; `reset()` drops pending edges. `NullSpokenFireSource`
  never fires; `FakeSpokenFireSource.trigger()` does.
- **`pewpew.input.pipeline`.** With a `FakeInputSource` and a `FakeIpcServer`
  recording sent `Message`s: a scripted gaze track produces the expected frame
  sequence; an `activation_edge` produces a `FIRE` pulse; a `pause_edge`
  produces `PAUSE` and toggles an overlay flag; `release_all()` emits the full
  set of zero-`value` frames; a disconnect mid-track stops sends without raising.
- **`pewpew.input.simulator_source`** with `pytest-qt`: synthesised
  `QMouseEvent` / `QKeyEvent` on the host produce the right `InputSample`;
  `Leave` clears `gaze_xy`; edges are one-shot.
- **`pewpew.engine`.** `start(ipc_address=…)` puts `DOOMED_PRISM_IPC_ADDR` in
  the child env (a fake `popen_factory` captures `env=`); `ipc_address` property;
  `stop()` unlinks a POSIX socket path best-effort. The existing
  `DOOMED_PRISM_FB_NAME` tests still pass.
- **`pewpew.host_widget`** with `pytest-qt` and injected fakes: `showEvent`
  starts the server before the engine and passes the address; `_on_tick` calls
  `server.poll()` and `pipeline.tick()`; `hideEvent` triggers `release_all()` +
  `PAUSE`; a disconnect callback triggers `release_all()`; `cleanup()` runs
  stop-input → release-all → server-close → reader-close → engine-stop in that
  order (recorded on fakes) and is idempotent; the handshake-timeout path raises
  `RuntimeError("engine did not connect input")` after cleanup.
- **`scripts/build_crispy.py`.** `plan_commands` emits an apply (or
  `apply --check`) per entry in `PATCHES`, in order; the marker is written only
  after all applies; `--check` short-circuits on the first failing patch. The
  existing single-patch tests are updated to the list.
- **`tests/test_distribution_metadata.py`.** Expectations updated for the new
  modules, the new patch, and `scripts/ci_ipc_smoke.py`.
- **`tests/test_validation_docs*.py`.** A new module asserts the M3 checklist
  and result carry the four decision strings, the "IPC-only, SDL window
  unfocused" phrasing, the release-all lifecycle checks, and both
  publication-safety scan invocations — mirroring `test_validation_docs.py`.
- **`scripts/ci_ipc_smoke.py`** is exercised only in CI (Linux, real build);
  it is not a pytest module. It prints `IPC runtime smoke: PASS/FAIL` and exits
  accordingly, like `ci_posix_smoke.py`, and skips with exit 0 on non-POSIX.

## 16. Delivery sequence

### Plan 3a — `docs/superpowers/plans/2026-09-05-doomed-prism-milestone-3a.md`

1. `pewpew.ipc.protocol` — frame encode/decode, `Message`, `MessageType`,
   `IpcProtocolError`; `tests/test_ipc_protocol.py`.
2. `pewpew.ipc.server` — dual-transport `IpcServer`, handshake, disconnect;
   `tests/fakes/fake_ipc.py`, `tests/test_ipc_server.py`.
3. `patches/crispy-doom-ipc-input.diff` — `i_ipc_input.c` / `.h`, call sites,
   `CMakeLists.txt`; verified by a manual local build against the pinned tag.
4. `scripts/build_crispy.py` — `PATCHES` list, per-patch apply / `--check`,
   marker semantics; `tests/test_build_crispy.py` updates.
5. `pewpew.input.actions` — `Action`, `HeldAction`, `ActionRouter`;
   `tests/test_input_actions.py`.
6. `pewpew.input.gaze` — `GazeZoneMap`, `GazeFilter`;
   `tests/test_input_gaze.py`.
7. `pewpew.input.fire` — `FireArbiter`, source protocols, `NullSpokenFireSource`;
   `tests/test_input_fire.py`.
8. `pewpew.input.source` + `pewpew.input.simulator_source` — `InputSource`,
   `InputSample`, `SimulatorInputSource`, `PrismInputSource` stub;
   `tests/test_input_source.py` (+ a `pytest-qt` module).
9. `pewpew.input.pipeline` — `InputPipeline.tick` / `release_all`;
   `tests/test_input_pipeline.py`, `tests/fakes/fake_input.py`.
10. `pewpew.engine` — `start(ipc_address=…)`, `ipc_address`, `stop()` unlink;
    `tests/test_engine.py` updates.
11. `pewpew.host_widget` — server lifecycle, input tick, release-all wiring,
    `_PauseOverlay`, `cleanup()` ordering; `tests/test_host_widget*.py` updates.
12. `.gitignore` / metadata / `tests/test_distribution_metadata.py`; full
    `pytest -q` and both `check_publication_safety.py` scans green.
13. `scripts/ci_ipc_smoke.py` and the `ci.yml` step; new
    `tests/test_validation_docs_m3.py`.
14. `docs/validation/milestone-3-checklist.md`; run the 3a decision gate;
    record `docs/validation/milestone-3-result.md`.

### Plan 3b — `docs/superpowers/plans/2026-09-05-doomed-prism-milestone-3b.md`

Written only after 3a's gate records PASS.

1. §9 offline-speech-library licence review; record the result; stop on a fail.
2. Desktop audio-capture adapter behind an `AudioSource` protocol; fake.
3. Real "pew pew" keyword detector implementing 3a's `SpokenFireSource`;
   calibration-sample handling (never committed).
4. Closed English command grammar + router → the R6 "later" discrete actions;
   confirmation flow for `save`/`load`/`exit`.
5. C patch: the extra discrete `code`s wired to their DOOM keys (append to
   `crispy-doom-ipc-input.diff`).
6. `host_widget` / `pipeline` wiring for the voice source; a crashed voice
   worker disables voice and preserves click/blink and Enter (§8).
7. `docs/validation/milestone-3b-checklist.md`; run the 3b gate; record the
   result.

## 17. Milestone 3a decision gate

Run manually on Windows against a separately installed Raven Framework. Keep all
evidence under gitignored `artifacts/milestone-3/`. Record no Raven source,
credentials, private paths, or commercial IWAD identity — the M2 gate's rules
apply verbatim.

**The hard question.** Does IPC-only normalized input drive real DOOM gameplay
inside the Qt viewport — gaze steering, progressive turn, debounced click-fire,
fused spoken-fire (fake source on a debug key), Enter-pause — with Crispy's SDL
window unfocused the entire time, and does every lifecycle transition release all
held inputs with no stuck key and no orphan?

**Environment and launch.** `python scripts/build_crispy.py` builds the
doubly-patched engine; `--check` passes for both patches; record the pinned tag
and commit, compiler, and SDL2 versions. `doomed-prism validate` exits 0.
`python -m pytest -q` green; `check_publication_safety.py --root .` exit 0.
Establish the M2 before/after crispy-doom PID baseline. Launch
`doomed-prism run-desktop`.

**Objective checks.**

- Exactly one new crispy-doom PID.
- The IPC socket exists while running (POSIX: the path; Windows: a listening
  `127.0.0.1` port owned by the PewPew process) and is gone after close.
- A `FrameReader` probe still shows `frame_counter` advancing (M2 path
  unbroken).
- With **Crispy's SDL window minimised or behind the Raven Simulator** for the
  whole run:
  - Gaze into the left turn band turns the DOOM view left; right band, right;
    returning to the dead zone stops the turn within ~2 ticks.
  - Gaze farther from the dead zone turns visibly faster than gaze just outside
    it (progressive turn, §6).
  - Gaze into the upper band walks forward; lower band, backward; upper corner
    walks forward while turning.
  - A click fires one shot; five fast clicks fire fewer than five shots
    (debounce).
  - The debug-key `FakeSpokenFireSource.trigger()` fires a shot through the same
    path; a click and a trigger within ~30 ms fire once (fusion).
  - `Enter` shows the `PAUSED` overlay and pauses the game; `Enter` again
    resumes. No SDL-window focus was used.
  - Reaching a live first-person game was done with clicks via menu mode (§11),
    not the keyboard.
- No `SetParent` anywhere (M2 regression check, still valid).

**Lifecycle checks.**

- Trigger Raven sleep/conceal (or hide the host): the game pauses and, on
  resume, no key is stuck — a held turn from before the hide does not persist.
- Kill the PewPew process while a turn is held: DOOM stops turning (C-side
  release-all on EOF) and remains running on SDL input; no orphan after its
  window is closed.
- Normal close: `cleanup()` runs stop-input → release-all → server-close →
  reader-close → engine-stop with no exception; one PID gone; socket path
  removed.

**Per-mode evidence.** Raw plus each available optical mode (Night, Day,
Outdoors, Camera): one short local video or two time-separated captures showing
gaze-driven view motion and a fired shot inside the composited viewport, with
the SDL window not focused. Night carries the full dynamic proof; the others may
be lighter, as in the M2 gate.

**Hard decision, recorded in the single final field of
`docs/validation/milestone-3-result.md`.**

- **PASS — IPC input path viable.** Gaze movement and progressive turn,
  click-fire with debounce, spoken-fire fusion via the fake source, and
  Enter-pause all drive the composited DOOM with the SDL window unfocused;
  every lifecycle transition releases held input with no stuck key; one clean
  PID, no orphan, socket removed, no `cleanup()` exception; the M2 framebuffer
  path still advances.
- **FAIL — IPC input path insufficient.** The engine connects and the handshake
  completes, but injected events do not reliably drive gameplay (for example
  `ev_mouse` turning is unusable, or `D_PostEvent` from the pump races the tic
  and drops inputs). This opens a design task for the R5 keyboard-duty-cycle
  turn or a different injection point — it does not discard the IPC boundary.
- **BLOCKED/RETRY — implementation or environment failure.** Build, launch,
  connection, handshake, geometry, lifecycle, or evidence collection fails. Fix
  the named issue and repeat with a fresh PID. Does not select an injection
  design.
- **PENDING — incomplete evidence.** Evidence incomplete or a named optical mode
  unavailable without a documented reason. Never a pass.

**Final automated verification and commit.** As in M2: `python -m pytest -q`,
`git diff --check`, an exact-path `git add` of only
`docs/validation/milestone-3-checklist.md` and
`docs/validation/milestone-3-result.md`, `check_publication_safety.py --root .`
and `--history`, then `git commit -m "docs: record IPC input path result"`.

## 18. Exit criteria

Milestone 3a is complete when all automated tests pass, both publication-safety
scans are clean, CI is green including the IPC runtime smoke test, and
`milestone-3-result.md` records a reproducible PASS or FAIL. A FAIL is a valid
engineering result: it keeps the §4 IPC boundary and reopens only the
event-injection method.

Milestone 3b is complete when the §9 licence review is recorded as a pass, the
offline grammar and the real spoken-fire detector work end-to-end with fakes in
CI and on the Windows gate, and `milestone-3b-result.md` records a reproducible
PASS or FAIL.
