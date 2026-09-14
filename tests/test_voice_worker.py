from __future__ import annotations

from pewpew.input.actions import Action, ActionRouter
from pewpew.ipc.protocol import Message
from pewpew.voice.asr import AsrResult, AsrStatus, FakeAsrBackend
from pewpew.voice.audio import FakeAudioSource
from pewpew.voice.worker import VoiceWorker


def _router():
    sent: list[Message] = []
    return ActionRouter(sent.append), sent


def test_a_matched_command_is_dispatched_as_a_discrete_action() -> None:
    router, sent = _router()
    backend = FakeAsrBackend([AsrResult(AsrStatus.TRANSCRIPT, "weapon one")])
    worker = VoiceWorker(FakeAudioSource(b"clip"), backend, router)

    worker.record_and_dispatch(0.0)

    assert sent == [Message.discrete(int(Action.WEAPON_1))]


def test_an_unmatched_transcript_dispatches_nothing() -> None:
    router, sent = _router()
    backend = FakeAsrBackend([AsrResult(AsrStatus.TRANSCRIPT, "what time is it")])
    worker = VoiceWorker(FakeAudioSource(b"clip"), backend, router)

    worker.record_and_dispatch(0.0)

    assert sent == []


def test_empty_or_failure_dispatches_nothing() -> None:
    router, sent = _router()
    backend = FakeAsrBackend([AsrResult(AsrStatus.EMPTY_OR_FAILURE)])
    worker = VoiceWorker(FakeAudioSource(b"clip"), backend, router)

    worker.record_and_dispatch(0.0)

    assert sent == []


def test_a_crash_in_the_backend_disables_voice_without_raising() -> None:
    class _RaisingBackend:
        def transcribe(self, wav_bytes: bytes):
            raise RuntimeError("boom")

    router, sent = _router()
    worker = VoiceWorker(FakeAudioSource(b"clip"), _RaisingBackend(), router)

    worker.record_and_dispatch(0.0)  # must not raise

    assert worker.disabled is True
    assert sent == []


def test_a_disabled_worker_does_nothing_on_later_calls() -> None:
    router, sent = _router()
    backend = FakeAsrBackend([AsrResult(AsrStatus.TRANSCRIPT, "weapon one")])
    worker = VoiceWorker(FakeAudioSource(b"clip"), backend, router)
    worker.disabled = True

    worker.record_and_dispatch(0.0)

    assert sent == []
