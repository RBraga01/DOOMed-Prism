"""The single unit that wires source -> gaze -> fire -> router -> IPC send."""

from __future__ import annotations

from collections.abc import Callable

from pewpew.input.actions import Action, ActionRouter
from pewpew.input.fire import FireArbiter, NullSpokenFireSource, SpokenFireSource
from pewpew.input.gaze import GazeFilter, GazeZoneMap
from pewpew.input.source import InputSource
from pewpew.ipc.protocol import Message


class InputPipeline:
    def __init__(
        self,
        source: InputSource,
        send: Callable[[Message], None],
        *,
        surface: tuple[int, int] = (640, 640),
        spoken_fire: SpokenFireSource | None = None,
    ) -> None:
        self._source = source
        self._zones = GazeZoneMap(*surface)
        self._filter = GazeFilter()
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
        raw = (
            self._zones.resolve(*sample.gaze_xy)
            if sample.gaze_xy is not None
            else frozenset()
        )
        self._router.set_held(self._filter.update(raw, now))
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
