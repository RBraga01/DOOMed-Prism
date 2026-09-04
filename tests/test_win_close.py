"""Tests for the cooperative native-close helper."""

from __future__ import annotations

import sys

import pytest

from pewpew.win_close import request_close_windows


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX no-op path only")
def test_request_close_windows_is_a_noop_off_windows() -> None:
    assert request_close_windows(4321) == 0
