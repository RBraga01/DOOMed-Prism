# DOOMed Prism Milestone 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make live, updating DOOM frames appear inside the Qt viewport widget so Raven Simulator's `QWidget.grab()` compositor captures them in Raw and every optical mode.

**Architecture:** A small opt-in Crispy Doom patch copies each rendered frame into a shared-memory triple-buffer. A stdlib-only Python reader maps that segment. The Qt host paints the latest frame into a plain `QWidget` on a repaint timer, and all Win32 native-window reparenting is deleted. Crispy Doom is fetched and built from a pinned upstream tag by a script; no third-party source is vendored.

**Tech Stack:** Python 3.10+, PySide6 (Raven extra), pytest, `mmap`/`struct` (stdlib), C99 + SDL2 + CMake for the engine patch, Windows `ctypes` for the graceful-close helper.

**Spec:** `docs/superpowers/specs/2026-09-04-doomed-prism-milestone-2-design.md`

## Global Constraints

- Every commit must be safe to publish. Never commit Raven-owned source, commercial IWADs, credentials, generated binaries, screenshots with private data, or vendored third-party engine source. The only new tracked engine artifact is `patches/crispy-doom-fb-export.diff` (original work, GPL-2.0-or-later).
- Automated tests run without Crispy Doom, Raven Framework, an IWAD, a C toolchain, or a display, using project-owned fakes.
- The only accepted viewport is 640×480 at `(0, 80)` inside the writable 640×640 app surface.
- The export path is pinned to 640×480 non-hires. No hires or multi-resolution export in this milestone.
- Do not treat black pixels as opaque. In optical modes DOOM's dark areas must read as transparent (additive display).
- Do not add the IPC socket, gaze/blink/voice input, performance modes, the governor, ARM64 build validation, or the OpenGL ES surface in this milestone.
- Do not use screen scraping, desktop capture, or video streaming to disguise a failed integration.
- Shared-memory segment layout is little-endian. The header is 64 bytes; three pixel slots of `2560 * 480 = 1_228_800` bytes each follow; total segment size is `3_686_464` bytes.
- Branch: `feature/doomed-prism-m2` (already created from `c59cef5`).

---

## Task 1: Shared-memory frame reader

**Files:**
- Create: `src/pewpew/framebuffer.py`
- Create: `tests/fakes/fake_framebuffer.py`
- Create: `tests/test_framebuffer.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - Module constants: `HEADER_SIZE = 64`, `SLOT_COUNT = 3`, `WIDTH = 640`, `HEIGHT = 480`, `STRIDE = 2560`, `SLOT_BYTES = 1_228_800`, `SEGMENT_SIZE = 3_686_464`, `MAGIC = 0x50504642`, `VERSION = 1`, `PIXEL_FORMAT_ARGB8888 = 0x16362004`, `FLAG_SHUTTING_DOWN = 0x1`.
  - `class FrameSegmentError(RuntimeError)` — raised when a segment exists but its header is wrong or incompatible.
  - `@dataclass(frozen=True) class Frame` with fields `width: int`, `height: int`, `stride: int`, `pixel_format: int`, `counter: int`, `buffer: memoryview`.
  - `class FrameReader`:
    - `__init__(self, name: str) -> None`
    - `try_open(self) -> bool` — returns `False` when the segment does not exist yet; returns `True` once mapped; raises `FrameSegmentError` when the segment exists but `magic`/`version`/`pixel_format` are wrong. Idempotent once open.
    - `latest(self) -> Frame | None` — `None` when not open, when `frame_counter == 0`, or when `FLAG_SHUTTING_DOWN` is set; otherwise a zero-copy `Frame` whose `buffer` views the active slot.
    - `close(self) -> None` — idempotent; unmaps and closes the POSIX fd.
    - `is_open` property → `bool`.
  - `tests/fakes/fake_framebuffer.py`: `class FakeFramebufferWriter` with `__init__(self, name: str)`, `write_frame(self, pixels: bytes) -> int` (returns the new counter), `set_shutting_down(self) -> None`, `write_raw_header(self, *, magic=MAGIC, version=VERSION, pixel_format=PIXEL_FORMAT_ARGB8888) -> None`, `close(self) -> None`, and `unlink(self) -> None`. It creates a real segment with the same Windows-tagname / POSIX-`/dev/shm` branch the reader uses, so the real `FrameReader` reads it.

- [ ] **Step 1: Write the failing reader tests**

Create `tests/fakes/fake_framebuffer.py` first with the minimum needed by the tests:

```python
"""A project-owned shared-memory writer for exercising the real FrameReader."""

from __future__ import annotations

import mmap
import os
import struct
import sys

from pewpew.framebuffer import (
    FLAG_SHUTTING_DOWN,
    HEADER_SIZE,
    MAGIC,
    PIXEL_FORMAT_ARGB8888,
    SEGMENT_SIZE,
    SLOT_BYTES,
    SLOT_COUNT,
    STRIDE,
    VERSION,
    HEIGHT,
    WIDTH,
)

_HEADER = struct.Struct("<11I")


class FakeFramebufferWriter:
    """Creates and fills a real segment the same way the C exporter will."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._counter = 0
        self._active = 0
        self._flags = 0
        if sys.platform == "win32":
            self._fd = -1
            self._map = mmap.mmap(-1, SEGMENT_SIZE, tagname=name)
        else:
            path = f"/dev/shm/{name}"
            self._fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            os.ftruncate(self._fd, SEGMENT_SIZE)
            self._map = mmap.mmap(self._fd, SEGMENT_SIZE)
        self._write_header()

    def _write_header(
        self,
        *,
        magic: int = MAGIC,
        version: int = VERSION,
        pixel_format: int = PIXEL_FORMAT_ARGB8888,
    ) -> None:
        self._map[0:HEADER_SIZE] = b"\x00" * HEADER_SIZE
        self._map[0 : _HEADER.size] = _HEADER.pack(
            magic,
            version,
            SLOT_COUNT,
            SLOT_BYTES,
            WIDTH,
            HEIGHT,
            STRIDE,
            pixel_format,
            self._active,
            self._counter,
            self._flags,
        )

    def write_raw_header(
        self,
        *,
        magic: int = MAGIC,
        version: int = VERSION,
        pixel_format: int = PIXEL_FORMAT_ARGB8888,
    ) -> None:
        self._write_header(magic=magic, version=version, pixel_format=pixel_format)

    def write_frame(self, pixels: bytes) -> int:
        if len(pixels) != SLOT_BYTES:
            raise ValueError("frame payload must be exactly one slot")
        self._active = (self._active + 1) % SLOT_COUNT
        offset = HEADER_SIZE + self._active * SLOT_BYTES
        self._map[offset : offset + SLOT_BYTES] = pixels
        self._counter = (self._counter + 1) & 0xFFFFFFFF
        self._write_header()
        return self._counter

    def set_shutting_down(self) -> None:
        self._flags |= FLAG_SHUTTING_DOWN
        self._write_header()

    def close(self) -> None:
        self._map.close()
        if self._fd != -1:
            os.close(self._fd)
            self._fd = -1

    def unlink(self) -> None:
        if sys.platform != "win32":
            try:
                os.unlink(f"/dev/shm/{self._name}")
            except OSError:
                pass
```

Then `tests/test_framebuffer.py`:

```python
"""Tests for the stdlib-only shared-memory frame reader."""

from __future__ import annotations

import secrets

import pytest

from fakes.fake_framebuffer import FakeFramebufferWriter
from pewpew.framebuffer import (
    PIXEL_FORMAT_ARGB8888,
    SLOT_BYTES,
    STRIDE,
    FrameReader,
    FrameSegmentError,
)


@pytest.fixture
def segment_name() -> str:
    return f"doomed-prism-fb-test-{secrets.token_hex(4)}"


@pytest.fixture
def writer(segment_name: str):
    writer = FakeFramebufferWriter(segment_name)
    try:
        yield writer
    finally:
        writer.close()
        writer.unlink()


def test_try_open_is_false_until_the_segment_exists(segment_name: str) -> None:
    # POSIX: /dev/shm/<name> is absent. Windows: try_open maps a fresh zero
    # segment and rejects the all-zero header as not-ready. Both return False.
    reader = FrameReader(segment_name)
    assert reader.try_open() is False
    assert reader.is_open is False


def test_latest_is_none_before_the_first_frame(writer, segment_name: str) -> None:
    reader = FrameReader(segment_name)
    assert reader.try_open() is True
    assert reader.latest() is None
    reader.close()


def test_latest_returns_the_active_slot_bytes_and_counter(
    writer, segment_name: str
) -> None:
    first = bytes([0x11]) * SLOT_BYTES
    second = bytes([0x22]) * SLOT_BYTES
    writer.write_frame(first)
    counter = writer.write_frame(second)

    reader = FrameReader(segment_name)
    reader.try_open()
    frame = reader.latest()

    assert frame is not None
    assert (frame.width, frame.height, frame.stride) == (640, 480, STRIDE)
    assert frame.pixel_format == PIXEL_FORMAT_ARGB8888
    assert frame.counter == counter
    assert bytes(frame.buffer) == second
    reader.close()


def test_counter_advance_is_visible_on_the_next_latest(
    writer, segment_name: str
) -> None:
    writer.write_frame(bytes(SLOT_BYTES))
    reader = FrameReader(segment_name)
    reader.try_open()
    first = reader.latest().counter
    writer.write_frame(bytes(SLOT_BYTES))
    second = reader.latest().counter

    assert second != first
    reader.close()


def test_shutting_down_flag_makes_latest_none(writer, segment_name: str) -> None:
    writer.write_frame(bytes(SLOT_BYTES))
    writer.set_shutting_down()

    reader = FrameReader(segment_name)
    reader.try_open()
    assert reader.latest() is None
    reader.close()


def test_bad_magic_raises_frame_segment_error(writer, segment_name: str) -> None:
    writer.write_raw_header(magic=0xDEADBEEF)
    reader = FrameReader(segment_name)
    with pytest.raises(FrameSegmentError):
        reader.try_open()


def test_unexpected_pixel_format_raises_frame_segment_error(
    writer, segment_name: str
) -> None:
    writer.write_raw_header(pixel_format=0x12345678)
    reader = FrameReader(segment_name)
    with pytest.raises(FrameSegmentError):
        reader.try_open()


def test_close_is_idempotent(writer, segment_name: str) -> None:
    reader = FrameReader(segment_name)
    reader.try_open()
    reader.close()
    reader.close()
    assert reader.is_open is False
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_framebuffer.py -q`

Expected: FAIL — `pewpew.framebuffer` does not exist yet.

- [ ] **Step 3: Implement `pewpew.framebuffer`**

```python
"""Stdlib-only reader for the Crispy Doom shared-memory frame segment."""

from __future__ import annotations

import mmap
import os
import struct
import sys
from dataclasses import dataclass

HEADER_SIZE = 64
SLOT_COUNT = 3
WIDTH = 640
HEIGHT = 480
STRIDE = WIDTH * 4
SLOT_BYTES = STRIDE * HEIGHT
SEGMENT_SIZE = HEADER_SIZE + SLOT_COUNT * SLOT_BYTES
MAGIC = 0x50504642
VERSION = 1
PIXEL_FORMAT_ARGB8888 = 0x16362004
FLAG_SHUTTING_DOWN = 0x1

_HEADER = struct.Struct("<11I")


class FrameSegmentError(RuntimeError):
    """Raised when a segment exists but its header is wrong or incompatible."""


@dataclass(frozen=True)
class Frame:
    """One decoded frame view. ``buffer`` is valid until the next reader call."""

    width: int
    height: int
    stride: int
    pixel_format: int
    counter: int
    buffer: memoryview


class FrameReader:
    """Map a named segment read-only and hand out the most recent frame."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._fd = -1
        self._map: mmap.mmap | None = None

    @property
    def is_open(self) -> bool:
        return self._map is not None

    def try_open(self) -> bool:
        if self._map is not None:
            return True
        try:
            self._map = self._map_segment()
        except FileNotFoundError:
            self._fd = -1
            return False
        fields = _HEADER.unpack(self._map[0 : _HEADER.size])
        magic, version, pixel_format = fields[0], fields[1], fields[7]
        # On Windows, mmap with a tagname creates a fresh zero-filled mapping
        # when the name does not exist yet. Treat an all-zero header as
        # "producer has not written it yet" and retry, rather than as an error.
        if magic == 0 and version == 0:
            self.close()
            return False
        if (
            magic != MAGIC
            or version != VERSION
            or pixel_format != PIXEL_FORMAT_ARGB8888
        ):
            self.close()
            raise FrameSegmentError(
                f"segment {self._name!r} header is invalid or unsupported"
            )
        return True

    def latest(self) -> Frame | None:
        mapping = self._map
        if mapping is None:
            return None
        fields = _HEADER.unpack(mapping[0 : _HEADER.size])
        (_magic, _version, _slots, _slot_bytes, width, height, stride,
         pixel_format, active_index, frame_counter, flags) = fields
        if frame_counter == 0 or flags & FLAG_SHUTTING_DOWN:
            return None
        offset = HEADER_SIZE + active_index * SLOT_BYTES
        buffer = memoryview(mapping)[offset : offset + SLOT_BYTES]
        counter_after = _HEADER.unpack(mapping[0 : _HEADER.size])[9]
        return Frame(width, height, stride, pixel_format, counter_after, buffer)

    def close(self) -> None:
        if self._map is not None:
            self._map.close()
            self._map = None
        if self._fd != -1:
            os.close(self._fd)
            self._fd = -1

    def _map_segment(self) -> mmap.mmap:
        if sys.platform == "win32":
            try:
                return mmap.mmap(
                    -1, SEGMENT_SIZE, tagname=self._name, access=mmap.ACCESS_READ
                )
            except OSError as error:  # tag does not exist yet
                raise FileNotFoundError(self._name) from error
        path = f"/dev/shm/{self._name}"
        self._fd = os.open(path, os.O_RDONLY)
        return mmap.mmap(self._fd, SEGMENT_SIZE, prot=mmap.PROT_READ)
```

- [ ] **Step 4: Run the tests and the whole suite**

Run:

```bash
python -m pytest tests/test_framebuffer.py -q
python -m pytest -q
```

Expected: the new file passes; the rest of the suite is unchanged and green.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/framebuffer.py tests/fakes/fake_framebuffer.py tests/test_framebuffer.py
git commit -m "feat: add shared-memory frame reader"
```

## Task 2: Crispy Doom frame-export patch

This task produces two tracked artifacts — `patches/crispy-doom-fb-export.diff` and `crispy-doom.lock` — plus a manual integration check. It requires a local C toolchain, SDL2/SDL2_mixer/SDL2_net development libraries, CMake, and Git. It does **not** add pytest coverage; its verification is the integration check in Step 6.

**Files:**
- Create: `patches/crispy-doom-fb-export.diff`
- Create: `crispy-doom.lock`
- Working tree only (not committed): a Crispy Doom checkout under `build/crispy/`

**Interfaces:**
- Consumes: `pewpew.framebuffer.FrameReader` and its constants (Task 1) for the integration check.
- Produces:
  - `crispy-doom.lock` (TOML): keys `repo` (string URL), `tag` (string, `"crispy-doom-7.1"`), `commit` (40-hex string), `tarball_sha256` (64-hex string of the tag's source tarball).
  - The patch adds `src/i_framebuffer_export.c` and `src/i_framebuffer_export.h` to Crispy and modifies `src/i_video.c`. Public C API in the header:
    - `void FB_Export_Init(void);` — reads `DOOMED_PRISM_FB_NAME`; if unset, all functions become no-ops. Creates the segment, `shm_unlink`/tag-recreates to clear any stale one, writes the header with `width=640 height=480 stride=2560`.
    - `void FB_Export_Publish(SDL_Surface *argb);` — asserts `argb->w == 640 && argb->h == 480` and `argb->format->format == SDL_PIXELFORMAT_ARGB8888`; copies `argb->pixels` into slot `(active+1)%3`; release-stores `active_index`; increments `frame_counter` (u32 wrap).
    - `void FB_Export_Shutdown(void);` — sets `FLAG_SHUTTING_DOWN`, unmaps, and `shm_unlink`s (POSIX).

- [ ] **Step 1: Pin and fetch upstream Crispy Doom**

```bash
mkdir -p build
git clone --branch crispy-doom-7.1 https://github.com/fabiangreffrath/crispy-doom build/crispy
cd build/crispy
git rev-parse HEAD          # record this as crispy-doom.lock commit
cd ../..
```

Create `crispy-doom.lock`:

```toml
repo = "https://github.com/fabiangreffrath/crispy-doom"
tag = "crispy-doom-7.1"
commit = "<40-hex from git rev-parse HEAD above>"
tarball_sha256 = "<sha256 of https://github.com/fabiangreffrath/crispy-doom/archive/refs/tags/crispy-doom-7.1.tar.gz>"
```

Compute the tarball hash:

```bash
curl -L -o build/crispy-7.1.tar.gz https://github.com/fabiangreffrath/crispy-doom/archive/refs/tags/crispy-doom-7.1.tar.gz
sha256sum build/crispy-7.1.tar.gz
```

- [ ] **Step 2: Add `src/i_framebuffer_export.h` in the checkout**

```c
//
// Copyright(C) 2026 DOOMed Prism contributors
//
// This program is free software; you can redistribute it and/or
// modify it under the terms of the GNU General Public License
// as published by the Free Software Foundation; either version 2
// of the License, or (at your option) any later version.
//
// DOOMed Prism: publish each rendered frame into a shared-memory
// triple-buffer for an external Qt host. Active only when the
// environment variable DOOMED_PRISM_FB_NAME is set.
//

#ifndef I_FRAMEBUFFER_EXPORT_H
#define I_FRAMEBUFFER_EXPORT_H

#include "SDL.h"

void FB_Export_Init(void);
void FB_Export_Publish(SDL_Surface *argb);
void FB_Export_Shutdown(void);

#endif
```

- [ ] **Step 3: Add `src/i_framebuffer_export.c` in the checkout**

Skeleton to adapt (GPL-2.0-or-later header identical in spirit to the `.h`; the
POSIX path is shown in full, the Windows path is the marked `#else` branch):

```c
#include <assert.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "i_framebuffer_export.h"

#ifdef _WIN32
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#endif

#define FB_HEADER_SIZE 64
#define FB_SLOT_COUNT 3
#define FB_WIDTH 640
#define FB_HEIGHT 480
#define FB_STRIDE 2560
#define FB_SLOT_BYTES (FB_STRIDE * FB_HEIGHT)          /* 1228800 */
#define FB_SEGMENT_SIZE (FB_HEADER_SIZE + FB_SLOT_COUNT * FB_SLOT_BYTES)
#define FB_MAGIC 0x50504642u
#define FB_VERSION 1u
#define FB_PIXFMT_ARGB8888 0x16362004u
#define FB_FLAG_SHUTTING_DOWN 0x1u

static int fb_enabled = 0;
static const char *fb_name = NULL;
static unsigned char *fb_base = NULL;
static uint32_t fb_active = 0;
static uint32_t fb_counter = 0;
#ifdef _WIN32
static HANDLE fb_handle = NULL;
#else
static int fb_fd = -1;
#endif

static void fb_write_header(uint32_t flags)
{
    uint32_t *h = (uint32_t *) fb_base;
    h[0] = FB_MAGIC;      h[1] = FB_VERSION;   h[2] = FB_SLOT_COUNT;
    h[3] = FB_SLOT_BYTES; h[4] = FB_WIDTH;     h[5] = FB_HEIGHT;
    h[6] = FB_STRIDE;     h[7] = FB_PIXFMT_ARGB8888;
    h[8] = fb_active;     h[9] = fb_counter;   h[10] = flags;
}

void FB_Export_Init(void)
{
    fb_name = getenv("DOOMED_PRISM_FB_NAME");
    if (fb_name == NULL || fb_name[0] == '\0') { fb_enabled = 0; return; }

#ifdef _WIN32
    fb_handle = CreateFileMappingA(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE,
                                   0, FB_SEGMENT_SIZE, fb_name);
    if (fb_handle == NULL) { fb_enabled = 0; return; }
    fb_base = (unsigned char *) MapViewOfFile(fb_handle, FILE_MAP_ALL_ACCESS,
                                              0, 0, FB_SEGMENT_SIZE);
#else
    shm_unlink(fb_name);
    fb_fd = shm_open(fb_name, O_CREAT | O_RDWR, 0600);
    if (fb_fd < 0) { fb_enabled = 0; return; }
    if (ftruncate(fb_fd, FB_SEGMENT_SIZE) != 0) { close(fb_fd); fb_enabled = 0; return; }
    fb_base = mmap(NULL, FB_SEGMENT_SIZE, PROT_READ | PROT_WRITE,
                   MAP_SHARED, fb_fd, 0);
#endif
    if (fb_base == NULL) { fb_enabled = 0; return; }
    memset(fb_base, 0, FB_HEADER_SIZE);
    fb_active = 0; fb_counter = 0;
    fb_write_header(0);
    fb_enabled = 1;
}

void FB_Export_Publish(SDL_Surface *argb)
{
    if (!fb_enabled) { return; }
    assert(argb->w == FB_WIDTH && argb->h == FB_HEIGHT);
    assert(argb->format->format == SDL_PIXELFORMAT_ARGB8888);
    uint32_t next = (fb_active + 1u) % FB_SLOT_COUNT;
    memcpy(fb_base + FB_HEADER_SIZE + next * FB_SLOT_BYTES,
           argb->pixels, FB_SLOT_BYTES);
    atomic_thread_fence(memory_order_release);
    fb_active = next;
    fb_counter = fb_counter + 1u;   /* u32 wrap is intentional */
    fb_write_header(0);
}

void FB_Export_Shutdown(void)
{
    if (!fb_enabled) { return; }
    fb_write_header(FB_FLAG_SHUTTING_DOWN);
#ifdef _WIN32
    UnmapViewOfFile(fb_base);
    CloseHandle(fb_handle);
#else
    munmap(fb_base, FB_SEGMENT_SIZE);
    close(fb_fd);
    shm_unlink(fb_name);
#endif
    fb_enabled = 0;
    fb_base = NULL;
}
```

Notes: link `-lrt` on Linux for `shm_open` if the toolchain needs it (CMake:
`target_link_libraries(... rt)` guarded by `if(NOT WIN32)`). The header write
after `memcpy` doubles as the release publish of `active_index` and
`frame_counter`; a reader that re-reads the counter around its copy sees a
consistent pair.

- Layout constants match `pewpew.framebuffer`: `HEADER_SIZE 64`, `SLOT_COUNT 3`, width 640, height 480, stride 2560, `SLOT_BYTES 1228800`, `SEGMENT_SIZE 3686464`, `MAGIC 0x50504642`, `VERSION 1`, `PIXEL_FORMAT_ARGB8888 0x16362004`, `FLAG_SHUTTING_DOWN 0x1`.
- Header is 11 little-endian `uint32_t`: `magic, version, slot_count, slot_bytes, width, height, stride, pixel_format, active_index, frame_counter, flags`.
- `FB_Export_Init`: `name = getenv("DOOMED_PRISM_FB_NAME")`; if `NULL`, set an internal `enabled = 0` and return. POSIX: `shm_unlink(name)` (ignore errors), `fd = shm_open(name, O_CREAT|O_RDWR, 0600)`, `ftruncate(fd, SEGMENT_SIZE)`, `base = mmap(NULL, SEGMENT_SIZE, PROT_READ|PROT_WRITE, MAP_SHARED, fd, 0)`. Windows: `h = CreateFileMappingA(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, SEGMENT_SIZE, name)`, `base = MapViewOfFile(h, FILE_MAP_ALL_ACCESS, 0, 0, SEGMENT_SIZE)`. Zero the header, then write it with `active_index=0`, `frame_counter=0`, `flags=0`.
- `FB_Export_Publish`: if `!enabled` return. `assert(argb->w == 640 && argb->h == 480)`. `assert(argb->format->format == SDL_PIXELFORMAT_ARGB8888)`. `next = (active + 1) % 3`. `memcpy((char*)base + HEADER_SIZE + next*SLOT_BYTES, argb->pixels, SLOT_BYTES)`. Full memory barrier (`__atomic_thread_fence(__ATOMIC_RELEASE)` or `MemoryBarrier()`), write `active_index = next`, `frame_counter = ++counter` (u32). `active = next`.
- `FB_Export_Shutdown`: if `!enabled` return. Set `flags |= FLAG_SHUTTING_DOWN` in the header. POSIX: `munmap`, `close(fd)`, `shm_unlink(name)`. Windows: `UnmapViewOfFile`, `CloseHandle`.

- [ ] **Step 4: Wire `src/i_video.c` and the build in the checkout**

- Add `#include "i_framebuffer_export.h"` near the other includes.
- In `I_InitGraphics`, after the renderer and `argbbuffer` are created: if `getenv("DOOMED_PRISM_FB_NAME")` is set, force the hires setting off using the tag's config-struct field (in `crispy-doom-7.1` this is `crispy->hires = 0;`) **before** the surfaces are sized, then call `FB_Export_Init();`. If the code path requires hires to be decided earlier, set it at the top of `I_InitGraphics` guarded by the same `getenv` check.
- In `I_FinishUpdate`, immediately after the existing `SDL_UpdateTexture(texture, NULL, argbbuffer->pixels, argbbuffer->pitch);` call, add `FB_Export_Publish(argbbuffer);`.
- In `I_ShutdownGraphics`, add `FB_Export_Shutdown();` before the existing teardown.
- Add `i_framebuffer_export.c` to `src/CMakeLists.txt` in the `crispy-doom`/`SOURCE_FILES` list next to `i_video.c`.

- [ ] **Step 5: Build the patched engine**

```bash
cd build/crispy
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
# note the built executable, e.g. build/src/crispy-doom(.exe)
cd ../..
```

- [ ] **Step 6: Integration check with the real reader**

Create a throwaway script `build/probe.py` (not committed):

```python
import os, sys, time
sys.path.insert(0, "src")
from pewpew.framebuffer import FrameReader

name = "doomed-prism-fb-probe"
os.environ["DOOMED_PRISM_FB_NAME"] = name
# launch the built engine yourself in another shell with:
#   DOOMED_PRISM_FB_NAME=doomed-prism-fb-probe \
#   build/crispy/build/src/crispy-doom -iwad <iwad> -window -width 640 -height 480
reader = FrameReader(name)
while not reader.try_open():
    time.sleep(0.1)
seen = set()
for _ in range(120):
    f = reader.latest()
    if f:
        seen.add(f.counter)
    time.sleep(0.05)
print("distinct counters:", len(seen), "sample:", sorted(seen)[:5])
assert len(seen) > 10, "frame counter is not advancing"
print("OK: frames are advancing")
```

Run the built engine with `DOOMED_PRISM_FB_NAME=doomed-prism-fb-probe` and a lawful IWAD, then run `python build/probe.py`. Expected: `OK: frames are advancing`. Close the engine; confirm `/dev/shm/doomed-prism-fb-probe` is gone (POSIX).

- [ ] **Step 7: Generate the patch**

```bash
cd build/crispy
git add -A src/
git diff --cached > ../../patches/crispy-doom-fb-export.diff
git reset --hard && git clean -fd src/      # restore the pinned tag, patch now lives only in the .diff
git apply --check ../../patches/crispy-doom-fb-export.diff && echo "applies cleanly to a clean checkout"
cd ../..
```

`patches/crispy-doom-fb-export.diff` must be a single unified diff with `a/` and
`b/` prefixes rooted at the Crispy checkout (`src/i_video.c`,
`src/CMakeLists.txt`, and the two new `src/i_framebuffer_export.*` files). The
checkout is left clean; Task 3's `scripts/build_crispy.py` re-applies the patch
and rebuilds, and `--check` is its permanent regression guard.

- [ ] **Step 8: Commit the patch and lock**

```bash
git add patches/crispy-doom-fb-export.diff crispy-doom.lock
git commit -m "feat: add Crispy Doom shared-memory frame-export patch"
```

## Task 3: Engine fetch-and-build script

**Files:**
- Create: `scripts/build_crispy.py`
- Create: `tests/test_build_crispy.py`

**Interfaces:**
- Consumes: `crispy-doom.lock` and `patches/crispy-doom-fb-export.diff` (Task 2).
- Produces:
  - `load_lock(path: pathlib.Path) -> Lock` where `Lock` is a frozen dataclass with `repo: str`, `tag: str`, `commit: str`, `tarball_sha256: str`.
  - `plan_commands(lock: Lock, *, build_dir: pathlib.Path, patch: pathlib.Path, check_only: bool) -> list[list[str]]` — the exact command list, so tests assert it without running anything.
  - `run(argv: list[str] | None = None, *, runner=subprocess.run) -> int` — CLI entry. Flags: none (default build), `--check` (only `git apply --check`), `--clean` (remove `build_dir`, then exit 0). Idempotency: skips clone when `build_dir/.git` exists; skips `git apply` when `build_dir/.doomed-prism-applied` exists and, on a real apply, writes that marker.
  - `main()` wired to `pyproject.toml` is **not** added; the script is invoked as `python scripts/build_crispy.py`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the Crispy Doom fetch-and-build script (no real clone or build)."""

from __future__ import annotations

from pathlib import Path

import pytest

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "build_crispy", Path(__file__).resolve().parents[1] / "scripts" / "build_crispy.py"
)
build_crispy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_crispy)


def _write_lock(tmp_path: Path) -> Path:
    lock = tmp_path / "crispy-doom.lock"
    lock.write_text(
        'repo = "https://example.invalid/crispy-doom"\n'
        'tag = "crispy-doom-7.1"\n'
        'commit = "0123456789012345678901234567890123456789"\n'
        'tarball_sha256 = "%s"\n' % ("a" * 64),
        encoding="utf-8",
    )
    return lock


def test_load_lock_reads_all_four_fields(tmp_path: Path) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    assert lock.tag == "crispy-doom-7.1"
    assert lock.commit == "0123456789012345678901234567890123456789"
    assert lock.repo.endswith("crispy-doom")
    assert len(lock.tarball_sha256) == 64


def test_plan_commands_clones_pinned_tag_applies_patch_then_builds(
    tmp_path: Path,
) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    build_dir = tmp_path / "build" / "crispy"
    patch = tmp_path / "patches" / "crispy-doom-fb-export.diff"

    commands = build_crispy.plan_commands(
        lock, build_dir=build_dir, patch=patch, check_only=False
    )

    joined = [" ".join(c) for c in commands]
    assert any("clone" in c and "crispy-doom-7.1" in c for c in joined)
    assert any(c.startswith("git") and "apply" in c and str(patch) in c for c in joined)
    assert any("cmake" in c and "--build" in c for c in joined)


def test_plan_commands_check_only_stops_after_git_apply_check(tmp_path: Path) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    commands = build_crispy.plan_commands(
        lock,
        build_dir=tmp_path / "b",
        patch=tmp_path / "p.diff",
        check_only=True,
    )
    joined = [" ".join(c) for c in commands]
    assert any("apply" in c and "--check" in c for c in joined)
    assert not any("cmake" in c for c in joined)


def test_clean_removes_the_build_directory(tmp_path: Path) -> None:
    build_dir = tmp_path / "build" / "crispy"
    build_dir.mkdir(parents=True)
    (build_dir / "marker").write_text("x", encoding="utf-8")

    calls: list[list[str]] = []
    exit_code = build_crispy.run(
        ["--clean"],
        runner=lambda cmd, **_: calls.append(cmd),
        _build_dir=build_dir,
        _lock_path=_write_lock(tmp_path),
        _patch=tmp_path / "p.diff",
    )

    assert exit_code == 0
    assert not build_dir.exists()
    assert calls == []


def test_run_skips_git_apply_when_marker_present(tmp_path: Path) -> None:
    build_dir = tmp_path / "build" / "crispy"
    (build_dir / ".git").mkdir(parents=True)
    (build_dir / ".doomed-prism-applied").write_text("1", encoding="utf-8")

    calls: list[list[str]] = []
    build_crispy.run(
        [],
        runner=lambda cmd, **_: calls.append(cmd) or _ok(),
        _build_dir=build_dir,
        _lock_path=_write_lock(tmp_path),
        _patch=tmp_path / "p.diff",
    )

    joined = [" ".join(c) for c in calls]
    assert not any("clone" in c for c in joined)
    assert not any("apply" in c and "--check" not in c for c in joined)


def _ok():
    class _R:
        returncode = 0

    return _R()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_build_crispy.py -q`

Expected: FAIL — `scripts/build_crispy.py` does not exist.

- [ ] **Step 3: Implement `scripts/build_crispy.py`**

```python
"""Fetch Crispy Doom at a pinned tag, apply the frame-export patch, and build it."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_BUILD_DIR = _ROOT / "build" / "crispy"
_DEFAULT_LOCK = _ROOT / "crispy-doom.lock"
_DEFAULT_PATCH = _ROOT / "patches" / "crispy-doom-fb-export.diff"
_MARKER = ".doomed-prism-applied"


@dataclass(frozen=True)
class Lock:
    repo: str
    tag: str
    commit: str
    tarball_sha256: str


def load_lock(path: Path) -> Lock:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return Lock(
        repo=data["repo"],
        tag=data["tag"],
        commit=data["commit"],
        tarball_sha256=data["tarball_sha256"],
    )


def plan_commands(
    lock: Lock, *, build_dir: Path, patch: Path, check_only: bool
) -> list[list[str]]:
    commands: list[list[str]] = []
    if not (build_dir / ".git").exists():
        commands.append(
            ["git", "clone", "--branch", lock.tag, lock.repo, str(build_dir)]
        )
    if check_only:
        commands.append(["git", "-C", str(build_dir), "apply", "--check", str(patch)])
        return commands
    if not (build_dir / _MARKER).exists():
        commands.append(["git", "-C", str(build_dir), "apply", str(patch)])
    commands.append(
        ["cmake", "-S", str(build_dir), "-B", str(build_dir / "build"),
         "-DCMAKE_BUILD_TYPE=Release"]
    )
    commands.append(["cmake", "--build", str(build_dir / "build")])
    return commands


def run(
    argv: list[str] | None = None,
    *,
    runner=subprocess.run,
    _build_dir: Path | None = None,
    _lock_path: Path | None = None,
    _patch: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="build_crispy")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args(argv)

    build_dir = _build_dir or _DEFAULT_BUILD_DIR
    lock_path = _lock_path or _DEFAULT_LOCK
    patch = _patch or _DEFAULT_PATCH

    if args.clean:
        if build_dir.exists():
            shutil.rmtree(build_dir)
        return 0

    lock = load_lock(lock_path)
    commands = plan_commands(
        lock, build_dir=build_dir, patch=patch, check_only=args.check
    )
    for command in commands:
        result = runner(command, cwd=str(_ROOT))
        if getattr(result, "returncode", 0) != 0:
            print(f"command failed: {' '.join(command)}", file=sys.stderr)
            return 1
        if command[:4] == ["git", "-C", str(build_dir), "apply"] and "--check" not in command:
            (build_dir / _MARKER).write_text("1", encoding="utf-8")

    if not args.check:
        exe = build_dir / "build" / "src" / (
            "crispy-doom.exe" if sys.platform == "win32" else "crispy-doom"
        )
        print(str(exe))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
```

The `runner` is always called as `runner(command, cwd=<repo root>)`, so test doubles use `lambda cmd, **_: ...` and return either `None` (treated as success) or an object with `returncode`.

- [ ] **Step 4: Run the tests and the suite**

```bash
python -m pytest tests/test_build_crispy.py -q
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Real end-to-end check (opt-in, not in CI default)**

```bash
python scripts/build_crispy.py --check     # git apply --check only
python scripts/build_crispy.py              # full build; prints the exe path
```

Expected: `--check` prints "patch applies", the full build prints a path that exists.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_crispy.py tests/test_build_crispy.py
git commit -m "feat: add pinned Crispy Doom fetch-and-build script"
```

## Task 4: Engine segment wiring and graceful-close extraction

**Files:**
- Create: `src/pewpew/win_close.py`
- Modify: `src/pewpew/engine.py`
- Modify: `tests/fakes/fake_doom.py`
- Modify: `tests/test_engine.py`

**Interfaces:**
- Consumes: nothing new; `windows.request_close_windows` is being replaced.
- Produces:
  - `pewpew.win_close.request_close_windows(pid: int) -> int` — posts `WM_CLOSE` to every top-level window owned by `pid`; returns the count; a no-op returning `0` off Windows. No injectable API parameter.
  - `pewpew.engine.DoomProcess.frame_segment_name` property → `str | None`. Set by `start()`, cleared by `stop()` after the child exits.
  - `pewpew.engine.PopenFactory` is now `Callable[[list[str], Mapping[str, str]], _Process]`. The default is a module function `_spawn(args, env)` calling `subprocess.Popen(args, env=env)`.
  - `tests/fakes/fake_doom.py`: `FakePopen.__init__(self, arguments, env)` stores `self.env`; `FakePopenFactory.__call__(self, arguments, env)`.

- [ ] **Step 1: Write failing tests**

The existing `test_engine.py` tests need no edits — they reach the factory only
through `DoomProcess.start()`, and `_command()` is unchanged. Only the fake
(Step 1, `fake_doom.py`) grows an `env` parameter. Add these new tests to
`tests/test_engine.py`:

```python
def test_start_passes_a_unique_frame_segment_name_through_the_child_environment(
    tmp_path: Path,
) -> None:
    """Catches a missing or non-unique DOOMED_PRISM_FB_NAME for the export patch."""
    factory = FakePopenFactory()
    engine = DoomProcess(_runtime_config(tmp_path), popen_factory=factory)

    engine.start()

    name = engine.frame_segment_name
    assert name is not None and name.startswith("doomed-prism-fb-")
    assert factory.processes[0].env["DOOMED_PRISM_FB_NAME"] == name

    other = DoomProcess(_runtime_config(tmp_path), popen_factory=FakePopenFactory())
    other.start()
    assert other.frame_segment_name != name


def test_stop_clears_the_segment_name_after_the_child_exits(tmp_path: Path) -> None:
    """Catches a stale segment name lingering after shutdown."""
    factory = FakePopenFactory()

    def close_window(pid: int) -> None:
        factory.processes[0].returncode = 0

    engine = DoomProcess(
        _runtime_config(tmp_path), popen_factory=factory, graceful_close=close_window
    )
    engine.start()
    engine.stop()

    assert engine.frame_segment_name is None
```

Add `tests/test_win_close.py`:

```python
"""Tests for the cooperative native-close helper."""

from __future__ import annotations

import sys

import pytest

from pewpew.win_close import request_close_windows


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX no-op path only")
def test_request_close_windows_is_a_noop_off_windows() -> None:
    assert request_close_windows(4321) == 0
```

Update `tests/fakes/fake_doom.py` — two targeted edits, keeping every existing
attribute:

- `FakePopen.__init__(self, arguments: Sequence[str]) -> None:` becomes
  `FakePopen.__init__(self, arguments: Sequence[str], env: Mapping[str, str]) -> None:`
  and adds `self.env = dict(env)` right after `self.arguments = list(arguments)`.
  Add `from collections.abc import Mapping` to the imports.
- `FakePopenFactory.__call__(self, arguments: Sequence[str]) -> FakePopen:`
  becomes `__call__(self, arguments: Sequence[str], env: Mapping[str, str])` and
  calls `FakePopen(arguments, env)`.

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/test_engine.py tests/test_win_close.py -q`

Expected: FAIL — `frame_segment_name` missing, `win_close` missing, factory signature mismatch.

- [ ] **Step 3: Create `src/pewpew/win_close.py`**

```python
"""Cooperative native window closure for a supervised child (Windows only)."""

from __future__ import annotations

import sys

_WM_CLOSE = 0x0010


def request_close_windows(pid: int) -> int:
    """Post WM_CLOSE to every top-level window owned by ``pid``. No-op off Windows."""
    if sys.platform != "win32":
        return 0

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]

    closed = 0

    def _callback(hwnd: int, _lparam: int) -> bool:
        nonlocal closed
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)
            closed += 1
        return True

    user32.EnumWindows(enum_proc(_callback), 0)
    return closed
```

- [ ] **Step 4: Modify `src/pewpew/engine.py`**

- Add imports: `import os`, `import secrets`, `from collections.abc import Mapping`.
- Change `PopenFactory = Callable[[list[str], Mapping[str, str]], _Process]`.
- Add `def _spawn(args: list[str], env: Mapping[str, str]) -> _Process: return subprocess.Popen(args, env=env)` and default `popen_factory: PopenFactory = _spawn`.
- Replace the `_windows_graceful_close` import line with `from pewpew.win_close import request_close_windows`.
- In `__init__`, add `self._frame_segment_name: str | None = None`.
- In `start()`:

```python
def start(self) -> int:
    if self.poll() is None and self._process is not None:
        raise EngineAlreadyRunning("Crispy Doom is already running")
    name = f"doomed-prism-fb-{os.getpid()}-{secrets.token_hex(4)}"
    child_env = {**os.environ, "DOOMED_PRISM_FB_NAME": name}
    self._process = self._popen_factory(self._command(), child_env)
    self._frame_segment_name = name
    return self._process.pid
```

- Add the property:

```python
@property
def frame_segment_name(self) -> str | None:
    return self._frame_segment_name
```

- Rewrite `stop()` so every path that clears `self._process` also releases the
  segment; the re-raised `TimeoutExpired` path keeps the name for a retry:

```python
def stop(self, timeout_s: float = 3.0) -> None:
    process = self._process
    if process is None:
        return
    if process.poll() is not None:
        self._process = None
        self._release_segment()
        return

    try:
        self._graceful_close(process.pid)
    except Exception:
        pass
    else:
        try:
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            pass
        else:
            self._process = None
            self._release_segment()
            return

    process.terminate()
    try:
        process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        raise
    self._process = None
    self._release_segment()

def _release_segment(self) -> None:
    name = self._frame_segment_name
    self._frame_segment_name = None
    if not name or sys.platform == "win32":
        return
    try:
        os.unlink(f"/dev/shm/{name}")
    except OSError:
        pass
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_engine.py tests/test_win_close.py -q
python -m pytest -q
```

Expected: the engine and win_close tests pass. `tests/test_windows.py` still passes for now (it is deleted in Task 5).

- [ ] **Step 6: Commit**

```bash
git add src/pewpew/win_close.py src/pewpew/engine.py tests/fakes/fake_doom.py tests/test_engine.py tests/test_win_close.py
git commit -m "feat: pass a frame-segment name through the engine child env"
```

## Task 5: Host widget framebuffer rewrite

**Files:**
- Modify: `src/pewpew/host_widget.py`
- Modify: `tests/test_host_widget.py`
- Modify: `tests/test_host_widget_qt.py`
- Delete: `src/pewpew/windows.py`
- Delete: `tests/test_windows.py`

**Interfaces:**
- Consumes: `pewpew.framebuffer.FrameReader`, `FrameSegmentError`, `Frame` (Task 1); `pewpew.engine.DoomProcess.frame_segment_name` (Task 4).
- Produces:
  - `DoomHostWidget(config=None, *, engine=None, frame_reader=None, frame_reader_factory=FrameReader, clock=time.monotonic)`. The 640×640 host with a `viewport` child of type `_DoomViewport`.
  - `_DoomViewport(QWidget)` with `set_reader(reader)` and a `paintEvent` that draws the latest `Frame` via `QImage(..., QImage.Format_RGB32)` scaled into `self.rect()`; paints nothing when there is no frame.
  - `cleanup()` runs `reader.close()` then `engine.stop()`, idempotent, retrying each transiently failed step; wired to `closeEvent` and `QApplication.aboutToQuit`.
  - `showEvent` starts the engine (once), builds the reader from `engine.frame_segment_name` if not injected, and starts a repaint `QTimer` (`_REPAINT_INTERVAL_MS = 16`). On a hidden→shown cycle after start, it only restarts the timer.
  - `hideEvent` stops the timer.
  - A private `_on_tick()` that: retries `reader.try_open()` until open; raises `RuntimeError("engine did not export frames")` (after running cleanup) when the segment is still unavailable at `clock() > deadline` (`_SEGMENT_OPEN_TIMEOUT_S = 10.0`) or when `engine.poll()` is not `None`; raises `RuntimeError("frame segment is invalid")` on `FrameSegmentError`; otherwise calls `viewport.update()` when `latest().counter` changed, and stops the timer once `engine.poll()` is not `None`.

- [ ] **Step 1: Rewrite `tests/test_host_widget.py` to the import-guard only**

```python
"""The pure-Python host tests: only the missing-Qt-dependency contract."""

from __future__ import annotations

import pytest


def test_missing_qt_dependency_fails_explicitly() -> None:
    """Catches a silent skip or vague failure when the Raven extra is absent."""
    import pewpew.host_widget as module

    if module.DoomHostWidget.__bases__ != (object,):
        pytest.skip("a real Qt binding is available in this environment")

    with pytest.raises(RuntimeError, match="requires the PySide6 Raven extra"):
        module.DoomHostWidget()
```

- [ ] **Step 2: Rewrite `tests/test_host_widget_qt.py` for the framebuffer path**

```python
"""Real PySide6 + pytest-qt coverage for the framebuffer-painting host."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication, QWidget
except ModuleNotFoundError as error:
    raise RuntimeError("PySide6 is required by the project's dev test extra") from error
except ImportError as error:
    if "libEGL.so.1" not in str(error):
        raise
    pytest.skip(
        "PySide6 cannot initialize because this platform lacks libEGL.so.1",
        allow_module_level=True,
    )

from pewpew.framebuffer import STRIDE, SLOT_BYTES, Frame, FrameSegmentError
from pewpew.host_widget import DoomHostWidget


class _Engine:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self._return: int | None = None
        self.frame_segment_name = "doomed-prism-fb-test-0"

    def start(self) -> int:
        self.start_calls += 1
        return 8128

    def stop(self) -> None:
        self.stop_calls += 1

    def poll(self) -> int | None:
        return self._return


class _Reader:
    def __init__(self) -> None:
        self.available = True
        self.raise_on_open: Exception | None = None
        self.is_open = False
        self.close_calls = 0
        self._frame: Frame | None = None

    def try_open(self) -> bool:
        if self.raise_on_open is not None:
            raise self.raise_on_open
        if not self.available:
            return False
        self.is_open = True
        return True

    def set_frame(self, counter: int, byte: int) -> None:
        pixels = bytes([byte, byte, byte, 0xFF]) * (SLOT_BYTES // 4)
        self._frame = Frame(640, 480, STRIDE, 0x16362004, counter, memoryview(pixels))

    def latest(self) -> Frame | None:
        return self._frame if self.is_open else None

    def close(self) -> None:
        self.close_calls += 1
        self.is_open = False


def _host(qtbot, engine=None, reader=None) -> DoomHostWidget:
    engine = engine or _Engine()
    reader = reader or _Reader()
    config = SimpleNamespace(viewport_width=640, viewport_height=480)
    host = DoomHostWidget(config, engine=engine, frame_reader=reader)
    qtbot.addWidget(host)
    return host


def test_geometry_is_the_unpainted_640_square_with_a_640x480_viewport(qtbot) -> None:
    host = _host(qtbot)
    assert host.size().toTuple() == (640, 640)
    assert isinstance(host.viewport, QWidget)
    assert host.viewport.objectName() == "viewport"
    assert host.viewport.geometry().getRect() == (0, 80, 640, 480)
    assert not host.autoFillBackground()
    assert host.testAttribute(Qt.WA_NoSystemBackground)


def test_grab_captures_the_live_frame_pixels_inside_the_viewport(qtbot) -> None:
    """The Milestone 1 failure fixed: QWidget.grab() now contains DOOM pixels."""
    reader = _Reader()
    host = _host(qtbot, reader=reader)
    host.show()
    reader.try_open()
    reader.set_frame(counter=1, byte=0x40)
    host._on_tick()

    image = host.viewport.grab().toImage()
    sample = QColor(image.pixel(320, 240))
    assert (sample.red(), sample.green(), sample.blue()) == (0x40, 0x40, 0x40)


def test_no_frame_produces_no_repaint_and_paints_safely(qtbot) -> None:
    reader = _Reader()
    host = _host(qtbot, reader=reader)
    host.show()
    reader.try_open()  # open, but no frame set

    updates: list[int] = []
    host.viewport.update = lambda *a: updates.append(1)  # type: ignore[assignment]
    host._on_tick()

    assert updates == []
    host.viewport.grab()  # a no-frame paintEvent must not raise


def test_tick_repaints_only_when_the_counter_advances(qtbot) -> None:
    reader = _Reader()
    host = _host(qtbot, reader=reader)
    host.show()
    reader.try_open()
    reader.set_frame(counter=7, byte=0x10)

    updates: list[int] = []
    host.viewport.update = lambda *a: updates.append(1)  # type: ignore[assignment]
    host._on_tick()
    host._on_tick()

    assert updates == [1]


def test_invalid_segment_raises_and_cleans_up(qtbot) -> None:
    engine = _Engine()
    reader = _Reader()
    reader.raise_on_open = FrameSegmentError("bad header")
    host = _host(qtbot, engine=engine, reader=reader)
    host.show()

    with pytest.raises(RuntimeError, match="frame segment is invalid"):
        host._on_tick()
    assert engine.stop_calls == 1
    assert reader.close_calls == 1


def test_missing_segment_past_deadline_raises(qtbot) -> None:
    engine = _Engine()
    reader = _Reader()
    reader.available = False
    clock_values = iter([0.0, 100.0])  # showEvent sets deadline=10.0; tick sees 100.0
    config = SimpleNamespace(viewport_width=640, viewport_height=480)
    host = DoomHostWidget(
        config, engine=engine, frame_reader=reader, clock=lambda: next(clock_values)
    )
    qtbot.addWidget(host)
    host.show()

    with pytest.raises(RuntimeError, match="did not export frames"):
        host._on_tick()
    assert engine.stop_calls == 1


def test_cleanup_closes_reader_before_stopping_engine(qtbot) -> None:
    order: list[str] = []
    engine = _Engine()
    engine.stop = lambda: order.append("engine")  # type: ignore[assignment]
    reader = _Reader()
    reader.close = lambda: order.append("reader")  # type: ignore[assignment]
    host = _host(qtbot, engine=engine, reader=reader)

    host.cleanup()
    host.cleanup()

    assert order == ["reader", "engine"]


def test_about_to_quit_and_close_event_both_run_cleanup(qtbot) -> None:
    engine = _Engine()
    host = _host(qtbot, engine=engine)
    QApplication.instance().aboutToQuit.emit()
    assert engine.stop_calls == 1

    engine2 = _Engine()
    host2 = _host(qtbot, engine=engine2)
    host2.close()
    assert engine2.stop_calls == 1
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_host_widget_qt.py -q`

Expected: FAIL — the host still imports `pewpew.windows` and has no `_on_tick`, `_DoomViewport`, or `frame_reader` parameter.

- [ ] **Step 4: Rewrite `src/pewpew/host_widget.py`**

```python
"""Qt host that paints external Doom frames from shared memory into a viewport."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import Protocol

from pewpew.config import RuntimeConfig
from pewpew.engine import DoomProcess
from pewpew.framebuffer import Frame, FrameReader, FrameSegmentError


class _Engine(Protocol):
    def start(self) -> int: ...

    def stop(self) -> None: ...

    def poll(self) -> int | None: ...

    @property
    def frame_segment_name(self) -> str | None: ...


class _Reader(Protocol):
    is_open: bool

    def try_open(self) -> bool: ...

    def latest(self) -> Frame | None: ...

    def close(self) -> None: ...


try:  # Keep non-desktop commands importable without the optional Qt dependency.
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QCloseEvent, QHideEvent, QImage, QPainter, QShowEvent
    from PySide6.QtWidgets import QApplication, QWidget
except ImportError as _qt_import_error:  # pragma: no cover - depends on local extras

    class DoomHostWidget:
        """Explain the missing optional Qt dependency at desktop-host creation."""

        def __init__(
            self, *_: object, _error: ImportError = _qt_import_error, **__: object
        ) -> None:
            raise RuntimeError(
                "the desktop host requires the PySide6 Raven extra"
            ) from _error

else:

    class _DoomViewport(QWidget):
        """A transparent 640x480 widget that blits the newest shared-memory frame."""

        def __init__(self, parent: QWidget) -> None:
            super().__init__(parent)
            self.setAttribute(Qt.WA_NoSystemBackground, True)
            self.setAttribute(Qt.WA_OpaquePaintEvent, False)
            self._reader: _Reader | None = None

        def set_reader(self, reader: _Reader | None) -> None:
            self._reader = reader

        def paintEvent(self, event: object) -> None:
            del event
            reader = self._reader
            frame = reader.latest() if reader is not None else None
            if frame is None:
                return
            image = QImage(
                frame.buffer,
                frame.width,
                frame.height,
                frame.stride,
                QImage.Format_RGB32,
            )
            painter = QPainter(self)
            painter.drawImage(self.rect(), image)
            painter.end()

    class DoomHostWidget(QWidget):
        """A transparent 640x640 surface painting Doom frames into its viewport."""

        _HOST_WIDTH = 640
        _HOST_HEIGHT = 640
        _REPAINT_INTERVAL_MS = 16
        _SEGMENT_OPEN_TIMEOUT_S = 10.0

        def __init__(
            self,
            config: RuntimeConfig | None = None,
            *,
            engine: _Engine | None = None,
            frame_reader: _Reader | None = None,
            frame_reader_factory: Callable[[str], _Reader] = FrameReader,
            clock: Callable[[], float] = time.monotonic,
        ) -> None:
            super().__init__()
            self._config = config
            self._engine = engine if engine is not None else self._new_engine(config)
            self._reader = frame_reader
            self._reader_factory = frame_reader_factory
            self._clock = clock
            self._started = False
            self._shutdown_requested = False
            self._deadline = 0.0
            self._last_counter: int | None = None

            self.setFixedSize(self._HOST_WIDTH, self._HOST_HEIGHT)
            self.setAutoFillBackground(False)
            self.setAttribute(Qt.WA_NoSystemBackground, True)
            self.setAttribute(Qt.WA_OpaquePaintEvent, False)

            self.viewport = _DoomViewport(self)
            self.viewport.setObjectName("viewport")
            self.viewport.setGeometry(0, 80, 640, 480)
            if self._reader is not None:
                self.viewport.set_reader(self._reader)

            self._timer = QTimer(self)
            self._timer.setInterval(self._REPAINT_INTERVAL_MS)
            self._timer.timeout.connect(self._on_tick)

            application = QApplication.instance()
            if application is not None:
                application.aboutToQuit.connect(self.cleanup)

        def showEvent(self, event: QShowEvent) -> None:
            super().showEvent(event)
            if self._shutdown_requested:
                return
            if self._started:
                self._timer.start()
                return
            if self._config is None and self._engine is None:
                return
            self._started = True
            try:
                self._engine.start()
                if self._reader is None:
                    name = self._engine.frame_segment_name
                    self._reader = self._reader_factory(name)
                    self.viewport.set_reader(self._reader)
                self._deadline = self._clock() + self._SEGMENT_OPEN_TIMEOUT_S
                self._timer.start()
            except BaseException:
                self._cleanup_after_startup_failure()
                raise

        def hideEvent(self, event: QHideEvent) -> None:
            super().hideEvent(event)
            self._timer.stop()

        def closeEvent(self, event: QCloseEvent) -> None:
            self.cleanup()
            event.accept()

        def _on_tick(self) -> None:
            reader = self._reader
            if reader is None:
                return
            if not reader.is_open:
                try:
                    opened = reader.try_open()
                except FrameSegmentError:
                    self._cleanup_after_startup_failure()
                    raise RuntimeError("frame segment is invalid")
                if not opened:
                    if self._engine.poll() is not None or self._clock() > self._deadline:
                        self._cleanup_after_startup_failure()
                        raise RuntimeError("engine did not export frames")
                    return
            frame = reader.latest()
            counter = frame.counter if frame is not None else None
            if counter != self._last_counter:
                self._last_counter = counter
                self.viewport.update()
            if self._engine.poll() is not None:
                self._timer.stop()

        def cleanup(self) -> None:
            self._shutdown_requested = True
            self._timer.stop()
            errors: list[Exception] = []
            if self._reader is not None:
                try:
                    self._reader.close()
                except Exception as error:  # noqa: BLE001 - retried on next call
                    errors.append(error)
                else:
                    self._reader = None
                    self.viewport.set_reader(None)
            if self._engine is not None:
                try:
                    self._engine.stop()
                except Exception as error:  # noqa: BLE001 - retried on next call
                    errors.append(error)
                else:
                    self._engine = None
            if errors:
                raise errors[0]

        def _cleanup_after_startup_failure(self) -> None:
            try:
                self.cleanup()
            except Exception:  # noqa: BLE001 - do not mask the original failure
                pass

        @staticmethod
        def _new_engine(config: RuntimeConfig | None) -> _Engine | None:
            if config is None:
                return None
            return DoomProcess(config)
```

- [ ] **Step 5: Delete the retired reparenting module**

```bash
git rm src/pewpew/windows.py tests/test_windows.py
```

- [ ] **Step 6: Run the full suite**

```bash
python -m pytest -q
python scripts/check_publication_safety.py --root .
```

Expected: all tests pass and the scan exits 0. `test_raven_app.py` is unchanged — the `DoomHostWidget(config)` contract it depends on is the same. `test_distribution_metadata.py` needs no change either: it only asserts the SPDX license and `prune tests` in `MANIFEST.in`; it does not enumerate modules, so removing `windows.py` does not affect it.

- [ ] **Step 7: Commit**

```bash
git add src/pewpew/host_widget.py tests/test_host_widget.py tests/test_host_widget_qt.py
git commit -m "feat: paint Doom frames from shared memory; retire window embedding"
```

## Task 6: Ignore build artifacts and confirm a clean tree

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add the two ignore rules**

Append to `.gitignore`:

```
build/
*.egg-info/
```

- [ ] **Step 2: Confirm nothing stray is tracked or newly ignored by accident**

```bash
git status --short
git check-ignore -v build/ src/doomed_prism.egg-info/
git ls-files | grep -E 'egg-info|^build/' || echo "clean: no build or egg-info tracked"
```

Expected: `build/` and `*.egg-info/` report as ignored; nothing matching is tracked.

- [ ] **Step 3: Full verification sweep**

```bash
python -m pytest -q
python scripts/check_publication_safety.py --root .
python scripts/check_publication_safety.py --root . --history
git diff --check
```

Expected: tests green, both scans exit 0, no whitespace errors.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore build/ and egg-info directories"
```

## Task 7: Milestone 2 decision gate

**Files:**
- Create: `docs/validation/milestone-2-checklist.md`
- Create: `docs/validation/milestone-2-result.md`
- Create when testing: `artifacts/milestone-2/` (ignored)

This mirrors Milestone 1's Task 6. The checklist and the result template are written and committed first; then the gate is run manually on a Windows host with Raven Framework installed separately, and the result document is filled and committed.

- [ ] **Step 1: Write `docs/validation/milestone-2-checklist.md`**

Transcribe spec section 14 into a runnable checklist with the same structure and safety rules as `docs/validation/milestone-1-checklist.md`: scope and safety; environment and launch (build via `scripts/build_crispy.py`, record the pinned tag/commit, compiler and SDL2 versions, `build_crispy.py --check` passes; set `DOOMED_PRISM_CRISPY_EXE`/`_IWAD`; `doomed-prism validate` exit 0; clean crispy-doom PID baseline with the before/after procedure; 100% display scaling; `pytest -q` green; `check_publication_safety.py --root .` exit 0; `doomed-prism run-desktop`); objective checks (exactly one new PID; a `FrameReader` probe shows `frame_counter` advancing; viewport geometry `(0, 80, 640, 480)`; both margins and the home control uncovered; no `SetParent` in the window tree); the per-mode evidence table for Raw, Night, Day, Outdoors, Camera (live pixels inside the viewport; frames update; viewport geometry holds; the app capture includes the DOOM frame not a grey-fill; dark areas read as transparent in optical modes; a keypress in Crispy's separate SDL window changes state visible in the viewport); cleanup (one PID gone, no orphan, `cleanup()` runs reader-close then engine-stop with no exception); and the hard decision rule with the four outcomes from spec section 14. Keep all evidence under the ignored `artifacts/milestone-2/`.

- [ ] **Step 2: Write `docs/validation/milestone-2-result.md`**

Use the same template shape as `docs/validation/milestone-1-result.md`: run identification; environment (Windows version, Python version, Raven Framework version/commit, Crispy Doom pinned tag + commit from `crispy-doom.lock`, compiler + SDL2 versions, IWAD identity only if redistribution permits, GPU, display scaling, DPI-awareness); launch and interaction; the per-mode evidence table; cleanup evidence; automated verification; and a single **Final decision** field starting at `PENDING — incomplete evidence` with the four outcomes from spec section 14 listed beneath it.

- [ ] **Step 3: Commit the checklist and template**

```bash
git add docs/validation/milestone-2-checklist.md docs/validation/milestone-2-result.md
git commit -m "docs: add Milestone 2 framebuffer capture checklist"
```

- [ ] **Step 4: Run the gate on Windows**

Follow `docs/validation/milestone-2-checklist.md` exactly. Build the patched engine with `python scripts/build_crispy.py`. Establish a clean crispy-doom PID baseline. `doomed-prism run-desktop`. Probe the segment with a small `FrameReader` script to confirm `frame_counter` advances. Step Raven Simulator through Raw, Night, Day, Outdoors, and Camera; for each, save two time-separated captures or a short video to `artifacts/milestone-2/`. Confirm a keypress in Crispy's separate SDL window changes what the Qt viewport shows. Close Raven normally and confirm the one PID is gone with no teardown exception.

- [ ] **Step 5: Apply the hard decision and fill the result**

Edit the single **Final decision** field in `docs/validation/milestone-2-result.md` to exactly one of: `PASS — framebuffer integration viable`; `FAIL — framebuffer path insufficient`; `BLOCKED/RETRY — implementation or environment failure`; `PENDING — incomplete evidence`. Record every environment and per-mode field with a short non-sensitive observation. Keep captures out of Git.

- [ ] **Step 6: Final automated verification and commit**

```bash
python -m pytest -q
git diff --check
git add -- docs/validation/milestone-2-checklist.md docs/validation/milestone-2-result.md
git diff --cached --name-status
git diff --cached --check
python scripts/check_publication_safety.py --root .
python scripts/check_publication_safety.py --root . --history
git commit -m "docs: record framebuffer integration result"
git status --short
```

`git diff --cached --name-status` must list only the two documentation paths. The scanner reads the staged index, so it runs after that exact-path `git add`. Expected: tests pass, both scans exit 0, no whitespace errors, and `git status --short` shows only ignored `artifacts/` and `build/` content after the commit.

## Milestone Exit Criteria

Milestone 2 is complete when all automated tests pass, the publication-safety scan is clean (`--root .` and `--history`), and `milestone-2-result.md` records a reproducible PASS or FAIL. A FAIL is a valid engineering result: it retires the shared-memory framebuffer path and moves the decision to approach B (a shared OpenGL ES / Qt rendering surface).
