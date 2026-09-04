"""Tests for the Crispy Doom fetch-and-build script (no real clone or build)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "build_crispy", Path(__file__).resolve().parents[1] / "scripts" / "build_crispy.py"
)
build_crispy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = build_crispy
_spec.loader.exec_module(build_crispy)


def _write_lock(tmp_path: Path) -> Path:
    lock = tmp_path / "crispy-doom.lock"
    lock.write_text(
        'repo = "https://example.invalid/crispy-doom"\n'
        'tag = "crispy-doom-7.1"\n'
        'commit = "0123456789012345678901234567890123456789"\n'
        'tarball_sha256 = "%s"\n' % ("a" * 64),
        encoding="utf-8",
    )
    return lock


def test_load_lock_reads_all_four_fields(tmp_path: Path) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    assert lock.tag == "crispy-doom-7.1"
    assert lock.commit == "0123456789012345678901234567890123456789"
    assert lock.repo.endswith("crispy-doom")
    assert len(lock.tarball_sha256) == 64


def test_plan_commands_clones_pinned_tag_applies_patch_then_builds(
    tmp_path: Path,
) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    build_dir = tmp_path / "build" / "crispy"
    patch = tmp_path / "patches" / "crispy-doom-fb-export.diff"

    commands = build_crispy.plan_commands(
        lock, build_dir=build_dir, patch=patch, check_only=False
    )

    joined = [" ".join(c) for c in commands]
    assert any("clone" in c and "crispy-doom-7.1" in c for c in joined)
    assert any(c.startswith("git") and "apply" in c and str(patch) in c for c in joined)
    assert any("cmake" in c and "--build" in c for c in joined)


def test_plan_commands_check_only_stops_after_git_apply_check(tmp_path: Path) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    commands = build_crispy.plan_commands(
        lock,
        build_dir=tmp_path / "b",
        patch=tmp_path / "p.diff",
        check_only=True,
    )
    joined = [" ".join(c) for c in commands]
    assert any("apply" in c and "--check" in c for c in joined)
    assert not any("cmake" in c for c in joined)


def test_clean_removes_the_build_directory(tmp_path: Path) -> None:
    build_dir = tmp_path / "build" / "crispy"
    build_dir.mkdir(parents=True)
    (build_dir / "marker").write_text("x", encoding="utf-8")

    calls: list[list[str]] = []
    exit_code = build_crispy.run(
        ["--clean"],
        runner=lambda cmd, **_: calls.append(cmd),
        _build_dir=build_dir,
        _lock_path=_write_lock(tmp_path),
        _patch=tmp_path / "p.diff",
    )

    assert exit_code == 0
    assert not build_dir.exists()
    assert calls == []


def test_run_skips_git_apply_when_marker_present(tmp_path: Path) -> None:
    build_dir = tmp_path / "build" / "crispy"
    (build_dir / ".git").mkdir(parents=True)
    (build_dir / ".doomed-prism-applied").write_text("1", encoding="utf-8")

    calls: list[list[str]] = []
    build_crispy.run(
        [],
        runner=lambda cmd, **_: calls.append(cmd) or _ok(),
        _build_dir=build_dir,
        _lock_path=_write_lock(tmp_path),
        _patch=tmp_path / "p.diff",
    )

    joined = [" ".join(c) for c in calls]
    assert not any("clone" in c for c in joined)
    assert not any(
        cmd[:4] == ["git", "-C", str(build_dir), "apply"] and "--check" not in cmd
        for cmd in calls
    )


def _ok():
    class _R:
        returncode = 0

    return _R()
