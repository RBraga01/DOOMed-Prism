"""Cooperative native window closure for a supervised child (Windows only)."""

from __future__ import annotations

import sys

_WM_CLOSE = 0x0010


def request_close_windows(pid: int) -> int:
    """Post WM_CLOSE to every top-level window owned by ``pid``. No-op off Windows."""
    if sys.platform != "win32":
        return 0

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]

    closed = 0

    def _callback(hwnd: int, _lparam: int) -> bool:
        nonlocal closed
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)
            closed += 1
        return True

    user32.EnumWindows(enum_proc(_callback), 0)
    return closed
