"""Fetch Crispy Doom at a pinned tag, apply the frame-export patch, and build it."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_BUILD_DIR = _ROOT / "build" / "crispy"
_DEFAULT_LOCK = _ROOT / "crispy-doom.lock"
_DEFAULT_PATCH = _ROOT / "patches" / "crispy-doom-fb-export.diff"
_MARKER = ".doomed-prism-applied"


@dataclass(frozen=True)
class Lock:
    repo: str
    tag: str
    commit: str
    tarball_sha256: str


def load_lock(path: Path) -> Lock:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return Lock(
        repo=data["repo"],
        tag=data["tag"],
        commit=data["commit"],
        tarball_sha256=data["tarball_sha256"],
    )


def plan_commands(
    lock: Lock, *, build_dir: Path, patch: Path, check_only: bool
) -> list[list[str]]:
    commands: list[list[str]] = []
    if not (build_dir / ".git").exists():
        commands.append(
            ["git", "clone", "--branch", lock.tag, lock.repo, str(build_dir)]
        )
    if check_only:
        commands.append(["git", "-C", str(build_dir), "apply", "--check", str(patch)])
        return commands
    if not (build_dir / _MARKER).exists():
        commands.append(["git", "-C", str(build_dir), "apply", str(patch)])
    commands.append(
        ["cmake", "-S", str(build_dir), "-B", str(build_dir / "build"),
         "-DCMAKE_BUILD_TYPE=Release"]
    )
    commands.append(["cmake", "--build", str(build_dir / "build")])
    return commands


def run(
    argv: list[str] | None = None,
    *,
    runner=subprocess.run,
    _build_dir: Path | None = None,
    _lock_path: Path | None = None,
    _patch: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="build_crispy")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args(argv)

    build_dir = _build_dir or _DEFAULT_BUILD_DIR
    lock_path = _lock_path or _DEFAULT_LOCK
    patch = _patch or _DEFAULT_PATCH

    if args.clean:
        if build_dir.exists():
            shutil.rmtree(build_dir)
        return 0

    lock = load_lock(lock_path)
    commands = plan_commands(
        lock, build_dir=build_dir, patch=patch, check_only=args.check
    )
    for command in commands:
        result = runner(command, cwd=str(_ROOT))
        if getattr(result, "returncode", 0) != 0:
            print(f"command failed: {' '.join(command)}", file=sys.stderr)
            return 1
        if command[:4] == ["git", "-C", str(build_dir), "apply"] and "--check" not in command:
            (build_dir / _MARKER).write_text("1", encoding="utf-8")

    if not args.check:
        exe = build_dir / "build" / "src" / (
            "crispy-doom.exe" if sys.platform == "win32" else "crispy-doom"
        )
        print(str(exe))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
