"""Read gaze / click / pause / debug-fire from Qt events on the host widget."""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QWidget

from pewpew.input.source import InputSample

# Gate key bindings. Return/Enter is the physical ClickButton stand-in (§9); P
# is an alias that never collides with the Raven framework's own shortcuts. B
# stands in for a spoken "pew pew" when DOOMED_PRISM_DEBUG_FIRE is set.
# (F9 was retired 2026-09-08: Raven binds it as a shortcut, so it was consumed
# before it ever reached this event filter.)
_PAUSE_KEYS = frozenset({Qt.Key_Return, Qt.Key_Enter, Qt.Key_P})
_DEBUG_KEY = Qt.Key_B


class SimulatorInputSource(QObject):
    def __init__(self, widget: QWidget) -> None:
        super().__init__(widget)  # parented -> auto-removed as a filter when it dies
        self._widget = widget
        self._debug_fire = bool(os.environ.get("DOOMED_PRISM_DEBUG_FIRE"))
        self._gaze: tuple[int, int] | None = None
        self._activation = False
        self._pause = False
        self._debug_edge = False
        widget.setMouseTracking(True)
        widget.installEventFilter(self)
        # Keys are delivered to the *focused* widget, which the DOOM viewport
        # almost never is (the Raven framework holds focus). Filter at the
        # application level so a key press anywhere in the app reaches us
        # before Raven's own keyPressEvent / shortcuts.
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    @property
    def widget(self) -> QWidget:
        return self._widget

    def _handles(self, key: int) -> bool:
        return key in _PAUSE_KEYS or (key == _DEBUG_KEY and self._debug_fire)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        etype = event.type()

        # --- keyboard: handled app-wide, regardless of which widget is focused ---
        if etype == QEvent.Type.ShortcutOverride:
            # Claim our keys before Qt dispatches them as shortcuts, or Raven
            # eats Enter (-> its focused exit button) and P / B never arrive as
            # a plain KeyPress. accept() + True = "deliver this to me as a key
            # press instead of firing a shortcut".
            if self._handles(event.key()):
                event.accept()
                return True
            return False
        if etype == QEvent.Type.KeyPress:
            key = event.key()
            if key in _PAUSE_KEYS:
                self._pause = True
                return True  # consume it app-wide
            if key == _DEBUG_KEY and self._debug_fire:
                self._debug_edge = True
                return True
            return False

        # --- pointer: only from the DOOM viewport this source was built for ---
        if obj is not self._widget:
            return False
        if etype == QEvent.Type.MouseMove:
            p = event.position().toPoint()
            self._gaze = (
                max(0, min(self._widget.width() - 1, p.x())),
                max(0, min(self._widget.height() - 1, p.y())),
            )
        elif etype == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
            self._activation = True
        elif etype == QEvent.Type.Leave:
            self._gaze = None
        return False

    def sample(self, now: float) -> InputSample:
        s = InputSample(self._gaze, self._activation, self._pause, self._debug_edge)
        self._activation = self._pause = self._debug_edge = False
        return s
