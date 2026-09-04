"""Reversible Win32 embedding for an external SDL game window."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
import sys
import time
from typing import Protocol


if sys.platform == "win32":  # pragma: no cover - exercised on Windows hosts
    import ctypes as _ctypes
    from ctypes import wintypes as _wintypes
else:  # Keep this module importable for protocol-based tests on every platform.
    _ctypes = None
    _wintypes = None


GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_NONCLIENT_FRAME = (
    WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
)
WM_CLOSE = 0x0010

_POLL_INTERVAL_S = 0.05
_SW_SHOW = 5
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020


class UnsupportedPlatform(RuntimeError):
    """Raised when the concrete Win32 adapter is requested off Windows."""


class WindowDiscoveryTimeout(TimeoutError):
    """Raised when a process does not create a visible window in time."""


class WindowEmbeddingRollbackError(RuntimeError):
    """Raised when embedding fails and its automatic rollback is incomplete."""

    def __init__(
        self,
        embedded_window: EmbeddedWindow,
        embedding_error: BaseException,
        rollback_error: Exception,
    ) -> None:
        super().__init__("window embedding failed and rollback is incomplete")
        self.embedded_window = embedded_window
        self.embedding_error = embedding_error
        self.rollback_error = rollback_error


@dataclass(frozen=True)
class WindowRect:
    """A Win32 window rectangle in left, top, right, bottom form."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


class Win32Api(Protocol):
    """Injectable boundary containing only native operations this module needs."""

    def enum_windows(self) -> Iterable[int]: ...

    def get_window_process_id(self, hwnd: int) -> int: ...

    def is_window_visible(self, hwnd: int) -> bool: ...

    def get_parent(self, hwnd: int) -> int: ...

    def set_parent(self, hwnd: int, parent_hwnd: int) -> None: ...

    def get_window_style(self, hwnd: int) -> int: ...

    def set_window_style(self, hwnd: int, style: int) -> None: ...

    def get_window_rect(self, hwnd: int) -> WindowRect: ...

    def get_client_rect(self, hwnd: int) -> WindowRect: ...

    def set_window_position(
        self, hwnd: int, x: int, y: int, width: int, height: int
    ) -> None: ...

    def show_window(self, hwnd: int) -> None: ...

    def post_close(self, hwnd: int) -> None: ...


class CtypesWin32Api:
    """Concrete ``user32`` implementation of :class:`Win32Api`."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise UnsupportedPlatform("native window embedding requires Windows")
        assert _ctypes is not None
        assert _wintypes is not None
        self._ctypes = _ctypes
        self._wintypes = _wintypes
        self._user32 = _ctypes.windll.user32
        self._kernel32 = _ctypes.windll.kernel32
        self._enum_callback_type = _ctypes.WINFUNCTYPE(
            _wintypes.BOOL, _wintypes.HWND, _wintypes.LPARAM
        )
        self._configure_signatures()

    def _configure_signatures(self) -> None:
        c = self._ctypes
        w = self._wintypes
        user32 = self._user32
        self._kernel32.SetLastError.argtypes = [w.DWORD]
        self._kernel32.SetLastError.restype = None
        self._kernel32.GetLastError.argtypes = []
        self._kernel32.GetLastError.restype = w.DWORD
        user32.EnumWindows.argtypes = [self._enum_callback_type, w.LPARAM]
        user32.EnumWindows.restype = w.BOOL
        user32.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
        user32.GetWindowThreadProcessId.restype = w.DWORD
        user32.IsWindowVisible.argtypes = [w.HWND]
        user32.IsWindowVisible.restype = w.BOOL
        user32.GetParent.argtypes = [w.HWND]
        user32.GetParent.restype = w.HWND
        user32.SetParent.argtypes = [w.HWND, w.HWND]
        user32.SetParent.restype = w.HWND
        user32.GetWindowLongPtrW.argtypes = [w.HWND, c.c_int]
        user32.GetWindowLongPtrW.restype = c.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [w.HWND, c.c_int, c.c_ssize_t]
        user32.SetWindowLongPtrW.restype = c.c_ssize_t
        user32.GetWindowRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
        user32.GetWindowRect.restype = w.BOOL
        user32.GetClientRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
        user32.GetClientRect.restype = w.BOOL
        user32.SetWindowPos.argtypes = [
            w.HWND,
            w.HWND,
            c.c_int,
            c.c_int,
            c.c_int,
            c.c_int,
            w.UINT,
        ]
        user32.SetWindowPos.restype = w.BOOL
        user32.ShowWindow.argtypes = [w.HWND, c.c_int]
        user32.ShowWindow.restype = w.BOOL
        user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        user32.PostMessageW.restype = w.BOOL

    def enum_windows(self) -> list[int]:
        handles: list[int] = []

        @self._enum_callback_type
        def collect(hwnd: int, _lparam: int) -> bool:
            handles.append(int(hwnd))
            return True

        if not self._user32.EnumWindows(collect, 0):
            raise self._ctypes.WinError(self._last_error())
        return handles

    def get_window_process_id(self, hwnd: int) -> int:
        process_id = self._wintypes.DWORD()
        if not self._user32.GetWindowThreadProcessId(
            hwnd, self._ctypes.byref(process_id)
        ):
            raise self._ctypes.WinError(self._last_error())
        return int(process_id.value)

    def is_window_visible(self, hwnd: int) -> bool:
        return bool(self._user32.IsWindowVisible(hwnd))

    def get_parent(self, hwnd: int) -> int:
        self._clear_last_error()
        parent = self._user32.GetParent(hwnd)
        self._raise_if_null_error(parent)
        return int(parent or 0)

    def set_parent(self, hwnd: int, parent_hwnd: int) -> None:
        self._clear_last_error()
        previous_parent = self._user32.SetParent(hwnd, parent_hwnd)
        self._raise_if_null_error(previous_parent)

    def get_window_style(self, hwnd: int) -> int:
        self._clear_last_error()
        style = self._user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
        self._raise_if_null_error(style)
        return int(style)

    def set_window_style(self, hwnd: int, style: int) -> None:
        self._clear_last_error()
        previous_style = self._user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style)
        self._raise_if_null_error(previous_style)

    def get_window_rect(self, hwnd: int) -> WindowRect:
        rectangle = self._wintypes.RECT()
        if not self._user32.GetWindowRect(hwnd, self._ctypes.byref(rectangle)):
            raise self._ctypes.WinError(self._last_error())
        return WindowRect(
            int(rectangle.left),
            int(rectangle.top),
            int(rectangle.right),
            int(rectangle.bottom),
        )

    def get_client_rect(self, hwnd: int) -> WindowRect:
        rectangle = self._wintypes.RECT()
        if not self._user32.GetClientRect(hwnd, self._ctypes.byref(rectangle)):
            raise self._ctypes.WinError(self._last_error())
        return WindowRect(
            int(rectangle.left),
            int(rectangle.top),
            int(rectangle.right),
            int(rectangle.bottom),
        )

    def set_window_position(
        self, hwnd: int, x: int, y: int, width: int, height: int
    ) -> None:
        flags = _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_FRAMECHANGED
        if not self._user32.SetWindowPos(hwnd, 0, x, y, width, height, flags):
            raise self._ctypes.WinError(self._last_error())

    def show_window(self, hwnd: int) -> None:
        self._user32.ShowWindow(hwnd, _SW_SHOW)

    def post_close(self, hwnd: int) -> None:
        if not self._user32.PostMessageW(hwnd, WM_CLOSE, 0, 0):
            raise self._ctypes.WinError(self._last_error())

    def _raise_if_null_error(self, result: object) -> None:
        if not result:
            error = self._last_error()
            if error:
                raise self._ctypes.WinError(error)

    def _clear_last_error(self) -> None:
        self._kernel32.SetLastError(0)

    def _last_error(self) -> int:
        return int(self._kernel32.GetLastError())


@dataclass
class EmbeddedWindow:
    """Original native state plus an idempotent restoration operation."""

    child_hwnd: int
    original_parent: int
    original_style: int
    original_rectangle: WindowRect
    _api: Win32Api = field(repr=False)
    _parent_pending: bool = field(default=True, repr=False)
    _style_pending: bool = field(default=True, repr=False)
    _rectangle_pending: bool = field(default=True, repr=False)

    def restore(self) -> None:
        """Reinstate each part of the original native state at most once."""
        errors: list[Exception] = []

        if self._parent_pending:
            try:
                self._api.set_parent(self.child_hwnd, self.original_parent)
            except Exception as error:
                errors.append(error)
            else:
                self._parent_pending = False

        if self._style_pending:
            try:
                self._api.set_window_style(self.child_hwnd, self.original_style)
            except Exception as error:
                errors.append(error)
            else:
                self._style_pending = False

        if self._rectangle_pending:
            rectangle = self.original_rectangle
            try:
                self._api.set_window_position(
                    self.child_hwnd,
                    rectangle.left,
                    rectangle.top,
                    rectangle.width,
                    rectangle.height,
                )
            except Exception as error:
                errors.append(error)
            else:
                self._rectangle_pending = False

        if errors:
            raise errors[0]


def find_top_level_window(
    pid: int,
    timeout_s: float,
    *,
    api: Win32Api | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Return the first visible top-level window owned by ``pid``."""
    native = api if api is not None else CtypesWin32Api()
    deadline = monotonic() + max(timeout_s, 0.0)

    while True:
        for hwnd in native.enum_windows():
            if (
                native.is_window_visible(hwnd)
                and native.get_window_process_id(hwnd) == pid
            ):
                return hwnd

        remaining = deadline - monotonic()
        if remaining <= 0:
            raise WindowDiscoveryTimeout(
                f"no visible top-level window found for process {pid}"
            )
        sleep(min(_POLL_INTERVAL_S, remaining))


def embed_window(
    child_hwnd: int,
    parent_hwnd: int,
    width: int,
    height: int,
    *,
    api: Win32Api | None = None,
) -> EmbeddedWindow:
    """Embed one native window, rolling back if any mutation fails."""
    native = api if api is not None else CtypesWin32Api()
    original_parent = native.get_parent(child_hwnd)
    original_style = native.get_window_style(child_hwnd)
    original_rectangle = native.get_window_rect(child_hwnd)
    embedded = EmbeddedWindow(
        child_hwnd=child_hwnd,
        original_parent=original_parent,
        original_style=original_style,
        original_rectangle=original_rectangle,
        _api=native,
        _parent_pending=False,
        _style_pending=False,
        _rectangle_pending=False,
    )

    try:
        # Remove frame styles as well as WS_POPUP so the requested outer size
        # is also the child client area.  The postcondition below detects any
        # remaining DPI or cross-process SetParent virtualization mismatch.
        embedded_style = (original_style | WS_CHILD) & ~(
            WS_POPUP | WS_NONCLIENT_FRAME
        )
        native.set_window_style(child_hwnd, embedded_style)
        embedded._style_pending = True
        native.set_parent(child_hwnd, parent_hwnd)
        embedded._parent_pending = True
        native.set_window_position(child_hwnd, 0, 0, width, height)
        embedded._rectangle_pending = True
        native.show_window(child_hwnd)
        client_rectangle = native.get_client_rect(child_hwnd)
        if (client_rectangle.width, client_rectangle.height) != (width, height):
            raise RuntimeError(
                "embedded window client size does not match requested "
                f"{width}x{height}"
            )
    except BaseException as embedding_error:
        try:
            embedded.restore()
        except Exception as rollback_error:
            raise WindowEmbeddingRollbackError(
                embedded,
                embedding_error,
                rollback_error,
            ) from rollback_error
        raise

    return embedded


def request_close_windows(pid: int, *, api: Win32Api | None = None) -> int:
    """Post ``WM_CLOSE`` to every native window owned by one child process.

    A process can own auxiliary hidden windows as well as the SDL surface, so
    visibility is intentionally not a filter.  This only requests cooperative
    shutdown; :class:`pewpew.engine.DoomProcess` owns the bounded escalation.
    """
    native = api if api is not None else CtypesWin32Api()
    count = 0
    for hwnd in native.enum_windows():
        if native.get_window_process_id(hwnd) == pid:
            native.post_close(hwnd)
            count += 1
    return count
