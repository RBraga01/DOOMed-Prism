"""Tests for the normalized action model and the IPC-emitting router."""

from __future__ import annotations

from pewpew.input.actions import (
    TURN_MAX_MOUSE_DELTA,
    Action,
    ActionRouter,
    HeldAction,
)
from pewpew.ipc.protocol import Message, MessageType


def test_action_codes_match_the_wire_table() -> None:
    assert (Action.MOVE_FORWARD, Action.MOVE_BACKWARD) == (1, 2)
    assert (Action.TURN_LEFT, Action.TURN_RIGHT) == (3, 4)
    assert (Action.FIRE, Action.USE, Action.PAUSE) == (10, 11, 20)


def _router():
    sent: list[Message] = []
    return ActionRouter(sent.append), sent


def test_set_held_emits_move_forward_on_hold_then_release() -> None:
    router, sent = _router()
    router.set_held(frozenset({HeldAction(Action.MOVE_FORWARD, 1.0)}))
    router.set_held(frozenset())
    assert sent == [
        Message.action(Action.MOVE_FORWARD, 10000),
        Message.action(Action.MOVE_FORWARD, 0),
    ]


def test_turn_emits_a_frame_every_call_while_held() -> None:
    """TURN is a one-shot mouse delta: a held gaze must re-send it every tick."""
    router, sent = _router()
    router.set_held(frozenset({HeldAction(Action.TURN_RIGHT, 1.0)}))
    # A near-identical magnitude must STILL produce a frame — not silence.
    router.set_held(frozenset({HeldAction(Action.TURN_RIGHT, 0.99)}))
    router.set_held(frozenset({HeldAction(Action.TURN_RIGHT, 0.5)}))
    router.set_held(frozenset())  # release
    assert sent == [
        Message.turn(Action.TURN_RIGHT, TURN_MAX_MOUSE_DELTA),
        Message.turn(Action.TURN_RIGHT, round(0.99 * TURN_MAX_MOUSE_DELTA)),
        Message.turn(Action.TURN_RIGHT, round(0.5 * TURN_MAX_MOUSE_DELTA)),
        Message.turn(Action.TURN_RIGHT, 0),
    ]
    # exactly one TURN frame per non-release call, then one 0 on release
    assert len([m for m in sent if m.value != 0]) == 3
    assert [m.value for m in sent].count(0) == 1


def test_move_held_across_many_calls_emits_one_hold_then_one_release() -> None:
    router, sent = _router()
    for _ in range(5):
        router.set_held(frozenset({HeldAction(Action.MOVE_FORWARD, 1.0)}))
    router.set_held(frozenset())
    assert sent == [
        Message.action(Action.MOVE_FORWARD, 10000),
        Message.action(Action.MOVE_FORWARD, 0),
    ]


def test_pulse_and_discrete_emit_one_frame_each() -> None:
    router, sent = _router()
    router.pulse(Action.FIRE)
    router.discrete(Action.PAUSE)
    assert sent == [Message.pulse(Action.FIRE), Message.discrete(Action.PAUSE)]


def test_release_all_releases_every_held_action_and_is_a_noop_when_empty() -> None:
    router, sent = _router()
    router.set_held(
        frozenset({HeldAction(Action.MOVE_FORWARD, 1.0), HeldAction(Action.TURN_LEFT, 1.0)})
    )
    sent.clear()
    router.release_all()
    kinds = {(m.type, m.code) for m in sent}
    assert (MessageType.ACTION, Action.MOVE_FORWARD) in kinds
    assert (MessageType.TURN, Action.TURN_LEFT) in kinds
    assert all(m.value == 0 for m in sent)
    sent.clear()
    router.release_all()
    assert sent == []
