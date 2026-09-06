"""POSIX IPC runtime smoke test: does the patched engine accept and act on IPC input?

Usage: python scripts/ci_ipc_smoke.py <crispy-doom-exe> <iwad-path>
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
from pewpew.ipc.protocol import Message  # noqa: E402
from pewpew.ipc.server import IpcServer  # noqa: E402

SOCKET_PATH = "/tmp/doomed-prism-ipc-ci.sock"
FB_NAME = "doomed-prism-fb-ipc-ci"
CONNECT_TIMEOUT_S = 30.0
FLOOD_FRAMES = 500


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
    print(f"IPC runtime smoke: FAIL - {msg}")
    sys.exit(1)


def main() -> int:
    if sys.platform == "win32":
        print("IPC runtime smoke: skipped (not a POSIX platform)")
        return 0
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    exe, iwad = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if not exe.is_file() or not iwad.is_file():
        _fail("engine or IWAD not found")

    server = IpcServer(address_factory=_fixed_factory)
    server.start()
    env = {
        **os.environ,
        "DOOMED_PRISM_IPC_ADDR": SOCKET_PATH,
        "DOOMED_PRISM_FB_NAME": FB_NAME,
        "DOOMED_PRISM_WARP": "1 1",
        "SDL_AUDIODRIVER": "dummy",
    }
    proc = subprocess.Popen(
        [str(exe), "-iwad", str(iwad), "-window", "-width", "640", "-height", "480",
         "-warp", "1", "1", "-skill", "3", "-nomusic", "-nosound"],
        env=env,
    )
    try:
        deadline = time.monotonic() + CONNECT_TIMEOUT_S
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                _fail(f"engine exited early ({proc.returncode})")
            server.poll()
            if server.is_connected:
                break
            time.sleep(0.05)
        else:
            _fail("engine never completed the IPC handshake")
        print(f"socket {Path(SOCKET_PATH).name}: present, handshake complete")

        reader = FrameReader(FB_NAME)
        while not reader.try_open():
            time.sleep(0.05)
        counters: set[int] = set()
        for i in range(FLOOD_FRAMES):
            server.send(Message.turn(4, i % 40))
            if i % 50 == 0:
                server.send(Message.pulse(10))
            server.poll()
            f = reader.latest()
            if f is not None:
                counters.add(f.counter)
            time.sleep(1 / 60)
        reader.close()
        if len(counters) < 10:
            _fail(f"frame_counter did not advance under IPC load ({len(counters)})")
        print(f"frame_counter advancing under IPC load: {len(counters)} distinct values")
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
    print(f"socket {Path(SOCKET_PATH).name}: absent after teardown")
    print("IPC runtime smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
