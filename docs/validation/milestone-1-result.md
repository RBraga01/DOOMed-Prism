# Milestone 1: Raven Simulator embedding result

This template records the decision-gate observations only. The **Final decision**
field at the end is the sole authority for this run and begins as
`PENDING — manual Raven Simulator run required`. Do not enter private paths,
credentials, Raven source, executable locations, screenshots, or raw terminal
output. Keep local evidence in ignored `artifacts/milestone-1/`.

## Run identification

- Date (UTC): 2026-09-04
- Tester: RBraga01
- Repository commit: `93f7ee0` on `feature/doomed-prism-m1` (this run added two
  launch fixes in that commit; the result document is committed on top)

## Environment

- Windows version: Windows 11 Home, 10.0.26200
- Python version: 3.14.4
- Raven Framework version/commit: 1.0.4 at `b1a38f4` (pristine checkout; local
  patches stashed for the run)
- Crispy Doom version/commit: 7.1.0 (`crispy-doom-7.1` win64 release build)
- IWAD name: `doom1.wad` — DOOM shareware v1.9; redistribution of the shareware
  IWAD is permitted, so it is recorded here
- IWAD SHA-256: `BB449C7480E9A02A62012D041406E8E43DAA51CAA0650646D1307D8650B8F837`
- GPU: NVIDIA GeForce RTX 3060
- Display scaling: 100% (system DPI 96)
- DPI-awareness match (Raven, Qt host, and Crispy Doom): yes — every measured
  window rectangle is an exact integer at 100% scaling; no DPI virtualization
  observed

### Environment adaptation for this run

- No standalone install of Raven Framework or a Python 3.12 runtime exists on
  this host. Raven Framework 1.0.4 is installed editable only in its own
  virtual environment (Python 3.14.4, PySide6 6.11.2). `doomed-prism` was
  installed with `pip install -e .` into that same environment, and
  `pytest-qt>=4.4,<5` was added there so the full suite runs. The fixed
  viewport, engine, and adapter code were unchanged by this.

## Launch and interaction

- `python -m pip install -e ".[dev,raven]"`: adapted — `pip install -e .` into
  the separately installed Raven Framework environment (see adaptation note).
  Result: success.
- `doomed-prism validate`: pass (exit 0; both runtime paths valid)
- `doomed-prism run-desktop`: launches only after two launch fixes committed in
  `93f7ee0` (see below). Raven emitted `RAVEN APP READY LAUNCH SIGNAL`; exactly
  one Crispy Doom child process started.
- Native client-size measurement (`GetClientRect`): **640×480 native client
  pixels** — pass
- Keyboard-playable Crispy Doom: **not verifiable** — no game pixels were
  visible in any simulator mode; synthetic key messages posted to the SDL
  window produced no visible change
- Viewport geometry: **(0, 80, 640, 480)** — pass (SDL child at screen
  `(40, 161)`; the 640×640 host surface at screen `(40, 81)`)
- Upper 80-pixel margin uncovered: yes
- Lower 80-pixel margin uncovered: yes
- Raven home control uncovered: yes

### Launch fixes made during this run (commit `93f7ee0`)

1. `raven_app.py` imported a non-existent top-level `core` namespace
   (`from core.raven_app import RavenApp`). Against Raven Framework 1.0.4,
   `core` is a subpackage that uses relative imports, so the import failed.
   Changed to the documented public API `from raven_framework import RavenApp,
   RunApp`.
2. `raven_app.py` called `RavenApp.add_widget(...)`, which does not exist.
   `RavenApp` extends `Container`; changed to `self.app.add(self.host_widget,
   0, 0)`.

Both were launch-blocking. `tests/test_raven_app.py` was updated to match.

## Per-mode app-capture evidence

Mark each observation `yes`, `no`, `not available`, or `not run`. For an
available mode, prove frame updates with two time-separated captures showing
different game states or one short local video. The evidence field may contain
only local filenames, never a path.

| Mode | Available | Live game pixels in app surface | Frames update during play | Viewport `(0, 80, 640, 480)` | App capture includes SDL child (not blank) | Local evidence filenames | Non-sensitive observation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Raw | yes | no | no | yes | no | not captured | App surface shows only the flat Qt content fill (`#282936`); the reparented SDL child is not drawn |
| Night | yes | no | no | not applicable | no | not captured | Only the background environment video is shown; app surface fully transparent |
| Day | yes | no | no | not applicable | no | not captured | Only the background environment video is shown |
| Outdoors | yes | no | no | not applicable | no | not captured | Only the background environment video is shown |
| Camera | not run | not run | not run | not run | not run | not captured | Not separately exercised; Raw and three optical modes were already conclusive |

No evidence files were captured: there were no live child pixels to capture in
any mode, and the checklist forbids substituting desktop or screen capture.

## Cleanup evidence

- Clean pre-launch Crispy Doom PID baseline: none — met
- Crispy Doom PIDs added after launch: exactly one — met
- Crispy Doom PID observed before closing Raven Simulator: one supervised child
  (the single new PID selected by the before/after procedure)
- Raven Simulator closed normally: yes (`WM_CLOSE` posted to the root window)
- Recorded PID absent after close: yes
- Cleanup result: no orphan process
- Non-sensitive cleanup observation: the supervised Crispy Doom child
  terminated when Raven Simulator closed. Teardown itself raised:
  `host_widget.cleanup()` → `EmbeddedWindow.restore()` → `SetParent` on the
  already-destroyed child window → `WinError 87`. No orphan resulted, but the
  reversible-restore path is not ordered safely against engine stop.

If the recorded PID remains present after Raven Simulator closes, record
`orphan process present` and set this run's Final decision to
`BLOCKED/RETRY — implementation or environment failure`. Stopping the orphan
manually is allowed only for local cleanup: it cannot turn this run into PASS.
Retain the failed observation, then use a new PID and repeat the entire run with
fresh per-mode evidence before considering another decision.

## Automated verification after manual run

- `python -m pytest -q`: 85 passed, 4 skipped
- `git diff --check`: clean (no whitespace errors)
- Exact-path documentation staging inspected: yes
- `git diff --cached --check`: clean
- `python scripts/check_publication_safety.py --root .` after staging: exit 0
- `git status --short`: empty after the commit

## Final decision

**Final decision:** BLOCKED/RETRY — implementation or environment failure

The embedded Crispy Doom native window is created, sized to 640×480 native
client pixels, positioned at viewport `(0, 80, 640, 480)`, and reparented into
the Qt viewport (`WS_CHILD` set, `WS_POPUP` removed, parent = the Raven
process window), with matching DPI-awareness at 100% scaling and a clean
single-PID lifecycle that leaves no orphan. Those objective checks pass.

No live game pixels appear in any Raven Simulator mode, Raw included. Raven
Framework 1.0.4 composites the application through `QWidget.grab()` in every
mode: the optical modes blend `self._app_widget.grab()` with a background
video, and Raw also presents a `grab()` result through `_composite_label`.
`QWidget.grab()` renders only the Qt widget tree and cannot capture a foreign
native child window attached with Win32 `SetParent`. Because Raw capture is
not known-good, the `FAIL — native child not captured` precondition is not
met, so this run is `BLOCKED/RETRY`. Teardown additionally raised in
`EmbeddedWindow.restore()` (`SetParent` on a destroyed handle, `WinError 87`).

This outcome does not select a framebuffer architecture. It is, however,
strong evidence for the Milestone 2 direction: a GPL-compatible Crispy Doom
frame-exposure modification or a shared OpenGL ES/Qt rendering surface, rather
than native-window reparenting. Re-running this exact gate is only meaningful
if the host presents the app surface without `QWidget.grab()`; otherwise
proceed to the framebuffer design task.

Use only one of these decisions after completing the checklist:

- **PASS — native embedding viable:** Raw and every available optical mode have
  two changed captures or a short video proving live, updating SDL pixels in the
  app capture; keyboard play, native geometry, uncovered margins/home control,
  matching DPI-awareness, and cleanup all pass.
- **FAIL — native child not captured:** Raw capture is known-good, but an
  available optical mode omits or freezes the SDL child. Only this capture-specific outcome selects framebuffer integration. Do not use screen
  capture as a workaround; open the next design task for a GPL-compliant Crispy
  Doom frame-exposure modification or shared OpenGL ES/Qt rendering surface.
- **BLOCKED/RETRY — implementation or environment failure:** keyboard play,
  geometry/margin/home-control, native client pixels, DPI-awareness, cleanup,
  launch, or evidence collection fails. Fix the named issue and repeat with a
  fresh PID; this outcome does not choose a framebuffer architecture.
- **PENDING — incomplete evidence:** evidence remains incomplete or a named
  optical mode is unavailable without a documented reason. This is not a
  passing result. A documented unavailable mode is not an SDL-child failure,
  but all available optical modes must pass for PASS.
