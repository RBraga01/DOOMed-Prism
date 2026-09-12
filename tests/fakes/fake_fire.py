"""A manually triggered SpokenFireSource for fusion tests."""

from __future__ import annotations


class FakeSpokenFireSource:
    def __init__(self) -> None:
        self._pending = False

    def trigger(self) -> None:
        self._pending = True

    def spoken_fire_edge(self) -> bool:
        fired, self._pending = self._pending, False
        return fired
