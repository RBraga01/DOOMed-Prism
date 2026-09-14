"""Owns the audio/backend/grammar cycle and feeds Action into the existing,
unmodified ActionRouter. A crash anywhere in this cycle disables voice only
-- click, gaze, and Enter/P pause are never touched (mirrors the
crash-isolation shape in src/pewpew/host_widget.py). Fire is deliberately
not handled here -- see src/pewpew/voice/fire_source.py's integration note.
"""

from __future__ import annotations

from pewpew.input.actions import ActionRouter
from pewpew.voice.asr import AsrBackend
from pewpew.voice.audio import AudioSource
from pewpew.voice.grammar import match_command


class VoiceWorker:
    def __init__(self, audio: AudioSource, backend: AsrBackend, router: ActionRouter) -> None:
        self._audio = audio
        self._backend = backend
        self._router = router
        self.disabled = False

    def record_and_dispatch(self, now: float) -> None:
        if self.disabled:
            return
        try:
            self._audio.start()
            clip = self._audio.stop()
            result = self._backend.transcribe(clip)
            action = match_command(result)
            if action is not None:
                self._router.discrete(action)
        except Exception:
            self.disabled = True
