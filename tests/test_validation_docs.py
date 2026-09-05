"""Static contracts for the manual simulator decision gate."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "docs" / "validation" / "milestone-1-checklist.md"
RESULT = ROOT / "docs" / "validation" / "milestone-1-result.md"


def test_decision_gate_reserves_framebuffer_failure_for_optical_capture_loss() -> None:
    """Catches keyboard, geometry, cleanup, or evidence failures selecting framebuffer."""
    documents = CHECKLIST.read_text(encoding="utf-8") + RESULT.read_text(
        encoding="utf-8"
    )

    assert "PASS — native embedding viable" in documents
    assert "FAIL — native child not captured" in documents
    assert "BLOCKED/RETRY — implementation or environment failure" in documents
    assert "PENDING — incomplete evidence" in documents
    assert "Raw capture is known-good" in documents
    assert "Only this capture-specific outcome selects framebuffer integration" in documents


def test_decision_gate_establishes_a_trustworthy_native_pixel_dpi_boundary() -> None:
    """Catches validation relying only on logical Qt geometry under DPI scaling."""
    documents = CHECKLIST.read_text(encoding="utf-8") + RESULT.read_text(
        encoding="utf-8"
    )

    assert "100% display scaling" in documents
    assert "GetClientRect" in documents
    assert "640×480 native client pixels" in documents
    assert "DPI-awareness" in documents
    assert "cross-process SetParent" in documents


def test_validation_checklist_runs_index_and_reachable_history_safety_scans() -> None:
    checklist = CHECKLIST.read_text(encoding="utf-8")

    assert "check_publication_safety.py --root ." in checklist
    assert "check_publication_safety.py --root . --history" in checklist
