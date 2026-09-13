"""Tests for the normalized action model and the IPC-emitting router (R14)."""

from __future__ import annotations

from pewpew.input.actions import (
    MAGNITUDE_STEPS,
    MOVE_MAGNITUDE_SCALE,
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


def test_move_magnitude_scale_matches_the_spec() -> None:
    assert MOVE_MAGNITUDE_SCALE == 10000


def _router():
    sent: list[Message] = []
    return ActionRouter(sent.append), sent


def _q(magnitude: float) -> float:
    m = 0.0 if magnitude < 0.0 else 1.0 if magnitude > 1.0 else magnitude
    return round(m * MAGNITUDE_STEPS) / MAGNITUDE_STEPS


def test_quantiser_pins_the_mid_grid_and_round_up_cases_with_literals() -> None:
    router, sent = _router()
    router.set_held(frozenset({HeldAction(Action.MOVE_FORWARD, 0.75), HeldAction(Action.TURN_RIGHT, 0.99)}))
    vals = {(m.type, m.code): m.value for m in sent}
    assert vals[(MessageType.ACTION, Action.MOVE_FORWARD)] == 7500   # 0.75 -> 15/20 -> 7500
    assert vals[(MessageType.TURN, Action.TURN_RIGHT)] == 160        # 0.99 -> round(19.8)=20/20=1.0 -> min(160, 160) (rounds UP to full)


def test_turn_axis_quantiser_is_discriminating() -> None:
    # These magnitudes are fixed points of NEITHER quantiser path, so they only
    # pass while _turn_value still applies the shared _quantise on the TURN axis.
    router, sent = _router()
    router.set_held(frozenset({HeldAction(Action.TURN_RIGHT, 0.5626)}))
    # _quantise(0.5626) = round(11.252)/20 = 0.55 -> min(round(0.55*160)=88, 160) = 88.
    # The un-quantised round(0.5626 * 160) = round(90.02) = 90, so == 88 pins it.
    assert sent == [Message.turn(Action.TURN_RIGHT, 88)]

    router, sent = _router()  # fresh: TURN_LEFT is newly held, not in _held
    router.set_held(frozenset({HeldAction(Action.TURN_LEFT, 0.0126)}))
    # _quantise(0.0126) = round(0.252)/20 = 0.0 -> wire 0 -> set_held stays silent.
    # The un-quantised round(0.0126 * 160) = round(2.016) = 2 would emit turn(3, 2).
    assert sent == []


def test_move_emits_an_analog_frame_every_call_while_held_then_one_zero() -> None:
    router, sent = _router()
    for mag in (1.0, 0.75, 0.5):
        router.set_held(frozenset({HeldAction(Action.MOVE_FORWARD, mag)}))
    router.set_held(frozenset())  # release
    assert sent == [
        Message.action(Action.MOVE_FORWARD, round(_q(1.0) * MOVE_MAGNITUDE_SCALE)),
        Message.action(Action.MOVE_FORWARD, round(_q(0.75) * MOVE_MAGNITUDE_SCALE)),
        Message.action(Action.MOVE_FORWARD, round(_q(0.5) * MOVE_MAGNITUDE_SCALE)),
        Message.action(Action.MOVE_FORWARD, 0),
    ]
    assert [m.value for m in sent].count(0) == 1


def test_turn_emits_a_frame_every_call_while_held_then_one_zero() -> None:
    router, sent = _router()
    for mag in (1.0, 0.99, 0.5):
        router.set_held(frozenset({HeldAction(Action.TURN_RIGHT, mag)}))
    router.set_held(frozenset())
    assert sent == [
        Message.turn(Action.TURN_RIGHT, min(round(_q(1.0) * TURN_MAX_MOUSE_DELTA), TURN_MAX_MOUSE_DELTA)),
        Message.turn(Action.TURN_RIGHT, min(round(_q(0.99) * TURN_MAX_MOUSE_DELTA), TURN_MAX_MOUSE_DELTA)),
        Message.turn(Action.TURN_RIGHT, min(round(_q(0.5) * TURN_MAX_MOUSE_DELTA), TURN_MAX_MOUSE_DELTA)),
        Message.turn(Action.TURN_RIGHT, 0),
    ]


def test_full_deflection_maps_to_the_scale_maxima() -> None:
    router, sent = _router()
    router.set_held(
        frozenset({HeldAction(Action.MOVE_FORWARD, 1.0), HeldAction(Action.TURN_LEFT, 1.0)})
    )
    values = {(m.type, m.code): m.value for m in sent}
    assert values[(MessageType.ACTION, Action.MOVE_FORWARD)] == 10000
    assert values[(MessageType.TURN, Action.TURN_LEFT)] == TURN_MAX_MOUSE_DELTA


def test_a_sub_quantum_hold_emits_nothing_then_one_zero_only_after_a_real_value() -> None:
    router, sent = _router()
    tiny = 0.4 / MAGNITUDE_STEPS  # quantises to 0
    router.set_held(frozenset({HeldAction(Action.MOVE_FORWARD, tiny)}))
    assert sent == []  # never engaged -> silent
    router.set_held(frozenset({HeldAction(Action.MOVE_FORWARD, 1.0)}))  # now a real value
    router.set_held(frozenset({HeldAction(Action.MOVE_FORWARD, tiny)}))  # falls back below the quantum
    router.set_held(frozenset())
    assert [m.value for m in sent] == [10000, 0]  # one real, one fall — no second 0 on release


def test_over_range_magnitude_is_clamped() -> None:
    router, sent = _router()
    router.set_held(frozenset({HeldAction(Action.TURN_RIGHT, 3.0)}))
    assert sent == [Message.turn(Action.TURN_RIGHT, TURN_MAX_MOUSE_DELTA)]


def test_pulse_and_discrete_emit_one_frame_each() -> None:
    router, sent = _router()
    router.pulse(Action.FIRE)
    router.discrete(Action.PAUSE)
    assert sent == [Message.pulse(Action.FIRE), Message.discrete(Action.PAUSE)]


def test_release_all_zeros_every_outstanding_axis_and_is_a_noop_when_clear() -> None:
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
