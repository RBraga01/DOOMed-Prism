# Milestone 1: Raven Simulator embedding result

This template records the decision-gate observations only. The **Final decision**
field at the end is the sole authority for this run and begins as
`PENDING — manual Raven Simulator run required`. Do not enter private paths,
credentials, Raven source, executable locations, screenshots, or raw terminal
output. Keep local evidence in ignored `artifacts/milestone-1/`.

## Run identification

- Date (UTC): PENDING
- Tester: PENDING (use a non-sensitive role or initials if needed)
- Repository commit: PENDING

## Environment

- Windows version: PENDING
- Python version: PENDING
- Raven Framework version/commit: PENDING
- Crispy Doom version/commit: PENDING
- IWAD name: PENDING — record only when redistribution permits; otherwise `not recorded (redistribution not permitted)`
- IWAD SHA-256: PENDING — record only when redistribution permits; otherwise `not recorded (redistribution not permitted)`
- GPU: PENDING
- Display scaling: PENDING
- DPI-awareness match (Raven, Qt host, and Crispy Doom): PENDING

## Launch and interaction

- `python -m pip install -e ".[dev,raven]"`: PENDING
- `doomed-prism validate`: PENDING
- `doomed-prism run-desktop`: PENDING
- Native client-size measurement (`GetClientRect`): PENDING — required `640×480 native client pixels`
- Keyboard-playable Crispy Doom: PENDING
- Viewport geometry: PENDING — required `(0, 80, 640, 480)`
- Upper 80-pixel margin uncovered: PENDING
- Lower 80-pixel margin uncovered: PENDING
- Raven home control uncovered: PENDING

## Per-mode app-capture evidence

Mark each observation `yes`, `no`, `not available`, or `not run`. For an
available mode, prove frame updates with two time-separated captures showing
different game states or one short local video. The evidence field may contain
only local filenames, never a path.

| Mode | Available | Live game pixels in app surface | Frames update during play | Viewport `(0, 80, 640, 480)` | App capture includes SDL child (not blank) | Local evidence filenames | Non-sensitive observation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Raw | not run | not run | not run | not run | not run | not captured | PENDING |
| Night | not run | not run | not run | not run | not run | not captured | PENDING |
| Day | not run | not run | not run | not run | not run | not captured | PENDING |
| Outdoors | not run | not run | not run | not run | not run | not captured | PENDING |
| Camera | not run | not run | not run | not run | not run | not captured | PENDING |

## Cleanup evidence

- Clean pre-launch Crispy Doom PID baseline: PENDING — required `none`
- Crispy Doom PIDs added after launch: PENDING — required `exactly one`
- Crispy Doom PID observed before closing Raven Simulator: PENDING
- Raven Simulator closed normally: PENDING
- Recorded PID absent after close: PENDING
- Cleanup result: PENDING — `no orphan process` is required for PASS
- Non-sensitive cleanup observation: PENDING

If the recorded PID remains present after Raven Simulator closes, record
`orphan process present` and set this run's Final decision to
`BLOCKED/RETRY — implementation or environment failure`. Stopping the orphan
manually is allowed only for local cleanup: it cannot turn this run into PASS.
Retain the failed observation, then use a new PID and repeat the entire run with
fresh per-mode evidence before considering another decision.

## Automated verification after manual run

- `python -m pytest -q`: PENDING
- `git diff --check`: PENDING
- Exact-path documentation staging inspected: PENDING
- `git diff --cached --check`: PENDING
- `python scripts/check_publication_safety.py --root .` after staging: PENDING
- `git status --short`: PENDING

## Final decision

**Final decision:** PENDING — incomplete evidence

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
