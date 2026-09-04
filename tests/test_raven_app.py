"""Tests for the optional Raven wrapper using project-owned Raven fakes."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

from pewpew.cli import main


class _FakeRavenApp:
    def __init__(self) -> None:
        self.added_widgets: list[tuple[object, int, int]] = []

    def add_widget(self, widget: object, x: int, y: int) -> None:
        self.added_widgets.append((widget, x, y))


class _FakeRunApp:
    calls: list[tuple[object, str, str]] = []

    @classmethod
    def run(cls, factory: object, app_id: str, app_key: str) -> None:
        cls.calls.append((factory(), app_id, app_key))  # type: ignore[operator]


def test_importing_wrapper_does_not_import_raven(monkeypatch: pytest.MonkeyPatch) -> None:
    """Catches an accidental module-level dependency on Raven Framework."""
    monkeypatch.delitem(sys.modules, "core", raising=False)
    monkeypatch.delitem(sys.modules, "core.raven_app", raising=False)
    monkeypatch.delitem(sys.modules, "core.run_app", raising=False)

    import pewpew.raven_app as raven_app

    importlib.reload(raven_app)

    assert "core.raven_app" not in sys.modules
    assert "core.run_app" not in sys.modules


def test_raven_wrapper_adds_exactly_one_host_at_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a Raven app with extra widgets, wrong coordinates, or credentials."""
    core = ModuleType("core")
    raven_module = ModuleType("core.raven_app")
    run_module = ModuleType("core.run_app")
    raven_module.RavenApp = _FakeRavenApp
    run_module.RunApp = _FakeRunApp
    monkeypatch.setitem(sys.modules, "core", core)
    monkeypatch.setitem(sys.modules, "core.raven_app", raven_module)
    monkeypatch.setitem(sys.modules, "core.run_app", run_module)

    import pewpew.raven_app as raven_app

    class Host:
        def __init__(self, config: object) -> None:
            self.config = config

    _FakeRunApp.calls.clear()
    monkeypatch.setattr(raven_app, "DoomHostWidget", Host)
    config = object()

    raven_app.run_desktop(config)  # type: ignore[arg-type]

    app, app_id, app_key = _FakeRunApp.calls[0]
    assert (app_id, app_key) == ("", "")
    assert app.added_widgets == [(app.host_widget, 0, 0)]
    assert isinstance(app.host_widget, Host)
    assert app.host_widget.config is config


def test_cli_passes_validated_configuration_to_raven_entry_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches CLI delegation without the validated RuntimeConfig instance."""
    crispy_exe = tmp_path / "crispy-doom"
    iwad = tmp_path / "freedoom1.wad"
    crispy_exe.touch()
    iwad.touch()
    monkeypatch.setenv("DOOMED_PRISM_CRISPY_EXE", str(crispy_exe))
    monkeypatch.setenv("DOOMED_PRISM_IWAD", str(iwad))
    received: list[object] = []

    import pewpew.raven_app as raven_app

    monkeypatch.setattr(raven_app, "run_desktop", received.append)

    assert main(["run-desktop"]) == 0
    assert received[0].crispy_exe == crispy_exe.resolve()
    assert received[0].iwad == iwad.resolve()
