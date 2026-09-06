"""Input-source protocol, the InputSample record, and the Prism stub."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class InputSample:
    gaze_xy: tuple[int, int] | None
    activation_edge: bool
    pause_edge: bool
    debug_fire_edge: bool


class InputSource(Protocol):
    def sample(self, now: float) -> InputSample: ...


class PrismInputSource:
    def sample(self, now: float) -> InputSample:
        raise NotImplementedError(
            "Prism gaze/blink input arrives with the hardware phase"
        )
