"""Fetch Crispy Doom at a pinned tag, apply the frame-export patch, and build it.

The pin in ``crispy-doom.lock`` is enforced, not merely recorded:

* ``commit`` is the authoritative pin. After the clone, ``git rev-parse HEAD``
  of the checkout must equal ``lock.commit``; a moved upstream tag aborts the
  run. This check also gates ``--check`` (a ``git apply --check`` against a
  moved tag is meaningless).
* ``tarball_sha256`` is verified against the upstream tag archive
  (``https://github.com/<owner>/<repo>/archive/refs/tags/<tag>.tar.gz``),
  downloaded with the Python standard library only. Pass ``--offline`` to skip
  just this download (e.g. ``--check`` in a network-less sandbox); the default
  build path always performs it.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_BUILD_DIR = _ROOT / "build" / "crispy"
_DEFAULT_LOCK = _ROOT / "crispy-doom.lock"
_DEFAULT_PATCH = _ROOT / "patches" / "crispy-doom-fb-export.diff"
_MARKER = ".doomed-prism-applied"
_TARBALL_TIMEOUT_S = 120


@dataclass(frozen=True)
class Lock:
    repo: str
    tag: str
    commit: str
    tarball_sha256: str


class LockVerificationError(RuntimeError):
    """Raised when the cloned source does not match ``crispy-doom.lock``."""


def load_lock(path: Path) -> Lock:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return Lock(
        repo=data["repo"],
        tag=data["tag"],
        commit=data["commit"],
        tarball_sha256=data["tarball_sha256"],
    )


def tarball_url(lock: Lock) -> str:
    """Derive the GitHub tag-archive URL from ``lock.repo`` and ``lock.tag``."""
    path = lock.repo.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    owner_repo = "/".join(path.split("/")[-2:])
    return (
        f"https://github.com/{owner_repo}/archive/refs/tags/{lock.tag}.tar.gz"
    )


def _default_fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=_TARBALL_TIMEOUT_S) as response:  # noqa: S310
        return response.read()


def verify_commit(build_dir: Path, lock: Lock, *, runner=subprocess.run) -> None:
    """Fail unless the clone's ``HEAD`` is exactly ``lock.commit``."""
    result = runner(
        ["git", "-C", str(build_dir), "rev-parse", "HEAD"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
    )
    if getattr(result, "returncode", 0) != 0:
        raise LockVerificationError(
            f"could not resolve HEAD of the Crispy Doom checkout at {build_dir}"
        )
    head = (getattr(result, "stdout", "") or "").strip()
    if head != lock.commit:
        raise LockVerificationError(
            "crispy-doom.lock pin mismatch:\n"
            f"  pinned commit (crispy-doom.lock): {lock.commit}\n"
            f"  cloned HEAD ({lock.tag}):          {head}\n"
            f"the upstream tag {lock.tag!r} no longer points at the pinned "
            "commit -- re-pin crispy-doom.lock deliberately if this is expected."
        )


def verify_tarball(lock: Lock, *, fetch=_default_fetch) -> None:
    """Fail unless the upstream tag archive hashes to ``lock.tarball_sha256``."""
    url = tarball_url(lock)
    try:
        data = fetch(url)
    except Exception as error:  # network / HTTP failure
        raise LockVerificationError(
            f"could not download the pinned tag archive {url}: {error}"
        ) from error
    digest = hashlib.sha256(data).hexdigest()
    if digest != lock.tarball_sha256:
        raise LockVerificationError(
            "crispy-doom.lock tarball hash mismatch:\n"
            f"  url:                              {url}\n"
            f"  pinned tarball_sha256:            {lock.tarball_sha256}\n"
            f"  sha256 of the downloaded archive: {digest}\n"
            "the upstream tag archive no longer matches the pinned hash -- "
            "re-pin crispy-doom.lock deliberately if this is expected."
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
    fetch=_default_fetch,
    _build_dir: Path | None = None,
    _lock_path: Path | None = None,
    _patch: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="build_crispy")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the pin and that the patch applies cleanly; no build",
    )
    parser.add_argument("--clean", action="store_true", help="remove the build directory")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip the tarball-hash download only (commit pin is still verified)",
    )
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

    # Execute the optional clone first, then enforce the pin before anything
    # touches the patch or the build.
    pending = list(commands)
    if pending and pending[0][:2] == ["git", "clone"]:
        clone = pending.pop(0)
        result = runner(clone, cwd=str(_ROOT))
        if getattr(result, "returncode", 0) != 0:
            print(f"command failed: {' '.join(clone)}", file=sys.stderr)
            return 1

    try:
        verify_commit(build_dir, lock, runner=runner)
        if args.offline:
            print("--offline: skipping the tarball-hash download", file=sys.stderr)
        else:
            verify_tarball(lock, fetch=fetch)
    except LockVerificationError as error:
        print(str(error), file=sys.stderr)
        return 1

    for command in pending:
        result = runner(command, cwd=str(_ROOT))
        if getattr(result, "returncode", 0) != 0:
            print(f"command failed: {' '.join(command)}", file=sys.stderr)
            return 1
        if command[:4] == ["git", "-C", str(build_dir), "apply"] and "--check" not in command:
            build_dir.mkdir(parents=True, exist_ok=True)
            (build_dir / _MARKER).write_text("1", encoding="utf-8")

    if not args.check:
        exe = build_dir / "build" / "src" / (
            "crispy-doom.exe" if sys.platform == "win32" else "crispy-doom"
        )
        print(str(exe))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
