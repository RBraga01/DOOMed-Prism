# Milestone 2: Framebuffer capture decision gate

Run this checklist only on a Windows machine where Raven Framework is installed
separately. This repository must not receive Raven source, credentials, local
paths, Crispy Doom binaries, IWADs, or simulator screenshots. Keep screenshots
and any local notes under the ignored `artifacts/milestone-2/` directory.

## Scope and safety

- [ ] Confirm this checkout contains no uncommitted runtime artifacts before starting.
- [ ] Keep the Raven installation, Crispy Doom build, and all local runtime locations out of this document and the result document.
- [ ] Do not record Raven credentials, environment-variable values, user names, machine names, or private paths in terminal output or screenshots.
- [ ] Use an IWAD only when lawfully available. Record its name and SHA-256 in the result only when that disclosure is permitted; otherwise write `not recorded (redistribution not permitted)`.
- [ ] Create the ignored local evidence directory:

  ```powershell
  New-Item -ItemType Directory -Force artifacts/milestone-2 | Out-Null
  ```

## Environment and launch

- [ ] Set Windows to **100% display scaling** before launching. Confirm the Qt host and Crispy Doom use matching DPI-awareness. A scaling mismatch is `BLOCKED/RETRY — implementation or environment failure`.
- [ ] Build Crispy Doom with the pinned patch:

  ```powershell
  python scripts/build_crispy.py
  ```

  Record the result. Confirm that `python scripts/build_crispy.py --check` passes, and record the pinned tag (`crispy-doom-7.1`) and commit SHA from `crispy-doom.lock`, the C compiler version, and the SDL2 development library version.

- [ ] Record the required environment fields in `docs/validation/milestone-2-result.md` without private locations or credentials: Windows version, Python version, Crispy Doom pinned tag/commit, C compiler version, SDL2 version, permitted IWAD identity/checksum, GPU, and display scaling.
- [ ] Configure the Crispy Doom executable built by the script and the IWAD through
  `DOOMED_PRISM_CRISPY_EXE` and `DOOMED_PRISM_IWAD` as described in the
  [local Doom runtime README section](../../README.md#local-doom-runtime).
  Do not copy either value into this repository.
- [ ] Confirm `python -m pytest -q` passes (all tests green) and
  `python scripts/check_publication_safety.py --root .` exits 0.
- [ ] In a dedicated PowerShell validation window that will remain open for the
  whole run, establish a clean Crispy Doom PID baseline before launch:

  ```powershell
  $beforePids = @(Get-Process -Name "crispy-doom" -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty Id)
  if ($beforePids.Count -ne 0) { throw "Crispy Doom baseline is not clean" }
  ```

  If this reports an existing process, stop the validation run, close that
  process normally, and begin again from a new clean baseline. Do not count a
  pre-existing process as the supervised child.
- [ ] From a separate PowerShell window at the repository root, run:

  ```powershell
  python -m pip install -e ".[dev,raven]"
  doomed-prism validate
  doomed-prism run-desktop
  ```

- [ ] After Crispy Doom appears, return to the validation window and identify
  the one PID added after the clean baseline:

  ```powershell
  $afterPids = @(Get-Process -Name "crispy-doom" -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty Id)
  $newPids = @($afterPids | Where-Object { $_ -notin $beforePids })
  if ($newPids.Count -ne 1) { throw "Expected exactly one new Crispy Doom PID" }
  $doomPid = [int]$newPids[0]
  $doomPid
  ```

  Record only `$doomPid` in the result document. If there is not exactly one
  new PID, record `BLOCKED/RETRY — implementation or environment failure`,
  restore a clean baseline, and repeat the entire run.
- [ ] Verify the shared-memory segment is live and exporting frames. Write a small
  probe script in PowerShell or Python using `pewpew.framebuffer.FrameReader` to:
  - Open the segment (name printed in result during launch).
  - Confirm `magic == 0x50504642` and `version == 1`.
  - Observe `frame_counter` advance over 1–2 seconds while the game is running.
  - Record the result in the result document.

  This proves the export path is live independently of the Qt viewport.
- [ ] In Raven Simulator, confirm that live DOOM pixels are visible inside the Qt
  viewport (the central 640×480 display area at vertical offset 80px).
- [ ] Confirm the game exactly fills the viewport `(0, 80, 640, 480)` within the
  640×640 app surface, leaves both 80-pixel margins uncovered, and does not cover
  the Raven home control. Record the Win32 `GetClientRect` result: it must be
  **640×480 native client pixels**, not only matching logical Qt geometry.
- [ ] Confirm no Win32 `SetParent` calls exist in the window tree. Crispy Doom's
  SDL window must remain independent, not reparented into the Qt host. This is a
  regression check from Milestone 1.

## Evidence collection

For every mode below, start or continue a live game and visibly change the game
state (for example, move or turn). Capture proof of change as either two
time-separated app-capture screenshots showing different game states or one
short local app-capture video. Use these exact mode names and suggested artifact
names. Do not add the captures to Git.

| Mode | Suggested local evidence | Required observation |
| --- | --- | --- |
| Raw | `raw-1.png` + `raw-2.png`, or `raw.mp4` | Geometry, visibility, live updates, and Raven app capture includes frame |
| Night | `night-1.png` + `night-2.png`, or `night.mp4` | Optical compositing, live updates, transparency, and Raven app capture includes frame |
| Day | `day-1.png` + `day-2.png`, or `day.mp4` | Optical compositing, live updates, transparency, and Raven app capture includes frame |
| Outdoors | `outdoors-1.png` + `outdoors-2.png`, or `outdoors.mp4` | Optical compositing, live updates, transparency, and Raven app capture includes frame |
| Camera | `camera-1.png` + `camera-2.png`, or `camera.mp4` | Optical compositing, live updates, transparency, and Raven app capture includes frame |

For each row in the result document, record all of the following as `yes`, `no`, `not available`, or `not run` (with a short non-sensitive observation):

- live DOOM pixels appear inside the Qt viewport within the app surface;
- frames visibly update while playing; the attract loop is sufficient;
- viewport remains `(0, 80, 640, 480)`;
- Raven Simulator's app capture includes the DOOM frame rather than a blank or grey rectangle;
- in the optical modes, dark DOOM areas read as transparent (additive display, not opaque);
- a keypress in Crispy's separate SDL window produces a visible state change in the
  Qt viewport, proving the shared-memory path tracks real gameplay, not only the attract loop;
- two time-separated local screenshot filenames showing changed game state, or one short local video filename (or `not captured`).

## Cleanup check

- [ ] Before closing Raven Simulator, confirm that the numeric `$doomPid`
  selected by the before/after procedure is recorded in the result document.
  Do not record its executable path.
- [ ] Close Raven Simulator normally.
- [ ] In the same validation window, verify that the recorded PID no longer
  exists:

  ```powershell
  Get-Process -Id $doomPid -ErrorAction SilentlyContinue
  ```

- [ ] Record `no orphan process` only when the command produces no process
  result. If it returns the recorded PID, record `orphan process present` and
  mark this run `BLOCKED/RETRY — implementation or environment failure`.
- [ ] You may terminate an orphan locally for machine hygiene, but that does not
  alter the failed observation or convert this run to PASS. Preserve the failure
  in the result, then perform a fresh complete run with a new PID and new
  per-mode evidence before considering a new decision. Do not commit process
  output.
- [ ] Record whether `cleanup()` executed without exception. The Milestone 1
  teardown raised `WinError 87` when calling `SetParent` on a destroyed handle;
  Milestone 2 must execute reader-close followed by engine-stop with no exception.
  If an exception occurs, record the exception type and message, mark this run
  `BLOCKED/RETRY`, and repeat with a fresh PID.

## Hard decision rule

After every available mode and the cleanup check are complete, edit the sole
final decision field in the result document:

- **PASS — framebuffer integration viable** only when Raw and every available optical
  mode (Night, Day, Outdoors, and Camera) have two changed app captures or a
  short video proving live DOOM pixels, frame updates, correct viewport geometry,
  and inclusion in Raven's app capture; dark areas read as transparent in optical
  modes; a keyboard press in Crispy's SDL window produces a visible state change
  in the Qt viewport; the cleanup check passes with no orphan and no exception;
  and matching display scaling is confirmed.
- **FAIL — framebuffer path insufficient** only when the shared-memory export
  is confirmed live (segment counter advancing) but the Qt viewport is still not
  captured in an available optical mode, or additive compositing is wrong (for
  example, dark areas render opaque instead of transparent). Only this outcome
  selects a shared OpenGL ES / Qt rendering surface design. Do not use screen
  capture or desktop capture as a workaround.
- **BLOCKED/RETRY — implementation or environment failure** when build, launch,
  geometry, display scaling, segment creation, keyboard input, orphan cleanup,
  teardown exception, or required evidence fails. Record the failure, fix or
  change the environment, then repeat the whole run with a fresh PID; this outcome
  does not select a framebuffer architecture.
- Leave the decision **PENDING — incomplete evidence** only while evidence is
  incomplete (including `not run`) or a named optical mode is unavailable
  without a documented reason. PENDING is never PASS.

## Final automated verification and commit

After the manual decision is recorded, verify the worktree, then stage exactly
the two documentation files. Never use `git add .`, `git add -A`, or a wildcard,
and never stage anything under `artifacts/`.

```bash
python -m pytest -q
git diff --check
git add -- docs/validation/milestone-2-checklist.md docs/validation/milestone-2-result.md
git diff --cached --name-status
git diff --cached --check
python scripts/check_publication_safety.py --root .
python scripts/check_publication_safety.py --root . --history
git commit -m "docs: add Milestone 2 framebuffer capture checklist"
git status --short
```

Before committing, inspect `git diff --cached --name-status`: it must list only
the two exact documentation paths above. The scanner reads the staged Git index,
so it must run after that exact-path `git add`. Expected: tests pass, the scanner
exits 0, there are no whitespace errors, and `git status --short` is empty after
the commit. Do not commit ignored evidence or restricted runtime material.
