# Milestone 1: Raven Simulator capture decision gate

Run this checklist only on a Windows machine where Raven Framework is installed
separately. This repository must not receive Raven source, credentials, local
paths, Crispy Doom binaries, IWADs, or simulator screenshots. Keep screenshots
and any local notes under the ignored `artifacts/milestone-1/` directory.

## Scope and safety

- [ ] Confirm this checkout contains no uncommitted runtime artifacts before starting.
- [ ] Keep the Raven installation and all local runtime locations out of this document and the result document.
- [ ] Do not record Raven credentials, environment-variable values, user names, machine names, or private paths in terminal output or screenshots.
- [ ] Use an IWAD only when lawfully available. Record its name and SHA-256 in the result only when that disclosure is permitted; otherwise write `not recorded (redistribution not permitted)`.
- [ ] Create the ignored local evidence directory:

  ```powershell
  New-Item -ItemType Directory -Force artifacts/milestone-1 | Out-Null
  ```

## Environment and launch

- [ ] Set Windows to **100% display scaling** before launching. Confirm Raven, the Qt host, and Crispy Doom use matching DPI-awareness. A cross-process SetParent can otherwise cause Windows DPI virtualization; a mismatch is
  `BLOCKED/RETRY — implementation or environment failure`.
- [ ] Record the required environment fields in `docs/validation/milestone-1-result.md` without private locations or credentials: Windows version, Python version, Raven Framework version/commit, Crispy Doom version/commit, permitted IWAD identity/checksum, GPU, and display scaling.
- [ ] Configure the locally installed Crispy Doom executable and IWAD through
  `DOOMED_PRISM_CRISPY_EXE` and `DOOMED_PRISM_IWAD` as described in the
  [local Doom runtime README section](../../README.md#local-doom-runtime).
  Do not copy either value into this repository.
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
- [ ] In Raven Simulator, confirm Crispy Doom accepts keyboard input while its native child is embedded in the app.
- [ ] Confirm the game exactly fills the viewport `(0, 80, 640, 480)` within the 640x640 app surface, leaves both 80-pixel margins uncovered, and does not cover the Raven home control. Record the Win32 `GetClientRect` result: it must be **640×480 native client pixels**, not only matching logical Qt geometry.

## Evidence collection

For every mode below, start or continue a live game and visibly change the game
state (for example, move or turn). Capture proof of change as either two
time-separated app-capture screenshots showing different game states or one
short local app-capture video. Use these exact mode names and suggested artifact
names. Do not add the captures to Git.

| Mode | Suggested local evidence | Required observation |
| --- | --- | --- |
| Raw | `raw-1.png` + `raw-2.png`, or `raw.mp4` | Geometry, visibility, and live updates |
| Night | `night-1.png` + `night-2.png`, or `night.mp4` | Optical compositing and live updates |
| Day | `day-1.png` + `day-2.png`, or `day.mp4` | Optical compositing and live updates |
| Outdoors | `outdoors-1.png` + `outdoors-2.png`, or `outdoors.mp4` | Optical compositing and live updates |
| Camera | `camera-1.png` + `camera-2.png`, or `camera.mp4` | Optical compositing and live updates |

For each row in the result document, record all of the following as `yes`, `no`, `not available`, or `not run` (with a short non-sensitive observation):

- live game pixels appear inside the app surface;
- frames visibly update while playing;
- viewport remains `(0, 80, 640, 480)`;
- Raven Simulator's app capture includes the SDL child rather than a blank rectangle;
- two time-separated local screenshot filenames showing changed game state, or
  one short local video filename (or `not captured`).

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

## Hard decision rule

After every available mode and the cleanup check are complete, edit the sole
final decision field in the result document:

- **PASS — native embedding viable** only when Raw and every available optical
  mode (Night, Day, Outdoors, and Camera) have two changed app captures or a
  short video proving live SDL pixels and updates; keyboard play works; the
  viewport has 640×480 native client pixels; both margins and the Raven home
  control are uncovered; DPI-awareness matches; and cleanup leaves no child.
- **FAIL — native child not captured** only when Raw capture is known-good and
  an available optical mode omits or freezes the SDL child. Only this capture-specific outcome selects framebuffer integration. Do not work around
  it with screen capture, desktop capture, or video streaming.
- **BLOCKED/RETRY — implementation or environment failure** when keyboard,
  geometry, DPI-awareness, cleanup, launch, or required evidence fails. Record
  the failure, fix or change the environment, then repeat the whole run with a
  fresh PID; this outcome does not select a framebuffer architecture.
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
git add -- docs/validation/milestone-1-checklist.md docs/validation/milestone-1-result.md
git diff --cached --name-status
git diff --cached --check
python scripts/check_publication_safety.py --root .
python scripts/check_publication_safety.py --root . --history
git commit -m "docs: record Raven simulator embedding result"
git status --short
```

Before committing, inspect `git diff --cached --name-status`: it must list only
the two exact documentation paths above. The scanner reads the staged Git index,
so it must run after that exact-path `git add`. Expected: tests pass, the scanner
exits 0, there are no whitespace errors, and `git status --short` is empty after
the commit. Do not commit ignored evidence or restricted runtime material.
