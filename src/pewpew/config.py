"""Validated local runtime configuration for DOOMed Prism."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


class ConfigurationError(ValueError):
    """Raised when a required local runtime setting is invalid."""


@dataclass(frozen=True)
class RuntimeConfig:
    """The local executable, IWAD, and fixed Prism viewport settings."""

    crispy_exe: Path
    iwad: Path
    viewport_width: int = field(default=640, init=False)
    viewport_height: int = field(default=480, init=False)
    viewport_x: int = field(default=0, init=False)
    viewport_y: int = field(default=80, init=False)

    def __post_init__(self) -> None:
        """Validate direct construction as well as environment construction."""
        crispy_exe = _validated_file(self.crispy_exe, "DOOMED_PRISM_CRISPY_EXE")
        iwad = _validated_file(self.iwad, "DOOMED_PRISM_IWAD")
        if iwad.suffix.lower() != ".wad":
            raise ConfigurationError("DOOMED_PRISM_IWAD must name a .wad file")
        object.__setattr__(self, "crispy_exe", crispy_exe)
        object.__setattr__(self, "iwad", iwad)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> RuntimeConfig:
        """Build configuration from local environment variables."""
        return cls(
            crispy_exe=Path(_required_setting(env, "DOOMED_PRISM_CRISPY_EXE")),
            iwad=Path(_required_setting(env, "DOOMED_PRISM_IWAD")),
        )


def _required_setting(env: Mapping[str, str], variable: str) -> str:
    """Return a required environment setting without exposing its value."""
    value = env.get(variable)
    if not value:
        raise ConfigurationError(f"{variable} is required")
    return value


def _validated_file(value: str | Path, variable: str) -> Path:
    """Resolve a supplied path without exposing its value."""
    try:
        path = Path(value).resolve(strict=True)
    except (OSError, TypeError):
        raise ConfigurationError(f"{variable} must name an existing file") from None
    if not path.is_file():
        raise ConfigurationError(f"{variable} must name a file")
    return path
