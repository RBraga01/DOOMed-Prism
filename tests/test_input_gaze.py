"""Tests for gaze-zone resolution and the dwell / jitter filter."""

from __future__ import annotations

from pewpew.input.actions import Action, HeldAction
from pewpew.input.gaze import GazeFilter, GazeZoneMap


def _map() -> GazeZoneMap:
    return GazeZoneMap(640, 640)  # centre (320, 320); hw=180, hh=150


def _actions(s: frozenset[HeldAction]) -> set[Action]:
    return {h.action for h in s}


def test_dead_zone_centre_resolves_to_nothing() -> None:
    assert _map().resolve(320, 320) == frozenset()


def test_right_turn_band_grows_monotonically_toward_the_edge() -> None:
    gmap = _map()
    near = next(iter(gmap.resolve(320 + 181, 320)))
    far = next(iter(gmap.resolve(639, 320)))
    assert near.action is Action.TURN_RIGHT and far.action is Action.TURN_RIGHT
    assert 0.0 <= near.magnitude < far.magnitude <= 1.0


def test_upper_band_is_move_forward_lower_is_move_backward() -> None:
    gmap = _map()
    assert _actions(gmap.resolve(320, 320 - 200)) == {Action.MOVE_FORWARD}
    assert _actions(gmap.resolve(320, 320 + 200)) == {Action.MOVE_BACKWARD}


def test_upper_right_corner_is_forward_plus_right_turn() -> None:
    assert _actions(_map().resolve(320 + 200, 320 - 200)) == {
        Action.MOVE_FORWARD,
        Action.TURN_RIGHT,
    }


def test_filter_requires_dwell_before_emitting() -> None:
    f = GazeFilter(dwell_s=0.15, grace_s=0.02)
    raw = frozenset({HeldAction(Action.TURN_LEFT, 1.0)})
    assert f.update(raw, now=0.0) == frozenset()
    assert f.update(raw, now=0.10) == frozenset()
    assert _actions(f.update(raw, now=0.16)) == {Action.TURN_LEFT}


def test_filter_rides_out_a_one_sample_dropout_but_releases_after_grace() -> None:
    f = GazeFilter(dwell_s=0.15, grace_s=0.02)
    raw = frozenset({HeldAction(Action.MOVE_FORWARD, 1.0)})
    f.update(raw, now=0.0)
    f.update(raw, now=0.20)  # now held
    assert _actions(f.update(frozenset(), now=0.205)) == {Action.MOVE_FORWARD}
    assert f.update(frozenset(), now=0.25) == frozenset()


def test_a_brief_dropout_and_return_does_not_re_require_full_dwell() -> None:
    f = GazeFilter(dwell_s=0.15, grace_s=0.05)
    raw = frozenset({HeldAction(Action.TURN_LEFT, 1.0)})
    f.update(raw, now=0.0)
    f.update(raw, now=0.20)          # held
    f.update(frozenset(), now=0.22)  # 20 ms dropout, within grace
    assert _actions(f.update(raw, now=0.24)) == {Action.TURN_LEFT}  # still held


def test_region_change_releases_the_outgoing_action_immediately() -> None:
    f = GazeFilter(dwell_s=0.0, grace_s=1.0)
    f.update(frozenset({HeldAction(Action.TURN_LEFT, 1.0)}), now=0.0)
    got = f.update(frozenset({HeldAction(Action.TURN_RIGHT, 1.0)}), now=0.01)
    assert _actions(got) == {Action.TURN_RIGHT}


def test_turn_magnitude_is_ema_smoothed() -> None:
    f = GazeFilter(dwell_s=0.0, grace_s=1.0, ema_alpha=0.5)
    m0 = next(iter(f.update(frozenset({HeldAction(Action.TURN_RIGHT, 1.0)}), now=0.0)))
    m1 = next(iter(f.update(frozenset({HeldAction(Action.TURN_RIGHT, 0.0)}), now=0.01)))
    assert m0.magnitude == 1.0
    assert 0.0 < m1.magnitude < 1.0
