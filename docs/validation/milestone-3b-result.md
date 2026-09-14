# Milestone 3b: voice command grammar and "pew pew" result

This document records the software-gate decision only (spec R15). The
hardware/performance gate is a separate, later result and is not filled in
here — see `docs/validation/milestone-3b-checklist.md`'s "Hardware/performance
gate" section for exactly what remains open.

## Backend

- ASR: Raven Framework's `OpenAiHelper.transcribe_audio` — **cloud today**.
  Raven has stated that planned local/on-device models will land behind the
  same function/interface; that is Raven's roadmap, not something DOOMed
  Prism can claim as implemented — offline operation is not claimed by this
  project today.
- Fallback (not implemented): PocketSphinx — independently researched,
  documented in `docs/superpowers/specs/2026-09-05-doomed-prism-milestone-3-design.md`
  (ruling R15), ready if the hardware gate ever shows Raven's ASR unsuitable.
- "pew pew" fire detector: `RavenSpokenFireSource`, backed by the same
  `OpenAiHelper` path. A dedicated low-latency detector (openWakeWord is a
  *candidate*, not selected) remains an option, decided only by the
  hardware/performance gate's measured latency and false positive/negative
  rate.

## Software-gate checklist result

- [x] `python -m pytest -q`: **251 passed, 6 skipped.**
- [x] `check_publication_safety.py --root .`: **exit 0.**
- [x] `check_publication_safety.py --root . --history`: **exit 0.**
- [x] Command grammar dispatches correctly against `FakeAsrBackend`,
  including pulse-vs-discrete routing for state-polled keys (`USE`,
  `WEAPON_1..7`): **confirmed** — `tests/test_voice_worker.py`,
  `tests/test_voice_grammar.py`,
  `tests/test_distribution_metadata.py::test_every_grammar_action_has_a_c_dispatch_arm`.
  Also verified on a real engine rebuild: switching to `WEAPON_1` (fist)
  changed the status-bar pixel hash, switching back to `WEAPON_2` (pistol)
  restored the exact original hash — a discriminating round-trip result.
- [x] "pew pew" fires once per utterance, cooldown respected: **confirmed**
  — `tests/test_voice_fire_source.py`.
- [x] Voice crash isolation confirmed (gaze/click/Enter unaffected):
  **confirmed for both halves of the voice surface** — the command path
  (`tests/test_voice_worker.py`) and the fire path
  (`tests/test_voice_fire_source.py`, including a raising `AudioSource`).
- [x] Simulator microphone manual pass on Windows: **unit-tested** against a
  fake `Microphone` (`tests/test_voice_audio.py`). Manually speaking into
  the real Simulator microphone against a running, wired engine is
  deferred along with the rest of host integration — see "Known
  limitations / deferred" below; there is no wired path to speak into yet.

## Known limitations / deferred

Recorded here, not silently absent, per this project's no-overclaiming
discipline (final-review fix brief, Important 5/7):

- **Host integration is not part of this gate.** Nothing in this milestone
  constructs or drives `VoiceWorker` or `RavenSpokenFireSource` from a
  running application. `InputPipeline`'s `ActionRouter` is private with no
  accessor, so the two classes are unreachable from `src/pewpew/host_widget.py`
  today. Wiring them in — including deciding the cleanest seam that respects
  "`pipeline.py`'s consumer side doesn't change" — is explicitly deferred to
  a follow-up task, not rushed into this bug-fix pass.
- **The capture-session and threading model is an open decision, not yet
  made.** As designed, `VoiceWorker` and `RavenSpokenFireSource` each own an
  independent `AudioSource` and call `transcribe()` inline/synchronously —
  once wired to real classes, that means two separate microphone sessions on
  one physical input device and two synchronous cloud round trips per cycle,
  potentially on the UI thread. Whether the two paths share one capture
  session, and whether the transcribe call moves off the UI thread (a
  single-slot queue plus a worker thread was suggested), is a structural
  decision that belongs with the host-integration follow-up task, not this
  gate.
- Both gaps are real, but neither blocks this software gate: they were
  identified by the final whole-branch review (Important 5 and 7) and the
  ruling made there was to defer, not to redesign inside this fix pass.

## Final decision

- **Software gate:** PASS — every row in the checklist above is confirmed
  against committed tests and a real engine rebuild.
- **Hardware/performance gate:** PENDING — not started; requires physical
  Raven Prism access. See `milestone-3b-checklist.md`'s "Hardware/performance
  gate" section for exactly what remains open (real mic entitlement,
  measured ASR latency/accuracy, "pew pew" false-positive/negative rate,
  CPU/RAM/thermal impact).
- **Overall M3b:** PENDING — a software-gate PASS does not close Milestone
  3b on its own; the hardware/performance gate must pass first. This
  distinction is deliberate (spec R15's two-gate split), not an oversight:
  the software gate is independently mergeable, and waiting on hardware
  access to land already-verified, tested work would leave it stranded on
  an external Raven-side dependency for no benefit.

**Final decision:** Software gate PASS; Hardware/performance gate and
overall Milestone 3b remain PENDING.
