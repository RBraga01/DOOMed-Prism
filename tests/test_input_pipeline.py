"""Tests for the InputPipeline integration unit (R14)."""

from __future__ import annotations

from fakes.fake_fire import FakeSpokenFireSource
from fakes.fake_input import FakeInputSource
from pewpew.input.pipeline import InputPipeline
from pewpew.input.source import InputSample
from pewpew.ipc.protocol import Message, MessageType


def _pipe(samples, *, spoken_fire=None, surface=None):
    src = FakeInputSource(list(samples))
    sent: list[Message] = []
    return (
        InputPipeline(src, sent.append, spoken_fire=spoken_fire, surface=surface),
        sent,
    )


def _values(sent, msg_type, code):
    return [m.value for m in sent if m.type is msg_type and m.code == code]


def test_pipeline_builds_the_stick_on_the_source_widget_when_surface_is_none() -> None:
    pipe, _ = _pipe([InputSample((320, 240), False, False, False)])
    assert (pipe._stick._cx, pipe._stick._cy) == (320, 240)  # 640x480 widget


def test_finding_1_backward_is_reachable_and_symmetric_with_forward() -> None:
    # No explicit surface -> 640x480. y=1 is far forward, y=478 is far backward.
    fwd, sent_f = _pipe([InputSample((320, 1), False, False, False)] * 8)
    for i in range(8):
        fwd.tick(now=i)
    bwd, sent_b = _pipe([InputSample((320, 478), False, False, False)] * 8)
    for i in range(8):
        bwd.tick(now=i)
    f_vals = _values(sent_f, MessageType.ACTION, 1)  # MOVE_FORWARD
    b_vals = _values(sent_b, MessageType.ACTION, 2)  # MOVE_BACKWARD
    assert f_vals and b_vals
    assert abs(f_vals[-1] - b_vals[-1]) <= 10000 // 20  # within one quantum


def test_finding_2_forward_does_not_drop_to_zero_across_a_diagonal_sweep() -> None:
    cx, cy, k = 320, 240, 150
    track = [
        InputSample(
            (round(cx + (i / 30.0) * k), round(cy - (1.0 - i / 30.0) * k)),
            False, False, False,
        )
        for i in range(31)
    ]
    pipe, sent = _pipe(track)
    for i in range(31):
        pipe.tick(now=i)
    fwd = _values(sent, MessageType.ACTION, 1)
    last_nz = max(i for i, v in enumerate(fwd) if v > 0)
    assert last_nz >= 18
    assert all(v > 0 for v in fwd[:last_nz]), "MOVE_FORWARD hit 0 mid-sweep"
    # natural EMA falloff is ~1500 wire units/tick; a cut is a near-full drop.
    for a, b in zip(fwd[:last_nz], fwd[1 : last_nz + 1]):
        assert b >= a - 2500, f"MOVE_FORWARD stuttered {a} -> {b}"


def test_finding_3_forward_and_turn_scale_together_with_eccentricity() -> None:
    # +y drives MOVE_FORWARD, +x drives TURN_RIGHT. Compare at matching
    # NORMALIZED eccentricity (nx == ny), since the half-extents differ
    # (320 vs 240): forward's wire curve must track turn's -> as proportional.
    fwd_vals, turn_vals = [], []
    for frac in (0.35, 0.5, 0.7, 0.9, 1.0):  # all past the 0.28 dead zone
        dx, dy = round(frac * 320), round(frac * 240)
        pf, sf = _pipe([InputSample((320, 240 - dy), False, False, False)] * 12)
        pt, st = _pipe([InputSample((320 + dx, 240), False, False, False)] * 12)
        for i in range(12):
            pf.tick(now=i)
            pt.tick(now=i)
        f = _values(sf, MessageType.ACTION, 1)
        t = _values(st, MessageType.TURN, 4)
        assert f and t, f"no frame at frac {frac}"
        fwd_vals.append(f[-1])
        turn_vals.append(t[-1])
    assert fwd_vals == sorted(fwd_vals) and turn_vals == sorted(turn_vals)
    assert fwd_vals[-1] == 10000 and turn_vals[-1] == 40  # both saturate
    for f, t in zip(fwd_vals, turn_vals):
        assert abs(f / 10000 - t / 40) <= 1 / 20   # normalized curves agree within a quantum


def test_activation_edge_produces_a_fire_pulse() -> None:
    pipe, sent = _pipe([InputSample((320, 240), True, False, False)])
    pipe.tick(now=0.0)
    assert Message.pulse(10) in sent


def test_debug_fire_edge_produces_a_fire_pulse() -> None:
    pipe, sent = _pipe([InputSample((320, 240), False, False, True)])
    pipe.tick(now=0.0)
    assert Message.pulse(10) in sent


def test_spoken_fire_source_produces_a_fire_pulse() -> None:
    spoken = FakeSpokenFireSource()
    pipe, sent = _pipe([InputSample((320, 240), False, False, False)], spoken_fire=spoken)
    spoken.trigger()
    pipe.tick(now=0.0)
    assert Message.pulse(10) in sent


def test_pause_edge_toggles_paused_and_sends_one_discrete() -> None:
    pipe, sent = _pipe([InputSample((320, 240), False, True, False)])
    assert pipe.paused is False
    pipe.tick(now=0.0)
    assert pipe.paused is True
    assert sent.count(Message.discrete(20)) == 1


def test_release_all_resets_the_filter_emits_one_zero_per_axis_and_clears_paused() -> None:
    hold = InputSample((639, 478), False, False, False)  # diagonal: both axes held
    pipe, sent = _pipe([hold] * 10)
    for i in range(10):
        pipe.tick(now=i)
    pipe.toggle_pause()
    sent.clear()
    pipe.release_all()
    assert pipe.paused is False
    assert _values(sent, MessageType.ACTION, 2) == [0]  # MOVE_BACKWARD: exactly one 0
    assert _values(sent, MessageType.TURN, 4) == [0]    # TURN_RIGHT: exactly one 0
    # filter reset: the very next dead-zone tick emits nothing new
    sent.clear()
    pipe._source.queue.append(InputSample((320, 240), False, False, False))
    pipe.tick(now=99)
    assert sent == []


def test_a_raising_send_does_not_propagate_out_of_tick() -> None:
    calls = {"n": 0}

    def flaky_send(_message):
        calls["n"] += 1
        if calls["n"] > 2:
            raise ConnectionError("peer gone")

    src = FakeInputSource([InputSample((639, 240), True, False, False)] * 6)
    pipe = InputPipeline(src, flaky_send)
    for i in range(6):
        pipe.tick(now=i)  # must not raise
    assert calls["n"] > 2
