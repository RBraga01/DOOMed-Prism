"""Headless-engine runtime smoke test: does DOOMED_PRISM_HEADLESS_ENGINE let the
patched engine run -- framebuffer export, IPC handshake, input round-trip, and
clean shutdown -- with no real display server available at all?

This is deliberately narrower proof than "no visible surface on Raven Prism
hardware": succeeding with DISPLAY unset and no Xvfb is strong evidence that
SDL's dummy video driver is in effect and that the engine no longer depends on
a real display server, not a claim about what the Raven compositor shows on
physical hardware. The final "only the Raven app is visible" acceptance
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

from pewpew.framebuffer import FrameReader  # noqa: E402
from pewpew.input.actions import Action  # noqa: E402
from pewpew.ipc.protocol import Message  # noqa: E402
from pewpew.ipc.server import IpcServer  # noqa: E402

SOCKET_PATH = "/tmp/doomed-prism-ipc-headless-ci.sock"
FB_NAME = "doomed-prism-fb-headless-ci"
CONNECT_TIMEOUT_S = 30.0
OPEN_TIMEOUT_S = 30.0
SAMPLE_FRAMES = 90  # ~1.5s at 60Hz -- enough to prove frame_counter is moving


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

    server = IpcServer(address_factory=_fixed_factory)
    server.start()
    # DISPLAY/XAUTHORITY are stripped, not just left unset by the caller --
    # this makes the "no real display server required" proof self-contained
    # regardless of whatever the outer CI job happens to export.
    env = {
        k: v for k, v in os.environ.items() if k not in ("DISPLAY", "XAUTHORITY")
    }
    env.update(
        {
            "DOOMED_PRISM_HEADLESS_ENGINE": "1",
            "DOOMED_PRISM_IPC_ADDR": SOCKET_PATH,
            "DOOMED_PRISM_FB_NAME": FB_NAME,
            "DOOMED_PRISM_WARP": "1 1",
            "SDL_AUDIODRIVER": "dummy",
        }
    )
    proc = subprocess.Popen(
        [str(exe), "-iwad", str(iwad), "-window", "-width", "640", "-height", "480",
         "-warp", "1", "1", "-skill", "3", "-nomusic", "-nosound"],
        env=env,
    )
    try:
        deadline = time.monotonic() + CONNECT_TIMEOUT_S
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                _fail(f"engine exited early ({proc.returncode}) -- with no DISPLAY, this "
                      "usually means SDL_VIDEODRIVER=dummy did not take effect")
            server.poll()
            if server.is_connected:
                break
            time.sleep(0.05)
        else:
            _fail("engine never completed the IPC handshake")
        print("no DISPLAY, no Xvfb: engine started and completed the IPC handshake")

        reader = FrameReader(FB_NAME)
        open_deadline = time.monotonic() + OPEN_TIMEOUT_S
        while time.monotonic() < open_deadline:
            if proc.poll() is not None:
                _fail(f"engine exited early ({proc.returncode}) before the framebuffer opened")
            if reader.try_open():
                break
            time.sleep(0.05)
        else:
            _fail("framebuffer segment never became readable")
        print(f"framebuffer {FB_NAME}: opened")

        counters: set[int] = set()
        for i in range(SAMPLE_FRAMES):
            if i % 15 == 0:
                server.send(Message.pulse(int(Action.FIRE)))
            server.poll()
            if proc.poll() is not None:
                _fail(f"engine exited early ({proc.returncode}) while sampling frames")
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
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=4)

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
