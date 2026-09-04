"""Behaviour tests for the publication-safety scanner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPOSITORY_ROOT / "scripts" / "check_publication_safety.py"


def _tracked_fixture(tmp_path: Path, relative_path: str, content: str = "fixture\n") -> Path:
    """Create a tiny repository containing one tracked fixture file."""
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    subprocess.run(["git", "init", "-q", str(fixture_root)], check=True)
    path = fixture_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(fixture_root), "add", relative_path], check=True)
    return fixture_root


def _commit_all(root: Path, message: str) -> str:
    """Commit the fixture index with repository-local non-sensitive identity."""
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(root), "commit", "-qm", message], check=True)
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


@pytest.mark.parametrize(
    ("relative_path", "content", "expected_violation"),
    [
        ("game.wad", "fixture\n", "game.wad"),
        ("mod.pk3", "fixture\n", "mod.pk3"),
        ("engine.exe", "fixture\n", "engine.exe"),
        ("engine.dll", "fixture\n", "engine.dll"),
        ("engine.so", "fixture\n", "engine.so"),
        (".env", "fixture\n", ".env"),
        ("app_key", "fixture\n", "app_key"),
        ("raven_framework/module.py", "fixture\n", "raven_framework/module.py"),
        ("settings.toml", 'app_' + 'key = "not-empty"\n', "app_key"),
        ("settings.toml", 'app_' + 'id = "not-empty"\n', "app_id"),
    ],
)
def test_scanner_rejects_tracked_publication_hazards(
    tmp_path: Path, relative_path: str, content: str, expected_violation: str
) -> None:
    fixture_root = _tracked_fixture(tmp_path, relative_path, content)

    result = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert expected_violation in result.stdout


def test_scanner_ignores_untracked_and_ignored_hazards(tmp_path: Path) -> None:
    fixture_root = _tracked_fixture(tmp_path, "safe.txt")
    (fixture_root / ".gitignore").write_text("ignored.wad\n", encoding="utf-8")
    (fixture_root / "ignored.wad").write_text("fixture\n", encoding="utf-8")
    (fixture_root / "untracked.wad").write_text("fixture\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == ""


def test_scanner_uses_staged_content_when_worktree_file_is_removed(tmp_path: Path) -> None:
    fixture_root = _tracked_fixture(tmp_path, "safe.txt")
    staged_path = fixture_root / "staged.py"
    staged_path.write_text('app_' + 'key = "staged-secret"\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(fixture_root), "add", "staged.py"], check=True)
    staged_path.unlink()

    result = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "staged.py" in result.stdout
    assert "app_key" in result.stdout


def test_scanner_does_not_follow_tracked_symlinks(tmp_path: Path) -> None:
    fixture_root = _tracked_fixture(tmp_path, "safe.txt")
    (fixture_root / ".gitignore").write_text("untracked-secret.txt\n", encoding="utf-8")
    (fixture_root / "untracked-secret.txt").write_text(
        'app_' + 'key = "untracked-secret"\n', encoding="utf-8"
    )
    (fixture_root / "safe-link.txt").symlink_to("untracked-secret.txt")
    subprocess.run(["git", "-C", str(fixture_root), "add", "safe-link.txt"], check=True)

    result = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == ""


def test_scanner_skips_credential_text_in_indexed_binary_blob(tmp_path: Path) -> None:
    fixture_root = _tracked_fixture(tmp_path, "safe.txt")
    binary_path = fixture_root / "payload.bin"
    binary_path.write_bytes(b"\0" + b"app_" + b'key = "binary-secret"\n')
    subprocess.run(["git", "-C", str(fixture_root), "add", "payload.bin"], check=True)

    result = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == ""


def test_scanner_reports_forbidden_binary_game_data_without_decoding(tmp_path: Path) -> None:
    fixture_root = _tracked_fixture(tmp_path, "safe.txt")
    game_data = fixture_root / "game.wad"
    game_data.write_bytes(b"\xff\0binary-game-data")
    subprocess.run(["git", "-C", str(fixture_root), "add", "game.wad"], check=True)

    result = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "game.wad" in result.stdout


def test_scanner_allows_empty_credential_literals(tmp_path: Path) -> None:
    fixture_root = _tracked_fixture(
        tmp_path, "settings.py", 'app_' + 'id="", app_' + 'key=""\n'
    )

    result = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("content", "expected_violation"),
    [
        ('app_' + 'key = r"raw-secret"\n', "app_key"),
        ('app_' + 'id = """triple-secret"""\n', "app_id"),
        ('app_' + 'key = ("parenthesized-secret")\n', "app_key"),
    ],
)
def test_scanner_rejects_extended_non_empty_credential_literals(
    tmp_path: Path, content: str, expected_violation: str
) -> None:
    fixture_root = _tracked_fixture(tmp_path, "settings.py", content)

    result = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert expected_violation in result.stdout


@pytest.mark.parametrize(
    "relative_path",
    [
        "GAME.WAD",
        "PLUGIN.PK3",
        "ENGINE.EXE",
        "LIBRARY.DLL",
        "MODULE.SO",
        ".ENV",
        "APP_KEY",
        "RAVEN_FRAMEWORK/module.py",
    ],
)
def test_scanner_rejects_forbidden_suffixes_and_names_case_insensitively(
    tmp_path: Path, relative_path: str
) -> None:
    fixture_root = _tracked_fixture(tmp_path, relative_path)

    result = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert relative_path in result.stdout


@pytest.mark.parametrize(
    ("content", "expected_violation"),
    [
        ('{"app_' + 'key": "json-secret"}\n', "app_key"),
        ("'app_" + "id': 'yaml-secret'\n", "app_id"),
    ],
)
def test_scanner_rejects_quoted_json_and_yaml_credential_keys(
    tmp_path: Path, content: str, expected_violation: str
) -> None:
    fixture_root = _tracked_fixture(tmp_path, "settings.txt", content)

    result = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert expected_violation in result.stdout


def test_scanner_validates_gitlink_path_before_skipping_gitlink_content(
    tmp_path: Path,
) -> None:
    fixture_root = _tracked_fixture(tmp_path, "safe.txt")
    commit = _commit_all(fixture_root, "safe base")
    subprocess.run(
        [
            "git",
            "-C",
            str(fixture_root),
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{commit},raven_framework",
        ],
        check=True,
    )

    result = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "raven_framework" in result.stdout


def test_history_mode_rejects_a_forbidden_file_removed_from_the_current_tree(
    tmp_path: Path,
) -> None:
    fixture_root = _tracked_fixture(tmp_path, "safe.txt")
    _commit_all(fixture_root, "safe base")
    historical_path = fixture_root / "REMOVED.WAD"
    historical_path.write_text("historical fixture\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(fixture_root), "add", historical_path.name], check=True
    )
    _commit_all(fixture_root, "add forbidden history fixture")
    subprocess.run(
        ["git", "-C", str(fixture_root), "rm", "-q", historical_path.name],
        check=True,
    )
    _commit_all(fixture_root, "remove forbidden history fixture")

    current = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )
    history = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root), "--history"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert current.returncode == 0
    assert history.returncode == 1
    assert historical_path.name in history.stdout


def test_history_mode_checks_a_forbidden_old_name_when_its_blob_is_reused(
    tmp_path: Path,
) -> None:
    fixture_root = _tracked_fixture(
        tmp_path, "REMOVED.WAD", content="reused historical fixture\n"
    )
    _commit_all(fixture_root, "add forbidden name")
    subprocess.run(
        ["git", "-C", str(fixture_root), "mv", "REMOVED.WAD", "safe.txt"],
        check=True,
    )
    _commit_all(fixture_root, "reuse blob under safe name")

    current = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )
    history = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root), "--history"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert current.returncode == 0
    assert history.returncode == 1
    assert "REMOVED.WAD" in history.stdout


def test_history_mode_checks_a_removed_gitlink_path_without_reading_its_commit(
    tmp_path: Path,
) -> None:
    fixture_root = _tracked_fixture(tmp_path, "safe.txt")
    target_commit = _commit_all(fixture_root, "safe base")
    subprocess.run(
        [
            "git",
            "-C",
            str(fixture_root),
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{target_commit},raven_framework",
        ],
        check=True,
    )
    _commit_all(fixture_root, "add forbidden gitlink")
    subprocess.run(
        ["git", "-C", str(fixture_root), "rm", "--cached", "-q", "raven_framework"],
        check=True,
    )
    _commit_all(fixture_root, "remove forbidden gitlink")

    current = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root)],
        text=True,
        capture_output=True,
        check=False,
    )
    history = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(fixture_root), "--history"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert current.returncode == 0
    assert history.returncode == 1
    assert "raven_framework" in history.stdout
