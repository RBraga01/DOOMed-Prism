"""Tests for reversible native Windows child-window embedding."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pewpew.windows import (
    WS_CHILD,
    WS_POPUP,
    CtypesWin32Api,
    UnsupportedPlatform,
    WindowDiscoveryTimeout,
    WindowEmbeddingRollbackError,
    WindowRect,
    embed_window,
    find_top_level_window,
)


@dataclass
class _WindowState:
    pid: int
    visible: bool
    parent: int
    style: int
    rectangle: WindowRect


class _FakeWin32Api:
    """Stateful substitute for the external Win32 boundary."""

    def __init__(self, windows: dict[int, _WindowState]) -> None:
        self.windows = deepcopy(windows)
        self.enumeration_frames: list[list[int]] = [list(windows)]
        self.enumeration_calls = 0
        self.mutation_calls: list[tuple[object, ...]] = []
        self.client_rect_requests: list[int] = []
        self.forced_client_rectangle: WindowRect | None = None
        self.close_requests: list[int] = []
        self.failures: list[str] = []

    def enum_windows(self) -> list[int]:
        frame_index = min(self.enumeration_calls, len(self.enumeration_frames) - 1)
        self.enumeration_calls += 1
        return list(self.enumeration_frames[frame_index])

    def get_window_process_id(self, hwnd: int) -> int:
        return self.windows[hwnd].pid

    def is_window_visible(self, hwnd: int) -> bool:
        return self.windows[hwnd].visible

    def get_parent(self, hwnd: int) -> int:
        return self.windows[hwnd].parent

    def set_parent(self, hwnd: int, parent_hwnd: int) -> None:
        self._maybe_fail("set_parent")
        self.windows[hwnd].parent = parent_hwnd
        self.mutation_calls.append(("set_parent", hwnd, parent_hwnd))

    def get_window_style(self, hwnd: int) -> int:
        return self.windows[hwnd].style

    def set_window_style(self, hwnd: int, style: int) -> None:
        self._maybe_fail("set_window_style")
        self.windows[hwnd].style = style
        self.mutation_calls.append(("set_window_style", hwnd, style))

    def get_window_rect(self, hwnd: int) -> WindowRect:
        return self.windows[hwnd].rectangle

    def get_client_rect(self, hwnd: int) -> WindowRect:
        self.client_rect_requests.append(hwnd)
        if self.forced_client_rectangle is not None:
            return self.forced_client_rectangle
        rectangle = self.windows[hwnd].rectangle
        if self.windows[hwnd].style & 0x00C40000:
            return WindowRect(0, 0, rectangle.width - 16, rectangle.height - 39)
        return WindowRect(0, 0, rectangle.width, rectangle.height)

    def set_window_position(
        self, hwnd: int, x: int, y: int, width: int, height: int
    ) -> None:
        self._maybe_fail("set_window_position")
        self.windows[hwnd].rectangle = WindowRect(x, y, x + width, y + height)
        self.mutation_calls.append(
            ("set_window_position", hwnd, x, y, width, height)
        )

    def show_window(self, hwnd: int) -> None:
        self._maybe_fail("show_window")
        self.windows[hwnd].visible = True
        self.mutation_calls.append(("show_window", hwnd))

    def post_close(self, hwnd: int) -> None:
        self._maybe_fail("post_close")
        self.close_requests.append(hwnd)

    def _maybe_fail(self, operation: str) -> None:
        if self.failures and self.failures[0] == operation:
            self.failures.pop(0)
            raise OSError(f"injected {operation} failure")


class _FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.sleeps.append(duration)
        self.now += duration


def _source_window() -> dict[int, _WindowState]:
    return {
        101: _WindowState(
            pid=4001,
            visible=True,
            parent=77,
            style=WS_POPUP | 0x00040000,
            rectangle=WindowRect(23, 41, 823, 641),
        )
    }


def test_discovery_ignores_invisible_and_foreign_process_windows() -> None:
    """Catches discovery selecting a hidden or different process's window."""
    api = _FakeWin32Api(
        {
            10: _WindowState(42, False, 0, WS_POPUP, WindowRect(0, 0, 1, 1)),
            11: _WindowState(99, True, 0, WS_POPUP, WindowRect(0, 0, 1, 1)),
            12: _WindowState(42, True, 0, WS_POPUP, WindowRect(0, 0, 1, 1)),
        }
    )

    hwnd = find_top_level_window(42, timeout_s=0, api=api)

    assert hwnd == 12


def test_discovery_retries_until_the_process_window_appears() -> None:
    """Catches discovery giving up before a delayed SDL window is created."""
    api = _FakeWin32Api(_source_window())
    api.enumeration_frames = [[], [], [101]]
    fake_time = _FakeTime()

    hwnd = find_top_level_window(
        4001,
        timeout_s=0.2,
        api=api,
        monotonic=fake_time.monotonic,
        sleep=fake_time.sleep,
    )

    assert hwnd == 101
    assert api.enumeration_calls == 3
    assert fake_time.sleeps == [0.05, 0.05]


def test_discovery_raises_after_retrying_through_the_timeout() -> None:
    """Catches an unbounded wait or a timeout that performs no retries."""
    api = _FakeWin32Api({})
    api.enumeration_frames = [[]]
    fake_time = _FakeTime()

    with pytest.raises(WindowDiscoveryTimeout):
        find_top_level_window(
            4001,
            timeout_s=0.12,
            api=api,
            monotonic=fake_time.monotonic,
            sleep=fake_time.sleep,
        )

    assert api.enumeration_calls == 4
    assert fake_time.now == pytest.approx(0.12)


def test_embedding_records_original_state_and_applies_child_window_state() -> None:
    """Catches lost restoration data or incorrect child-window geometry/style."""
    source = _source_window()
    api = _FakeWin32Api(source)

    embedded = embed_window(101, 808, width=640, height=480, api=api)

    assert embedded.child_hwnd == 101
    assert embedded.original_parent == 77
    assert embedded.original_style == WS_POPUP | 0x00040000
    assert embedded.original_rectangle == WindowRect(23, 41, 823, 641)
    assert api.windows[101] == _WindowState(
        pid=4001,
        visible=True,
        parent=808,
        style=WS_CHILD,
        rectangle=WindowRect(0, 0, 640, 480),
    )
    assert api.client_rect_requests == [101]


def test_embedding_rejects_and_rolls_back_an_inexact_native_client_size() -> None:
    """Catches DPI or frame virtualization leaving fewer than 640x480 client pixels."""
    source = _source_window()
    api = _FakeWin32Api(source)
    api.forced_client_rectangle = WindowRect(0, 0, 624, 441)

    with pytest.raises(RuntimeError, match="client size"):
        embed_window(101, 808, width=640, height=480, api=api)

    assert api.windows[101] == source[101]
    assert api.client_rect_requests == [101]


def test_restore_reinstates_original_state_only_once() -> None:
    """Catches lossy restoration or repeated native mutations during cleanup."""
    source = _source_window()
    api = _FakeWin32Api(source)
    embedded = embed_window(101, 808, width=640, height=480, api=api)

    embedded.restore()
    calls_after_first_restore = list(api.mutation_calls)
    embedded.restore()

    assert api.windows[101] == source[101]
    assert api.mutation_calls == calls_after_first_restore
    assert api.mutation_calls[-3:] == [
        ("set_parent", 101, 77),
        ("set_window_style", 101, WS_POPUP | 0x00040000),
        ("set_window_position", 101, 23, 41, 800, 600),
    ]


@pytest.mark.parametrize(
    ("failed_operation", "expected_calls"),
    [
        ("set_window_style", []),
        (
            "set_parent",
            [
                ("set_window_style", 101, WS_CHILD),
                ("set_window_style", 101, WS_POPUP | 0x00040000),
            ],
        ),
        (
            "set_window_position",
            [
                ("set_window_style", 101, WS_CHILD),
                ("set_parent", 101, 808),
                ("set_parent", 101, 77),
                ("set_window_style", 101, WS_POPUP | 0x00040000),
            ],
        ),
        (
            "show_window",
            [
                ("set_window_style", 101, WS_CHILD),
                ("set_parent", 101, 808),
                ("set_window_position", 101, 0, 0, 640, 480),
                ("set_parent", 101, 77),
                ("set_window_style", 101, WS_POPUP | 0x00040000),
                ("set_window_position", 101, 23, 41, 800, 600),
            ],
        ),
    ],
)
def test_partial_embedding_failure_rolls_back_every_completed_mutation(
    failed_operation: str, expected_calls: list[tuple[object, ...]]
) -> None:
    """Catches a partial failure leaving the engine window embedded or resized."""
    source = _source_window()
    api = _FakeWin32Api(source)
    api.failures = [failed_operation]

    with pytest.raises(OSError, match=f"injected {failed_operation} failure"):
        embed_window(101, 808, width=640, height=480, api=api)

    assert api.windows[101] == source[101]
    assert api.mutation_calls == expected_calls


def test_failed_automatic_rollback_exposes_recovery_for_remaining_mutations() -> None:
    """Catches rollback failure discarding the only retryable recovery state."""
    source = _source_window()
    api = _FakeWin32Api(source)
    api.failures = ["set_window_position", "set_parent"]

    with pytest.raises(WindowEmbeddingRollbackError) as caught:
        embed_window(101, 808, width=640, height=480, api=api)

    error = caught.value
    assert str(error.embedding_error) == "injected set_window_position failure"
    assert str(error.rollback_error) == "injected set_parent failure"
    assert error.__cause__ is error.rollback_error
    assert error.rollback_error.__context__ is error.embedding_error
    assert api.windows[101] == _WindowState(
        pid=4001,
        visible=True,
        parent=808,
        style=WS_POPUP | 0x00040000,
        rectangle=WindowRect(23, 41, 823, 641),
    )

    api.failures.clear()
    error.embedded_window.restore()

    assert api.windows[101] == source[101]
    assert api.mutation_calls == [
        ("set_window_style", 101, WS_CHILD),
        ("set_parent", 101, 808),
        ("set_window_style", 101, WS_POPUP | 0x00040000),
        ("set_parent", 101, 77),
    ]


def test_graceful_close_posts_wm_close_only_to_windows_owned_by_process() -> None:
    """Catches graceful shutdown closing another process or using hard termination."""
    import pewpew.windows as windows

    api = _FakeWin32Api(
        {
            10: _WindowState(42, True, 0, WS_POPUP, WindowRect(0, 0, 1, 1)),
            11: _WindowState(99, True, 0, WS_POPUP, WindowRect(0, 0, 1, 1)),
            12: _WindowState(42, False, 0, WS_POPUP, WindowRect(0, 0, 1, 1)),
        }
    )

    count = windows.request_close_windows(42, api=api)

    assert count == 2
    assert api.close_requests == [10, 12]


@pytest.mark.skipif(sys.platform == "win32", reason="requires a non-Windows host")
def test_real_adapter_rejects_unsupported_platforms() -> None:
    """Catches accidental user32 access while importing or running cross-platform."""
    with pytest.raises(UnsupportedPlatform):
        CtypesWin32Api()
