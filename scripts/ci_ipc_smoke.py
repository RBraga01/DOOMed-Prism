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
from pewpew.input.actions import Action, MOVE_MAGNITUDE_SCALE, TURN_MAX_MOUSE_DELTA  # noqa: E402
from pewpew.ipc.protocol import Message  # noqa: E402
from pewpew.ipc.server import IpcServer  # noqa: E402

SOCKET_PATH = "/tmp/doomed-prism-ipc-ci.sock"
FB_NAME = "doomed-prism-fb-ipc-ci"
CONNECT_TIMEOUT_S = 30.0
OPEN_TIMEOUT_S = 30.0
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
        open_deadline = time.monotonic() + OPEN_TIMEOUT_S
        while time.monotonic() < open_deadline:
            if proc.poll() is not None:
                _fail(f"engine exited early ({proc.returncode}) before the framebuffer opened")
            if reader.try_open():
                break
            time.sleep(0.05)
        else:
            _fail("framebuffer segment never became readable")
        RAMP_START, RAMP_LEN = 120, 160          # 80 frames forward 0->max->0, then 80 backward
        counters: set[int] = set()
        ramp_counters: set[int] = set()
        for i in range(FLOOD_FRAMES):
            # TURN sweep spanning 0 .. TURN_MAX_MOUSE_DELTA + margin (exercises the C clamp)
            server.send(Message.turn(int(Action.TURN_RIGHT), i % (TURN_MAX_MOUSE_DELTA + 8)))
            # analog MOVE ramp: a triangle 0 -> MOVE_MAGNITUDE_SCALE -> 0, forward then backward
            if RAMP_START <= i < RAMP_START + RAMP_LEN:
                k = i - RAMP_START
                half = RAMP_LEN // 2
                local = k if k < half else k - half
                frac = local / (half - 1)
                tri = 1.0 - abs(2.0 * frac - 1.0)
                code = Action.MOVE_FORWARD if k < half else Action.MOVE_BACKWARD
                server.send(Message.action(int(code), round(tri * MOVE_MAGNITUDE_SCALE)))
            elif i == RAMP_START + RAMP_LEN:
                server.send(Message.action(int(Action.MOVE_FORWARD), 0))
                server.send(Message.action(int(Action.MOVE_BACKWARD), 0))
            if i % 50 == 0:
                server.send(Message.pulse(int(Action.FIRE)))
            server.poll()
            if proc.poll() is not None:
                _fail(f"engine exited early ({proc.returncode}) during the flood")
            frame = reader.latest()
            if frame is not None:
                counters.add(frame.counter)
                if RAMP_START <= i < RAMP_START + RAMP_LEN:
                    ramp_counters.add(frame.counter)
            time.sleep(1 / 60)
        reader.close()
        if not server.is_connected:
            _fail("engine disconnected during the action flood")
        if len(counters) < 10:
            _fail(f"frame_counter did not advance under IPC load ({len(counters)})")
        if len(ramp_counters) < 10:
            _fail(f"frame_counter stalled during the analog MOVE ramp ({len(ramp_counters)})")
        print(
            f"frame_counter advancing under IPC load: {len(counters)} distinct values "
            f"({len(ramp_counters)} during the analog MOVE ramp)"
        )
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
