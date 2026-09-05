# DOOMed Prism Milestone 3a Implementation Plan — Input core and the IPC boundary

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make DOOM playable through normalized actions carried over a local IPC socket — gaze-zone movement and progressive turn, click / spoken fire fusion, Enter-pause — with Crispy Doom's SDL keyboard no longer the play input.

**Architecture:** A stdlib fixed-8-byte-frame IPC protocol; a `IpcServer` on the PewPew side (AF_UNIX on POSIX, `127.0.0.1` TCP on Windows) that PewPew binds before launching Crispy. A second Crispy Doom patch (`patches/crispy-doom-ipc-input.diff`, applied as a series after the M2 frame-export patch) connects on startup and injects `D_PostEvent` key/mouse events once per built tic. A Python input pipeline (gaze zones → dwell/jitter filter → fire arbiter → action router) ticks from the existing host `QTimer` and drains to the server. `host_widget` owns the server lifecycle and releases all held input on sleep / IPC loss / shutdown.

**Tech Stack:** Python 3.10+, PySide6 (Raven extra), pytest + pytest-qt, `socket`/`struct`/`selectors` (stdlib), C99 + BSD sockets / winsock + CMake for the engine patch, the pinned `crispy-doom-7.1` tag.

**Spec:** `docs/superpowers/specs/2026-09-05-doomed-prism-milestone-3-design.md` (this plan implements the spec's §16 "Plan 3a"; the decision gate is spec §17, exit criteria spec §18. Executors read both documents.)

## Global Constraints

- **Branch:** `feature/doomed-prism-m3` (already created from `main` @ `389ef4b`; the four spec commits are on it). Do not push, merge, or publish without authorization.
- **Publication safety.** Every commit must be safe to publish. Never commit Raven-owned source, commercial IWADs, credentials, generated binaries, screenshots with private data, vendored third-party engine source, or acoustic-model / audio files. The only new tracked engine artifact is `patches/crispy-doom-ipc-input.diff` (original work, GPL-2.0-or-later, with GPL headers matching Crispy on the new `src/i_ipc_input.c` / `.h`). Both `python scripts/check_publication_safety.py --root .` and `--root . --history` must exit 0 before every commit.
- **Tests run without** Crispy Doom, Raven Framework, an IWAD, a C toolchain, or a display, using project-owned fakes. `IpcServer` tests bind a real *in-process* loopback listener (no external process); the `address_factory` seam only selects the platform branch + path.
- **Wire frame (spec §5, R10):** `struct` format `"<BBHi"`, exactly 8 bytes, little-endian: `version: u8`, `type: u8`, `code: u16`, `value: i32`. `IPC_PROTOCOL_VERSION = 1`, `IPC_FRAME_SIZE = 8`. No on-wire magic.
- **`MessageType` (spec §5):** `HELLO = 0`, `ACTION = 1`, `PULSE = 2`, `DISCRETE = 3`, `TURN = 4`, `BYE = 6`. Value `5` is reserved (unused in M3). Any other `type` → `IpcProtocolError`.
- **Action `code` table (spec §5) — the C `#define`s and `pewpew.input.actions.Action` MUST both equal this, asserted by a test:**
  `MOVE_FORWARD = 1`, `MOVE_BACKWARD = 2`, `TURN_LEFT = 3`, `TURN_RIGHT = 4`, `FIRE = 10`, `USE = 11`, `PAUSE = 20`. Codes `21`–`24` (`MENU_*`) and `40`–`79` (weapons / automap / save / load / exit) are **reserved for Milestone 3b** and are not defined in 3a.
- **`value` semantics (spec §5):** `ACTION` → `10000` on hold, `0` on release. `TURN` → unsigned clamped mouse-x magnitude (direction is carried in `code`). `PULSE` / `DISCRETE` / `HELLO` / `BYE` → `0`. All magnitude→wire scaling lives in `ActionRouter`; `pewpew.ipc.protocol` does no scaling and never imports `pewpew.input`.
- **Tunable constants (spec R11) — module-level `UPPER_SNAKE_CASE`, not `RuntimeConfig` fields:**
  `DEAD_ZONE_HALF_W = 180`, `DEAD_ZONE_HALF_H = 150`, `TURN_RESPONSE_EXPONENT = 1.5`, `MAGNITUDE_EMA_ALPHA = 0.4`, `DWELL_S = 0.15`, `JITTER_GRACE_S = 0.02` (all in `pewpew.input.gaze`); `MAGNITUDE_STEPS = 20`, `TURN_MAX_MOUSE_DELTA = 40` (`pewpew.input.actions`); `FIRE_DEBOUNCE_S = 0.12` (`pewpew.input.fire`); `PULSE_HOLD_TICS = 2`, `IPC_TURN_CLAMP = 40` (C, `i_ipc_input.c`). Protocol constants (`IPC_PROTOCOL_VERSION`, `IPC_FRAME_SIZE`, `IPC_HANDSHAKE_TIMEOUT_S = 10.0`, `IPC_HELLO_TIMEOUT_S = 2.0`) are protocol-governed, not R11 tunables.
- **`IpcServer` is the sole owner of the socket path** (bind + unlink). `engine.stop()` never touches it. The client socket is **blocking** with `settimeout(0.05)`; a send timeout / reset is treated as a disconnect. The listening socket's `accept` is non-blocking.
- **No menu-navigation action in 3a.** The gate reaches gameplay via `-warp`: `DoomProcess` appends `-warp <DOOMED_PRISM_WARP> -skill <DOOMED_PRISM_SKILL or 3>` to Crispy's argv only when `DOOMED_PRISM_WARP` is set.
- **The Crispy patch series (spec §13, R4).** `scripts/build_crispy.py` holds `PATCHES = ("patches/crispy-doom-fb-export.diff", "patches/crispy-doom-ipc-input.diff")` and applies it cumulatively on disk: `git -C <dir> reset --hard <lock.commit>` + `git -C <dir> clean -fd -- src/`, then `git -C <dir> apply <p1>`, then `git -C <dir> apply <p2>`, then write `.doomed-prism-applied` **once**. `--check` = same restore + real `git apply <p1>` + `git apply --check <p2>`, no marker. Patch 2 is authored against the patch-1-applied tree and touches **no** patch-1 line.
- **DRY / YAGNI / TDD.** New modules live under `src/pewpew/ipc/` and `src/pewpew/input/` (many small focused files). Fakes live under `tests/fakes/`.

---

## Checkpoint A — transport core (Tasks 1–4)

Tasks 1–4 deliver a tested IPC protocol, a tested `IpcServer`, the Crispy IPC-input patch (manually build-verified), and the multi-patch build script. They are a coherent, independently reviewable unit and a safe place to pause or resume (spec R1). Task 13's CI smoke is what exercises Task 3 at runtime.

---

## Task 1: IPC wire protocol

**Files:**
- Create: `src/pewpew/ipc/__init__.py` (empty)
- Create: `src/pewpew/ipc/protocol.py`
- Create: `tests/test_ipc_protocol.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - Constants: `IPC_PROTOCOL_VERSION = 1`, `IPC_FRAME_SIZE = 8`.
  - `class MessageType(enum.IntEnum)`: `HELLO = 0`, `ACTION = 1`, `PULSE = 2`, `DISCRETE = 3`, `TURN = 4`, `BYE = 6`.
  - `class IpcProtocolError(RuntimeError)`.
  - `@dataclass(frozen=True) class Message` with fields `type: MessageType`, `code: int`, `value: int`, and classmethods:
    - `Message.hello() -> Message` → `type=HELLO, code=IPC_PROTOCOL_VERSION, value=0`
    - `Message.bye() -> Message` → `type=BYE, code=0, value=0`
    - `Message.action(code: int, value: int) -> Message` → `type=ACTION`
    - `Message.turn(code: int, value: int) -> Message` → `type=TURN`
    - `Message.pulse(code: int) -> Message` → `type=PULSE, value=0`
    - `Message.discrete(code: int) -> Message` → `type=DISCRETE, value=0`
  - `encode(message: Message) -> bytes` — always exactly 8 bytes.
  - `decode(buffer: bytes) -> tuple[Message | None, bytes]` — consumes one whole frame from the front of `buffer`; `(None, buffer)` when `len(buffer) < 8`; raises `IpcProtocolError` on an out-of-range `version` or an unknown `type`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ipc_protocol.py`:

```python
"""Tests for the fixed 8-byte IPC wire protocol."""

from __future__ import annotations

import struct

import pytest

from pewpew.ipc.protocol import (
    IPC_FRAME_SIZE,
    IPC_PROTOCOL_VERSION,
    IpcProtocolError,
    Message,
    MessageType,
    decode,
    encode,
)


def test_every_frame_is_exactly_eight_bytes() -> None:
    for message in (
        Message.hello(),
        Message.bye(),
        Message.action(1, 10000),
        Message.turn(3, 40),
        Message.pulse(10),
        Message.discrete(20),
    ):
        assert len(encode(message)) == IPC_FRAME_SIZE


def test_encode_is_little_endian_BBHi() -> None:
    raw = encode(Message.turn(code=4, value=-7))
    assert raw == struct.pack("<BBHi", IPC_PROTOCOL_VERSION, MessageType.TURN, 4, -7)


def test_round_trips_every_message_type() -> None:
    for message in (
        Message.hello(),
        Message.bye(),
        Message.action(2, 0),
        Message.turn(3, 25),
        Message.pulse(11),
        Message.discrete(20),
    ):
        decoded, rest = decode(encode(message))
        assert decoded == message
        assert rest == b""


def test_decode_returns_none_on_a_partial_frame() -> None:
    decoded, rest = decode(b"\x01\x01\x00")
    assert decoded is None
    assert rest == b"\x01\x01\x00"


def test_decode_consumes_one_frame_and_returns_the_remainder() -> None:
    buffer = encode(Message.pulse(10)) + encode(Message.discrete(20))
    first, rest = decode(buffer)
    assert first == Message.pulse(10)
    second, rest2 = decode(rest)
    assert second == Message.discrete(20)
    assert rest2 == b""


def test_decode_rejects_an_unknown_type() -> None:
    frame = struct.pack("<BBHi", IPC_PROTOCOL_VERSION, 99, 0, 0)
    with pytest.raises(IpcProtocolError):
        decode(frame)


def test_decode_rejects_a_version_mismatch() -> None:
    frame = struct.pack("<BBHi", IPC_PROTOCOL_VERSION + 1, MessageType.HELLO, 1, 0)
    with pytest.raises(IpcProtocolError):
        decode(frame)


def test_hello_carries_the_protocol_version_in_code() -> None:
    assert Message.hello().code == IPC_PROTOCOL_VERSION
    assert Message.hello().type is MessageType.HELLO
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_ipc_protocol.py -q`
Expected: FAIL — `pewpew.ipc.protocol` does not exist.

- [ ] **Step 3: Implement `src/pewpew/ipc/protocol.py`**

```python
"""Fixed 8-byte little-endian IPC wire protocol (stdlib only)."""

from __future__ import annotations

import enum
import struct
from dataclasses import dataclass

IPC_PROTOCOL_VERSION = 1
IPC_FRAME_SIZE = 8

_FRAME = struct.Struct("<BBHi")  # version:u8, type:u8, code:u16, value:i32


class MessageType(enum.IntEnum):
    HELLO = 0
    ACTION = 1
    PULSE = 2
    DISCRETE = 3
    TURN = 4
    BYE = 6


class IpcProtocolError(RuntimeError):
    """Raised on a version mismatch or an unknown message type."""


@dataclass(frozen=True)
class Message:
    type: MessageType
    code: int
    value: int

    @classmethod
    def hello(cls) -> "Message":
        return cls(MessageType.HELLO, IPC_PROTOCOL_VERSION, 0)

    @classmethod
    def bye(cls) -> "Message":
        return cls(MessageType.BYE, 0, 0)

    @classmethod
    def action(cls, code: int, value: int) -> "Message":
        return cls(MessageType.ACTION, code, value)

    @classmethod
    def turn(cls, code: int, value: int) -> "Message":
        return cls(MessageType.TURN, code, value)

    @classmethod
    def pulse(cls, code: int) -> "Message":
        return cls(MessageType.PULSE, code, 0)

    @classmethod
    def discrete(cls, code: int) -> "Message":
        return cls(MessageType.DISCRETE, code, 0)


def encode(message: Message) -> bytes:
    return _FRAME.pack(
        IPC_PROTOCOL_VERSION, int(message.type), message.code, message.value
    )


def decode(buffer: bytes) -> tuple[Message | None, bytes]:
    if len(buffer) < IPC_FRAME_SIZE:
        return None, buffer
    version, raw_type, code, value = _FRAME.unpack(buffer[:IPC_FRAME_SIZE])
    if version != IPC_PROTOCOL_VERSION:
        raise IpcProtocolError(f"unsupported protocol version {version}")
    try:
        message_type = MessageType(raw_type)
    except ValueError as error:
        raise IpcProtocolError(f"unknown message type {raw_type}") from error
    return Message(message_type, code, value), buffer[IPC_FRAME_SIZE:]
```

- [ ] **Step 4: Run the tests and the whole suite**

```bash
python -m pytest tests/test_ipc_protocol.py -q
python -m pytest -q
```

Expected: the new file passes; the rest of the suite is unchanged and green.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/ipc/__init__.py src/pewpew/ipc/protocol.py tests/test_ipc_protocol.py
git commit -m "feat: add the fixed-frame IPC wire protocol"
```

---

## Task 2: `IpcServer` (PewPew side of the transport)

**Files:**
- Create: `src/pewpew/ipc/server.py`
- Create: `tests/fakes/fake_ipc.py`
- Create: `tests/test_ipc_server.py`

**Interfaces:**
- Consumes: `pewpew.ipc.protocol` (`Message`, `MessageType`, `IpcProtocolError`, `encode`, `decode`, `IPC_FRAME_SIZE`, `IPC_PROTOCOL_VERSION`).
- Produces:
  - `AddressFactory = Callable[[], tuple[socket.socket, str]]` — returns a **bound, listening, non-blocking** socket and its address string. Default: POSIX → `AF_UNIX` at `${XDG_RUNTIME_DIR or /tmp}/doomed-prism-ipc-<pid>-<token>.sock` (asserts `len(path) < 104`, `unlink`s a stale path first); Windows → `AF_INET` `("127.0.0.1", 0)`, address `"127.0.0.1:<port>"`.
  - `class IpcServer`:
    - `__init__(self, *, address_factory: AddressFactory | None = None, on_disconnect: Callable[[], None] | None = None) -> None`
    - `start(self) -> str` — calls the factory, stores the listening socket + address, returns the address.
    - `poll(self) -> None` — non-blocking: accept a pending client (a 2nd connection is accepted then immediately closed); drive the `HELLO` handshake across calls; detect EOF/reset → set `is_connected = False`, call `on_disconnect` exactly once.
    - `send(self, message: Message) -> None` — no-op unless `is_connected`; otherwise `sendall(encode(message))`; `BrokenPipeError` / `ConnectionResetError` / `socket.timeout` → disconnect.
    - `close(self) -> None` — `send(Message.bye())` if connected, close client + listening sockets, `unlink` the POSIX path. Idempotent.
    - `is_connected: bool` property.
    - `protocol_mismatch: bool` property — set `True` when the client's `HELLO` version does not match.
  - `tests/fakes/fake_ipc.py`: `class FakeIpcClient` — the child side for tests. `__init__(self, address: str)` connects in-process (parses `"127.0.0.1:<port>"` or opens the `AF_UNIX` path). `send_hello(self, version: int = IPC_PROTOCOL_VERSION) -> None`; `recv_message(self, timeout: float = 1.0) -> Message` (blocks briefly, decodes one frame); `close(self) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/fakes/fake_ipc.py`:

```python
"""In-process stand-in for the Crispy Doom IPC client (the child side)."""

from __future__ import annotations

import socket

from pewpew.ipc.protocol import IPC_FRAME_SIZE, IPC_PROTOCOL_VERSION, Message, decode, encode


class FakeIpcClient:
    def __init__(self, address: str) -> None:
        if address.startswith("127.0.0.1:"):
            host, port = address.split(":")
            self._sock = socket.create_connection((host, int(port)), timeout=1.0)
        else:
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.settimeout(1.0)
            self._sock.connect(address)
        self._buffer = b""

    def send_hello(self, version: int = IPC_PROTOCOL_VERSION) -> None:
        self._sock.sendall(encode(Message(Message.hello().type, version, 0)))

    def recv_message(self, timeout: float = 1.0) -> Message:
        self._sock.settimeout(timeout)
        while True:
            message, self._buffer = decode(self._buffer)
            if message is not None:
                return message
            chunk = self._sock.recv(64)
            if not chunk:
                raise ConnectionError("server closed before a full frame")
            self._buffer += chunk

    def close(self) -> None:
        self._sock.close()
```

Create `tests/test_ipc_server.py`:

```python
"""Tests for the PewPew-side IPC server (real in-process loopback, no child process)."""

from __future__ import annotations

import socket
import sys

import pytest

from fakes.fake_ipc import FakeIpcClient
from pewpew.ipc.protocol import IPC_PROTOCOL_VERSION, Message, MessageType
from pewpew.ipc.server import IpcServer


def _loopback_factory():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.setblocking(False)
    port = listener.getsockname()[1]
    return listener, f"127.0.0.1:{port}"


@pytest.fixture
def server():
    srv = IpcServer(address_factory=_loopback_factory)
    try:
        yield srv
    finally:
        srv.close()


def test_start_returns_the_listening_address(server: IpcServer) -> None:
    address = server.start()
    assert address.startswith("127.0.0.1:")
    assert server.is_connected is False


def test_handshake_connects_on_a_matching_hello(server: IpcServer) -> None:
    address = server.start()
    client = FakeIpcClient(address)
    server.poll()  # accept
    assert client.recv_message().type is MessageType.HELLO  # server greets first
    client.send_hello(IPC_PROTOCOL_VERSION)
    for _ in range(10):
        server.poll()
        if server.is_connected:
            break
    assert server.is_connected is True
    assert server.protocol_mismatch is False
    client.close()


def test_handshake_rejects_a_version_mismatch(server: IpcServer) -> None:
    address = server.start()
    client = FakeIpcClient(address)
    server.poll()
    client.recv_message()
    client.send_hello(IPC_PROTOCOL_VERSION + 1)
    for _ in range(10):
        server.poll()
        if server.protocol_mismatch:
            break
    assert server.protocol_mismatch is True
    assert server.is_connected is False
    client.close()


def test_send_before_a_connected_client_is_a_noop(server: IpcServer) -> None:
    server.start()
    server.send(Message.pulse(10))  # must not raise


def test_send_delivers_a_frame_to_the_connected_client(server: IpcServer) -> None:
    address = server.start()
    client = FakeIpcClient(address)
    server.poll()
    client.recv_message()
    client.send_hello()
    for _ in range(10):
        server.poll()
        if server.is_connected:
            break
    server.send(Message.action(1, 10000))
    assert client.recv_message() == Message.action(1, 10000)
    client.close()


def test_client_close_fires_on_disconnect_exactly_once(server: IpcServer) -> None:
    calls: list[int] = []
    server._on_disconnect = lambda: calls.append(1)  # set via ctor in real use
    address = server.start()
    client = FakeIpcClient(address)
    server.poll()
    client.recv_message()
    client.send_hello()
    for _ in range(10):
        server.poll()
        if server.is_connected:
            break
    client.close()
    for _ in range(10):
        server.poll()
    assert calls == [1]
    assert server.is_connected is False


def test_close_is_idempotent(server: IpcServer) -> None:
    server.start()
    server.close()
    server.close()


@pytest.mark.skipif(sys.platform == "win32", reason="AF_UNIX path-length guard is POSIX")
def test_default_posix_factory_rejects_an_over_long_path(monkeypatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/" + "x" * 200)
    with pytest.raises(OSError):
        IpcServer().start()
```

*(Note: the `on_disconnect` test wires the callback through the constructor in real code; the plan's test uses a private attr only to keep the fixture simple — the implementer should accept `on_disconnect=` in `__init__` and the test should pass it there. Rewrite that one test to `IpcServer(address_factory=_loopback_factory, on_disconnect=lambda: calls.append(1))` and drop the fixture for that case.)*

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/test_ipc_server.py -q`
Expected: FAIL — `pewpew.ipc.server` does not exist.

- [ ] **Step 3: Implement `src/pewpew/ipc/server.py`**

```python
"""PewPew-side IPC server: bind before launch, stream actions, detect the child leaving."""

from __future__ import annotations

import os
import secrets
import socket
import sys
from collections.abc import Callable

from pewpew.ipc.protocol import (
    IPC_FRAME_SIZE,
    IPC_PROTOCOL_VERSION,
    IpcProtocolError,
    Message,
    MessageType,
    decode,
    encode,
)

AddressFactory = Callable[[], "tuple[socket.socket, str]"]
_HELLO_MAX_BYTES = IPC_FRAME_SIZE
_SUN_PATH_LIMIT = 104


def _default_factory() -> "tuple[socket.socket, str]":
    token = secrets.token_hex(4)
    if sys.platform == "win32":
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.setblocking(False)
        return listener, f"127.0.0.1:{listener.getsockname()[1]}"
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    path = os.path.join(base, f"doomed-prism-ipc-{os.getpid()}-{token}.sock")
    if len(path) >= _SUN_PATH_LIMIT:
        raise OSError(f"AF_UNIX path too long ({len(path)} >= {_SUN_PATH_LIMIT}): {path}")
    try:
        os.unlink(path)
    except OSError:
        pass
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(path)
    listener.listen(1)
    listener.setblocking(False)
    return listener, path


class IpcServer:
    def __init__(
        self,
        *,
        address_factory: AddressFactory | None = None,
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        self._factory = address_factory or _default_factory
        self._on_disconnect = on_disconnect or (lambda: None)
        self._listener: socket.socket | None = None
        self._client: socket.socket | None = None
        self._address: str | None = None
        self._hello_buffer = b""
        self._is_connected = False
        self._protocol_mismatch = False
        self._disconnect_fired = False

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def protocol_mismatch(self) -> bool:
        return self._protocol_mismatch

    def start(self) -> str:
        self._listener, self._address = self._factory()
        return self._address

    def poll(self) -> None:
        if self._listener is None:
            return
        if self._client is None:
            self._try_accept()
            return
        if not self._is_connected:
            self._drive_handshake()
            return
        self._check_alive()

    def _try_accept(self) -> None:
        try:
            client, _ = self._listener.accept()
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            return
        if self._client is not None:
            client.close()
            return
        client.setblocking(True)
        client.settimeout(0.05)
        self._client = client
        try:
            self._client.sendall(encode(Message.hello()))
        except OSError:
            self._drop()

    def _drive_handshake(self) -> None:
        assert self._client is not None
        try:
            self._client.setblocking(False)
            chunk = self._client.recv(_HELLO_MAX_BYTES - len(self._hello_buffer))
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._drop()
            return
        finally:
            if self._client is not None:
                self._client.settimeout(0.05)
        if not chunk:
            self._drop()
            return
        self._hello_buffer += chunk
        message, rest = decode(self._hello_buffer) if len(
            self._hello_buffer
        ) >= IPC_FRAME_SIZE else (None, self._hello_buffer)
        if message is None:
            return
        self._hello_buffer = rest
        if message.type is not MessageType.HELLO or message.code != IPC_PROTOCOL_VERSION:
            self._protocol_mismatch = True
            self._close_client()
            return
        self._is_connected = True

    def _check_alive(self) -> None:
        assert self._client is not None
        try:
            self._client.setblocking(False)
            chunk = self._client.recv(64)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._drop()
            return
        finally:
            if self._client is not None:
                self._client.settimeout(0.05)
        if not chunk:
            self._drop()

    def send(self, message: Message) -> None:
        if not self._is_connected or self._client is None:
            return
        try:
            self._client.sendall(encode(message))
        except (BrokenPipeError, ConnectionResetError, socket.timeout, OSError):
            self._drop()

    def close(self) -> None:
        if self._is_connected and self._client is not None:
            try:
                self._client.sendall(encode(Message.bye()))
            except OSError:
                pass
        self._close_client()
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        if self._address and not self._address.startswith("127.0.0.1:"):
            try:
                os.unlink(self._address)
            except OSError:
                pass
        self._address = None

    def _close_client(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        self._is_connected = False

    def _drop(self) -> None:
        self._close_client()
        if not self._disconnect_fired:
            self._disconnect_fired = True
            self._on_disconnect()
```

- [ ] **Step 4: Run tests and the suite**

```bash
python -m pytest tests/test_ipc_server.py -q
python -m pytest -q
```

Expected: PASS. (Rework the `on_disconnect` test to pass the callback via `__init__` as noted in Step 1.)

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/ipc/server.py tests/fakes/fake_ipc.py tests/test_ipc_server.py
git commit -m "feat: add the PewPew-side IPC server"
```

---

## Task 3: Crispy Doom IPC-input patch (patch 2 of the series)

This task produces one tracked artifact — `patches/crispy-doom-ipc-input.diff` — plus a manual integration check. It needs a local C toolchain, SDL2/SDL2_mixer/SDL2_net dev libraries, CMake, and Git for Windows (not MSYS2 git — see the M2 README hazard). It does **not** add pytest coverage; its runtime verification is Task 13's CI smoke and the §17 gate.

**Files:**
- Create: `patches/crispy-doom-ipc-input.diff`
- Working tree only (not committed): the `build/crispy/` checkout, now with both patches applied.

**Interfaces:**
- Consumes: the wire constants from Task 1 (frame layout, `MessageType` values, the action `code` table from Global Constraints) — replicated as C `#define`s.
- Produces: the patch adds `src/i_ipc_input.c` and `src/i_ipc_input.h` to Crispy and modifies `src/d_loop.c`, `src/i_video.c`, and `src/CMakeLists.txt`. Public C API in the header:
  - `void IPC_Input_Init(void);` — reads `DOOMED_PRISM_IPC_ADDR`; unset/empty → all functions no-op. Opens the socket, **blocking** `connect()`, then sets it non-blocking; sends `HELLO`; spin-reads the server `HELLO` for ≤ `IPC_HELLO_TIMEOUT_S` (2.0 s); on timeout or a version mismatch, closes the socket and disables.
  - `void IPC_Input_Pump(void);` — non-blocking `recv` into an 8-byte staging buffer; per full frame, `D_PostEvent` per the mapping below; decrements the `PULSE_HOLD_TICS` release scheduler; on EOF/error runs release-all and closes.
  - `void IPC_Input_Shutdown(void);` — release-all, close the socket, `WSACleanup` on Windows. Idempotent. Does **not** unlink (the server owns the path).

- [ ] **Step 1: Restore the checkout and apply patch 1**

```bash
cd build/crispy
git reset --hard $(python - <<'PY'
import tomllib, pathlib
print(tomllib.loads(pathlib.Path("../../crispy-doom.lock").read_text())["commit"])
PY
)
git clean -fd -- src/
git apply ../../patches/crispy-doom-fb-export.diff
cd ../..
```

(If `build/crispy/` does not exist, run `python scripts/build_crispy.py --check` first to clone the pinned tag, then restore as above.)

- [ ] **Step 2: Add `src/i_ipc_input.h` in the checkout**

```c
//
// Copyright(C) 2026 DOOMed Prism contributors
//
// This program is free software; you can redistribute it and/or
// modify it under the terms of the GNU General Public License
// as published by the Free Software Foundation; either version 2
// of the License, or (at your option) any later version.
//
// DOOMed Prism: read normalized input actions from a local socket named by
// DOOMED_PRISM_IPC_ADDR and inject them into DOOM's event queue via
// D_PostEvent. Active only when that environment variable is set.
//
// Wire format (must stay byte-identical to src/pewpew/ipc/protocol.py):
// an 8-byte little-endian frame: uint8 version, uint8 type, uint16 code,
// int32 value.
//

#ifndef I_IPC_INPUT_H
#define I_IPC_INPUT_H

void IPC_Input_Init(void);
void IPC_Input_Pump(void);
void IPC_Input_Shutdown(void);

#endif
```

- [ ] **Step 3: Add `src/i_ipc_input.c` in the checkout**

Skeleton to adapt. The `key_up` / `key_down` / `key_fire` / `key_use` / `key_pause` globals come from `doomkeys.h` / the Crispy config so a rebound key is honoured. `D_PostEvent` and `event_t` / `ev_keydown` / `ev_keyup` / `ev_mouse` come from `d_event.h`.

```c
//
// (GPL-2.0-or-later header identical in spirit to i_ipc_input.h)
//

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "d_event.h"
#include "doomkeys.h"
#include "i_ipc_input.h"
#include "m_config.h"     /* key_* externs via the config system in this tag */

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
typedef SOCKET ipc_sock_t;
#define IPC_INVALID INVALID_SOCKET
#else
#include <arpa/inet.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
typedef int ipc_sock_t;
#define IPC_INVALID (-1)
#endif

#define IPC_FRAME_SIZE 8
#define IPC_PROTOCOL_VERSION 1
#define IPC_HELLO_TIMEOUT_MS 2000
#define PULSE_HOLD_TICS 2
#define IPC_TURN_CLAMP 40

/* MessageType */
#define MT_HELLO 0
#define MT_ACTION 1
#define MT_PULSE 2
#define MT_DISCRETE 3
#define MT_TURN 4
#define MT_BYE 6

/* action codes (src/pewpew/ipc/protocol.py + plan Global Constraints) */
#define AC_MOVE_FORWARD 1
#define AC_MOVE_BACKWARD 2
#define AC_TURN_LEFT 3
#define AC_TURN_RIGHT 4
#define AC_FIRE 10
#define AC_USE 11
#define AC_PAUSE 20

static int ipc_enabled = 0;
static ipc_sock_t ipc_sock = IPC_INVALID;
static unsigned char ipc_buf[IPC_FRAME_SIZE];
static int ipc_have = 0;

/* held[] indexed by a small local enum; release-all posts keyup for each set */
enum { H_FWD, H_BACK, H_COUNT };
static int held[H_COUNT];
static int held_key[H_COUNT];         /* resolved DOOM key for each slot */

/* pending pulse keyups: key + tics-until-release */
static int pulse_key[4];
static int pulse_tics[4];

static void ipc_post_key(evtype_t t, int key)
{
    event_t ev;
    ev.type = t;
    ev.data1 = key;
    ev.data2 = -1;
    ev.data3 = -1;
    D_PostEvent(&ev);
}

static void ipc_post_mouse_x(int dx)
{
    event_t ev;
    ev.type = ev_mouse;
    ev.data1 = 0;      /* buttons: 0 is fine while the SDL window is unfocused */
    ev.data2 = dx;     /* x motion — DOOM's analog turn axis */
    ev.data3 = 0;
    D_PostEvent(&ev);
}

static void ipc_release_all(void)
{
    int i;
    for (i = 0; i < H_COUNT; i++)
    {
        if (held[i]) { ipc_post_key(ev_keyup, held_key[i]); held[i] = 0; }
    }
    for (i = 0; i < 4; i++)
    {
        if (pulse_tics[i] > 0) { ipc_post_key(ev_keyup, pulse_key[i]); pulse_tics[i] = 0; }
    }
    ipc_post_key(ev_keyup, key_fire);
    ipc_post_key(ev_keyup, key_use);
}

static void ipc_disable(void)
{
    ipc_release_all();
    if (ipc_sock != IPC_INVALID)
    {
#ifdef _WIN32
        closesocket(ipc_sock);
#else
        close(ipc_sock);
#endif
        ipc_sock = IPC_INVALID;
    }
    ipc_enabled = 0;
}

static int ipc_connect(const char *addr)
{
    /* "127.0.0.1:<port>" -> AF_INET; otherwise an AF_UNIX path.
       blocking connect first, then set non-blocking. Return 0 on success. */
    /* ... implement both branches with getaddrinfo / sockaddr_un ... */
    return 0;
}

static void ipc_handshake(void)
{
    /* send HELLO(version); spin-read one 8-byte frame for <= IPC_HELLO_TIMEOUT_MS;
       on a matching HELLO -> ipc_enabled = 1; else ipc_disable(). */
}

void IPC_Input_Init(void)
{
    const char *addr = getenv("DOOMED_PRISM_IPC_ADDR");
    if (addr == NULL || addr[0] == '\0') { ipc_enabled = 0; return; }
#ifdef _WIN32
    { WSADATA w; if (WSAStartup(MAKEWORD(2, 2), &w) != 0) return; }
#endif
    held_key[H_FWD] = key_up;
    held_key[H_BACK] = key_down;
    if (ipc_connect(addr) != 0) { ipc_disable(); return; }
    ipc_handshake();
}

static void ipc_apply(uint8_t type, uint16_t code, int32_t value)
{
    int slot, i;
    switch (type)
    {
        case MT_ACTION:
            slot = (code == AC_MOVE_FORWARD) ? H_FWD
                 : (code == AC_MOVE_BACKWARD) ? H_BACK : -1;
            if (slot < 0) break;
            if (value != 0 && !held[slot]) { ipc_post_key(ev_keydown, held_key[slot]); held[slot] = 1; }
            else if (value == 0 && held[slot]) { ipc_post_key(ev_keyup, held_key[slot]); held[slot] = 0; }
            break;
        case MT_TURN:
        {
            int d = value; if (d > IPC_TURN_CLAMP) d = IPC_TURN_CLAMP; if (d < 0) d = 0;
            if (d != 0) ipc_post_mouse_x(code == AC_TURN_LEFT ? -d : d);
            break;
        }
        case MT_PULSE:
        {
            int key = (code == AC_FIRE) ? key_fire : (code == AC_USE) ? key_use : -1;
            if (key < 0) break;
            ipc_post_key(ev_keydown, key);
            for (i = 0; i < 4; i++)
                if (pulse_tics[i] == 0) { pulse_key[i] = key; pulse_tics[i] = PULSE_HOLD_TICS; break; }
            break;
        }
        case MT_DISCRETE:
            if (code == AC_PAUSE) { ipc_post_key(ev_keydown, key_pause); ipc_post_key(ev_keyup, key_pause); }
            break;
        case MT_BYE:
            ipc_disable();
            break;
        default:
            break;
    }
}

void IPC_Input_Pump(void)
{
    int i, n;
    if (!ipc_enabled) return;

    for (i = 0; i < 4; i++)
        if (pulse_tics[i] > 0 && --pulse_tics[i] == 0)
            ipc_post_key(ev_keyup, pulse_key[i]);

    for (;;)
    {
#ifdef _WIN32
        n = recv(ipc_sock, (char *)ipc_buf + ipc_have, IPC_FRAME_SIZE - ipc_have, 0);
        if (n == SOCKET_ERROR) { if (WSAGetLastError() == WSAEWOULDBLOCK) break; ipc_disable(); return; }
#else
        n = (int)recv(ipc_sock, ipc_buf + ipc_have, IPC_FRAME_SIZE - ipc_have, 0);
        if (n < 0) { if (errno == EWOULDBLOCK || errno == EAGAIN) break; ipc_disable(); return; }
#endif
        if (n == 0) { ipc_disable(); return; }
        ipc_have += n;
        if (ipc_have < IPC_FRAME_SIZE) continue;
        ipc_have = 0;
        {
            uint8_t version = ipc_buf[0], type = ipc_buf[1];
            uint16_t code = (uint16_t)(ipc_buf[2] | (ipc_buf[3] << 8));
            int32_t value = (int32_t)((uint32_t)ipc_buf[4] | ((uint32_t)ipc_buf[5] << 8)
                          | ((uint32_t)ipc_buf[6] << 16) | ((uint32_t)ipc_buf[7] << 24));
            if (version != IPC_PROTOCOL_VERSION) { ipc_disable(); return; }
            ipc_apply(type, code, value);
        }
    }
}

void IPC_Input_Shutdown(void)
{
    if (!ipc_enabled && ipc_sock == IPC_INVALID) return;
    ipc_disable();
#ifdef _WIN32
    WSACleanup();
#endif
}
```

Flesh out `ipc_connect` and `ipc_handshake` against the tag's headers. Add `#include <errno.h>` on POSIX. Confirm the exact `key_pause` / `key_up` / `key_down` / `key_fire` / `key_use` extern source in `crispy-doom-7.1` and `#include` it.

- [ ] **Step 4: Wire the call sites in the checkout**

- `src/i_video.c`, `I_InitGraphics`: add `#include "i_ipc_input.h"` in the include block, and `IPC_Input_Init();` on the line **immediately after** patch 1's `FB_Export_Init();` (a distinct added line — not an edit of patch 1's line).
- `src/i_video.c`, `I_ShutdownGraphics`: `IPC_Input_Shutdown();` on the line immediately before patch 1's `FB_Export_Shutdown();`.
- `src/d_loop.c`, `BuildNewTic()`: add `IPC_Input_Pump();` immediately before the `loop_interface->ProcessEvents();` call, and `#include "i_ipc_input.h"` near the top. **Binding invariant (spec §10):** exactly one pump per built tic, after SDL events are drained and before `G_BuildTiccmd`. If `BuildNewTic()` at this tag does not have that call, use `D_ProcessEvents()` in `src/d_main.c` and record the real function + line in the patch header comment.
- `src/CMakeLists.txt`: add `i_ipc_input.c        i_ipc_input.h` to `GAME_SOURCE_FILES` on a line **not adjacent** to patch 1's `i_framebuffer_export.*` line (e.g. next to `i_input.c`). Add a separate `if(WIN32) list(APPEND EXTRA_LIBS ws2_32) endif()` block that does not touch patch 1's `winmm shlwapi` line.

- [ ] **Step 5: Build the doubly-patched engine**

```bash
cd build/crispy
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
cd ../..
```

- [ ] **Step 6: Manual integration check with `IpcServer` + `FrameReader`**

Create a throwaway `build/ipc_probe.py` (not committed):

```python
import os, sys, time, subprocess
sys.path.insert(0, "src")
from pewpew.ipc.server import IpcServer
from pewpew.ipc.protocol import Message
from pewpew.framebuffer import FrameReader

srv = IpcServer()
addr = srv.start()
fb = "doomed-prism-fb-ipcprobe"
env = {**os.environ, "DOOMED_PRISM_IPC_ADDR": addr, "DOOMED_PRISM_FB_NAME": fb,
       "DOOMED_PRISM_WARP": "1 1"}
exe = "build/crispy/build/src/crispy-doom"  # or .exe
proc = subprocess.Popen([exe, "-iwad", sys.argv[1], "-window", "-width", "640",
                         "-height", "480", "-warp", "1", "1", "-skill", "3"], env=env)
reader = FrameReader(fb)
for _ in range(200):
    srv.poll()
    if srv.is_connected:
        break
    time.sleep(0.05)
assert srv.is_connected, "engine never completed the IPC handshake"
while not reader.try_open():
    time.sleep(0.05)
before = reader.latest().counter
for _ in range(60):                         # ~1s of TURN_RIGHT
    srv.send(Message.turn(4, 30)); srv.poll(); time.sleep(1 / 35)
srv.send(Message.pulse(10))                  # one shot
time.sleep(0.5)
after = reader.latest().counter
assert after > before, "frame_counter did not advance under IPC input"
srv.close(); proc.terminate()
print("OK: engine connected, handshook, stayed live under IPC input")
```

Run with a lawful IWAD. Expected: `OK: ...`. Visually confirm in the Crispy window that `TURN_RIGHT` rotates the view and the `PULSE` fires. Close the engine; confirm no leftover socket file (POSIX).

- [ ] **Step 7: Generate the patch**

```bash
cd build/crispy
git add -A src/
git diff --cached src/ > ../../patches/crispy-doom-ipc-input.diff
git reset
cd ../..
# verify the series still composes:
python scripts/build_crispy.py --check   # (Task 4 provides the multi-patch --check)
```

`patches/crispy-doom-ipc-input.diff` must be a single unified diff, `a/`/`b/` prefixes rooted at the checkout, containing only: new `src/i_ipc_input.c` / `.h`, and small hunks in `src/d_loop.c`, `src/i_video.c`, `src/CMakeLists.txt`. Record `git apply --stat` output; the net added-line count should be well under ~400.

- [ ] **Step 8: Commit the patch**

```bash
git add patches/crispy-doom-ipc-input.diff
git commit -m "feat: add the Crispy Doom IPC-input patch"
```

---

## Task 4: Multi-patch `build_crispy.py`

**Files:**
- Modify: `scripts/build_crispy.py`
- Modify: `tests/test_build_crispy.py`

**Interfaces:**
- Consumes: `crispy-doom.lock` (`commit`), `patches/crispy-doom-fb-export.diff`, `patches/crispy-doom-ipc-input.diff`.
- Produces:
  - Module constant `PATCHES: tuple[Path, ...] = (_ROOT / "patches" / "crispy-doom-fb-export.diff", _ROOT / "patches" / "crispy-doom-ipc-input.diff")`.
  - `plan_commands(lock, *, build_dir, patches=PATCHES, check_only) -> list[list[str]]` — same shape as today, extended: when the marker is absent (or `check_only`), the list begins with `["git", "-C", str(build_dir), "reset", "--hard", lock.commit]` then `["git", "-C", str(build_dir), "clean", "-fd", "--", "src/"]`, then one `["git", "-C", str(build_dir), "apply", str(p)]` per patch for a real build, or `apply <p1>` (real) + `apply --check <p2>` under `check_only`; then `cmake` configure + build for a real build.
  - `run(...)` writes the `.doomed-prism-applied` marker exactly once, only after the **last** `git apply` (non-`--check`) command in the list succeeds.

- [ ] **Step 1: Write / update the failing tests**

Add to `tests/test_build_crispy.py`:

```python
def test_plan_commands_restores_then_applies_every_patch_in_order(tmp_path: Path) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    build_dir = tmp_path / "build" / "crispy"
    patches = (tmp_path / "p1.diff", tmp_path / "p2.diff")

    commands = build_crispy.plan_commands(
        lock, build_dir=build_dir, patches=patches, check_only=False
    )
    joined = [" ".join(c) for c in commands]

    assert joined[0].endswith(f"reset --hard {lock.commit}")
    assert "clean -fd -- src/" in joined[1]
    applies = [c for c in joined if " apply " in c]
    assert applies[0].endswith(str(patches[0]))
    assert applies[1].endswith(str(patches[1]))
    assert "--check" not in " ".join(applies)
    assert any("cmake" in c and "--build" in c for c in joined)


def test_plan_commands_check_only_applies_p1_for_real_then_checks_p2(tmp_path: Path) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    patches = (tmp_path / "p1.diff", tmp_path / "p2.diff")
    commands = build_crispy.plan_commands(
        lock, build_dir=tmp_path / "b", patches=patches, check_only=True
    )
    joined = [" ".join(c) for c in commands]
    assert joined[0].endswith(f"reset --hard {lock.commit}")
    assert any(c.endswith(f"apply {patches[0]}") for c in joined)          # p1 real
    assert any(c.endswith(f"apply --check {patches[1]}") for c in joined)  # p2 checked
    assert not any("cmake" in c for c in joined)


def test_run_writes_the_marker_only_after_the_last_patch_applies(tmp_path: Path) -> None:
    build_dir = tmp_path / "build" / "crispy"
    (build_dir / ".git").mkdir(parents=True)
    patches = (tmp_path / "p1.diff", tmp_path / "p2.diff")
    patches[0].write_text("x", encoding="utf-8")
    patches[1].write_text("x", encoding="utf-8")

    seen: list[str] = []

    def runner(cmd, **_):
        seen.append(" ".join(cmd))
        # simulate the SECOND `git apply` failing
        if cmd[-1].endswith("p2.diff") and "apply" in cmd and "--check" not in cmd:
            class _R:
                returncode = 1
            return _R()
        class _OK:
            returncode = 0
        return _OK()

    exit_code = build_crispy.run(
        [], runner=runner, _build_dir=build_dir, _lock_path=_write_lock(tmp_path),
        _patches=patches,
    )
    assert exit_code == 1
    assert not (build_dir / ".doomed-prism-applied").exists()
```

Also update `test_plan_commands_clones_pinned_tag_applies_patch_then_builds` and any test asserting a single `apply` to the new two-patch shape, and add `_patches=` passthrough to `run`'s test signature.

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/test_build_crispy.py -q`
Expected: FAIL — `PATCHES` / `patches=` / `_patches=` not present; single-apply assumption.

- [ ] **Step 3: Update `scripts/build_crispy.py`**

- Add `PATCHES = (_ROOT / "patches" / "crispy-doom-fb-export.diff", _ROOT / "patches" / "crispy-doom-ipc-input.diff")` near `_DEFAULT_PATCH` (keep `_DEFAULT_PATCH` only if still referenced; otherwise remove).
- `plan_commands(lock, *, build_dir, patches=PATCHES, check_only)`:

```python
def plan_commands(lock, *, build_dir, patches=PATCHES, check_only):
    git = ["git", "-C", str(build_dir)]
    commands: list[list[str]] = []
    if not (build_dir / ".git").exists():
        commands.append(["git", "clone", "--branch", lock.tag, lock.repo, str(build_dir)])
    commands.append(git + ["reset", "--hard", lock.commit])
    commands.append(git + ["clean", "-fd", "--", "src/"])
    if check_only:
        commands.append(git + ["apply", str(patches[0])])
        for patch in patches[1:]:
            commands.append(git + ["apply", "--check", str(patch)])
        return commands
    for patch in patches:
        commands.append(git + ["apply", str(patch)])
    commands.append(
        ["cmake", "-S", str(build_dir), "-B", str(build_dir / "build"),
         "-DCMAKE_BUILD_TYPE=Release"]
    )
    commands.append(["cmake", "--build", str(build_dir / "build")])
    return commands
```

- In `run`, add a `_patches` test seam and change the marker rule: the marker is written once, after the command that is `git ... apply <patches[-1]>` **without** `--check` succeeds. Replace the old per-`apply` marker write:

```python
last_apply = git + ["apply", str(patches[-1])]
...
for command in commands:
    result = runner(command, cwd=str(_ROOT))
    if getattr(result, "returncode", 0) != 0:
        print(f"command failed: {' '.join(command)}", file=sys.stderr)
        return 1
    if command == last_apply and not args.check:
        (build_dir / _MARKER).write_text("1", encoding="utf-8")
```

- Keep the existing `git rev-parse HEAD == lock.commit` verification and the `tarball_sha256` check (they still run; `reset --hard <commit>` keeps HEAD at the pinned commit).

- [ ] **Step 4: Run tests and the suite**

```bash
python -m pytest tests/test_build_crispy.py -q
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Real end-to-end check (opt-in)**

```bash
python scripts/build_crispy.py --check    # restore + apply p1 + --check p2
python scripts/build_crispy.py            # full series build; prints the exe path
```

- [ ] **Step 6: Commit**

```bash
git add scripts/build_crispy.py tests/test_build_crispy.py
git commit -m "feat: apply the Crispy Doom patch series cumulatively"
```

---

## Task 5: Normalized action model and router

**Files:**
- Create: `src/pewpew/input/__init__.py` (empty)
- Create: `src/pewpew/input/actions.py`
- Create: `tests/test_input_actions.py`

**Interfaces:**
- Consumes: `pewpew.ipc.protocol` (`Message`).
- Produces:
  - Constants: `MAGNITUDE_STEPS = 20`, `TURN_MAX_MOUSE_DELTA = 40`.
  - `class Action(enum.IntEnum)`: `MOVE_FORWARD = 1`, `MOVE_BACKWARD = 2`, `TURN_LEFT = 3`, `TURN_RIGHT = 4`, `FIRE = 10`, `USE = 11`, `PAUSE = 20`.
  - `@dataclass(frozen=True) class HeldAction`: `action: Action`, `magnitude: float` (0.0–1.0; always `1.0` for `MOVE_*`).
  - `class ActionRouter`:
    - `__init__(self, sink: Callable[[Message], None]) -> None`
    - `set_held(self, held: frozenset[HeldAction]) -> None` — diffs against the previous held set. For a newly held / released `MOVE_*` action emits `Message.action(code, 10000 | 0)`. For `TURN_*` emits `Message.turn(code, value)` where `value = _turn_value(magnitude)` whenever the **quantised** step changes (quantum `1/MAGNITUDE_STEPS`) or the action just became held/released (release → `value = 0`).
    - `pulse(self, action: Action) -> None` — emits `Message.pulse(action)`.
    - `discrete(self, action: Action) -> None` — emits `Message.discrete(action)`.
    - `release_all(self) -> None` — emits a `0`-value frame for every currently held action (in a stable order), then clears the held set. Emits nothing for already-released actions.
  - Module function `_turn_value(magnitude: float) -> int` = `max(0, min(TURN_MAX_MOUSE_DELTA, round(magnitude * TURN_MAX_MOUSE_DELTA)))`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the normalized action model and the IPC-emitting router."""

from __future__ import annotations

from pewpew.input.actions import (
    MAGNITUDE_STEPS,
    TURN_MAX_MOUSE_DELTA,
    Action,
    ActionRouter,
    HeldAction,
)
from pewpew.ipc.protocol import Message, MessageType


def test_action_codes_match_the_wire_table() -> None:
    assert (Action.MOVE_FORWARD, Action.MOVE_BACKWARD) == (1, 2)
    assert (Action.TURN_LEFT, Action.TURN_RIGHT) == (3, 4)
    assert (Action.FIRE, Action.USE, Action.PAUSE) == (10, 11, 20)


def _router():
    sent: list[Message] = []
    return ActionRouter(sent.append), sent


def test_set_held_emits_move_forward_on_hold_then_release() -> None:
    router, sent = _router()
    router.set_held(frozenset({HeldAction(Action.MOVE_FORWARD, 1.0)}))
    router.set_held(frozenset())
    assert sent == [
        Message.action(Action.MOVE_FORWARD, 10000),
        Message.action(Action.MOVE_FORWARD, 0),
    ]


def test_turn_emits_scaled_value_and_only_on_a_quantised_step_change() -> None:
    router, sent = _router()
    router.set_held(frozenset({HeldAction(Action.TURN_RIGHT, 1.0)}))
    router.set_held(frozenset({HeldAction(Action.TURN_RIGHT, 0.99)}))  # same quantum
    router.set_held(frozenset({HeldAction(Action.TURN_RIGHT, 0.5)}))   # new quantum
    router.set_held(frozenset())
    assert sent == [
        Message.turn(Action.TURN_RIGHT, TURN_MAX_MOUSE_DELTA),
        Message.turn(Action.TURN_RIGHT, round(0.5 * TURN_MAX_MOUSE_DELTA)),
        Message.turn(Action.TURN_RIGHT, 0),
    ]


def test_pulse_and_discrete_emit_one_frame_each() -> None:
    router, sent = _router()
    router.pulse(Action.FIRE)
    router.discrete(Action.PAUSE)
    assert sent == [Message.pulse(Action.FIRE), Message.discrete(Action.PAUSE)]


def test_release_all_releases_every_held_action_and_is_a_noop_when_empty() -> None:
    router, sent = _router()
    router.set_held(
        frozenset({HeldAction(Action.MOVE_FORWARD, 1.0), HeldAction(Action.TURN_LEFT, 1.0)})
    )
    sent.clear()
    router.release_all()
    kinds = {(m.type, m.code) for m in sent}
    assert (MessageType.ACTION, Action.MOVE_FORWARD) in kinds
    assert (MessageType.TURN, Action.TURN_LEFT) in kinds
    assert all(m.value == 0 for m in sent)
    sent.clear()
    router.release_all()
    assert sent == []
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/test_input_actions.py -q` — FAIL (module missing).

- [ ] **Step 3: Implement `src/pewpew/input/actions.py`**

```python
"""Normalized game actions and the router that turns held state into IPC frames."""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass

from pewpew.ipc.protocol import Message

MAGNITUDE_STEPS = 20
TURN_MAX_MOUSE_DELTA = 40

_MOVE = frozenset()  # filled below
_TURN = frozenset()


class Action(enum.IntEnum):
    MOVE_FORWARD = 1
    MOVE_BACKWARD = 2
    TURN_LEFT = 3
    TURN_RIGHT = 4
    FIRE = 10
    USE = 11
    PAUSE = 20


_MOVE = frozenset({Action.MOVE_FORWARD, Action.MOVE_BACKWARD})
_TURN = frozenset({Action.TURN_LEFT, Action.TURN_RIGHT})


@dataclass(frozen=True)
class HeldAction:
    action: Action
    magnitude: float


def _turn_value(magnitude: float) -> int:
    return max(0, min(TURN_MAX_MOUSE_DELTA, round(magnitude * TURN_MAX_MOUSE_DELTA)))


def _quantum(magnitude: float) -> int:
    return max(0, min(MAGNITUDE_STEPS, round(magnitude * MAGNITUDE_STEPS)))


class ActionRouter:
    def __init__(self, sink: Callable[[Message], None]) -> None:
        self._sink = sink
        self._held: dict[Action, int] = {}  # action -> last emitted quantum

    def set_held(self, held: frozenset[HeldAction]) -> None:
        incoming = {h.action: h.magnitude for h in held}
        for action in sorted(self._held):
            if action not in incoming:
                self._emit_release(action)
        for action in sorted(incoming, key=int):
            magnitude = incoming[action]
            if action in _MOVE:
                if action not in self._held:
                    self._held[action] = 1
                    self._sink(Message.action(int(action), 10000))
            elif action in _TURN:
                q = _quantum(magnitude)
                if self._held.get(action) != q:
                    self._held[action] = q
                    self._sink(Message.turn(int(action), _turn_value(magnitude)))

    def pulse(self, action: Action) -> None:
        self._sink(Message.pulse(int(action)))

    def discrete(self, action: Action) -> None:
        self._sink(Message.discrete(int(action)))

    def release_all(self) -> None:
        for action in sorted(self._held, key=int):
            self._emit_zero(action)
        self._held.clear()

    def _emit_release(self, action: Action) -> None:
        self._emit_zero(action)
        del self._held[action]

    def _emit_zero(self, action: Action) -> None:
        if action in _MOVE:
            self._sink(Message.action(int(action), 0))
        else:
            self._sink(Message.turn(int(action), 0))
```

- [ ] **Step 4: Run tests and the suite**

```bash
python -m pytest tests/test_input_actions.py -q
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/input/__init__.py src/pewpew/input/actions.py tests/test_input_actions.py
git commit -m "feat: add the normalized action model and IPC router"
```

---

## Task 6: Gaze zones and the stabilising filter

**Files:**
- Create: `src/pewpew/input/gaze.py`
- Create: `tests/test_input_gaze.py`

**Interfaces:**
- Consumes: `pewpew.input.actions` (`Action`, `HeldAction`).
- Produces:
  - Constants: `DEAD_ZONE_HALF_W = 180`, `DEAD_ZONE_HALF_H = 150`, `TURN_RESPONSE_EXPONENT = 1.5`, `MAGNITUDE_EMA_ALPHA = 0.4`, `DWELL_S = 0.15`, `JITTER_GRACE_S = 0.02`.
  - `class GazeZoneMap`:
    - `__init__(self, surface_w: int, surface_h: int, *, dead_zone: tuple[int, int] = (DEAD_ZONE_HALF_W, DEAD_ZONE_HALF_H), turn_exponent: float = TURN_RESPONSE_EXPONENT) -> None`
    - `resolve(self, x: int, y: int) -> frozenset[HeldAction]` — dead zone → empty; turn band (`|dx|>hw and |dy|<=hh`) → `{HeldAction(TURN_*, m)}` with `m = ((|dx|-hw)/(cx-hw)) ** turn_exponent` clamped to `[0,1]` (raw float); forward/back band (`|dy|>hh and |dx|<=hw`) → `{HeldAction(MOVE_*, 1.0)}`; corner (`|dx|>hw and |dy|>hh`) → the union of the matching `MOVE_*` (1.0) and `TURN_*` (raw float).
  - `class GazeFilter`:
    - `__init__(self, *, dwell_s: float = DWELL_S, grace_s: float = JITTER_GRACE_S, ema_alpha: float = MAGNITUDE_EMA_ALPHA) -> None`
    - `update(self, raw: frozenset[HeldAction], now: float) -> frozenset[HeldAction]` — per-action-id entry dwell (`dwell_s` of continuous presence before emit); release after `grace_s` of absence, or immediately when `raw` is non-empty but lacks the action (region change); `TURN_*` emitted magnitude is an EMA (`ema_alpha`) of the raw magnitude, re-seeded on re-acquisition; `MOVE_*` magnitude passed through as `1.0`.
    - `reset(self) -> None` — clears all timers and EMA state (called by `InputPipeline.release_all`).

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for gaze-zone resolution and the dwell / jitter filter."""

from __future__ import annotations

from pewpew.input.actions import Action, HeldAction
from pewpew.input.gaze import GazeFilter, GazeZoneMap


def _map() -> GazeZoneMap:
    return GazeZoneMap(640, 640)  # centre (320, 320); hw=180, hh=150


def _only(actions: frozenset[HeldAction]) -> set[Action]:
    return {h.action for h in actions}


def test_dead_zone_centre_resolves_to_nothing() -> None:
    assert _map().resolve(320, 320) == frozenset()


def test_right_turn_band_grows_monotonically_toward_the_edge() -> None:
    gmap = _map()
    near = next(iter(gmap.resolve(320 + 181, 320)))
    far = next(iter(gmap.resolve(639, 320)))
    assert near.action is Action.TURN_RIGHT and far.action is Action.TURN_RIGHT
    assert 0.0 <= near.magnitude < far.magnitude <= 1.0


def test_upper_band_is_move_forward_lower_is_move_backward() -> None:
    gmap = _map()
    assert _only(gmap.resolve(320, 320 - 200)) == {Action.MOVE_FORWARD}
    assert _only(gmap.resolve(320, 320 + 200)) == {Action.MOVE_BACKWARD}


def test_upper_right_corner_is_forward_plus_right_turn() -> None:
    assert _only(_map().resolve(320 + 200, 320 - 200)) == {
        Action.MOVE_FORWARD,
        Action.TURN_RIGHT,
    }


def test_filter_requires_dwell_before_emitting() -> None:
    f = GazeFilter(dwell_s=0.15, grace_s=0.02)
    raw = frozenset({HeldAction(Action.TURN_LEFT, 1.0)})
    assert f.update(raw, now=0.0) == frozenset()
    assert f.update(raw, now=0.1) == frozenset()
    got = f.update(raw, now=0.16)
    assert {h.action for h in got} == {Action.TURN_LEFT}


def test_filter_rides_out_a_one_sample_dropout_but_releases_after_grace() -> None:
    f = GazeFilter(dwell_s=0.15, grace_s=0.02)
    raw = frozenset({HeldAction(Action.MOVE_FORWARD, 1.0)})
    f.update(raw, now=0.0)
    f.update(raw, now=0.2)  # now held
    assert {h.action for h in f.update(frozenset(), now=0.205)} == {Action.MOVE_FORWARD}
    assert f.update(frozenset(), now=0.25) == frozenset()  # past grace


def test_region_change_releases_the_outgoing_action_immediately() -> None:
    f = GazeFilter(dwell_s=0.0, grace_s=1.0)
    left = frozenset({HeldAction(Action.TURN_LEFT, 1.0)})
    right = frozenset({HeldAction(Action.TURN_RIGHT, 1.0)})
    f.update(left, now=0.0)
    got = f.update(right, now=0.01)
    assert {h.action for h in got} == {Action.TURN_RIGHT}  # LEFT dropped same tick


def test_turn_magnitude_is_ema_smoothed() -> None:
    f = GazeFilter(dwell_s=0.0, grace_s=1.0, ema_alpha=0.5)
    m0 = next(iter(f.update(frozenset({HeldAction(Action.TURN_RIGHT, 1.0)}), now=0.0)))
    m1 = next(iter(f.update(frozenset({HeldAction(Action.TURN_RIGHT, 0.0)}), now=0.01)))
    assert m0.magnitude == 1.0
    assert 0.0 < m1.magnitude < 1.0
```

- [ ] **Step 2: Run and confirm failure** — `python -m pytest tests/test_input_gaze.py -q` — FAIL.

- [ ] **Step 3: Implement `src/pewpew/input/gaze.py`**

```python
"""Gaze-zone geometry and a dwell / jitter filter over the raw region set."""

from __future__ import annotations

from pewpew.input.actions import Action, HeldAction

DEAD_ZONE_HALF_W = 180
DEAD_ZONE_HALF_H = 150
TURN_RESPONSE_EXPONENT = 1.5
MAGNITUDE_EMA_ALPHA = 0.4
DWELL_S = 0.15
JITTER_GRACE_S = 0.02


class GazeZoneMap:
    def __init__(
        self,
        surface_w: int,
        surface_h: int,
        *,
        dead_zone: tuple[int, int] = (DEAD_ZONE_HALF_W, DEAD_ZONE_HALF_H),
        turn_exponent: float = TURN_RESPONSE_EXPONENT,
    ) -> None:
        self._cx = surface_w // 2
        self._cy = surface_h // 2
        self._hw, self._hh = dead_zone
        self._exp = turn_exponent

    def _turn_magnitude(self, dx: int) -> float:
        span = max(1, self._cx - self._hw)
        m = (abs(dx) - self._hw) / span
        return max(0.0, min(1.0, m)) ** self._exp

    def resolve(self, x: int, y: int) -> frozenset[HeldAction]:
        dx, dy = x - self._cx, y - self._cy
        out_x, out_y = abs(dx) > self._hw, abs(dy) > self._hh
        if not out_x and not out_y:
            return frozenset()
        actions: set[HeldAction] = set()
        if out_x and not out_y:
            side = Action.TURN_LEFT if dx < 0 else Action.TURN_RIGHT
            return frozenset({HeldAction(side, self._turn_magnitude(dx))})
        if out_y and not out_x:
            move = Action.MOVE_FORWARD if dy < 0 else Action.MOVE_BACKWARD
            return frozenset({HeldAction(move, 1.0)})
        # corner
        move = Action.MOVE_FORWARD if dy < 0 else Action.MOVE_BACKWARD
        side = Action.TURN_LEFT if dx < 0 else Action.TURN_RIGHT
        actions.add(HeldAction(move, 1.0))
        actions.add(HeldAction(side, self._turn_magnitude(dx)))
        return frozenset(actions)


class GazeFilter:
    def __init__(
        self,
        *,
        dwell_s: float = DWELL_S,
        grace_s: float = JITTER_GRACE_S,
        ema_alpha: float = MAGNITUDE_EMA_ALPHA,
    ) -> None:
        self._dwell_s = dwell_s
        self._grace_s = grace_s
        self._alpha = ema_alpha
        self._since: dict[Action, float] = {}     # first-seen time of a dwelling candidate
        self._emitted: dict[Action, float] = {}   # emitted action -> last-present time
        self._ema: dict[Action, float] = {}

    def reset(self) -> None:
        self._since.clear()
        self._emitted.clear()
        self._ema.clear()

    def update(self, raw: frozenset[HeldAction], now: float) -> frozenset[HeldAction]:
        raw_by_action = {h.action: h.magnitude for h in raw}
        raw_nonempty = bool(raw_by_action)

        # dwell bookkeeping for candidates not yet emitted
        for action in list(self._since):
            if action not in raw_by_action:
                del self._since[action]
        for action in raw_by_action:
            self._since.setdefault(action, now)

        # release bookkeeping for already-emitted actions
        for action in list(self._emitted):
            if action in raw_by_action:
                self._emitted[action] = now
            elif raw_nonempty:  # region change
                del self._emitted[action]
                self._ema.pop(action, None)
            elif now - self._emitted[action] > self._grace_s:
                del self._emitted[action]
                self._ema.pop(action, None)

        # promote dwelt candidates
        for action, first_seen in list(self._since.items()):
            if action not in self._emitted and now - first_seen >= self._dwell_s:
                self._emitted[action] = now

        out: set[HeldAction] = set()
        for action in self._emitted:
            raw_m = raw_by_action.get(action, self._ema.get(action, 1.0))
            if action in (Action.TURN_LEFT, Action.TURN_RIGHT):
                prev = self._ema.get(action, raw_m)
                m = self._alpha * raw_m + (1 - self._alpha) * prev
                self._ema[action] = m
            else:
                m = 1.0
            out.add(HeldAction(action, m))
        return frozenset(out)
```

- [ ] **Step 4: Run tests and the suite** — both green.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/input/gaze.py tests/test_input_gaze.py
git commit -m "feat: add gaze-zone resolution and the dwell/jitter filter"
```

---

## Task 7: Fire arbiter and the spoken-fire source protocols

**Files:**
- Create: `src/pewpew/input/fire.py`
- Create: `tests/test_input_fire.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - Constant `FIRE_DEBOUNCE_S = 0.12`.
  - `class DeliberateActionSource(typing.Protocol)`: `def activation_edge(self) -> bool: ...` (one-shot; cleared by the call).
  - `class SpokenFireSource(typing.Protocol)`: `def spoken_fire_edge(self) -> bool: ...`.
  - `class NullSpokenFireSource`: `spoken_fire_edge()` always returns `False`.
  - `class FireArbiter`:
    - `__init__(self, *, debounce_s: float = FIRE_DEBOUNCE_S) -> None`
    - `deliberate_action(self) -> None` — record a pending edge.
    - `spoken_fire(self) -> None` — record a pending edge.
    - `poll(self, now: float) -> bool` — `True` at most once per `debounce_s`: if any edge is pending and `now - last_shot >= debounce_s`, clear all pending edges, set `last_shot = now`, return `True`. An edge arriving while inside the window is discarded on the next `poll` where it is still "inside".
    - `reset(self) -> None` — clear pending edges and `last_shot`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the debounced, dual-source fire arbiter."""

from __future__ import annotations

from pewpew.input.fire import FireArbiter, NullSpokenFireSource


def test_single_edge_fires_once() -> None:
    a = FireArbiter(debounce_s=0.12)
    a.deliberate_action()
    assert a.poll(now=0.0) is True
    assert a.poll(now=0.01) is False


def test_two_edges_inside_the_window_fire_once() -> None:
    a = FireArbiter(debounce_s=0.12)
    a.deliberate_action()
    a.spoken_fire()
    assert a.poll(now=0.0) is True
    assert a.poll(now=0.05) is False


def test_edges_a_debounce_apart_fire_twice() -> None:
    a = FireArbiter(debounce_s=0.12)
    a.deliberate_action()
    assert a.poll(now=0.0) is True
    a.deliberate_action()
    assert a.poll(now=0.13) is True


def test_three_edges_at_0_005_020_fire_twice() -> None:
    a = FireArbiter(debounce_s=0.12)
    a.deliberate_action()
    assert a.poll(now=0.00) is True
    a.deliberate_action()          # arrives inside the window
    assert a.poll(now=0.05) is False  # discarded, not queued
    a.deliberate_action()
    assert a.poll(now=0.20) is True


def test_reset_drops_pending_edges() -> None:
    a = FireArbiter(debounce_s=0.12)
    a.deliberate_action()
    a.reset()
    assert a.poll(now=0.0) is False


def test_null_spoken_source_never_fires() -> None:
    assert NullSpokenFireSource().spoken_fire_edge() is False
```

- [ ] **Step 2: Run and confirm failure** — FAIL.

- [ ] **Step 3: Implement `src/pewpew/input/fire.py`**

```python
"""Fuse a deliberate action and a spoken 'pew pew' into one debounced FIRE."""

from __future__ import annotations

from typing import Protocol

FIRE_DEBOUNCE_S = 0.12


class DeliberateActionSource(Protocol):
    def activation_edge(self) -> bool: ...


class SpokenFireSource(Protocol):
    def spoken_fire_edge(self) -> bool: ...


class NullSpokenFireSource:
    def spoken_fire_edge(self) -> bool:
        return False


class FireArbiter:
    def __init__(self, *, debounce_s: float = FIRE_DEBOUNCE_S) -> None:
        self._debounce_s = debounce_s
        self._pending = False
        self._last_shot: float | None = None

    def deliberate_action(self) -> None:
        self._pending = True

    def spoken_fire(self) -> None:
        self._pending = True

    def poll(self, now: float) -> bool:
        if not self._pending:
            return False
        if self._last_shot is not None and now - self._last_shot < self._debounce_s:
            self._pending = False  # discard: not queued
            return False
        self._pending = False
        self._last_shot = now
        return True

    def reset(self) -> None:
        self._pending = False
        self._last_shot = None
```

- [ ] **Step 4: Run tests and the suite** — green.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/input/fire.py tests/test_input_fire.py
git commit -m "feat: add the debounced dual-source fire arbiter"
```

---

## Task 8: Input source protocol, the simulator source, and stubs

**Files:**
- Create: `src/pewpew/input/source.py`
- Create: `src/pewpew/input/simulator_source.py`
- Create: `tests/test_input_source.py`
- Create: `tests/test_input_source_qt.py`

**Interfaces:**
- Consumes: `pewpew.input.fire` (`SpokenFireSource`), PySide6.
- Produces:
  - `@dataclass(frozen=True) class InputSample`: `gaze_xy: tuple[int, int] | None`, `activation_edge: bool`, `pause_edge: bool`, `debug_fire_edge: bool`.
  - `class InputSource(typing.Protocol)`: `def sample(self, now: float) -> InputSample: ...`.
  - `class PrismInputSource`: `sample()` raises `NotImplementedError("Prism gaze/blink input arrives with the hardware phase")`.
  - `class DebugKeySpokenFireSource` (implements `SpokenFireSource`): `__init__(self)` reads `os.environ.get("DOOMED_PRISM_DEBUG_FIRE")`; `arm(self) -> None` sets a pending edge only when armed by the env var; `spoken_fire_edge(self) -> bool` returns and clears it.
  - `class SimulatorInputSource` (in `simulator_source.py`): `__init__(self, widget)` installs a Qt event filter on `widget`, enables mouse tracking. Tracks the last mouse position (clamped to `widget` 640×640 space), one-shot left-press → `activation_edge`, one-shot `Return`/`Enter` → `pause_edge`, one-shot `F9` (only when `DOOMED_PRISM_DEBUG_FIRE` set) → `debug_fire_edge`, `Leave` → `gaze_xy = None`. `sample(now)` returns the accumulated `InputSample` and clears the edges.

- [ ] **Step 1: Write the failing pure tests** (`tests/test_input_source.py`)

```python
"""Pure tests for the input-source stubs (no Qt)."""

from __future__ import annotations

import pytest

from pewpew.input.source import DebugKeySpokenFireSource, InputSample, PrismInputSource


def test_prism_source_is_a_documented_stub() -> None:
    with pytest.raises(NotImplementedError, match="hardware phase"):
        PrismInputSource().sample(0.0)


def test_debug_fire_source_is_inert_without_the_env_var(monkeypatch) -> None:
    monkeypatch.delenv("DOOMED_PRISM_DEBUG_FIRE", raising=False)
    src = DebugKeySpokenFireSource()
    src.arm()
    assert src.spoken_fire_edge() is False


def test_debug_fire_source_fires_once_when_armed(monkeypatch) -> None:
    monkeypatch.setenv("DOOMED_PRISM_DEBUG_FIRE", "1")
    src = DebugKeySpokenFireSource()
    src.arm()
    assert src.spoken_fire_edge() is True
    assert src.spoken_fire_edge() is False


def test_input_sample_defaults() -> None:
    s = InputSample(gaze_xy=(1, 2), activation_edge=False, pause_edge=False, debug_fire_edge=False)
    assert s.gaze_xy == (1, 2)
```

- [ ] **Step 2: Write the failing Qt test** (`tests/test_input_source_qt.py`)

```python
"""Real pytest-qt coverage for SimulatorInputSource."""

from __future__ import annotations

import pytest

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QKeyEvent, QMouseEvent
    from PySide6.QtWidgets import QWidget
except ModuleNotFoundError as error:
    raise RuntimeError("PySide6 is required by the project's dev test extra") from error
except ImportError as error:
    if "libEGL.so.1" not in str(error):
        raise
    pytest.skip("PySide6 cannot initialize (no libEGL)", allow_module_level=True)

from pewpew.input.simulator_source import SimulatorInputSource


def _mouse(kind, pos, button=Qt.LeftButton):
    return QMouseEvent(kind, pos, button, button, Qt.NoModifier)


def test_mouse_move_then_press_then_sample(qtbot) -> None:
    w = QWidget()
    w.setFixedSize(640, 640)
    qtbot.addWidget(w)
    src = SimulatorInputSource(w)
    w.event(_mouse(QMouseEvent.Type.MouseMove, QPoint(400, 300)))
    w.event(_mouse(QMouseEvent.Type.MouseButtonPress, QPoint(400, 300)))
    s = src.sample(0.0)
    assert s.gaze_xy == (400, 300)
    assert s.activation_edge is True
    assert src.sample(0.0).activation_edge is False  # one-shot


def test_return_key_sets_pause_edge_once(qtbot) -> None:
    w = QWidget()
    w.setFixedSize(640, 640)
    qtbot.addWidget(w)
    src = SimulatorInputSource(w)
    w.event(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Return, Qt.NoModifier))
    assert src.sample(0.0).pause_edge is True
    assert src.sample(0.0).pause_edge is False


def test_leave_clears_gaze(qtbot) -> None:
    from PySide6.QtCore import QEvent

    w = QWidget()
    w.setFixedSize(640, 640)
    qtbot.addWidget(w)
    src = SimulatorInputSource(w)
    w.event(_mouse(QMouseEvent.Type.MouseMove, QPoint(10, 10)))
    w.event(QEvent(QEvent.Type.Leave))
    assert src.sample(0.0).gaze_xy is None


def test_f9_debug_fire_edge_only_with_env(qtbot, monkeypatch) -> None:
    monkeypatch.setenv("DOOMED_PRISM_DEBUG_FIRE", "1")
    w = QWidget()
    w.setFixedSize(640, 640)
    qtbot.addWidget(w)
    src = SimulatorInputSource(w)
    w.event(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_F9, Qt.NoModifier))
    assert src.sample(0.0).debug_fire_edge is True
```

- [ ] **Step 3: Run and confirm failure** — FAIL (modules missing).

- [ ] **Step 4: Implement `src/pewpew/input/source.py`**

```python
"""Input-source protocol, the InputSample record, and non-simulator stubs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class InputSample:
    gaze_xy: tuple[int, int] | None
    activation_edge: bool
    pause_edge: bool
    debug_fire_edge: bool


class InputSource(Protocol):
    def sample(self, now: float) -> InputSample: ...


class PrismInputSource:
    def sample(self, now: float) -> InputSample:
        raise NotImplementedError(
            "Prism gaze/blink input arrives with the hardware phase"
        )


class DebugKeySpokenFireSource:
    def __init__(self) -> None:
        self._enabled = bool(os.environ.get("DOOMED_PRISM_DEBUG_FIRE"))
        self._pending = False

    def arm(self) -> None:
        if self._enabled:
            self._pending = True

    def spoken_fire_edge(self) -> bool:
        fired, self._pending = self._pending, False
        return fired
```

- [ ] **Step 5: Implement `src/pewpew/input/simulator_source.py`**

```python
"""Read gaze / click / Enter / F9 from Qt events on the host widget."""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QWidget

from pewpew.input.source import InputSample


class SimulatorInputSource(QObject):
    def __init__(self, widget: QWidget) -> None:
        super().__init__(widget)
        self._widget = widget
        self._debug_fire = bool(os.environ.get("DOOMED_PRISM_DEBUG_FIRE"))
        self._gaze: tuple[int, int] | None = None
        self._activation = False
        self._pause = False
        self._debug_edge = False
        widget.setMouseTracking(True)
        widget.installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        etype = event.type()
        if etype == QEvent.Type.MouseMove:
            p = event.position().toPoint()
            x = max(0, min(self._widget.width() - 1, p.x()))
            y = max(0, min(self._widget.height() - 1, p.y()))
            self._gaze = (x, y)
        elif etype == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
            self._activation = True
        elif etype == QEvent.Type.Leave:
            self._gaze = None
        elif etype == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._pause = True
            elif key == Qt.Key_F9 and self._debug_fire:
                self._debug_edge = True
        return False

    def sample(self, now: float) -> InputSample:
        s = InputSample(self._gaze, self._activation, self._pause, self._debug_edge)
        self._activation = self._pause = self._debug_edge = False
        return s
```

- [ ] **Step 6: Run tests and the suite**

```bash
python -m pytest tests/test_input_source.py tests/test_input_source_qt.py -q
python -m pytest -q
```

Expected: PASS (the Qt module skips only where PySide6 cannot init).

- [ ] **Step 7: Commit**

```bash
git add src/pewpew/input/source.py src/pewpew/input/simulator_source.py tests/test_input_source.py tests/test_input_source_qt.py
git commit -m "feat: add the input-source protocol and simulator source"
```

---

## Task 9: The input pipeline

**Files:**
- Create: `src/pewpew/input/pipeline.py`
- Create: `tests/fakes/fake_input.py`
- Create: `tests/test_input_pipeline.py`

**Interfaces:**
- Consumes: `pewpew.input.actions` (`ActionRouter`, `Action`), `pewpew.input.gaze` (`GazeZoneMap`, `GazeFilter`), `pewpew.input.fire` (`FireArbiter`, `SpokenFireSource`, `NullSpokenFireSource`), `pewpew.input.source` (`InputSource`, `InputSample`), `pewpew.ipc.protocol` (`Message`).
- Produces:
  - `class InputPipeline`:
    - `__init__(self, source: InputSource, send: Callable[[Message], None], *, surface: tuple[int, int] = (640, 640), spoken_fire: SpokenFireSource | None = None) -> None` — builds `GazeZoneMap`, `GazeFilter`, `FireArbiter`, `ActionRouter(send)`; `spoken_fire` defaults to `NullSpokenFireSource()`.
    - `tick(self, now: float) -> None` — one host tick: `sample = source.sample(now)`; gaze → `GazeZoneMap.resolve` → `GazeFilter.update` → `ActionRouter.set_held`; `if sample.activation_edge: fire.deliberate_action()`; `if spoken_fire.spoken_fire_edge() or sample.debug_fire_edge: fire.spoken_fire()`; `if fire.poll(now): router.pulse(Action.FIRE)`; `if sample.pause_edge: self.toggle_pause()`.
    - `toggle_pause(self) -> None` — `router.discrete(Action.PAUSE)`; flip `self.paused`.
    - `release_all(self) -> None` — `filter.reset()`, `fire.reset()`, `router.release_all()`, `self.paused = False`.
    - `paused: bool` attribute (starts `False`).
  - `tests/fakes/fake_input.py`: `class FakeInputSource` with a `queue: list[InputSample]`; `sample(now)` pops the front or returns an all-`None`/`False` sample.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the InputPipeline integration unit."""

from __future__ import annotations

from fakes.fake_input import FakeInputSource
from pewpew.input.pipeline import InputPipeline
from pewpew.input.source import InputSample
from pewpew.ipc.protocol import Message, MessageType


def _pipe(samples):
    src = FakeInputSource(list(samples))
    sent: list[Message] = []
    return InputPipeline(src, sent.append), sent


def test_gaze_in_the_right_band_emits_a_turn_frame_after_dwell() -> None:
    far_right = InputSample((639, 320), False, False, False)
    pipe, sent = _pipe([far_right] * 40)
    for i in range(40):
        pipe.tick(now=i * 0.05)  # 2s of ticks — dwell (0.15s) satisfied
    turns = [m for m in sent if m.type is MessageType.TURN and m.value > 0]
    assert turns, "expected at least one TURN frame with a non-zero value"
    assert turns[0].code == 4  # TURN_RIGHT


def test_activation_edge_produces_a_fire_pulse() -> None:
    click = InputSample((320, 320), True, False, False)
    pipe, sent = _pipe([click])
    pipe.tick(now=0.0)
    assert Message.pulse(10) in sent


def test_pause_edge_toggles_paused_and_sends_one_discrete() -> None:
    p = InputSample((320, 320), False, True, False)
    pipe, sent = _pipe([p])
    assert pipe.paused is False
    pipe.tick(now=0.0)
    assert pipe.paused is True
    assert sent.count(Message.discrete(20)) == 1


def test_release_all_emits_zeros_and_clears_paused() -> None:
    hold = InputSample((639, 320), False, False, False)
    pipe, sent = _pipe([hold] * 10)
    for i in range(10):
        pipe.tick(now=i * 0.05)
    pipe.toggle_pause()
    sent.clear()
    pipe.release_all()
    assert pipe.paused is False
    assert sent and all(m.value == 0 for m in sent if m.type in (MessageType.TURN, MessageType.ACTION))
```

Create `tests/fakes/fake_input.py`:

```python
"""A scripted InputSource for pipeline tests."""

from __future__ import annotations

from pewpew.input.source import InputSample

_EMPTY = InputSample(gaze_xy=None, activation_edge=False, pause_edge=False, debug_fire_edge=False)


class FakeInputSource:
    def __init__(self, queue: list[InputSample]) -> None:
        self.queue = queue

    def sample(self, now: float) -> InputSample:
        return self.queue.pop(0) if self.queue else _EMPTY
```

- [ ] **Step 2: Run and confirm failure** — FAIL.

- [ ] **Step 3: Implement `src/pewpew/input/pipeline.py`**

```python
"""The single unit that wires source -> gaze -> fire -> router -> IPC send."""

from __future__ import annotations

from collections.abc import Callable

from pewpew.input.actions import Action, ActionRouter
from pewpew.input.fire import FireArbiter, NullSpokenFireSource, SpokenFireSource
from pewpew.input.gaze import GazeFilter, GazeZoneMap
from pewpew.input.source import InputSource
from pewpew.ipc.protocol import Message


class InputPipeline:
    def __init__(
        self,
        source: InputSource,
        send: Callable[[Message], None],
        *,
        surface: tuple[int, int] = (640, 640),
        spoken_fire: SpokenFireSource | None = None,
    ) -> None:
        self._source = source
        self._zones = GazeZoneMap(*surface)
        self._filter = GazeFilter()
        self._fire = FireArbiter()
        self._router = ActionRouter(send)
        self._spoken = spoken_fire or NullSpokenFireSource()
        self.paused = False

    def tick(self, now: float) -> None:
        sample = self._source.sample(now)
        raw = (
            self._zones.resolve(*sample.gaze_xy)
            if sample.gaze_xy is not None
            else frozenset()
        )
        self._router.set_held(self._filter.update(raw, now))
        if sample.activation_edge:
            self._fire.deliberate_action()
        if self._spoken.spoken_fire_edge() or sample.debug_fire_edge:
            self._fire.spoken_fire()
        if self._fire.poll(now):
            self._router.pulse(Action.FIRE)
        if sample.pause_edge:
            self.toggle_pause()

    def toggle_pause(self) -> None:
        self._router.discrete(Action.PAUSE)
        self.paused = not self.paused

    def release_all(self) -> None:
        self._filter.reset()
        self._fire.reset()
        self._router.release_all()
        self.paused = False
```

- [ ] **Step 4: Run tests and the suite** — green.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/input/pipeline.py tests/fakes/fake_input.py tests/test_input_pipeline.py
git commit -m "feat: add the input pipeline integration unit"
```

---

## Task 10: Engine — IPC address and warp argv

**Files:**
- Modify: `src/pewpew/engine.py`
- Modify: `tests/test_engine.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `DoomProcess.start(self, *, ipc_address: str | None = None) -> int` — when `ipc_address` is given, adds `DOOMED_PRISM_IPC_ADDR=<addr>` to the child env alongside `DOOMED_PRISM_FB_NAME`.
  - `DoomProcess.ipc_address` property → `str | None` (set by `start`, unchanged by `stop`).
  - `_command()` appends `["-warp", *shlex.split(os.environ["DOOMED_PRISM_WARP"]), "-skill", os.environ.get("DOOMED_PRISM_SKILL", "3")]` **only** when `DOOMED_PRISM_WARP` is set and non-empty. `stop()` does not touch any socket path.

- [ ] **Step 1: Write / update the failing tests**

Add to `tests/test_engine.py`:

```python
def test_start_passes_the_ipc_address_through_the_child_environment(tmp_path: Path) -> None:
    factory = FakePopenFactory()
    engine = DoomProcess(_runtime_config(tmp_path), popen_factory=factory)
    engine.start(ipc_address="127.0.0.1:54321")
    assert engine.ipc_address == "127.0.0.1:54321"
    assert factory.processes[0].env["DOOMED_PRISM_IPC_ADDR"] == "127.0.0.1:54321"


def test_warp_env_appends_warp_and_skill_argv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOOMED_PRISM_WARP", "1 1")
    monkeypatch.delenv("DOOMED_PRISM_SKILL", raising=False)
    factory = FakePopenFactory()
    DoomProcess(_runtime_config(tmp_path), popen_factory=factory).start()
    args = factory.processes[0].arguments
    assert args[-4:] == ["-warp", "1", "1", "-skill", "3"][-4:] or args[-5:] == ["-warp", "1", "1", "-skill", "3"]
```

Update `test_start_launches_configured_windowed_engine_once_and_returns_its_pid` to begin with:

```python
    monkeypatch.delenv("DOOMED_PRISM_WARP", raising=False)
    monkeypatch.delenv("DOOMED_PRISM_SKILL", raising=False)
```

(add `monkeypatch: pytest.MonkeyPatch` to its signature).

- [ ] **Step 2: Run and confirm failure** — FAIL (`ipc_address` / warp not present).

- [ ] **Step 3: Modify `src/pewpew/engine.py`**

- Add `import shlex`.
- `__init__`: add `self._ipc_address: str | None = None`.
- `start`:

```python
def start(self, *, ipc_address: str | None = None) -> int:
    if self.poll() is None and self._process is not None:
        raise EngineAlreadyRunning("Crispy Doom is already running")
    name = f"doomed-prism-fb-{os.getpid()}-{secrets.token_hex(4)}"
    child_env = {**os.environ, "DOOMED_PRISM_FB_NAME": name}
    if ipc_address:
        child_env["DOOMED_PRISM_IPC_ADDR"] = ipc_address
        self._ipc_address = ipc_address
    self._process = self._popen_factory(self._command(), child_env)
    self._frame_segment_name = name
    return self._process.pid
```

- Add:

```python
@property
def ipc_address(self) -> str | None:
    return self._ipc_address
```

- `_command`: before `return`, build the base list, then:

```python
    warp = os.environ.get("DOOMED_PRISM_WARP")
    if warp:
        command += ["-warp", *shlex.split(warp), "-skill",
                    os.environ.get("DOOMED_PRISM_SKILL", "3")]
    return command
```

- Leave `_release_segment()` (the `/dev/shm` framebuffer unlink) exactly as is; do not add any socket unlink.

- [ ] **Step 4: Run tests and the suite** — green.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/engine.py tests/test_engine.py
git commit -m "feat: pass the IPC address and optional warp target to Crispy"
```

---

## Task 11: Host widget — server lifecycle, input tick, release-all, pause overlay

**Files:**
- Modify: `src/pewpew/host_widget.py`
- Modify: `tests/test_host_widget_qt.py`

**Interfaces:**
- Consumes: `pewpew.ipc.server` (`IpcServer`), `pewpew.input.pipeline` (`InputPipeline`), `pewpew.input.simulator_source` (`SimulatorInputSource`), `pewpew.input.source` (`DebugKeySpokenFireSource`), `pewpew.engine.DoomProcess.ipc_address`.
- Produces (added to `DoomHostWidget`, all keyword-only, all with test-injectable defaults):
  - `__init__(..., *, ipc_server=None, input_pipeline_factory=None)`.
  - `showEvent`: if not injected, `self._server = IpcServer(on_disconnect=self._on_ipc_disconnect)`, `addr = self._server.start()`, `self._engine.start(ipc_address=addr)` (replacing the bare `start()`), then build `self._pipeline` from a `SimulatorInputSource(self.viewport)` (+ `DebugKeySpokenFireSource()` as `spoken_fire`) and `self._server.send`. Arm `self._ipc_deadline = clock() + 10.0`.
  - `_on_tick`: **first line** (before every existing early return) → `self._server.poll()`. After the existing frame-wait guard clears, also call `self._pipeline.tick(self._clock())`. If the handshake has not completed by `_ipc_deadline` and frames are flowing → `_cleanup_after_startup_failure()` then `raise RuntimeError("engine did not connect input")`. If `self._server.protocol_mismatch` → `_cleanup_after_startup_failure()` then `raise RuntimeError("input protocol mismatch")`.
  - `_on_ipc_disconnect`: `self._pipeline.release_all()`, `self._server.close()` (no `PAUSE`).
  - `hideEvent`: if `not self._shutdown_requested` and started → `self._pipeline.release_all()`; if `not self._pipeline.paused` → `self._pipeline.toggle_pause()`; show `_PauseOverlay`. (Keep the existing `self._timer.stop()`.)
  - `showEvent` (restart branch, already-started): if `self._pipeline.paused` → `self._pipeline.toggle_pause()` (unpause); hide `_PauseOverlay`; `self._pipeline.release_all()`; restart timer.
  - `cleanup()`: extend to stop the timer → `self._pipeline.release_all()` (guarded: pipeline may be `None`) → `self._server.close()` → `reader.close()` → `engine.stop()`, keeping the existing retry-on-transient-failure behaviour and idempotence.
  - `_PauseOverlay(QWidget)`: a translucent child of the host, `objectName() == "pause_overlay"`, draws the word `PAUSED`; `setVisible` driven by `self._pipeline.paused`.

- [ ] **Step 1: Write the failing tests**

Add fakes + tests to `tests/test_host_widget_qt.py`:

```python
class _Server:
    def __init__(self) -> None:
        self.started = False
        self.closed = 0
        self.sent: list = []
        self.is_connected = False
        self.protocol_mismatch = False
        self.on_disconnect = lambda: None

    def start(self) -> str:
        self.started = True
        return "127.0.0.1:0"

    def poll(self) -> None:
        pass

    def send(self, message) -> None:
        self.sent.append(message)

    def close(self) -> None:
        self.closed += 1


def test_showevent_starts_server_before_engine_and_passes_the_address(qtbot) -> None:
    order: list[str] = []
    engine = _Engine()
    engine.start = lambda *, ipc_address=None: order.append(f"engine:{ipc_address}") or 8128
    server = _Server()
    server.start = lambda: order.append("server") or "127.0.0.1:0"
    host = _host(qtbot, engine=engine)
    host._inject_server(server)  # test seam set by the ctor when ipc_server= is passed
    host.show()
    assert order == ["server", "engine:127.0.0.1:0"]


def test_on_tick_polls_the_server_before_any_early_return(qtbot) -> None:
    server = _Server()
    polled: list[int] = []
    server.poll = lambda: polled.append(1)
    reader = _Reader()
    reader.available = False  # forces the early "waiting for segment" return
    host = _host(qtbot, reader=reader)
    host._inject_server(server)
    host.show()
    host._on_tick()
    assert polled  # poll happened despite the early return


def test_ipc_disconnect_releases_all_and_closes_without_pause(qtbot) -> None:
    server = _Server()
    host = _host(qtbot)
    host._inject_server(server)
    host.show()
    host._on_ipc_disconnect()
    assert server.closed == 1
    assert not any(getattr(m, "code", None) == 20 for m in server.sent)  # no PAUSE
```

(Adapt `_host` / `DoomHostWidget.__init__` so a test can inject the server; the simplest seam is an `ipc_server=` ctor kwarg plus an `_inject_server` helper used only by tests, or pass `ipc_server=` directly.)

- [ ] **Step 2: Run and confirm failure** — FAIL.

- [ ] **Step 3: Implement the `host_widget.py` changes** per the Interfaces block above. Keep the M2 framebuffer path (`_DoomViewport`, `_seen_frame`, the 10 s frame deadline) intact; layer the IPC concerns beside it. `_on_tick` order: `server.poll()` → (frame-wait guard / early returns) → `pipeline.tick()` → IPC-deadline / protocol-mismatch checks → the existing counter/repaint logic.

- [ ] **Step 4: Run tests and the suite**

```bash
python -m pytest tests/test_host_widget.py tests/test_host_widget_qt.py -q
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/host_widget.py tests/test_host_widget_qt.py
git commit -m "feat: wire the IPC server and input pipeline into the host widget"
```

---

## Task 12: README refresh and distribution metadata

**Files:**
- Modify: `README.md`
- Modify: `tests/test_distribution_metadata.py`

**Interfaces:**
- Consumes: nothing.
- Produces: README "License" names **both** patches as the corresponding source; "Current status" notes M3a (IPC input) in progress; "What comes next" moved forward with a line that voice ships in Milestone 3b after an offline-speech licence review; `test_distribution_metadata.py` expectations updated for `src/pewpew/ipc/`, `src/pewpew/input/`, `patches/crispy-doom-ipc-input.diff`, `scripts/ci_ipc_smoke.py`.

- [ ] **Step 1: Update the failing metadata test**

In `tests/test_distribution_metadata.py`, extend `test_source_distribution_explicitly_excludes_unshipped_test_dependencies` (or add a sibling test) to assert the README License paragraph mentions "IPC-input patch" and that `patches/` contains both diff filenames:

```python
def test_readme_license_names_both_engine_patches() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "crispy-doom-fb-export.diff" not in readme  # names, not filenames, in prose
    assert "frame-export" in readme and "IPC-input" in readme
    patches = {p.name for p in (ROOT / "patches").iterdir()}
    assert patches == {"crispy-doom-fb-export.diff", "crispy-doom-ipc-input.diff"}
```

- [ ] **Step 2: Run and confirm failure** — FAIL (README not updated).

- [ ] **Step 3: Edit `README.md`**

- "Current status": add a bullet — *Milestone 3a (hands-free input over a local IPC socket) is in progress on `feature/doomed-prism-m3`.*
- "What comes next": reword to *Milestone 3a delivers the input core and the IPC boundary. Voice — spoken menu/weapon commands and a spoken "pew pew" — ships in Milestone 3b, after an offline-speech-library licence review.*
- "License": change *"contains only the frame‑export patch and a pinned reference to Crispy Doom, never its source"* → *"contains only the frame‑export and IPC‑input patches and a pinned reference to Crispy Doom, never its source"*.

- [ ] **Step 4: Run tests and both safety scans**

```bash
python -m pytest -q
python scripts/check_publication_safety.py --root .
python scripts/check_publication_safety.py --root . --history
```

Expected: green; both scans exit 0.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_distribution_metadata.py
git commit -m "docs: name the IPC-input patch in the README and metadata tests"
```

---

## Task 13: CI IPC runtime smoke test

**Files:**
- Create: `scripts/ci_ipc_smoke.py`
- Modify: `.github/workflows/ci.yml`
- Create: `tests/test_validation_docs_m3.py`

**Interfaces:**
- Consumes: `pewpew.ipc.server.IpcServer`, `pewpew.ipc.protocol.Message`, `pewpew.framebuffer.FrameReader`.
- Produces: a CI-only script (not a pytest module) that builds nothing itself; it takes `<crispy-doom-exe> <iwad>`, binds an `IpcServer` at the fixed path `/tmp/doomed-prism-ipc-ci.sock` via an `address_factory`, launches the engine with `DOOMED_PRISM_IPC_ADDR`, `DOOMED_PRISM_FB_NAME`, and `DOOMED_PRISM_WARP="1 1"`, completes the handshake, streams a 500-frame action flood (`TURN_RIGHT` ramp then a `FIRE` burst), asserts the framebuffer `frame_counter` advances throughout, then `server.close()` + `SIGINT` and asserts no orphan `crispy-doom` and the socket path is gone. Prints only the socket basename + presence/absence. Exits 0 on success / non-POSIX, 1 on failure.

- [ ] **Step 1: Write `scripts/ci_ipc_smoke.py`**

```python
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
    listener.listen(1)
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
            server.send(Message.turn(4, (i % 40)))
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
```

- [ ] **Step 2: Add the CI step and the M3 branch trigger**

In `.github/workflows/ci.yml`:
- `on.push.branches`: add `- feature/doomed-prism-m3`.
- In `linux-build-and-posix-smoke`, after the "POSIX shared-memory runtime smoke test" step:

```yaml
      - name: IPC runtime smoke test
        run: |
          set -o pipefail
          xvfb-run -a python scripts/ci_ipc_smoke.py \
            "${{ steps.build.outputs.exe }}" \
            /usr/share/games/doom/freedoom1.wad | tee ipc-smoke.log
          {
            echo "### IPC runtime validation"
            echo ""
            echo ":white_check_mark: The patched engine connected over a local socket, completed the version handshake, stayed live with an advancing \`frame_counter\` under a 500-frame action flood, and tore down cleanly with no orphan and no leftover socket."
          } >> "$GITHUB_STEP_SUMMARY"
```

Do **not** `cat ipc-smoke.log` into the summary (the log names the socket basename only, but keep the summary templated).

- [ ] **Step 3: Write `tests/test_validation_docs_m3.py`**

```python
"""Static contracts for the Milestone 3a manual decision gate."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "docs" / "validation" / "milestone-3a-checklist.md"
RESULT = ROOT / "docs" / "validation" / "milestone-3a-result.md"


def _docs() -> str:
    return CHECKLIST.read_text(encoding="utf-8") + RESULT.read_text(encoding="utf-8")


def test_gate_carries_the_four_decision_strings() -> None:
    d = _docs()
    assert "PASS — IPC input path viable" in d
    assert "FAIL — IPC input path insufficient" in d
    assert "BLOCKED/RETRY — implementation or environment failure" in d
    assert "PENDING — incomplete evidence" in d


def test_gate_requires_ipc_only_play_with_the_sdl_window_unfocused() -> None:
    d = _docs()
    assert "SDL window" in d and "unfocused" in d
    assert "release" in d.lower() and "held" in d.lower()


def test_gate_runs_both_publication_safety_scans_and_the_diff_stat() -> None:
    checklist = CHECKLIST.read_text(encoding="utf-8")
    assert "check_publication_safety.py --root ." in checklist
    assert "check_publication_safety.py --root . --history" in checklist
    assert "git apply --stat patches/crispy-doom-ipc-input.diff" in checklist


def test_gate_uses_placeholder_ipc_addresses_only() -> None:
    d = _docs()
    assert "<tempdir>/doomed-prism-ipc-<pid>-<token>.sock" in d
    assert "127.0.0.1:<port>" in d
    for private in ("AppData\\Local\\Temp", "/home/", "/Users/"):
        assert private not in d
```

- [ ] **Step 4: Run tests and the suite**

```bash
python -m pytest tests/test_validation_docs_m3.py -q   # fails until Task 14 writes the docs
python -m pytest -q --deselect tests/test_validation_docs_m3.py
```

Expected: the M3 doc test fails (docs not yet written — Task 14); everything else green. Do not commit a broken test into a green suite — either mark the four `test_validation_docs_m3` tests `@pytest.mark.xfail(reason="docs land in Task 14", strict=True)` now and remove the marks in Task 14, or fold this file's creation into Task 14. **Chosen: fold `tests/test_validation_docs_m3.py` into Task 14** and, in this task, commit only `ci_ipc_smoke.py` + the `ci.yml` changes.

- [ ] **Step 5: Commit**

```bash
git add scripts/ci_ipc_smoke.py .github/workflows/ci.yml
git commit -m "ci: add the POSIX IPC runtime smoke test"
```

---

## Task 14: Milestone 3a decision gate

**Files:**
- Create: `docs/validation/milestone-3a-checklist.md`
- Create: `docs/validation/milestone-3a-result.md`
- Create: `tests/test_validation_docs_m3.py` (from Task 13 Step 3)

**Interfaces:**
- Consumes: everything.
- Produces: the manual gate documents (mirroring `docs/validation/milestone-2-checklist.md` / `-result.md` structure and safety rules) and the static contract test.

- [ ] **Step 1: Write `docs/validation/milestone-3a-checklist.md`**

Mirror the M2 checklist. Sections: *Scope and safety* (no Raven source / credentials / private paths / commercial IWAD identity; evidence under gitignored `artifacts/milestone-3/`; record the IPC address only as `<tempdir>/doomed-prism-ipc-<pid>-<token>.sock` / `127.0.0.1:<port>` and only its presence/absence + port). *Environment and launch* (`build_crispy.py` builds the series; `build_crispy.py --check` passes — restore + real `apply p1` + `apply --check p2`; record `git apply --stat patches/crispy-doom-ipc-input.diff` and confirm the file set + line ceiling; `doomed-prism validate` exits 0; `pytest -q` green; `check_publication_safety.py --root .` and `--root . --history` exit 0; M2 before/after crispy-doom PID baseline; `DOOMED_PRISM_WARP="1 1"`, `DOOMED_PRISM_DEBUG_FIRE=1`; launch `doomed-prism run-desktop`). *Objective checks* (one new PID; IPC socket present while running, absent after; `FrameReader` probe still shows `frame_counter` advancing; with Crispy's SDL window minimised/behind for the whole run: left/right turn bands turn the view, return-to-dead-zone stops within ~2 ticks, farther gaze turns faster, upper/lower bands walk forward/back, upper corner walks-and-turns, one click = one shot, five fast clicks < five shots, `F9` fires through the same path, click + `F9` within ~30 ms = one shot, `Enter` shows `PAUSED` and pauses / `Enter` resumes; no `SetParent` anywhere). *Lifecycle checks* (sleep/conceal → pause + overlay, resume → unpause + no stuck key; kill PewPew while a turn is held → DOOM stops turning, keeps running on SDL, no orphan; normal close → `cleanup()` stop-tick → release-all → server-close → reader-close → engine-stop, no exception, one PID gone, socket removed). *Per-mode evidence* (Raw + each optical mode; one short local Freedoom-only video or two time-separated captures showing gaze-driven motion + a fired shot inside the composited viewport with the SDL window unfocused; any clip promoted to `docs/media/` is Freedoom-only, reviewed frame-by-frame for usernames/paths/IWAD identity). *Hard decision rule* (the four strings from spec §17). *Final automated verification and commit* (`pytest -q`; `git diff --check`; exact-path `git add` of only the two `milestone-3a-*` docs; `git diff --cached --name-status`; `git diff --cached --check`; both safety scans; `git commit -m "docs: record IPC input path result"`; `git status --short` empty).

- [ ] **Step 2: Write `docs/validation/milestone-3a-result.md`**

Mirror `milestone-2-result.md`: run identification, environment, launch/interaction, objective checks, per-mode evidence table, lifecycle-check results, automated verification, and a single **Final decision** field starting at `PENDING — incomplete evidence`, followed by the four decision definitions verbatim from spec §17.

- [ ] **Step 3: Add `tests/test_validation_docs_m3.py`** (the code from Task 13 Step 3).

- [ ] **Step 4: Run the suite**

```bash
python -m pytest -q
python scripts/check_publication_safety.py --root .
python scripts/check_publication_safety.py --root . --history
```

Expected: all green (the M3 doc test now passes); both scans exit 0.

- [ ] **Step 5: Commit the gate scaffolding**

```bash
git add docs/validation/milestone-3a-checklist.md docs/validation/milestone-3a-result.md tests/test_validation_docs_m3.py
git commit -m "docs: add the Milestone 3a decision-gate checklist and result template"
```

- [ ] **Step 6: Run the manual decision gate**

Follow `docs/validation/milestone-3a-checklist.md` on Windows against a separately installed Raven Framework. Record observations in `milestone-3a-result.md`. Set the single **Final decision** field per spec §17. This step is manual and gated — stop here and hand the result to the user; do not push, merge, or publish.

---

## Self-Review

**Spec coverage (spec §16 Plan 3a tasks 1–14 ↔ this plan):** 1↔T1, 2↔T2, 3↔T3, 4↔T4, 5↔T5, 6↔T6, 7↔T7, 8↔T8, 9↔T9, 10↔T10, 11↔T11, 12↔T12, 13↔T13, 14↔T14. Spec §5 code table → T1 Global Constraints + T5 `test_action_codes_match_the_wire_table`. Spec §6 (`InputSample`, sources) → T8. Spec §7 (gaze) → T6. Spec §8 (fire) → T7. Spec §10 (C patch, `BuildNewTic` invariant, `PULSE_HOLD_TICS`) → T3. Spec §11 (`-warp`) → T10. Spec §12 (lifecycle: release-all, symmetric pause, deadlines, error strings) → T9 + T11. Spec §13 (patch series, `ci_ipc_smoke`, `feature/doomed-prism-m3` trigger) → T4 + T13. Spec §14 (GPL headers, corresponding-source, diff-minimality, placeholder addresses) → T3 + T12 + T14. Spec §17 gate → T14. Spec §18 exit criteria (`ci_ipc_smoke` at its fixed minimum) → T13. No gap.

**Placeholder scan:** every code step carries real code. The one deliberate skeleton is T3's `i_ipc_input.c` (`ipc_connect` / `ipc_handshake` bodies described, not spelled out) — this matches the M2 plan's Task 2 precedent for a C patch verified by manual build rather than pytest, and T3's Interfaces + Steps 4–7 pin the exact call sites, constants, and file set.

**Type consistency:** `Action` codes (1/2/3/4/10/11/20) identical in T1 Global Constraints, T3 `#define`s, T5 `Action` enum + test. `Message.turn(code, value)` / `Message.action(code, value)` take wire ints everywhere (T1, T5, T13). `HeldAction(action, magnitude)` used identically in T5/T6/T9. `InputSample(gaze_xy, activation_edge, pause_edge, debug_fire_edge)` identical in T8/T9. `InputPipeline(source, send, *, surface, spoken_fire)` / `tick(now)` / `release_all()` / `toggle_pause()` / `paused` identical in T9/T11. `IpcServer(*, address_factory, on_disconnect)` / `start()->str` / `poll()` / `send(Message)` / `close()` / `is_connected` / `protocol_mismatch` identical in T2/T11/T13. `DoomProcess.start(*, ipc_address=None)` / `ipc_address` identical in T10/T11.
