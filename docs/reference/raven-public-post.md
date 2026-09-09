# Reference: Raven's public recognition of DOOMed Prism

## The public post

- **Date:** September 9, 2026
- **Source:** Raven Resonance, on LinkedIn
- **Link:** <https://lnkd.in/p/eyuTeH6z>

Raven Resonance publicly showed DOOMed Prism running on physical Raven Prism
hardware, describing it as:

> "the first natively compiled (non web app) DOOM port on lightweight eyewear"

The post credited **Ricardo Braga**.

## Technical clarification from Raven

On Raven's Discord, Parth Arora (Raven) clarified whether the project had been
run directly from the repository on an actual Prism, and what changes were
required:

> "Yep it worked right out of the repo, I actually had to make some changes to
> test it on my Mac simulator but for the glasses, I just compiled the code on
> glasses and ran it."

Per Parth Arora / Raven, this means:

- it worked directly from the repository — not a separately adapted build;
- the code was compiled **on the physical Raven Prism**;
- it ran on the glasses;
- **no glasses-specific changes were required**;
- the changes mentioned were for his **Mac simulator** test, not for the
  physical glasses.

## How this project treats it

- **Raven-side, on-device recognition and validation.** The demonstration on
  physical hardware, the quoted description, and the technical clarification are
  Raven's. This is external recognition and attribution of the work.
- **Native Raven Prism / ARM64 build and run — externally validated.** Raven
  Prism is ARM64, and Raven compiled this repository directly on the glasses and
  ran it successfully. That is external evidence the project builds and runs
  natively on Prism ARM64 hardware.
- **In-repo ARM64 CI gate.** CI builds the patched engine and runs the POSIX
  shared-memory runtime smoke natively on `ubuntu-24.04-arm` (aarch64) on every
  push, so "does it build and run on ARM64 Linux?" is now answered in this
  repository, not only by Raven. That is still distinct from the physical Prism:
  CI proves ARM64 *Linux*; Raven proved the *device* itself (its toolchain,
  runtime, and compositor). Both point the same way.
- **Separate from the input-interaction work.** The gaze/input interaction is
  developed on a separate branch and is not part of this documentation change.
  The Raven hardware evidence establishes that the port / build / rendering path
  runs on the glasses; it does **not** establish that the gaze-joystick input
  interaction has passed on-glasses validation. That interaction gate remains
  open.
- **Not a formal endorsement.** DOOMed Prism remains an independent, unofficial
  experimental project. Raven's post and confirmation are evidence and public
  recognition, not affiliation, sponsorship, or a formal endorsement. See the
  Disclaimer in the [README](../../README.md).

## Still outstanding

- An in-repo, milestone-gated validation of the gaze input interaction on
  physical Raven Prism hardware (distinct from Raven's own demonstration above,
  and from the ARM64-Linux CI gate).
