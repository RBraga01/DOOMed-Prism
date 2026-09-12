"""Tests for the radial gaze stick and the dual-rate vector filter (R14)."""

from __future__ import annotations

from math import hypot

from pewpew.input.actions import Action, HeldAction
from pewpew.input.gaze import (
    DEAD_ZONE_RADIUS,
    EMA_ZERO_EPSILON,
    GazeStick,
    GazeVectorFilter,
)


def _stick(w: int = 640, h: int = 480) -> GazeStick:
    return GazeStick(w, h)  # centre (320, 240); dead 0.28, outer 0.95, exp 1.5


def _actions(s) -> set[Action]:
    return {h.action for h in s}


# ---- GazeStick geometry ----

def test_dead_zone_circle_interior_resolves_to_zero() -> None:
    s = _stick()
    assert s.resolve(320, 240) == (0.0, 0.0)
    # 0.2 of the half-height up from centre: inside the 0.28 circle.
    assert s.resolve(320, 240 - int(0.2 * 240)) == (0.0, 0.0)


def test_just_outside_the_dead_zone_is_a_small_vector_growing_to_full() -> None:
    s = _stick()
    near = s.resolve(320, 240 - int(0.30 * 240))   # just past the 0.28 ring
    far = s.resolve(320, 0)                          # top edge — past saturation
    assert 0.0 < hypot(*near) < hypot(*far)
    assert abs(hypot(*far) - 1.0) < 1e-6            # saturates at magnitude 1.0


def test_magnitude_is_monotonic_along_a_radius() -> None:
    s = _stick()
    mags = [hypot(*s.resolve(320, 240 - dy)) for dy in range(0, 241, 12)]
    assert mags == sorted(mags)


def test_direction_matches_the_gaze_offset() -> None:
    s = _stick()
    fx, fy = s.resolve(320 + 100, 240 - 60)   # right and up
    assert fx > 0 and fy < 0
    # unit direction preserved: fx/fy ratio matches the normalized offset ratio
    nx, ny = 100 / 320.0, -60 / 240.0
    assert abs(fx / fy - nx / ny) < 1e-6


def test_a_corner_gaze_does_not_over_drive_both_axes() -> None:
    """hypot(nx, ny) > 1 in the corner triangles; the vector magnitude must
    still be s (<= 1), not ~sqrt(2)*s — the unclamped-norm reconstruction."""
    s = _stick()
    fx, fy = s.resolve(639, 0)                 # extreme corner
    assert hypot(fx, fy) <= 1.0 + 1e-9
    assert abs(fx) < 1.0 and abs(fy) < 1.0     # neither axis pinned at s


def test_outermost_pixel_normalizes_to_about_plus_or_minus_one() -> None:
    s = _stick(640, 480)
    _, fy_bottom = s.resolve(320, 479)
    _, fy_top = s.resolve(320, 0)
    assert fy_bottom > 0 and fy_top < 0
    assert abs(abs(fy_bottom) - 1.0) < 0.05 and abs(abs(fy_top) - 1.0) < 0.05


def test_surface_size_changes_the_classification_of_a_pixel() -> None:
    # (320, 400) on 640x480 is well into the backward band; on 640x640 it is
    # inside the dead zone (centre 320, |dy|=80, 80/320 = 0.25 < 0.28).
    assert GazeStick(640, 480).resolve(320, 400) != (0.0, 0.0)
    assert GazeStick(640, 640).resolve(320, 400) == (0.0, 0.0)


def test_constructor_rejects_a_bad_tunable() -> None:
    import pytest

    with pytest.raises(AssertionError):
        GazeStick(640, 480, outer_saturation=0.2, dead_zone_radius=0.28)
    with pytest.raises(AssertionError):
        GazeStick(640, 480, response_exponent=0.0)


# ---- GazeVectorFilter ----

def test_filter_ramps_up_at_ema_alpha_and_maps_signs() -> None:
    f = GazeVectorFilter()
    out = f.update((0.5, -0.5), now=0.0)     # right + forward
    assert _actions(out) == {Action.TURN_RIGHT, Action.MOVE_FORWARD}
    m0 = {h.action: h.magnitude for h in out}
    assert 0.0 < m0[Action.TURN_RIGHT] < 0.5      # EMA has not reached the input yet
    out2 = f.update((0.5, -0.5), now=0.0)
    m1 = {h.action: h.magnitude for h in out2}
    assert m1[Action.TURN_RIGHT] > m0[Action.TURN_RIGHT]


def test_left_and_backward_signs() -> None:
    f = GazeVectorFilter(ema_alpha=1.0)          # follow the input exactly
    out = f.update((-0.4, 0.6), now=0.0)
    assert _actions(out) == {Action.TURN_LEFT, Action.MOVE_BACKWARD}


def test_a_nearby_nonzero_dropout_barely_dents_the_output() -> None:
    # A one-frame jitter to a *nearby non-zero* vector stays on ema_alpha (0.4),
    # so the output barely moves. (A genuine (0,0) is a different case below.)
    f = GazeVectorFilter()
    for _ in range(6):
        f.update((0.0, -0.8), now=0.0)
    before = next(h.magnitude for h in f.update((0.0, -0.8), now=0.0))
    dip = next(h.magnitude for h in f.update((0.0, -0.78), now=0.0))
    assert dip > 0.9 * before


def test_a_genuine_zero_input_drops_fast_by_design() -> None:
    # (0,0) IS the look-back-to-centre signal -> release_alpha (0.8) -> ~80%/tick.
    f = GazeVectorFilter()
    for _ in range(6):
        f.update((0.0, -0.8), now=0.0)
    before = next(h.magnitude for h in f.update((0.0, -0.8), now=0.0))
    dip = next(h.magnitude for h in f.update((0.0, 0.0), now=0.0))
    assert 0.15 * before < dip < 0.30 * before   # ~0.2x, the intended fast release


def test_release_alpha_stops_a_held_turn_within_about_five_ticks() -> None:
    f = GazeVectorFilter()
    for _ in range(4):
        f.update((0.9, 0.0), now=0.0)
    n = 0
    for n in range(1, 9):
        if not f.update((0.0, 0.0), now=0.0):
            break
    assert n <= 6                                # ~3 to first quantum, ~5 to snap


def test_reset_clears_the_ema_state() -> None:
    f = GazeVectorFilter()
    for _ in range(4):
        f.update((0.9, -0.9), now=0.0)
    f.reset()
    assert f.update((0.0, 0.0), now=0.0) == frozenset()   # no residual tail


def test_output_snaps_to_empty_below_the_epsilon() -> None:
    f = GazeVectorFilter()
    f.update((EMA_ZERO_EPSILON * 0.4, 0.0), now=0.0)
    assert f.update((0.0, 0.0), now=0.0) == frozenset()


# ---- finding 2: a diagonal sweep must not stutter forward ----

def test_forward_never_cuts_out_on_a_diagonal_sweep() -> None:
    s = _stick()
    f = GazeVectorFilter()
    cx, cy, k = 320, 240, 150
    pts = [
        (round(cx + (i / 30.0) * k), round(cy - (1.0 - i / 30.0) * k))
        for i in range(31)
    ]  # pure forward -> pure right, through the old zone boundary
    mags: list[float] = []
    for (x, y) in pts:
        out = f.update(s.resolve(x, y), now=0.0)
        fwd = [h.magnitude for h in out if h.action is Action.MOVE_FORWARD]
        mags.append(fwd[0] if fwd else 0.0)
    # No interior zero: everything before the LAST non-zero sample is non-zero.
    last_nz = max(i for i, m in enumerate(mags) if m > 0.0)
    assert last_nz >= 20
    assert all(m > 0.0 for m in mags[:last_nz]), "forward cut out mid-sweep"
    # No abrupt collapse: the natural per-tick EMA falloff is ~0.15 of raw
    # magnitude; a real stutter/cut is a near-full drop. 0.25 cleanly separates.
    for a, b in zip(mags[:last_nz], mags[1 : last_nz + 1]):
        assert b >= a - 0.25, f"forward stuttered {a:.3f} -> {b:.3f}"
