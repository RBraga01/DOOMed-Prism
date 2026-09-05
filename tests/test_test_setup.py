"""Tests for the headless-safe pytest Qt setup."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


CONFTEST_PATH = Path(__file__).with_name("conftest.py")


def _platform_after_isolated_setup(configured_platform: str | None) -> str:
    """Run the pytest setup with a controlled incoming platform selection."""
    environment = os.environ.copy()
    if configured_platform is None:
        environment.pop("QT_QPA_PLATFORM", None)
    else:
        environment["QT_QPA_PLATFORM"] = configured_platform

    script = (
        "import os, runpy, sys; "
        "runpy.run_path(sys.argv[1]); "
        "print(os.environ['QT_QPA_PLATFORM'])"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(CONFTEST_PATH)],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows retains native Qt tests")
def test_non_windows_qt_tests_default_to_offscreen() -> None:
    """Use the headless Qt platform when the caller did not select one."""
    assert _platform_after_isolated_setup(None) == "offscreen"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows retains native Qt tests")
def test_non_windows_qt_tests_preserve_preconfigured_platform() -> None:
    """Keep a caller-selected Qt platform authoritative."""
    assert _platform_after_isolated_setup("minimal") == "minimal"
