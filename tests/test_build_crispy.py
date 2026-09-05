"""Tests for the Crispy Doom fetch-and-build script (no real clone or build)."""

from __future__ import annotations

import hashlib
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

_COMMIT = "0123456789012345678901234567890123456789"
_FAKE_TARBALL = b"fake-crispy-doom-tarball-bytes"
_FAKE_TARBALL_SHA256 = hashlib.sha256(_FAKE_TARBALL).hexdigest()


def _write_lock(
    tmp_path: Path,
    *,
    commit: str = _COMMIT,
    tarball_sha256: str = _FAKE_TARBALL_SHA256,
) -> Path:
    lock = tmp_path / "crispy-doom.lock"
    lock.write_text(
        'repo = "https://github.com/example/crispy-doom"\n'
        'tag = "crispy-doom-7.1"\n'
        f'commit = "{commit}"\n'
        f'tarball_sha256 = "{tarball_sha256}"\n',
        encoding="utf-8",
    )
    return lock


class _Result:
    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


def _make_runner(
    calls: list[list[str]],
    *,
    head: str = _COMMIT,
    fail_cmd_substr: str | None = None,
):
    """Fake ``subprocess.run``: records argv, answers ``git rev-parse HEAD``."""

    def _runner(cmd, **_kwargs):
        calls.append(cmd)
        if fail_cmd_substr is not None and fail_cmd_substr in " ".join(cmd):
            return _Result(returncode=1)
        if cmd[-2:] == ["rev-parse", "HEAD"]:
            return _Result(returncode=0, stdout=head + "\n")
        return _Result(returncode=0)

    return _runner


def _fake_fetch(data: bytes = _FAKE_TARBALL):
    def _fetch(url: str) -> bytes:  # noqa: ARG001 - signature is the contract
        return data

    return _fetch


# --------------------------------------------------------------------------- #
# load_lock / plan_commands (unchanged behaviour)
# --------------------------------------------------------------------------- #


def test_load_lock_reads_all_four_fields(tmp_path: Path) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    assert lock.tag == "crispy-doom-7.1"
    assert lock.commit == _COMMIT
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
        runner=_make_runner(calls),
        fetch=_fake_fetch(),
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


# --------------------------------------------------------------------------- #
# commit pin verification
# --------------------------------------------------------------------------- #


def test_verify_commit_passes_when_head_matches_lock(tmp_path: Path) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    calls: list[list[str]] = []
    build_crispy.verify_commit(
        tmp_path / "build" / "crispy", lock, runner=_make_runner(calls, head=_COMMIT)
    )
    assert any(c[-2:] == ["rev-parse", "HEAD"] for c in calls)


def test_verify_commit_raises_when_head_differs_and_names_both_shas(
    tmp_path: Path,
) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    other = "f" * 40
    with pytest.raises(build_crispy.LockVerificationError) as excinfo:
        build_crispy.verify_commit(
            tmp_path / "b", lock, runner=_make_runner([], head=other)
        )
    message = str(excinfo.value)
    assert _COMMIT in message and other in message
    assert "crispy-doom-7.1" in message


def test_run_happy_path_verifies_commit_then_applies_and_builds(
    tmp_path: Path,
) -> None:
    build_dir = tmp_path / "build" / "crispy"
    calls: list[list[str]] = []
    exit_code = build_crispy.run(
        [],
        runner=_make_runner(calls, head=_COMMIT),
        fetch=_fake_fetch(),
        _build_dir=build_dir,
        _lock_path=_write_lock(tmp_path),
        _patch=tmp_path / "p.diff",
    )
    assert exit_code == 0
    joined = [" ".join(c) for c in calls]
    assert any("clone" in c for c in joined)
    assert any(c[-2:] == ["rev-parse", "HEAD"] for c in calls)
    assert any("apply" in c and "--check" not in c for c in joined)
    assert any("cmake" in c and "--build" in c for c in joined)


def test_run_aborts_on_commit_mismatch_before_apply_or_cmake(tmp_path: Path) -> None:
    build_dir = tmp_path / "build" / "crispy"
    calls: list[list[str]] = []
    exit_code = build_crispy.run(
        [],
        runner=_make_runner(calls, head="a" * 40),
        fetch=_fake_fetch(),
        _build_dir=build_dir,
        _lock_path=_write_lock(tmp_path),
        _patch=tmp_path / "p.diff",
    )
    assert exit_code != 0
    joined = [" ".join(c) for c in calls]
    assert not any("apply" in c for c in joined)
    assert not any("cmake" in c for c in joined)


def test_check_verifies_commit_before_git_apply_check(tmp_path: Path) -> None:
    build_dir = tmp_path / "build" / "crispy"
    (build_dir / ".git").mkdir(parents=True)
    calls: list[list[str]] = []
    exit_code = build_crispy.run(
        ["--check"],
        runner=_make_runner(calls, head="b" * 40),
        fetch=_fake_fetch(),
        _build_dir=build_dir,
        _lock_path=_write_lock(tmp_path),
        _patch=tmp_path / "p.diff",
    )
    assert exit_code != 0
    joined = [" ".join(c) for c in calls]
    assert any(c[-2:] == ["rev-parse", "HEAD"] for c in calls)
    assert not any("apply" in c and "--check" in c for c in joined)


# --------------------------------------------------------------------------- #
# tarball hash verification
# --------------------------------------------------------------------------- #


def test_verify_tarball_passes_when_hash_matches(tmp_path: Path) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    seen: list[str] = []

    def _fetch(url: str) -> bytes:
        seen.append(url)
        return _FAKE_TARBALL

    build_crispy.verify_tarball(lock, fetch=_fetch)
    assert seen == [
        "https://github.com/example/crispy-doom/archive/refs/tags/"
        "crispy-doom-7.1.tar.gz"
    ]


def test_verify_tarball_raises_when_hash_differs(tmp_path: Path) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    with pytest.raises(build_crispy.LockVerificationError) as excinfo:
        build_crispy.verify_tarball(lock, fetch=_fake_fetch(b"different-bytes"))
    assert lock.tarball_sha256 in str(excinfo.value)


def test_run_happy_path_downloads_and_verifies_tarball(tmp_path: Path) -> None:
    build_dir = tmp_path / "build" / "crispy"
    calls: list[list[str]] = []
    fetched: list[str] = []

    def _fetch(url: str) -> bytes:
        fetched.append(url)
        return _FAKE_TARBALL

    exit_code = build_crispy.run(
        [],
        runner=_make_runner(calls, head=_COMMIT),
        fetch=_fetch,
        _build_dir=build_dir,
        _lock_path=_write_lock(tmp_path),
        _patch=tmp_path / "p.diff",
    )
    assert exit_code == 0
    assert fetched and fetched[0].endswith("crispy-doom-7.1.tar.gz")


def test_run_aborts_on_tarball_mismatch(tmp_path: Path) -> None:
    build_dir = tmp_path / "build" / "crispy"
    calls: list[list[str]] = []
    exit_code = build_crispy.run(
        [],
        runner=_make_runner(calls, head=_COMMIT),
        fetch=_fake_fetch(b"tampered"),
        _build_dir=build_dir,
        _lock_path=_write_lock(tmp_path),
        _patch=tmp_path / "p.diff",
    )
    assert exit_code != 0
    joined = [" ".join(c) for c in calls]
    assert not any("cmake" in c for c in joined)


def test_offline_skips_tarball_download_but_still_verifies_commit(
    tmp_path: Path,
) -> None:
    build_dir = tmp_path / "build" / "crispy"
    calls: list[list[str]] = []
    fetched: list[str] = []

    exit_code = build_crispy.run(
        ["--offline"],
        runner=_make_runner(calls, head=_COMMIT),
        fetch=lambda url: fetched.append(url) or b"",
        _build_dir=build_dir,
        _lock_path=_write_lock(tmp_path),
        _patch=tmp_path / "p.diff",
    )
    assert exit_code == 0
    assert fetched == []  # no download attempted
    assert any(c[-2:] == ["rev-parse", "HEAD"] for c in calls)


def test_offline_still_aborts_on_commit_mismatch(tmp_path: Path) -> None:
    build_dir = tmp_path / "build" / "crispy"
    calls: list[list[str]] = []
    exit_code = build_crispy.run(
        ["--offline"],
        runner=_make_runner(calls, head="c" * 40),
        fetch=lambda url: b"",
        _build_dir=build_dir,
        _lock_path=_write_lock(tmp_path),
        _patch=tmp_path / "p.diff",
    )
    assert exit_code != 0


def _ok():
    class _R:
        returncode = 0

    return _R()
