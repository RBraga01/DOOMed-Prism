"""The ASR backend seam: a tri-state result that never invents observability
the underlying transcription call doesn't give us. See spec R15's correction.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Protocol


class AsrStatus(enum.Enum):
    #: Non-empty transcribed text -- the only status downstream matching acts on.
    TRANSCRIPT = "transcript"
    #: The backend's own call collapsed silence, no-speech, and a real failure
    #: into this one ambiguous outcome. Never reported as a confirmed failure.
    EMPTY_OR_FAILURE = "empty_or_failure"
    #: Something this adapter itself observed directly (missing key, import
    #: failure, an exception outside the wrapped call). Never inferred from
    #: the backend returning an empty transcript.
    LOCAL_ERROR = "local_error"


@dataclass(frozen=True)
class AsrResult:
    status: AsrStatus
    text: str = ""


class AsrBackend(Protocol):
    def transcribe(self, wav_bytes: bytes) -> AsrResult: ...


class FakeAsrBackend:
    """Scripted responses for tests. No network, no raven_framework import."""

    def __init__(self, results: list[AsrResult] | None = None) -> None:
        self._results = list(results) if results else []
        self.calls: list[bytes] = []

    def transcribe(self, wav_bytes: bytes) -> AsrResult:
        self.calls.append(wav_bytes)
        if not self._results:
            return AsrResult(AsrStatus.EMPTY_OR_FAILURE)
        return self._results.pop(0)
