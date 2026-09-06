"""Static contracts for the Milestone 3a manual decision gate."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "docs" / "validation" / "milestone-3a-checklist.md"
RESULT = ROOT / "docs" / "validation" / "milestone-3a-result.md"


def _docs() -> str:
    return CHECKLIST.read_text(encoding="utf-8") + RESULT.read_text(encoding="utf-8")


def test_gate_carries_the_four_decision_strings() -> None:
    d = _docs()
    assert "PASS — IPC input path viable" in d
    assert "FAIL — IPC input path insufficient" in d
    assert "BLOCKED/RETRY — implementation or environment failure" in d
    assert "PENDING — incomplete evidence" in d


def test_gate_requires_ipc_only_play_with_the_sdl_window_unfocused() -> None:
    d = _docs()
    assert "SDL window" in d and "unfocused" in d
    lowered = d.lower()
    assert "release" in lowered and "held" in lowered


def test_gate_runs_both_publication_safety_scans_and_the_diff_stat() -> None:
    checklist = CHECKLIST.read_text(encoding="utf-8")
    assert "check_publication_safety.py --root ." in checklist
    assert "check_publication_safety.py --root . --history" in checklist
    assert "git apply --stat patches/crispy-doom-ipc-input.diff" in checklist


def test_gate_uses_placeholder_ipc_addresses_only() -> None:
    d = _docs()
    assert "<tempdir>/doomed-prism-ipc-<pid>-<token>.sock" in d
    assert "127.0.0.1:<port>" in d
    for private in ("AppData\\Local\\Temp", "/home/", "/Users/"):
        assert private not in d
