"""Tests for the neutral Qt host using a project-owned headless Qt fake."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from pewpew.windows import WindowEmbeddingRollbackError


class _Signal:
    def __init__(self) -> None:
        self._callbacks: list[object] = []

    def connect(self, callback: object) -> None:
        self._callbacks.append(callback)

    def emit(self) -> None:
        for callback in list(self._callbacks):
            callback()  # type: ignore[operator]


class _Size:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def toTuple(self) -> tuple[int, int]:
        return self.width, self.height


class _Rectangle:
    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self._values = (x, y, width, height)

    def getRect(self) -> tuple[int, int, int, int]:
        return self._values


class _Qt:
    WA_NativeWindow = 1
    WA_NoSystemBackground = 2
    WA_OpaquePaintEvent = 3


class _QApplication:
    _application: _QApplication | None = None

    def __init__(self) -> None:
        self.aboutToQuit = _Signal()

    @classmethod
    def instance(cls) -> _QApplication:
        if cls._application is None:
            cls._application = cls()
        return cls._application


class _QWidget:
    _next_window_id = 100

    def __init__(self, parent: object | None = None) -> None:
        self.parent = parent
        self._size = _Size(0, 0)
        self._geometry = _Rectangle(0, 0, 0, 0)
        self._attributes: dict[object, bool] = {}
        self._object_name = ""
        self._auto_fill_background = False
        self._window_id = self._next_window_id
        type(self)._next_window_id += 1

    def setFixedSize(self, width: int, height: int) -> None:
        self._size = _Size(width, height)

    def size(self) -> _Size:
        return self._size

    def setAutoFillBackground(self, enabled: bool) -> None:
        self._auto_fill_background = enabled

    def autoFillBackground(self) -> bool:
        return self._auto_fill_background

    def setAttribute(self, attribute: object, enabled: bool = True) -> None:
        self._attributes[attribute] = enabled

    def testAttribute(self, attribute: object) -> bool:
        return self._attributes.get(attribute, False)

    def setObjectName(self, name: str) -> None:
        self._object_name = name

    def objectName(self) -> str:
        return self._object_name

    def setGeometry(self, x: int, y: int, width: int, height: int) -> None:
        self._geometry = _Rectangle(x, y, width, height)

    def geometry(self) -> _Rectangle:
        return self._geometry

    def winId(self) -> int:
        return self._window_id

    def showEvent(self, event: object) -> None:
        del event

    def show(self) -> None:
        self.showEvent(_QShowEvent())

    def close(self) -> None:
        self.closeEvent(_QCloseEvent())


class _QCloseEvent:
    def __init__(self) -> None:
        self.accepted = False

    def accept(self) -> None:
        self.accepted = True


class _QShowEvent:
    pass


@pytest.fixture
def host_widget(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Reload the host with the minimal project-owned Qt contract it uses."""
    import pewpew.host_widget as module

    qt_core = ModuleType("PySide6.QtCore")
    qt_core.Qt = _Qt
    qt_gui = ModuleType("PySide6.QtGui")
    qt_gui.QCloseEvent = _QCloseEvent
    qt_gui.QShowEvent = _QShowEvent
    qt_widgets = ModuleType("PySide6.QtWidgets")
    qt_widgets.QApplication = _QApplication
    qt_widgets.QWidget = _QWidget
    pyside = ModuleType("PySide6")

    with monkeypatch.context() as context:
        context.setitem(sys.modules, "PySide6", pyside)
        context.setitem(sys.modules, "PySide6.QtCore", qt_core)
        context.setitem(sys.modules, "PySide6.QtGui", qt_gui)
        context.setitem(sys.modules, "PySide6.QtWidgets", qt_widgets)
        yield importlib.reload(module)

    importlib.reload(module)


class _Engine:
    def __init__(self, *, fail_first_stop: bool = False) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self._fail_first_stop = fail_first_stop

    def start(self) -> int:
        self.start_calls += 1
        return 8128

    def stop(self) -> None:
        self.stop_calls += 1
        if self._fail_first_stop and self.stop_calls == 1:
            raise OSError("temporary engine-stop failure")


class _EmbeddedWindow:
    def __init__(self, *, fail_first_restore: bool = False) -> None:
        self.restore_calls = 0
        self._fail_first_restore = fail_first_restore

    def restore(self) -> None:
        self.restore_calls += 1
        if self._fail_first_restore and self.restore_calls == 1:
            raise OSError("temporary restore failure")


def test_missing_qt_dependency_fails_explicitly() -> None:
    """Catches a silent test skip or a vague desktop-host setup failure."""
    import pewpew.host_widget as module

    if module.DoomHostWidget.__bases__ != (object,):
        pytest.skip("a real Qt binding is available in this environment")

    with pytest.raises(RuntimeError, match="requires the PySide6 Raven extra"):
        module.DoomHostWidget()


def test_host_has_an_unpainted_640_square_with_a_native_doom_viewport(
    host_widget: Any,
) -> None:
    """Catches geometry or painting that obscures either 80-pixel Raven margin."""
    host = host_widget.DoomHostWidget()

    assert host.size().toTuple() == (640, 640)
    assert isinstance(host.viewport, _QWidget)
    assert host.viewport.objectName() == "viewport"
    assert host.viewport.geometry().getRect() == (0, 80, 640, 480)
    assert host.viewport.testAttribute(_Qt.WA_NativeWindow)
    assert int(host.viewport.winId()) != 0
    assert not host.autoFillBackground()
    assert host.testAttribute(_Qt.WA_NoSystemBackground)
    assert not host.testAttribute(_Qt.WA_OpaquePaintEvent)


def test_about_to_quit_stops_and_restores(host_widget: Any) -> None:
    """Catches removal of the application-shutdown cleanup connection."""
    engine = _Engine()
    embedded = _EmbeddedWindow()
    host_widget.DoomHostWidget(engine=engine, embedded_window=embedded)

    _QApplication.instance().aboutToQuit.emit()

    assert engine.stop_calls == 1
    assert embedded.restore_calls == 1


def test_close_event_stops_and_restores(host_widget: Any) -> None:
    """Catches removal of the ordinary-widget-close cleanup path."""
    engine = _Engine()
    embedded = _EmbeddedWindow()
    host = host_widget.DoomHostWidget(engine=engine, embedded_window=embedded)

    host.close()

    assert engine.stop_calls == 1
    assert embedded.restore_calls == 1


def test_successful_cleanup_is_idempotent(host_widget: Any) -> None:
    """Catches duplicate native restore or process-stop requests after shutdown."""
    engine = _Engine()
    embedded = _EmbeddedWindow()
    host = host_widget.DoomHostWidget(engine=engine, embedded_window=embedded)

    host.cleanup()
    host.cleanup()

    assert engine.stop_calls == 1
    assert embedded.restore_calls == 1


def test_cleanup_retries_each_transiently_failed_operation(host_widget: Any) -> None:
    """Catches cleanup marking failed restore or stop operations as complete."""
    engine = _Engine(fail_first_stop=True)
    embedded = _EmbeddedWindow(fail_first_restore=True)
    host = host_widget.DoomHostWidget(engine=engine, embedded_window=embedded)

    with pytest.raises(OSError, match="temporary restore failure"):
        host.cleanup()
    host.cleanup()

    assert engine.stop_calls == 2
    assert embedded.restore_calls == 2


def test_embedding_rollback_keeps_the_recoverable_embedded_window(
    host_widget: Any,
) -> None:
    """Catches loss of the window state exposed by failed native embedding."""
    engine = _Engine()
    embedded = _EmbeddedWindow(fail_first_restore=True)
    config = SimpleNamespace(viewport_width=640, viewport_height=480)

    def find_window(pid: int, timeout_s: float) -> int:
        assert (pid, timeout_s) == (8128, 10.0)
        return 913

    def embed(*_: object) -> object:
        raise WindowEmbeddingRollbackError(
            SimpleNamespace(restore=embedded.restore),
            OSError("embedding failed"),
            OSError("rollback failed"),
        )

    host = host_widget.DoomHostWidget(
        config,
        engine=engine,
        window_finder=find_window,
        window_embedder=embed,
    )

    with pytest.raises(WindowEmbeddingRollbackError, match="rollback is incomplete"):
        host.show()
    host.cleanup()

    assert engine.stop_calls == 1
    assert embedded.restore_calls == 2


def test_show_launches_and_embeds_the_engine_into_the_native_viewport(
    host_widget: Any,
) -> None:
    """Catches startup that skips native viewport creation or uses wrong dimensions."""
    engine = _Engine()
    calls: list[tuple[object, ...]] = []
    config = SimpleNamespace(viewport_width=640, viewport_height=480)

    def find_window(pid: int, timeout_s: float) -> int:
        calls.append(("find", pid, timeout_s))
        return 913

    def embed(
        child_hwnd: int, parent_hwnd: int, width: int, height: int
    ) -> _EmbeddedWindow:
        calls.append(("embed", child_hwnd, parent_hwnd, width, height))
        return _EmbeddedWindow()

    host = host_widget.DoomHostWidget(
        config,
        engine=engine,
        window_finder=find_window,
        window_embedder=embed,
    )

    host.show()

    assert engine.start_calls == 1
    assert calls == [
        ("find", 8128, 10.0),
        ("embed", 913, int(host.viewport.winId()), 640, 480),
    ]
