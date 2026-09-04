"""Neutral Qt host for the fixed-size external Doom viewport."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from pewpew.config import RuntimeConfig
from pewpew.engine import DoomProcess
from pewpew.windows import (
    EmbeddedWindow,
    WindowEmbeddingRollbackError,
    embed_window,
    find_top_level_window,
)


class _Engine(Protocol):
    def start(self) -> int: ...

    def stop(self) -> None: ...


class _RestorableWindow(Protocol):
    def restore(self) -> None: ...


WindowFinder = Callable[[int, float], int]
WindowEmbedder = Callable[[int, int, int, int], EmbeddedWindow]


try:  # Keep non-desktop commands importable when the optional Qt dependency is absent.
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QCloseEvent, QShowEvent
    from PySide6.QtWidgets import QApplication, QWidget
except ImportError as _qt_import_error:  # pragma: no cover - depends on local extras

    class DoomHostWidget:
        """Explain the missing optional Qt dependency at desktop-host creation."""

        def __init__(
            self, *_: object, _error: ImportError = _qt_import_error, **__: object
        ) -> None:
            raise RuntimeError("the desktop host requires the PySide6 Raven extra") from (
                _error
            )

else:

    class DoomHostWidget(QWidget):
        """A transparent 640x640 surface with one native 640x480 Doom child."""

        _HOST_WIDTH = 640
        _HOST_HEIGHT = 640
        _WINDOW_DISCOVERY_TIMEOUT_S = 10.0

        def __init__(
            self,
            config: RuntimeConfig | None = None,
            *,
            engine: _Engine | None = None,
            embedded_window: _RestorableWindow | None = None,
            window_finder: WindowFinder = find_top_level_window,
            window_embedder: WindowEmbedder = embed_window,
        ) -> None:
            super().__init__()
            self._config = config
            self._engine = engine if engine is not None else self._new_engine(config)
            self._embedded_window = embedded_window
            self._window_finder = window_finder
            self._window_embedder = window_embedder
            self._started = False
            self._shutdown_requested = False

            self.setFixedSize(self._HOST_WIDTH, self._HOST_HEIGHT)
            self.setAutoFillBackground(False)
            self.setAttribute(Qt.WA_NoSystemBackground, True)
            self.setAttribute(Qt.WA_OpaquePaintEvent, False)

            self.viewport = QWidget(self)
            self.viewport.setObjectName("viewport")
            self.viewport.setGeometry(0, 80, 640, 480)
            self.viewport.setAttribute(Qt.WA_NativeWindow, True)
            self.viewport.winId()

            application = QApplication.instance()
            if application is not None:
                application.aboutToQuit.connect(self.cleanup)

        def showEvent(self, event: QShowEvent) -> None:
            """Start and embed the external engine after the native child exists."""
            super().showEvent(event)
            if self._started or self._shutdown_requested or self._config is None:
                return

            self._started = True
            try:
                pid = self._engine.start()
                child_hwnd = self._window_finder(
                    pid, self._WINDOW_DISCOVERY_TIMEOUT_S
                )
                self._embedded_window = self._window_embedder(
                    child_hwnd,
                    int(self.viewport.winId()),
                    self._config.viewport_width,
                    self._config.viewport_height,
                )
            except WindowEmbeddingRollbackError as error:
                self._embedded_window = error.embedded_window
                self._cleanup_after_startup_failure()
                raise
            except BaseException:
                self._cleanup_after_startup_failure()
                raise

        def closeEvent(self, event: QCloseEvent) -> None:
            """Use the same cleanup path for ordinary widget closure."""
            self.cleanup()
            event.accept()

        def cleanup(self) -> None:
            """Restore and stop each resource once its individual cleanup succeeds."""
            self._shutdown_requested = True

            errors: list[Exception] = []
            if self._embedded_window is not None:
                try:
                    self._embedded_window.restore()
                except Exception as error:
                    errors.append(error)
                else:
                    self._embedded_window = None
            if self._engine is not None:
                try:
                    self._engine.stop()
                except Exception as error:
                    errors.append(error)
                else:
                    self._engine = None
            if errors:
                raise errors[0]

        def _cleanup_after_startup_failure(self) -> None:
            """Attempt shutdown without hiding the original startup failure."""
            try:
                self.cleanup()
            except Exception:
                pass

        @staticmethod
        def _new_engine(config: RuntimeConfig | None) -> _Engine | None:
            if config is None:
                return None
            return DoomProcess(config)
