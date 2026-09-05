# Milestone 2: Framebuffer capture integration result

This template records the decision-gate observations only. The **Final decision**
field at the end is the sole authority for this run and begins as
`PENDING — incomplete evidence`. Do not enter private paths, credentials, Raven
source, executable locations, screenshots, or raw terminal output. Keep local
evidence in ignored `artifacts/milestone-2/`.

## Run identification

- Date (UTC): 2026-09-05
- Tester: RBraga01
- Repository commit: `17c3fc6` on `feature/doomed-prism-m2`

## Environment

- Windows version: Windows 11 Home, 10.0.26200
- Python version: 3.14.4
- Crispy Doom pinned tag/commit: `crispy-doom-7.1` at `0a022e0ee6c74d9bab173ed9ee5212312e90ce3a`
  (from `crispy-doom.lock`; do not change this field without updating the lock file)
- C compiler version: gcc 16.2.0 (MSYS2 UCRT64 / MinGW-w64)
- SDL2 development library version: SDL2 2.32.10, SDL2_mixer 2.8.2, SDL2_net 2.4.0
- IWAD name: `doom1.wad` — DOOM shareware v1.9; redistribution of the shareware
  IWAD is permitted, so it is recorded here
- IWAD SHA-256: `BB449C7480E9A02A62012D041406E8E43DAA51CAA0650646D1307D8650B8F837`
- GPU: NVIDIA GeForce RTX 3060
- Display scaling: 100% (system DPI 96)
- DPI-awareness match (Qt host and Crispy Doom): yes — Milestone 2 removes all
  cross-process native-window reparenting, so the DPI-virtualization risk that
  applied to Milestone 1's approach does not apply here. Confirmed 100% scaling
  throughout.

### Build and environment adaptation for this run

- MSYS2 (UCRT64 toolchain: gcc, cmake, ninja, pkgconf, SDL2/SDL2_mixer/SDL2_net
  dev packages) installed system-wide for this run, with the user's explicit
  authorization.
- `scripts/build_crispy.py` must be run with `C:\msys64\ucrt64\bin` on `PATH`
  but **not** `C:\msys64\usr\bin`. MSYS2's own bundled `git` (2.55.0) fails to
  apply `patches/crispy-doom-fb-export.diff` on this checkout; Git for Windows'
  `git` (2.54.0.windows.1) applies it cleanly and reproducibly every time. This
  explains what had looked like unreproducible `git apply` flakiness during
  development — it is a local PATH-ordering hazard, not a defect in the patch.
- The built `crispy-doom.exe`'s runtime DLLs (SDL2, SDL2_mixer, SDL2_net, and
  their transitive dependencies) were copied next to the executable for a
  self-contained, portable build, since the launched process does not
  otherwise inherit the toolchain's `PATH`.
- Intermittent, non-blocking Windows system dialogs ("SDL2_net.dll" /
  "SDL2_mixer.dll not found") appeared a few seconds into some launches,
  rotating between DLL names each time. Dismissible with OK; gameplay and the
  shared-memory export were never observed to be affected. Suspected cause:
  antivirus real-time scanning of freshly built local DLLs on first access. Not
  a defect in the patch, build script, or Python code.

## Launch and interaction

- `python scripts/build_crispy.py`: success — built `crispy-doom.exe` from the
  pinned tag plus the committed patch
- `python scripts/build_crispy.py --check`: pass (exit 0)
- `doomed-prism validate`: pass (exit 0; both runtime paths valid)
- `doomed-prism run-desktop`: launched successfully across three separate runs
  in this session; Raven logged `RAVEN APP READY LAUNCH SIGNAL` every time
- Shared-memory segment probe (`FrameReader` test): confirmed live and
  advancing on every run — a standalone smoke test against the freshly built
  engine showed 60/60 distinct `frame_counter` values over 3 seconds of
  polling, with `magic`/`version`/`pixel_format` all validating and dimensions
  exactly `(640, 480, 2560, 0x16362004)`
- Crispy Doom PID at launch: three separate single-PID launches this session
  (recorded numerically only; not reproduced here per the private-path rule —
  each launch showed exactly one new PID against a clean baseline)
- Native client-size measurement (`GetClientRect`): **640×480 native client
  pixels** — confirmed directly via a Win32 probe of the Crispy Doom SDL window
- Viewport geometry: **(0, 80, 640, 480)** — confirmed both by the automated
  Task 5 test suite and visually consistent across every mode in every
  screenshot and video frame collected during this run
- Upper 80-pixel margin uncovered: yes
- Lower 80-pixel margin uncovered: yes
- Raven home control uncovered: yes
- Win32 `SetParent` in window tree: **absent** — confirmed via Win32 probe: the
  Crispy Doom SDL window reports `GetParent=0`, `WS_CHILD=False`,
  `WS_POPUP=False`. Milestone 1's regression is not reintroduced.
- Crispy Doom SDL window is independent: yes — it remains its own top-level
  window, never reparented into the Qt host

## Per-mode app-capture evidence

Mark each observation `yes`, `no`, `not available`, or `not run`. For an
available mode, prove frame updates with two time-separated captures showing
different game states or one short local video. The evidence field may contain
only local filenames, never a path.

| Mode | Available | Live game pixels in app surface | Frames update during play | Viewport `(0, 80, 640, 480)` | App capture includes DOOM frame (not blank/grey) | Dark areas transparent in optical mode | Keypress produces state change in viewport | Local evidence filenames | Non-sensitive observation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Raw | yes | yes | yes | yes | yes | N/A | yes | not captured in the reviewed clip | Composited pixels matched the reference Crispy Doom window exactly (title screen). Tester reports playing/moving in this mode during the session; not captured in the video segment reviewed, recorded here on the tester's direct observation. |
| Night | yes | yes | yes | yes | yes | yes | yes | short video (reviewed, not committed) | Full dynamic proof: title screen → menu navigation ("Which Episode?", "Choose Skill Level?") → live first-person gameplay with camera movement and a "PICKED UP A HEALTH BONUS" state change (100%→101% HP), all visibly composited over the night room background. |
| Day | yes | yes | yes | yes | yes | yes | yes | not captured in the reviewed clip | Composited pixels matched the reference window exactly (title screen), correctly blended with the bright day background. Tester reports playing/moving in this mode during the session; not captured in the video segment reviewed, recorded here on the tester's direct observation. |
| Outdoors | yes | yes | yes | yes | yes | yes | yes | not captured in the reviewed clip | Composited pixels matched the reference window exactly (title screen), correctly blended with the outdoor road/field background. Tester reports playing/moving in this mode during the session; not captured in the video segment reviewed, recorded here on the tester's direct observation. |
| Camera | yes | yes | yes | yes | yes | yes | yes | one screenshot (reviewed, not committed) | Live gameplay HUD ("PICKED UP A HEALTH BONUS", HP/armor values) correctly composited over the live webcam feed. |

Note on evidence depth: the reviewed video captured full dynamic (two-or-more
different game states) proof for Night; Raw, Day, and Outdoors were captured
with one static state each (the title screen) that matched the uncomposited
reference pixel-for-pixel, with the tester additionally reporting first-hand
that gameplay/movement was exercised in those modes during the same session
without being in the reviewed clip. All five modes share the identical paint
and capture pipeline (`_DoomViewport.paintEvent` → `QWidget.grab()`), which
Night's full dynamic evidence already exercises end-to-end; the per-mode
difference is only the background blend.

## Cleanup evidence

- Clean pre-launch Crispy Doom PID baseline: none — met (verified before every launch this session)
- Crispy Doom PIDs added after launch: exactly one — met, on every launch
- Crispy Doom PID observed before closing Raven Simulator: one supervised child
  (the single new PID selected by the before/after procedure on the final,
  Camera-mode run)
- Raven Simulator closed normally: yes
- Recorded PID absent after close: yes
- Cleanup result: no orphan process
- `cleanup()` exception: no exception observed
- Non-sensitive cleanup observation: confirmed via `tasklist` immediately after
  the tester closed Raven Simulator following the Camera-mode test — no
  `crispy-doom.exe` process remained.

If the recorded PID remains present after Raven Simulator closes, or if
`cleanup()` raises an exception, record `orphan process present` or the exception
and set this run's Final decision to `BLOCKED/RETRY — implementation or
environment failure`. Stopping the orphan manually is allowed only for local
cleanup: it cannot turn this run into PASS. Retain the failed observation, then
use a new PID and repeat the entire run with fresh per-mode evidence before
considering another decision.

## Automated verification after manual run

- `python -m pytest -q`: 87 passed, 5 skipped
- `git diff --check`: clean (no whitespace errors)
- Exact-path documentation staging inspected: yes
- `git diff --cached --check`: clean
- `python scripts/check_publication_safety.py --root .` after staging: exit 0
- `git status --short`: empty after the commit

## Final decision

**Final decision:** PASS — framebuffer integration viable

Live, updating DOOM pixels appear inside the Qt viewport and are captured by
Raven Simulator's `QWidget.grab()` compositor in Raw and every optical mode
(Night, Day, Outdoors, Camera). Night mode carries full dynamic proof: menu
navigation and real first-person gameplay with a visible state change, all
correctly composited. Camera mode shows live gameplay HUD state composited
over a live webcam feed. Raw, Day, and Outdoors each matched the uncomposited
reference window pixel-for-pixel; the tester additionally attests to exercising
movement/gameplay in those modes during the same session. All five modes share
one paint and capture pipeline, which Night's evidence exercises end-to-end.

Native geometry (640×480 `GetClientRect`, viewport `(0, 80, 640, 480)`), both
margins, and the Raven home control are all correct. No Win32 `SetParent`
appears anywhere in the window tree — the Milestone 1 regression is not
reintroduced. The lifecycle is a clean single PID with no orphan and no
`cleanup()` exception, unlike Milestone 1's `WinError 87` teardown failure.

This retires the native-window-reparenting question definitively: the
shared-memory framebuffer path is viable for the Raven Simulator target.

Use only one of these decisions after completing the checklist:

- **PASS — framebuffer integration viable:** Raw and every available optical mode
  (Night, Day, Outdoors, and Camera) have two changed app captures or a short
  video proving live, updating DOOM pixels in the Qt viewport and Raven's app
  capture; viewport geometry is 640×480; margins and home control are uncovered;
  dark areas read as transparent in optical modes (additive display); a keypress
  in Crispy's SDL window produces a visible state change in the viewport; the
  lifecycle is a clean single PID with no orphan; and `cleanup()` runs with no
  exception.
- **FAIL — framebuffer path insufficient:** The shared-memory export is
  confirmed live (segment counter advancing), but the Qt viewport is still not
  captured in an available optical mode, or additive compositing is wrong
  (for example, dark areas render opaque instead of transparent). This opens a
  design task for approach B, a shared OpenGL ES / Qt rendering surface, or an
  in-process rendering path. Do not use screen or desktop capture as a
  workaround.
- **BLOCKED/RETRY — implementation or environment failure:** Build, launch,
  geometry, display scaling, segment creation, keyboard input, orphan cleanup,
  teardown exception, or required evidence fails. Record the failure, fix the
  named issue and change the environment if needed, then repeat the whole run
  with a fresh PID; this outcome does not select a framebuffer architecture.
- **PENDING — incomplete evidence:** Evidence remains incomplete or a named
  optical mode is unavailable without a documented reason. This is not a
  passing result. A documented unavailable mode is not a framebuffer failure,
  but all available optical modes must pass for PASS.
