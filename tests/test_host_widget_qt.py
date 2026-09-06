"""Real PySide6 + pytest-qt coverage for the framebuffer-painting host."""

from __future__ import annotations

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

    def start(self, *, ipc_address: str | None = None) -> int:
        self.start_calls += 1
        self.ipc_arg = ipc_address
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


def test_open_segment_with_no_frame_past_deadline_raises(qtbot) -> None:
    """Spec §7: an opened-but-silent segment must still time out, not hang."""
    engine = _Engine()
    reader = _Reader()
    reader.is_open = True  # segment already open, but no frame was ever published
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


def test_cleanup_retries_each_transiently_failed_operation(qtbot) -> None:
    """Catches cleanup marking a failed reader-close or engine-stop as complete."""
    engine = _Engine()
    reader = _Reader()

    close_calls: list[int] = []

    def failing_close() -> None:
        close_calls.append(len(close_calls) + 1)
        if len(close_calls) == 1:
            raise OSError("temporary reader-close failure")
        reader.is_open = False

    reader.close = failing_close  # type: ignore[assignment]
    host = _host(qtbot, engine=engine, reader=reader)

    with pytest.raises(OSError, match="temporary reader-close failure"):
        host.cleanup()
    # engine.stop() must still have been attempted even though reader.close() raised first
    assert engine.stop_calls == 1
    assert close_calls == [1]

    host.cleanup()  # retry: reader.close() succeeds this time; engine already stopped, not retried
    assert close_calls == [1, 2]
    assert engine.stop_calls == 1


def test_about_to_quit_and_close_event_both_run_cleanup(qtbot) -> None:
    engine = _Engine()
    host = _host(qtbot, engine=engine)
    QApplication.instance().aboutToQuit.emit()
    assert engine.stop_calls == 1

    engine2 = _Engine()
    host2 = _host(qtbot, engine=engine2)
    host2.close()
    assert engine2.stop_calls == 1


class _Server:
    def __init__(self) -> None:
        self.started = False
        self.closed = 0
        self.sent: list = []
        self.is_connected = False
        self.protocol_mismatch = False
        self.on_disconnect = lambda: None
        self.poll_calls = 0

    def start(self) -> str:
        self.started = True
        return "127.0.0.1:0"

    def poll(self) -> None:
        self.poll_calls += 1

    def send(self, message) -> None:
        self.sent.append(message)

    def close(self) -> None:
        self.closed += 1


class _Pipeline:
    def __init__(self) -> None:
        self.ticks = 0
        self.releases = 0
        self.paused = False

    def tick(self, now: float) -> None:
        self.ticks += 1

    def release_all(self) -> None:
        self.releases += 1
        self.paused = False

    def toggle_pause(self) -> None:
        self.paused = not self.paused


def _ipc_host(qtbot, *, engine=None, reader=None, server=None, pipeline=None):
    engine = engine or _Engine()
    engine.start = lambda *, ipc_address=None: setattr(engine, "ipc_arg", ipc_address) or 8128
    reader = reader or _Reader()
    server = server or _Server()
    pipeline = pipeline or _Pipeline()
    config = SimpleNamespace(viewport_width=640, viewport_height=480)
    host = DoomHostWidget(
        config, engine=engine, frame_reader=reader,
        ipc_server=server, input_pipeline=pipeline,
    )
    qtbot.addWidget(host)
    return host, engine, reader, server, pipeline


def test_showevent_starts_server_before_engine_and_passes_the_address(qtbot) -> None:
    order: list[str] = []
    host, engine, _, server, _ = _ipc_host(qtbot)
    server.start = lambda: order.append("server") or "127.0.0.1:0"
    engine.start = lambda *, ipc_address=None: order.append(f"engine:{ipc_address}") or 8128
    host.show()
    assert order == ["server", "engine:127.0.0.1:0"]


def test_on_tick_polls_the_server_before_any_early_return(qtbot) -> None:
    reader = _Reader()
    reader.available = False  # forces the "waiting for segment" early return
    host, _, _, server, _ = _ipc_host(qtbot, reader=reader)
    host.show()
    host._on_tick()
    assert server.poll_calls >= 1


def test_ipc_disconnect_releases_all_and_closes_without_pause(qtbot) -> None:
    host, _, _, server, pipeline = _ipc_host(qtbot)
    host.show()
    host._on_ipc_disconnect()
    assert server.closed == 1
    assert pipeline.releases == 1
    assert not any(getattr(m, "code", None) == 20 for m in server.sent)


def test_protocol_mismatch_raises_after_cleanup(qtbot) -> None:
    # No frame is set: the mismatch check runs before the M2 frame-wait guard.
    host, engine, _, server, _ = _ipc_host(qtbot)
    server.protocol_mismatch = True
    host.show()
    with pytest.raises(RuntimeError, match="input protocol mismatch"):
        host._on_tick()
    assert engine.stop_calls == 1


def test_no_ipc_connection_past_deadline_raises(qtbot) -> None:
    reader = _Reader()
    now = [0.0]  # showEvent arms both deadlines from now[0]; the tick reads a later value
    host, engine, _, server, _ = _ipc_host(qtbot, reader=reader)
    host._clock = lambda: now[0]  # type: ignore[assignment]
    host.show()                    # _deadline = 10.0, _ipc_deadline = 10.0
    reader.try_open()
    reader.set_frame(counter=1, byte=0x20)  # frames flowing, but IPC never connects
    now[0] = 100.0                 # well past _ipc_deadline
    with pytest.raises(RuntimeError, match="engine did not connect input"):
        host._on_tick()
    assert engine.stop_calls == 1
