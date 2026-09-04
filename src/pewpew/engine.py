"""Supervision for an externally installed Crispy Doom process."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from typing import Protocol

from pewpew.config import RuntimeConfig


class EngineAlreadyRunning(RuntimeError):
    """Raised when a second Crispy Doom child would be launched."""


class _Process(Protocol):
    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def kill(self) -> None: ...


PopenFactory = Callable[[list[str]], _Process]
GracefulClose = Callable[[int], None]


class DoomProcess:
    """Launch and stop one windowed Crispy Doom child at a time."""

    def __init__(
        self,
        config: RuntimeConfig,
        popen_factory: PopenFactory = subprocess.Popen,
        graceful_close: GracefulClose | None = None,
    ) -> None:
        self._config = config
        self._popen_factory = popen_factory
        self._graceful_close = (
            graceful_close if graceful_close is not None else _windows_graceful_close
        )
        self._process: _Process | None = None

    def __enter__(self) -> DoomProcess:
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    def start(self) -> int:
        """Launch the configured Crispy Doom executable and return its PID."""
        if self.poll() is None and self._process is not None:
            raise EngineAlreadyRunning("Crispy Doom is already running")
        self._process = self._popen_factory(self._command())
        return self._process.pid

    def poll(self) -> int | None:
        """Return the child return code, or ``None`` while it is still running."""
        if self._process is None:
            return None
        return self._process.poll()

    def stop(self, timeout_s: float = 3.0) -> None:
        """Stop the live child gracefully, escalating only after a timeout."""
        process = self._process
        if process is None:
            return
        if process.poll() is not None:
            self._process = None
            return

        try:
            # Request that the process close its own windows before escalating.
            # A normal Qt/Raven shutdown must not start by forcefully killing SDL.
            self._graceful_close(process.pid)
        except Exception:
            # A native close-request failure must not strand the supervised child.
            pass
        else:
            try:
                process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                pass
            else:
                self._process = None
                return

        process.terminate()
        try:
            # Keep this wait bounded too.  If it times out, retain the handle
            # so a later cleanup call can retry instead of losing an orphan.
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            raise
        self._process = None

    def _command(self) -> list[str]:
        return [
            str(self._config.crispy_exe),
            "-iwad",
            str(self._config.iwad),
            "-window",
            "-width",
            str(self._config.viewport_width),
            "-height",
            str(self._config.viewport_height),
        ]


def _windows_graceful_close(pid: int) -> None:
    """Request cooperative native closure on Windows and remain a no-op elsewhere."""
    if sys.platform != "win32":
        return
    # Keep ctypes isolated in the adapter and import it only for desktop use.
    from pewpew.windows import request_close_windows

    request_close_windows(pid)
