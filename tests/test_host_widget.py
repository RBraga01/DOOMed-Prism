"""The pure-Python host tests: only the missing-Qt-dependency contract."""

from __future__ import annotations

import pytest


def test_missing_qt_dependency_fails_explicitly() -> None:
    """Catches a silent skip or vague failure when the Raven extra is absent."""
    import pewpew.host_widget as module

    if module.DoomHostWidget.__bases__ != (object,):
        pytest.skip("a real Qt binding is available in this environment")

    with pytest.raises(RuntimeError, match="requires the PySide6 Raven extra"):
        module.DoomHostWidget()
