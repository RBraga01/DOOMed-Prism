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

- [ ] `python -m pytest -q`: _fill in_
- [ ] `check_publication_safety.py --root .`: _fill in exit code_
- [ ] `check_publication_safety.py --root . --history`: _fill in exit code_
- [ ] Command grammar dispatches correctly against `FakeAsrBackend`: _fill in_
- [ ] "pew pew" fires once per utterance, cooldown respected: _fill in_
- [ ] Voice crash isolation confirmed (gaze/click/Enter unaffected): _fill in_
- [ ] Simulator microphone manual pass on Windows: _fill in_

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

**Final decision:** PENDING — incomplete evidence

Replace with the software gate's result once the checklist above is
complete. This field never claims the hardware/performance gate — that is a
separate, later record, and it never claims host integration or the
capture-session/threading decision are done either — see "Known limitations
/ deferred" above.
