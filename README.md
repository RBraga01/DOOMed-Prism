# DOOMed Prism

**Can it run DOOM?** Apparently Raven can. 😅

DOOMed Prism is an experimental DOOM port for Raven Prism smart glasses. The
game already runs inside the Raven Simulator, composited through a Qt‑painted
shared‑memory framebuffer. The ridiculous part is intentional. The engineering
underneath it is not.

![DOOM running inside the Raven Simulator](docs/media/raven-simulator.gif)

*The patched Crispy Doom engine running [Freedoom](https://freedoom.github.io/)
live inside the Raven Simulator's Night mode — the game surface is a Qt widget,
not a native SDL window.*

## Current status

**Milestone 3a — input & IPC:** implemented on `feature/doomed-prism-m3`.
Gaze drives a **radial analog stick** — proportional turn *and* forward/back
from one gaze vector — over a local IPC socket to the patched engine. The
Windows / Raven Simulator decision gate **passed** on 2026-09-08: IPC-only input drives the
composited DOOM with Crispy's SDL window unfocused, every lifecycle transition
releases held input with no stuck key or orphan process, and the Milestone 2
framebuffer path is unaffected. See
[`docs/validation/milestone-3a-result.md`](docs/validation/milestone-3a-result.md).

- Validated on Windows 11 in **Raw, Night, Day, Outdoors and Camera** modes —
  live, updating pixels composited by the real Raven Simulator compositor.
- Linux x86_64 build is validated in GitHub Actions.
- The POSIX `shm_open` runtime path is exercised in CI: a valid 640×480
  shared‑memory segment, a validated header, an advancing `frame_counter`, and a
  clean teardown that leaves no `/dev/shm` segment behind.
- The Crispy Doom pin in `crispy-doom.lock` is now actually enforced, not just
  recorded.
- The Python test suite is green (the only skips are POSIX‑only tests that do
  not run on Windows).
- **Raven has publicly shown DOOMed Prism running on physical Raven Prism
  hardware.** On September 9, 2026, Raven Resonance posted on LinkedIn that the
  port runs on the glasses — *"the first natively compiled (non web app) DOOM
  port on lightweight eyewear"* — and credited Ricardo Braga. Raven's Parth Arora
  separately confirmed on Raven's Discord that the repository compiled and ran
  **directly on the Prism, with no device-specific changes**. Quotes and details:
  [`docs/reference/raven-public-post.md`](docs/reference/raven-public-post.md).
  This is Raven-side public recognition, not affiliation, sponsorship, or a
  formal endorsement.

**Native ARM64 build and run — gated in CI *and* externally validated by Raven.**
GitHub Actions builds the patched engine and runs the POSIX shared-memory runtime
smoke natively on `ubuntu-24.04-arm` (aarch64) alongside x86_64; Raven separately
compiled this repository directly on the physical Prism and ran it, with no
device-specific changes.

**Still outstanding:** this project's own controlled, reproducible *on-glasses*
validation (distinct from Raven's external demonstration above). The simulator is
an optical preview, not the device.

## What comes next

Milestone 3 is about input — because right now the only thing you can do is
watch DOOM run.

- **Gaze** to steer and turn.
- **Double blink** as a deliberate action — probably `FIRE`.
- **Voice** for menus and weapon switching.
- A spoken **"pew pew"** as a fire command. This one is not a joke; it is a
  design goal.

Milestone 3a delivers the input core and the IPC boundary. Voice — spoken
menu/weapon commands and a spoken **"pew pew"** — ships in Milestone 3b, after
an offline‑speech‑library licence review.

## How it works

```
Crispy Doom
  ↓  patched framebuffer exporter (opt-in via DOOMED_PRISM_FB_NAME)
shared-memory triple buffer
  ↓  pewpew.framebuffer.FrameReader  (stdlib mmap, zero-copy)
Qt-painted Raven viewport  (a plain QWidget, no native window)
  ↓
Raven Simulator compositor  (QWidget.grab())
```

- No native Win32 window reparenting anymore.
- The shared‑memory framebuffer is now the rendering foundation.
- Because the viewport is an ordinary Qt‑painted widget, Raven captures the
  result through its own `QWidget.grab()` compositor, in every mode.

## Why shared memory?

Milestone 1 tried the obvious thing: launch Crispy Doom as a normal process and
reparent its native SDL window into the Qt app with `SetParent`.

The Win32 embedding itself worked — correct geometry, correct DPI, clean
lifecycle. But Raven Simulator composites applications through
`QWidget.grab()`, which walks the Qt widget tree and never sees a foreign native
child window. In every mode, the embedded game was a blank rectangle.

That architecture was retired. Milestone 2 moved rendering to a shared‑memory
segment the engine writes and a Qt widget paints — and that path passed the same
decision gate M1 failed.

The full investigation lives in [`docs/validation/`](docs/validation/).

## Why Raven?

Raven Prism is a useful target for this experiment because it exposes a
developer‑oriented stack, a simulator that lets the rendering path be tested
before hardware access, and an interaction model that is interesting for
hands‑free controls.

DOOMed Prism is not about turning smart glasses into a gaming device. It is a
deliberately extreme test case for rendering, input, latency, compositor
behaviour, and unconventional interaction on wearable displays. DOOM is the
stress test, not the point.

Raven is the current target, not a permanent dependency. The longer‑term goal is
to keep the engine/input boundary portable enough that other smart‑glasses
platforms could be explored later.

## Quick start

Windows is the primary local development path — Raven Simulator validation
happened there.

1. **Python 3.10+.** Install dev dependencies:

   ```bash
   python -m pip install -e ".[dev]"
   ```

2. **Build the patched Crispy Doom engine** (a stock build will not export
   frames — see the next section for prerequisites):

   ```bash
   python scripts/build_crispy.py
   ```

3. **Point the app at the engine and an IWAD.** In PowerShell:

   ```powershell
   $env:DOOMED_PRISM_CRISPY_EXE = "<path printed by build_crispy.py>"
   $env:DOOMED_PRISM_IWAD       = "C:\path\to\freedoom1.wad"
   ```

   Use a lawfully obtained IWAD. [Freedoom](https://freedoom.github.io/) is a
   free, redistributable option. You may instead point `DOOMED_PRISM_IWAD` at a
   commercial `DOOM.WAD` / `DOOM2.WAD` you own — but **never commit an IWAD to
   this repository.**

## Building the patched engine

The app reads frames from a shared‑memory segment, and drives input over a local
IPC socket, through two small committed patches to Crispy Doom — the
frame‑export patch (`patches/crispy-doom-fb-export.diff`) and the IPC‑input patch
(`patches/crispy-doom-ipc-input.diff`). `scripts/build_crispy.py` applies them as
a series; build with it, not a stock checkout.

**Prerequisite:** a C toolchain plus SDL2, SDL2_mixer, and SDL2_net development
libraries.

- Windows (MSYS2 UCRT64):

  ```bash
  pacman -S mingw-w64-ucrt-x86_64-toolchain mingw-w64-ucrt-x86_64-cmake \
      mingw-w64-ucrt-x86_64-ninja mingw-w64-ucrt-x86_64-pkgconf \
      mingw-w64-ucrt-x86_64-SDL2 mingw-w64-ucrt-x86_64-SDL2_mixer \
      mingw-w64-ucrt-x86_64-SDL2_net
  ```

- Linux: the equivalent toolchain plus `libsdl2-dev`, `libsdl2-mixer-dev`,
  `libsdl2-net-dev`.

**Usage:**

```bash
python scripts/build_crispy.py            # fetch the pinned tag, apply the patch,
                                          # build; prints the built exe path
python scripts/build_crispy.py --check    # verify the pin and that the patch
                                          # applies cleanly; no build
python scripts/build_crispy.py --check --offline   # same, skipping the tarball
                                          # download (the commit pin is still checked)
python scripts/build_crispy.py --clean    # remove the build directory
```

**The pin is enforced.** After cloning the tag, the checkout's
`git rev-parse HEAD` must equal `commit` in `crispy-doom.lock` — a moved upstream
tag aborts the run — and `tarball_sha256` is verified against the GitHub tag
archive, downloaded with the Python standard library. `--offline` skips only that
download.

**Windows git‑on‑`PATH` hazard:** MSYS2 ships its own `git` in
`C:\msys64\usr\bin`, and it can fail to apply the patch where Git for Windows'
`git` succeeds. If `git apply` fails with "patch does not apply" even though the
patch is fine, keep `C:\msys64\usr\bin` off `PATH` — only
`C:\msys64\ucrt64\bin` (the compiler) is needed there.

**Windows runtime DLLs:** the built `crispy-doom.exe` dynamically links SDL2,
SDL2_mixer, and SDL2_net. Add the toolchain's `bin` directory to `PATH` when
launching it, or copy those DLLs next to the executable.

## Validation and CI

GitHub Actions (`.github/workflows/ci.yml`) runs, on `ubuntu-latest`:

- `pytest`
- publication safety — working tree and full history
- `build_crispy.py --check` (patch applies + pin verified)
- a real Linux build of the patched engine
- a **POSIX runtime smoke test**: launch the built engine with a
  distro‑provided Freedoom IWAD, attach with `FrameReader`, and assert a valid
  640×480 segment, an advancing `frame_counter`, and a clean teardown with no
  leftover `/dev/shm` segment.

The build and the POSIX runtime smoke test also run natively on
`ubuntu-24.04-arm` (aarch64), so every push exercises the patched engine on
ARM64 Linux as well as x86_64.

What this does and does not prove:

- **Windows + Raven Simulator** is the actual proof that Raven's compositor
  captures the game. CI does not run the Raven Simulator.
- **Linux CI** proves the portable pieces — the build, the shared‑memory
  protocol, the teardown — independently of Raven.
- **ARM64** is gated in CI — a native `ubuntu-24.04-arm` build of the patched
  engine plus the POSIX runtime smoke — and was separately validated by Raven on
  the physical Prism (see
  [`docs/reference/raven-public-post.md`](docs/reference/raven-public-post.md)).
  What CI does *not* cover is on-glasses behaviour: the Raven compositor and the
  Prism's own runtime, not ARM64 as such.

## Publication safety

Every commit must be safe to publish. The repository must never contain Raven
framework source, commercial DOOM game data, IWADs, executables, shared
libraries, or credentials.

```bash
python scripts/check_publication_safety.py --root .
python scripts/check_publication_safety.py --root . --history
```

## Disclaimer

DOOMed Prism is an independent, unofficial experimental project.

It is not affiliated with, endorsed by, or sponsored by Raven Resonance,
id Software, Bethesda Softworks, ZeniMax Media, or their affiliates.

"Raven Prism", "DOOM", "Crispy Doom", and other product or project names
referenced here belong to their respective owners.

This repository does not distribute Raven Framework source code, commercial DOOM
IWADs, game assets, executables, or other proprietary third‑party content. Users
must provide any required external software or game data separately and in
accordance with its applicable license.

The Raven Simulator on Windows is this repository's own development and
validation environment — Milestones 2 and 3a passed their decision gates
against it — and CI additionally builds and runs the patched engine natively
on aarch64 Linux. Raven has separately compiled this project directly from the
repository on physical Raven Prism hardware and run it successfully. Raven's
post and its engineer's confirmation
([`docs/reference/raven-public-post.md`](docs/reference/raven-public-post.md))
are evidence and public recognition, not affiliation, sponsorship, or a formal
endorsement.

## License

Original DOOMed Prism / PewPew Engine code is licensed under GPL-2.0-or-later.
Crispy Doom is covered by its own upstream license; this repository contains
only the frame‑export and IPC‑input patches and a pinned reference to Crispy
Doom, never its source. Source distributions include the canonical GPL-2.0 text and deliberately
exclude the test suite, whose dependencies are development‑only.
