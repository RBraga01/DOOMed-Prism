"""Gaze-zone geometry and a dwell / jitter filter over the raw region set."""

from __future__ import annotations

from pewpew.input.actions import Action, HeldAction

DEAD_ZONE_HALF_W = 180
DEAD_ZONE_HALF_H = 150
TURN_RESPONSE_EXPONENT = 1.5
MAGNITUDE_EMA_ALPHA = 0.4
DWELL_S = 0.15
JITTER_GRACE_S = 0.02

_TURN = (Action.TURN_LEFT, Action.TURN_RIGHT)


class GazeZoneMap:
    def __init__(
        self,
        surface_w: int,
        surface_h: int,
        *,
        dead_zone: tuple[int, int] = (DEAD_ZONE_HALF_W, DEAD_ZONE_HALF_H),
        turn_exponent: float = TURN_RESPONSE_EXPONENT,
    ) -> None:
        self._cx = surface_w // 2
        self._cy = surface_h // 2
        self._hw, self._hh = dead_zone
        self._exp = turn_exponent

    def _turn_magnitude(self, dx: int) -> float:
        span = max(1, self._cx - self._hw)
        m = (abs(dx) - self._hw) / span
        return max(0.0, min(1.0, m)) ** self._exp

    def resolve(self, x: int, y: int) -> frozenset[HeldAction]:
        dx, dy = x - self._cx, y - self._cy
        out_x, out_y = abs(dx) > self._hw, abs(dy) > self._hh
        if not out_x and not out_y:
            return frozenset()
        if out_x and not out_y:
            side = Action.TURN_LEFT if dx < 0 else Action.TURN_RIGHT
            return frozenset({HeldAction(side, self._turn_magnitude(dx))})
        if out_y and not out_x:
            move = Action.MOVE_FORWARD if dy < 0 else Action.MOVE_BACKWARD
            return frozenset({HeldAction(move, 1.0)})
        move = Action.MOVE_FORWARD if dy < 0 else Action.MOVE_BACKWARD
        side = Action.TURN_LEFT if dx < 0 else Action.TURN_RIGHT
        return frozenset(
            {HeldAction(move, 1.0), HeldAction(side, self._turn_magnitude(dx))}
        )


class GazeFilter:
    def __init__(
        self,
        *,
        dwell_s: float = DWELL_S,
        grace_s: float = JITTER_GRACE_S,
        ema_alpha: float = MAGNITUDE_EMA_ALPHA,
    ) -> None:
        self._dwell_s = dwell_s
        self._grace_s = grace_s
        self._alpha = ema_alpha
        self._since: dict[Action, float] = {}     # dwell start for a not-yet-emitted candidate
        self._emitted: dict[Action, float] = {}   # emitted action -> last time it was present
        self._ema: dict[Action, float] = {}

    def reset(self) -> None:
        self._since.clear()
        self._emitted.clear()
        self._ema.clear()

    def update(self, raw: frozenset[HeldAction], now: float) -> frozenset[HeldAction]:
        raw_by_action = {h.action: h.magnitude for h in raw}
        raw_nonempty = bool(raw_by_action)

        for action in list(self._since):
            if action not in raw_by_action:
                del self._since[action]
        for action in raw_by_action:
            self._since.setdefault(action, now)

        for action in list(self._emitted):
            if action in raw_by_action:
                self._emitted[action] = now
            elif raw_nonempty:  # a different region — release now
                del self._emitted[action]
                self._ema.pop(action, None)
            elif now - self._emitted[action] > self._grace_s:
                del self._emitted[action]
                self._ema.pop(action, None)

        for action, first_seen in list(self._since.items()):
            if action not in self._emitted and now - first_seen >= self._dwell_s:
                self._emitted[action] = now

        out: set[HeldAction] = set()
        for action in self._emitted:
            if action in _TURN:
                raw_m = raw_by_action.get(action, self._ema.get(action, 0.0))
                prev = self._ema.get(action, raw_m)
                m = self._alpha * raw_m + (1 - self._alpha) * prev
                self._ema[action] = m
            else:
                m = 1.0
            out.add(HeldAction(action, m))
        return frozenset(out)
