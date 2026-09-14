"""Tests for the ASR result interface and FakeAsrBackend."""

from __future__ import annotations

from pewpew.voice.asr import AsrResult, AsrStatus, FakeAsrBackend


def test_asr_result_is_frozen_and_defaults_to_empty_text() -> None:
    result = AsrResult(AsrStatus.LOCAL_ERROR)
    assert result.status is AsrStatus.LOCAL_ERROR
    assert result.text == ""


def test_fake_backend_plays_back_scripted_results_in_order() -> None:
    backend = FakeAsrBackend([
        AsrResult(AsrStatus.TRANSCRIPT, "next weapon"),
        AsrResult(AsrStatus.EMPTY_OR_FAILURE),
    ])
    first = backend.transcribe(b"clip-one")
    second = backend.transcribe(b"clip-two")
    assert first == AsrResult(AsrStatus.TRANSCRIPT, "next weapon")
    assert second == AsrResult(AsrStatus.EMPTY_OR_FAILURE)
    assert backend.calls == [b"clip-one", b"clip-two"]


def test_fake_backend_defaults_to_empty_or_failure_once_exhausted() -> None:
    backend = FakeAsrBackend()
    assert backend.transcribe(b"clip") == AsrResult(AsrStatus.EMPTY_OR_FAILURE)
