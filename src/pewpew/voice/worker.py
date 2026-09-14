"""Owns the audio/backend/grammar cycle and feeds Action into the existing,
unmodified ActionRouter. A crash anywhere in this cycle disables voice only
-- click, gaze, and Enter/P pause are never touched (mirrors the
crash-isolation shape in src/pewpew/host_widget.py). Fire is deliberately
not handled here -- see src/pewpew/voice/fire_source.py's integration note.
"""

from __future__ import annotations

from pewpew.input.actions import ActionRouter
from pewpew.voice.asr import AsrBackend, AsrStatus
from pewpew.voice.audio import AudioSource
from pewpew.voice.grammar import _PULSE_ACTIONS, match_command

# A misconfigured/broken backend (missing API key, raven_framework import
# failure) latches AsrStatus.LOCAL_ERROR forever -- see raven_backend.py's
# tri-state boundary (spec R15). That's indistinguishable from a quiet room
# to match_command (both resolve to "no command"), so this worker tracks
# *consecutive* LOCAL_ERROR cycles itself and disables rather than silently
# no-opping forever. Any TRANSCRIPT or EMPTY_OR_FAILURE result resets the
# counter -- only a stuck run of LOCAL_ERROR indicates a misconfiguration
# rather than one-off flakiness.
_LOCAL_ERROR_DISABLE_THRESHOLD = 5


class VoiceWorker:
    def __init__(self, audio: AudioSource, backend: AsrBackend, router: ActionRouter) -> None:
        self._audio = audio
        self._backend = backend
        self._router = router
        self.disabled = False
        self._consecutive_local_errors = 0

    def record_and_dispatch(self, now: float) -> None:
        # `now` is accepted and unused -- kept for signature symmetry with
        # RavenSpokenFireSource.record_and_check(now), per the plan (both are
        # driven from the same host tick).
        if self.disabled:
            return
        try:
            self._audio.start()
            clip = self._audio.stop()
            result = self._backend.transcribe(clip)
            if result.status is AsrStatus.LOCAL_ERROR:
                self._consecutive_local_errors += 1
                if self._consecutive_local_errors >= _LOCAL_ERROR_DISABLE_THRESHOLD:
                    self.disabled = True
                return
            self._consecutive_local_errors = 0
            action = match_command(result)
            if action is not None:
                if action in _PULSE_ACTIONS:
                    self._router.pulse(action)
                else:
                    self._router.discrete(action)
        except Exception:
            self.disabled = True
