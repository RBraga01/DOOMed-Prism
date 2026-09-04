# DOOMed Prism

DOOMed Prism is the publication-safe Python foundation for the PewPew Engine
project. This repository intentionally contains no Raven framework code, Doom
game data, executables, shared libraries, or credentials.

## Development

Use Python 3.10 or later. Install development dependencies with:

```bash
python -m pip install -e '.[dev]'
```

Before committing, scan exactly the staged index. Before a release or public
handoff, also scan every object reachable from local branches and tags:

```bash
python scripts/check_publication_safety.py --root .
python scripts/check_publication_safety.py --root . --history
```

## Local Doom runtime

Install Crispy Doom and provide an IWAD locally. In PowerShell, set the paths
for the current session:

```powershell
$env:DOOMED_PRISM_CRISPY_EXE = "C:\path\to\crispy-doom.exe"
$env:DOOMED_PRISM_IWAD = "C:\path\to\freedoom1.wad"
```

You may instead point `DOOMED_PRISM_IWAD` to a lawfully obtained commercial
IWAD, but never add an IWAD to Git.

Original PewPew Engine code is licensed under GPL-2.0-or-later. Source
distributions include the canonical GPL-2.0 text and deliberately exclude the
test suite, whose dependencies are development-only.
