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
