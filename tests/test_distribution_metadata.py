"""Contracts for publishable source-distribution metadata."""

from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_project_uses_spdx_license_metadata_and_full_gpl_text() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

    assert metadata["project"]["license"] == "GPL-2.0-or-later"
    assert "Copyright (C) 2026 DOOMed Prism contributors" in license_text
    assert "GNU GENERAL PUBLIC LICENSE\n                       Version 2, June 1991" in license_text
    assert "END OF TERMS AND CONDITIONS" in license_text


def test_source_distribution_explicitly_excludes_unshipped_test_dependencies() -> None:
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert "prune tests" in manifest.splitlines()
