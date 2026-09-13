# Milestone 3a: IPC input path integration result

This document records the decision-gate observations. The **Final decision** field
at the end is the sole authority for this run. Do not enter private paths,
credentials, Raven source, executable locations, screenshots, or raw terminal
output. The IPC address is recorded only as the placeholders
`<tempdir>/doomed-prism-ipc-<pid>-<token>.sock` and `127.0.0.1:<port>`, and only
its presence/absence plus the port number. Local evidence (captures, the numeric
`$doomPid`, the listening port, GPU model, `ACTION.value` / `TURN.value` streams)
is kept in ignored `artifacts/milestone-3/` and is not transcribed here.

## Run identification

- Date (UTC): 2026-09-08
- Tester: RBraga01
- Repository commit: engine build under test `a90febf` on `feature/doomed-prism-m3`
  (`IPC_TURN_CLAMP = 160`). The branch head then advanced to `a8fe89e` — a
  CI-only merge of the pinned-Actions bump to Node 24 (`.github/workflows/ci.yml`
  only); no runtime or behaviour change.
- Manual interaction evidence was gathered across the R14 gate iteration on
  2026-09-07/08 on Windows with the Raven Simulator, with Crispy's SDL window
  minimised or behind the simulator and unfocused for the whole run.
- **Scripted re-check, 2026-09-12** (Claude, at RBraga01's direction): the four
  rows marked "Scripted" were re-verified directly against the same built
  engine and the real pewpew code, not through Raven's own UI (not scriptable
  here). Everything else in this document is RBraga01's direct observation in
  the Raven Simulator.

## Environment

- Windows version: Windows 11, build 10.0.26200
- Python version: 3.14 (local runtime); the CI matrix pins 3.12
- Crispy Doom pinned tag/commit: `crispy-doom-7.1` @
  `0a022e0ee6c74d9bab173ed9ee5212312e90ce3a` (from `crispy-doom.lock`;
  `tarball_sha256 = f0eb02afb81780165ddc81583ed5648cbee8b3205bcc27e181b3f61eb26f8416`)
- C compiler version: gcc 16.2.0 (MSYS2 UCRT64)
- SDL2 development library version: 2.32.10 (MSYS2 UCRT64)
- Freedoom IWAD name: `freedoom1.wad` (Freedoom Phase 1, 0.13.0 — freely
  redistributable, so its identity is recorded)
- Freedoom IWAD SHA-256:
  `7323bcc168c5a45ff10749b339960e98314740a734c30d4b9f3337001f9e703d`
- GPU: recorded in local evidence only
- Display scaling: 100% (system DPI 96) — confirmed
- No commercial IWAD identity is recorded anywhere in this document.

### Build and environment adaptation for this run

- Crispy Doom is built from the pinned tag with the ordered patch series applied
  cumulatively on disk (`crispy-doom-fb-export.diff` then
  `crispy-doom-ipc-input.diff`) under an MSYS2 UCRT64 toolchain (gcc + SDL2 dev
  packages, SDL2 runtime DLL co-located with the built executable), as in the
  Milestone 2 result. Git-for-Windows `git` is used for `git apply`.
- No blocking system dialogs or antivirus interactions affected gameplay or the
  shared-memory export during the run.

## Launch and interaction

- `python scripts/build_crispy.py`: pass — built `crispy-doom.exe` from the pinned
  tag plus the committed patch series
- `python scripts/build_crispy.py --check`: pass (exit code 0; restore + real
  `apply p1` + `apply --check p2`). The squelched whitespace warnings are the
  pre-existing `crispy-doom-fb-export.diff` advisories, not new.
- `git apply --stat patches/crispy-doom-ipc-input.diff`: 6 files, 419 insertions —
  `src/i_ipc_input.c` (+361), `src/i_ipc_input.h` (+30) plus small hunks in
  `src/d_loop.c` (+9), `src/i_video.c` (+8), `src/CMakeLists.txt` (+5), and one
  clearly-marked hunk in `src/doom/g_game.c` (+6, the R14 `forwardmove` fold).
  Only the allowed files; within the diff-minimality ceiling.
- `doomed-prism validate`: pass (exit 0; both runtime paths valid)
- `python -m pytest -q`: 208 passed, 6 skipped
- `python scripts/check_publication_safety.py --root .`: exit 0
- `python scripts/check_publication_safety.py --root . --history`: exit 0
- Gate environment set: `DOOMED_PRISM_WARP="1 1"`, `DOOMED_PRISM_DEBUG_FIRE=1` — confirmed
- `doomed-prism run-desktop`: pass — Raven `RAVEN APP READY LAUNCH SIGNAL` observed
- Clean Crispy Doom PID baseline before launch: none (clean baseline)
- New Crispy Doom PID after launch: exactly one (numeric value in local evidence)
- IPC socket present while running: yes — Windows `127.0.0.1:<port>` listening,
  owned by the PewPew process (presence and port recorded in local evidence)
- IPC socket gone after close: yes — listening port released
- `FrameReader` probe — `frame_counter` advancing while running: yes. Scripted:
  a standalone `DoomProcess` + `FrameReader` against the same binary —
  `frame_counter` 4 → 65 over 2s, strictly increasing.
- Win32 `SetParent` in window tree: absent. Scripted: `EnumWindows` /
  `GetParent` / `GetWindowLongPtr` on the live `crispy-doom.exe` — `GetParent =
  0`, not `WS_CHILD`, not `WS_POPUP`.
- Crispy Doom SDL window independent and unfocused for the whole run: yes

## Objective-check results

All view/movement checks were performed with **Crispy's SDL window minimised or
behind the Raven Simulator, and unfocused, for the whole run**.

| Check | Result | Non-sensitive observation |
| --- | --- | --- |
| Exactly one new crispy-doom PID | yes | one supervised child against a clean baseline |
| IPC socket present while running / gone after close | yes / yes | Windows `127.0.0.1:<port>`; presence + port in local evidence only |
| `FrameReader` `frame_counter` advancing (M2 path unbroken) | yes | composited view animates in all five modes; scripted re-check (see Launch and interaction) |
| Turn: left of the dead-zone circle turns left; right turns right; stop within ~3–5 ticks | yes | returning gaze inside the circle stops the turn smoothly, no abrupt cut |
| Turn rate rises with distance from the circle, smoothly, no step | yes | curved analog response; full deflection reaches DOOM's run-turn rate |
| Forward/back proportional to gaze eccentricity (or degraded single-speed — say which) | yes — **proportional forward** | speed rises with eccentricity; noticeable acceleration toward the edge |
| Backward as reachable and as fast as forward (no ~9 px sliver) | yes | radial model is symmetric; no dead sliver below centre |
| Diagonal sweep never makes forward stutter or cut out | yes | forward + turn come from **one vector**; sweeping the diagonal stays smooth |
| One click fires one shot | yes | |
| Five fast clicks fire fewer than five shots (debounce) | yes | `PULSE_HOLD_TICS` hold understood |
| `B` fires a shot through the same path | yes | debug spoken-fire source, `DOOMED_PRISM_DEBUG_FIRE=1` |
| Click + `B` within ~30 ms fire once (fusion) | yes | single shot on the fused edge |
| `P` (or `Enter`) shows the `PAUSED` overlay and pauses; press again to resume | yes | neither key closes the simulator (the `QApplication`-level `ShortcutOverride` fix) |
| No SDL-window focus used at any point | yes | Raven Simulator held focus throughout |
| No `SetParent` anywhere in the window tree | yes | independent top-level SDL window; scripted re-check (see Launch and interaction) |

## Per-mode evidence

Gaze-driven view motion **and** a fired shot were shown inside the composited
viewport, with the SDL window unfocused, for Raw and every available optical
mode. Evidence files are retained under ignored `artifacts/milestone-3/`; only
their existence is recorded here.

| Mode | Available | Gaze-driven view motion in composited viewport | Fired shot visible in composited viewport | SDL window unfocused throughout | Local evidence | Non-sensitive observation |
| --- | --- | --- | --- | --- | --- | --- |
| Raw | yes | yes | yes | yes | captured (local) | |
| Night | yes | yes | yes | yes | captured (local) | full dynamic proof — gaze steering the stick, proportional turn and forward, a fired shot, and Enter-pause in one capture |
| Day | yes | yes | yes | yes | captured (local) | |
| Outdoors | yes | yes | yes | yes | captured (local) | |
| Camera | yes | yes | yes | yes | captured (local) | |

Note on evidence depth: Night carries full dynamic (two-or-more different game
states) proof — gaze steering the radial stick, proportional turn and forward, a
fired shot, and Enter-pause. Raw, Day, Outdoors, and Camera are lighter, as in
the Milestone 2 gate, since all modes share one paint and capture pipeline. No
clip was promoted into tracked `docs/media/`; any that were would be
Freedoom-only and reviewed frame-by-frame for usernames, paths, and IWAD
identity.

## Lifecycle-check results

Every transition released all held inputs — no stuck key, no held turn
persisting — and left no orphan process.

| Transition | Held input released, no stuck key | No orphan / clean PID | `cleanup()` exception | Non-sensitive observation |
| --- | --- | --- | --- | --- |
| Sleep / conceal (or hide host) → pause + overlay; resume → unpause | yes | _n/a_ | _n/a_ | Scripted: drove the real `DoomHostWidget` directly via `.hide()`/`.show()` (the checklist's own alternative to Raven's conceal gesture). `router._held` was empty immediately after hide and stayed empty through resume with gaze moved off-corner; view-change rate 31 → 2 → 6 — no residual turn. Overlay-visible isn't observable this way (Qt hides all children of a hidden parent) but is already confirmed by the `P`/`Enter` test above. |
| Kill PewPew while the stick is held forward-and-turning → DOOM stops turning **and stops moving forward**, keeps running on SDL | yes | yes | _n/a_ | Scripted: a standalone IPC holder flooded full-deflection forward+turn, then was hard-killed. View-change rate dropped 43 → 9 while `frame_counter` kept advancing; `crispy-doom.exe` survived. Manual cleanup needed `taskkill /F` afterward — DOOM's own quit prompt needs a keypress this probe didn't send, not an M3a defect. |
| Normal close → `cleanup()` stop-tick → release-all → server-close → reader-close → engine-stop | yes | yes | none | one PID gone; listening port released; independently reconfirmed — zero project processes and no listening IPC port after close |

## Automated verification after manual run

- `python -m pytest -q`: 208 passed, 6 skipped
- `git diff --check`: clean
- Exact-path documentation staging inspected (`git diff --cached --name-status`
  lists only the two `milestone-3a-*.md` paths): yes
- `git diff --cached --check`: clean
- `python scripts/check_publication_safety.py --root .` after staging: exit 0
- `python scripts/check_publication_safety.py --root . --history` after staging: exit 0
- `git status --short`: empty after the commit

## Final decision

**Final decision:** PASS — IPC input path viable

The R14 radial stick drives the composited DOOM with the SDL window unfocused —
**proportional forward** and proportional turn from **one vector**, a round
dead-zone circle, no forward stutter when the gaze sweeps a **diagonal**,
**backward as reachable as forward** — together with click-fire debounce, `B`
spoken-fire fusion, and Enter-pause. Every lifecycle transition releases held
input with no stuck key; one clean PID, no orphan, socket removed, no
`cleanup()` exception; the M2 framebuffer path still advances. Moving feels as
controllable as looking around (the R14 acceptance bar).

The five decisions this field may hold:

- **PASS — IPC input path viable.** The R14 radial stick drives the composited
  DOOM with the SDL window unfocused — proportional turn **and**
  proportional forward/back from one vector, a round dead zone, no forward
  stutter when the gaze sweeps a diagonal, backward as reachable as forward —
  together with click-fire debounce, `B` spoken-fire fusion, and Enter-pause;
  every lifecycle transition releases held input with no stuck key; one clean
  PID, no orphan, socket removed, no `cleanup()` exception; the M2 framebuffer
  path still advances. Moving feels as controllable as looking around (the R14
  acceptance bar).
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
