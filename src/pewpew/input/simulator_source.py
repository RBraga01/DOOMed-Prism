"""Read gaze / click / Enter / F9 from Qt events on the host widget."""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QWidget

from pewpew.input.source import InputSample


class SimulatorInputSource(QObject):
    def __init__(self, widget: QWidget) -> None:
        super().__init__(widget)
        self._widget = widget
        self._debug_fire = bool(os.environ.get("DOOMED_PRISM_DEBUG_FIRE"))
        self._gaze: tuple[int, int] | None = None
        self._activation = False
        self._pause = False
        self._debug_edge = False
        widget.setMouseTracking(True)
        widget.installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        etype = event.type()
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
        elif etype == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._pause = True
            elif key == Qt.Key_F9 and self._debug_fire:
                self._debug_edge = True
        return False

    def sample(self, now: float) -> InputSample:
        s = InputSample(self._gaze, self._activation, self._pause, self._debug_edge)
        self._activation = self._pause = self._debug_edge = False
        return s
