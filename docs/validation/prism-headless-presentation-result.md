# Prism headless engine presentation — hardware finding result

## Finding

Raven Prism hardware testing (Parth) showed both Crispy Doom's native SDL
window and the DOOMed Prism/Raven compositor output visible simultaneously
on-device. Not the intended architecture: on Prism, Crispy should run only
as the engine/framebuffer producer, headless — the Raven app should be the
only visible surface. A two-window setup remains acceptable for
Windows/Simulator development.

## Fix

`DOOMED_PRISM_HEADLESS_ENGINE`, an opt-in env var (PR #11, merged
`8a536c4`, base `main` at `dee83e1`). When set, `DoomProcess.start()` adds
`SDL_VIDEODRIVER=dummy` to the child's environment — SDL runs its full
internal window/renderer/texture pipeline with no real window ever
created. Unset by default; Windows/Simulator/Linux development is
unaffected. **Prism deployment must set this explicitly** — nothing does
so automatically yet.

Investigation (see the PR and `src/pewpew/engine.py`'s comment) ruled out
`-noblit` (it also disables the framebuffer export) and any Crispy
patch change (the framebuffer export reads a CPU-side render buffer, and
IPC input arrives via `D_PostEvent`, so neither depends on window
visibility).

## Software/CI gate

**PASS.**

- `python -m pytest -q`: 253 passed, 6 skipped
- `check_publication_safety.py --root .` / `--root . --history`: exit 0
- `build_crispy.py --check`: exit 0 (zero patch changes)
- `scripts/ci_headless_smoke.py`, wired into both the Linux x86_64 and
  ARM64 CI jobs: launches the engine through the real `DoomProcess.start()`
  with `DOOMED_PRISM_HEADLESS_ENGINE=1` and `DISPLAY`/`XAUTHORITY` stripped
  entirely — no Xvfb. Confirms the IPC handshake, framebuffer export, and
  input round-trip all still work, with clean teardown. Passed on both
  architectures in PR #11's CI run, and again in the push-triggered `main`
  CI run for the merge commit.

**What this does and does not prove:** succeeding with no display server
at all is strong evidence the engine no longer *depends* on one. It is
**not** evidence of what the Raven compositor actually shows on physical
Prism hardware.

## Physical-Prism gate

**PENDING.** Not yet run. Deploy the merged build to real Prism hardware
with `DOOMED_PRISM_HEADLESS_ENGINE=1` set, and confirm: only the Raven app
is visible — no separate Crispy surface. Owner: Parth/Raven, next time the
new build can be run on-device.

## Final decision

**Final decision:** PENDING — physical-Prism confirmation outstanding.

This hardware finding is not fully closed until the physical-Prism gate
above passes. The software/CI gate passing does not block other
development from proceeding in the meantime (spec R15's software/hardware
gate split applies the same discipline here).
