"""Diagnostic command-line interface for local DOOMed Prism setup."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from pewpew.config import ConfigurationError, RuntimeConfig


def main(argv: Sequence[str] | None = None) -> int:
    """Run a diagnostic subcommand without revealing local runtime paths."""
    parser = argparse.ArgumentParser(prog="doomed-prism")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("validate")
    subcommands.add_parser("run-desktop")
    arguments = parser.parse_args(argv)

    if arguments.command == "validate":
        return _validate()

    return _run_desktop()


def _validate() -> int:
    try:
        RuntimeConfig.from_env(os.environ)
    except ConfigurationError as error:
        print(f"ConfigurationError: {error}", file=sys.stderr)
        return 2

    print("crispy_exe: file (valid)")
    print("iwad: .wad file (valid)")
    return 0


def _run_desktop() -> int:
    try:
        config = RuntimeConfig.from_env(os.environ)
    except ConfigurationError as error:
        print(f"ConfigurationError: {error}", file=sys.stderr)
        return 2

    from pewpew.raven_app import run_desktop

    run_desktop(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
