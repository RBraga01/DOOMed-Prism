#!/usr/bin/env python3
"""Reject tracked material that is unsafe to publish."""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


FORBIDDEN_SUFFIXES = (".wad", ".pk3", ".exe", ".dll", ".so")
FORBIDDEN_NAMES = {".env", "app_key"}
CREDENTIAL_LITERAL = re.compile(
    r"(?:\b(?P<bare_name>app_key|app_id)\b|[\"'](?P<quoted_name>app_key|app_id)[\"'])"
    r"\s*(?:=|:)\s*(?:\(\s*)*"
    r"(?:[rRuUbBfF]{0,3})?"
    r'(?:"""(?P<triple_double>.+?)"""|'
    r"'''(?P<triple_single>.+?)'''|"
    r'"(?P<single_double>(?:\\.|[^"\\\r\n])+?)"|'
    r"'(?P<single_single>(?:\\.|[^'\\\r\n])+?)')",
    re.DOTALL,
)


@dataclass(frozen=True)
class IndexBlob:
    """A stage-zero index entry, including gitlinks that have no blob content."""

    path: PurePosixPath
    object_id: str
    mode: str


@dataclass(frozen=True)
class HistoryEntry:
    """One path entry from a tree belonging to a reachable commit."""

    path: PurePosixPath
    object_id: str
    mode: str


def indexed_blobs(root: Path) -> list[IndexBlob]:
    """Return stage-zero blobs from Git's index without reading the worktree."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--stage", "-z"],
        check=True,
        capture_output=True,
    )
    blobs: list[IndexBlob] = []
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", maxsplit=1)
        mode, object_id, stage = metadata.split()
        if stage != b"0":
            continue
        blobs.append(
            IndexBlob(
                path=PurePosixPath(raw_path.decode("utf-8", errors="surrogateescape")),
                object_id=object_id.decode("ascii"),
                mode=mode.decode("ascii"),
            )
        )
    return blobs


def indexed_blob_content(root: Path, object_id: str) -> bytes:
    """Read one staged Git blob by object ID, never through a filesystem path."""
    return subprocess.run(
        ["git", "-C", str(root), "cat-file", "blob", object_id],
        check=True,
        capture_output=True,
    ).stdout


def text_blob_content(blob: bytes) -> str | None:
    """Decode text blobs while leaving binary blobs unscanned."""
    if b"\0" in blob:
        return None
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return None


def path_violation(path: PurePosixPath) -> str | None:
    """Describe a forbidden tracked pathname, if it has one."""
    path_name = path.name.casefold()
    if any(path_name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
        return "forbidden tracked file"
    if path_name in FORBIDDEN_NAMES:
        return "forbidden tracked file"
    if "raven_framework" in {part.casefold() for part in path.parts}:
        return "forbidden tracked Raven framework path"
    return None


def credential_violations(content: str) -> list[str]:
    """Find non-empty app credential literals in an indexed text blob."""
    return [
        match.group("bare_name") or match.group("quoted_name")
        for match in CREDENTIAL_LITERAL.finditer(content)
    ]


def scan(root: Path) -> list[str]:
    """Return one publication-safety violation per output line."""
    violations: list[str] = []
    for blob in indexed_blobs(root):
        path_problem = path_violation(blob.path)
        if path_problem:
            violations.append(f"{blob.path}: {path_problem}")
            continue
        if blob.mode == "160000":
            continue
        content = text_blob_content(indexed_blob_content(root, blob.object_id))
        if content is None:
            continue
        for credential_name in credential_violations(content):
            violations.append(f"{blob.path}: non-empty {credential_name} literal")
    return violations


def reachable_history_entries(root: Path) -> list[HistoryEntry]:
    """Return every path in every commit reachable from a local ref.

    Object walks retain only one path hint per object ID, which loses an old
    forbidden name when the same blob or gitlink is reachable under another
    name.  Enumerating each commit tree preserves every historical pathname.
    """
    commits = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    entries: list[HistoryEntry] = []
    for commit in commits:
        tree = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-r", "-z", "--full-tree", commit],
            check=True,
            capture_output=True,
        )
        for record in tree.stdout.split(b"\0"):
            if not record:
                continue
            metadata, raw_path = record.split(b"\t", maxsplit=1)
            mode, _object_type, object_id = metadata.split()
            entries.append(
                HistoryEntry(
                    path=PurePosixPath(
                        raw_path.decode("utf-8", errors="surrogateescape")
                    ),
                    object_id=object_id.decode("ascii"),
                    mode=mode.decode("ascii"),
                )
            )
    return entries


def scan_history(root: Path) -> list[str]:
    """Scan all reachable Git history for paths and readable text blobs."""
    violations: list[str] = []
    scanned_blobs: set[str] = set()
    for entry in reachable_history_entries(root):
        path_problem = path_violation(entry.path)
        if path_problem:
            violations.append(f"{entry.path}: {path_problem}")
            continue
        if entry.mode == "160000" or entry.object_id in scanned_blobs:
            continue
        scanned_blobs.add(entry.object_id)
        content = text_blob_content(indexed_blob_content(root, entry.object_id))
        if content is None:
            continue
        for credential_name in credential_violations(content):
            violations.append(f"{entry.path}: non-empty {credential_name} literal")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Git repository to scan")
    parser.add_argument(
        "--history",
        action="store_true",
        help="scan every object reachable from local branches and tags",
    )
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    violations = scan_history(root) if arguments.history else scan(root)
    if violations:
        print("\n".join(violations))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
