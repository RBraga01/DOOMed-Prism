"""Tests for the debounced, dual-source fire arbiter."""

from __future__ import annotations

from fakes.fake_fire import FakeSpokenFireSource
from pewpew.input.fire import FireArbiter, NullSpokenFireSource


def test_single_edge_fires_once() -> None:
    a = FireArbiter(debounce_s=0.12)
    a.deliberate_action()
    assert a.poll(now=0.0) is True
    assert a.poll(now=0.01) is False


def test_two_edges_inside_the_window_fire_once() -> None:
    a = FireArbiter(debounce_s=0.12)
    a.deliberate_action()
    a.spoken_fire()
    assert a.poll(now=0.0) is True
    assert a.poll(now=0.05) is False


def test_edges_a_debounce_apart_fire_twice() -> None:
    a = FireArbiter(debounce_s=0.12)
    a.deliberate_action()
    assert a.poll(now=0.0) is True
    a.deliberate_action()
    assert a.poll(now=0.13) is True


def test_three_edges_at_0_005_020_fire_twice() -> None:
    a = FireArbiter(debounce_s=0.12)
    a.deliberate_action()
    assert a.poll(now=0.00) is True
    a.deliberate_action()             # inside the window
    assert a.poll(now=0.05) is False  # discarded, not queued
    a.deliberate_action()
    assert a.poll(now=0.20) is True


def test_deliberate_and_fake_spoken_edge_fuse_to_one_shot() -> None:
    a = FireArbiter(debounce_s=0.12)
    spoken = FakeSpokenFireSource()
    a.deliberate_action()
    spoken.trigger()
    if spoken.spoken_fire_edge():
        a.spoken_fire()
    assert a.poll(now=0.0) is True
    assert a.poll(now=0.05) is False


def test_reset_drops_pending_edges() -> None:
    a = FireArbiter(debounce_s=0.12)
    a.deliberate_action()
    a.reset()
    assert a.poll(now=0.0) is False


def test_null_spoken_source_never_fires() -> None:
    assert NullSpokenFireSource().spoken_fire_edge() is False
