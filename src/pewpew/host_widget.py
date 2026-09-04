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
