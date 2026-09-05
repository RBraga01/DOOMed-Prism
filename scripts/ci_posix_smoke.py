"""POSIX runtime smoke test for the shared-memory frame-export path.

A successful Linux *build* proves only that the ``shm_open`` branch of
``i_framebuffer_export.c`` compiles and links. This script exercises that branch
at *runtime*: it launches the patched Crispy Doom engine with
``DOOMED_PRISM_FB_NAME`` set, attaches with ``pewpew.framebuffer.FrameReader``,
verifies a valid 640x480 segment whose ``frame_counter`` advances, then confirms
a clean teardown.

Usage::

    python scripts/ci_posix_smoke.py <crispy-doom-exe> <iwad-path>

Exits 0 on success, 1 on any failure. Linux only (uses ``/dev/shm`` and POSIX
signals); on other platforms it prints a skip line and exits 0.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from pewpew.framebuffer import (  # noqa: E402  (path insert must precede import)
    PIXEL_FORMAT_ARGB8888,
    STRIDE,
    FrameReader,
)

SEGMENT_NAME = "doomed-prism-fb-ci"
OPEN_TIMEOUT_S = 30.0
SAMPLE_WINDOW_S = 5.0
MIN_DISTINCT_COUNTERS = 5


def _fail(message: str) -> None:
    print(f"POSIX runtime smoke: FAIL - {message}")
    sys.exit(1)


def _kill(process: subprocess.Popen) -> str:
    """Escalate SIGINT -> SIGTERM -> SIGKILL. Return the signal that worked."""
    for name, sig, wait_s in (
        ("SIGINT", signal.SIGINT, 6.0),
        ("SIGTERM", signal.SIGTERM, 4.0),
        ("SIGKILL", signal.SIGKILL, 4.0),
    ):
        process.send_signal(sig)
        try:
            process.wait(timeout=wait_s)
            return name
        except subprocess.TimeoutExpired:
            continue
    return "none (still alive)"


def main() -> int:
    if sys.platform == "win32":
        print("POSIX runtime smoke: skipped (not a POSIX platform)")
        return 0
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    exe = Path(sys.argv[1]).resolve()
    iwad = Path(sys.argv[2]).resolve()
    if not exe.is_file():
        _fail(f"engine executable not found: {exe}")
    if not iwad.is_file():
        _fail(f"IWAD not found: {iwad}")

    shm_path = Path("/dev/shm") / SEGMENT_NAME
    shm_path.unlink(missing_ok=True)

    env = {
        **os.environ,
        "DOOMED_PRISM_FB_NAME": SEGMENT_NAME,
        "SDL_AUDIODRIVER": "dummy",
    }
    command = [
        str(exe),
        "-iwad",
        str(iwad),
        "-window",
        "-width",
        "640",
        "-height",
        "480",
        "-nomusic",
        "-nosound",
    ]
    print(f"launching: {' '.join(command)}")
    process = subprocess.Popen(command, env=env)

    try:
        reader = FrameReader(SEGMENT_NAME)
        deadline = time.monotonic() + OPEN_TIMEOUT_S
        while time.monotonic() < deadline:
            if process.poll() is not None:
                _fail(f"engine exited early with code {process.returncode}")
            if reader.try_open():
                break
            time.sleep(0.1)
        else:
            _fail(f"segment {SEGMENT_NAME!r} never became readable within "
                  f"{OPEN_TIMEOUT_S:.0f}s")

        print("segment opened; sampling frames")
        counters: set[int] = set()
        first: object | None = None
        sample_deadline = time.monotonic() + SAMPLE_WINDOW_S
        while time.monotonic() < sample_deadline:
            frame = reader.latest()
            if frame is not None:
                if first is None:
                    first = frame
                counters.add(frame.counter)
            time.sleep(0.05)
        reader.close()

        if first is None:
            _fail("segment opened but latest() never returned a frame")
        if (first.width, first.height, first.stride) != (640, 480, STRIDE):
            _fail(f"unexpected dimensions "
                  f"{(first.width, first.height, first.stride)} "
                  f"(want (640, 480, {STRIDE}))")
        if first.pixel_format != PIXEL_FORMAT_ARGB8888:
            _fail(f"unexpected pixel format {first.pixel_format:#x}")
        if len(counters) < MIN_DISTINCT_COUNTERS:
            _fail(f"frame_counter is not advancing "
                  f"({len(counters)} distinct value(s) over {SAMPLE_WINDOW_S:.0f}s)")
        print(f"frame_counter advancing: {len(counters)} distinct values, "
              f"sample {sorted(counters)[:5]}")
        print(f"segment shape OK: 640x480, stride {STRIDE}, "
              f"format {first.pixel_format:#x}")
    finally:
        stop_signal = _kill(process)
    print(f"engine stopped via {stop_signal}")

    if process.poll() is None:
        _fail("engine process still alive after SIGKILL")

    leftover = subprocess.run(
        ["pgrep", "-x", "crispy-doom"], capture_output=True, text=True
    )
    if leftover.returncode == 0:
        _fail(f"orphan crispy-doom process(es): {leftover.stdout.split()}")

    if stop_signal == "SIGINT":
        # Clean SIGINT runs Crispy's I_AtExit -> FB_Export_Shutdown, which
        # shm_unlink()s the segment. This is the graceful-teardown path the
        # Milestone 2 review noted was only ever verified by forced kill.
        if shm_path.exists():
            _fail("clean SIGINT exit left /dev/shm segment behind "
                  "(FB_Export_Shutdown did not run)")
        print("clean SIGINT teardown: segment removed by FB_Export_Shutdown")
    else:
        # Forced kill does not run atexit handlers; the segment is expected to
        # linger. Best-effort unlink, as pewpew.engine.DoomProcess.stop() does.
        shm_path.unlink(missing_ok=True)
        print(f"forced stop ({stop_signal}); segment cleaned up best-effort")

    print("POSIX runtime smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
