"""Tests for the stdlib-only shared-memory frame reader."""

from __future__ import annotations

from pathlib import Path
import os
import secrets
import sys

import pytest

TESTS_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIRECTORY))
sys.path.insert(0, str(TESTS_DIRECTORY.parent / "src"))

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
    buffer_copy = bytes(frame.buffer)
    assert buffer_copy == second
    # Release the frame (and its memoryview) before closing so the mapping can close
    del frame
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


def test_wrong_width_raises_frame_segment_error(writer, segment_name: str) -> None:
    writer.write_raw_header(width=320)
    reader = FrameReader(segment_name)
    with pytest.raises(FrameSegmentError):
        reader.try_open()


def test_wrong_height_raises_frame_segment_error(writer, segment_name: str) -> None:
    writer.write_raw_header(height=240)
    reader = FrameReader(segment_name)
    with pytest.raises(FrameSegmentError):
        reader.try_open()


def test_wrong_stride_raises_frame_segment_error(writer, segment_name: str) -> None:
    writer.write_raw_header(stride=1280)
    reader = FrameReader(segment_name)
    with pytest.raises(FrameSegmentError):
        reader.try_open()


def test_out_of_range_active_index_makes_latest_none(
    writer, segment_name: str
) -> None:
    writer.write_frame(bytes(SLOT_BYTES))
    writer.write_raw_header(active_index=99)

    reader = FrameReader(segment_name)
    reader.try_open()
    assert reader.latest() is None
    reader.close()


def test_close_is_idempotent(writer, segment_name: str) -> None:
    reader = FrameReader(segment_name)
    reader.try_open()
    reader.close()
    reader.close()
    assert reader.is_open is False


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-specific race: undersized file")
def test_try_open_retries_on_undersized_posix_file(segment_name: str) -> None:
    # If the producer has opened /dev/shm/<name> but not yet ftruncate'd it
    # to SEGMENT_SIZE, mmap raises ValueError. This must be caught and
    # try_open must return False (not raise or leak the fd).
    path = f"/dev/shm/{segment_name}"
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.ftruncate(fd, 4096)  # Undersized file
        os.close(fd)

        reader = FrameReader(segment_name)
        assert reader.try_open() is False
        assert reader.is_open is False
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
