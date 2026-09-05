"""Tests for local Doom runtime configuration."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pewpew.config import ConfigurationError, RuntimeConfig


def test_from_env_rejects_missing_crispy_executable() -> None:
    with pytest.raises(ConfigurationError, match="DOOMED_PRISM_CRISPY_EXE"):
        RuntimeConfig.from_env({})


def test_from_env_rejects_missing_iwad(tmp_path: Path) -> None:
    crispy_exe = tmp_path / "crispy-doom"
    crispy_exe.touch()

    with pytest.raises(ConfigurationError, match="DOOMED_PRISM_IWAD"):
        RuntimeConfig.from_env({"DOOMED_PRISM_CRISPY_EXE": str(crispy_exe)})


@pytest.mark.parametrize("variable", ["DOOMED_PRISM_CRISPY_EXE", "DOOMED_PRISM_IWAD"])
def test_from_env_rejects_nonexistent_paths(tmp_path: Path, variable: str) -> None:
    crispy_exe = tmp_path / "crispy-doom"
    iwad = tmp_path / "freedoom1.wad"
    if variable != "DOOMED_PRISM_CRISPY_EXE":
        crispy_exe.touch()
    if variable != "DOOMED_PRISM_IWAD":
        iwad.touch()
    env = {
        "DOOMED_PRISM_CRISPY_EXE": str(crispy_exe),
        "DOOMED_PRISM_IWAD": str(iwad),
    }

    with pytest.raises(ConfigurationError, match=variable):
        RuntimeConfig.from_env(env)


def test_from_env_rejects_iwad_with_non_wad_suffix(tmp_path: Path) -> None:
    crispy_exe = tmp_path / "crispy-doom"
    iwad = tmp_path / "freedoom1.txt"
    crispy_exe.touch()
    iwad.touch()

    with pytest.raises(ConfigurationError, match="DOOMED_PRISM_IWAD"):
        RuntimeConfig.from_env(
            {
                "DOOMED_PRISM_CRISPY_EXE": str(crispy_exe),
                "DOOMED_PRISM_IWAD": str(iwad),
            }
        )


def test_from_env_accepts_uppercase_wad_suffix(tmp_path: Path) -> None:
    crispy_exe = tmp_path / "crispy-doom"
    iwad = tmp_path / "FREEDOOM1.WAD"
    crispy_exe.touch()
    iwad.touch()

    config = RuntimeConfig.from_env(
        {
            "DOOMED_PRISM_CRISPY_EXE": str(crispy_exe),
            "DOOMED_PRISM_IWAD": str(iwad),
        }
    )

    assert config.iwad == iwad.resolve(strict=True)


def test_direct_constructor_enforces_path_invariants(tmp_path: Path) -> None:
    crispy_exe = tmp_path / "crispy-doom"
    iwad = tmp_path / "private-settings.txt"
    crispy_exe.touch()
    iwad.write_text("private file contents", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="DOOMED_PRISM_IWAD"):
        RuntimeConfig(crispy_exe=crispy_exe, iwad=iwad)


def test_viewport_constants_cannot_be_overridden_in_constructor(tmp_path: Path) -> None:
    crispy_exe = tmp_path / "crispy-doom"
    iwad = tmp_path / "freedoom1.wad"
    crispy_exe.touch()
    iwad.touch()

    with pytest.raises(TypeError, match="viewport_width"):
        RuntimeConfig(crispy_exe=crispy_exe, iwad=iwad, viewport_width=800)


def test_configuration_errors_do_not_echo_local_values_or_contents(tmp_path: Path) -> None:
    crispy_exe = tmp_path / "crispy-doom"
    iwad = tmp_path / "private-settings.txt"
    private_contents = "private file contents"
    crispy_exe.touch()
    iwad.write_text(private_contents, encoding="utf-8")

    with pytest.raises(ConfigurationError) as error:
        RuntimeConfig.from_env(
            {
                "DOOMED_PRISM_CRISPY_EXE": str(crispy_exe),
                "DOOMED_PRISM_IWAD": str(iwad),
            }
        )

    message = str(error.value)
    assert "DOOMED_PRISM_IWAD" in message
    assert str(iwad) not in message
    assert private_contents not in message


def test_from_env_returns_immutable_config_with_fixed_viewport_defaults(
    tmp_path: Path,
) -> None:
    crispy_exe = tmp_path / "crispy-doom"
    iwad = tmp_path / "freedoom1.wad"
    crispy_exe.touch()
    iwad.touch()

    config = RuntimeConfig.from_env(
        {
            "DOOMED_PRISM_CRISPY_EXE": str(crispy_exe),
            "DOOMED_PRISM_IWAD": str(iwad),
        }
    )

    assert config.crispy_exe == crispy_exe.resolve(strict=True)
    assert config.iwad == iwad.resolve(strict=True)
    assert (config.viewport_width, config.viewport_height) == (640, 480)
    assert (config.viewport_x, config.viewport_y) == (0, 80)
    with pytest.raises(FrozenInstanceError):
        config.viewport_width = 800  # type: ignore[misc]
