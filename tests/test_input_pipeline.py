"""Tests for the InputPipeline integration unit."""

from __future__ import annotations

import pytest

from fakes.fake_fire import FakeSpokenFireSource
from fakes.fake_input import FakeInputSource
from pewpew.input.pipeline import InputPipeline
from pewpew.input.source import InputSample
from pewpew.ipc.protocol import Message, MessageType


def _pipe(samples, *, spoken_fire=None):
    src = FakeInputSource(list(samples))
    sent: list[Message] = []
    return InputPipeline(src, sent.append, spoken_fire=spoken_fire), sent


def test_gaze_in_the_right_band_emits_a_turn_frame_after_dwell() -> None:
    far_right = InputSample((639, 320), False, False, False)
    pipe, sent = _pipe([far_right] * 40)
    for i in range(40):
        pipe.tick(now=i * 0.05)  # 2 s of ticks — the 0.15 s dwell is satisfied by tick 3
    turns = [m for m in sent if m.type is MessageType.TURN and m.value > 0]
    assert turns and turns[0].code == 4  # TURN_RIGHT, non-zero value


def test_activation_edge_produces_a_fire_pulse() -> None:
    pipe, sent = _pipe([InputSample((320, 320), True, False, False)])
    pipe.tick(now=0.0)
    assert Message.pulse(10) in sent


def test_debug_fire_edge_produces_a_fire_pulse() -> None:
    pipe, sent = _pipe([InputSample((320, 320), False, False, True)])
    pipe.tick(now=0.0)
    assert Message.pulse(10) in sent


def test_spoken_fire_source_produces_a_fire_pulse() -> None:
    spoken = FakeSpokenFireSource()
    pipe, sent = _pipe([InputSample((320, 320), False, False, False)], spoken_fire=spoken)
    spoken.trigger()
    pipe.tick(now=0.0)
    assert Message.pulse(10) in sent


def test_pause_edge_toggles_paused_and_sends_one_discrete() -> None:
    pipe, sent = _pipe([InputSample((320, 320), False, True, False)])
    assert pipe.paused is False
    pipe.tick(now=0.0)
    assert pipe.paused is True
    assert sent.count(Message.discrete(20)) == 1


def test_release_all_emits_zeros_and_clears_paused() -> None:
    hold = InputSample((639, 320), False, False, False)
    pipe, sent = _pipe([hold] * 10)
    for i in range(10):
        pipe.tick(now=i * 0.05)
    pipe.toggle_pause()
    sent.clear()
    pipe.release_all()
    assert pipe.paused is False
    assert sent and all(
        m.value == 0 for m in sent if m.type in (MessageType.TURN, MessageType.ACTION)
    )


def test_a_raising_send_does_not_propagate_out_of_tick() -> None:
    calls = {"n": 0}

    def flaky_send(_message):
        calls["n"] += 1
        if calls["n"] > 2:
            raise ConnectionError("peer gone")

    src = FakeInputSource([InputSample((639, 320), True, False, False)] * 6)
    pipe = InputPipeline(src, flaky_send)
    for i in range(6):
        pipe.tick(now=i * 0.05)  # must not raise
