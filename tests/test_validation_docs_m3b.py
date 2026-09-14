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
