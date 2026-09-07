# DOOMed Prism — Milestone 3 Design: Input and the IPC Boundary

Date: 2026-09-05 (amended 2026-09-07 — R14, radial analog stick)
Status: Plan 3a implemented on `feature/doomed-prism-m3` and CI-green; the
Milestone 3a manual decision gate was run and surfaced three input-feel
findings (backward unreachable, forward "cut" when turning, forward speed
unbalanced against the ramped turn). **Ruling R14 (2026-09-07)** replaces the
discrete-zone gaze model with a radial analog stick, which dissolves all three;
it supersedes the forward-axis half of R5 and the movement half of R6, and
rewrites §7. R14 was brainstormed with and approved by the user section by
section, and is being audited by separate auditor agents before the affected 3a
tasks are re-planned and re-implemented. The original three auditor passes
(architecture/feasibility, spec-consistency, publication-safety) stand for
everything R14 does not touch.
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
  Crispy Doom IPC-input patch, the normalized-action model, radial analog-stick
  gaze movement (R14 — proportional turn and forward from one vector), fire
  fusion (deliberate action + spoken fire), the simulator input source,
  lifecycle wiring, CI, and the 3a decision gate.
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
patch-1 additions (e.g. `FB_Export_Init();` in `i_video.c`). Patch 2 only ever
*adds* lines within regions patch 1 introduced or leaves untouched; neither diff
emits a change to a line the other also changes.

`scripts/build_crispy.py` holds an ordered `PATCHES` tuple and applies the
series **cumulatively, one file at a time, on disk**, restoring the checkout to
the pristine pinned state first. A single `git apply <p1> <p2>` is not used:
under `--check` nothing is written, so patch 2 (whose context legitimately
includes patch-1 additions) would be validated against the un-patched tree and
fail; and a real multi-file `git apply` is not atomic across files, so a
failing patch 2 would leave patch 1 half-applied.

- **Build / apply (marker absent):**
  `git -C <dir> reset --hard <lock.commit>` and `git -C <dir> clean -fd -- src/`
  (reverts patch-1's tracked edits, removes both patches' new untracked
  `src/i_*_export.*` / `src/i_ipc_input.*` and any partial prior apply, and
  leaves the `<dir>/build/` CMake tree intact), then `git -C <dir> apply <p1>`,
  then `git -C <dir> apply <p2>`, then write the `.doomed-prism-applied` marker
  **once**. A failure at any step leaves no marker; the next run's restore
  returns the checkout to pristine and the whole series is re-attempted.
- **`--check`:** same restore, then `git -C <dir> apply <p1>` (real, on the
  disposable checkout), then `git -C <dir> apply --check <p2>`. This is the
  honest "does the series still apply" test — patch 2 is checked against the
  tree it was authored against. No marker is written. (A local `--check`
  therefore leaves the checkout at "patch 1 applied, no marker"; the next real
  build restores and re-applies both, so `--check` never corrupts a later
  build.) In CI the checkout is a fresh clone.

SDL keyboard input in Crispy is **left untouched** — IPC is an *additional*
event source.

**Rationale.** Two focused diffs stay independently reviewable GPL
corresponding-source artifacts. Restoring to the pinned commit before every
apply makes the series idempotent and self-healing after a partial failure, and
running patch 1 for real before `--check`ing patch 2 is the only accurate
patch-rot signal for a dependent series.

**Cost if wrong.** If the series ever fails to compose, concatenate the two into
one `crispy-doom-prism.diff` and drop the tuple — a modest `build_crispy.py`
change the tests already cover.

### R5 — Discrete actions are injected as key events; analog turning is injected as synthetic mouse-x motion

**(R14, 2026-09-07) supersedes the forward/back half:** movement is now an
analog `forwardmove` contribution derived from the gaze vector (§10, R14), not
`key_up` / `key_down` key events. The discrete-action and synthetic-`ev_mouse`
turn halves below stand.

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
| Held analog | `MOVE_FORWARD`, `MOVE_BACKWARD` | **(R14)** `ACTION` frame each tic, `value` = proportional magnitude `[0, 10000]` from the gaze vector, `0` on release | — |
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

`FireArbiter` consumes a *deliberate-action* edge (double-blink on hardware,
click in the simulator — §6) and a *spoken-fire* edge (spoken "pew pew" — §6).
In 3a the deliberate-action edge is the simulator click, and the spoken-fire
edge is stubbed: the pipeline's `spoken_fire` source is a `NullSpokenFireSource`
that never fires, and the 3a gate drives the fusion path without real audio via
an env-gated `F9` key on `SimulatorInputSource` that sets
`InputSample.debug_fire_edge`, which `InputPipeline.tick` routes into
`FireArbiter.spoken_fire()`. `tests/fakes` carries a `FakeSpokenFireSource` with
a `trigger()` method for the fusion unit tests. 3b supplies the real acoustic
`SpokenFireSource` as the pipeline's `spoken_fire`. Both edges feed one `FIRE`
pulse through shared debounce so a blink and a "pew pew" inside the debounce
window produce exactly one shot (§6).

**Cost if wrong.** None structural — the interface is designed for both sources
from the start.

### R8 — The Raven-facing input source sits behind an `InputSource` protocol; only `SimulatorInputSource` is implemented

`SimulatorInputSource` reads gaze position (mouse), focused-element activation
(click → `activation_edge`), the physical button (Enter → `pause_edge`), and —
only when `DOOMED_PRISM_DEBUG_FIRE` is set — an `F9` debug key
(→ `debug_fire_edge`) that stands in for a spoken "pew pew", all from Qt events
on the host widget, never from Raven APIs directly (§6: "The game bridge does
not depend directly on Raven APIs"). `PrismInputSource` is a documented stub
raising `NotImplementedError`. Real gaze coordinates, a raw double-blink event,
and sensor entitlements are §12 hardware-phase items.

**Cost if wrong.** The protocol may need one more method for real gaze/blink
entitlements — a change §12 already anticipates.

### R9 — One `release_all()` covers sleep/conceal, IPC loss, and shutdown, on both sides

Python side: `InputPipeline.release_all()` calls `GazeVectorFilter.reset()`
(R14), tells `ActionRouter` to emit a `0`-value message for every currently
held axis, and resets `FireArbiter`. `cleanup()` ordering:
stop the input tick → `pipeline.release_all()` → `IpcServer.close()` →
`reader.close()` → `engine.stop()`.

C side: on socket EOF the patch **(R14)** zeroes the injected `forwardmove`
contribution `ipc_forwardmove` (and, in the keyboard-duty-cycle fallback, posts
`ev_keyup` for any movement key still held), posts a defensive `ev_keyup` for
fire/use, disables itself, and closes the socket, so a dead supervisor never
leaves DOOM moving (§4, §8). Turn needs nothing — with no fresh `ev_mouse`,
`mousex` falls to 0 at the next `G_BuildTiccmd`. DOOM keeps running on SDL
input. (A *frozen* supervisor sends no EOF; the `IPC_MOVE_STALE_PUMPS` watchdog
in §10 zeroes `ipc_forwardmove` after ~0.1 s so forward degrades like turn.)

**Cost if wrong.** Ordering tweaks. The invariant — "no held input survives a
lifecycle transition" — is what the gate checks; R14 changes the C mechanism
(zero a value, not release a key) but not the invariant.

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

Exhaustive list. §6 calls the shaping "configurable"; a user-facing config
surface is deferred until the manual gate shows tuning is needed, at which point
each constant becomes a `RuntimeConfig` field with the same name.
`GazeStick` / `GazeVectorFilter` / `FireArbiter` already accept these as
constructor arguments, so the seam exists.

R14 (2026-09-07) rewrote the `pewpew.input.gaze` rows: the rectangular
`DEAD_ZONE_HALF_W` / `DEAD_ZONE_HALF_H`, `DWELL_S`, and `JITTER_GRACE_S` are
gone; `TURN_RESPONSE_EXPONENT` became the axis-shared `RESPONSE_EXPONENT`;
`DEAD_ZONE_RADIUS`, `OUTER_SATURATION`, `EMA_ZERO_EPSILON` and
`RELEASE_EMA_ALPHA` are new; `IPC_MOVE_STALE_PUMPS` is a new C-side constant.
`MAGNITUDE_EMA_ALPHA` now weights the whole output vector, not just turn.

| Constant | Module | Default | Unit | Meaning |
| --- | --- | --- | --- | --- |
| `DEAD_ZONE_RADIUS` | `pewpew.input.gaze` | `0.28` | fraction of normalized space | radius of the central no-action circle; `r` at or below this emits nothing (R14) |
| `OUTER_SATURATION` | `pewpew.input.gaze` | `0.95` | fraction of normalized space | `r` at or above this maps to full deflection; the live band is `[DEAD_ZONE_RADIUS, OUTER_SATURATION]` (R14) |
| `RESPONSE_EXPONENT` | `pewpew.input.gaze` | `1.5` | — | shaping exponent applied to the rescaled magnitude; one curve for both axes (R14; was `TURN_RESPONSE_EXPONENT`) |
| `MAGNITUDE_EMA_ALPHA` | `pewpew.input.gaze` | `0.4` | — | EMA weight for the gaze output vector `(fx, fy)` each tick while the raw vector is non-zero (R14) |
| `RELEASE_EMA_ALPHA` | `pewpew.input.gaze` | `0.8` | — | EMA weight used instead while the raw vector is `(0, 0)`, so a look-back-to-centre reaches the first quantum in ~3 ticks and snaps to zero in ~5, versus ~9 / ~14 at `MAGNITUDE_EMA_ALPHA` (R14) |
| `EMA_ZERO_EPSILON` | `pewpew.input.gaze` | `1e-3` | vector magnitude | below this the smoothed vector is snapped to `(0, 0)` so a rested stick stops emitting (R14) |
| `MAGNITUDE_STEPS` | `pewpew.input.actions` | `20` | — | quantisation of a smoothed magnitude before it is sent, for both axes (quantum `1/MAGNITUDE_STEPS`) |
| `MOVE_MAGNITUDE_SCALE` | `pewpew.input.actions` | `10000` | wire units | magnitude `1.0` maps to this `ACTION.value` (R14) |
| `TURN_MAX_MOUSE_DELTA` | `pewpew.input.actions` | `40` | mouse units | magnitude `1.0` maps to this signed per-tic x delta (gate-tunable) |
| `FIRE_DEBOUNCE_S` | `pewpew.input.fire` | `0.12` | s | minimum interval between fused shots |
| `PULSE_HOLD_TICS` | C `i_ipc_input.c` | `2` | game tics | how long a `PULSE` holds its key down before the paired keyup |
| `IPC_TURN_CLAMP` | C `i_ipc_input.c` | `40` | mouse units | C-side clamp on an injected turn x value |
| `MOVE_MAX_FORWARDMOVE` | C `i_ipc_input.c` | `50` | DOOM `forwardmove` units | `ACTION.value` `10000` maps to this signed `forwardmove` contribution (R14; `50` is DOOM's run value `forwardmove[1]` = `MAXPLMOVE`) |
| `IPC_MOVE_STALE_PUMPS` | C `i_ipc_input.c` | `6` | pump calls | zero `ipc_forwardmove` after this many pumps with no `ACTION` frame — forward degrades on a frozen (not dead) supervisor, as turn already does (R14) |
| `IPC_MOVE_WIRE_MAX` | C `i_ipc_input.c` | `10000` | wire units | the `ACTION.value` full-scale; `#define`d equal to `pewpew.input.actions.MOVE_MAGNITUDE_SCALE`, asserted by `test_c_patch_constants_match_the_python_enums` (R14) |

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

### R14 — Gaze is a radial analog stick, not discrete zones (amendment, 2026-09-07)

Supersedes: the forward-axis half of R5 and the movement half of R6; rewrites
§7; edits §1/R1 (deliverable summary), §2 (patch-2 summary), §3 (approach-A
row), §4 (units + data-flow steps 4–6 + step 9 + the ASCII diagram), §5
(`ACTION.value` semantics + Functions), §6 (the socket byte-rate note — a
consequence of the per-tick streams, no interface change), §9 (the simulator
gaze coordinate space + a public `widget` accessor), §10 (the C `MOVE_*`
translation + pump coalescing + the `forwardmove` fold), §12 and R9 (the C
release-all wording), §13 (the CI-smoke assertion set), §14 and §17 (the
patch-2 file allow-list and gate geometry), §18 (exit criteria), and the R11
tunable list. Unchanged: the IPC boundary, the wire framing (R10), the
transport (R2), the `IpcServer` role and API (R3, §6 — only its byte-rate note
moves), fire fusion (R7, §8), the `InputSource` *protocol* (R8 — the simulator
source gains a `widget` accessor and its coordinate-space comment is
corrected), the `release_all` *invariant* (R9 — "no held input survives a
lifecycle transition"; only its stated C mechanism changes), and the
`TURN → ev_mouse` translation itself (the pump now coalesces `TURN` frames but
each still becomes one signed `ev_mouse` x-delta — the analog half of R5).

**Why.** The 3a gate showed the discrete-zone model does not "feel as natural as
looking around" (the user's acceptance bar). Three findings, one root cause
each, all dissolved by going radial:

1. *Backward unreachable.* `SimulatorInputSource` clamps gaze to the viewport
   (640×480) but `InputPipeline` built `GazeZoneMap` in the 640×640 default
   surface, so the backward band (`dy > 150` from centre `y = 320`) sat below
   the reachable `y ≤ 479` — a ~9 px strip. R14 builds the stick from the
   **actual viewport size**, and a radial model on that surface is symmetric.
2. *Forward "cut" when glancing sideways.* `GazeFilter` released a held action
   the instant the raw set changed region, then charged the re-entering action
   a fresh `DWELL_S`. Continuous aiming stuttered. R14 has **no regions to
   transition between** — the dwell/grace/region-change machinery is deleted.
3. *Forward too fast / unbalanced against the ramped turn.* Forward was digital
   (`value = 10000` on/off) while turn ramped `0–40`. R14 drives **both axes
   from one curved vector**, so forward is as proportional as turn.

**The model** (`pewpew.input.gaze`, pure, time via `now`):

- **Normalized space.** Centre `(cx, cy) = (w // 2, h // 2)` of the surface the
  stick is constructed with. `InputPipeline` constructs `GazeStick` with the
  host viewport's real `(width, height)` (`host_widget` passes
  `surface=(self.viewport.width(), self.viewport.height())` explicitly — the
  640×640-vs-viewport mismatch is finding 1's root cause). `SimulatorInputSource`
  reports `gaze_xy` in **viewport-local pixels**, clamped to `[0, w-1] × [0, h-1]`
  (§9). Raw offset `(dx, dy) = (gx − cx, gy − cy)`; per-axis normalize by the
  half-extent `nx = dx / (w / 2)`, `ny = dy / (h / 2)` (each in `[−1, 1]` at the
  edges). `r_raw = hypot(nx, ny)` (up to `√2` into a corner); `r = min(1.0,
  r_raw)`. Fixed centre; gaze recentering is a hardware-phase concern (R8).
- **Radial dead zone.** `r ≤ DEAD_ZONE_RADIUS` (default `0.28`, fraction of
  normalized space) → zero vector, `(0.0, 0.0)`. One magnitude test, not two
  per-axis tests — no axis fires while the other is "dead". Circular in
  normalized space; an ellipse in pixels matching the viewport aspect (correct —
  a pixel-circular dead zone would starve the shorter axis).
- **Live-band rescale + outer saturation.** `t = clamp01((r −
  DEAD_ZONE_RADIUS) / (OUTER_SATURATION − DEAD_ZONE_RADIUS))`, with
  `OUTER_SATURATION` default `0.95` (gaze cannot hold the corner). `t` runs 0 at
  the dead-zone edge to 1 at/after the saturation ring. `t` and `r` use the
  **clamped** `r`.
- **Response curve.** `s = t ** RESPONSE_EXPONENT` (default `1.5`) — one curve,
  both axes. This is the former `TURN_RESPONSE_EXPONENT`, renamed and shared.
- **Reconstruct.** Unit direction from the **unclamped** norm:
  `(ux, uy) = (nx / r_raw, ny / r_raw)` (guarded by `r_raw > 0`, which the
  dead-zone early return already guarantees). The stick vector is
  `(fx, fy) = (ux * s, uy * s)`, with `hypot(fx, fy) == s` exactly, each
  component in `[−1, 1]`. Using `r_raw` (not the clamped `r`) here is what keeps
  a diagonal a genuine trade-off on the unit circle instead of over-driving both
  axes by up to ~41 % in the corners. `GazeStick.resolve` returns this
  `(fx, fy)` and nothing else — no `HeldAction`s, no state. `__init__` asserts
  `0 < DEAD_ZONE_RADIUS < OUTER_SATURATION ≤ 1` and `RESPONSE_EXPONENT > 0`.
- **Smoothing + map** (in `GazeVectorFilter`, §7). EMA the vector `(fx, fy)` —
  one filter for the whole stick, replacing the per-`TURN`-action EMA. Two
  rates: `MAGNITUDE_EMA_ALPHA` (default `0.4`) while the raw vector is non-zero
  (rising / in-band), and `RELEASE_EMA_ALPHA` (default `0.8`) while the raw
  vector is `(0.0, 0.0)` (gaze in the dead zone or `gaze_xy is None`), so a
  look-back-to-centre reaches the first quantum in ~3 ticks and a zero output
  in ~5, versus ~9 / ~14 at `MAGNITUDE_EMA_ALPHA`. Below
  `EMA_ZERO_EPSILON` (`1e-3`) the smoothed vector snaps to `(0.0, 0.0)`.
  `e_prev` starts at `(0.0, 0.0)` (no seed step) and `reset()` returns it there.
  Then map the smoothed `(ex, ey)` — still raw floats — to `HeldAction`s:
  `ey < 0 → MOVE_FORWARD |ey|`, `ey > 0 → MOVE_BACKWARD ey`, `ex < 0 →
  TURN_LEFT |ex|`, `ex > 0 → TURN_RIGHT ex`; a diagonal yields both, no corner
  special-case. `update` returns `frozenset[HeldAction]` with ≤ one `MOVE_*` and
  ≤ one `TURN_*`. Backward speed is symmetric with forward. No dwell, no grace,
  no region-change rule.

**Units.** `GazeStick.resolve(x, y) -> tuple[float, float]` (pure geometry)
replaces `GazeZoneMap`. `GazeVectorFilter.update(vec, now) ->
frozenset[HeldAction]` + `GazeVectorFilter.reset() -> None` (sets `e_prev` to
`(0.0, 0.0)`; called by `InputPipeline.release_all()`) replaces `GazeFilter`.
The filter hands `ActionRouter` **raw smoothed float magnitudes**; quantisation
stays the single responsibility of `ActionRouter` (`MAGNITUDE_STEPS`), unchanged
from pre-R14. Same two-unit split, and the gaze→filter→router seam into
`InputPipeline` is the same shape. `InputPipeline(source, send, *, surface=None,
spoken_fire=NullSpokenFireSource())`: `send` is the raw `IpcServer.send`
callable (the router wraps it in the existing `_guarded_send`); `surface` is an
explicit `(w, h)` that `host_widget` always passes from the viewport, and
`None` is a test-only fallback that reads `source.widget` — the product path
never relies on it.

**Wire (§5).** `code` table unchanged (direction stays in `code`).
`ACTION.value` changes from `10000`/`0` on-off to a proportional magnitude in
`[0, MOVE_MAGNITUDE_SCALE]` (`10000`; `0` = released), quantised by the formula
below — parallel to `TURN.value`'s `[0, TURN_MAX_MOUSE_DELTA]` (`40`).
`Message.action(code, value)` keeps its signature; only the value range widens.
`decode(encode(m)) == m` is unaffected (`decode` does no range validation).
`MOVE_MAGNITUDE_SCALE = 10000` is a named constant in `pewpew.input.actions`
beside `TURN_MAX_MOUSE_DELTA`; the C side gets the same `10000` as a `#define`
that `test_c_patch_constants_match_the_python_enums` checks equal (§15).

**Router (`pewpew.input.actions`).** `ActionRouter.set_held` emits a frame for
**both** `MOVE_*` and `TURN_*` on every call while that axis is held, and
exactly one `0` frame per axis on release. One quantisation point, one formula
for both axes: `q = round(magnitude * MAGNITUDE_STEPS) / MAGNITUDE_STEPS`
(`magnitude` clamped to `[0, 1]`), then `value = round(q * MOVE_MAGNITUDE_SCALE)`
for `MOVE_*` and `value = min(round(q * TURN_MAX_MOUSE_DELTA),
TURN_MAX_MOUSE_DELTA)` for `TURN_*`. `q == 0` (sub-quantum magnitude) emits
nothing while newly held, and emits exactly one `0` frame on the fall from a
previously-non-zero value. The pre-R14 "emit `MOVE` only on the on/off
transition" rule is removed.

**C translator (patch 2).** The spec pins the **contract**, not the mechanism.

*Pump coalescing.* `IPC_Input_Pump()` drains **all** buffered frames in one
call. `PULSE` / `DISCRETE` / `BYE` are applied per frame in arrival order (they
are edges). `TURN` and `ACTION` are **coalesced**: keep only the most recent
`TURN` frame and the most recent `ACTION` frame seen in the drain, and apply
each once after the drain — one `ev_mouse` post for turn, one `ipc_forwardmove`
assignment for forward. Without this, `G_Responder` *sums* every drained
`ev_mouse` `data2` into `mousex` (≈ 1.8 turn frames per pump at a 62.5 Hz
producer / ~35 Hz tic consumer) so turn would run ~1.8× hotter than the
last-value-wins forward axis — reintroducing the exact imbalance R14 removes —
and an unbounded `ev_mouse` burst after an engine stall can overflow the
64-slot `D_PostEvent` ring and drop a queued `ev_keyup` / pause edge.
Coalescing makes §4 data-flow step 6 ("the most recent `TURN` and `ACTION`
frame apply once per pump") literally true and bounds `D_PostEvent` traffic.

*Forward staleness watchdog.* A per-pump counter resets on any `ACTION` frame
(including the `0`) and increments otherwise; at `IPC_MOVE_STALE_PUMPS` (default
`6`, ≈ 0.1 s) `ipc_forwardmove` is zeroed. A healthy producer refreshes every
tic, so only a *frozen* (not dead) supervisor — GC pause, `SIGSTOP`, breakpoint
— trips it, making forward degrade the way turn already self-cancels when
`mousex` falls to 0 (§4 step 6, §12).

*The `ipc_forwardmove` contribution* is a signed value scaled `10000 →
MOVE_MAX_FORWARDMOVE` (`50`, DOOM's run value; sign from `code`), zeroed on
release / EOF / `BYE` / `IPC_Input_Shutdown` / the watchdog — R9's invariant
holds. The Task-3 implementer picks the mechanism against the real
`crispy-doom-7.1` source, recording the choice and rejected options in the
patch header:

1. **A bounded additive term inside `G_BuildTiccmd`** (recommended). Add
   `forward += ipc_clamp(ipc_forwardmove);` to the **local `forward`** int
   *before* DOOM's existing `BETWEEN(-MAXPLMOVE, MAXPLMOVE, forward)` clamp in
   `src/doom/g_game.c` (Doom's `G_BuildTiccmd`, not the shared `d_loop.c`), so a
   simultaneous SDL-keyboard contribution and the IPC term compose and are
   clamped together to `±MAXPLMOVE` (no turbo). `ipc_enabled`-guarded. This is
   the one patch-2 hunk in a vanilla function; ≈ 3 net lines, clearly marked.
   Deterministic, config-independent, controller-independent, and genuinely
   per-built-tic (it runs *inside* `G_BuildTiccmd`, unlike the pump). Narrows
   §10's "patch 2 edits no vanilla line" to "one clearly-marked vanilla line".
2. **Synthetic `ev_joystick`.** `crispy-doom-7.1` ships `use_analog = 1` by
   default, so a synthetic analog `ev_joystick` *would* drive `forward`
   proportionally on a stock config — but it is scaled by `forwardmove[speed]`
   (max = walk 25 unless always-run is on, not R14's fixed 50), it overwrites
   `joyxmove` / `joyymove` / `joystrafemove` / `joylook` wholesale (fighting a
   real controller), and it silently reverts to digital if the user's
   `default.cfg` disables `use_analog`. Rejected for those reasons, not for
   "the classic path is digital".
3. **Fallback — keyboard duty-cycle.** Hold `key_up` / `key_down` for N of every
   M built tics ∝ magnitude, with the duty counter gated on `maketic`
   advancing (a pump call is **not** always a built tic — `BuildNewTic()` can
   throttle before `G_BuildTiccmd`). The normalized `MOVE_* + magnitude 0–1`
   action is identical in all three; this choice never leaves the C translator.

**Cost if wrong.** If the radial stick still does not feel natural at the gate,
the tuning surface is the module constants (`DEAD_ZONE_RADIUS`,
`OUTER_SATURATION`, `RESPONSE_EXPONENT`, `MAGNITUDE_EMA_ALPHA`,
`RELEASE_EMA_ALPHA`) — `MAGNITUDE_EMA_ALPHA` / `RELEASE_EMA_ALPHA` are the
primary knobs, gate-adjustable per R11. If the C forward path (all three
options) cannot make `forwardmove` proportional, the gate records **FAIL — IPC
input path insufficient** as §17 provides, and the build drops to the
**degraded forward mode** below. The zone model is not resurrected.

**Degraded forward mode ("continuous direction, digital forward").** Not a
"one-line R6 revert" — R14 deleted the C movement-key path and the router's
MOVE-only-on-transition branch, so the coherent minimal degrade keeps R14's
shape and collapses only the *magnitude*: (a) the C translator clamps
`ipc_forwardmove` to exactly `±MOVE_MAX_FORWARDMOVE` (bang-bang) instead of the
proportional scale, keeping the coalescing, the watchdog and the fold; (b)
`ActionRouter` and `GazeVectorFilter` are unchanged (they still stream a
proportional `MOVE_*` magnitude the C side floors to full-or-zero); (c) §5's
`ACTION.value` doc and R11 note MOVE as effectively bang-bang in this mode; (d)
§17 gains a degraded-PASS line ("continuous direction; forward is single-speed;
turn is proportional"). One gaze-independent C test covers (a). Direction
(up/down/diagonal) still comes from the vector — only the walk speed loses its
ramp.

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
  decodes frames, `D_PostEvent`s key and mouse events, folds an analog
  `forwardmove` contribution (R14), and releases-all on EOF. SDL keyboard input
  is untouched.
- `scripts/build_crispy.py`: an ordered `PATCHES` tuple applied cumulatively
  on disk after a `reset --hard <commit>` + `clean -fd -- src/` restore
  (`--check` applies patch 1 for real then `--check`s patch 2); the marker
  written once after the series applies (R4, §13).
- The normalized action model and `ActionRouter` (held set, pulse, discrete,
  `release_all`), the sole owner of magnitude quantisation, draining to an
  injected sink that maps to IPC `Message` objects.
- `GazeStick` + `GazeVectorFilter` (R14): the radial analog stick — round dead
  zone, live-band rescale, one shared response curve, vector reconstruction —
  and the output-vector EMA that maps to ≤ one `MOVE_*` + ≤ one `TURN_*`.
- `FireArbiter` + the two source protocols (R7), with the real deliberate-action
  (simulator click) source and `NullSpokenFireSource` in 3a.
- `InputSource` protocol + `SimulatorInputSource` (Qt events on the host,
  including the env-gated `F9` → `debug_fire_edge` gate scaffold) +
  `PrismInputSource` stub.
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
| **A. Local socket + a small Crispy patch that `D_PostEvent`s translated events.** | **Chosen.** Implements §4 as written, keeps the two-process split, portable (`AF_UNIX` / loopback TCP), a minimal auditable second patch, reuses DOOM's own event queue and key bindings (and, for the analog forward axis, R14 adds one bounded `forwardmove` term inside `G_BuildTiccmd` — still no OS window focus, no config globals). |
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
  InputPipeline.tick(now)                             d_loop.c BuildNewTic()  (once per pump; >= built tics)
    +- GazeStick.resolve(x, y) -> (fx, fy)               +- IPC_Input_Pump()         (patch 2) -- drain +
    +- GazeVectorFilter (dual-rate EMA) -> {HeldAction}       coalesce: 1 ev_mouse dx + last ipc_forwardmove
    +- FireArbiter (click edge + spoken edge)          I_FinishUpdate
    +- ActionRouter (per-tick MOVE+TURN, quantise)       +- FB_Export_Publish()      (patch 1, unchanged)
    v                                                   IPC EOF -> zero forwardmove + keyup fire/use, stop
  IpcServer.send(Message)  --8-byte frames-->  socket  --> IPC_Input reader
  IpcServer.on_disconnect  <-- socket EOF
```

### New and changed units

| Unit | Language | Responsibility | Depends on |
| --- | --- | --- | --- |
| `pewpew.ipc.protocol` | Python | `Message` (frozen; `type`, `code: int`, `value: int`), `MessageType` enum, `encode(msg) -> bytes` (8 bytes), `decode(buf) -> (Message | None, bytes)`; `IpcProtocolError`; constants `IPC_PROTOCOL_VERSION = 1`, `IPC_FRAME_SIZE = 8`. Pure. Never imports `pewpew.input`. | `struct` (stdlib) |
| `pewpew.ipc.server` | Python | `IpcServer(*, address_factory=default)`: `start() -> str`, `poll() -> None`, `send(Message) -> None`, `is_connected: bool`, `on_disconnect: Callable`, `close()`. Blocking socket, short send timeout, single client. Sole owner of the socket path (bind + unlink). | `socket` (stdlib), `pewpew.ipc.protocol` |
| `pewpew.input.actions` | Python | `Action` enum (the sole `Action ↔ int` mapping, matching the §5 table), `HeldAction(action, magnitude)`, `ActionRouter(sink)`: `set_held(frozenset[HeldAction])`, `pulse(Action)`, `discrete(Action)`, `release_all()`. **(R14)** every `set_held` call while an axis is held emits a frame for both `MOVE_*` (`ACTION`) and `TURN_*` (`TURN`); one formula quantises both — `q = round(magnitude * MAGNITUDE_STEPS) / MAGNITUDE_STEPS`, then `value = round(q * MOVE_MAGNITUDE_SCALE)` / `min(round(q * TURN_MAX_MOUSE_DELTA), TURN_MAX_MOUSE_DELTA)`; `q == 0` emits nothing while newly held, one `0` frame on the fall / release. Constants `MAGNITUDE_STEPS` (`20`), `MOVE_MAGNITUDE_SCALE` (`10000`), `TURN_MAX_MOUSE_DELTA` (`40`). Pure + sink. | `pewpew.ipc.protocol` |
| `pewpew.input.gaze` | Python | **(R14)** `GazeStick(surface_w, surface_h, *, dead_zone_radius=0.28, outer_saturation=0.95, response_exponent=1.5)` (`__init__` asserts `0 < dz < outer_sat <= 1`, `exp > 0`): `resolve(x, y) -> tuple[float, float]` — the curved, saturated stick vector `(fx, fy)`, `hypot == s`, direction from the unclamped norm; stateless. `GazeVectorFilter(*, ema_alpha=0.4, release_alpha=0.8)`: `update(vec, now) -> frozenset[HeldAction]` (dual-rate EMA, snap `< EMA_ZERO_EPSILON`, map to ≤ one `MOVE_*` + ≤ one `TURN_*` as raw-float magnitudes — quantisation is `ActionRouter`'s) and `reset() -> None` (`e_prev` → `(0, 0)`, called by `release_all`). No dwell, grace, or region rule. Pure; time via `now` only. | `pewpew.input.actions` |
| `pewpew.input.fire` | Python | `FireArbiter(*, debounce_s=0.12)`: `deliberate_action()`, `spoken_fire()`, `poll(now) -> bool`, `reset()`. `DeliberateActionSource` / `SpokenFireSource` protocols; `NullSpokenFireSource`. Pure; time via `poll(now)` only. | — |
| `pewpew.input.source` | Python | `InputSource` protocol: `sample(now) -> InputSample`. `InputSample(gaze_xy: tuple[int,int] | None, activation_edge: bool, pause_edge: bool, debug_fire_edge: bool)`. `PrismInputSource` stub. | — |
| `pewpew.input.simulator_source` | Python | `SimulatorInputSource(widget)`: a Qt event filter tracks mouse position, left-press edges, `Return`/`Enter` edges, and (env-gated) `F9` edges; `sample(now)` returns and clears the accumulated `InputSample`. `Leave` sets `gaze_xy = None`. | PySide6, `pewpew.input.source` |
| `pewpew.input.pipeline` | Python | `InputPipeline(source, send, *, surface=None, spoken_fire=NullSpokenFireSource())`: builds `GazeStick`, `GazeVectorFilter`, `FireArbiter`, `ActionRouter(sink=_guarded_send)` where `_guarded_send` wraps the `send` callable in `try/except OSError`. `host_widget` always passes an explicit `surface=(viewport.width(), viewport.height())`; `surface=None` is a test-only fallback that reads `source.widget`. `tick(now)`, `release_all()` (resets filter + fire + router, calls `filter.reset()`), `toggle_pause()`, `paused: bool`. The single integration unit. Time via `tick(now)`. | all of the above |
| `pewpew.engine` (modified) | Python | `start(*, ipc_address: str | None = None)` injects `DOOMED_PRISM_IPC_ADDR`; when `DOOMED_PRISM_WARP` is set, appends `-warp <value> -skill <DOOMED_PRISM_SKILL or 3>` to argv; `ipc_address` property. `stop()` does **not** touch the socket path (the server owns it). Mirrors the existing `frame_segment_name` env handling. | existing |
| `pewpew.host_widget` (modified) | Python | `showEvent`: `IpcServer.start()`, `engine.start(ipc_address=…)`, build `InputPipeline`. `_on_tick`: **first** `server.poll()` + disconnect handling (before any early return), then, once past the M2 frame-wait, `pipeline.tick(now)`. `hideEvent` / child-disconnect / handshake-timeout wired per §12. `cleanup()` extended per R9. A `_PauseOverlay` child driven by `pipeline.paused`. | `pewpew.input.pipeline`, `pewpew.ipc.server` |
| `src/i_ipc_input.c` / `.h` (patch 2) | C | `IPC_Input_Init()` (connect, blocking then non-blocking; no-op if `DOOMED_PRISM_IPC_ADDR` unset), `IPC_Input_Pump()` (**(R14)** drain all frames; `PULSE`/`DISCRETE`/`BYE` per frame; **coalesce** `TURN`/`ACTION` to the last value and apply once; `PULSE_HOLD_TICS` release scheduler; `IPC_MOVE_STALE_PUMPS` forward watchdog; EOF → release held → stop), `IPC_Input_Shutdown()`. Holds `ipc_forwardmove`. GPL-2.0-or-later header matching Crispy's style. | BSD sockets / winsock; `d_event.h` |
| `src/d_loop.c`, `src/i_video.c` (patch 2) | C | ~6 lines: `IPC_Input_Init()` after `FB_Export_Init()`; `IPC_Input_Pump()` in `BuildNewTic()` once per pump call (≥ built tics — §10), immediately before `loop_interface->ProcessEvents()`; `IPC_Input_Shutdown()` before `FB_Export_Shutdown()`. No signal-handler edit (§10). | the above |
| `src/doom/g_game.c` (patch 2, **only if R14 mechanism 1**) | C | one `ipc_enabled`-guarded hunk (≈ 3 net lines) folding `ipc_forwardmove` into the local `forward` int just before `G_BuildTiccmd`'s existing `BETWEEN(-MAXPLMOVE, MAXPLMOVE, forward)` clamp. Absent if mechanism 2/3 is chosen. | the above |
| `scripts/build_crispy.py` (modified) | Python | `PATCHES` tuple; cumulative on-disk apply after `reset --hard <commit>` + `clean -fd -- src/` (leaves `<dir>/build/` intact); `--check` = restore + real `apply p1` + `apply --check p2`; marker written once (R4, §13). | existing |
| `patches/crispy-doom-ipc-input.diff` | diff | The complete IPC-input modification, authored against the patch-1 tree. GPL-2.0-or-later. Adds `src/i_ipc_input.c` / `.h` plus small hunks in `d_loop.c` / `i_video.c` / `src/CMakeLists.txt` and — **only if R14 mechanism 1 is chosen** — one clearly-marked hunk in `src/doom/g_game.c`. | — |
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
4. **(R14)** `vec = stick.resolve(*sample.gaze_xy)` when `gaze_xy` is not
   `None`, else `(0.0, 0.0)` — the curved, saturated stick vector.
5. **(R14)** `held = vector_filter.update(vec, now)` — EMA the vector (rate
   `MAGNITUDE_EMA_ALPHA`, or `RELEASE_EMA_ALPHA` while `vec` is `(0, 0)`), then
   map to ≤ one `MOVE_*` and ≤ one `TURN_*` `HeldAction` as **raw floats**. No
   dwell / grace / region rule (there are no regions). Quantisation is not done
   here (§7).
6. **(R14)** `router.set_held(held)` — while an axis is held it emits a frame on
   **every** call, both axes quantised by the one formula (`q = round(magnitude
   * MAGNITUDE_STEPS) / MAGNITUDE_STEPS`): `MOVE_*` an `ACTION` frame with
   `value = round(q * MOVE_MAGNITUDE_SCALE)`, `TURN_*` a `TURN` frame with
   `value = min(round(q * TURN_MAX_MOUSE_DELTA), TURN_MAX_MOUSE_DELTA)`. Each
   axis emits exactly one `0` frame on the fall to `q == 0` / release. The C
   pump coalesces per drain (§10), so the **most recent** `TURN` and `ACTION`
   frame each apply once per pump — the Python side emits every tick so the C
   value is always current and the forward staleness watchdog sees liveness.
7. `if sample.activation_edge: fire.deliberate_action()`;
   `if spoken_fire.spoken_fire_edge() or sample.debug_fire_edge:
   fire.spoken_fire()`; `if fire.poll(now): router.pulse(FIRE)`.
8. `if sample.pause_edge: pipeline.toggle_pause()` — sends one `DISCRETE PAUSE`,
   flips `pipeline.paused`, and the host shows/hides `_PauseOverlay`.
9. Each `router` emission calls the injected `send` callable — the pipeline's
   `_guarded_send`, which wraps `IpcServer.send` in `try/except OSError`. Before
   the handshake completes `IpcServer.send` is a no-op; the router still tracks
   held state so it re-sends or releases later. (R14: the pipeline holds a
   `send` callable, not the `IpcServer` object.)
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
| 4 | `value` | i32 | `ACTION` (R14): proportional magnitude `[0, MOVE_MAGNITUDE_SCALE]` (`10000`), `0` on release; direction is in `code`. `TURN`: unsigned clamped mouse-x magnitude `[0, TURN_MAX_MOUSE_DELTA]` (`40`), direction in `code`. `PULSE`/`DISCRETE`/`HELLO`/`BYE`: `0`. |

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
imports `pewpew.input`. `Message.action(code, value)` (caller passes the scaled,
quantised magnitude `0..MOVE_MAGNITUDE_SCALE`), `Message.turn(code, value)`
(caller passes the clamped mouse-x magnitude), `Message.pulse(code)` /
`Message.discrete(code)` /
`Message.hello()` / `Message.bye()` (`value = 0`). All take a plain `int`
`code`. All the magnitude→wire scaling lives in `ActionRouter`
(`pewpew.input.actions`, which owns `MAGNITUDE_STEPS`, `MOVE_MAGNITUDE_SCALE`
and `TURN_MAX_MOUSE_DELTA`): one quantiser for both axes — `q = round(magnitude
* MAGNITUDE_STEPS) / MAGNITUDE_STEPS`, then `round(q * MOVE_MAGNITUDE_SCALE)`
for `MOVE_*` and `min(round(q * TURN_MAX_MOUSE_DELTA), TURN_MAX_MOUSE_DELTA)`
for `TURN_*` (R14). The round-trip contract is `decode(encode(m)) == m`
(`decode` does no value-range validation); `ActionRouter`'s scaling is tested
separately.

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
  must not stall the Qt UI thread). At M3's volume — under ~1 KB/s over
  loopback / `AF_UNIX` even with R14's per-tick `MOVE` + `TURN` streams — a
  blocking `sendall` never actually blocks (64 KB+ socket buffers).
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

## 7. The gaze stick and the vector filter (R14)

`pewpew.input.gaze`, pure Python, time supplied by the `now` argument. R14
(2026-09-07) replaced the rectangular `GazeZoneMap` / dwell-gated `GazeFilter`
with a radial analog stick: movement and turning are two axes of one curved
vector, so moving feels like looking around. R14's "Why" records the three
gate findings this dissolves.

### `GazeStick`

`GazeStick(surface_w, surface_h, *, dead_zone_radius=DEAD_ZONE_RADIUS (0.28),
outer_saturation=OUTER_SATURATION (0.95),
response_exponent=RESPONSE_EXPONENT (1.5))`. `__init__` asserts
`0 < dead_zone_radius < outer_saturation <= 1` and `response_exponent > 0`.

`InputPipeline` constructs it with the **host viewport's real `(width,
height)`** — `host_widget` passes `surface=(self.viewport.width(),
self.viewport.height())` (640×480 for the current simulator); a 640×640 default
was finding 1's root cause. `SimulatorInputSource` reports `gaze_xy` in
viewport-local pixels clamped to that rect (§9), so a resting gaze at the
viewport centre maps to `(0, 0)`. Centre is `(surface_w // 2, surface_h // 2)`,
fixed; gaze recentering is a hardware-phase concern (R8).

`resolve(x, y) -> (fx, fy)`, stateless:

1. `dx, dy = x - cx, y - cy`.
2. Per-axis normalize: `nx = dx / (surface_w / 2)`, `ny = dy / (surface_h / 2)`
   — each ≈ `±1.0` at the outermost reachable pixel (`w-1` / `h-1`, ~one part
   in `w/2` short of exactly `1.0`; `OUTER_SATURATION` covers the gap).
3. `r_raw = hypot(nx, ny)` (up to `√2` toward a corner); `r = min(1.0, r_raw)`.
   If `r <= dead_zone_radius` → return `(0.0, 0.0)` (the round dead zone — one
   magnitude test, so no axis fires while the other is dead). This early return
   also guarantees `r_raw > 0` below.
4. `t = clamp01((r - dead_zone_radius) / (outer_saturation - dead_zone_radius))`
   — 0 at the dead-zone edge, 1 at/after the saturation ring. Uses the
   **clamped** `r`.
5. `s = t ** response_exponent` — one curve for both axes.
6. Unit direction from the **unclamped** norm: `ux, uy = nx / r_raw, ny / r_raw`.
   Return `(ux * s, uy * s)` — `hypot` of the result is exactly `s`, each
   component in `[-1, 1]`. Normalizing by `r_raw` (not `r`) is what makes a
   corner gaze a real trade-off on the unit circle instead of driving both axes
   toward `s` at once (~41 % over-drive).

The vector's *direction* is exactly where gaze points; its *magnitude* is the
curved, saturated deflection, continuous across the dead-zone boundary
(`t → 0 ⇒ s → 0`).

### `GazeVectorFilter`

`GazeVectorFilter(*, ema_alpha=MAGNITUDE_EMA_ALPHA (0.4),
release_alpha=RELEASE_EMA_ALPHA (0.8))`.

`update(vec, now) -> frozenset[HeldAction]`:

1. Choose the rate: `a = release_alpha` when `vec == (0.0, 0.0)` (gaze in the
   dead zone, or `gaze_xy is None`), else `ema_alpha`. EMA each component:
   `e = a * vec + (1 - a) * e_prev`. `e_prev` starts at `(0.0, 0.0)` (no seed
   step — the first non-zero `vec` rises from zero). Snap `e` to exactly
   `(0.0, 0.0)` once `hypot(e) < EMA_ZERO_EPSILON` (`1e-3`). The faster
   `release_alpha` makes a look-back-to-centre reach the first quantum in ~3
   ticks and snap in ~5, versus ~9 / ~14 at `ema_alpha`.
2. Map the smoothed `(ex, ey)` — **still raw floats** — to `HeldAction`s:
   `ey < 0 -> HeldAction(MOVE_FORWARD, |ey|)`, `ey > 0 ->
   HeldAction(MOVE_BACKWARD, ey)`; `ex < 0 -> HeldAction(TURN_LEFT, |ex|)`,
   `ex > 0 -> HeldAction(TURN_RIGHT, ex)`. A component of exactly `0.0`
   contributes nothing. Result has ≤ one `MOVE_*` and ≤ one `TURN_*`.

`reset() -> None` sets `e_prev` back to `(0.0, 0.0)`; `InputPipeline.release_all()`
calls it, so a hide / disconnect / shutdown leaves no decaying tail for the next
acquisition.

No dwell, no grace, no region-change rule — the dead zone plus the EMA are the
whole jitter defence. `MAGNITUDE_EMA_ALPHA` / `RELEASE_EMA_ALPHA` are the primary
gate tuning knobs (R14 "Cost if wrong"). The `now` argument is retained for
pipeline symmetry and a possible future rate limit; the default filter does not
read it.

Quantisation stays in `ActionRouter` (§4 step 6, `MAGNITUDE_STEPS` in
`pewpew.input.actions`) — one quantisation point, one formula for both axes
(R14 "Router"); `GazeVectorFilter` hands it raw smoothed floats. A held axis
whose quantised magnitude `q` is `0` emits nothing while newly held, and emits a
single `0` frame on the fall from a previously-non-zero value.

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
`NullSpokenFireSource` returns `False` forever (3a default). `FakeSpokenFireSource`
(test fakes) exposes `trigger()` and is used in the fusion unit tests. In the 3a
gate the spoken-fire edge comes from `SimulatorInputSource`'s env-gated `F9`
key via `InputSample.debug_fire_edge`, not a `SpokenFireSource`.

## 9. Input sources

`pewpew.input.source` / `pewpew.input.simulator_source`.

`InputSource` protocol: `sample(now) -> InputSample`. `InputSample` is a frozen
dataclass: `gaze_xy: tuple[int, int] | None`, `activation_edge: bool`,
`pause_edge: bool`, `debug_fire_edge: bool`. Edges mean "did this happen since
the last `sample()`" and are cleared by the call.

`SimulatorInputSource(widget)` installs a Qt event filter on `widget` (the
`_DoomViewport`, geometry `(0, 80, 640, 480)`) and enables mouse tracking. It
exposes `widget` as a public read-only attribute so `InputPipeline` can read
the viewport size for the `surface=None` test fallback (R14 — the product path
passes `surface` explicitly).

- **(R14)** `MouseMove` → store the position in **viewport-local pixels**,
  clamped to `[0, widget.width() - 1] × [0, widget.height() - 1]` (640×480 for
  the current simulator). This is the space `GazeStick` is built with, origin at
  the viewport's top-left, so a resting gaze at the viewport centre is `(0, 0)`
  after normalization. (Pre-R14 the pipeline built a 640×640 `GazeZoneMap` over
  this 640×480 space — finding 1.)
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
- `void IPC_Input_Pump(void)` — if disabled, return. **(R14) Drain the whole
  socket buffer** with non-blocking `recv` into an 8-byte staging buffer. As
  each complete frame is decoded: `PULSE` / `DISCRETE` / `BYE` are applied
  **per frame, in arrival order** (they are edges); `TURN` and `ACTION` are
  **coalesced** — remember only the most recent `TURN` frame and the most
  recent `ACTION` frame, applying each **once** after the drain finishes. This
  is load-bearing: `G_Responder` *sums* every `ev_mouse` `data2` into `mousex`,
  so posting one `ev_mouse` per buffered `TURN` frame (≈ 1.8 per pump at
  62.5 Hz producer / ~35 Hz consumer, and an unbounded burst after an engine
  stall) would make turn out-scale the last-value-wins forward axis and can
  overflow the 64-slot `D_PostEvent` ring. Also decrement `PULSE_HOLD_TICS`
  countdowns and step the `IPC_MOVE_STALE_PUMPS` watchdog once per pump call.
  - `ACTION` `MOVE_FORWARD` / `MOVE_BACKWARD` **(R14, analog, coalesced)**:
    scale the last frame's `value` (`0..IPC_MOVE_WIRE_MAX` = `10000`) to
    `0..MOVE_MAX_FORWARDMOVE` (`50`), sign from `code` (`MOVE_FORWARD` positive,
    `MOVE_BACKWARD` negative), store as the single signed `ipc_forwardmove`;
    `value == 0` sets it to `0`. Reset the stale-pump counter on **any**
    `ACTION` frame (incl. `0`). The pump posts **no** movement key; the mechanism
    the Task-3 implementer selects per R14 folds `ipc_forwardmove` into DOOM's
    `forward` (primary: the additive term inside `G_BuildTiccmd`; then
    `ev_joystick`; fallback: a `key_up` / `key_down` duty-cycle gated on
    `maketic`). No `held[]` bit for movement; release-all (below) just zeroes
    `ipc_forwardmove` (plus, in the duty-cycle fallback, the paired `ev_keyup`).
  - **Forward staleness watchdog (R14):** if the stale-pump counter reaches
    `IPC_MOVE_STALE_PUMPS` (`6`), set `ipc_forwardmove = 0`. A healthy producer
    sends an `ACTION` frame every tic, so this only trips when the supervisor is
    *frozen but not dead* (no EOF) — making forward degrade the way turn already
    does when `mousex` naturally falls to 0.
  - `TURN` `TURN_LEFT` / `TURN_RIGHT` **(coalesced)**: from the last `TURN`
    frame, `int d = value; if (d > IPC_TURN_CLAMP) d = IPC_TURN_CLAMP; if (d <
    0) d = 0;` then post **one** `ev_mouse` with `data2 = (code == TURN_LEFT ?
    -d : d)` and `data3 = 0`. `data1` (mouse-button bitmap) is `0`: the 3a gate
    runs with Crispy's SDL window unfocused, so a per-pump `SetMouseButtons(0)`
    is harmless; real SDL button tracking is a hardware-phase refinement. Post
    only when `d != 0`; a last frame of `0` posts nothing (letting `mousex`
    fall to 0 is the release).
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
    **release-all**: `ipc_forwardmove = 0` (plus, in the duty-cycle fallback,
    `ev_keyup` for any movement key still held); post a defensive `ev_keyup` for
    `key_fire` / `key_use`; `ipc_enabled = 0`; close the socket. DOOM continues
    on SDL input.
- `void IPC_Input_Shutdown(void)` — release-all, close the socket, `WSACleanup`
  on Windows. Idempotent (guarded by `ipc_enabled` plus a `socket >= 0` check).
  Does not `unlink` — the server owns the path.

**Call sites (patch 2 hunks):**

- `IPC_Input_Init();` immediately after `FB_Export_Init();` in `I_InitGraphics`
  (`src/i_video.c`) — that context line exists because patch 1 is applied first.
- `IPC_Input_Pump();` in `BuildNewTic()` in `src/d_loop.c`, immediately before
  `loop_interface->ProcessEvents()`, so injected and SDL events share one queue
  and the following `G_BuildTiccmd`. **Binding invariant:** one pump per
  `BuildNewTic()` call, after SDL events are drained and before
  `G_BuildTiccmd`. Note `BuildNewTic()` calls are a **superset** of built tics —
  it can `return false` at the maketic throttle *before* `G_BuildTiccmd`, and
  `NetUpdate()` calls it `0..newtics` times per frame. So a pump call is not
  guaranteed to be followed by a built tic; the `PULSE_HOLD_TICS` countdown and
  the `IPC_MOVE_STALE_PUMPS` watchdog count **pump calls**, and R14 mechanism 1
  is preferred precisely because the fold runs *inside* `G_BuildTiccmd` (truly
  per built tic), while the mechanism-3 duty counter must be gated on `maketic`
  advancing. The final function and line are recorded in the patch header
  comment (as M2 §0 did). `TryRunTics()` does **not** satisfy the invariant.
- `IPC_Input_Shutdown();` immediately before `FB_Export_Shutdown();` in
  `I_ShutdownGraphics` (the normal-exit path).
- `forward` fold **(R14, mechanism 1 only)** — one `ipc_enabled`-guarded hunk
  in `G_BuildTiccmd` (`src/doom/g_game.c`): `forward += ipc_clamp(
  ipc_forwardmove);` added to the **local `forward` int**, immediately *before*
  DOOM's existing `BETWEEN(-MAXPLMOVE, MAXPLMOVE, forward)` clamp — so a
  simultaneous SDL-keyboard forward and the IPC term compose and are clamped
  **together** to `±MAXPLMOVE` (folding into `cmd->forwardmove` *after* the
  clamp would let the two sum to `2 × MAXPLMOVE` and trip `TURBOTHRESHOLD`).
  ≈ 3 net lines, clearly commented, posts no event. Absent if mechanism 2/3 is
  chosen. This is the one patch-2 edit to a vanilla (non-patch-1, non-new)
  line. Note the IPC term bypasses DOOM's `speed` / always-run state — full
  deflection is always `MOVE_MAX_FORWARDMOVE` (run), so a tester who toggles
  always-run sees SDL-keyboard forward change but IPC forward unchanged. This
  matches R14's fixed `10000 → 50` mapping and is intentional.
- **No signal handling in patch 2.** On a SIGINT/SIGTERM stop the process dies
  before `I_ShutdownGraphics` runs, but the kernel closes the client socket fd
  as the process exits, so the server (PewPew) sees EOF, runs its own
  `on_disconnect`, and unlinks the socket path it owns (§6, R3). Patch 1's
  `fb_signal_handler` still unlinks the shared-memory segment. Apart from the
  optional R14 `G_BuildTiccmd` fold above, every patch-2 hunk is an addition in
  a region patch 1 introduced (`I_InitGraphics` / `I_ShutdownGraphics` bodies),
  a region patch 1 does not touch (`d_loop.c`), or a new file.

**`src/CMakeLists.txt`:** add `i_ipc_input.c i_ipc_input.h` to the source list
(a different line from patch 1's `i_framebuffer_export.*` insertion); `if(WIN32)
list(APPEND EXTRA_LIBS ws2_32)`.

**Constants** shared byte-for-byte with `pewpew.ipc.protocol` and the §5 table:
`IPC_FRAME_SIZE 8`, `IPC_PROTOCOL_VERSION 1`, the `MessageType` values, the
action `code`s, and **(R14)** `IPC_MOVE_WIRE_MAX 10000` (`#define`d equal to
`pewpew.input.actions.MOVE_MAGNITUDE_SCALE`). `PULSE_HOLD_TICS`, `IPC_TURN_CLAMP`,
**(R14)** `MOVE_MAX_FORWARDMOVE 50` and `IPC_MOVE_STALE_PUMPS 6` are C-side
constants (R11) with no Python equal — `test_c_patch_constants_match_the_python_enums`
checks the shared set for equality and the C-only set for presence (§15).

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
  release-all **(R14)** zeroes `ipc_forwardmove` (plus `ev_keyup` for any
  movement key in the duty-cycle fallback) and posts `ev_keyup` for fire/use;
  turn self-cancels as `mousex` decays; DOOM keeps running on SDL input, then
  exits when its window closes (M2 lifecycle). A *frozen* (not dead) supervisor
  sends no EOF — the `IPC_MOVE_STALE_PUMPS` watchdog zeroes `ipc_forwardmove`
  after ~0.1 s.
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
  "patches/crispy-doom-ipc-input.diff")` and applies the series **cumulatively
  on disk** (R4 — `git apply` does not compose multiple patch-file arguments):
  - Real build, marker absent: `git -C <dir> reset --hard <lock.commit>` +
    `git -C <dir> clean -fd -- src/` (reverts patch-1 edits, removes both
    patches' new `src/` files and any partial prior apply, leaves `<dir>/build/`
    intact), then `git -C <dir> apply <p1>`, then `git -C <dir> apply <p2>`,
    then write `.doomed-prism-applied` **once**. Any step failing leaves no
    marker; the next run's restore returns pristine and re-attempts the whole
    series (self-healing after a partial apply).
  - `--check`: same restore, then `git -C <dir> apply <p1>` (real), then
    `git -C <dir> apply --check <p2>`. No marker. The next real build restores
    and re-applies both, so `--check` never corrupts a later build.
  - Tests: marker absent → restore + `apply p1` + `apply p2` + marker once;
    `--check` → restore + `apply p1` + `apply --check p2`, no `cmake`, no
    marker; a run left with p1 on disk and no marker → next run restores and
    re-applies cleanly; the existing `git rev-parse HEAD == lock.commit` guard
    still holds after the reset.
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
  **Fixed minimum assertion set (an exit criterion, §18) — (R14):** `HELLO`
  handshake succeeds; a 500-frame flood is accepted, interleaving (a) `TURN`
  values sweeping `0 … TURN_MAX_MOUSE_DELTA + margin` (exercises the C clamp),
  (b) a `MOVE_FORWARD` magnitude ramp `0 → MOVE_MAGNITUDE_SCALE → 0` and a
  `MOVE_BACKWARD` ramp (exercises the analog `forwardmove` path and its
  terminating `0`), and (c) a `PULSE FIRE` burst; **across the MOVE-ramp window
  specifically**: `server.is_connected` stays true and `on_disconnect` never
  fires (no fixed-frame desync on the widened value range), `proc.poll()` stays
  `None` (no `I_Error` / assertion on a mid-range `forwardmove`), and
  `frame_counter` gains ≥ 10 distinct values (engine alive and folding input);
  `frame_counter` keeps advancing over the whole run; `server.close()` then the
  engine exits within a bounded wait or on `SIGINT`; no orphan `crispy-doom`;
  the fixed socket path is gone. Any richer assertion (e.g. proving the view
  actually turned or walked) may be added as an `xfail`-marked extra with a
  recorded reason, never removed silently. The script prints only
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
  plus small hunks in `d_loop.c` / `i_video.c` / `src/CMakeLists.txt` and —
  **only when R14's `forwardmove` mechanism 1 is chosen** — one clearly-marked
  ≈ 3-line hunk in `src/doom/g_game.c` (`G_BuildTiccmd`). Any other file is
  `BLOCKED/RETRY`. A stated net-added-line ceiling (≤ 420, allowing the R14
  coalescing / watchdog / fold) is checked by eye against the `--stat` output;
  `test_distribution_metadata.py` asserts the diff's touched-file set is within
  this allow-list. A future scanner heuristic (flag any `patches/*.diff` that
  adds a complete `*.c` body over N lines) is noted as optional follow-up.
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
- **`pewpew.input.actions` (R14).** `set_held` emits a frame for **both**
  `MOVE_*` (`ACTION`) and `TURN_*` (`TURN`) on every call while that axis is
  held, and exactly one `0` frame per axis on release / fall to `q == 0`. The
  one quantiser (`q = round(magnitude * MAGNITUDE_STEPS) / MAGNITUDE_STEPS`,
  then `round(q * MOVE_MAGNITUDE_SCALE)` / `min(round(q * TURN_MAX_MOUSE_DELTA),
  TURN_MAX_MOUSE_DELTA)`) is asserted for `magnitude` `1.0` (→ `10000` / `40`),
  a mid value on the step grid, a sub-quantum value (emits nothing while newly
  held; one `0` on the fall from a non-zero value), and an over-`1.0` guard
  (clamped). `pulse` / `discrete` emit one frame; `release_all` emits a `0`
  frame for every held axis and nothing for already-released ones; the sink
  receives `Message`s whose `code` matches the §5 table.
- **`pewpew.input.gaze` (R14).** `GazeStick.resolve`: the dead-zone circle
  interior returns `(0, 0)`; a point just outside returns a small vector, a
  point at/beyond the saturation ring returns `hypot == 1.0`, magnitude
  increases monotonically between (the curve); the returned direction matches
  the gaze direction (unit-vector check); a **corner** point (`hypot(nx, ny) >
  1`) still returns `hypot(fx, fy) == s` (≤ 1), *not* `√2·s` — the unclamped-norm
  fix; `y = h-1` yields `ny ≈ +1.0` (not `+1.33`), `y = 0` yields `≈ −1.0`;
  `GazeStick(640, 480)` and `GazeStick(640, 640)` classify the same pixel
  differently. `__init__` rejects `outer_saturation <= dead_zone_radius` and
  `response_exponent <= 0`. `GazeVectorFilter.update` with an explicit `now`:
  the output-vector EMA ramps toward a held vector at `MAGNITUDE_EMA_ALPHA`; a
  one-sample dropout to a *nearby non-zero* vector barely dents the output
  (still `ema_alpha` — EMA, not a hard drop); a genuine `(0, 0)` input applies
  the faster `RELEASE_EMA_ALPHA` (an ~80 % single-tick drop — that is the
  intended look-back-to-centre response), reaching a zero output in ~3–5 ticks;
  the EMA state resets to `(0, 0)` after the output settles; `reset()` zeroes
  `e_prev` so a held vector then `reset()` then a dead-zone sample yields the
  empty set with no residual; the map yields ≤ one `MOVE_*` + ≤ one `TURN_*`
  with the right signs.
- **`pewpew.input.gaze` — the finding-2 sweep (R14).** Feed `GazeVectorFilter` a
  20–40-sample arc from `(cx, cy − k)` (pure forward) through `(cx + k·0.7, cy −
  k·0.7)` to `(cx + k, cy)` (pure right), stepping through where the pre-R14 zone
  boundary sat: assert `MOVE_FORWARD` magnitude is > 0 for every sample with
  `ey < 0` and never drops by more than one EMA step between consecutive
  samples — forward does not stutter or cut on a diagonal sweep.
- **`pewpew.input.fire`.** A single edge fires once; two edges inside
  `debounce_s` fire once; edges `debounce_s` apart fire twice; three edges at
  `t = 0, 0.05, 0.20` with `debounce_s = 0.12` → 2 shots (the mid edge is
  discarded, not queued); `deliberate` and `spoken` edges fuse; `reset()` drops
  pending edges. `NullSpokenFireSource` never fires; `FakeSpokenFireSource.
  trigger()` does.
- **`pewpew.input.pipeline` (R14).** With a `FakeInputSource` reporting a
  640×480 widget and a `FakeIpcServer` recording sent `Message`s:
  - **F1 guard** — built with **no explicit `surface`** the pipeline resolves
    the stick centre to `(320, 240)`; gaze `(320, 479)` sends `MOVE_BACKWARD`
    whose `value` equals (within one quantum) `MOVE_FORWARD`'s for gaze
    `(320, 0)` — the surface is viewport-sized and symmetric, not a 640×640
    constant.
  - **F2 guard** — a diagonal gaze sweep (as in the gaze sweep test) produces a
    `MOVE_FORWARD` `ACTION` stream with no frame dropping to `0` mid-sweep.
  - **F3 guard** — a gaze track of increasing eccentricity along +y produces a
    monotonically non-decreasing `MOVE_FORWARD` `value` stream, in step with the
    `TURN` `value` stream for the same eccentricity along +x.
  - an `activation_edge` produces a `FIRE` pulse; a `pause_edge` toggles
    `paused` and sends one `DISCRETE PAUSE`; `release_all()` calls
    `filter.reset()`, emits exactly one `0` `ACTION` and one `0` `TURN` for the
    held axes, and resets `paused`; a disconnect mid-track stops sends without
    raising (the `_guarded_send` `OSError` swallow).
- **`pewpew.input.simulator_source`** with `pytest-qt`: synthesised
  `QMouseEvent` / `QKeyEvent` produce the right `InputSample`; `Leave` clears
  `gaze_xy`; `F9` sets `debug_fire_edge` only when `DOOMED_PRISM_DEBUG_FIRE` is
  set; edges are one-shot.
- **`pewpew.engine`.** `start(ipc_address=…)` puts `DOOMED_PRISM_IPC_ADDR` in
  the child env (a fake `popen_factory` captures `env=`); with
  `DOOMED_PRISM_WARP="1 1"` set, argv gains `-warp 1 1 -skill 3` (and
  `DOOMED_PRISM_SKILL` overrides the `3`); unset → argv byte-identical to M2;
  `ipc_address` property; `stop()` does **not** touch the socket path. The
  existing exact-argv assertion in
  `test_start_launches_configured_windowed_engine_once_and_returns_its_pid` gains
  `monkeypatch.delenv("DOOMED_PRISM_WARP", raising=False)` (and `DOOMED_PRISM_SKILL`)
  so a developer with those exported does not see it fail; the
  `DOOMED_PRISM_FB_NAME` tests still pass.
- **`pewpew.host_widget`** with `pytest-qt` and injected fakes: `showEvent`
  starts the server before the engine and passes the address; **(R14)** the
  non-injected `showEvent` builds `InputPipeline` with an explicit
  `surface=(self.viewport.width(), self.viewport.height())` — a test asserts the
  constructed pipeline's stick centre is `(320, 240)` (the F1 guard at the host
  layer, since the real viewport geometry is `(0, 80, 640, 480)`). `_on_tick`
  calls `server.poll()` **before** any early return and calls `pipeline.tick()`
  only past the frame-wait; `hideEvent` (not shutting down) runs `release_all()`
  + one `PAUSE` + shows the overlay, and `showEvent` after start is symmetric
  (unpause + hide overlay); a child disconnect runs `release_all()` +
  `server.close()` and **no** `PAUSE`; `cleanup()` runs stop-tick → release-all
  → server-close → reader-close → engine-stop in that order (recorded on fakes)
  and is idempotent; the handshake-timeout path raises `RuntimeError("engine did
  not connect input")` after cleanup and the version-mismatch path raises
  `RuntimeError("input protocol mismatch")` after cleanup.
- **`scripts/build_crispy.py`.** `plan_commands` (marker absent) emits
  `reset --hard <commit>` + `clean -fd -- src/` + `apply <p1>` + `apply <p2>`, in that
  order, and the marker is written once after `apply <p2>` succeeds. Under
  `--check` it emits `reset --hard` + `clean -fd -- src/` + `apply <p1>` +
  `apply --check <p2>`, no `cmake`, no marker. Tests: the ordered command list
  for each mode; a checkout left with p1 on disk and no marker → next run's
  `reset --hard` restores and the series re-applies; the `HEAD == lock.commit`
  guard still passes after the reset. Existing single-patch tests updated to the
  tuple.
- **`tests/test_distribution_metadata.py`.** Expectations updated for the new
  modules, the new patch, and `scripts/ci_ipc_smoke.py`. **(R14)**
  `test_c_patch_constants_match_the_python_enums` gains: the shared set
  (`IPC_MOVE_WIRE_MAX` `#define` == `pewpew.input.actions.MOVE_MAGNITUDE_SCALE`
  == `10000`) checked for equality, and the C-only set (`MOVE_MAX_FORWARDMOVE`
  `50`, `IPC_MOVE_STALE_PUMPS` `6`) checked for presence in the diff. A separate
  assertion: the diff's touched-file set is a subset of the §14 allow-list
  (`i_ipc_input.c/.h`, `d_loop.c`, `i_video.c`, `CMakeLists.txt`, and
  optionally `doom/g_game.c`).
- **`tests/test_validation_docs_m3.py`** (new, mirroring
  `test_validation_docs.py`): the 3a checklist and result carry the **five**
  decision strings (incl. R14's degraded-forward PASS), the "IPC-only, SDL
  window unfocused" phrasing, the release-all lifecycle checks, both
  publication-safety scan invocations, the `git apply --stat` diff-minimality
  step, and only the placeholder IPC-address forms (no `AppData\Local\Temp` /
  `/home/` / `/Users/`). **(R14)** it also asserts the checklist contains the
  radial-stick geometry phrases ("dead-zone circle", "one vector", "proportional
  forward", "diagonal", "backward as reachable as forward") and does **not**
  contain the retired zone vocabulary ("turn band", "upper band", "upper
  corner", "progressive turn", rectangular "dead zone").
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

The 14-task sequence below was implemented on `feature/doomed-prism-m3` and is
CI-green. **R14 (2026-09-07)** re-plans only the tasks it touches, in a follow-up
plan `docs/superpowers/plans/2026-09-07-doomed-prism-milestone-3a-radial-stick.md`
executed on the same branch on top of the shipped work:

- **task 3** — C translator: analog `ipc_forwardmove` + the `forwardmove` fold
  (mechanism 1 preferred), per-drain `TURN`/`ACTION` coalescing, the
  `IPC_MOVE_STALE_PUMPS` watchdog, the new `#define`s; regenerate the diff;
  rebuild under MSYS2 + confirm the Linux CI smoke.
- **task 5** — `ActionRouter`: per-tick `MOVE` + `TURN` emit, the one
  `MAGNITUDE_STEPS` quantiser formula, `MOVE_MAGNITUDE_SCALE`, sub-quantum →
  nothing / one `0` on the fall.
- **task 6** — `pewpew.input.gaze`: `GazeZoneMap`/`GazeFilter` →
  `GazeStick` (unclamped-norm reconstruction, `__init__` asserts) /
  `GazeVectorFilter` (dual-rate EMA, `EMA_ZERO_EPSILON` snap, `reset()`); the
  finding-2 sweep test.
- **task 8** — `simulator_source`: expose `widget` read-only; correct the §9
  coordinate-space comment (behaviour already viewport-relative). **task 9** —
  `InputPipeline`: `surface` arg (explicit from the host), `_guarded_send`
  wrapping the `send` callable, `release_all` → `filter.reset()`; the F1/F2/F3
  pipeline guards.
- **task 11** — `host_widget`: build the pipeline with
  `surface=(viewport.width(), viewport.height())`; the host-layer F1 centre
  assertion.
- **tasks 12–14** — README line on the stick; `test_distribution_metadata`
  constant + allow-list assertions; `ci_ipc_smoke.py` analog `MOVE` flood
  (§13); **rewrite `docs/validation/milestone-3a-checklist.md` and
  `-result.md`** to the §17 R14 geometry and the five decision strings, and add
  the `test_validation_docs_m3.py` present/absent phrase assertions.

Tasks 1, 2, 4, 7, 10 (protocol, server, build script, fire, engine) are
untouched. The follow-up plan is itself audited by separate auditor agents
before execution.

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
4. `scripts/build_crispy.py` — `PATCHES` tuple, cumulative on-disk apply with a
   `reset --hard <commit>` + `clean -fd -- src/` restore before every attempt,
   `--check` = restore + real `apply p1` + `apply --check p2`, marker written
   once after `apply p2` (R4, §13); `tests/test_build_crispy.py` updates.
   *(A clean split point: tasks 1–4 are the transport core, R1 note.)*
5. `pewpew.input.actions` — `Action` (values = §5 table), `HeldAction`,
   `ActionRouter` (sole quantiser); `tests/test_input_actions.py`.
6. `pewpew.input.gaze` — **(R14)** `GazeStick` (radial vector), `GazeVectorFilter`
   (output-vector EMA, `now`-argument time); `tests/test_input_gaze.py`.
7. `pewpew.input.fire` — `FireArbiter` (discard-in-window), source protocols,
   `NullSpokenFireSource`, `tests/fakes/fake_fire.py` (`FakeSpokenFireSource`);
   `tests/test_input_fire.py`.
8. `pewpew.input.source` + `pewpew.input.simulator_source` — `InputSource`,
   `InputSample` (incl. `debug_fire_edge`), `SimulatorInputSource` (with the
   env-gated `F9` handler), `PrismInputSource` stub;
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
inside the Qt viewport — the radial analog stick (proportional turn **and**
forward/back from one gaze vector, round dead zone), debounced click-fire,
fused spoken-fire (the `F9` debug source with `DOOMED_PRISM_DEBUG_FIRE=1`),
Enter-pause — with Crispy's SDL window unfocused the entire time, does moving
feel as controllable as looking around, and does every lifecycle transition
release all held input with no stuck key/forward and no orphan?

**Environment and launch.** `python scripts/build_crispy.py` builds the patched
engine from the series; `python scripts/build_crispy.py --check` passes (restore
+ real `apply p1` + `apply --check p2`); record the pinned tag and commit,
compiler, and SDL2 versions. Record `git apply --stat
patches/crispy-doom-ipc-input.diff` and confirm it adds only
`src/i_ipc_input.c` / `.h` plus small hunks in `d_loop.c` / `i_video.c` /
`src/CMakeLists.txt` — and, if R14 `forwardmove` mechanism 1 was chosen, one
marked `src/doom/g_game.c` hunk — within the §14 line ceiling. `doomed-prism validate`
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
  - **(R14)** Gaze left of the dead-zone circle turns the DOOM view left; right
    of it, right; returning gaze inside the circle stops the turn within ~3–5
    ticks (the `RELEASE_EMA_ALPHA` decay — smooth, no abrupt cut; a hide / kill
    is instant via `release_all`).
  - **(R14)** Gaze farther from the circle turns visibly faster than gaze just
    outside it, smoothly, with no step (the curved analog stick, §6).
  - **(R14, finding 3)** Gaze above the circle walks forward; below, backward —
    and, like turn, **faster the farther out**, smoothly. If the C forward path
    fell back to the degraded mode (R14), forward is single-speed but still
    direction-correct — record which.
  - **(R14, finding 1)** Backward is as reachable and as fast as forward (the
    symmetric viewport-sized surface). The ~9 px backward sliver is gone.
  - **(R14, finding 2)** Gaze up-and-to-a-side walks forward while turning, both
    scaled from one vector; sweeping the gaze slowly across that diagonal — and
    across where the old zone boundary used to be — never makes forward stutter,
    slow abruptly, or cut out.
  - A click fires one shot; five fast clicks fire fewer than five shots
    (debounce, `PULSE_HOLD_TICS` hold understood).
  - `F9` fires a shot through the same path; a click and an `F9` within ~30 ms
    fire once (fusion).
  - `Enter` shows the `PAUSED` overlay and pauses; `Enter` again resumes. No
    SDL-window focus was used at any point.
- No `SetParent` anywhere (M2 regression check, still valid).

**Lifecycle checks.**

- Trigger Raven sleep/conceal (or hide the host): the game pauses, the overlay
  shows; on resume it unpauses and no input is stuck — a held turn **or a held
  forward** from before the hide does not persist (R14).
- Kill the PewPew process while the stick is held forward-and-turning: DOOM
  stops turning (no fresh `ev_mouse`, `mousex` decays) **and stops moving
  forward** (the C release-all zeroes `ipc_forwardmove`; in the duty-cycle
  fallback it posts the paired `ev_keyup`) within ~1 tic, and remains running on
  SDL input; no orphan after its window is closed.
- Normal close: `cleanup()` runs stop-tick → release-all → server-close →
  reader-close → engine-stop with no exception; one PID gone; socket path
  removed.
- **(R14) F3 semi-objective artifact.** During the movement checks, the tester
  logs the outgoing `ACTION.value` and `TURN.value` streams (from
  `ActionRouter`, or a debug print) to gitignored `artifacts/milestone-3/` and
  attaches a quick plot of value vs gaze eccentricity — a curve rising 0 →
  `MOVE_MAGNITUDE_SCALE` / `TURN_MAX_MOUSE_DELTA` shows proportionality without
  a frame probe. Freedoom-only, no resolved paths.

**Per-mode evidence.** Raw plus each available optical mode (Night, Day,
Outdoors, Camera): one short local video or two time-separated captures showing
gaze-driven view motion and a fired shot inside the composited viewport, with
the SDL window not focused. Night carries the full dynamic proof; the others may
be lighter, as in the M2 gate. Any clip promoted into tracked `docs/media/` is
Freedoom-only and reviewed frame-by-frame for usernames, paths, and IWAD
identity.

**Hard decision, recorded in the single final field of
`docs/validation/milestone-3a-result.md`.**

- **PASS — IPC input path viable.** The R14 radial stick drives the composited
  DOOM with the SDL window unfocused — proportional turn **and** proportional
  forward/back from one vector, a round dead zone, no forward stutter when the
  gaze sweeps a diagonal, backward as reachable as forward — together with
  click-fire debounce, `F9` spoken-fire fusion, and Enter-pause; every lifecycle
  transition releases held input with no stuck key; one clean PID, no orphan,
  socket removed, no `cleanup()` exception; the M2 framebuffer path still
  advances. Moving feels as controllable as looking around (the R14 acceptance
  bar).
- **PASS (degraded forward) — IPC input path viable, forward single-speed.**
  Everything under PASS holds *except* proportional forward: the C forward path
  fell back to R14's degraded mode, so forward is direction-correct (up / down /
  diagonal from the vector) but a single speed past the dead zone. Turn is
  proportional. Acceptable to close 3a; a follow-up re-opens the `forwardmove`
  mechanism only.
- **FAIL — IPC input path insufficient.** The engine connects and the handshake
  completes, but injected input does not reliably drive gameplay — `ev_mouse`
  turning is unusable, *even single-speed* forward does not reach the game, or
  `D_PostEvent` from the pump races the tic and drops inputs. This opens a
  design task for the R5 keyboard-duty-cycle turn / R14 duty-cycle forward or a
  different injection point — it does not discard the §4 IPC boundary or
  resurrect the zone model.
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
assertion set (§13, incl. the R14 analog-`MOVE` flood)**, and
`milestone-3a-result.md` records a reproducible PASS, PASS (degraded forward),
or FAIL. A FAIL is a valid engineering result: it keeps the §4 IPC boundary and
reopens only the event-injection method; "PASS (degraded forward)" closes 3a
with a follow-up scoped to the `forwardmove` mechanism only.

Milestone 3b is complete when `check_publication_safety.py` and `.gitignore`
cover audio/model files, the §9 licence review is recorded as a pass, the
offline grammar and the real spoken-fire detector work end-to-end with fakes in
CI and on the Windows gate, no model or audio file is tracked, and
`milestone-3b-result.md` records a reproducible PASS or FAIL.
