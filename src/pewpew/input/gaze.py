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
