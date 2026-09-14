# src/pewpew/voice/raven_backend.py
"""The preferred ASR integration: the Raven Framework's own OpenAiHelper.

Per spec R15's inspection findings, OpenAiHelper.transcribe_audio() is a
whole-clip, synchronous, cloud call that returns "" for silence, no-speech,
and a real API failure alike -- there is no way to tell those apart at that
interface. This adapter reports LOCAL_ERROR only for what it can observe
itself (a missing key, raven_framework being unavailable, or an exception
escaping the wrapped call); every case Raven's own function already
collapsed to "" is reported as EMPTY_OR_FAILURE, never as a confirmed
failure. See spec R15's correction -- this distinction is deliberate.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from pewpew.voice.asr import AsrResult, AsrStatus

_ENV_API_KEY = "DOOMED_PRISM_OPENAI_KEY"


def _default_helper_factory(api_key: str) -> Any:
    from raven_framework.helpers import OpenAiHelper  # lazy: optional dependency

    return OpenAiHelper(open_ai_key=api_key)


class RavenAiHelperBackend:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        helper_factory: Callable[[str], Any] = _default_helper_factory,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get(_ENV_API_KEY, "")
        self._helper_factory = helper_factory
        self._helper: Any = None
        self._unavailable = False
        if not self._api_key:
            self._unavailable = True
            return
        try:
            self._helper = self._helper_factory(self._api_key)
        except Exception:
            self._unavailable = True

    def transcribe(self, wav_bytes: bytes) -> AsrResult:
        if self._unavailable or self._helper is None:
            return AsrResult(AsrStatus.LOCAL_ERROR)
        try:
            text = self._helper.transcribe_audio(wav_bytes)
        except Exception:
            return AsrResult(AsrStatus.LOCAL_ERROR)
        if not text:
            return AsrResult(AsrStatus.EMPTY_OR_FAILURE)
        return AsrResult(AsrStatus.TRANSCRIPT, text)
