"""A scripted InputSource for pipeline tests."""

from __future__ import annotations

from pewpew.input.source import InputSample

_EMPTY = InputSample(
    gaze_xy=None, activation_edge=False, pause_edge=False, debug_fire_edge=False
)


class FakeInputSource:
    def __init__(self, queue: list[InputSample]) -> None:
        self.queue = queue

    def sample(self, now: float) -> InputSample:
        return self.queue.pop(0) if self.queue else _EMPTY
