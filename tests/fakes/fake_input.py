"""A scripted InputSource for pipeline tests."""

from __future__ import annotations

from pewpew.input.source import InputSample

_EMPTY = InputSample(
    gaze_xy=None, activation_edge=False, pause_edge=False, debug_fire_edge=False
)


class _FakeWidget:
    def __init__(self, w: int, h: int) -> None:
        self._w, self._h = w, h

    def width(self) -> int:
        return self._w

    def height(self) -> int:
        return self._h


class FakeInputSource:
    def __init__(self, queue: list[InputSample], *, widget_size=(640, 480)) -> None:
        self.queue = queue
        self.widget = _FakeWidget(*widget_size)

    def sample(self, now: float) -> InputSample:
        return self.queue.pop(0) if self.queue else _EMPTY
