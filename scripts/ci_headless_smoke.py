"""Headless-engine runtime smoke test: with DOOMED_PRISM_HEADLESS_ENGINE set,
does DoomProcess.start() actually launch a Crispy that runs -- framebuffer
export, IPC handshake, input round-trip, clean shutdown -- with no real
display server available at all?

Launches through the real pewpew.engine.DoomProcess (not a hand-rolled
subprocess.Popen), so this exercises the exact mechanism the env var ships:
DOOMED_PRISM_HEADLESS_ENGINE set in THIS process's own environment before
DoomProcess.start() reads it and translates it into SDL_VIDEODRIVER=dummy
for the child.

This is deliberately narrower proof than "no visible surface on Raven Prism
hardware": succeeding with DISPLAY unset and no Xvfb is strong evidence that
SDL's dummy video driver is in effect and that the engine no longer depends
on a real display server, not a claim about what the Raven compositor shows
on physical hardware. The final "only the Raven app is visible" acceptance
criterion remains a separate, physical-Prism validation gate (Parth).

Usage: python scripts/ci_headless_smoke.py <crispy-doom-exe> <iwad-path>
Exits 0 on success or non-POSIX; 1 on any failure. Linux only.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from pewpew.config import RuntimeConfig  # noqa: E402
from pewpew.engine import DoomProcess  # noqa: E402
from pewpew.framebuffer import FrameReader  # noqa: E402
from pewpew.input.actions import Action  # noqa: E402
from pewpew.ipc.protocol import Message  # noqa: E402
from pewpew.ipc.server import IpcServer  # noqa: E402

SOCKET_PATH = "/tmp/doomed-prism-ipc-headless-ci.sock"
CONNECT_TIMEOUT_S = 30.0
OPEN_TIMEOUT_S = 30.0
SAMPLE_FRAMES = 90  # ~1.5s at 60Hz -- enough to prove frame_counter is moving
STOP_TIMEOUT_S = 6.0


def _fixed_factory():
    try:
        os.unlink(SOCKET_PATH)
    except OSError:
        pass
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(SOCKET_PATH)
    listener.listen(2)
    listener.setblocking(False)
    return listener, SOCKET_PATH


def _sigint_close(pid: int) -> None:
    os.kill(pid, signal.SIGINT)


def _fail(msg: str) -> None:
    print(f"Headless engine smoke: FAIL - {msg}")
    sys.exit(1)


def main() -> int:
    if sys.platform == "win32":
        print("Headless engine smoke: skipped (not a POSIX platform)")
        return 0
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    exe, iwad = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if not exe.is_file() or not iwad.is_file():
        _fail("engine or IWAD not found")

    # DISPLAY/XAUTHORITY are removed from THIS process's own environment, and
    # DOOMED_PRISM_HEADLESS_ENGINE is set here too -- DoomProcess.start()
    # builds the child's env from os.environ, so mutating it here (rather
    # than a hand-built child dict) is what makes this exercise the actual
    # shipped launch path instead of a parallel reimplementation of it.
    os.environ.pop("DISPLAY", None)
    os.environ.pop("XAUTHORITY", None)
    os.environ["DOOMED_PRISM_HEADLESS_ENGINE"] = "1"
    os.environ["DOOMED_PRISM_WARP"] = "1 1"
    os.environ["DOOMED_PRISM_SKILL"] = "3"
    os.environ["SDL_AUDIODRIVER"] = "dummy"

    server = IpcServer(address_factory=_fixed_factory)
    server.start()

    config = RuntimeConfig(crispy_exe=exe, iwad=iwad)
    # _sigint_close: DoomProcess's default graceful_close is Windows-only and
    # no-ops on POSIX, which would make stop() wait out a pointless timeout
    # before escalating to terminate() -- SIGINT matches how the engine is
    # already shut down elsewhere on POSIX (ci_ipc_smoke.py, ci_posix_smoke.py).
    engine = DoomProcess(config, graceful_close=_sigint_close)
    engine.start(ipc_address=SOCKET_PATH)
    fb_name = engine.frame_segment_name
    try:
        deadline = time.monotonic() + CONNECT_TIMEOUT_S
        while time.monotonic() < deadline:
            if engine.poll() is not None:
                _fail(f"engine exited early ({engine.poll()}) -- with no DISPLAY, this "
                      "usually means SDL_VIDEODRIVER=dummy did not take effect")
            server.poll()
            if server.is_connected:
                break
            time.sleep(0.05)
        else:
            _fail("engine never completed the IPC handshake")
        print("no DISPLAY, no Xvfb: DoomProcess.start() launched the engine and "
              "completed the IPC handshake")

        reader = FrameReader(fb_name)
        open_deadline = time.monotonic() + OPEN_TIMEOUT_S
        while time.monotonic() < open_deadline:
            if engine.poll() is not None:
                _fail(f"engine exited early ({engine.poll()}) before the framebuffer opened")
            if reader.try_open():
                break
            time.sleep(0.05)
        else:
            _fail("framebuffer segment never became readable")
        print(f"framebuffer {fb_name}: opened")

        counters: set[int] = set()
        for i in range(SAMPLE_FRAMES):
            if i % 15 == 0:
                server.send(Message.pulse(int(Action.FIRE)))
            server.poll()
            if engine.poll() is not None:
                _fail(f"engine exited early ({engine.poll()}) while sampling frames")
            frame = reader.latest()
            if frame is not None:
                counters.add(frame.counter)
            time.sleep(1 / 60)
        reader.close()
        if not server.is_connected:
            _fail("engine disconnected while sampling frames")
        if len(counters) < 10:
            _fail(f"frame_counter did not advance under headless IPC input ({len(counters)})")
        print(f"frame_counter advancing headless: {len(counters)} distinct values "
              f"(IPC input round-trip confirmed live)")
    finally:
        server.close()
        engine.stop(timeout_s=STOP_TIMEOUT_S)

    leftover = subprocess.run(["pgrep", "-x", "crispy-doom"], capture_output=True, text=True)
    if leftover.returncode == 0:
        _fail("orphan crispy-doom process")
    if Path(SOCKET_PATH).exists():
        os.unlink(SOCKET_PATH)
        _fail("socket path left behind after server.close()")
    print(f"socket {Path(SOCKET_PATH).name}: absent after teardown -- clean shutdown")
    print("Headless engine smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
