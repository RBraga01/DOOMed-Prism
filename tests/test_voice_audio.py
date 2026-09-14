from __future__ import annotations

from pewpew.voice.audio import FakeAudioSource, RavenMicrophoneSource


def test_fake_audio_source_records_start_and_stop_and_returns_the_clip() -> None:
    source = FakeAudioSource(recording=b"RIFF....WAVEfmt ")
    assert source.started is False
    source.start()
    assert source.started is True
    clip = source.stop()
    assert clip == b"RIFF....WAVEfmt "
    assert source.stopped is True


class _FakeMicrophone:
    def __init__(self) -> None:
        self.recording_started = False
        self.recording_stopped = False

    def start_recording(self):
        self.recording_started = True

    def stop_recording(self) -> bytes:
        self.recording_stopped = True
        return b"wav-bytes"


def test_raven_microphone_source_wraps_start_and_stop_recording() -> None:
    built: list[_FakeMicrophone] = []

    def factory(app_id: str, app_key: str) -> _FakeMicrophone:
        mic = _FakeMicrophone()
        built.append(mic)
        return mic

    source = RavenMicrophoneSource(microphone_factory=factory)
    source.start()
    clip = source.stop()
    assert built[0].recording_started is True
    assert built[0].recording_stopped is True
    assert clip == b"wav-bytes"


def test_raven_microphone_source_is_lazy_and_stop_before_start_is_silent() -> None:
    def factory(app_id: str, app_key: str):
        raise AssertionError("must not construct before start()")

    source = RavenMicrophoneSource(microphone_factory=factory)
    assert source.stop() == b""


def test_a_second_stop_without_an_intervening_start_is_silent() -> None:
    # Minor 4: "is recording" is now tracked explicitly rather than inferred
    # from `_microphone is None`, so a second stop() after a start/stop pair
    # returns b"" instead of calling stop_recording() again on an
    # already-stopped device.
    built: list[_FakeMicrophone] = []

    def factory(app_id: str, app_key: str) -> _FakeMicrophone:
        mic = _FakeMicrophone()
        built.append(mic)
        return mic

    source = RavenMicrophoneSource(microphone_factory=factory)
    source.start()
    first = source.stop()
    second = source.stop()

    assert first == b"wav-bytes"
    assert second == b""
