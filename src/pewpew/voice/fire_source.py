"""The "pew pew" fire path (spec R13's keyword, R7's SpokenFireSource
protocol). Backed by an AsrBackend today (spec R15) -- nothing here is
Raven-specific beyond the backend object it's handed, so a future dedicated
low-latency detector is a swap at the call site, not a change to this class.
"""

from __future__ import annotations

from pewpew.voice.asr import AsrBackend, AsrStatus
from pewpew.voice.audio import AudioSource

_PEW_PEW = "pew pew"


class RavenSpokenFireSource:
    def __init__(
        self,
        backend: AsrBackend,
        audio: AudioSource,
        *,
        cooldown_s: float = 1.0,
    ) -> None:
        self._backend = backend
        self._audio = audio
        self._cooldown_s = cooldown_s
        self._edge = False
        self._last_fire: float | None = None

    def record_and_check(self, now: float) -> None:
        self._audio.start()
        clip = self._audio.stop()
        result = self._backend.transcribe(clip)
        if result.status is not AsrStatus.TRANSCRIPT:
            return
        if result.text.strip().lower() != _PEW_PEW:
            return
        if self._last_fire is not None and now - self._last_fire < self._cooldown_s:
            return
        self._last_fire = now
        self._edge = True

    def spoken_fire_edge(self) -> bool:
        edge = self._edge
        self._edge = False
        return edge
