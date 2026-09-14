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

## Final decision

**Final decision:** PENDING — incomplete evidence

Replace with the software gate's result once the checklist above is
complete. This field never claims the hardware/performance gate — that is a
separate, later record.
