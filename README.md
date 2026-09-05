# DOOMed Prism

DOOMed Prism is the publication-safe Python foundation for the PewPew Engine
project. This repository intentionally contains no Raven framework code, Doom
game data, executables, shared libraries, or credentials.

## Development

Use Python 3.10 or later. Install development dependencies with:

```bash
python -m pip install -e '.[dev]'
```

Before committing, scan exactly the staged index. Before a release or public
handoff, also scan every object reachable from local branches and tags:

```bash
python scripts/check_publication_safety.py --root .
python scripts/check_publication_safety.py --root . --history
```

## Local Doom runtime

Install Crispy Doom and provide an IWAD locally. In PowerShell, set the paths
for the current session:

```powershell
$env:DOOMED_PRISM_CRISPY_EXE = "C:\path\to\crispy-doom.exe"
$env:DOOMED_PRISM_IWAD = "C:\path\to\freedoom1.wad"
```

You may instead point `DOOMED_PRISM_IWAD` to a lawfully obtained commercial
IWAD, but never add an IWAD to Git.

`DOOMED_PRISM_CRISPY_EXE` must point at Crispy Doom built by this project's
patch (see below) — a stock, unmodified Crispy Doom build will not export
frames, and the app will eventually raise "engine did not export frames".

### Building the patched engine

The app reads frames from a shared-memory segment that a small, committed
patch (`patches/crispy-doom-fb-export.diff`) adds to Crispy Doom. Build it
with `scripts/build_crispy.py` rather than a stock Crispy Doom checkout.

**Prerequisite:** a C toolchain plus SDL2, SDL2_mixer, and SDL2_net
development libraries.

- Windows (MSYS2 UCRT64):
  ```bash
  pacman -S mingw-w64-ucrt-x86_64-toolchain mingw-w64-ucrt-x86_64-cmake \
      mingw-w64-ucrt-x86_64-ninja mingw-w64-ucrt-x86_64-pkgconf \
      mingw-w64-ucrt-x86_64-SDL2 mingw-w64-ucrt-x86_64-SDL2_mixer \
      mingw-w64-ucrt-x86_64-SDL2_net
  ```
- Linux: install the equivalent toolchain and `libsdl2-dev`,
  `libsdl2-mixer-dev`, `libsdl2-net-dev` packages from your distribution.

**Usage:**

```bash
python scripts/build_crispy.py            # fetch the pinned tag, apply the
                                            # patch, and build; prints the
                                            # built executable path
python scripts/build_crispy.py --check     # verify the pin + that the patch
                                            # applies cleanly, no build
python scripts/build_crispy.py --check --offline  # same, but skip the tarball
                                            # download (commit pin still checked)
python scripts/build_crispy.py --clean     # remove the build directory
```

The pin in `crispy-doom.lock` is **enforced**, not just recorded: after the
clone, `commit` is compared against the checkout's `git rev-parse HEAD` (a moved
upstream tag aborts the run), and `tarball_sha256` is verified against the
GitHub tag archive (`.../archive/refs/tags/<tag>.tar.gz`), downloaded with the
Python standard library. Pass `--offline` to skip only that download (for
`--check` in a network-less sandbox); the default build path always performs it.

Point `DOOMED_PRISM_CRISPY_EXE` at the executable path the build prints.

**Windows git-on-`PATH` hazard:** MSYS2 ships its own `git` in
`C:\msys64\usr\bin`, and it can fail to apply
`patches/crispy-doom-fb-export.diff` where Git for Windows' `git` succeeds.
If `git apply` (or `scripts/build_crispy.py`) fails with "patch does not
apply" even though the patch is fine, make sure `C:\msys64\usr\bin` is not
ahead of Git for Windows on `PATH` — only `C:\msys64\ucrt64\bin` (the
compiler toolchain itself) is needed there.

**Windows runtime DLLs:** the built `crispy-doom.exe` dynamically links
SDL2, SDL2_mixer, and SDL2_net. Either add the toolchain's `bin` directory
(e.g. `C:\msys64\ucrt64\bin`) to `PATH` when launching it, or copy those
runtime DLLs next to the built executable.

Original PewPew Engine code is licensed under GPL-2.0-or-later. Source
distributions include the canonical GPL-2.0 text and deliberately exclude the
test suite, whose dependencies are development-only.
