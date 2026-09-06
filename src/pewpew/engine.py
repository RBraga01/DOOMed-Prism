"""Supervision for an externally installed Crispy Doom process."""

from __future__ import annotations

import os
import secrets
import shlex
import subprocess
import sys
from collections.abc import Callable, Mapping
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


PopenFactory = Callable[[list[str], Mapping[str, str]], _Process]
GracefulClose = Callable[[int], None]


def _spawn(args: list[str], env: Mapping[str, str]) -> _Process:
    return subprocess.Popen(args, env=env)


class DoomProcess:
    """Launch and stop one windowed Crispy Doom child at a time."""

    def __init__(
        self,
        config: RuntimeConfig,
        popen_factory: PopenFactory = _spawn,
        graceful_close: GracefulClose | None = None,
    ) -> None:
        self._config = config
        self._popen_factory = popen_factory
        self._graceful_close = (
            graceful_close if graceful_close is not None else _windows_graceful_close
        )
        self._process: _Process | None = None
        self._frame_segment_name: str | None = None
        self._ipc_address: str | None = None

    def __enter__(self) -> DoomProcess:
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    def start(self, *, ipc_address: str | None = None) -> int:
        """Launch the configured Crispy Doom executable and return its PID."""
        if self.poll() is None and self._process is not None:
            raise EngineAlreadyRunning("Crispy Doom is already running")
        name = f"doomed-prism-fb-{os.getpid()}-{secrets.token_hex(4)}"
        child_env = {**os.environ, "DOOMED_PRISM_FB_NAME": name}
        if ipc_address:
            child_env["DOOMED_PRISM_IPC_ADDR"] = ipc_address
            self._ipc_address = ipc_address
        self._process = self._popen_factory(self._command(), child_env)
        self._frame_segment_name = name
        return self._process.pid

    def poll(self) -> int | None:
        """Return the child return code, or ``None`` while it is still running."""
        if self._process is None:
            return None
        return self._process.poll()

    @property
    def frame_segment_name(self) -> str | None:
        return self._frame_segment_name

    @property
    def ipc_address(self) -> str | None:
        return self._ipc_address

    def stop(self, timeout_s: float = 3.0) -> None:
        """Stop the live child gracefully, escalating only after a timeout."""
        process = self._process
        if process is None:
            return
        if process.poll() is not None:
            self._process = None
            self._release_segment()
            return

        try:
            self._graceful_close(process.pid)
        except Exception:
            pass
        else:
            try:
                process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                pass
            else:
                self._process = None
                self._release_segment()
                return

        process.terminate()
        try:
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            raise
        self._process = None
        self._release_segment()

    def _command(self) -> list[str]:
        command = [
            str(self._config.crispy_exe),
            "-iwad",
            str(self._config.iwad),
            "-window",
            "-width",
            str(self._config.viewport_width),
            "-height",
            str(self._config.viewport_height),
        ]
        warp = os.environ.get("DOOMED_PRISM_WARP")
        if warp:
            command += ["-warp", *shlex.split(warp), "-skill",
                        os.environ.get("DOOMED_PRISM_SKILL", "3")]
        return command

    def _release_segment(self) -> None:
        name = self._frame_segment_name
        self._frame_segment_name = None
        if not name or sys.platform == "win32":
            return
        try:
            os.unlink(f"/dev/shm/{name}")
        except OSError:
            pass


def _windows_graceful_close(pid: int) -> None:
    """Request cooperative native closure on Windows and remain a no-op elsewhere."""
    if sys.platform != "win32":
        return
    # Keep ctypes isolated in the adapter and import it only for desktop use.
    from pewpew.win_close import request_close_windows

    request_close_windows(pid)
