# Milestone 2: Framebuffer capture integration result

This template records the decision-gate observations only. The **Final decision**
field at the end is the sole authority for this run and begins as
`PENDING — incomplete evidence`. Do not enter private paths, credentials, Raven
source, executable locations, screenshots, or raw terminal output. Keep local
evidence in ignored `artifacts/milestone-2/`.

## Run identification

- Date (UTC): PENDING
- Tester: PENDING
- Repository commit: PENDING on `feature/doomed-prism-m2`

## Environment

- Windows version: PENDING
- Python version: PENDING
- Crispy Doom pinned tag/commit: `crispy-doom-7.1` at `0a022e0ee6c74d9bab173ed9ee5212312e90ce3a`
  (from `crispy-doom.lock`; do not change this field without updating the lock file)
- C compiler version: PENDING
- SDL2 development library version: PENDING
- IWAD name: PENDING — record only when redistribution is permitted; otherwise write `not recorded (redistribution not permitted)`
- IWAD SHA-256: PENDING — record only when redistribution is permitted
- GPU: PENDING
- Display scaling: PENDING (must be 100%)
- DPI-awareness match (Qt host and Crispy Doom): PENDING

### Build and environment adaptation for this run

Record any adaptations made to run this gate (for example, a non-standard Python
environment, a modified build script invocation, or SDL2 library location):

- PENDING

## Launch and interaction

- `python scripts/build_crispy.py`: PENDING (record success/failure and any build output)
- `python scripts/build_crispy.py --check`: PENDING (must pass)
- `doomed-prism validate`: PENDING
- `doomed-prism run-desktop`: PENDING (record the engine startup result and the printed frame segment name)
- Shared-memory segment probe (`FrameReader` test): PENDING (record that the segment exists, magic and version validate, and frame_counter advances over 1–2 seconds)
- Crispy Doom PID at launch: PENDING (record only the numeric PID)
- Native client-size measurement (`GetClientRect`): PENDING (must be **640×480 native client pixels**)
- Viewport geometry: PENDING (must be **(0, 80, 640, 480)**)
- Upper 80-pixel margin uncovered: PENDING (yes/no)
- Lower 80-pixel margin uncovered: PENDING (yes/no)
- Raven home control uncovered: PENDING (yes/no)
- Win32 `SetParent` in window tree: PENDING (must be absent; regression check from Milestone 1)
- Crispy Doom SDL window is independent: PENDING (yes/no — not reparented into Qt host)

## Per-mode app-capture evidence

Mark each observation `yes`, `no`, `not available`, or `not run`. For an
available mode, prove frame updates with two time-separated captures showing
different game states or one short local video. The evidence field may contain
only local filenames, never a path.

| Mode | Available | Live game pixels in app surface | Frames update during play | Viewport `(0, 80, 640, 480)` | App capture includes DOOM frame (not blank/grey) | Dark areas transparent in optical mode | Keypress produces state change in viewport | Local evidence filenames | Non-sensitive observation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Raw | PENDING | PENDING | PENDING | PENDING | PENDING | N/A | PENDING | PENDING | PENDING |
| Night | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Day | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Outdoors | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Camera | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |

## Cleanup evidence

- Clean pre-launch Crispy Doom PID baseline: PENDING (none = met)
- Crispy Doom PIDs added after launch: PENDING (must be exactly one)
- Crispy Doom PID observed before closing Raven Simulator: PENDING (numeric PID)
- Raven Simulator closed normally: PENDING (yes/no)
- Recorded PID absent after close: PENDING (yes = no orphan / no = orphan present)
- Cleanup result: PENDING (`no orphan process` or `orphan process present`)
- `cleanup()` exception: PENDING (`no exception` or record exception type and message; Milestone 1 raised `WinError 87`)
- Non-sensitive cleanup observation: PENDING

If the recorded PID remains present after Raven Simulator closes, or if
`cleanup()` raises an exception, record `orphan process present` or the exception
and set this run's Final decision to `BLOCKED/RETRY — implementation or
environment failure`. Stopping the orphan manually is allowed only for local
cleanup: it cannot turn this run into PASS. Retain the failed observation, then
use a new PID and repeat the entire run with fresh per-mode evidence before
considering another decision.

## Automated verification after manual run

- `python -m pytest -q`: PENDING (record test counts)
- `git diff --check`: PENDING (clean/errors)
- Exact-path documentation staging inspected: PENDING (yes/no)
- `git diff --cached --check`: PENDING (clean/errors)
- `python scripts/check_publication_safety.py --root .` after staging: PENDING (exit code)
- `git status --short`: PENDING (empty after commit / record any remaining changes)

## Final decision

**Final decision:** PENDING — incomplete evidence

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
