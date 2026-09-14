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
    # 420 (M3a) -> 453 (M3b task 6) -> 461 (M3b final-review fix pass, Critical 2):
    # WEAPON_1..7 were originally wired as MT_DISCRETE keydown/keyup pairs (task
    # 6), which the final whole-branch review found DOOM's own gamekeydown[]
    # polling erases before G_BuildTiccmd ever reads them -- the same trap
    # key_fire/key_use already avoid via MT_PULSE's pulse_key[]/pulse_tics[]
    # hold. The fix moves the 7 weapon codes onto that same MT_PULSE path (a
    # `switch (code)` replacing the old two-way ternary) and removes their 7
    # MT_DISCRETE arms (net -14 lines there), and adds a comment above
    # ipc_apply() documenting DOOM's two input-consumption models so the next
    # code isn't wired the same wrong way. Net effect: 452 -> 460 actual added
    # lines. Ceiling kept at actual + 1, same margin M3a and task 6 used.
    assert added <= 461, f"IPC patch added {added} lines (> 461 ceiling)"


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
    assert defs["AC_WEAPON_1"] == Action.WEAPON_1
    assert defs["AC_WEAPON_2"] == Action.WEAPON_2
    assert defs["AC_WEAPON_3"] == Action.WEAPON_3
    assert defs["AC_WEAPON_4"] == Action.WEAPON_4
    assert defs["AC_WEAPON_5"] == Action.WEAPON_5
    assert defs["AC_WEAPON_6"] == Action.WEAPON_6
    assert defs["AC_WEAPON_7"] == Action.WEAPON_7
    assert defs["AC_MENU_CONFIRM"] == Action.MENU_CONFIRM
    assert defs["AC_MENU_CANCEL"] == Action.MENU_CANCEL
    assert defs["AC_MENU_UP"] == Action.MENU_UP
    assert defs["AC_MENU_DOWN"] == Action.MENU_DOWN
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
    assert turn_clamp == TURN_MAX_MOUSE_DELTA == 160

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


def test_every_grammar_action_has_a_c_dispatch_arm() -> None:
    """The exact class of bug the final whole-branch review's Critical 1 and
    2 findings were: a grammar phrase whose Action reaches no C-side
    dispatch arm -- or reaches one under the wrong message type for DOOM's
    input-consumption model -- matches successfully and then silently does
    nothing end-to-end (Critical 1: AC_USE dispatched as MT_DISCRETE, which
    ipc_apply() never handled for that code; Critical 2: AC_WEAPON_1..7 as an
    instantaneous MT_DISCRETE keydown+keyup pair, erased by DOOM's own
    gamekeydown[] polling before G_BuildTiccmd ever read it). A bare
    "does the code appear anywhere in ipc_apply()" check does not catch
    either bug -- AC_USE and the weapon codes were always textually present,
    just under the wrong case. This test instead scans the MT_PULSE and
    MT_DISCRETE case bodies separately and asserts every state-polled Action
    (grammar._PULSE_ACTIONS -- the ones that need MT_PULSE's hold mechanism,
    per the fix brief's Critical 1/2 root cause) is reachable specifically
    within the MT_PULSE case, not merely somewhere in the function.
    """
    import re

    from pewpew.voice import grammar

    diff = (ROOT / "patches" / "crispy-doom-ipc-input.diff").read_text(encoding="utf-8")
    # ipc_apply()'s body contains, in order, the MT_PULSE switch(code), the
    # MT_DISCRETE if-chain, then MT_BYE -- every line in this whole-new-file
    # diff is "+"-prefixed, so "case MT_DISCRETE:"/"case MT_BYE:" delimit the
    # MT_PULSE case's own body without needing to track brace depth.
    pulse_match = re.search(
        r"\+\s*case MT_PULSE:\n(.*?)\n\+\s*case MT_DISCRETE:", diff, re.DOTALL
    )
    discrete_match = re.search(
        r"\+\s*case MT_DISCRETE:\n(.*?)\n\+\s*case MT_BYE:", diff, re.DOTALL
    )
    assert pulse_match and discrete_match, "could not locate ipc_apply()'s case bodies in the IPC patch"
    pulse_reachable = set(re.findall(r"AC_(\w+)", pulse_match.group(1)))
    discrete_reachable = set(re.findall(r"AC_(\w+)", discrete_match.group(1)))
    reachable = pulse_reachable | discrete_reachable

    phrase_action_names = {action.name for action in grammar._PHRASES.values()}
    unreachable = phrase_action_names - reachable
    assert not unreachable, (
        "grammar._PHRASES names Action(s) with no C-side dispatch arm in "
        f"ipc_apply() (MT_PULSE or MT_DISCRETE): {sorted(unreachable)}"
    )

    pulse_action_names = {action.name for action in grammar._PULSE_ACTIONS}
    wrongly_typed = pulse_action_names - pulse_reachable
    assert not wrongly_typed, (
        "grammar._PULSE_ACTIONS names Action(s) reachable only outside "
        "MT_PULSE -- an instantaneous MT_DISCRETE keydown+keyup pair for a "
        "state-polled key is erased by DOOM's gamekeydown[] polling before "
        f"G_BuildTiccmd reads it (Critical 2's exact bug): {sorted(wrongly_typed)}"
    )
