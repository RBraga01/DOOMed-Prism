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


def test_readme_names_both_engine_patches_in_the_license_section() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    license_section = text.split("## License", 1)[1].lower()
    assert "frame" in license_section and "ipc" in license_section
    diffs = {p.name for p in (ROOT / "patches").iterdir() if p.suffix == ".diff"}
    assert diffs == {"crispy-doom-fb-export.diff", "crispy-doom-ipc-input.diff"}


def test_c_patch_constants_match_the_python_enums() -> None:
    import re

    from pewpew.input.actions import Action
    from pewpew.ipc.protocol import MessageType

    diff = (ROOT / "patches" / "crispy-doom-ipc-input.diff").read_text(encoding="utf-8")
    defs = {n: int(v) for n, v in re.findall(r"#define\s+(AC_\w+|MT_\w+)\s+(\d+)", diff)}
    assert defs["AC_MOVE_FORWARD"] == Action.MOVE_FORWARD
    assert defs["AC_MOVE_BACKWARD"] == Action.MOVE_BACKWARD
    assert defs["AC_TURN_LEFT"] == Action.TURN_LEFT
    assert defs["AC_TURN_RIGHT"] == Action.TURN_RIGHT
    assert defs["AC_FIRE"] == Action.FIRE
    assert defs["AC_USE"] == Action.USE
    assert defs["AC_PAUSE"] == Action.PAUSE
    assert defs["MT_HELLO"] == MessageType.HELLO
    assert defs["MT_ACTION"] == MessageType.ACTION
    assert defs["MT_PULSE"] == MessageType.PULSE
    assert defs["MT_DISCRETE"] == MessageType.DISCRETE
    assert defs["MT_TURN"] == MessageType.TURN
    assert defs["MT_BYE"] == MessageType.BYE
