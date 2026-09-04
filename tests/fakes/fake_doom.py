"""Controlled stand-in for a Crispy Doom child process."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence


class FakePopen:
    """A process double that records lifecycle effects without launching Doom."""

    next_pid = 4100

    def __init__(self, arguments: Sequence[str]) -> None:
        self.arguments = list(arguments)
        self.pid = type(self).next_pid
        type(self).next_pid += 1
        self.returncode: int | None = None
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_timeouts: list[float | None] = []
        self.wait_timeouts_remaining = 0
        self.terminate_exits = True

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        if self.returncode is None and self.terminate_exits:
            self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        if self.wait_timeouts_remaining and self.returncode is None:
            self.wait_timeouts_remaining -= 1
            raise subprocess.TimeoutExpired(self.arguments, timeout)
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9


class FakePopenFactory:
    """Factory that supplies fakes and records every process launch."""

    def __init__(self) -> None:
        self.processes: list[FakePopen] = []

    def __call__(self, arguments: Sequence[str]) -> FakePopen:
        process = FakePopen(arguments)
        self.processes.append(process)
        return process
