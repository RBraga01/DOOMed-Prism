# Milestone 3a: IPC input path integration result

This template records the decision-gate observations only. The **Final decision**
field at the end is the sole authority for this run and begins as
`PENDING — incomplete evidence`. Do not enter private paths, credentials, Raven
source, executable locations, screenshots, or raw terminal output. Record the IPC
address only as the placeholders `<tempdir>/doomed-prism-ipc-<pid>-<token>.sock`
and `127.0.0.1:<port>`, and only its presence/absence plus the port number. Keep
local evidence in ignored `artifacts/milestone-3/`.

## Run identification

- Date (UTC): _not yet run_
- Tester: RBraga01
- Repository commit: _fill in_ on `feature/doomed-prism-m3`

## Environment

- Windows version: _fill in_
- Python version: _fill in_
- Crispy Doom pinned tag/commit: _fill in from `crispy-doom.lock`_
  (do not change this field without updating the lock file)
- C compiler version: _fill in_
- SDL2 development library version: _fill in_
- Freedoom IWAD name: _fill in, or_ `not recorded (redistribution not permitted)`
- Freedoom IWAD SHA-256: _fill in, or_ `not recorded (redistribution not permitted)`
- GPU: _fill in_
- Display scaling: 100% (system DPI 96) — confirm
- No commercial IWAD identity is recorded anywhere in this document.

### Build and environment adaptation for this run

- Record any local toolchain setup (MSYS2 / UCRT64, SDL2 dev packages, DLL
  co-location) without private paths, exactly as the Milestone 2 result did.
- Record any non-blocking system dialogs or antivirus interactions observed, and
  whether gameplay or the shared-memory export was affected.

## Launch and interaction

- `python scripts/build_crispy.py`: _pass / fail_ — built `crispy-doom.exe` from
  the pinned tag plus the committed patch series (`crispy-doom-fb-export.diff`
  then `crispy-doom-ipc-input.diff`)
- `python scripts/build_crispy.py --check`: _pass / fail_ (exit code: _fill in_;
  restore + real `apply p1` + `apply --check p2`)
- `git apply --stat patches/crispy-doom-ipc-input.diff`: _diffstat summary_ —
  confirm it adds only `src/i_ipc_input.c` / `src/i_ipc_input.h` plus small hunks
  in `src/d_loop.c`, `src/i_video.c`, `src/CMakeLists.txt`, within the
  diff-minimality line ceiling (changed lines: _fill in_)
- `doomed-prism validate`: _pass / fail_ (exit 0 expected; both runtime paths valid)
- `python -m pytest -q`: _fill in_ (all green expected)
- `python scripts/check_publication_safety.py --root .`: _exit code_ (0 expected)
- `python scripts/check_publication_safety.py --root . --history`: _exit code_ (0 expected)
- Gate environment set: `DOOMED_PRISM_WARP="1 1"`, `DOOMED_PRISM_DEBUG_FIRE=1` — confirm
- `doomed-prism run-desktop`: _fill in_ (Raven `RAVEN APP READY LAUNCH SIGNAL` observed?)
- Clean Crispy Doom PID baseline before launch: _none / not clean_
- New Crispy Doom PID after launch (`$doomPid`, numeric only): _fill in_ (exactly one expected)
- IPC socket present while running: _yes / no_ — POSIX placeholder
  `<tempdir>/doomed-prism-ipc-<pid>-<token>.sock` present, **or** Windows
  `127.0.0.1:<port>` listening (port: _fill in_; record presence and port only)
- IPC socket gone after close: _yes / no_
- `FrameReader` probe — `frame_counter` advancing while running: _yes / no_
  (M2 framebuffer path unbroken)
- Win32 `SetParent` in window tree: _absent / present_ (absent expected;
  `GetParent=0`, `WS_CHILD=False`, `WS_POPUP=False`)
- Crispy Doom SDL window independent and unfocused for the whole run: _yes / no_

## Objective-check results

Mark each `yes`, `no`, `not available`, or `not run`, with a short non-sensitive
observation. All view/movement checks are performed with **Crispy's SDL window
minimised or behind the Raven Simulator, and unfocused, for the whole run**.

| Check | Result | Non-sensitive observation |
| --- | --- | --- |
| Exactly one new crispy-doom PID | _fill in_ | |
| IPC socket present while running / gone after close | _fill in_ | placeholder address + port only |
| `FrameReader` `frame_counter` advancing (M2 path unbroken) | _fill in_ | |
| Left turn band turns view left; right band turns right | _fill in_ | |
| Return to dead zone stops the turn within ~2 ticks | _fill in_ | |
| Gaze farther from the dead zone turns faster (progressive) | _fill in_ | |
| Upper band walks forward; lower band walks backward | _fill in_ | |
| Upper corner walks forward while turning | _fill in_ | |
| One click fires one shot | _fill in_ | |
| Five fast clicks fire fewer than five shots (debounce) | _fill in_ | |
| `F9` fires a shot through the same path | _fill in_ | |
| Click + `F9` within ~30 ms fire once (fusion) | _fill in_ | |
| `Enter` shows the `PAUSED` overlay and pauses; `Enter` resumes | _fill in_ | |
| No SDL-window focus used at any point | _fill in_ | |
| No `SetParent` anywhere in the window tree | _fill in_ | |

## Per-mode evidence

Mark each observation `yes`, `no`, `not available`, or `not run`. For an available
mode, prove gaze-driven view motion **and** a fired shot inside the composited
viewport with the SDL window unfocused, using one short local Freedoom-only video
or two time-separated captures. The evidence field may contain only local
filenames, never a path.

| Mode | Available | Gaze-driven view motion in composited viewport | Fired shot visible in composited viewport | SDL window unfocused throughout | Local evidence filenames | Non-sensitive observation |
| --- | --- | --- | --- | --- | --- | --- |
| Raw | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in / not captured_ | |
| Night | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in / not captured_ | full dynamic proof expected here |
| Day | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in / not captured_ | |
| Outdoors | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in / not captured_ | |
| Camera | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in / not captured_ | |

Note on evidence depth: Night must carry full dynamic (two-or-more different game
states) proof — gaze steering, progressive turn, a fired shot, and Enter-pause.
Raw, Day, Outdoors, and Camera may be lighter, as in the Milestone 2 gate, since
all modes share one paint and capture pipeline. Any clip promoted into tracked
`docs/media/` is Freedoom-only and was reviewed frame-by-frame for usernames,
paths, and IWAD identity.

## Lifecycle-check results

Every transition must release all held inputs — no stuck key, no held turn
persisting — and leave no orphan process.

| Transition | Held input released, no stuck key | No orphan / clean PID | `cleanup()` exception | Non-sensitive observation |
| --- | --- | --- | --- | --- |
| Sleep / conceal (or hide host) → pause + overlay; resume → unpause | _fill in_ | _n/a_ | _n/a_ | held turn from before the hide must not persist |
| Kill PewPew while a turn is held → DOOM stops turning, keeps running on SDL | _fill in_ | _fill in_ | _n/a_ | no orphan after its window is closed |
| Normal close → `cleanup()` stop-tick → release-all → server-close → reader-close → engine-stop | _fill in_ | _fill in_ | _none expected_ | one PID gone; socket path removed |

If the recorded PID remains present after PewPew closes, or if `cleanup()` raises
an exception, record `orphan process present` or the exception type and message
and set this run's Final decision to `BLOCKED/RETRY — implementation or
environment failure`. Stopping an orphan manually is allowed only for local
cleanup: it cannot turn this run into PASS. Retain the failed observation, then
use a new PID and repeat the entire run with fresh per-mode evidence before
considering another decision.

## Automated verification after manual run

- `python -m pytest -q`: _fill in_
- `git diff --check`: _clean / errors_
- Exact-path documentation staging inspected (`git diff --cached --name-status`
  lists only the two `milestone-3a-*.md` paths): _yes / no_
- `git diff --cached --check`: _clean / errors_
- `python scripts/check_publication_safety.py --root .` after staging: _exit code_
- `python scripts/check_publication_safety.py --root . --history` after staging: _exit code_
- `git status --short`: _empty / not empty_ after the commit

## Final decision

**Final decision:** PENDING — incomplete evidence

_This run has not been performed yet. Replace this line with exactly one of the
four decisions below once the checklist is complete._

Use only one of these decisions after completing the checklist:

- **PASS — IPC input path viable.** Gaze movement and progressive turn,
  click-fire with debounce, spoken-fire fusion via the `F9` source, and
  Enter-pause all drive the composited DOOM with the SDL window unfocused; every
  lifecycle transition releases held input with no stuck key; one clean PID, no
  orphan, socket removed, no `cleanup()` exception; the M2 framebuffer path still
  advances.
- **FAIL — IPC input path insufficient.** The engine connects and the handshake
  completes, but injected events do not reliably drive gameplay (for example
  `ev_mouse` turning is unusable, or `D_PostEvent` from the pump races the tic and
  drops inputs). This opens a design task for the R5 keyboard-duty-cycle turn or a
  different injection point — it does not discard the §4 IPC boundary.
- **BLOCKED/RETRY — implementation or environment failure.** Build, launch,
  connection, handshake, geometry, lifecycle, or evidence collection fails. Fix
  the named issue and repeat with a fresh PID. Does not select an injection
  design.
- **PENDING — incomplete evidence.** Evidence incomplete or a named optical mode
  unavailable without a documented reason. Never a pass.
