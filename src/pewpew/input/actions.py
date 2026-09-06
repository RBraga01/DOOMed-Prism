"""Normalized game actions and the router that turns held state into IPC frames."""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass

from pewpew.ipc.protocol import Message

MAGNITUDE_STEPS = 20
TURN_MAX_MOUSE_DELTA = 40


class Action(enum.IntEnum):
    MOVE_FORWARD = 1
    MOVE_BACKWARD = 2
    TURN_LEFT = 3
    TURN_RIGHT = 4
    FIRE = 10
    USE = 11
    PAUSE = 20


_MOVE = frozenset({Action.MOVE_FORWARD, Action.MOVE_BACKWARD})
_TURN = frozenset({Action.TURN_LEFT, Action.TURN_RIGHT})


@dataclass(frozen=True)
class HeldAction:
    action: Action
    magnitude: float


def _turn_value(magnitude: float) -> int:
    return max(0, min(TURN_MAX_MOUSE_DELTA, round(magnitude * TURN_MAX_MOUSE_DELTA)))


class ActionRouter:
    def __init__(self, sink: Callable[[Message], None]) -> None:
        self._sink = sink
        self._held: dict[Action, int] = {}  # action -> 1 while held (MOVE and TURN)

    def set_held(self, held: frozenset[HeldAction]) -> None:
        incoming = {h.action: h.magnitude for h in held}
        for action in sorted(self._held):
            if action not in incoming:
                self._emit_zero(action)
                del self._held[action]
        for action in sorted(incoming):
            magnitude = incoming[action]
            if action in _MOVE:
                # On/off: one 10000 on the transition to held, one 0 on release.
                if action not in self._held:
                    self._held[action] = 1
                    self._sink(Message.action(int(action), 10000))
            elif action in _TURN:
                # TURN is a one-shot ev_mouse delta the C side zeroes every tic,
                # so a sustained turn needs a fresh frame on *every* call while
                # the gaze is held (spec R6). Release still emits exactly one 0.
                self._held[action] = 1
                self._sink(Message.turn(int(action), _turn_value(magnitude)))

    def pulse(self, action: Action) -> None:
        self._sink(Message.pulse(int(action)))

    def discrete(self, action: Action) -> None:
        self._sink(Message.discrete(int(action)))

    def release_all(self) -> None:
        for action in sorted(self._held):
            self._emit_zero(action)
        self._held.clear()

    def _emit_zero(self, action: Action) -> None:
        if action in _MOVE:
            self._sink(Message.action(int(action), 0))
        else:
            self._sink(Message.turn(int(action), 0))
