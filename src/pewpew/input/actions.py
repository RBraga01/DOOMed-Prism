"""Normalized game actions and the router that turns held state into IPC frames."""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass

from pewpew.ipc.protocol import Message

MAGNITUDE_STEPS = 20
# Raised 40 -> 160 across the 2026-09-08 gate: R14's per-drain TURN coalescing
# removed a ~1.8x accumulation the pre-R14 per-frame ev_mouse apply had implied,
# and at 40/72 a full-deflection gaze turn (data2*8 angleturn/tic) sat below
# DOOM's own walk-turn keyboard value (640). 160 -> 1280/tic == DOOM's run-turn
# at full deflection. Kept in lockstep with the C `IPC_TURN_CLAMP`. R11 gate-tunable.
TURN_MAX_MOUSE_DELTA = 160
MOVE_MAGNITUDE_SCALE = 10000


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


def _quantise(magnitude: float) -> float:
    """Snap a raw magnitude to the MAGNITUDE_STEPS grid, clamped to [0, 1]."""
    clamped = 0.0 if magnitude < 0.0 else 1.0 if magnitude > 1.0 else magnitude
    return round(clamped * MAGNITUDE_STEPS) / MAGNITUDE_STEPS


def _move_value(magnitude: float) -> int:
    return round(_quantise(magnitude) * MOVE_MAGNITUDE_SCALE)


def _turn_value(magnitude: float) -> int:
    return min(
        round(_quantise(magnitude) * TURN_MAX_MOUSE_DELTA), TURN_MAX_MOUSE_DELTA
    )


class ActionRouter:
    def __init__(self, sink: Callable[[Message], None]) -> None:
        self._sink = sink
        self._held: dict[Action, int] = {}  # axis -> last non-zero wire value sent

    def set_held(self, held: frozenset[HeldAction]) -> None:
        incoming = {h.action: h.magnitude for h in held}
        for action in sorted(self._held):
            if action not in incoming:
                self._emit_zero(action)
                del self._held[action]
        for action in sorted(incoming):
            if action in _MOVE:
                value = _move_value(incoming[action])
            elif action in _TURN:
                value = _turn_value(incoming[action])
            else:
                continue
            if value == 0 and action not in self._held:
                continue  # sub-quantum, never engaged — stay silent
            self._sink(self._frame(action, value))
            if value == 0:
                del self._held[action]
            else:
                self._held[action] = value

    def pulse(self, action: Action) -> None:
        self._sink(Message.pulse(int(action)))

    def discrete(self, action: Action) -> None:
        self._sink(Message.discrete(int(action)))

    def release_all(self) -> None:
        for action in sorted(self._held):
            self._emit_zero(action)
        self._held.clear()

    @staticmethod
    def _frame(action: Action, value: int) -> Message:
        if action in _MOVE:
            return Message.action(int(action), value)
        return Message.turn(int(action), value)

    def _emit_zero(self, action: Action) -> None:
        self._sink(self._frame(action, 0))
