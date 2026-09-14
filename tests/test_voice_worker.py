from __future__ import annotations

from pewpew.input.actions import Action, ActionRouter
from pewpew.ipc.protocol import Message
from pewpew.voice.asr import AsrResult, AsrStatus, FakeAsrBackend
from pewpew.voice.audio import FakeAudioSource
from pewpew.voice.worker import VoiceWorker


def _router():
    sent: list[Message] = []
    return ActionRouter(sent.append), sent


def test_a_matched_edge_consumed_command_is_dispatched_as_a_discrete_action() -> None:
    # PAUSE is edge-consumed on the C side (sendpause, never gamekeydown[]),
    # so an instantaneous MT_DISCRETE keydown+keyup pair is correct for it.
    router, sent = _router()
    backend = FakeAsrBackend([AsrResult(AsrStatus.TRANSCRIPT, "pause")])
    worker = VoiceWorker(FakeAudioSource(b"clip"), backend, router)

    worker.record_and_dispatch(0.0)

    assert sent == [Message.discrete(int(Action.PAUSE))]


def test_use_is_dispatched_via_pulse_not_discrete() -> None:
    # Critical 1: key_use is read from DOOM's gamekeydown[] in
    # G_BuildTiccmd -- a state-polled key -- so an instantaneous
    # MT_DISCRETE pair is silently erased before BuildTiccmd ever sees it.
    # It must go through MT_PULSE's hold mechanism instead.
    router, sent = _router()
    backend = FakeAsrBackend([AsrResult(AsrStatus.TRANSCRIPT, "use")])
    worker = VoiceWorker(FakeAudioSource(b"clip"), backend, router)

    worker.record_and_dispatch(0.0)

    assert sent == [Message.pulse(int(Action.USE))]


def test_a_weapon_switch_is_dispatched_via_pulse_not_discrete() -> None:
    # Critical 2: key_weaponN is likewise state-polled (gamekeydown[]), so
    # WEAPON_1..7 need the same MT_PULSE routing as USE.
    router, sent = _router()
    backend = FakeAsrBackend([AsrResult(AsrStatus.TRANSCRIPT, "weapon one")])
    worker = VoiceWorker(FakeAudioSource(b"clip"), backend, router)

    worker.record_and_dispatch(0.0)

    assert sent == [Message.pulse(int(Action.WEAPON_1))]


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


def test_n_consecutive_local_errors_disable_the_worker() -> None:
    # Important 3: a persistently misconfigured/broken backend (missing key,
    # raven_framework import failure) latches LOCAL_ERROR forever, which is
    # otherwise indistinguishable from a quiet room. N consecutive
    # LOCAL_ERROR cycles should disable the worker rather than no-op forever.
    router, sent = _router()
    from pewpew.voice.worker import _LOCAL_ERROR_DISABLE_THRESHOLD

    backend = FakeAsrBackend(
        [AsrResult(AsrStatus.LOCAL_ERROR)] * _LOCAL_ERROR_DISABLE_THRESHOLD
    )
    worker = VoiceWorker(FakeAudioSource(b"clip"), backend, router)

    for _ in range(_LOCAL_ERROR_DISABLE_THRESHOLD - 1):
        worker.record_and_dispatch(0.0)
        assert worker.disabled is False

    worker.record_and_dispatch(0.0)

    assert worker.disabled is True
    assert sent == []


def test_a_transcript_or_empty_or_failure_resets_the_local_error_counter() -> None:
    router, sent = _router()
    from pewpew.voice.worker import _LOCAL_ERROR_DISABLE_THRESHOLD

    # One fewer than the threshold, then a TRANSCRIPT that should reset the
    # counter, then the threshold minus one LOCAL_ERRORs again -- if the
    # counter weren't reset, this would disable the worker.
    results = (
        [AsrResult(AsrStatus.LOCAL_ERROR)] * (_LOCAL_ERROR_DISABLE_THRESHOLD - 1)
        + [AsrResult(AsrStatus.TRANSCRIPT, "what time is it")]
        + [AsrResult(AsrStatus.LOCAL_ERROR)] * (_LOCAL_ERROR_DISABLE_THRESHOLD - 1)
    )
    backend = FakeAsrBackend(results)
    worker = VoiceWorker(FakeAudioSource(b"clip"), backend, router)

    for _ in results:
        worker.record_and_dispatch(0.0)

    assert worker.disabled is False
    assert sent == []
