# Milestone 3a — Radial Analog Stick (R14) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the discrete gaze-zone input model with a radial analog stick — proportional turn *and* forward/back from one curved gaze vector — on top of the already-shipped, CI-green Milestone 3a implementation.

**Architecture:** The gaze cursor over the viewport is one 2-D vector. `GazeStick` (pure geometry) maps a gaze pixel to a curved, saturated vector `(fx, fy)`; `GazeVectorFilter` dual-rate-EMA-smooths it and maps it to ≤ one `MOVE_*` + ≤ one `TURN_*` `HeldAction`. `ActionRouter` quantises both axes with one formula and emits a frame every tick while held. The Crispy Doom patch gains an analog `ipc_forwardmove` folded into `G_BuildTiccmd`'s local `forward` before the `±MAXPLMOVE` clamp, plus per-drain `TURN`/`ACTION` coalescing and a staleness watchdog. The wire protocol is unchanged except that `ACTION.value` becomes a proportional `[0, 10000]` magnitude.

**Tech Stack:** Python 3.14 (stdlib `math`, `socket`, `struct`), PySide6 (Qt host), C (crispy-doom-7.1 patch, MSYS2 UCRT64 gcc), pytest + pytest-qt, GitHub Actions Linux CI.

**Spec:** `docs/superpowers/specs/2026-09-05-doomed-prism-milestone-3-design.md` — ruling **R14** plus the amended §2/§3/§4/§5/§6/§7/§9/§10/§12/§13/§14/§15/§16/§17/§18. Read R14 in full and §7, §10, §15 before starting.

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from R11 / R14 / §5 / §14.

- **`pewpew.input.gaze` constants (module-level, exact defaults):** `DEAD_ZONE_RADIUS = 0.28`, `OUTER_SATURATION = 0.95`, `RESPONSE_EXPONENT = 1.5`, `MAGNITUDE_EMA_ALPHA = 0.4`, `RELEASE_EMA_ALPHA = 0.8`, `EMA_ZERO_EPSILON = 1e-3`. All fractions of normalized space except `EMA_ZERO_EPSILON` (a vector magnitude).
- **`pewpew.input.actions` constants:** `MAGNITUDE_STEPS = 20`, `MOVE_MAGNITUDE_SCALE = 10000`, `TURN_MAX_MOUSE_DELTA = 40`.
- **C `i_ipc_input.c` constants (`#define`):** `PULSE_HOLD_TICS 2`, `IPC_TURN_CLAMP 40`, `MOVE_MAX_FORWARDMOVE 50` (DOOM's run value `forwardmove[1]` = `MAXPLMOVE`), `IPC_MOVE_STALE_PUMPS 6`, `IPC_MOVE_WIRE_MAX 10000` (must `#define` equal to `MOVE_MAGNITUDE_SCALE`).
- **The one quantiser formula (both axes, in `ActionRouter`):** clamp `magnitude` to `[0.0, 1.0]`; `q = round(magnitude * MAGNITUDE_STEPS) / MAGNITUDE_STEPS`; `MOVE_*` wire `value = round(q * MOVE_MAGNITUDE_SCALE)`; `TURN_*` wire `value = min(round(q * TURN_MAX_MOUSE_DELTA), TURN_MAX_MOUSE_DELTA)`. `q == 0` emits **nothing** while an axis is newly held, and exactly one `0` frame on the fall from a previously-non-zero value or on release.
- **§5 action `code` table — UNCHANGED:** `MOVE_FORWARD=1`, `MOVE_BACKWARD=2`, `TURN_LEFT=3`, `TURN_RIGHT=4`, `FIRE=10`, `USE=11`, `PAUSE=20`. Direction stays in `code`; `ACTION.value` is now a proportional magnitude `[0, MOVE_MAGNITUDE_SCALE]` (`0` = released). `Message.action(code, value)` signature unchanged. `decode(encode(m)) == m` unaffected; `decode` does no range validation.
- **Wire frame:** fixed 8 bytes little-endian, `struct` `"<BBHi"` = `version:u8, type:u8, code:u16, value:i32`. `IPC_PROTOCOL_VERSION = 1`, `IPC_FRAME_SIZE = 8`. `MessageType`: `HELLO=0, ACTION=1, PULSE=2, DISCRETE=3, TURN=4, BYE=6` (5 reserved).
- **C patch series:** `scripts/build_crispy.py` applies `patches/crispy-doom-fb-export.diff` then `patches/crispy-doom-ipc-input.diff` cumulatively on disk after `git reset --hard 0a022e0ee6c74d9bab173ed9ee5212312e90ce3a` + `git clean -fd -- src/`. `crispy-doom.lock` pins tag `crispy-doom-7.1`, commit `0a022e0ee6c74d9bab173ed9ee5212312e90ce3a`. `--check` = restore + real `apply p1` + `apply --check p2`.
- **§14 patch-2 file allow-list:** `src/i_ipc_input.c`, `src/i_ipc_input.h`, `src/d_loop.c`, `src/i_video.c`, `src/CMakeLists.txt`, and `src/doom/g_game.c` (the R14 mechanism-1 forward fold — mechanism 1 IS chosen). Net-added-line ceiling ≤ 420. Any other file is `BLOCKED/RETRY` at the gate.
- **R14 C forward mechanism = option 1** (a bounded additive term inside `G_BuildTiccmd`). The implementer confirms it against `build/crispy/src/doom/g_game.c` and records "chosen: additive `forward` term; rejected: `ev_joystick` (scaled by `forwardmove[speed]`, overwrites `joy*move`, `use_analog`-cfg-dependent), keyboard duty-cycle (a pump call is not always a built tic)" in the patch header comment.
- **Publication safety:** no Raven source, IWADs, engine binaries, credentials, or resolved local paths enter git. `python scripts/check_publication_safety.py --root .` and `--root . --history` must exit 0. The validation docs use only the placeholders `<tempdir>/doomed-prism-ipc-<pid>-<token>.sock` and `127.0.0.1:<port>`.
- **Tests run without Raven / Crispy / an IWAD** via project fakes. `python -m pytest -q` must be fully green on the Windows dev box (6 POSIX-only skips are expected). CI (Linux) additionally runs `scripts/ci_ipc_smoke.py` against a real build.
- **Environment:** Windows 11; the project venv is `E:\Projectos\raven-agent-hud\.venv` (run `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest ...`). For the C build prepend `C:\msys64\ucrt64\bin` to `PATH` (gcc 16.2, cmake, ninja). Use **Git-for-Windows** `git` (not MSYS2's `/usr/bin/git`) for `git apply`. `build/crispy/` is a `crispy-doom-7.1` checkout.
- **Branch:** `feature/doomed-prism-m3` (already created from `main` @ `389ef4b`; the 14-task 3a implementation and the R14 spec commits are on it). Do not branch again. Commit after every GREEN step.
- **Do not touch** original-3a tasks 1, 2, 4, 7, 10 (`pewpew.ipc.protocol`, `pewpew.ipc.server`, `scripts/build_crispy.py`, `pewpew.input.fire`, `pewpew.engine`) — R14 leaves them alone.

---

## File Structure

| File | Responsibility after this plan |
| --- | --- |
| `src/pewpew/input/gaze.py` | **Rewritten.** `GazeStick` (radial geometry → `(fx, fy)`), `GazeVectorFilter` (dual-rate EMA → `frozenset[HeldAction]`, `reset()`). No zones, dwell, grace, or region rule. |
| `src/pewpew/input/actions.py` | **Modified.** `ActionRouter` emits per-tick analog `MOVE` + `TURN`; one `_quantise` formula; new `MOVE_MAGNITUDE_SCALE`. |
| `src/pewpew/input/simulator_source.py` | **Modified (small).** Public read-only `widget` property. |
| `src/pewpew/input/pipeline.py` | **Modified.** `surface=None` default (reads `source.widget` size when a test omits it; `host_widget` passes it explicitly); builds `GazeStick`/`GazeVectorFilter`; `release_all()` calls `filter.reset()`. |
| `src/pewpew/host_widget.py` | **Modified (small).** Build `InputPipeline(..., surface=(self.viewport.width(), self.viewport.height()))`. |
| `patches/crispy-doom-ipc-input.diff` | **Regenerated.** Analog `ipc_forwardmove` + scaling; per-drain `TURN`/`ACTION` coalescing; `IPC_MOVE_STALE_PUMPS` watchdog; new `#define`s; `IPC_Input_ForwardMove()` accessor; one `src/doom/g_game.c` fold hunk. |
| `scripts/ci_ipc_smoke.py` | **Modified.** Interleave an analog `MOVE` ramp + widen the `TURN` sweep; assert liveness across the ramp window. |
| `.github/workflows/ci.yml` | **Modified (text).** Step-summary line mentions the analog forward/back ramp. |
| `tests/test_input_gaze.py` | **Rewritten** for `GazeStick` / `GazeVectorFilter` + the finding-2 sweep + the corner test. |
| `tests/test_input_actions.py` | **Modified** for per-tick analog emit + the quantiser. |
| `tests/test_input_source_qt.py` | **+1 test** for the `widget` property. |
| `tests/test_input_pipeline.py`, `tests/fakes/fake_input.py` | **Modified.** `FakeInputSource` gets a fake `widget`; F1/F2/F3 pipeline guards. |
| `tests/test_host_widget_qt.py` | **+1 test** — host-layer F1 (stick centre `(320, 240)`). |
| `tests/test_distribution_metadata.py` | **Modified.** Constant-match widening + the diff file-set allow-list assertion. |
| `README.md` | **+1 line** — current status names the radial analog stick. |
| `docs/validation/milestone-3a-checklist.md`, `docs/validation/milestone-3a-result.md` | **Rewritten** geometry sections + the five decision strings. |
| `tests/test_validation_docs_m3.py` | **Modified.** Five decision strings; R14 phrases present / zone phrases absent. |

---

## Task 1: `pewpew.input.gaze` — the radial stick and the vector filter

**Files:**
- Rewrite: `src/pewpew/input/gaze.py`
- Rewrite test: `tests/test_input_gaze.py`

**Interfaces:**
- Consumes: `pewpew.input.actions.Action` (unchanged enum), `pewpew.input.actions.HeldAction` (`HeldAction(action, magnitude)`, unchanged).
- Produces:
  - `GazeStick(surface_w: int, surface_h: int, *, dead_zone_radius: float = DEAD_ZONE_RADIUS, outer_saturation: float = OUTER_SATURATION, response_exponent: float = RESPONSE_EXPONENT)` — `__init__` asserts `0.0 < dead_zone_radius < outer_saturation <= 1.0` and `response_exponent > 0.0`. Attributes `_cx`, `_cy` (ints, `surface_w // 2`, `surface_h // 2`). Method `resolve(x: int, y: int) -> tuple[float, float]` — stateless, returns `(fx, fy)` with `hypot(fx, fy) == s <= 1.0`, or `(0.0, 0.0)` inside the dead zone.
  - `GazeVectorFilter(*, ema_alpha: float = MAGNITUDE_EMA_ALPHA, release_alpha: float = RELEASE_EMA_ALPHA)` — `update(vec: tuple[float, float], now: float) -> frozenset[HeldAction]` (≤ one `MOVE_*` + ≤ one `TURN_*`, raw-float magnitudes) and `reset() -> None` (sets `e_prev` to `(0.0, 0.0)`).
  - Module constants `DEAD_ZONE_RADIUS`, `OUTER_SATURATION`, `RESPONSE_EXPONENT`, `MAGNITUDE_EMA_ALPHA`, `RELEASE_EMA_ALPHA`, `EMA_ZERO_EPSILON`.

- [ ] **Step 1: Write the failing tests**

Replace the whole file `tests/test_input_gaze.py`:

```python
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


def test_a_single_sample_dropout_barely_dents_the_output() -> None:
    f = GazeVectorFilter()
    for _ in range(6):
        f.update((0.0, -0.8), now=0.0)          # steady forward
    before = next(h.magnitude for h in f.update((0.0, -0.8), now=0.0))
    dip = next(h.magnitude for h in f.update((0.0, 0.0), now=0.0))   # one dropout
    assert dip > 0.5 * before                    # EMA, not a hard drop


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
    pts = []
    for i in range(31):
        t = i / 30.0
        pts.append((round(cx + t * k), round(cy - (1.0 - t) * k)))   # forward -> right
    mags: list[float] = []
    for (x, y) in pts:
        out = f.update(s.resolve(x, y), now=0.0)
        fwd = [h.magnitude for h in out if h.action is Action.MOVE_FORWARD]
        mags.append(fwd[0] if fwd else 0.0)
    # forward is present for the whole sweep while the vector still points up,
    # and never collapses to 0 between two non-zero samples.
    nonzero = [m for m in mags if m > 0.0]
    assert len(nonzero) >= 20
    for a, b in zip(mags, mags[1:]):
        if a > 0.0 and b == 0.0:
            assert False, "forward cut out mid-sweep"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest tests/test_input_gaze.py -q`
Expected: FAIL — `ImportError: cannot import name 'GazeStick'` (the module still has `GazeZoneMap`/`GazeFilter`).

- [ ] **Step 3: Rewrite the implementation**

Replace the whole file `src/pewpew/input/gaze.py`:

```python
"""The radial analog stick and the vector filter over the gaze cursor (R14)."""

from __future__ import annotations

from math import hypot

from pewpew.input.actions import Action, HeldAction

DEAD_ZONE_RADIUS = 0.28
OUTER_SATURATION = 0.95
RESPONSE_EXPONENT = 1.5
MAGNITUDE_EMA_ALPHA = 0.4
RELEASE_EMA_ALPHA = 0.8
EMA_ZERO_EPSILON = 1e-3


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


class GazeStick:
    """Map a gaze pixel to a curved, saturated 2-D stick vector ``(fx, fy)``."""

    def __init__(
        self,
        surface_w: int,
        surface_h: int,
        *,
        dead_zone_radius: float = DEAD_ZONE_RADIUS,
        outer_saturation: float = OUTER_SATURATION,
        response_exponent: float = RESPONSE_EXPONENT,
    ) -> None:
        assert 0.0 < dead_zone_radius < outer_saturation <= 1.0, (
            "need 0 < dead_zone_radius < outer_saturation <= 1"
        )
        assert response_exponent > 0.0, "response_exponent must be > 0"
        self._cx = surface_w // 2
        self._cy = surface_h // 2
        self._half_w = surface_w / 2.0
        self._half_h = surface_h / 2.0
        self._dead = dead_zone_radius
        self._outer = outer_saturation
        self._exp = response_exponent

    def resolve(self, x: int, y: int) -> tuple[float, float]:
        nx = (x - self._cx) / self._half_w
        ny = (y - self._cy) / self._half_h
        r_raw = hypot(nx, ny)
        r = min(1.0, r_raw)
        if r <= self._dead:
            return (0.0, 0.0)
        t = _clamp01((r - self._dead) / (self._outer - self._dead))
        s = t**self._exp
        # Unit direction from the UNCLAMPED norm, so a corner gaze trades off on
        # the unit circle instead of over-driving both axes by up to ~41%.
        return (nx / r_raw * s, ny / r_raw * s)


class GazeVectorFilter:
    """Dual-rate EMA over the stick vector, then map to held actions."""

    def __init__(
        self,
        *,
        ema_alpha: float = MAGNITUDE_EMA_ALPHA,
        release_alpha: float = RELEASE_EMA_ALPHA,
    ) -> None:
        self._alpha = ema_alpha
        self._release_alpha = release_alpha
        self._ex = 0.0
        self._ey = 0.0

    def reset(self) -> None:
        self._ex = 0.0
        self._ey = 0.0

    def update(self, vec: tuple[float, float], now: float) -> frozenset[HeldAction]:
        del now  # retained for pipeline symmetry; the default filter does not read it
        vx, vy = vec
        alpha = self._release_alpha if (vx == 0.0 and vy == 0.0) else self._alpha
        self._ex = alpha * vx + (1.0 - alpha) * self._ex
        self._ey = alpha * vy + (1.0 - alpha) * self._ey
        if hypot(self._ex, self._ey) < EMA_ZERO_EPSILON:
            self._ex = 0.0
            self._ey = 0.0

        out: set[HeldAction] = set()
        if self._ey < 0.0:
            out.add(HeldAction(Action.MOVE_FORWARD, -self._ey))
        elif self._ey > 0.0:
            out.add(HeldAction(Action.MOVE_BACKWARD, self._ey))
        if self._ex < 0.0:
            out.add(HeldAction(Action.TURN_LEFT, -self._ex))
        elif self._ex > 0.0:
            out.add(HeldAction(Action.TURN_RIGHT, self._ex))
        return frozenset(out)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest tests/test_input_gaze.py -q`
Expected: PASS (all 14).

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/input/gaze.py tests/test_input_gaze.py
git commit -m "feat(input): replace gaze zones with a radial analog stick (R14 task 1)"
```

---

## Task 2: `pewpew.input.actions` — per-tick analog router with one quantiser

**Files:**
- Modify: `src/pewpew/input/actions.py`
- Modify test: `tests/test_input_actions.py`

**Interfaces:**
- Consumes: `pewpew.ipc.protocol.Message` (`Message.action(code, value)`, `Message.turn(code, value)`, `Message.pulse(code)`, `Message.discrete(code)` — unchanged).
- Produces:
  - New module constant `MOVE_MAGNITUDE_SCALE = 10000`.
  - `ActionRouter.set_held(held: frozenset[HeldAction])` — for every `MOVE_*` / `TURN_*` axis present, emits one frame **per call** carrying the quantised wire value; `q == 0` while newly held emits nothing; one `0` frame on the fall / on release.
  - `ActionRouter.pulse(action)`, `.discrete(action)`, `.release_all()` — unchanged behaviour (release_all emits one `0` per axis with an outstanding non-zero frame, then clears).
  - `HeldAction`, `Action`, `TURN_MAX_MOUSE_DELTA`, `MAGNITUDE_STEPS` — unchanged names.

- [ ] **Step 1: Write / update the failing tests**

Replace `tests/test_input_actions.py` with:

```python
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
    assert values[(MessageType.TURN, Action.TURN_LEFT)] == 40


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest tests/test_input_actions.py -q`
Expected: FAIL — `ImportError: cannot import name 'MOVE_MAGNITUDE_SCALE'`, and (once that is added) the per-tick / sub-quantum tests fail against the old on/off `set_held`.

- [ ] **Step 3: Modify the implementation**

In `src/pewpew/input/actions.py`, (a) add the constant beside the others:

```python
MAGNITUDE_STEPS = 20
TURN_MAX_MOUSE_DELTA = 40
MOVE_MAGNITUDE_SCALE = 10000
```

(b) replace `_turn_value` and add the shared quantiser + a MOVE scaler:

```python
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
```

(c) replace `ActionRouter` body (`_held` now maps an axis → its last non-zero wire value; present ⟺ a non-zero frame is outstanding):

```python
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
```

Keep the existing imports (`enum`, `Callable`, `dataclass`, `Message`) and the `Action` enum, `_MOVE`, `_TURN`, `HeldAction` definitions unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest tests/test_input_actions.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/input/actions.py tests/test_input_actions.py
git commit -m "feat(input): per-tick analog MOVE+TURN emit with one quantiser (R14 task 2)"
```

---

## Task 3: `pewpew.input.pipeline` — explicit surface, stick wiring, filter reset

**Files:**
- Modify: `src/pewpew/input/pipeline.py`
- Modify: `src/pewpew/input/simulator_source.py` (add the `widget` property — the pipeline's `surface=None` fallback consumes it)
- Modify: `tests/fakes/fake_input.py`
- Modify test: `tests/test_input_pipeline.py`
- Modify test: `tests/test_input_source_qt.py` (one test for the property)

**Interfaces:**
- Consumes: `GazeStick`, `GazeVectorFilter` (Task 1); `ActionRouter` (Task 2, signature unchanged); `pewpew.input.fire.FireArbiter` (unchanged); `pewpew.input.source.InputSample` (unchanged).
- Produces:
  - `InputPipeline(source, send, *, surface: tuple[int, int] | None = None, spoken_fire=None)` — when `surface is None`, reads `(source.widget.width(), source.widget.height())`. Builds `GazeStick(*surface)` and `GazeVectorFilter()`.
  - `InputPipeline.tick(now)`, `.release_all()` (now calls `self._filter.reset()`), `.toggle_pause()`, `.paused: bool` — unchanged signatures.
  - `SimulatorInputSource.widget -> QWidget` — read-only property.
  - `FakeInputSource(queue, *, widget_size=(640, 480))` with a `.widget` exposing `.width()` / `.height()`.

- [ ] **Step 1: Write / update the failing tests**

(a) `tests/fakes/fake_input.py` — replace the file:

```python
"""A scripted InputSource for pipeline tests."""

from __future__ import annotations

from pewpew.input.source import InputSample

_EMPTY = InputSample(
    gaze_xy=None, activation_edge=False, pause_edge=False, debug_fire_edge=False
)


class _FakeWidget:
    def __init__(self, w: int, h: int) -> None:
        self._w, self._h = w, h

    def width(self) -> int:
        return self._w

    def height(self) -> int:
        return self._h


class FakeInputSource:
    def __init__(self, queue: list[InputSample], *, widget_size=(640, 480)) -> None:
        self.queue = queue
        self.widget = _FakeWidget(*widget_size)

    def sample(self, now: float) -> InputSample:
        return self.queue.pop(0) if self.queue else _EMPTY
```

(b) `tests/test_input_pipeline.py` — replace the file:

```python
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
    track = []
    for i in range(31):
        t = i / 30.0
        track.append(
            InputSample((round(cx + t * k), round(cy - (1.0 - t) * k)), False, False, False)
        )
    pipe, sent = _pipe(track)
    for i in range(31):
        pipe.tick(now=i)
    fwd = _values(sent, MessageType.ACTION, 1)
    assert len([v for v in fwd if v > 0]) >= 18
    assert 0 not in fwd[: fwd.index(0)] if 0 in fwd else True  # no interior zero before the tail


def test_finding_3_forward_value_rises_monotonically_with_gaze_eccentricity() -> None:
    last = -1
    for dy in (30, 60, 100, 160, 230):
        pipe, sent = _pipe([InputSample((320, 240 - dy), False, False, False)] * 12)
        for i in range(12):
            pipe.tick(now=i)
        v = _values(sent, MessageType.ACTION, 1)[-1]
        assert v >= last
        last = v
    assert last == 10000  # the outer sample saturates


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


def test_release_all_resets_the_filter_emits_zeros_and_clears_paused() -> None:
    hold = InputSample((639, 240), False, False, False)
    pipe, sent = _pipe([hold] * 10)
    for i in range(10):
        pipe.tick(now=i)
    pipe.toggle_pause()
    sent.clear()
    pipe.release_all()
    assert pipe.paused is False
    assert sent and all(
        m.value == 0 for m in sent if m.type in (MessageType.TURN, MessageType.ACTION)
    )
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
```

(c) `tests/test_input_source_qt.py` — add one test:

```python
def test_widget_property_exposes_the_filtered_widget(qtbot) -> None:
    w = _widget(qtbot)
    src = SimulatorInputSource(w)
    assert src.widget is w
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest tests/test_input_pipeline.py tests/test_input_source_qt.py::test_widget_property_exposes_the_filtered_widget -q`
Expected: FAIL — `AttributeError: 'InputPipeline' object has no attribute '_stick'` / `'SimulatorInputSource' object has no attribute 'widget'`.

- [ ] **Step 3: Modify the implementations**

(a) `src/pewpew/input/pipeline.py` — replace the imports and `__init__`, adjust `tick` and `release_all`:

```python
"""The single unit that wires source -> gaze -> fire -> router -> IPC send."""

from __future__ import annotations

from collections.abc import Callable

from pewpew.input.actions import Action, ActionRouter
from pewpew.input.fire import FireArbiter, NullSpokenFireSource, SpokenFireSource
from pewpew.input.gaze import GazeStick, GazeVectorFilter
from pewpew.input.source import InputSource
from pewpew.ipc.protocol import Message


class InputPipeline:
    def __init__(
        self,
        source: InputSource,
        send: Callable[[Message], None],
        *,
        surface: tuple[int, int] | None = None,
        spoken_fire: SpokenFireSource | None = None,
    ) -> None:
        self._source = source
        if surface is None:
            widget = source.widget
            surface = (widget.width(), widget.height())
        self._stick = GazeStick(*surface)
        self._filter = GazeVectorFilter()
        self._fire = FireArbiter()
        self._router = ActionRouter(self._guarded_send)
        self._send = send
        self._spoken = spoken_fire or NullSpokenFireSource()
        self.paused = False

    def _guarded_send(self, message: Message) -> None:
        try:
            self._send(message)
        except OSError:
            pass  # a dead peer is handled by the host's disconnect path

    def tick(self, now: float) -> None:
        sample = self._source.sample(now)
        vec = (
            self._stick.resolve(*sample.gaze_xy)
            if sample.gaze_xy is not None
            else (0.0, 0.0)
        )
        self._router.set_held(self._filter.update(vec, now))
        if sample.activation_edge:
            self._fire.deliberate_action()
        if self._spoken.spoken_fire_edge() or sample.debug_fire_edge:
            self._fire.spoken_fire()
        if self._fire.poll(now):
            self._router.pulse(Action.FIRE)
        if sample.pause_edge:
            self.toggle_pause()

    def toggle_pause(self) -> None:
        self._router.discrete(Action.PAUSE)
        self.paused = not self.paused

    def release_all(self) -> None:
        self._filter.reset()
        self._fire.reset()
        self._router.release_all()
        self.paused = False
```

(b) `src/pewpew/input/simulator_source.py` — add the property (right after `__init__`):

```python
    @property
    def widget(self) -> QWidget:
        return self._widget
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest tests/test_input_pipeline.py tests/test_input_source_qt.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/input/pipeline.py src/pewpew/input/simulator_source.py tests/fakes/fake_input.py tests/test_input_pipeline.py tests/test_input_source_qt.py
git commit -m "feat(input): pipeline builds the stick from the viewport surface (R14 task 3)"
```

---

## Task 4: `pewpew.host_widget` — build the pipeline with the viewport surface

**Files:**
- Modify: `src/pewpew/host_widget.py` (the `showEvent` first-start branch, ~line 204)
- Modify test: `tests/test_host_widget_qt.py` (+1 test)

**Interfaces:**
- Consumes: `InputPipeline(source, send, *, surface=..., spoken_fire=...)` (Task 3); `SimulatorInputSource` (Task 3).
- Produces: no new interface — a behavioural guarantee that the non-injected pipeline's `GazeStick` centre is `(320, 240)` for the real `(0, 80, 640, 480)` viewport.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_host_widget_qt.py` (near the other non-injected `_host` tests, using the module's existing `_Engine` / `_Reader` / `_Server` fakes and `SimpleNamespace`):

```python
def test_showevent_builds_the_pipeline_stick_on_the_viewport_surface(qtbot) -> None:
    """Finding-1 regression guard at the host layer: no injected pipeline, so
    showEvent builds the real InputPipeline with surface = the 640x480 viewport."""
    engine = _Engine()
    engine.start = lambda *, ipc_address=None: 8128
    reader = _Reader()
    server = _Server()
    config = SimpleNamespace(viewport_width=640, viewport_height=480)
    host = DoomHostWidget(config, engine=engine, frame_reader=reader, ipc_server=server)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    stick = host._pipeline._stick
    assert (stick._cx, stick._cy) == (320, 240)
    host.cleanup()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest tests/test_host_widget_qt.py::test_showevent_builds_the_pipeline_stick_on_the_viewport_surface -q`
Expected: FAIL — the pipeline is built with the default `surface=None`, `SimulatorInputSource.widget` is the viewport (640×480) so `_cy` is `240`… actually this passes by accident once Task 3 lands. To make the test *meaningful as a host-layer guard*, it must fail if the host stops passing `surface` AND the source stops exposing `widget`. Keep it as a guard; before Task 4's edit it already passes via the Task-3 fallback. That is acceptable — the assertion still catches a regression to a 640×640 constant. Proceed to Step 3 to make the host pass `surface` explicitly (the product path per R14).

- [ ] **Step 3: Modify the implementation**

In `src/pewpew/host_widget.py`, the `showEvent` first-start branch currently reads:

```python
                self._pipeline = self._injected_pipeline or InputPipeline(
                    SimulatorInputSource(self.viewport), self._server.send
                )
```

Replace with:

```python
                self._pipeline = self._injected_pipeline or InputPipeline(
                    SimulatorInputSource(self.viewport),
                    self._server.send,
                    surface=(self.viewport.width(), self.viewport.height()),
                )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest tests/test_host_widget_qt.py -q`
Expected: PASS (all — the new test plus the existing suite).

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/host_widget.py tests/test_host_widget_qt.py
git commit -m "feat(host): build the input pipeline with the explicit viewport surface (R14 task 4)"
```

- [ ] **Step 6: Full Python suite green**

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest -q`
Expected: all pass, 6 POSIX-only skips. If `tests/test_distribution_metadata.py::test_c_patch_constants_match_the_python_enums` fails now it is because Task 2 added `MOVE_MAGNITUDE_SCALE` but the C patch has no `IPC_MOVE_WIRE_MAX` yet — that is expected and fixed in Task 5/Task 7. Note it and continue; do **not** weaken that test.

---

## Task 5: `patches/crispy-doom-ipc-input.diff` — analog forward, coalescing, watchdog

**Files:**
- Regenerate: `patches/crispy-doom-ipc-input.diff` (adds a `src/doom/g_game.c` hunk; rewrites `src/i_ipc_input.c` / `.h`)
- Build artifact (not committed): `build/crispy/` rebuilt

**Interfaces:**
- Consumes: the wire frame (unchanged); `MOVE_MAGNITUDE_SCALE = 10000` from Python (mirrored as `IPC_MOVE_WIRE_MAX`).
- Produces: a `crispy-doom.exe` whose `MOVE_*` frames drive an analog `cmd->forwardmove` contribution; `git apply --check` still passes via `build_crispy.py --check`.

- [ ] **Step 1: Confirm mechanism 1 against the real source**

Read `build/crispy/src/doom/g_game.c` around `G_BuildTiccmd`. Confirm: `forwardmove[2] = {0x19, 0x32}` (line ~169), `#define MAXPLMOVE (forwardmove[1])` (= 50), and the clamp block:

```c
    if (forward > MAXPLMOVE)
        forward = MAXPLMOVE;
    else if (forward < -MAXPLMOVE)
        forward = -MAXPLMOVE;
    ...
    cmd->forwardmove += forward;
```

The fold point is **immediately before `if (forward > MAXPLMOVE)`** (currently line ~904). Record in the patch header: "chosen: additive `forward` term inside `G_BuildTiccmd` (deterministic, config-independent); rejected: `ev_joystick` (crispy `use_analog=1` by default but the term is scaled by `forwardmove[speed]` = walk 25 unless always-run, overwrites `joyxmove/joyymove/joystrafemove/joylook`, reverts to digital if `default.cfg` disables `use_analog`); keyboard duty-cycle (a `BuildNewTic()` pump call is not always a built tic)."

- [ ] **Step 2: Stage the doubly-patched tree for editing**

Use Git-for-Windows `git` (e.g. `& "C:\Program Files\Git\bin\git.exe"`). From `E:\Projectos\doomed_prism`:

```bash
git -C build/crispy reset --hard 0a022e0ee6c74d9bab173ed9ee5212312e90ce3a
git -C build/crispy clean -fd -- src/
git -C build/crispy apply ../../patches/crispy-doom-fb-export.diff
git -C build/crispy -c user.email=x@x -c user.name=x commit -aqm "P1 BASE (temp)"
git -C build/crispy apply ../../patches/crispy-doom-ipc-input.diff
```

The working tree now has patch 1 committed and patch 2 (the current version) applied but unstaged. Edit the four source files below, then regenerate the diff in Step 7.

- [ ] **Step 3: Rewrite `build/crispy/src/i_ipc_input.h`**

Add the accessor declaration:

```c
#ifndef I_IPC_INPUT_H
#define I_IPC_INPUT_H

void IPC_Input_Init(void);
void IPC_Input_Pump(void);
void IPC_Input_Shutdown(void);

// DOOMed Prism (R14): the signed analog forwardmove contribution for the
// current tic, already scaled to +/-MOVE_MAX_FORWARDMOVE. Returns 0 when the
// IPC input path is disabled. G_BuildTiccmd folds this into its local `forward`.
int IPC_Input_ForwardMove(void);

#endif
```

Keep the existing GPL header and the wire-format comment block above it.

- [ ] **Step 4: Rewrite `build/crispy/src/i_ipc_input.c`**

Changes, keeping every unchanged function verbatim:

(a) Add to the `#define` block (after `IPC_TURN_CLAMP 40`):

```c
#define IPC_MOVE_WIRE_MAX 10000      /* == pewpew.input.actions.MOVE_MAGNITUDE_SCALE */
#define MOVE_MAX_FORWARDMOVE 50      /* DOOM forwardmove[1] run value == MAXPLMOVE */
#define IPC_MOVE_STALE_PUMPS 6       /* pumps with no ACTION frame -> stop moving  */
```

(b) Replace the movement-key state. **Delete**:

```c
enum { H_FWD, H_BACK, H_COUNT };
static int held[H_COUNT];
static int held_key[H_COUNT];
```

and **add**:

```c
static int ipc_forwardmove = 0;   /* signed, already scaled to +/-MOVE_MAX_FORWARDMOVE */
static int ipc_move_stale = 0;    /* pumps since the last ACTION frame */
```

(c) Replace `ipc_release_all`:

```c
static void ipc_release_all(void)
{
    int i;
    ipc_forwardmove = 0;
    for (i = 0; i < 4; i++)
        if (pulse_tics[i] > 0) { ipc_post_key(ev_keyup, pulse_key[i]); pulse_tics[i] = 0; }
    ipc_post_key(ev_keyup, key_fire);
    ipc_post_key(ev_keyup, key_use);
}
```

(d) In `IPC_Input_Init`, **delete** the two lines:

```c
    held_key[H_FWD] = key_up;
    held_key[H_BACK] = key_down;
```

(e) Add a scaler and the accessor (above `ipc_apply`):

```c
static void ipc_store_forwardmove(uint16_t code, int32_t value)
{
    int mag = (int) (value < 0 ? -value : value);
    if (code != AC_MOVE_FORWARD && code != AC_MOVE_BACKWARD) return;
    if (mag > IPC_MOVE_WIRE_MAX) mag = IPC_MOVE_WIRE_MAX;
    mag = (int) (((long) mag * MOVE_MAX_FORWARDMOVE) / IPC_MOVE_WIRE_MAX);
    ipc_forwardmove = (code == AC_MOVE_BACKWARD) ? -mag : mag;
    ipc_move_stale = 0;   /* any ACTION frame, including value 0, is liveness */
}

int IPC_Input_ForwardMove(void)
{
    return ipc_enabled ? ipc_forwardmove : 0;
}
```

(f) In `ipc_apply`, **delete** the whole `case MT_ACTION:` block and the whole `case MT_TURN:` block (they are handled in the pump now for coalescing). Leave `MT_PULSE`, `MT_DISCRETE`, `MT_BYE`, `default`.

(g) Replace `IPC_Input_Pump` entirely:

```c
void IPC_Input_Pump(void)
{
    int i, n;
    int have_turn = 0, turn_dx = 0;

    if (!ipc_enabled) return;

    for (i = 0; i < 4; i++)
        if (pulse_tics[i] > 0 && --pulse_tics[i] == 0)
            ipc_post_key(ev_keyup, pulse_key[i]);

    /* Forward staleness watchdog: a frozen (not dead) supervisor sends no EOF,
       so decay forward to 0 the way turn already self-cancels via mousex. */
    if (ipc_move_stale < IPC_MOVE_STALE_PUMPS)
    {
        ipc_move_stale++;
        if (ipc_move_stale >= IPC_MOVE_STALE_PUMPS)
            ipc_forwardmove = 0;
    }

    for (;;)
    {
        uint8_t type;
        uint16_t code;
        int32_t value;

        n = (int) recv(ipc_sock, (char *) ipc_buf + ipc_have,
                       IPC_FRAME_SIZE - ipc_have, 0);
        if (n == 0) { ipc_disable(); return; }
        if (n < 0)
        {
            if (IPC_WOULDBLOCK) break;
            ipc_disable();
            return;
        }
        ipc_have += n;
        if (ipc_have < IPC_FRAME_SIZE) continue;
        ipc_have = 0;

        if (ipc_buf[0] != IPC_PROTOCOL_VERSION) { ipc_disable(); return; }
        type = ipc_buf[1];
        code = (uint16_t) (ipc_buf[2] | (ipc_buf[3] << 8));
        value = (int32_t) ((uint32_t) ipc_buf[4]
              | ((uint32_t) ipc_buf[5] << 8)
              | ((uint32_t) ipc_buf[6] << 16)
              | ((uint32_t) ipc_buf[7] << 24));

        if (type == MT_TURN)
        {
            int d = value;
            if (d > IPC_TURN_CLAMP) d = IPC_TURN_CLAMP;
            if (d < 0) d = 0;
            have_turn = 1;                                  /* last TURN wins */
            turn_dx = (code == AC_TURN_LEFT) ? -d : d;
        }
        else if (type == MT_ACTION)
        {
            ipc_store_forwardmove(code, value);            /* last ACTION wins */
        }
        else
        {
            ipc_apply(type, code, value);                  /* PULSE/DISCRETE/BYE: per frame */
            if (!ipc_enabled) return;                      /* MT_BYE disabled us */
        }
    }

    if (have_turn && turn_dx != 0)
        ipc_post_mouse_x(turn_dx);
}
```

Update the call-site binding comment at the top of the file to note "R14: TURN and ACTION frames are coalesced per drain — the pump keeps only the most recent of each and applies it once; the additive `forward` term (mechanism 1) is folded in G_BuildTiccmd; IPC_MOVE_STALE_PUMPS zeroes forward when the producer freezes without an EOF."

- [ ] **Step 5: Add the `src/doom/g_game.c` hunk**

In `build/crispy/src/doom/g_game.c`:

(a) Add the include beside the existing `i_*.h` includes near the top (after `#include "i_system.h"` or similar):

```c
#include "i_ipc_input.h"
```

(b) Immediately before `if (forward > MAXPLMOVE)` (currently line ~904), insert:

```c
    // DOOMed Prism (R14): fold the IPC analog forward contribution into the
    // local `forward` so it is clamped to +/-MAXPLMOVE together with any
    // SDL-keyboard forward below (no turbo), before cmd->forwardmove += forward.
    forward += IPC_Input_ForwardMove();

```

- [ ] **Step 6: Build and probe (Windows)**

```bash
export PATH="/c/msys64/ucrt64/bin:$PATH"
& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" scripts/build_crispy.py
```

Expected: builds `build/crispy/build/src/crispy-doom.exe`. Then run a live handshake + framebuffer probe (reuse the pattern from `scripts/ci_ipc_smoke.py` locally, or the scratchpad launch script): start an `IpcServer`, launch the exe with `DOOMED_PRISM_IPC_ADDR` + `DOOMED_PRISM_FB_NAME` + `DOOMED_PRISM_WARP="1 1"`, `poll()` to `is_connected`, stream a `Message.action(MOVE_FORWARD, 10000)` for ~2 s then `Message.action(MOVE_FORWARD, 0)`, confirm `frame_counter` keeps advancing and no `proc.poll()`.

- [ ] **Step 7: Regenerate the committed diff**

```bash
git -C build/crispy add -A src/
git -C build/crispy diff --cached HEAD -- \
  src/i_ipc_input.c src/i_ipc_input.h src/d_loop.c src/i_video.c \
  src/CMakeLists.txt src/doom/g_game.c > patches/crispy-doom-ipc-input.diff
git -C build/crispy reset --hard 0a022e0ee6c74d9bab173ed9ee5212312e90ce3a
git -C build/crispy clean -fd -- src/
```

Then verify the regenerated series still composes and rebuilds:

```bash
& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" scripts/build_crispy.py --check
export PATH="/c/msys64/ucrt64/bin:$PATH"
& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" scripts/build_crispy.py
```

Expected: `--check` exits 0 ("restore + real apply p1 + apply --check p2"), the build succeeds. Confirm the diffstat:

```bash
git apply --stat patches/crispy-doom-ipc-input.diff
```

Expected files only: `src/CMakeLists.txt`, `src/d_loop.c`, `src/doom/g_game.c`, `src/i_ipc_input.c`, `src/i_ipc_input.h`, `src/i_video.c`; total added lines ≤ 420.

- [ ] **Step 8: Run the Python suite**

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest -q`
Expected: `tests/test_distribution_metadata.py::test_c_patch_constants_match_the_python_enums` still fails (the assertions for `IPC_MOVE_WIRE_MAX` are added in Task 7); everything else green. Do not fix it here.

- [ ] **Step 9: Commit**

```bash
git add patches/crispy-doom-ipc-input.diff
git commit -m "feat(engine): analog forwardmove, per-drain coalescing, stale watchdog (R14 task 5)"
```

---

## Task 6: `scripts/ci_ipc_smoke.py` + `ci.yml` — analog MOVE flood assertions

**Files:**
- Modify: `scripts/ci_ipc_smoke.py`
- Modify: `.github/workflows/ci.yml` (step-summary text only)

**Interfaces:**
- Consumes: `Message.action`, `Message.turn`, `Message.pulse`; `MOVE_MAGNITUDE_SCALE`, `TURN_MAX_MOUSE_DELTA` from `pewpew.input.actions`.
- Produces: a CI check that fails if the analog forward path is a no-op, wrong-signed, or engine-aborting.

- [ ] **Step 1: Edit `scripts/ci_ipc_smoke.py`**

Add the import:

```python
from pewpew.input.actions import Action, MOVE_MAGNITUDE_SCALE, TURN_MAX_MOUSE_DELTA  # noqa: E402
```

Replace the flood loop (the `for i in range(FLOOD_FRAMES):` block and the assertions after it) with:

```python
    RAMP_START, RAMP_LEN = 120, 160          # 80 frames forward 0->max->0, then 80 backward
    counters: set[int] = set()
    ramp_counters: set[int] = set()
    for i in range(FLOOD_FRAMES):
        # TURN sweep spanning 0 .. TURN_MAX_MOUSE_DELTA + margin (exercises the C clamp)
        server.send(Message.turn(int(Action.TURN_RIGHT), i % (TURN_MAX_MOUSE_DELTA + 8)))
        # analog MOVE ramp: a triangle 0 -> MOVE_MAGNITUDE_SCALE -> 0, forward then backward
        if RAMP_START <= i < RAMP_START + RAMP_LEN:
            k = i - RAMP_START
            half = RAMP_LEN // 2
            local = k if k < half else k - half
            frac = local / (half - 1)
            tri = 1.0 - abs(2.0 * frac - 1.0)
            code = Action.MOVE_FORWARD if k < half else Action.MOVE_BACKWARD
            server.send(Message.action(int(code), round(tri * MOVE_MAGNITUDE_SCALE)))
        elif i == RAMP_START + RAMP_LEN:
            server.send(Message.action(int(Action.MOVE_FORWARD), 0))
            server.send(Message.action(int(Action.MOVE_BACKWARD), 0))
        if i % 50 == 0:
            server.send(Message.pulse(int(Action.FIRE)))
        server.poll()
        if proc.poll() is not None:
            _fail(f"engine exited early ({proc.returncode}) during the flood")
        frame = reader.latest()
        if frame is not None:
            counters.add(frame.counter)
            if RAMP_START <= i < RAMP_START + RAMP_LEN:
                ramp_counters.add(frame.counter)
        time.sleep(1 / 60)
    reader.close()
    if not server.is_connected:
        _fail("engine disconnected during the action flood")
    if len(counters) < 10:
        _fail(f"frame_counter did not advance under IPC load ({len(counters)})")
    if len(ramp_counters) < 10:
        _fail(f"frame_counter stalled during the analog MOVE ramp ({len(ramp_counters)})")
    print(
        f"frame_counter advancing under IPC load: {len(counters)} distinct values "
        f"({len(ramp_counters)} during the analog MOVE ramp)"
    )
```

Keep `FLOOD_FRAMES = 500`, the connect/handshake, the framebuffer open loop, and the teardown/orphan/socket checks exactly as they are.

- [ ] **Step 2: Edit `.github/workflows/ci.yml`**

In the "IPC runtime smoke test" step's `$GITHUB_STEP_SUMMARY` block, replace the `:white_check_mark:` line with:

```yaml
            echo ":white_check_mark: The patched engine connected over a local socket, completed the version handshake, stayed live with an advancing \`frame_counter\` under a 500-frame action flood **including an analog forward/back \`forwardmove\` ramp**, and tore down cleanly with no orphan and no leftover socket."
```

- [ ] **Step 3: Local dry-run (optional, Windows has no POSIX AF_UNIX path)**

`scripts/ci_ipc_smoke.py` `sys.exit(0)`s on `win32`. Confirm it still imports cleanly:

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" scripts/ci_ipc_smoke.py x y`
Expected: prints `IPC runtime smoke: skipped (not a POSIX platform)` and exits 0.

- [ ] **Step 4: Commit**

```bash
git add scripts/ci_ipc_smoke.py .github/workflows/ci.yml
git commit -m "test(ci): flood the analog MOVE path in the IPC runtime smoke (R14 task 6)"
```

---

## Task 7: `tests/test_distribution_metadata.py` + README — constant match & allow-list

**Files:**
- Modify test: `tests/test_distribution_metadata.py`
- Modify: `README.md` (one status line)

**Interfaces:**
- Consumes: `patches/crispy-doom-ipc-input.diff` (Task 5); `MOVE_MAGNITUDE_SCALE` (Task 2).
- Produces: a green `test_c_patch_constants_match_the_python_enums` plus a new file-set allow-list test.

- [ ] **Step 1: Update the tests**

In `tests/test_distribution_metadata.py`, extend `test_c_patch_constants_match_the_python_enums` — after the existing `turn_clamp` assertion add:

```python
    from pewpew.input.actions import MOVE_MAGNITUDE_SCALE

    move_wire_max = int(
        re.search(r"#define\s+IPC_MOVE_WIRE_MAX\s+(\d+)", diff).group(1)
    )
    assert move_wire_max == MOVE_MAGNITUDE_SCALE == 10000
    assert re.search(r"#define\s+MOVE_MAX_FORWARDMOVE\s+50\b", diff)
    assert re.search(r"#define\s+IPC_MOVE_STALE_PUMPS\s+\d+", diff)
```

Add a new test:

```python
def test_ipc_patch_touches_only_the_allowed_engine_files() -> None:
    import re

    diff = (ROOT / "patches" / "crispy-doom-ipc-input.diff").read_text(encoding="utf-8")
    touched = set(re.findall(r"^diff --git a/(\S+) b/\S+", diff, re.MULTILINE))
    allowed = {
        "src/i_ipc_input.c",
        "src/i_ipc_input.h",
        "src/d_loop.c",
        "src/i_video.c",
        "src/CMakeLists.txt",
        "src/doom/g_game.c",  # R14 mechanism 1: the forwardmove fold
    }
    assert touched <= allowed, f"unexpected files in the IPC patch: {touched - allowed}"
```

- [ ] **Step 2: Update the README status line**

In `README.md`, find the "Current status" / "What comes next" area and set the input-layer line to name the model, e.g.:

```markdown
- **Milestone 3a — input & IPC:** implemented on `feature/doomed-prism-m3`.
  Gaze drives a **radial analog stick** — proportional turn *and* forward/back
  from one gaze vector — over a local IPC socket to the patched engine; the
  Windows/Raven decision gate is still pending.
```

Keep the `## License` section untouched (it already names "the frame-export and IPC-input patches").

- [ ] **Step 3: Run the tests**

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest tests/test_distribution_metadata.py -q`
Expected: PASS (all — including the previously-failing constants test).

- [ ] **Step 4: Commit**

```bash
git add tests/test_distribution_metadata.py README.md
git commit -m "test(dist): assert the new C constants and the patch file-set; README (R14 task 7)"
```

---

## Task 8: validation gate docs — R14 geometry and the five decision strings

**Files:**
- Rewrite sections of: `docs/validation/milestone-3a-checklist.md`
- Rewrite sections of: `docs/validation/milestone-3a-result.md`
- Modify test: `tests/test_validation_docs_m3.py`

**Interfaces:**
- Consumes: spec §17 (R14 objective checks + the five decision strings).
- Produces: gate docs a tester follows that describe the radial stick, and a static test that guards them.

- [ ] **Step 1: Update `tests/test_validation_docs_m3.py`**

Replace `test_gate_carries_the_four_decision_strings` and add the phrase test:

```python
def test_gate_carries_the_five_decision_strings() -> None:
    d = _docs()
    assert "PASS — IPC input path viable" in d
    assert "PASS (degraded forward) — IPC input path viable, forward single-speed" in d
    assert "FAIL — IPC input path insufficient" in d
    assert "BLOCKED/RETRY — implementation or environment failure" in d
    assert "PENDING — incomplete evidence" in d


def test_gate_describes_the_radial_stick_not_the_retired_zones() -> None:
    d = _docs()
    for present in (
        "dead-zone circle",
        "one vector",
        "proportional forward",
        "diagonal",
        "backward as reachable as forward",
    ):
        assert present in d, f"missing R14 phrase: {present}"
    for retired in ("turn band", "upper band", "lower band", "upper corner", "progressive turn"):
        assert retired not in d, f"retired zone phrase still present: {retired}"
```

Leave the other three tests (`..._ipc_only_play...`, `..._both_publication_safety_scans...`, `..._placeholder_ipc_addresses_only`) unchanged.

- [ ] **Step 2: Run to verify it fails**

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest tests/test_validation_docs_m3.py -q`
Expected: FAIL — the docs still say "turn band" / "progressive turn" / four decision strings.

- [ ] **Step 3: Rewrite the checklist geometry + decisions**

In `docs/validation/milestone-3a-checklist.md`:

(a) The "hard question" paragraph (lines ~8–13) — replace `gaze steering, progressive turn, debounced click-fire` with:

> the radial analog stick (proportional turn **and** forward/back from one gaze vector, a round dead zone), debounced click-fire

(b) The objective-check bullet list under "With Crispy's SDL window minimised … for the whole run" — replace the six zone bullets with:

```markdown
  - [ ] Gaze left of the **dead-zone circle** turns the DOOM view left; right of
    it, right. Returning gaze inside the circle stops the turn within ~3–5 ticks,
    smoothly, with no abrupt cut.
  - [ ] Gaze farther from the circle turns visibly faster than gaze just outside
    it, smoothly, with no step (the curved analog stick).
  - [ ] Gaze above the circle walks forward; below, backward — and, like turn,
    **faster the farther out**, smoothly. Record whether forward is proportional
    or (degraded mode) single-speed.
  - [ ] **Backward is as reachable and as fast as forward** — no ~9 px sliver.
  - [ ] Gaze up-and-to-a-side walks forward while turning, both from **one
    vector**; sweeping the gaze slowly across that **diagonal** (and across where
    the old zone boundary used to be) never makes forward stutter, slow abruptly,
    or cut out.
  - [ ] **One click fires one shot. Five fast clicks fire fewer than five shots**
    (debounce; the `PULSE_HOLD_TICS` key hold is understood).
  - [ ] **`F9` fires a shot through the same path** (spoken-fire fusion via the
    debug source). **A click and an `F9` within ~30 ms fire once.**
  - [ ] **`Enter` shows the `PAUSED` overlay and pauses; `Enter` again resumes.**
    No SDL-window focus was used at any point during the run.
```

(c) The "Kill the PewPew process while a turn is held" lifecycle bullet — replace `posts `ev_keyup` for every held `MOVE_*` key` with `zeroes the injected `forwardmove` contribution (and, in the duty-cycle fallback, posts `ev_keyup` for a movement key)`; and its heading with "while the stick is held forward-and-turning" and "DOOM stops turning **and stops moving forward**".

(d) The "Record the patch-2 diffstat" step (lines ~54–64) — after `and `src/CMakeLists.txt`` add `, and one clearly-marked hunk in `src/doom/g_game.c` (the R14 `forwardmove` fold)`.

(e) The "Hard decision rule" list — replace the four bullets with the five from spec §17 (verbatim): `PASS — IPC input path viable` (R14 wording), `PASS (degraded forward) — IPC input path viable, forward single-speed`, `FAIL — IPC input path insufficient`, `BLOCKED/RETRY — implementation or environment failure`, `PENDING — incomplete evidence`.

(f) Add one line to "Per-mode evidence": "During the movement checks, save the outgoing `ACTION.value` / `TURN.value` streams to `artifacts/milestone-3/` and attach a quick value-vs-eccentricity plot — a semi-objective proportionality artifact."

- [ ] **Step 4: Rewrite the result template geometry + decisions**

In `docs/validation/milestone-3a-result.md`:

(a) The objective-check table rows (lines ~78–82) — replace the five zone rows with:

```markdown
| Turn: left of the dead-zone circle turns left; right turns right; stop within ~3–5 ticks | _fill in_ | |
| Progressive turn — faster the farther from the circle, smoothly | _fill in_ | |
| Forward/back proportional to gaze eccentricity (or degraded single-speed — say which) | _fill in_ | |
| Backward as reachable and as fast as forward (no ~9 px sliver) | _fill in_ | |
| Diagonal sweep never makes forward stutter or cut out | _fill in_ | |
```

(b) The lifecycle table row for "Kill PewPew" — "DOOM stops turning **and stops moving forward**, keeps running on SDL".

(c) The "Final decision" block and the trailing decision list — replace with the five spec-§17 strings, `Final decision:` still starting as `PENDING — incomplete evidence`.

- [ ] **Step 5: Run the tests**

Run: `& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest tests/test_validation_docs_m3.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/validation/milestone-3a-checklist.md docs/validation/milestone-3a-result.md tests/test_validation_docs_m3.py
git commit -m "docs(gate): rewrite the 3a checklist/result for the radial stick (R14 task 8)"
```

- [ ] **Step 7: Full suite + publication safety**

```bash
& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" -m pytest -q
& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" scripts/check_publication_safety.py --root .
& "E:\Projectos\raven-agent-hud\.venv\Scripts\python.exe" scripts/check_publication_safety.py --root . --history
git diff --check
```

Expected: all tests pass (6 POSIX-only skips), both scans exit 0, no whitespace errors. This is the local pre-CI gate; CI additionally runs `ci_ipc_smoke.py` on Linux.

---

## Self-Review

**1. Spec coverage.** R14 model → Task 1. R14 "Router" quantiser → Task 2. §9 `widget` accessor + §7 `surface` → Task 3. §4 `host_widget` explicit surface → Task 4. §10 (analog `forwardmove`, coalescing, watchdog, `#define`s, `g_game.c` fold, mechanism-1 record) → Task 5. §13 analog-MOVE flood → Task 6. §14/§15 constant-match + file allow-list, README → Task 7. §17 five decision strings + geometry, §15 `test_validation_docs_m3` → Task 8. §12/R9 lifecycle wording lands in Task 8's checklist edits (d)/(c). §18 exit criteria = the union of Task 6 (CI) + Task 8 (result). The corner unit-vector test, the finding-2 sweep test, the `__init__` asserts, `reset()`, `EMA_ZERO_EPSILON` snap → Task 1 tests. F1/F2/F3 pipeline guards → Task 3 tests; host-layer F1 → Task 4. No spec section is left without a task.

**2. Placeholder scan.** Every code step carries real code; every test step carries runnable assertions; the C rewrites give the exact function bodies; the diff-regeneration gives the exact git commands with the pinned commit. No "TBD" / "add error handling" / "similar to Task N".

**3. Type consistency.** `GazeStick.resolve -> tuple[float, float]` (Task 1) is consumed as `vec` by `GazeVectorFilter.update(vec, now)` (Task 1) and by `InputPipeline.tick` (Task 3). `GazeVectorFilter.update -> frozenset[HeldAction]` feeds `ActionRouter.set_held(frozenset[HeldAction])` (Task 2) unchanged. `MOVE_MAGNITUDE_SCALE` is defined once (Task 2), imported by Task 6 and Task 7. `_stick` / `_filter` private names are used consistently in Tasks 3–4 tests. The C `IPC_Input_ForwardMove()` declared in `.h` (Task 5 step 3), defined in `.c` (step 4e), called in `g_game.c` (step 5) — one name. `IPC_MOVE_WIRE_MAX` is `#define`d in the C patch (Task 5) and asserted `== MOVE_MAGNITUDE_SCALE` (Task 7).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-07-doomed-prism-milestone-3a-radial-stick.md`.

Per the standing instruction this plan is audited by separate auditor agents before execution, then run via **superpowers:subagent-driven-development** (fresh subagent per task, spec+quality review after each, whole-branch review at the end), then CI, then the manual Windows/Raven decision gate.
