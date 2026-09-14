"""The audio-capture seam. RavenMicrophoneSource wraps the Raven Framework's
Microphone (Simulator/desktop Qt capture today; the real Prism microphone
once this app is Raven-entitled -- see spec R15's inspection findings)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class AudioSource(Protocol):
    def start(self) -> None: ...
    def stop(self) -> bytes: ...


class FakeAudioSource:
    def __init__(self, recording: bytes = b"") -> None:
        self._recording = recording
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> bytes:
        self.stopped = True
        return self._recording


def _default_microphone_factory(app_id: str, app_key: str) -> Any:
    from raven_framework.peripherals.microphone import Microphone  # lazy

    return Microphone(app_id=app_id, app_key=app_key)


class RavenMicrophoneSource:
    def __init__(
        self,
        *,
        app_id: str = "",
        app_key: str = "",
        microphone_factory: Callable[[str, str], Any] = _default_microphone_factory,
    ) -> None:
        self._app_id = app_id
        self._app_key = app_key
        self._microphone_factory = microphone_factory
        self._microphone: Any = None
        # Tracked explicitly rather than inferred from `self._microphone is
        # None` -- that would only protect the never-started case. Without
        # this flag, a second stop() with no intervening start() would call
        # stop_recording() again on an already-stopped device instead of
        # returning b"".
        self._is_recording = False

    def _ensure_microphone(self) -> Any:
        if self._microphone is None:
            self._microphone = self._microphone_factory(self._app_id, self._app_key)
        return self._microphone

    def start(self) -> None:
        self._ensure_microphone().start_recording()
        self._is_recording = True

    def stop(self) -> bytes:
        if not self._is_recording:
            return b""
        self._is_recording = False
        return self._microphone.stop_recording()
