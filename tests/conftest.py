"""Load pytest-qt only after a headless-safe Qt initialization probe."""

from __future__ import annotations

import os
import subprocess
import sys


if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qt_can_initialize() -> bool:
    """Contain Qt platform/plugin aborts in a probe subprocess."""
    probe = (
        "from PySide6.QtWidgets import QApplication; "
        "application = QApplication([]); application.quit()"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        env=os.environ,
        capture_output=True,
    )
    return result.returncode == 0


if _qt_can_initialize():
    pytest_plugins = ["pytestqt.plugin"]
