"""Real pytest-qt coverage for SimulatorInputSource."""

from __future__ import annotations

import pytest

try:
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QKeyEvent, QMouseEvent
    from PySide6.QtWidgets import QApplication, QWidget
except ModuleNotFoundError as error:
    raise RuntimeError("PySide6 is required by the project's dev test extra") from error
except ImportError as error:
    if "libEGL.so.1" not in str(error):
        raise
    pytest.skip("PySide6 cannot initialize (no libEGL)", allow_module_level=True)

from pewpew.input.simulator_source import SimulatorInputSource


def _widget(qtbot) -> QWidget:
    w = QWidget()
    w.setFixedSize(640, 640)
    qtbot.addWidget(w)
    return w


def _mouse(kind, x, y, button=Qt.LeftButton):
    pos = QPointF(x, y)
    return QMouseEvent(kind, pos, pos, button, button, Qt.NoModifier)


def test_mouse_move_then_press_then_sample(qtbot) -> None:
    w = _widget(qtbot)
    src = SimulatorInputSource(w)
    QApplication.sendEvent(w, _mouse(QEvent.Type.MouseMove, 400, 300))
    QApplication.sendEvent(w, _mouse(QEvent.Type.MouseButtonPress, 400, 300))
    s = src.sample(0.0)
    assert s.gaze_xy == (400, 300)
    assert s.activation_edge is True
    assert src.sample(0.0).activation_edge is False  # one-shot


def test_return_key_sets_pause_edge_once(qtbot) -> None:
    w = _widget(qtbot)
    src = SimulatorInputSource(w)
    QApplication.sendEvent(
        w, QKeyEvent(QEvent.Type.KeyPress, Qt.Key_Return, Qt.NoModifier)
    )
    assert src.sample(0.0).pause_edge is True
    assert src.sample(0.0).pause_edge is False


def test_leave_clears_gaze(qtbot) -> None:
    w = _widget(qtbot)
    src = SimulatorInputSource(w)
    QApplication.sendEvent(w, _mouse(QEvent.Type.MouseMove, 10, 10))
    QApplication.sendEvent(w, QEvent(QEvent.Type.Leave))
    assert src.sample(0.0).gaze_xy is None


def test_f9_debug_fire_edge_only_with_env(qtbot, monkeypatch) -> None:
    monkeypatch.setenv("DOOMED_PRISM_DEBUG_FIRE", "1")
    w = _widget(qtbot)
    src = SimulatorInputSource(w)
    QApplication.sendEvent(w, QKeyEvent(QEvent.Type.KeyPress, Qt.Key_F9, Qt.NoModifier))
    assert src.sample(0.0).debug_fire_edge is True


def test_f9_is_inert_without_the_env(qtbot, monkeypatch) -> None:
    monkeypatch.delenv("DOOMED_PRISM_DEBUG_FIRE", raising=False)
    w = _widget(qtbot)
    src = SimulatorInputSource(w)
    QApplication.sendEvent(w, QKeyEvent(QEvent.Type.KeyPress, Qt.Key_F9, Qt.NoModifier))
    assert src.sample(0.0).debug_fire_edge is False
