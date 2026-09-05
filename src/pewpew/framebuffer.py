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
    """One decoded frame view. ``buffer`` is valid until the next reader call.

    Holding a Frame past the next reader call (or close()) keeps the segment
    mapping alive until the Frame is garbage collected; release the frame
    to allow the mapping to close immediately.
    """

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
        (magic, version, slot_count, slot_bytes, width, height, stride,
         pixel_format, _active_index, _frame_counter, _flags) = fields
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
        if (
            slot_count != SLOT_COUNT
            or slot_bytes != SLOT_BYTES
            or width != WIDTH
            or height != HEIGHT
            or stride != STRIDE
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
        if active_index >= SLOT_COUNT:
            return None
        offset = HEADER_SIZE + active_index * SLOT_BYTES
        buffer = memoryview(mapping)[offset : offset + SLOT_BYTES]
        return Frame(width, height, stride, pixel_format, frame_counter, buffer)

    def close(self) -> None:
        if self._map is not None:
            try:
                self._map.close()
            except BufferError:
                # A retained Frame.buffer memoryview pins the mmap; the OS mapping
                # is released when the caller drops that Frame (GC). This is expected,
                # not an error to surface.
                pass
            self._map = None
        if self._fd != -1:
            try:
                os.close(self._fd)
            except OSError:
                pass
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
        try:
            return mmap.mmap(self._fd, SEGMENT_SIZE, prot=mmap.PROT_READ)
        except (ValueError, OSError) as error:
            # File exists but is not yet truncated to SEGMENT_SIZE (producer
            # has not finished initialization), or other OS-level issue.
            os.close(self._fd)
            self._fd = -1
            raise FileNotFoundError(self._name) from error
