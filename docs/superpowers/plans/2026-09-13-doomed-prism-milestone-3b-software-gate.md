# Milestone 3b Software Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Milestone 3b's *software* decision gate — a closed voice command
grammar and a real "pew pew" fire path, both backed by the Raven Framework's
existing `OpenAiHelper` ASR function, fully testable with fakes and the
Simulator microphone, with zero changes to `ActionRouter`'s public interface.

**Architecture:** A new `pewpew.voice` package mirrors `pewpew.input`'s shape:
an `AsrBackend` protocol behind a tri-state `AsrResult` (never inventing a
distinction Raven's own `""`-collapsing return doesn't give us), an
`AudioSource` protocol wrapping the Raven Framework's `Microphone`, a closed
`CommandGrammar` matcher, and two independent consumers of that seam: a
`VoiceWorker` that dispatches matched commands into the unmodified
`ActionRouter`, and a `RavenSpokenFireSource` implementing 3a's existing
`SpokenFireSource` protocol that plugs into `InputPipeline`'s existing
`spoken_fire` parameter — so "pew pew" flows through 3a's already-debounced
fire-fusion path instead of a second, competing one. `raven_framework` is
always imported lazily so the package — and every test — never requires it
installed.

**Tech Stack:** Python 3.10+, stdlib only for the new package's core logic;
`raven_framework` (Raven Framework, local dev install only, never a hard
dependency) for the two Raven-backed adapters.

**Spec:** `docs/superpowers/specs/2026-09-05-doomed-prism-milestone-3-design.md`,
ruling **R15** (read in full — supersedes R1's "offline voice" framing; builds
on R6's normalized action set, R7's `SpokenFireSource` split, R12's scope
boundary, and R13's `pew pew` keyword rename).

## Global Constraints

- **Publication safety first.** No audio, model, or calibration file is ever
  committed. Task 1 extends `scripts/check_publication_safety.py` and
  `.gitignore` *before* any other task lands code that could produce such a
  file locally.
- **No credentials committed.** The OpenAI key Raven's `OpenAiHelper` needs is
  supplied only via the environment variable `DOOMED_PRISM_OPENAI_KEY`,
  following the existing `DOOMED_PRISM_*` convention
  (`src/pewpew/config.py`). Never a literal, never a default value.
- **`raven_framework` stays optional.** Every module that imports it does so
  lazily, inside a function or `__init__`, wrapped so `ImportError` is a
  normal, handled outcome — not at module import time. `pytest` must never
  require `raven_framework`, a network connection, or a real microphone.
- **The tri-state ambiguity is load-bearing (R15 correction).**
  `AsrStatus.EMPTY_OR_FAILURE` is never reported as a confirmed failure, and
  `AsrStatus.LOCAL_ERROR` is never inferred from Raven's `""` return — only
  from something DOOMed Prism's own adapter can observe directly (missing
  key, `raven_framework` import failure, an exception outside the wrapped
  call). No downstream code may re-collapse this distinction.
- **`ActionRouter` and `pipeline.py`'s consumer side are unmodified.** Voice
  feeds `Action`s into `ActionRouter` exactly as gaze and click already do;
  this plan touches `pewpew.input.actions.Action` only to add new enum
  members, never the router's methods.
- **A crashed voice worker disables voice only** — click, blink/gaze, and
  Enter/P pause keep working (mirrors the existing crash-isolation shape in
  `src/pewpew/host_widget.py`).
- **This plan's scope is the software gate only.** The hardware/performance
  gate (real Prism microphone entitlement, measured Raven ASR latency and
  command accuracy, "pew pew" false-positive/negative rate, CPU/RAM/thermal,
  and the dedicated-fire-detector decision) is out of scope, cannot be closed
  from this environment, and is recorded as explicitly open in
  `docs/validation/milestone-3b-result.md` — not implied closed by this plan.

---

### Task 1: Publication safety — audio/model file suffixes and credential literal

**Files:**
- Modify: `scripts/check_publication_safety.py`
- Modify: `.gitignore`
- Test: `tests/test_publication_safety.py`

**Interfaces:**
- Consumes: nothing from later tasks.
- Produces: `FORBIDDEN_SUFFIXES` extended; `CREDENTIAL_LITERAL` extended to
  also catch `openai_key` / `open_ai_key` literals, so a future accidental
  hardcoded key is caught the same way `app_key` / `app_id` already are.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_publication_safety.py -- add these two cases to the existing file
def test_audio_and_model_suffixes_are_forbidden_tracked_files() -> None:
    from scripts.check_publication_safety import path_violation
    from pathlib import PurePosixPath

    for name in (
        "sample.wav", "sample.flac", "sample.ogg", "sample.mp3", "sample.opus",
        "raw.raw", "raw.pcm", "model.tflite", "model.onnx", "model.pt",
        "model.pb", "model.pbmm", "model.scorer", "model.gguf",
    ):
        assert path_violation(PurePosixPath(f"pewpew/voice/{name}")) is not None


def test_openai_key_literal_is_a_credential_violation() -> None:
    from scripts.check_publication_safety import credential_violations

    assert credential_violations('openai_' + 'key = "sk-not-a-real-key-but-nonempty"')
    assert credential_violations("open_ai_" + "key: 'also-nonempty'")
    assert not credential_violations('openai_key = ""')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_publication_safety.py -k "audio_and_model_suffixes or openai_key_literal" -v`
Expected: FAIL — `.wav`/`.tflite`/etc. are not in `FORBIDDEN_SUFFIXES` yet, and
`credential_violations` doesn't match `openai_key`/`open_ai_key` yet.

- [ ] **Step 3: Extend `FORBIDDEN_SUFFIXES` and `CREDENTIAL_LITERAL`**

In `scripts/check_publication_safety.py`, replace the existing constants:

```python
FORBIDDEN_SUFFIXES = (
    ".wad", ".pk3", ".exe", ".dll", ".so",
    # Audio and acoustic-model files: Milestone 3b's speech engine and any
    # model it depends on are fetched or supplied locally, like the IWAD --
    # never committed. See spec R15 / the M3 design §9 licence review.
    ".wav", ".flac", ".ogg", ".mp3", ".opus", ".raw", ".pcm",
    ".tflite", ".onnx", ".pt", ".pb", ".pbmm", ".scorer", ".gguf",
)
FORBIDDEN_NAMES = {".env", "app_key"}
CREDENTIAL_LITERAL = re.compile(
    r"(?:\b(?P<bare_name>app_key|app_id|openai_key|open_ai_key)\b|"
    r"[\"'](?P<quoted_name>app_key|app_id|openai_key|open_ai_key)[\"'])"
    r"\s*(?:=|:)\s*(?:\(\s*)*"
    r"(?:[rRuUbBfF]{0,3})?"
    r'(?:"""(?P<triple_double>.+?)"""|'
    r"'''(?P<triple_single>.+?)'''|"
    r'"(?P<single_double>(?:\\.|[^"\\\r\n])+?)"|'
    r"'(?P<single_single>(?:\\.|[^'\\\r\n])+?)')",
    re.DOTALL,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_publication_safety.py -v`
Expected: PASS — including the two new cases and every pre-existing case in
this file.

- [ ] **Step 5: Extend `.gitignore`**

Append to `.gitignore`:

```
models/
calibration/
*.wav
*.flac
*.ogg
*.mp3
*.opus
*.raw
*.pcm
*.tflite
*.onnx
*.pt
*.pb
*.pbmm
*.scorer
*.gguf
```

- [ ] **Step 6: Run the full suite and both publication-safety scans**

Run: `python -m pytest -q && python scripts/check_publication_safety.py --root . && python scripts/check_publication_safety.py --root . --history`
Expected: all pass, both scans exit 0.

- [ ] **Step 7: Commit**

```bash
git add scripts/check_publication_safety.py .gitignore tests/test_publication_safety.py
git commit -m "feat(publication-safety): forbid audio/model suffixes and openai key literals

Milestone 3b's speech backend and any model it needs are fetched or
supplied locally, like the IWAD -- never committed. Extends the existing
credential-literal scanner to also catch an accidentally hardcoded OpenAI
key, the same way app_key/app_id already are."
```

---

### Task 2: `pewpew.voice.asr` — the tri-state ASR result and backend protocol

**Files:**
- Create: `src/pewpew/voice/__init__.py`
- Create: `src/pewpew/voice/asr.py`
- Test: `tests/test_voice_asr.py`

**Interfaces:**
- Consumes: nothing.
- Produces (for every later task):
  - `AsrStatus` enum: `TRANSCRIPT`, `EMPTY_OR_FAILURE`, `LOCAL_ERROR`.
  - `AsrResult` frozen dataclass: `status: AsrStatus`, `text: str = ""`.
  - `AsrBackend` Protocol: `transcribe(self, wav_bytes: bytes) -> AsrResult`.
  - `FakeAsrBackend(results: list[AsrResult] | None = None)`: `.transcribe()`
    pops scripted results in order (defaulting to `EMPTY_OR_FAILURE` once
    exhausted); `.calls: list[bytes]` records every `wav_bytes` it was given.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_voice_asr.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_voice_asr.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pewpew.voice'`.

- [ ] **Step 3: Write the implementation**

```python
# src/pewpew/voice/__init__.py
"""Voice input for DOOMed Prism: ASR backends, the closed command grammar,
and the real "pew pew" fire path. See spec ruling R15."""
```

```python
# src/pewpew/voice/asr.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_voice_asr.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/voice/__init__.py src/pewpew/voice/asr.py tests/test_voice_asr.py
git commit -m "feat(voice): AsrResult/AsrStatus tri-state and the AsrBackend protocol"
```

---

### Task 3: `RavenAiHelperBackend` — the real, preferred ASR adapter

**Files:**
- Create: `src/pewpew/voice/raven_backend.py`
- Test: `tests/test_voice_raven_backend.py`

**Interfaces:**
- Consumes: `AsrBackend`, `AsrResult`, `AsrStatus` from Task 2.
- Produces: `RavenAiHelperBackend(*, api_key: str | None = None,
  helper_factory: Callable[[str], object] | None = None)` implementing
  `AsrBackend`. `helper_factory` is the test seam (default: lazily imports
  `raven_framework.helpers.OpenAiHelper` and constructs
  `OpenAiHelper(open_ai_key=api_key)`).

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_voice_raven_backend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pewpew.voice.raven_backend'`.

- [ ] **Step 3: Write the implementation**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_voice_raven_backend.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass; no new skips (this module needs no `raven_framework`
install to test).

- [ ] **Step 6: Commit**

```bash
git add src/pewpew/voice/raven_backend.py tests/test_voice_raven_backend.py
git commit -m "feat(voice): RavenAiHelperBackend, the preferred ASR adapter

Lazily imports raven_framework.helpers.OpenAiHelper. Reports LOCAL_ERROR
only for what this adapter observes directly (missing DOOMED_PRISM_OPENAI_KEY,
import/construction failure, an exception outside the wrapped call);
everything Raven's own transcribe_audio() already collapsed to \"\" is
EMPTY_OR_FAILURE, never a confirmed failure."
```

---

### Task 4: `pewpew.voice.audio` — the audio-capture seam

**Files:**
- Create: `src/pewpew/voice/audio.py`
- Test: `tests/test_voice_audio.py`

**Interfaces:**
- Consumes: nothing from earlier voice tasks.
- Produces: `AudioSource` Protocol (`start(self) -> None`,
  `stop(self) -> bytes`); `FakeAudioSource(recording: bytes = b"")`;
  `RavenMicrophoneSource(*, app_id: str = "", app_key: str = "",
  microphone_factory: Callable[[str, str], object] | None = None)`
  implementing `AudioSource` by lazily wrapping
  `raven_framework.peripherals.microphone.Microphone`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_voice_audio.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_voice_audio.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pewpew.voice.audio'`.

- [ ] **Step 3: Write the implementation**

```python
# src/pewpew/voice/audio.py
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

    def _ensure_microphone(self) -> Any:
        if self._microphone is None:
            self._microphone = self._microphone_factory(self._app_id, self._app_key)
        return self._microphone

    def start(self) -> None:
        self._ensure_microphone().start_recording()

    def stop(self) -> bytes:
        if self._microphone is None:
            return b""
        return self._microphone.stop_recording()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_voice_audio.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/voice/audio.py tests/test_voice_audio.py
git commit -m "feat(voice): AudioSource protocol and RavenMicrophoneSource"
```

---

### Task 5: New discrete `Action`s and `CommandGrammar`

**Files:**
- Modify: `src/pewpew/input/actions.py`
- Create: `src/pewpew/voice/grammar.py`
- Test: `tests/test_input_actions.py` (extend)
- Test: `tests/test_voice_grammar.py`

**Interfaces:**
- Consumes: `AsrResult`, `AsrStatus` from Task 2.
- Produces: new `Action` members (below); `match_command(result: AsrResult)
  -> Action | None` in `pewpew.voice.grammar`.

**New `Action` members.** Values continue after the existing `PAUSE = 20`.
Weapon-select and menu-confirm/cancel/up/down map to a single existing
Crispy Doom key each (confirmed in the vendored source,
`build/crispy/src/m_controls.c`), following exactly the pattern
`AC_PAUSE` already uses in `patches/crispy-doom-ipc-input.diff` (one
`ev_keydown` + `ev_keyup` pair). `NEXT_WEAPON`/`PREV_WEAPON` (Crispy's
`key_nextweapon`/`key_prevweapon` default to *unbound*, value `0`) and
`AUTOMAP`/`SAVE_GAME`/`LOAD_GAME`/`EXIT_DOOM` (each needs a menu-state-aware
key *sequence*, not one keydown/keyup pair — save/load/quit only respond
while the corresponding menu screen is already showing) need real per-key
engineering this plan does not have verified, real code for. They are
**reserved as `Action` values now** (so `CommandGrammar` and
`VoiceWorker` are written once against the final action set) but **not**
wired into the C patch or the phrase table in this task — a follow-up scoped
to that specific keybinding/menu-sequencing work does it once verified
against a running engine, not guessed here.

```python
class Action(enum.IntEnum):
    MOVE_FORWARD = 1
    MOVE_BACKWARD = 2
    TURN_LEFT = 3
    TURN_RIGHT = 4
    FIRE = 10
    USE = 11
    PAUSE = 20
    WEAPON_1 = 30
    WEAPON_2 = 31
    WEAPON_3 = 32
    WEAPON_4 = 33
    WEAPON_5 = 34
    WEAPON_6 = 35
    WEAPON_7 = 36
    MENU_CONFIRM = 37
    MENU_CANCEL = 38
    MENU_UP = 39
    MENU_DOWN = 40
    # Reserved (R15 task 5): not yet wired into the C patch -- see the note
    # above. Defined now so pewpew.voice is written once against the final
    # action set.
    NEXT_WEAPON = 41
    PREV_WEAPON = 42
    AUTOMAP = 43
    SAVE_GAME = 44
    LOAD_GAME = 45
    EXIT_DOOM = 46
```

`CommandGrammar`'s phrase table below covers only the codes wired in this
task (`WEAPON_1..7`, `MENU_CONFIRM/CANCEL/UP/DOWN`) plus `USE` (already
wired since 3a) and `PAUSE` (already wired since 3a) — voice can already
pause/resume and select weapons end-to-end. `map`/`save game`/`load
game`/`exit Doom`/`next weapon`/`previous weapon` phrases are added in the
follow-up that wires their C-side codes, not here (adding an unreachable
phrase now would silently do nothing when matched, which is worse than not
matching it yet).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_input_actions.py -- add to the existing file
def test_new_discrete_action_codes_match_the_spec_r15_values() -> None:
    assert (Action.WEAPON_1, Action.WEAPON_2, Action.WEAPON_3) == (30, 31, 32)
    assert (Action.WEAPON_4, Action.WEAPON_5, Action.WEAPON_6, Action.WEAPON_7) == (33, 34, 35, 36)
    assert (Action.MENU_CONFIRM, Action.MENU_CANCEL, Action.MENU_UP, Action.MENU_DOWN) == (37, 38, 39, 40)
    assert (Action.NEXT_WEAPON, Action.PREV_WEAPON) == (41, 42)
    assert (Action.AUTOMAP, Action.SAVE_GAME, Action.LOAD_GAME, Action.EXIT_DOOM) == (43, 44, 45, 46)
```

```python
# tests/test_voice_grammar.py
from __future__ import annotations

from pewpew.input.actions import Action
from pewpew.voice.asr import AsrResult, AsrStatus
from pewpew.voice.grammar import match_command


def test_matches_each_wired_phrase_to_its_action() -> None:
    cases = {
        "use": Action.USE,
        "open": Action.USE,
        "weapon one": Action.WEAPON_1,
        "weapon seven": Action.WEAPON_7,
        "pause": Action.PAUSE,
        "resume": Action.PAUSE,
        "menu up": Action.MENU_UP,
        "menu down": Action.MENU_DOWN,
        "confirm": Action.MENU_CONFIRM,
        "cancel": Action.MENU_CANCEL,
    }
    for phrase, action in cases.items():
        result = AsrResult(AsrStatus.TRANSCRIPT, phrase)
        assert match_command(result) is action


def test_matching_is_case_and_whitespace_insensitive() -> None:
    result = AsrResult(AsrStatus.TRANSCRIPT, "  Weapon One  ")
    assert match_command(result) is Action.WEAPON_1


def test_unrecognized_transcript_matches_nothing() -> None:
    result = AsrResult(AsrStatus.TRANSCRIPT, "what time is it")
    assert match_command(result) is None


def test_empty_or_failure_and_local_error_both_match_nothing_but_are_not_the_same_input() -> None:
    empty_or_failure = AsrResult(AsrStatus.EMPTY_OR_FAILURE)
    local_error = AsrResult(AsrStatus.LOCAL_ERROR)
    # Two genuinely different inputs, asserted separately, so a future change
    # that special-cases one without the other is caught here -- not merged
    # into one assertion that would hide that distinction.
    assert match_command(empty_or_failure) is None
    assert match_command(local_error) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_input_actions.py::test_new_discrete_action_codes_match_the_spec_r15_values tests/test_voice_grammar.py -v`
Expected: FAIL — `Action.WEAPON_1` doesn't exist yet;
`ModuleNotFoundError: No module named 'pewpew.voice.grammar'`.

- [ ] **Step 3: Add the new `Action` members**

In `src/pewpew/input/actions.py`, replace the `Action` class body with the
full member list shown above (keep `MOVE_FORWARD` through `PAUSE`
unchanged; append `WEAPON_1` through `EXIT_DOOM`).

- [ ] **Step 4: Write `pewpew.voice.grammar`**

```python
# src/pewpew/voice/grammar.py
"""The closed voice command grammar (spec R15 / M3 design §2's "In scope"
list). Matches only AsrStatus.TRANSCRIPT text -- EMPTY_OR_FAILURE and
LOCAL_ERROR both resolve to "no command", but as two distinct inputs, never
merged into a single "not a transcript" branch, so a later change to one
cannot silently change the other (spec R15's ambiguity-preservation rule).
"""

from __future__ import annotations

from pewpew.input.actions import Action
from pewpew.voice.asr import AsrResult, AsrStatus

# Only phrases whose Action is actually wired into the C patch (task 5) are
# listed here. An unreachable phrase would match and then silently do
# nothing, which is worse than not recognizing it yet.
_PHRASES: dict[str, Action] = {
    "use": Action.USE,
    "open": Action.USE,
    "weapon one": Action.WEAPON_1,
    "weapon two": Action.WEAPON_2,
    "weapon three": Action.WEAPON_3,
    "weapon four": Action.WEAPON_4,
    "weapon five": Action.WEAPON_5,
    "weapon six": Action.WEAPON_6,
    "weapon seven": Action.WEAPON_7,
    "pause": Action.PAUSE,
    "resume": Action.PAUSE,
    "menu up": Action.MENU_UP,
    "menu down": Action.MENU_DOWN,
    "confirm": Action.MENU_CONFIRM,
    "cancel": Action.MENU_CANCEL,
}


def match_command(result: AsrResult) -> Action | None:
    if result.status is not AsrStatus.TRANSCRIPT:
        return None
    return _PHRASES.get(result.text.strip().lower())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_input_actions.py tests/test_voice_grammar.py -v`
Expected: PASS, all cases including the pre-existing `test_input_actions.py`
suite.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/pewpew/input/actions.py src/pewpew/voice/grammar.py tests/test_input_actions.py tests/test_voice_grammar.py
git commit -m "feat(voice): closed command grammar and the new discrete Action codes

WEAPON_1..7 and MENU_CONFIRM/CANCEL/UP/DOWN are defined and phrase-matched.
NEXT_WEAPON, PREV_WEAPON, AUTOMAP, SAVE_GAME, LOAD_GAME, EXIT_DOOM are
reserved Action values only -- their C-side keybinding/menu-sequencing is
real engineering this task doesn't have verified code for yet (see the task
note), so no phrase maps to them until a follow-up wires them for real."
```

---

### Task 6: Wire `WEAPON_1..7` and `MENU_CONFIRM/CANCEL/UP/DOWN` into the C patch

**Files:**
- Modify: `patches/crispy-doom-ipc-input.diff`
- Modify: `tests/test_distribution_metadata.py`

**Interfaces:**
- Consumes: the `Action` values from Task 5.
- Produces: `AC_WEAPON_1..7`, `AC_MENU_CONFIRM`, `AC_MENU_CANCEL`,
  `AC_MENU_UP`, `AC_MENU_DOWN` `#define`s and their `MT_DISCRETE` dispatch,
  matching the existing `AC_PAUSE` pattern exactly.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_distribution_metadata.py -- add to test_c_patch_constants_match_the_python_enums
    assert defs["AC_WEAPON_1"] == Action.WEAPON_1
    assert defs["AC_WEAPON_2"] == Action.WEAPON_2
    assert defs["AC_WEAPON_3"] == Action.WEAPON_3
    assert defs["AC_WEAPON_4"] == Action.WEAPON_4
    assert defs["AC_WEAPON_5"] == Action.WEAPON_5
    assert defs["AC_WEAPON_6"] == Action.WEAPON_6
    assert defs["AC_WEAPON_7"] == Action.WEAPON_7
    assert defs["AC_MENU_CONFIRM"] == Action.MENU_CONFIRM
    assert defs["AC_MENU_CANCEL"] == Action.MENU_CANCEL
    assert defs["AC_MENU_UP"] == Action.MENU_UP
    assert defs["AC_MENU_DOWN"] == Action.MENU_DOWN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_distribution_metadata.py::test_c_patch_constants_match_the_python_enums -v`
Expected: FAIL — `KeyError: 'AC_WEAPON_1'`.

- [ ] **Step 3: Extend the C patch**

In `patches/crispy-doom-ipc-input.diff`, in the block of `#define AC_*`
constants (immediately after `+#define AC_PAUSE 20`), add:

```diff
+#define AC_WEAPON_1 30
+#define AC_WEAPON_2 31
+#define AC_WEAPON_3 32
+#define AC_WEAPON_4 33
+#define AC_WEAPON_5 34
+#define AC_WEAPON_6 35
+#define AC_WEAPON_7 36
+#define AC_MENU_CONFIRM 37
+#define AC_MENU_CANCEL 38
+#define AC_MENU_UP 39
+#define AC_MENU_DOWN 40
```

In the `MT_DISCRETE` case (immediately after the existing
`if (code == AC_PAUSE) { ipc_post_key(ev_keydown, key_pause); ipc_post_key(ev_keyup, key_pause); }`
line), add the matching dispatch, following the exact same
keydown/keyup-pair shape:

```diff
+            else if (code == AC_WEAPON_1)
+            { ipc_post_key(ev_keydown, key_weapon1); ipc_post_key(ev_keyup, key_weapon1); }
+            else if (code == AC_WEAPON_2)
+            { ipc_post_key(ev_keydown, key_weapon2); ipc_post_key(ev_keyup, key_weapon2); }
+            else if (code == AC_WEAPON_3)
+            { ipc_post_key(ev_keydown, key_weapon3); ipc_post_key(ev_keyup, key_weapon3); }
+            else if (code == AC_WEAPON_4)
+            { ipc_post_key(ev_keydown, key_weapon4); ipc_post_key(ev_keyup, key_weapon4); }
+            else if (code == AC_WEAPON_5)
+            { ipc_post_key(ev_keydown, key_weapon5); ipc_post_key(ev_keyup, key_weapon5); }
+            else if (code == AC_WEAPON_6)
+            { ipc_post_key(ev_keydown, key_weapon6); ipc_post_key(ev_keyup, key_weapon6); }
+            else if (code == AC_WEAPON_7)
+            { ipc_post_key(ev_keydown, key_weapon7); ipc_post_key(ev_keyup, key_weapon7); }
+            else if (code == AC_MENU_CONFIRM)
+            { ipc_post_key(ev_keydown, key_menu_forward); ipc_post_key(ev_keyup, key_menu_forward); }
+            else if (code == AC_MENU_CANCEL)
+            { ipc_post_key(ev_keydown, key_menu_back); ipc_post_key(ev_keyup, key_menu_back); }
+            else if (code == AC_MENU_UP)
+            { ipc_post_key(ev_keydown, key_menu_up); ipc_post_key(ev_keyup, key_menu_up); }
+            else if (code == AC_MENU_DOWN)
+            { ipc_post_key(ev_keydown, key_menu_down); ipc_post_key(ev_keyup, key_menu_down); }
```

`key_weapon1`..`key_weapon7`, `key_menu_forward`, `key_menu_back`,
`key_menu_up`, `key_menu_down` are Crispy Doom's own existing globals
(`src/m_controls.c`, already `extern`-visible to `g_game.c`/`d_loop.c`
where this patch's dispatch lives — confirm the exact `#include` needed by
checking what the file already includes near the existing `key_pause`
reference) — this mirrors `AC_PAUSE`'s use of `key_pause` exactly, no new
mechanism.

- [ ] **Step 4: Rebuild and verify the patch still applies cleanly**

Run: `python scripts/build_crispy.py --check`
Expected: exit 0 (restore + real patch 1 apply + `--check` patch 2).

- [ ] **Step 5: Rebuild for real and smoke-test one new code manually**

Run: `python scripts/build_crispy.py`, then launch the built engine with
`DOOMED_PRISM_IPC_ADDR` set and send an `AC_WEAPON_2` discrete frame from a
short script (mirror `scripts/ci_ipc_smoke.py`'s `Message.discrete(...)`
usage) — confirm the player's weapon actually switches to weapon 2 in the
composited output before proceeding. This is real hardware-independent
verification (Simulator/Linux CI runner both suffice) that the key mapping
is correct, not just that the patch text parses.

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_distribution_metadata.py -v`
Expected: PASS, including the pre-existing constant-sync assertions.

- [ ] **Step 7: Run the full suite and both publication-safety scans**

Run: `python -m pytest -q && python scripts/check_publication_safety.py --root . && python scripts/check_publication_safety.py --root . --history`
Expected: all pass, both scans exit 0.

- [ ] **Step 8: Commit**

```bash
git add patches/crispy-doom-ipc-input.diff tests/test_distribution_metadata.py
git commit -m "feat(engine): wire WEAPON_1..7 and MENU_CONFIRM/CANCEL/UP/DOWN discrete actions

Same AC_PAUSE keydown/keyup-pair mechanism, using Crispy's own existing
key_weapon1..7 / key_menu_forward / key_menu_back / key_menu_up /
key_menu_down globals. Verified against a running engine, not just parsed."
```

---

### Task 7: `RavenSpokenFireSource` — "pew pew" over the general ASR path

**Files:**
- Create: `src/pewpew/voice/fire_source.py`
- Test: `tests/test_voice_fire_source.py`

**Interfaces:**
- Consumes: `AsrBackend`, `AsrResult`, `AsrStatus` from Task 2;
  `pewpew.input.fire.SpokenFireSource` protocol (already exists, 3a).
- Produces: `RavenSpokenFireSource(backend: AsrBackend, audio: AudioSource, *,
  cooldown_s: float = 1.0)` implementing `spoken_fire_edge() -> bool`.
  `record_and_check(now: float) -> None` runs one capture+transcribe+match
  cycle — `now` is passed in explicitly by
  the caller for the cooldown check, the same "time as a parameter, never
  self-queried" shape `ActionRouter`/`InputPipeline.tick` already use, so
  there is no separate clock to inject or mock. `spoken_fire_edge()` reports
  and clears the edge, exactly like `SimulatorInputSource.sample()`'s edge
  fields do. (`start()` immediately followed by `stop()` in one call is a
  software-gate simplification — real recording-duration timing, e.g. a
  push-to-talk trigger or silence detection deciding *when* to call this
  method, is a hardware/performance-gate concern; `FakeAudioSource` doesn't
  need real elapsed time to prove the plumbing below it is correct.)

**Backend-independence (R15).** This is a first, correctness-oriented
implementation that reuses `RavenAiHelperBackend` to unblock end-to-end
testing now. The class takes `backend: AsrBackend` as a constructor
argument — nothing here is Raven-specific beyond the object it's handed, so
a future dedicated low-latency detector (a plain `AsrBackend`-shaped or even
entirely different implementation) is a swap at the call site that
constructs this class, not a change to this file.

**Integration point: `InputPipeline`, not `VoiceWorker` (important).**
`RavenSpokenFireSource` implements 3a's existing `SpokenFireSource` protocol
exactly (`spoken_fire_edge() -> bool`, nothing more) so it plugs into
`InputPipeline`'s already-existing constructor parameter —
`InputPipeline(source, send, spoken_fire=RavenSpokenFireSource(...))` — with
**zero changes to `pipeline.py`**. `InputPipeline.tick()` already polls
`spoken_fire_edge()` every tick and routes it through the existing debounced
`FireArbiter` (`src/pewpew/input/fire.py`), the same fusion path a click or
the `B` debug key already uses. `VoiceWorker` (Task 8) must **not** also
pulse `Action.FIRE` — routing fire through two places would let a click and
a spoken "pew pew" close together double-fire instead of fusing into the one
shot `FireArbiter` exists to guarantee. `VoiceWorker` owns the command
grammar only; fire is `InputPipeline`'s job, unchanged since 3a.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_voice_fire_source.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_voice_fire_source.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pewpew.voice.fire_source'`.

- [ ] **Step 3: Write the implementation**

```python
# src/pewpew/voice/fire_source.py
"""The "pew pew" fire path (spec R13's keyword, R7's SpokenFireSource
protocol). Backed by an AsrBackend today (spec R15) -- nothing here is
Raven-specific beyond the backend object it's handed, so a future dedicated
low-latency detector is a swap at the call site, not a change to this class.
"""

from __future__ import annotations

from pewpew.voice.asr import AsrBackend, AsrStatus
from pewpew.voice.audio import AudioSource

_PEW_PEW = "pew pew"


class RavenSpokenFireSource:
    def __init__(
        self,
        backend: AsrBackend,
        audio: AudioSource,
        *,
        cooldown_s: float = 1.0,
    ) -> None:
        self._backend = backend
        self._audio = audio
        self._cooldown_s = cooldown_s
        self._edge = False
        self._last_fire: float | None = None

    def record_and_check(self, now: float) -> None:
        self._audio.start()
        clip = self._audio.stop()
        result = self._backend.transcribe(clip)
        if result.status is not AsrStatus.TRANSCRIPT:
            return
        if result.text.strip().lower() != _PEW_PEW:
            return
        if self._last_fire is not None and now - self._last_fire < self._cooldown_s:
            return
        self._last_fire = now
        self._edge = True

    def spoken_fire_edge(self) -> bool:
        edge = self._edge
        self._edge = False
        return edge
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_voice_fire_source.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/voice/fire_source.py tests/test_voice_fire_source.py
git commit -m "feat(voice): RavenSpokenFireSource -- pew pew over the general ASR path

Implements 3a's existing SpokenFireSource protocol. Takes an AsrBackend at
construction so a future dedicated low-latency detector is a call-site
swap, not a change to this class (spec R15)."
```

---

### Task 8: `VoiceWorker` — crash-isolated integration into `ActionRouter`

**Files:**
- Create: `src/pewpew/voice/worker.py`
- Test: `tests/test_voice_worker.py`

**Interfaces:**
- Consumes: `AudioSource` (Task 4), `AsrBackend`/`AsrResult`/`AsrStatus`
  (Task 2/3), `match_command` (Task 5), `pewpew.input.actions.ActionRouter`
  (existing, unmodified).
- Produces: `VoiceWorker(audio: AudioSource, backend: AsrBackend, router:
  ActionRouter)`. `.record_and_dispatch(now: float) -> None` runs one full
  command cycle: records a clip, transcribes it, matches it against the
  closed grammar, and discretely dispatches the resulting `Action` through
  `router.discrete(...)` — wrapped so any exception disables voice (sets
  `.disabled = True`) without propagating, leaving `router` and every other
  input path untouched. `now` is accepted for signature symmetry with
  `RavenSpokenFireSource.record_and_check(now)` and future use (e.g. a
  future cooldown on repeated commands); this task does not yet use it.

**Fire is deliberately not this class's job.** `VoiceWorker` only ever calls
`router.discrete(...)` for matched grammar commands. "pew pew" goes through
`RavenSpokenFireSource` (Task 7) plugged into `InputPipeline`'s existing
`spoken_fire` parameter, so it flows through the same debounced `FireArbiter`
a click or the `B` debug key already uses — see Task 7's integration note.
Two independent recording cycles (this worker's slower command-grammar loop,
and `RavenSpokenFireSource`'s own) is correct here, not a duplication: they
serve different consumers with different debounce needs, exactly why 3a's
R7 split fire out from general input handling in the first place.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_voice_worker.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_voice_worker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pewpew.voice.worker'`.

- [ ] **Step 3: Write the implementation**

```python
# src/pewpew/voice/worker.py
"""Owns the audio/backend/grammar cycle and feeds Action into the existing,
unmodified ActionRouter. A crash anywhere in this cycle disables voice only
-- click, gaze, and Enter/P pause are never touched (mirrors the
crash-isolation shape in src/pewpew/host_widget.py). Fire is deliberately
not handled here -- see src/pewpew/voice/fire_source.py's integration note.
"""

from __future__ import annotations

from pewpew.input.actions import ActionRouter
from pewpew.voice.asr import AsrBackend
from pewpew.voice.audio import AudioSource
from pewpew.voice.grammar import match_command


class VoiceWorker:
    def __init__(self, audio: AudioSource, backend: AsrBackend, router: ActionRouter) -> None:
        self._audio = audio
        self._backend = backend
        self._router = router
        self.disabled = False

    def record_and_dispatch(self, now: float) -> None:
        if self.disabled:
            return
        try:
            self._audio.start()
            clip = self._audio.stop()
            result = self._backend.transcribe(clip)
            action = match_command(result)
            if action is not None:
                self._router.discrete(action)
        except Exception:
            self.disabled = True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_voice_worker.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/pewpew/voice/worker.py tests/test_voice_worker.py
git commit -m "feat(voice): VoiceWorker -- crash-isolated integration into ActionRouter

A crash anywhere in the record/transcribe/match/dispatch cycle disables
voice only; router and every other input path are untouched."
```

---

### Task 9: Milestone 3b decision-gate docs, split software / hardware

**Files:**
- Create: `docs/validation/milestone-3b-checklist.md`
- Create: `docs/validation/milestone-3b-result.md`
- Test: `tests/test_validation_docs_m3b.py`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: the gate record templates later tasks/gates fill in.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validation_docs_m3b.py
"""Static contracts for the Milestone 3b decision gate."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "docs" / "validation" / "milestone-3b-checklist.md"
RESULT = ROOT / "docs" / "validation" / "milestone-3b-result.md"


def _docs() -> str:
    return CHECKLIST.read_text(encoding="utf-8") + RESULT.read_text(encoding="utf-8")


def test_gate_is_split_into_a_software_and_a_hardware_performance_gate() -> None:
    d = _docs()
    assert "software gate" in d.lower()
    assert "hardware" in d.lower() and "performance" in d.lower()


def test_gate_names_the_raven_backend_as_preferred_and_pocketsphinx_as_fallback() -> None:
    d = _docs()
    assert "Raven" in d and "OpenAiHelper" in d
    assert "PocketSphinx" in d
    assert "fallback" in d.lower()


def test_gate_does_not_claim_offline_capability_for_the_current_backend() -> None:
    d = _docs()
    assert "cloud" in d.lower()
    # The one place "offline" may appear is describing Raven's *future* plan,
    # never today's capability -- this project overclaims nothing.
    assert "not something DOOMed Prism can claim" in d or "not claimed" in d.lower()


def test_result_starts_pending_and_never_hardcodes_a_pass() -> None:
    text = RESULT.read_text(encoding="utf-8")
    assert "PENDING" in text
    assert "Final decision" in text


def test_hardware_performance_items_are_named_explicitly_not_closeable_now() -> None:
    d = _docs()
    for item in ("Prism microphone", "latency", "false positive", "false negative", "thermal"):
        assert item.lower() in d.lower(), f"missing hardware-gate item: {item}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_validation_docs_m3b.py -v`
Expected: FAIL — neither doc file exists yet.

- [ ] **Step 3: Write `docs/validation/milestone-3b-checklist.md`**

```markdown
# Milestone 3b: voice command grammar and "pew pew" — decision gate

This milestone has **two separate gates** (spec R15): a software gate,
closeable now with fakes and the Simulator microphone, and a
hardware/performance gate that needs real Raven Prism access and is **not**
claimed closed by the software gate passing.

## Software gate (this checklist's scope)

- [ ] `check_publication_safety.py` and `.gitignore` cover audio/model
  suffixes (task 1) — confirm both scans still exit 0.
- [ ] The §9 licence review is recorded as committed text: **Raven Framework
  ASR (`OpenAiHelper`) preferred; PocketSphinx the independently researched
  fallback**, documented and ready, not implemented. A dedicated low-latency
  "pew pew" detector remains an architectural option, selected only if
  measurement (hardware gate) shows Raven's ASR is unsuitable for fire.
- [ ] `AsrStatus.EMPTY_OR_FAILURE` is never reported as a confirmed failure,
  and `AsrStatus.LOCAL_ERROR` is never inferred from Raven's `OpenAiHelper`
  returning `""` — confirm by reading `src/pewpew/voice/raven_backend.py`
  and its tests.
- [ ] The closed command grammar (`weapon one`–`seven`, `use`/`open`,
  `pause`/`resume`, `menu up`/`down`, `confirm`/`cancel`) dispatches the
  correct `Action` end-to-end against `FakeAsrBackend`, and against a real
  build with a scripted `AsrBackend` feeding known transcripts (no live
  microphone needed for this row).
- [ ] "pew pew" fires exactly once per utterance and respects its cooldown
  (`tests/test_voice_fire_source.py`).
- [ ] A backend/audio crash disables voice only — gaze, click, and Enter/P
  pause keep working (`tests/test_voice_worker.py`).
- [ ] The Simulator/desktop microphone path (`RavenMicrophoneSource`'s Qt
  fallback) can be exercised manually on the Windows dev box: speak a
  command, confirm the matched `Action` reaches the engine.
- [ ] `python -m pytest -q`: all green.
- [ ] Both publication-safety scans exit 0.

**This checklist's record: `docs/validation/milestone-3b-result.md`'s
"Software gate" section.**

## Hardware/performance gate — NOT part of this checklist

Recorded here only to make explicit what is *not* being claimed by a
software-gate PASS. Requires physical Raven Prism access:

- Real Prism microphone access (needs Raven app `app_id`/`app_key`
  entitlement — not available from a development machine).
- Measured Raven ASR (`OpenAiHelper.transcribe_audio`) round-trip latency on
  real hardware, and command-grammar recognition accuracy.
- "pew pew" false-positive rate (fires when the player didn't say it) and
  false-negative rate (doesn't fire when they did) on real hardware.
- CPU/RAM/thermal impact of the voice path on the Prism device — and, if the
  above shows Raven's ASR is unsuitable for fire specifically, the same
  measurements for whichever dedicated low-latency detector is chosen.
- Re-run whenever Raven ships its local, on-device ASR model behind the same
  `OpenAiHelper` interface — the latency characteristics, and therefore
  whether a dedicated fire detector is needed at all, may change
  substantially without any change to DOOMed Prism's own integration.
```

- [ ] **Step 4: Write `docs/validation/milestone-3b-result.md`**

```markdown
# Milestone 3b: voice command grammar and "pew pew" result

This document records the software-gate decision only (spec R15). The
hardware/performance gate is a separate, later result and is not filled in
here — see `docs/validation/milestone-3b-checklist.md`'s "Hardware/performance
gate" section for exactly what remains open.

## Backend

- ASR: Raven Framework's `OpenAiHelper.transcribe_audio` — **cloud today**.
  Raven has stated that planned local/on-device models will land behind the
  same function/interface; that is Raven's roadmap, not something DOOMed
  Prism can claim as implemented, and this document does not claim it.
- Fallback (not implemented): PocketSphinx — independently researched,
  documented in `docs/reference/`, ready if the hardware gate ever shows
  Raven's ASR unsuitable.
- "pew pew" fire detector: `RavenSpokenFireSource`, backed by the same
  `OpenAiHelper` path. A dedicated low-latency detector (openWakeWord is a
  *candidate*, not selected) remains an option, decided only by the
  hardware/performance gate's measured latency and false-positive/negative
  rate.

## Software-gate checklist result

- [ ] `python -m pytest -q`: _fill in_
- [ ] `check_publication_safety.py --root .`: _fill in exit code_
- [ ] `check_publication_safety.py --root . --history`: _fill in exit code_
- [ ] Command grammar dispatches correctly against `FakeAsrBackend`: _fill in_
- [ ] "pew pew" fires once per utterance, cooldown respected: _fill in_
- [ ] Voice crash isolation confirmed (gaze/click/Enter unaffected): _fill in_
- [ ] Simulator microphone manual pass on Windows: _fill in_

## Final decision

**Final decision:** PENDING — incomplete evidence

Replace with the software gate's result once the checklist above is
complete. This field never claims the hardware/performance gate — that is a
separate, later record.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_validation_docs_m3b.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Run the full suite and both publication-safety scans**

Run: `python -m pytest -q && python scripts/check_publication_safety.py --root . && python scripts/check_publication_safety.py --root . --history`
Expected: all pass, both scans exit 0.

- [ ] **Step 7: Commit**

```bash
git add docs/validation/milestone-3b-checklist.md docs/validation/milestone-3b-result.md tests/test_validation_docs_m3b.py
git commit -m "docs: Milestone 3b decision-gate templates, split software/hardware

Final decision starts PENDING. The hardware/performance gate is recorded as
explicitly not-yet-closeable, listing exactly what needs real Prism access."
```

---

## Self-review notes (writing-plans)

**Spec coverage:** every R15 "In scope (3b, per R15)" bullet maps to a task
— pub-safety extension (1), `AsrBackend`/`RavenAiHelperBackend`/`FakeAsrBackend`
(2–3), `AudioSource`/`RavenMicrophoneSource` (4), closed grammar (5),
R6 "later" codes (5–6, scoped down with a stated technical reason for the
deferred subset), `SpokenFireSource` real implementation (7), crash isolation
(8), gate docs split (9). `PocketSphinxBackend` is deliberately *not* a task —
R15 says documented, not implemented.

**Placeholder scan:** no "TBD"/"handle appropriately" in code steps; the two
`_fill in_` occurrences are in the *result* document template itself, which
is explicitly a fill-in-after-the-fact record (same shape as
`milestone-3a-result.md`), not a plan placeholder.

**Type consistency:** `AsrResult`/`AsrStatus` (Task 2) are used identically
in Tasks 3, 5, 7, 8. `AudioSource` (Task 4) is used identically in Tasks 7–8
(each owns its own instance — intentional, see Task 7/8's integration note).
`match_command` (Task 5) is consumed unchanged by Task 8. `Action` new
members (Task 5) are consumed unchanged by Tasks 6–8.

**Two defects caught and fixed during this review, before implementation:**
(1) `RavenSpokenFireSource` and `VoiceWorker` both originally declared a
`clock: Callable[[], float]` constructor parameter that every method ignored
in favor of an explicit `now` argument — dead parameter, removed from both;
`now`-as-parameter is the same shape `ActionRouter`/`InputPipeline.tick`
already use, so there is nothing left to inject or mock. (2) `VoiceWorker`
originally polled a `fire_source.spoken_fire_edge()` and pulsed
`Action.FIRE` itself — bypassing 3a's existing debounced `FireArbiter` and
risking a click plus a spoken "pew pew" close together double-firing instead
of fusing into one shot. Fixed by routing fire exclusively through
`InputPipeline`'s existing `spoken_fire` constructor parameter (Task 7's
integration note) and removing all fire handling from `VoiceWorker` (Task 8).
