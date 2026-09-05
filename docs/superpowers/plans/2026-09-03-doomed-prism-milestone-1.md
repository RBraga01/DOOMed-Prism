# DOOMed Prism Milestone 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that a keyboard-playable Crispy Doom process can occupy the intended 640×480 viewport inside a 640×640 Raven application and remain visible in both Raw and optically composited simulator modes.

**Architecture:** PewPew Engine owns a Qt/Raven host widget and supervises an externally installed Crispy Doom process. On Windows, a small platform adapter discovers the SDL window, reparents it into the host viewport, and restores or closes it safely. The experiment has a hard decision gate: if Raven Simulator cannot capture the native child window, this approach is rejected and the next milestone will integrate a GPL-compatible framebuffer/rendering path instead of using desktop screen capture.

**Tech Stack:** Python 3.10+, PySide6, Raven Framework alpha v1.0.4 installed separately, pytest, Windows `ctypes`, Crispy Doom installed separately for the spike.

**Spec:** `docs/superpowers/specs/2026-09-02-doomed-prism-design.md`

## Global Constraints

- Every commit must be safe to publish. Never commit Raven-owned source, commercial IWADs, credentials, generated binaries, screenshots containing private information, or unreviewed third-party assets.
- Raven Framework and Crispy Doom are external development dependencies in this milestone. Store only their paths in ignored local configuration or environment variables.
- Automated tests must run without Raven Framework, Crispy Doom, or an IWAD by using project-owned fakes.
- The only accepted viewport is 640×480 at `(0, 80)` inside the writable 640×640 app surface.
- Do not treat black pixels as opaque. Simulator Night, Day, Outdoors, and Camera modes remain required visual checks.
- Do not add gaze, blink, voice, IPC, performance governors, ARM64 builds, or Prism deployment in this milestone.
- Do not use screen scraping, desktop capture, or video streaming to disguise a failed native-window integration.

---

## Task 1: Bootstrap a publication-safe Python project

**Files:**

- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `README.md`
- Create: `src/pewpew/__init__.py`
- Create: `tests/test_publication_safety.py`
- Create: `scripts/check_publication_safety.py`

- [ ] **Step 1: Write the failing repository-safety test**

Create a test that runs `scripts/check_publication_safety.py --root <repo>` and fails when a fixture repository contains any of these tracked patterns: `*.wad`, `*.pk3`, `*.exe`, `*.dll`, `*.so`, `.env`, `app_key`, or `raven_framework/`. The scanner must inspect tracked paths with `git ls-files` and scan tracked text for the two credential names `app_key` and `app_id` when followed by a non-empty literal.

- [ ] **Step 2: Run the test and confirm failure**

Run: `python -m pytest tests/test_publication_safety.py -q`

Expected: FAIL because the scanner does not exist.

- [ ] **Step 3: Implement the project skeleton and scanner**

Use a `src` layout, Python `>=3.10`, and these optional dependency groups:

```toml
[project.optional-dependencies]
dev = ["pytest>=8,<9", "pytest-qt>=4.4,<5"]
raven = ["PySide6>=6.7,<7"]
```

Expose `doomed-prism = "pewpew.cli:main"` but create the CLI in Task 3. License original PewPew Engine code as `GPL-2.0-or-later`, preserving freedom to combine it with future Crispy Doom modifications. In `.gitignore`, block all forbidden binary/game-data patterns plus `.venv/`, `__pycache__/`, `.pytest_cache/`, `local.toml`, and `artifacts/`.

The scanner exits `0` when clean and `1` with one line per violation. It must not read ignored or untracked files.

- [ ] **Step 4: Run the tests and scanner**

Run:

```bash
python -m pytest tests/test_publication_safety.py -q
python scripts/check_publication_safety.py --root .
```

Expected: PASS and exit code 0.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore LICENSE README.md src tests scripts
git commit -m "chore: bootstrap publication-safe PewPew project"
```

## Task 2: Define validated local runtime configuration

**Files:**

- Create: `src/pewpew/config.py`
- Create: `tests/test_config.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing configuration tests**

Cover `RuntimeConfig.from_env(env: Mapping[str, str]) -> RuntimeConfig` with:

- missing `DOOMED_PRISM_CRISPY_EXE`;
- missing `DOOMED_PRISM_IWAD`;
- nonexistent paths;
- IWAD suffix other than `.wad`;
- valid paths producing an immutable config;
- fixed defaults `viewport_width=640`, `viewport_height=480`, `viewport_x=0`, `viewport_y=80`.

Errors must use `ConfigurationError` and name the invalid variable without printing secrets or file contents.

- [ ] **Step 2: Confirm failure**

Run: `python -m pytest tests/test_config.py -q`

Expected: FAIL because `pewpew.config` does not exist.

- [ ] **Step 3: Implement the minimum configuration model**

Implement a frozen dataclass. Resolve both paths with `Path.resolve(strict=True)`, require the engine path to be a file, and require the IWAD path to be a `.wad` file. Do not serialize either path into repository files or logs.

- [ ] **Step 4: Document local setup and verify**

Document PowerShell-only local variables:

```powershell
$env:DOOMED_PRISM_CRISPY_EXE = "C:\path\to\crispy-doom.exe"
$env:DOOMED_PRISM_IWAD = "C:\path\to\freedoom1.wad"
```

State explicitly that users may point to a lawfully obtained commercial IWAD, but must never add it to Git.

Run: `python -m pytest tests/test_config.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/config.py tests/test_config.py README.md
git commit -m "feat: validate external Doom runtime paths"
```

## Task 3: Supervise Crispy Doom without Raven dependencies

**Files:**

- Create: `src/pewpew/engine.py`
- Create: `src/pewpew/cli.py`
- Create: `tests/fakes/fake_doom.py`
- Create: `tests/test_engine.py`

- [ ] **Step 1: Write failing process-lifecycle tests**

Specify `DoomProcess(config, popen_factory=subprocess.Popen)` with:

- `start() -> int` launches exactly once and returns the PID;
- command arguments are `[exe, "-iwad", iwad, "-window", "-width", "640", "-height", "480"]`;
- `start()` raises `EngineAlreadyRunning` on a second live start;
- `poll() -> int | None` forwards process state;
- `stop(timeout_s=3.0)` calls `terminate`, waits, then calls `kill` only after timeout;
- `stop()` is idempotent;
- a context-manager exit always stops the child.

Use a fake `Popen` object; do not launch Crispy Doom in the unit tests.

- [ ] **Step 2: Confirm failure**

Run: `python -m pytest tests/test_engine.py -q`

Expected: FAIL because `pewpew.engine` does not exist.

- [ ] **Step 3: Implement supervision and a diagnostic CLI**

Implement only `validate` and `run-desktop` subcommands. `validate` prints path types and validity but not full paths. `run-desktop` will call the Qt host added later; until Task 5 it must exit with the explicit message `desktop host is not installed` and code `2`.

- [ ] **Step 4: Verify**

Run:

```bash
python -m pytest tests/test_engine.py -q
python -m pewpew.cli validate
```

Expected: tests pass; validation either succeeds with local variables or exits cleanly with a named configuration error.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/engine.py src/pewpew/cli.py tests/fakes tests/test_engine.py
git commit -m "feat: supervise external Crispy Doom process"
```

## Task 4: Implement the Windows native-window adapter

**Files:**

- Create: `src/pewpew/windows.py`
- Create: `tests/test_windows.py`

- [ ] **Step 1: Write failing Win32 adapter tests**

Inject a `Win32Api` protocol so tests run on every platform. Specify:

```python
find_top_level_window(pid: int, timeout_s: float) -> int
embed_window(child_hwnd: int, parent_hwnd: int, width: int, height: int) -> EmbeddedWindow
EmbeddedWindow.restore() -> None
```

Test these behaviours:

- enumeration ignores invisible windows and windows owned by another PID;
- discovery retries until timeout and raises `WindowDiscoveryTimeout`;
- embedding records the original parent, style, and rectangle;
- embedding sets `WS_CHILD`, removes `WS_POPUP`, assigns the Qt viewport parent, and sizes the child to 640×480;
- `restore()` reinstates the original parent/style/rectangle exactly once;
- any partial embedding failure rolls back prior mutations.

- [ ] **Step 2: Confirm failure**

Run: `python -m pytest tests/test_windows.py -q`

Expected: FAIL because `pewpew.windows` does not exist.

- [ ] **Step 3: Implement with guarded `ctypes` calls**

Import `ctypes.windll.user32` only when `sys.platform == "win32"`. Use `EnumWindows`, `GetWindowThreadProcessId`, `IsWindowVisible`, `GetParent`, `SetParent`, `GetWindowLongPtrW`, `SetWindowLongPtrW`, `GetWindowRect`, `SetWindowPos`, and `ShowWindow`. On other platforms, constructing the real adapter raises `UnsupportedPlatform` while protocol-based tests remain runnable.

- [ ] **Step 4: Verify**

Run: `python -m pytest tests/test_windows.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/windows.py tests/test_windows.py
git commit -m "feat: add reversible Windows SDL window embedding"
```

## Task 5: Build the 640×640 Raven host without copying Raven code

**Files:**

- Create: `src/pewpew/host_widget.py`
- Create: `src/pewpew/raven_app.py`
- Create: `tests/test_host_widget.py`
- Modify: `src/pewpew/cli.py`

- [ ] **Step 1: Write failing geometry and cleanup tests**

With `pytest-qt`, specify `DoomHostWidget` as a 640×640 `QWidget` containing a plain native child `QWidget` named `viewport`. Assert exact geometry `(0, 80, 640, 480)`, no painted opaque background, and a shutdown signal that stops the engine and restores the embedded window.

The unit test imports only `host_widget.py`; it must not require Raven Framework.

- [ ] **Step 2: Confirm failure**

Run: `python -m pytest tests/test_host_widget.py -q`

Expected: FAIL because the host widget does not exist.

- [ ] **Step 3: Implement the neutral Qt host**

Set `WA_NativeWindow` on `viewport`, call `winId()` before embedding, and leave the 80-pixel upper and lower bands unpainted. Add no controls over the gameplay area. Connect both widget close and Qt application shutdown to one idempotent cleanup method.

- [ ] **Step 4: Add the optional Raven wrapper**

In `raven_app.py`, import `RavenApp` and `RunApp` inside callable entry points, never at module import time. Implement `DoomedPrismApp(RavenApp)` with one `DoomHostWidget` added at `(0, 0)` and invoke it through:

```python
RunApp.run(lambda: DoomedPrismApp(config), app_id="", app_key="")
```

Do not vendor Raven code. Update `run-desktop` to construct the validated config and call this entry point.

- [ ] **Step 5: Verify without Raven installed**

Run:

```bash
python -m pytest tests/test_host_widget.py -q
python -m pytest -q
python scripts/check_publication_safety.py --root .
```

Expected: all automated tests pass and the repository scan is clean.

- [ ] **Step 6: Commit**

```bash
git add src/pewpew/host_widget.py src/pewpew/raven_app.py src/pewpew/cli.py tests/test_host_widget.py
git commit -m "feat: host Doom viewport in Raven app surface"
```

## Task 6: Run the simulator capture decision gate

**Files:**

- Create: `docs/validation/milestone-1-checklist.md`
- Create when testing: `artifacts/milestone-1/` (ignored)
- Modify after testing: `docs/validation/milestone-1-result.md`

- [ ] **Step 1: Record the environment before launching**

In the result document, record OS version, Python version, Raven Framework commit/version, Crispy Doom version/commit, IWAD name and checksum only when redistribution permits, GPU, and display scaling. Do not record private filesystem paths or Raven credentials.

- [ ] **Step 2: Launch through Raven Simulator**

On the Windows machine with Raven Framework installed separately:

```powershell
python -m pip install -e ".[dev,raven]"
doomed-prism validate
doomed-prism run-desktop
```

Confirm Crispy Doom is keyboard-playable and exactly fills the 640×480 viewport without covering either 80-pixel margin or the Raven home control.

- [ ] **Step 3: Capture objective evidence**

Save local screenshots in the ignored artifact directory for Raw, Night, Day, Outdoors, and Camera modes. For each mode, record:

- whether live game pixels appear inside the app surface;
- whether frames update while playing;
- whether the viewport remains at `(0, 80, 640, 480)`;
- whether the simulator's app capture includes the SDL child rather than a blank rectangle;
- whether closing Raven Simulator terminates Crispy Doom without an orphan process.

- [ ] **Step 4: Apply the hard decision**

Mark **PASS — native embedding viable** only if live SDL pixels appear in Raw and every available optical mode, keyboard play works, geometry is correct, and cleanup leaves no child process.

Mark **FAIL — framebuffer integration required** if any composited mode omits or freezes the SDL child. Do not patch around failure with screen capture. Open the next design task to choose between a Crispy Doom source modification that exposes frames and a shared OpenGL ES/Qt rendering surface, retaining GPL source and notices.

- [ ] **Step 5: Run final automated verification**

Run:

```bash
python -m pytest -q
python scripts/check_publication_safety.py --root .
git diff --check
git status --short
```

Expected: tests pass, scanner exits 0, no whitespace errors, and only the intended result document is uncommitted.

- [ ] **Step 6: Commit the result, not restricted evidence**

```bash
git add docs/validation/milestone-1-checklist.md docs/validation/milestone-1-result.md
git commit -m "docs: record Raven simulator embedding result"
```

## Milestone Exit Criteria

The milestone is complete only when all automated tests pass, the publication-safety scan is clean, and `milestone-1-result.md` contains either a reproducible PASS or FAIL decision. A FAIL is a valid engineering result: it retires an unsafe architecture before gaze, voice, and ARM64 work begins.
