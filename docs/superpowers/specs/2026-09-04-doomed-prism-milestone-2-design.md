# DOOMed Prism — Milestone 2 Design: Framebuffer Integration

Date: 2026-09-04
Status: Implemented and validated on the Windows / Raven Simulator target
(`docs/validation/milestone-2-result.md`: PASS). Cross-platform (POSIX / Linux /
ARM64) validation is intentionally outstanding — the `shm_open` branch is
code-reviewed, not built or run. No CI is established yet.
Depends on: `2026-09-02-doomed-prism-design.md` (§3, §4, §5, §8, §9)
Supersedes for the desktop path: the native-window embedding approach retired by
Milestone 1 (`docs/validation/milestone-1-result.md`).

## 0. Implementation deviations from this design (recorded 2026-09-05)

Building against the real `crispy-doom-7.1` source surfaced two constraints this
design did not anticipate. Both deviations were verified correct during the
Milestone 2 decision-gate run; §4–§7 below are kept as the design that was
approved, and this section is the authoritative record of where the shipped
code differs. Full detail: `docs/validation/milestone-2-result.md` and the
comments inside `patches/crispy-doom-fb-export.diff`.

1. **Not `crispy->hires = 0` / not a native 640×480 source.** The engine has no
   640×480 mode (`ORIGHEIGHT` is 200, not 240). The patch forces `hires = 1`
   and `widescreen = 0` (gated on `DOOMED_PRISM_FB_NAME`), producing a
   deterministic **640×400** source, which `FB_Export_Publish` nearest-neighbour
   row-maps into the fixed 640×480 wire-format slot using Crispy's own
   `6:5` (`actualheight = 6 * SCREENHEIGHT / 5`) aspect-correction ratio. The
   wire format itself is unchanged: 640×480, stride 2560. So the "pins 640×480
   non-hires" line in §2 and the `crispy->hires = 0` lines in §4/§5 describe the
   original intent, not the shipped behaviour.

2. **Frame publish only in the `CRISPY_TRUECOLOR` render path.** In the default
   (non-truecolor) path, `argbbuffer->pixels` aliases a GPU-locked, write-only
   streaming-texture region that segfaults on CPU read. `FB_Export_Publish` is
   therefore called only from the `CRISPY_TRUECOLOR` branch of `I_FinishUpdate`,
   and the top-level `CMakeLists.txt` option default is flipped `OFF → ON` so
   `scripts/build_crispy.py` produces a working export by default. §5's "publish
   immediately after `SDL_UpdateTexture`" holds only for that branch.

A follow-up runtime shape guard (`argb->w != FB_WIDTH || argb->pitch < FB_STRIDE
|| format != ARGB8888 → skip`) replaced the original one-time `assert`s, which
`-DNDEBUG` in a Release build compiled out.

## 1. Problem

Milestone 1 proved that a Win32-reparented native child window is invisible to
Raven Simulator. Raven Framework 1.0.4 composites the application through
`QWidget.grab()` in **every** mode: the optical modes blend
`self._app_widget.grab()` with a background video, and Raw also presents a
`grab()` result through `_composite_label`. `QWidget.grab()` renders only the
Qt widget tree and cannot capture a foreign native window attached with
`SetParent`. The Milestone 1 decision was `BLOCKED/RETRY`.

Milestone 2 makes DOOM frames land **inside a Qt widget** so the compositor
grabs them like any other painted content.

## 2. Scope

### In scope

- A minimal, opt-in Crispy Doom source patch that publishes each rendered
  frame into a shared-memory segment.
- A stdlib-only Python reader for that segment.
- A Qt host that paints the latest frame into the 640×480 viewport widget,
  with all native-window reparenting removed.
- A fetch-and-build script for the patched engine, pinned to an exact upstream
  Crispy Doom tag; no third-party source vendored into the repository.
- A Milestone 2 decision gate mirroring Milestone 1.

### Out of scope (YAGNI)

- The IPC socket and moving keyboard or gaze input off Crispy's SDL window
  (Milestone 3).
- Gaze zones, click-fire, voice commands, and "piu piu".
- Performance modes, the governor, and engine-versus-compositor metrics.
- ARM64 build validation and the shared OpenGL ES / Qt rendering surface
  (approach B; hardware phase).
- Waveguide Boost tuning. Milestone 2 checks only that additive compositing is
  correct, not that it is enhanced.
- Hires or multi-resolution export. Milestone 2 pins the wire format to
  640×480. (As built, the source is 640×400 hires and row-mapped to 640×480 —
  see §0; a native 640×480 source was the original intent but does not exist in
  this engine.)
- Audio. Crispy's default handling is left untouched and not evaluated.

## 3. Approaches considered

| Approach | Verdict |
| --- | --- |
| **A. Shared-memory framebuffer export** from a small Crispy Doom patch; Qt host paints it. | **Chosen.** Works with `QWidget.grab()`, keeps the two-process split (spec §4), portable (POSIX shm / Win32 file mapping), minimal auditable patch, trivial per-frame cost. |
| B. Shared OpenGL ES / Qt rendering surface (cross-process GL interop or in-process engine). | Deferred to the hardware phase. Cross-process GL sharing is platform-specific (`EGL_KHR_image`/DMA-BUF, WGL_NV_DX_interop); an in-process engine breaks the spec §4 isolation the governor needs. Premature for the simulator. |
| C. Pipe/socket frame streaming (no shared memory). | Fallback only. Simplest to implement but ~43–74 MB/s with extra copies and added latency. |

## 4. Architecture

Two processes as in spec §4. What changes: pixels stop flowing through a native
OS window and instead flow through a shared-memory triple-buffer that the Qt
host paints into a plain `QWidget`.

```
Crispy Doom process (patched)                 PewPew Engine process
  game loop -> I_FinishUpdate()                 DoomHostWidget (QWidget 640x640)
    +- SDL present to its own window              +- _DoomViewport (0,80,640,480)
    +- FB_Export_Publish(argbbuffer) --shm-->         paintEvent: QImage(slot) -> drawImage
  reads keyboard from its SDL window            FrameReader (mmap + atomic index)
```

### New and changed units

| Unit | Language | Responsibility | Depends on |
| --- | --- | --- | --- |
| `i_framebuffer_export.c` / `.h` (in the patch) | C | Own one shm segment; `FB_Export_Init(name)`, `FB_Export_Publish(SDL_Surface*)`, `FB_Export_Shutdown()` | `shm_open`/`mmap` or `CreateFileMapping`/`MapViewOfFile`; stdlib |
| `i_video.c` (in the patch) | C | ~10 lines: init once, publish right after `SDL_UpdateTexture`, shutdown in `I_ShutdownGraphics`; force `crispy_hires = 0` when export is active | the above |
| `pewpew.framebuffer` | Python | `FrameReader(name)` → `mmap`; `latest() -> Frame | None` | `mmap`, `struct` (stdlib) |
| `pewpew.host_widget` (modified) | Python | `_DoomViewport.paintEvent` draws `QImage` from `FrameReader.latest()`; a `QTimer` triggers repaint on counter change; **all `windows.py` use removed** | PySide6, `pewpew.framebuffer` |
| `pewpew.engine` (modified) | Python | `start()` generates the segment name, sets `DOOMED_PRISM_FB_NAME` in the child env, exposes `frame_segment_name`; `stop()` best-effort unlinks the POSIX path after the child exits | existing |
| `pewpew.win_close` (extracted) | Python | `request_close_windows(pid)` moved here from `windows.py` | `ctypes` (win32 only) |
| `scripts/build_crispy.py` | Python | Fetch pinned tag, verify, `git apply` the patch, CMake build, print the exe path; `--check`, `--clean` | local C toolchain, SDL2 dev libs |
| `patches/crispy-doom-fb-export.diff` | diff | The complete modification; GPL-2.0-or-later; corresponding source | — |
| `crispy-doom.lock` | TOML/JSON | `repo`, `tag`, `commit`, `tarball_sha256` | — |

`windows.py` and `tests/test_windows.py` are deleted. Milestone 1 retired that
approach.

## 5. Crispy Doom patch

**Hook point:** `i_video.c` → `I_FinishUpdate()`. Crispy already composes a full
32-bit frame into `argbbuffer->pixels` immediately before the existing
`SDL_UpdateTexture(...)` call. That is the single stable export point.

**Patch contents:**

- New `i_framebuffer_export.c` / `.h` with GPL-2.0-or-later headers matching
  Crispy. Portable shm: `#ifdef _WIN32` uses `CreateFileMappingA` /
  `MapViewOfFile`; otherwise `shm_open` / `ftruncate` / `mmap`. No third-party
  dependencies.
- About ten lines in `i_video.c`: include the header; `FB_Export_Init()` once
  in `I_InitGraphics` (guarded by `getenv("DOOMED_PRISM_FB_NAME")`);
  `FB_Export_Publish(argbbuffer)` immediately after `SDL_UpdateTexture`;
  `FB_Export_Shutdown()` in `I_ShutdownGraphics`.
- When `DOOMED_PRISM_FB_NAME` is set, force Crispy's hires setting off
  (`crispy->hires = 0` at the tag's config-struct name) so `argbbuffer` is
  deterministically 640×480 (stride 2560). Absent, the build is
  upstream-identical.

**Publish:** writer memcpys the pixel block into slot `(active_index + 1) % 3`,
then release-stores `active_index` and increments `frame_counter`. A one-time
assert checks `argb->format->format == SDL_PIXELFORMAT_ARGB8888` and
`argb->w == 640 && argb->h == 480`.

**Concurrency:** single-writer, single-reader, three slots, one atomic index.
The reader never retries and tearing is structurally impossible: the writer
never touches the slot the reader just latched or the one it will pick next.
This matches spec §3's existing "depth-one frame queue, drop when behind"
philosophy.

**Lifecycle:** `FB_Export_Init` does `shm_unlink` on the name before
`shm_open(O_CREAT)` to clear any stale segment; `FB_Export_Shutdown` unlinks
again. On an unclean crash the uniquely named ~3.7 MB segment leaks until
reboot; `DoomProcess.stop()` also unlinks the POSIX path after confirming the
child is dead. Windows mappings refcount away on handle close.

**GPL corresponding source:** the `.diff` plus the exact upstream repo, tag, and
commit in `crispy-doom.lock` is the complete modification record. No upstream C
is copied into this repository.

## 6. Shared-memory layout and the reader

Segment = a 64-byte header followed by three contiguous pixel slots. Total size
is fixed: `64 + 3 * stride * height` with `stride = 2560`, `height = 480` →
`64 + 3 * 1_228_800` = 3,686,464 bytes. Both sides compute this from 640×480; no
size negotiation.

### Header (little-endian, 64-byte aligned)

| Field | Type | Notes |
| --- | --- | --- |
| `magic` | u32 | `0x50504642` ("PPFB"); reader asserts |
| `version` | u32 | `1`; reader asserts |
| `slot_count` | u32 | `3` |
| `slot_bytes` | u32 | `stride * height` = 1,228,800 |
| `width` | u32 | 640 (validation only) |
| `height` | u32 | 480 (validation only) |
| `stride` | u32 | 2560 (= SDL `pitch`) |
| `pixel_format` | u32 | SDL enum for `ARGB8888`; reader asserts, maps to Qt `Format_RGB32` |
| `active_index` | u32 | atomic; slot most recently completed |
| `frame_counter` | u32 | monotonic; `0` = no frame yet; wrap is harmless (`!=` compare only) |
| `flags` | u32 | bit0 = producer shutting down |
| padding | — | to 64 bytes |

Slots start at offset 64; slot `i` pixels at `64 + i * slot_bytes`.

### `pewpew.framebuffer.FrameReader`

Stdlib only, no new dependency.

- **Open.** Windows: `mmap.mmap(-1, size, tagname=name, access=ACCESS_READ)`.
  POSIX: `fd = os.open(f"/dev/shm/{name}", os.O_RDONLY)`, then
  `mmap.mmap(fd, size, prot=mmap.PROT_READ)`. Validates `magic`, `version`,
  `pixel_format`; a mismatch raises `FrameSegmentError`.
- **`latest() -> Frame | None`.** Unpack the header. Return `None` when
  `frame_counter == 0`, or when `flags` bit0 is set. Otherwise return
  `Frame(width, height, stride, pixel_format, counter,
  buffer=memoryview(mmap)[off : off + slot_bytes])` — zero-copy. `counter` is
  re-read after computing `off` as a cheap guard.
- **`close()`.** Unmap; close the POSIX fd. Always safe; never depends on the
  producer.

`Frame.buffer` stays valid until the next `latest()` or `close()`. A slot is
stable for about two frame times, ample for a synchronous `paintEvent`.

## 7. The host

- `showEvent`: `engine.start()`, read `engine.frame_segment_name`, construct
  `FrameReader(name)`, start a `QTimer` at about 60 Hz. `FrameReader.open` is
  retried on each timer tick until it succeeds. Two conditions raise "engine did
  not export frames" and run cleanup: a 10 s bound elapsing with no readable
  segment, regardless of `engine.poll()`; or `engine.poll()` returning non-`None`
  before then.
- `_DoomViewport(QWidget)` with `paintEvent`: `f = reader.latest()`. When `f` is
  a frame, `img = QImage(f.buffer, f.width, f.height, f.stride,
  QImage.Format_RGB32)` then `painter.drawImage(self.rect(), img)`. When `f` is
  `None`, paint nothing; the widget stays transparent, which is correct for the
  additive display (spec §5).
- Timer tick: if `reader.latest()` reports a new `counter`, call
  `viewport.update()`; nothing otherwise.
- `_DoomViewport` is a normal Qt-painted widget. It needs no `WA_NativeWindow`
  and no `winId()`. `QWidget.grab()` captures its `paintEvent` output, so Raven
  composites the DOOM frame in Raw and every optical mode.
- No cross-process `SetParent`, so no DPI virtualization risk. The viewport is
  logical 640×480; the 640×480 frame blits 1:1 at 100% scaling.
- `hideEvent` stops the timer; `showEvent` restarts it if the engine has
  already started (Raven sleep/conceal, spec §8).
- `cleanup()`: stop the timer, `reader.close()`, then `engine.stop()`, in that
  order. `reader.close()` only unmaps and cannot fail on a dead child, which is
  the Milestone 1 teardown lesson (`EmbeddedWindow.restore()` raised
  `WinError 87`). Idempotent; wired to both `closeEvent` and
  `QApplication.aboutToQuit`.

## 8. Crispy Doom's window and keyboard for Milestone 2

Crispy still opens its normal SDL window and keeps SDL keyboard input, which is
sufficient for Milestone 2. It renders to that window and also publishes to the
shared segment.

The window is not reparented and not hidden. It sits as a separate small window
that the tester clicks to focus for keystrokes. The DOOM that is *evaluated* is
the Qt viewport; this extra window is a temporary development-time input sink
that Milestone 3's IPC input path removes.

## 9. Error handling and lifecycle

- **Segment slow or absent.** `FrameReader` retries open per timer tick and
  returns `None` meanwhile; the viewport is transparent. A 10 s bound with no
  readable segment raises and cleans up, as does an earlier non-`None`
  `engine.poll()`.
- **Producer death.** Clean: `flags` bit0 makes the host show a blank viewport
  at once. Crash: `engine.poll()` returns non-`None`; the host stops the timer.
  A frozen frame is never presented as live.
- **Stale or incompatible segment.** `magic`, `version`, or `pixel_format`
  mismatch raises `FrameSegmentError` and cleans up. The per-run random name
  plus the C-side `shm_unlink` on init make collisions negligible.
- **Cleanup ordering.** `reader.close()` before `engine.stop()`. No dependency
  on the child window still existing.
- **Raven sleep and wake (spec §8).** `hideEvent` stops the repaint timer;
  `showEvent` restarts it. No held-input concern, since keyboard is Crispy's
  SDL window.

## 10. Build and fetch

`scripts/build_crispy.py` with `crispy-doom.lock` (`repo`, `tag =
crispy-doom-7.1`, `commit <SHA>`, `tarball_sha256`):

- Clone or download that exact ref into a gitignored `build/crispy/`. Nothing is
  vendored.
- `git apply patches/crispy-doom-fb-export.diff`.
- `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build`.
  Print the built `crispy-doom` path. The developer points
  `DOOMED_PRISM_CRISPY_EXE` at it, exactly as in Milestone 1.
- Idempotent via a marker file. `--clean` removes the build directory.
  `--check` runs `git apply --check` only and is the patch-rot detector for CI.
- Prerequisites: a C toolchain and SDL2, SDL2_mixer, SDL2_net development
  libraries. MSYS2 / MinGW-w64 on Windows, system packages on Linux. A
  documented Milestone 2 developer prerequisite; CI builds it in a container.

## 11. Publication safety and licensing

- New tracked files are original and GPL-2.0-or-later, matching the project
  license: the `.diff`, `build_crispy.py`, `crispy-doom.lock`, the Python
  modules and tests, and the Milestone 2 documents.
- The unified `.diff` carries a few unchanged Crispy context lines per hunk.
  That is normal for a patch, is de minimis, and is the corresponding source
  for the modification. The exact upstream repo, tag, and commit are in
  `crispy-doom.lock` and this document.
- `.gitignore` gains `build/` and `*.egg-info/` (the latter a Milestone 1 loose
  end).
- `scripts/check_publication_safety.py` is unchanged. Build outputs are
  gitignored, the `.diff` is text, and no IWAD, Raven source, or binary enters
  git. The guarantees are those of Milestone 1.
- Before any public release (spec §9): ship the `.diff` as corresponding source
  with any distributed patched binary, and keep Crispy's `COPYING` and notices
  beside distributed builds.

## 12. Testing

All tests run without Crispy Doom, Raven Framework, a C toolchain, or a display,
on the Raven virtual environment's pytest 9.x as in Milestone 1.

- **`pewpew.framebuffer`.** A pure-Python `_FakeWriter` creates the mapping with
  the same Windows and POSIX branch, writes a header and a known pixel pattern
  into slot `(i + 1) % 3`, and bumps `active_index` and `frame_counter`.
  Assertions cover correct `width`, `height`, `stride`, `pixel_format`,
  `counter`, and exact bytes; `counter == 0` → `None`; `flags` bit0 → `None`;
  bad `magic` → `FrameSegmentError`; counter-advance detection; u32 wrap from
  `0xFFFFFFFF` to `0`.
- **`pewpew.host_widget`** with `pytest-qt` and an injected `_FakeReader` (the
  constructor gains a `frame_reader=` injectable): paint a fake frame, then
  `grab()` the widget and assert the grabbed `QImage` pixels match the fake
  frame. This directly proves the Milestone 1 failure is fixed. Also:
  `latest()` returns `None` → the viewport region is transparent; an unchanged
  counter triggers no `update()` (spy on `viewport.update`); `cleanup()` calls
  `reader.close()` then `engine.stop()` in that order (recorded on fakes), is
  idempotent, and runs on both `aboutToQuit` and `closeEvent`.
- **`pewpew.engine`.** `start()` sets `DOOMED_PRISM_FB_NAME` in the child
  environment (a fake `popen_factory` captures `env=`) and exposes
  `frame_segment_name` with the right shape and per-run uniqueness. `stop()`
  attempts the POSIX unlink after the child exits.
- **`scripts/build_crispy.py`.** Lock parsing, the idempotency marker, and
  argument and `--clean` handling with a fake command runner. A real build runs
  only under an opt-in `DOOMED_PRISM_BUILD_IT=1` and is skipped by default.
- **`tests/test_distribution_metadata.py`.** Update expectations for the new
  modules and scripts and the removal of `windows.py`.

## 13. Delivery sequence

1. `pewpew.framebuffer` reader plus its `_FakeWriter` tests.
2. The Crispy Doom patch and `i_framebuffer_export.c`, verified by a manual
   local build; `patches/crispy-doom-fb-export.diff` and `crispy-doom.lock`
   committed.
3. `scripts/build_crispy.py` with `--check` and `--clean`, and its unit tests.
4. `pewpew.engine` changes: segment name generation, child environment,
   `frame_segment_name`, `stop()` unlink; `pewpew.win_close` extraction.
5. `pewpew.host_widget` rewrite to the framebuffer path; delete `windows.py`
   and `tests/test_windows.py`; update `test_distribution_metadata.py`.
6. `.gitignore` updates; full `pytest -q` and `check_publication_safety.py`
   green.
7. `docs/validation/milestone-2-checklist.md`; run the decision gate; record
   `docs/validation/milestone-2-result.md`.

## 14. Milestone 2 decision gate

Run manually on Windows against a separately installed Raven Framework. Keep all
evidence under gitignored `artifacts/milestone-2/`. Record no Raven source,
credentials, private paths, or commercial IWAD identity.

**The hard question.** Do live, updating DOOM pixels appear inside the Qt
viewport and get captured by Raven's `QWidget.grab()` compositor in Raw and
every optical mode?

**Environment and launch.** `python scripts/build_crispy.py` succeeds; record
the pinned tag and commit from `crispy-doom.lock`, the compiler and SDL2
versions, and confirm `build_crispy.py --check` passes. Set
`DOOMED_PRISM_CRISPY_EXE` to the built engine and `DOOMED_PRISM_IWAD` to a
lawfully held IWAD. `doomed-prism validate` exits 0. Establish a clean
crispy-doom PID baseline with Milestone 1's before/after procedure. Confirm
100% display scaling, `python -m pytest -q` green, and
`check_publication_safety.py --root .` exit 0. Run `doomed-prism run-desktop`.

**Objective checks.** Exactly one new crispy-doom PID. The shared-memory
segment exists while running and `frame_counter` advances, probed with a small
`FrameReader` script, which proves the export path is live independently of Qt.
The viewport widget geometry is `(0, 80, 640, 480)` inside the 640×640 host,
with both 80-pixel margins and the Raven home control uncovered. No
cross-process `SetParent` exists anywhere in the window tree.

**Per-mode evidence.** For Raw, Night, Day, Outdoors, and Camera, record with
two time-separated captures or one short local video:

- live DOOM pixels appear inside the Qt viewport within the app surface;
- frames visibly update while the game runs; the attract loop is sufficient;
- the viewport stays at `(0, 80, 640, 480)`;
- Raven Simulator's app capture includes the DOOM frame rather than a blank or
  grey-fill rectangle;
- in the optical modes, DOOM's dark areas read as transparent, not as an opaque
  panel (spec §5);
- a keypress in Crispy's separate SDL window produces a state change that is
  visible in the Qt viewport, which proves the shared-memory path tracks real
  gameplay and not only the attract loop. Full playability is Milestone 3.

**Cleanup.** Close Raven Simulator normally. The one crispy-doom PID is gone
with no orphan. `cleanup()` runs reader-close then engine-stop with no
exception; the Milestone 1 teardown raised, and Milestone 2 must not. The
segment is removed, or leaks and is unlinked by `stop()` per section 9.

**Hard decision, recorded in the single final field of
`docs/validation/milestone-2-result.md`.**

- **PASS — framebuffer integration viable.** Live, updating DOOM pixels appear
  inside the viewport and are captured in Raw and every available optical mode;
  geometry, margins, and the home control are correct; additive compositing is
  correct; a keyboard-driven state change reaches the viewport; the lifecycle
  is a clean single PID with no teardown exception.
- **FAIL — framebuffer path insufficient.** The export path is live, with the
  segment counter advancing, but the Qt viewport is still not captured in an
  available optical mode, or additive compositing is wrong, for example an
  opaque black. This opens a design task for approach B, a shared OpenGL ES or
  Qt rendering surface, or an in-process rendering path.
- **BLOCKED/RETRY — implementation or environment failure.** Build, launch,
  geometry, DPI, segment creation, cleanup, or required evidence fails. Fix the
  named issue and repeat the whole run with a fresh PID. This outcome does not
  select an architecture.
- **PENDING — incomplete evidence.** Evidence remains incomplete or a named
  optical mode is unavailable without a documented reason. This is not a
  passing result.

**Final automated verification and commit.** As in Milestone 1: `python -m
pytest -q`, `git diff --check`, an exact-path `git add` of only
`docs/validation/milestone-2-checklist.md` and
`docs/validation/milestone-2-result.md`, `check_publication_safety.py --root .`
and `--history`, then `git commit -m "docs: record framebuffer integration
result"`.

## 15. Exit criteria

Milestone 2 is complete when all automated tests pass, the publication-safety
scan is clean, and `milestone-2-result.md` records a reproducible PASS or FAIL.
A FAIL is a valid engineering result: it retires the shared-memory framebuffer
path before hardware work and moves the decision to approach B.
