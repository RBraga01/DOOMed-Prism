# Milestone 3b: voice command grammar and "pew pew" — decision gate

This milestone has **two separate gates** (spec R15): a software gate,
closeable now with fakes and the Simulator microphone, and a
hardware/performance gate that needs real Raven Prism access and is **not**
claimed closed by the software gate passing.

## Software gate (this checklist's scope)

- [ ] `check_publication_safety.py` and `.gitignore` cover audio/model
  suffixes (task 1) — confirm both scans still exit 0.
- [ ] The §9 licence review's **conclusion** is recorded as committed text
  (ruling R15 in the M3 design spec): **Raven Framework ASR (`OpenAiHelper`)
  preferred; PocketSphinx the independently researched fallback**, not
  implemented. The underlying research (licence terms, model sizes,
  integration notes) was not committed to the repo as a separate writeup —
  R15's summary sentence is the only committed text. A dedicated low-latency
  "pew pew" detector remains an architectural option, selected only if
  measurement (hardware gate) shows Raven's ASR is unsuitable for fire.
- [ ] `AsrStatus.EMPTY_OR_FAILURE` is never reported as a confirmed failure,
  and `AsrStatus.LOCAL_ERROR` is never inferred from Raven's `OpenAiHelper`
  returning `""` — confirm by reading `src/pewpew/voice/raven_backend.py`
  and its tests.
- [ ] The closed command grammar (`weapon one`–`seven`, `use`/`open`,
  `pause`/`resume`, `menu up`/`down`, `confirm`/`cancel`) dispatches the
  correct `Action` end-to-end against `FakeAsrBackend`
  (`tests/test_voice_worker.py`, `tests/test_voice_grammar.py`), including
  the pulse-vs-discrete routing for state-polled keys (`USE`, `WEAPON_1..7`)
  and the real-engine verification recorded in
  `.superpowers/sdd/2026-09-13-doomed-prism-milestone-3b-software-gate/final-review-fix-report.md`.
  **Host integration is explicitly deferred**: nothing in this milestone
  constructs or drives `VoiceWorker`/`RavenSpokenFireSource` from the running
  application (`InputPipeline`'s `ActionRouter` is private with no
  accessor), so "against a real build with a scripted `AsrBackend` feeding
  known transcripts" as an *operator-driven, wired* row cannot be executed
  as written and is not claimed here — that is follow-up work (see
  `milestone-3b-result.md`'s "Known limitations / deferred").
- [ ] "pew pew" fires exactly once per utterance and respects its cooldown
  (`tests/test_voice_fire_source.py`).
- [ ] A backend/audio crash disables voice only — gaze, click, and Enter/P
  pause keep working. Covers both halves of the voice surface:
  `tests/test_voice_worker.py` (command path) and
  `tests/test_voice_fire_source.py` (fire path, including a raising
  `AudioSource`, not just a raising backend).
- [ ] The Simulator/desktop microphone path (`RavenMicrophoneSource`'s Qt
  fallback) is unit-tested against a fake `Microphone`
  (`tests/test_voice_audio.py`). **Manually speaking a command into the real
  Simulator microphone and confirming the matched `Action` reaches a running
  engine is deferred**, along with the rest of host integration (see above)
  — nothing in this milestone constructs `VoiceWorker`/`RavenSpokenFireSource`
  from a running application, so there is no wired path to speak into yet.
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
- "pew pew" false positive rate (fires when the player didn't say it) and
  false negative rate (doesn't fire when they did) on real hardware.
- CPU/RAM/thermal impact of the voice path on the Prism device — and, if the
  above shows Raven's ASR is unsuitable for fire specifically, the same
  measurements for whichever dedicated low-latency detector is chosen.
- Re-run whenever Raven ships its local, on-device ASR model behind the same
  `OpenAiHelper` interface — the latency characteristics, and therefore
  whether a dedicated fire detector is needed at all, may change
  substantially without any change to DOOMed Prism's own integration.
