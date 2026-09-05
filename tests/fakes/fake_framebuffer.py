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
        width: int = WIDTH,
        height: int = HEIGHT,
        stride: int = STRIDE,
        slot_count: int = SLOT_COUNT,
        slot_bytes: int = SLOT_BYTES,
        active_index: int | None = None,
    ) -> None:
        self._map[0:HEADER_SIZE] = b"\x00" * HEADER_SIZE
        self._map[0 : _HEADER.size] = _HEADER.pack(
            magic,
            version,
            slot_count,
            slot_bytes,
            width,
            height,
            stride,
            pixel_format,
            self._active if active_index is None else active_index,
            self._counter,
            self._flags,
        )

    def write_raw_header(
        self,
        *,
        magic: int = MAGIC,
        version: int = VERSION,
        pixel_format: int = PIXEL_FORMAT_ARGB8888,
        width: int = WIDTH,
        height: int = HEIGHT,
        stride: int = STRIDE,
        slot_count: int = SLOT_COUNT,
        slot_bytes: int = SLOT_BYTES,
        active_index: int | None = None,
    ) -> None:
        self._write_header(
            magic=magic,
            version=version,
            pixel_format=pixel_format,
            width=width,
            height=height,
            stride=stride,
            slot_count=slot_count,
            slot_bytes=slot_bytes,
            active_index=active_index,
        )

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
