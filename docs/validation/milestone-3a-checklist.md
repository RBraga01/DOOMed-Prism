# Milestone 3a: IPC input path decision gate

Run this checklist only on a Windows machine where Raven Framework is installed
separately. This repository must not receive Raven source, credentials, local
paths, Crispy Doom binaries, IWADs, or simulator screenshots. Keep screenshots
and any local notes under the ignored `artifacts/milestone-3/` directory.

The hard question this gate answers: **does IPC-only normalized input drive real
DOOM gameplay inside the Qt viewport — the radial analog stick (proportional turn
**and** forward/back from one gaze vector, a round dead zone), debounced
click-fire, fused spoken-fire (the `B` debug source with
`DOOMED_PRISM_DEBUG_FIRE=1`), and Enter-pause — with Crispy's SDL window
unfocused the entire time, and does every lifecycle transition release all held
inputs with no stuck key and no orphan process?**

## Scope and safety

- [ ] Confirm this checkout contains no uncommitted runtime artifacts before starting.
- [ ] Keep the Raven installation, Crispy Doom build, and all local runtime locations out of this document and the result document. This repository receives no Raven source and no credentials.
- [ ] Do not record Raven credentials, environment-variable values, user names, machine names, or private paths in terminal output or screenshots.
- [ ] Record the IPC address **only** as the placeholders `<tempdir>/doomed-prism-ipc-<pid>-<token>.sock` (POSIX) and `127.0.0.1:<port>` (Windows), and only its presence/absence plus the port number. Never paste the resolved socket path or temp directory.
- [ ] Do not record any commercial IWAD identity. Use a Freedoom IWAD for the gate. Record its name and SHA-256 in the result only when that disclosure is permitted; otherwise write `not recorded (redistribution not permitted)`.
- [ ] Create the ignored local evidence directory:

  ```powershell
  New-Item -ItemType Directory -Force artifacts/milestone-3 | Out-Null
  ```

- [ ] Confirm `artifacts/` is git-ignored (it is, from Milestone 2) and that nothing under it is staged at any point in this run.

## Environment and launch

- [ ] Set Windows to **100% display scaling** before launching. A scaling mismatch is `BLOCKED/RETRY — implementation or environment failure`.
- [ ] Build Crispy Doom with the pinned patch series:

  ```powershell
  python scripts/build_crispy.py
  ```

  Record the result. The script applies the ordered `PATCHES` series cumulatively
  on disk (`patches/crispy-doom-fb-export.diff` then
  `patches/crispy-doom-ipc-input.diff`) after restoring the checkout to the
  pinned commit.

- [ ] Confirm the series still composes:

  ```powershell
  python scripts/build_crispy.py --check
  ```

  This restores the disposable checkout, applies patch 1 for real, then runs
  `apply --check` on patch 2 (the honest "does the series still apply" test).
  Record `pass` / `fail` and the exit code.

- [ ] Record the patch-2 diffstat and confirm its shape and size:

  ```powershell
  git apply --stat patches/crispy-doom-ipc-input.diff
  ```

  Confirm it adds only `src/i_ipc_input.c` / `src/i_ipc_input.h` plus small hunks
  in `src/d_loop.c`, `src/i_video.c`, and `src/CMakeLists.txt`, and one
  clearly-marked hunk in `src/doom/g_game.c` (the R14 `forwardmove` fold), and
  that the total changed-line count stays within the stated diff-minimality
  ceiling. A patch that touches any other file, or exceeds the ceiling, is
  `BLOCKED/RETRY — implementation or environment failure`.

- [ ] Record the required environment fields in `docs/validation/milestone-3a-result.md` without private locations or credentials: Windows version, Python version, Crispy Doom pinned tag/commit from `crispy-doom.lock`, C compiler version, SDL2 development library version, permitted Freedoom IWAD identity/checksum (or the redaction note), GPU, and display scaling.
- [ ] Configure the Crispy Doom executable built by the script and the Freedoom IWAD through `DOOMED_PRISM_CRISPY_EXE` and `DOOMED_PRISM_IWAD` as described in the [local Doom runtime README section](../../README.md#local-doom-runtime). Do not copy either value into this repository.
- [ ] Confirm `doomed-prism validate` exits 0 (both runtime paths valid).
- [ ] Confirm `python -m pytest -q` passes (all tests green).
- [ ] Confirm both publication-safety scans exit 0:

  ```powershell
  python scripts/check_publication_safety.py --root .
  python scripts/check_publication_safety.py --root . --history
  ```

- [ ] In a dedicated PowerShell validation window that will remain open for the
  whole run, establish a clean Crispy Doom PID baseline before launch (the M2
  before/after procedure):

  ```powershell
  $beforePids = @(Get-Process -Name "crispy-doom" -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty Id)
  if ($beforePids.Count -ne 0) { throw "Crispy Doom baseline is not clean" }
  ```

  If this reports an existing process, stop, close it normally, and begin again
  from a clean baseline. Do not count a pre-existing process as the supervised
  child.

- [ ] Set the gate environment so the run reaches a live level with no menu
  navigation and drives the fusion path without real audio:

  ```powershell
  $env:DOOMED_PRISM_WARP = "1 1"
  $env:DOOMED_PRISM_DEBUG_FIRE = "1"
  ```

- [ ] From a separate PowerShell window at the repository root, run:

  ```powershell
  python -m pip install -e ".[dev,raven]"
  doomed-prism validate
  doomed-prism run-desktop
  ```

- [ ] After Crispy Doom appears, return to the validation window and identify the
  one PID added after the clean baseline:

  ```powershell
  $afterPids = @(Get-Process -Name "crispy-doom" -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty Id)
  $newPids = @($afterPids | Where-Object { $_ -notin $beforePids })
  if ($newPids.Count -ne 1) { throw "Expected exactly one new Crispy Doom PID" }
  $doomPid = [int]$newPids[0]
  $doomPid
  ```

  Record only `$doomPid` in the result document. If there is not exactly one new
  PID, record `BLOCKED/RETRY — implementation or environment failure`, restore a
  clean baseline, and repeat the entire run.

## Objective checks

Record each as `yes`, `no`, `not available`, or `not run` with a short
non-sensitive observation.

- [ ] **Exactly one new crispy-doom PID** against the clean baseline (from the
  before/after procedure above).
- [ ] **IPC socket present while running.** POSIX: the placeholder path
  `<tempdir>/doomed-prism-ipc-<pid>-<token>.sock` exists while the game runs.
  Windows: the PewPew process owns a listening `127.0.0.1:<port>` (record only
  presence and the port number). **IPC socket gone after close:** the placeholder
  path no longer exists / the listening port is released.
- [ ] **M2 framebuffer path unbroken.** A `pewpew.framebuffer.FrameReader` probe
  still shows `frame_counter` advancing over 1–2 seconds while the game runs
  (`magic == 0x50504642`, `version == 1`). The IPC input subsystem must not
  regress the M2 export path.
- [ ] **With Crispy's SDL window minimised or behind the Raven Simulator, and
  unfocused, for the whole run:**
  - [ ] Gaze left of the **dead-zone circle** turns the DOOM view left; right of
    it, right. Returning gaze inside the circle stops the turn within ~3–5 ticks,
    smoothly, with no abrupt cut.
  - [ ] Gaze farther from the circle turns visibly faster than gaze just outside
    it, smoothly, with no step (the curved analog stick).
  - [ ] Gaze above the circle walks forward; below, backward — and, like turn,
    **faster the farther out**, smoothly. Record whether forward is proportional
    or (degraded mode) single-speed.
  - [ ] **Backward is as reachable and as fast as forward** — no ~9 px sliver.
  - [ ] Gaze up-and-to-a-side walks forward while turning, both from **one
    vector**; sweeping the gaze slowly across that **diagonal** (and across where
    the old zone boundary used to be) never makes forward stutter, slow abruptly,
    or cut out.
  - [ ] **One click fires one shot. Five fast clicks fire fewer than five shots**
    (debounce; the `PULSE_HOLD_TICS` key hold is understood).
  - [ ] **`B` fires a shot through the same path** (spoken-fire fusion via the
    debug source, `DOOMED_PRISM_DEBUG_FIRE=1`). **A click and a `B` within
    ~30 ms fire once.** (`B` replaced `F9` on 2026-09-08 — Raven bound `F9` as
    a shortcut so it never reached the input filter.)
  - [ ] **`P` (or `Enter`) shows the `PAUSED` overlay and pauses; press again
    to resume.** Neither key closes the simulator (the `ShortcutOverride` fix).
    No SDL-window focus was used at any point during the run.
- [ ] **No Win32 `SetParent` anywhere** in the window tree. Crispy Doom's SDL
  window stays an independent top-level window, never reparented into the Qt
  host. This is a regression check carried from Milestones 1 and 2.

## Lifecycle checks

Every lifecycle transition must **release all held inputs** — no key stuck down,
no held turn persisting across the transition — and leave no orphan process.

- [ ] **Sleep / conceal (or hide the host).** While a turn is held, trigger Raven
  sleep/conceal or hide the host window: the game pauses and the `PAUSED` overlay
  shows. On resume it unpauses and no key is stuck — the held turn from before the
  hide does not persist.
- [ ] **Kill the PewPew process while the stick is held forward-and-turning.**
  DOOM stops turning **and stops moving forward** (the injected `ev_mouse` deltas
  stop; the C-side release-all zeroes the injected `forwardmove` contribution
  (and, in the duty-cycle fallback, posts `ev_keyup` for a movement key)) and
  keeps running on SDL input. After its window is closed there is no orphan
  process.
- [ ] **Normal close.** `cleanup()` runs stop-tick → `pipeline.release_all()` →
  `IpcServer.close()` → `reader.close()` → `engine.stop()` with no exception; the
  one recorded PID is gone; the IPC socket path is removed. Record the exception
  type and message if any step raises, then mark the run
  `BLOCKED/RETRY — implementation or environment failure` and repeat with a fresh
  PID.

## Per-mode evidence

For Raw plus each available optical mode (Night, Day, Outdoors, Camera), capture
one short local **Freedoom-only** video or two time-separated captures showing
gaze-driven view motion **and** a fired shot inside the composited viewport, with
the SDL window not focused. Night carries the full dynamic proof; the others may
be lighter, as in the Milestone 2 gate. Do not add the captures to Git.

| Mode | Suggested local evidence | Required observation |
| --- | --- | --- |
| Raw | `raw.mp4`, or `raw-1.png` + `raw-2.png` | Gaze-driven view motion and a fired shot inside the viewport, SDL window unfocused |
| Night | `night.mp4` | Full dynamic proof: gaze steering the radial stick, proportional turn and forward from one vector, a fired shot, and Enter-pause, all composited, SDL window unfocused |
| Day | `day.mp4`, or `day-1.png` + `day-2.png` | Gaze-driven view motion and a fired shot inside the composited viewport, SDL window unfocused |
| Outdoors | `outdoors.mp4`, or `outdoors-1.png` + `outdoors-2.png` | Gaze-driven view motion and a fired shot inside the composited viewport, SDL window unfocused |
| Camera | `camera.mp4`, or `camera-1.png` + `camera-2.png` | Gaze-driven view motion and a fired shot inside the composited viewport, SDL window unfocused |

- [ ] During the movement checks, save the outgoing `ACTION.value` /
  `TURN.value` streams to `artifacts/milestone-3/` and attach a quick
  value-vs-eccentricity plot — a semi-objective proportionality artifact.
- [ ] Any clip promoted into tracked `docs/media/` is **Freedoom-only** and has
  been reviewed frame-by-frame for usernames, file paths, and IWAD identity
  before being committed. A commercial IWAD clip is never promoted.

## Hard decision rule

After every available mode and all lifecycle checks are complete, edit the sole
**Final decision** field in `docs/validation/milestone-3a-result.md` to exactly
one of:

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

## Final automated verification and commit

After the manual decision is recorded, verify the worktree, then stage exactly
the two documentation files. Never use `git add .`, `git add -A`, or a wildcard,
and never stage anything under `artifacts/`.

```bash
python -m pytest -q
git diff --check
git add -- docs/validation/milestone-3a-checklist.md docs/validation/milestone-3a-result.md
git diff --cached --name-status
git diff --cached --check
python scripts/check_publication_safety.py --root .
python scripts/check_publication_safety.py --root . --history
git commit -m "docs: record IPC input path result"
git status --short
```

Before committing, inspect `git diff --cached --name-status`: it must list only
the two exact documentation paths above. The scanner reads the staged Git index,
so it must run after that exact-path `git add`. Expected: tests pass, both
scanners exit 0, there are no whitespace errors, and `git status --short` is
empty after the commit. The README refresh lands with the implementation commits,
not this decision-record commit. Do not commit ignored evidence or restricted
runtime material.
