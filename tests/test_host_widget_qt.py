"""Real PySide6 and pytest-qt coverage for the neutral Doom host widget."""

from __future__ import annotations

import pytest

try:
    from PySide6.QtCore import Qt
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

from pewpew.host_widget import DoomHostWidget


class _Engine:
    def __init__(self) -> None:
        self.stop_calls = 0

    def start(self) -> int:
        return 8128

    def stop(self) -> None:
        self.stop_calls += 1


class _EmbeddedWindow:
    def __init__(self) -> None:
        self.restore_calls = 0

    def restore(self) -> None:
        self.restore_calls += 1


def test_real_widget_has_the_fixed_native_viewport_geometry(qtbot: object) -> None:
    """Catches real-QWidget geometry or native-attribute regressions."""
    host = DoomHostWidget()
    qtbot.addWidget(host)  # type: ignore[attr-defined]

    assert host.size().toTuple() == (640, 640)
    assert isinstance(host.viewport, QWidget)
    assert host.viewport.objectName() == "viewport"
    assert host.viewport.geometry().getRect() == (0, 80, 640, 480)
    assert host.viewport.testAttribute(Qt.WA_NativeWindow)
    assert int(host.viewport.winId()) != 0
    assert not host.autoFillBackground()
    assert host.testAttribute(Qt.WA_NoSystemBackground)
    assert not host.testAttribute(Qt.WA_OpaquePaintEvent)


def test_real_about_to_quit_signal_runs_cleanup(qtbot: object) -> None:
    """Catches a disconnected real QApplication shutdown signal."""
    engine = _Engine()
    embedded = _EmbeddedWindow()
    host = DoomHostWidget(engine=engine, embedded_window=embedded)
    qtbot.addWidget(host)  # type: ignore[attr-defined]

    QApplication.instance().aboutToQuit.emit()  # type: ignore[union-attr]

    assert engine.stop_calls == 1
    assert embedded.restore_calls == 1


def test_real_close_event_runs_cleanup(qtbot: object) -> None:
    """Catches a real QWidget close event that bypasses host cleanup."""
    engine = _Engine()
    embedded = _EmbeddedWindow()
    host = DoomHostWidget(engine=engine, embedded_window=embedded)
    qtbot.addWidget(host)  # type: ignore[attr-defined]

    host.close()

    assert engine.stop_calls == 1
    assert embedded.restore_calls == 1
