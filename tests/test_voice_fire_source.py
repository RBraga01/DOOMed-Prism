from __future__ import annotations

from pewpew.voice.asr import AsrResult, AsrStatus, FakeAsrBackend
from pewpew.voice.audio import FakeAudioSource
from pewpew.voice.fire_source import RavenSpokenFireSource


def test_pew_pew_transcript_sets_the_fire_edge() -> None:
    backend = FakeAsrBackend([AsrResult(AsrStatus.TRANSCRIPT, "pew pew")])
    audio = FakeAudioSource(recording=b"clip")
    source = RavenSpokenFireSource(backend, audio)

    source.record_and_check(0.0)

    assert source.spoken_fire_edge() is True
    assert audio.started is True
    assert audio.stopped is True
    assert backend.calls == [b"clip"]


def test_edge_clears_after_being_read_once() -> None:
    backend = FakeAsrBackend([AsrResult(AsrStatus.TRANSCRIPT, "pew pew")])
    source = RavenSpokenFireSource(backend, FakeAudioSource(b"clip"))
    source.record_and_check(0.0)
    assert source.spoken_fire_edge() is True
    assert source.spoken_fire_edge() is False


def test_other_transcripts_and_ambiguous_results_do_not_fire() -> None:
    for result in (
        AsrResult(AsrStatus.TRANSCRIPT, "next weapon"),
        AsrResult(AsrStatus.EMPTY_OR_FAILURE),
        AsrResult(AsrStatus.LOCAL_ERROR),
    ):
        backend = FakeAsrBackend([result])
        source = RavenSpokenFireSource(backend, FakeAudioSource(b"clip"))
        source.record_and_check(0.0)
        assert source.spoken_fire_edge() is False


def test_matching_is_case_and_whitespace_insensitive() -> None:
    backend = FakeAsrBackend([AsrResult(AsrStatus.TRANSCRIPT, "  Pew Pew  ")])
    source = RavenSpokenFireSource(backend, FakeAudioSource(b"clip"))
    source.record_and_check(0.0)
    assert source.spoken_fire_edge() is True


def test_repeated_pew_pew_within_the_cooldown_only_fires_once() -> None:
    backend = FakeAsrBackend([
        AsrResult(AsrStatus.TRANSCRIPT, "pew pew"),
        AsrResult(AsrStatus.TRANSCRIPT, "pew pew"),
    ])
    source = RavenSpokenFireSource(backend, FakeAudioSource(b"clip"), cooldown_s=1.0)
    source.record_and_check(0.0)
    assert source.spoken_fire_edge() is True
    source.record_and_check(0.5)  # still inside the 1.0s cooldown
    assert source.spoken_fire_edge() is False


def test_a_crash_in_the_audio_source_disables_fire_without_raising() -> None:
    # Important 4: RavenSpokenFireSource had no crash isolation -- unlike
    # VoiceWorker -- and .start() is the first call and the most likely
    # real-world failure point (e.g. RavenMicrophoneSource without Raven app
    # entitlement). FakeAudioSource never raises, so this is a raising
    # AudioSource, not just a raising backend.
    class _RaisingAudioSource:
        def start(self) -> None:
            raise RuntimeError("boom")

        def stop(self) -> bytes:
            raise AssertionError("stop() should not be reached")

    backend = FakeAsrBackend([AsrResult(AsrStatus.TRANSCRIPT, "pew pew")])
    source = RavenSpokenFireSource(backend, _RaisingAudioSource())

    source.record_and_check(0.0)  # must not raise

    assert source.disabled is True
    assert source.spoken_fire_edge() is False


def test_a_disabled_fire_source_does_not_report_a_stale_edge() -> None:
    # A crash after `self._edge` was already set to True by an earlier,
    # successful cycle must not leave spoken_fire_edge() reporting True once
    # disabled.
    class _RaisingBackend:
        def transcribe(self, wav_bytes: bytes):
            raise RuntimeError("boom")

    backend = FakeAsrBackend([AsrResult(AsrStatus.TRANSCRIPT, "pew pew")])
    source = RavenSpokenFireSource(backend, FakeAudioSource(b"clip"))
    source.record_and_check(0.0)
    assert source.spoken_fire_edge() is True  # sanity: fired normally first

    source._edge = True  # simulate a stale edge set before a later crash
    source._backend = _RaisingBackend()
    source.record_and_check(1.0)  # must not raise

    assert source.disabled is True
    assert source.spoken_fire_edge() is False


def test_pew_pew_fires_again_after_the_cooldown_elapses() -> None:
    backend = FakeAsrBackend([
        AsrResult(AsrStatus.TRANSCRIPT, "pew pew"),
        AsrResult(AsrStatus.TRANSCRIPT, "pew pew"),
    ])
    source = RavenSpokenFireSource(backend, FakeAudioSource(b"clip"), cooldown_s=1.0)
    source.record_and_check(0.0)
    assert source.spoken_fire_edge() is True
    source.record_and_check(2.0)  # past the 1.0s cooldown
    assert source.spoken_fire_edge() is True
