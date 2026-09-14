# tests/test_voice_raven_backend.py
from __future__ import annotations

import pytest

from pewpew.voice.asr import AsrStatus
from pewpew.voice.raven_backend import RavenAiHelperBackend


class _FakeHelper:
    def __init__(self, script: list[str]) -> None:
        self._script = list(script)

    def transcribe_audio(self, wav_bytes: bytes) -> str:
        return self._script.pop(0) if self._script else ""


class _RaisingHelper:
    def transcribe_audio(self, wav_bytes: bytes) -> str:
        raise RuntimeError("unexpected")


def test_missing_api_key_is_a_local_error_and_never_calls_the_factory() -> None:
    calls: list[str] = []
    backend = RavenAiHelperBackend(
        api_key="", helper_factory=lambda key: calls.append(key) or _FakeHelper([])
    )
    result = backend.transcribe(b"clip")
    assert result.status is AsrStatus.LOCAL_ERROR
    assert calls == []  # never attempted -- we already know there's no key


def test_helper_factory_import_failure_is_a_local_error() -> None:
    def _boom(key: str) -> object:
        raise ImportError("raven_framework not installed")

    backend = RavenAiHelperBackend(api_key="sk-test", helper_factory=_boom)
    assert backend.transcribe(b"clip").status is AsrStatus.LOCAL_ERROR


def test_non_empty_transcript_is_reported_as_transcript() -> None:
    backend = RavenAiHelperBackend(
        api_key="sk-test", helper_factory=lambda key: _FakeHelper(["next weapon"])
    )
    result = backend.transcribe(b"clip")
    assert result.status is AsrStatus.TRANSCRIPT
    assert result.text == "next weapon"


def test_empty_transcript_is_empty_or_failure_not_a_confirmed_failure() -> None:
    backend = RavenAiHelperBackend(
        api_key="sk-test", helper_factory=lambda key: _FakeHelper([""])
    )
    result = backend.transcribe(b"clip")
    assert result.status is AsrStatus.EMPTY_OR_FAILURE


def test_an_exception_from_the_wrapped_call_is_a_local_error() -> None:
    backend = RavenAiHelperBackend(
        api_key="sk-test", helper_factory=lambda key: _RaisingHelper()
    )
    result = backend.transcribe(b"clip")
    assert result.status is AsrStatus.LOCAL_ERROR


def test_default_api_key_comes_from_the_doomed_prism_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOOMED_PRISM_OPENAI_KEY", "sk-from-env")
    seen: list[str] = []
    backend = RavenAiHelperBackend(
        helper_factory=lambda key: seen.append(key) or _FakeHelper(["map"])
    )
    backend.transcribe(b"clip")
    assert seen == ["sk-from-env"]
