"""Fuse a deliberate action and a spoken 'pew pew' into one debounced FIRE."""

from __future__ import annotations

from typing import Protocol

FIRE_DEBOUNCE_S = 0.12


class DeliberateActionSource(Protocol):
    def activation_edge(self) -> bool: ...


class SpokenFireSource(Protocol):
    def spoken_fire_edge(self) -> bool: ...


class NullSpokenFireSource:
    def spoken_fire_edge(self) -> bool:
        return False


class FireArbiter:
    def __init__(self, *, debounce_s: float = FIRE_DEBOUNCE_S) -> None:
        self._debounce_s = debounce_s
        self._pending = False
        self._last_shot: float | None = None

    def deliberate_action(self) -> None:
        self._pending = True

    def spoken_fire(self) -> None:
        self._pending = True

    def poll(self, now: float) -> bool:
        if not self._pending:
            return False
        if self._last_shot is not None and now - self._last_shot < self._debounce_s:
            self._pending = False  # discard, not queued
            return False
        self._pending = False
        self._last_shot = now
        return True

    def reset(self) -> None:
        self._pending = False
        self._last_shot = None
