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


def test_ipc_patch_touches_only_the_allowed_engine_files() -> None:
    import re

    diff = (ROOT / "patches" / "crispy-doom-ipc-input.diff").read_text(encoding="utf-8")
    touched = set(re.findall(r"^diff --git a/(\S+) b/\S+", diff, re.MULTILINE))
    allowed = {
        "src/i_ipc_input.c", "src/i_ipc_input.h", "src/d_loop.c",
        "src/i_video.c", "src/CMakeLists.txt",
        "src/doom/g_game.c",  # R14 mechanism 1: the forwardmove fold
    }
    assert touched and touched <= allowed, f"unexpected files: {touched - allowed}"
    added = sum(1 for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    assert added <= 420, f"IPC patch added {added} lines (> 420 ceiling)"


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

    # Numeric couplings that would misbehave silently if they drift.
    from pewpew.input.actions import TURN_MAX_MOUSE_DELTA
    from pewpew.ipc.protocol import IPC_FRAME_SIZE, IPC_PROTOCOL_VERSION

    frame_size = int(re.search(r"#define\s+IPC_FRAME_SIZE\s+(\d+)", diff).group(1))
    assert frame_size == 8 == IPC_FRAME_SIZE
    proto = int(re.search(r"#define\s+IPC_PROTOCOL_VERSION\s+(\d+)", diff).group(1))
    assert proto == IPC_PROTOCOL_VERSION
    turn_clamp = int(re.search(r"#define\s+IPC_TURN_CLAMP\s+(\d+)", diff).group(1))
    assert turn_clamp == TURN_MAX_MOUSE_DELTA == 40

    from pewpew.input.actions import MOVE_MAGNITUDE_SCALE

    move_wire_max = int(re.search(r"#define\s+IPC_MOVE_WIRE_MAX\s+(\d+)", diff).group(1))
    move_max_forwardmove = int(re.search(r"#define\s+MOVE_MAX_FORWARDMOVE\s+(\d+)", diff).group(1))
    stale_pumps = int(re.search(r"#define\s+IPC_MOVE_STALE_PUMPS\s+(\d+)", diff).group(1))
    # Shared full-scale: C #define == Python constant.
    assert move_wire_max == MOVE_MAGNITUDE_SCALE == 10000
    # C-only constants: present with the spec's exact values (R11).
    assert move_max_forwardmove == 50    # DOOM forwardmove[1] run value
    assert stale_pumps == 6
    # The documented forwardmove mapping contract the C side must implement.
    assert "10000" in diff and "MOVE_MAX_FORWARDMOVE" in diff
    assert re.search(r"IPC_Input_ForwardMove", diff)  # the accessor g_game.c folds
