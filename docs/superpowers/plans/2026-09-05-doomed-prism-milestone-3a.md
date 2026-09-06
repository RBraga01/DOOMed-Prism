# DOOMed Prism Milestone 3a Implementation Plan — Input core and the IPC boundary

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make DOOM playable through normalized actions carried over a local IPC socket — gaze-zone movement and progressive turn, click / spoken fire fusion, Enter-pause — with Crispy Doom's SDL keyboard no longer the play input.

**Architecture:** A stdlib fixed-8-byte-frame IPC protocol; an `IpcServer` on the PewPew side (AF_UNIX on POSIX, `127.0.0.1` TCP on Windows) that PewPew binds before launching Crispy. A second Crispy Doom patch (`patches/crispy-doom-ipc-input.diff`, applied as a series after the M2 frame-export patch) connects on startup and injects `D_PostEvent` key/mouse events once per built tic. A Python input pipeline (gaze zones → dwell/jitter filter → fire arbiter → action router) ticks from the existing host `QTimer` and drains to the server. `host_widget` owns the server lifecycle and releases all held input on sleep / IPC loss / shutdown.

**Tech Stack:** Python 3.10+, PySide6 (Raven extra), pytest + pytest-qt, `socket`/`struct`/`select` (stdlib), C99 + BSD sockets / winsock + CMake for the engine patch, the pinned `crispy-doom-7.1` tag.

**Spec:** `docs/superpowers/specs/2026-09-05-doomed-prism-milestone-3-design.md` (this plan implements the spec's §16 "Plan 3a"; the decision gate is spec §17, exit criteria spec §18. Executors read both documents.)

## Global Constraints

- **Branch:** `feature/doomed-prism-m3` (already created from `main` @ `389ef4b`; the spec commits are on it). Do not push, merge, or publish without authorization.
- **Publication safety.** Every commit must be safe to publish. Never commit Raven-owned source, commercial IWADs, credentials, generated binaries, screenshots with private data, vendored third-party engine source, or acoustic-model / audio files. The only new tracked engine artifact is `patches/crispy-doom-ipc-input.diff` (original work, GPL-2.0-or-later, with GPL headers matching Crispy on the new `src/i_ipc_input.c` / `.h`). Both `python scripts/check_publication_safety.py --root .` and `--root . --history` must exit 0 before every commit.
- **Tests run without** Crispy Doom, Raven Framework, an IWAD, a C toolchain, or a display, using project-owned fakes. `IpcServer` tests bind a real *in-process* loopback listener (no external process); the `address_factory` seam only selects the platform branch + path.
- **Wire frame (spec §5, R10):** `struct` format `"<BBHi"`, exactly 8 bytes, little-endian: `version: u8`, `type: u8`, `code: u16`, `value: i32`. `IPC_PROTOCOL_VERSION = 1`, `IPC_FRAME_SIZE = 8`. No on-wire magic. Protocol timeouts: `IPC_HANDSHAKE_TIMEOUT_S = 10.0`, `IPC_HELLO_TIMEOUT_S = 2.0` (the C side mirrors the latter as `IPC_HELLO_TIMEOUT_MS 2000`).
- **`MessageType` (spec §5):** `HELLO = 0`, `ACTION = 1`, `PULSE = 2`, `DISCRETE = 3`, `TURN = 4`, `BYE = 6`. Value `5` is reserved (unused in M3). Any other `type` → `IpcProtocolError`.
- **Action `code` table (spec §5) — the C `#define`s and `pewpew.input.actions.Action` MUST both equal this:**
  `MOVE_FORWARD = 1`, `MOVE_BACKWARD = 2`, `TURN_LEFT = 3`, `TURN_RIGHT = 4`, `FIRE = 10`, `USE = 11`, `PAUSE = 20`. Codes `21`–`24` (`MENU_*`) and `40`–`79` (weapons / automap / save / load / exit) are **reserved for Milestone 3b** and are not defined in 3a. Task 13 adds a test that greps the committed `.diff` for the `#define`s and asserts equality with the enums.
- **`value` semantics (spec §5):** `ACTION` → `10000` on hold, `0` on release. `TURN` → unsigned clamped mouse-x magnitude (direction is carried in `code`). `PULSE` / `DISCRETE` / `HELLO` / `BYE` → `0`. All magnitude→wire scaling lives in `ActionRouter`; `pewpew.ipc.protocol` does no scaling and never imports `pewpew.input`.
- **Tunable constants (spec R11) — module-level `UPPER_SNAKE_CASE`, not `RuntimeConfig` fields:**
  `DEAD_ZONE_HALF_W = 180`, `DEAD_ZONE_HALF_H = 150`, `TURN_RESPONSE_EXPONENT = 1.5`, `MAGNITUDE_EMA_ALPHA = 0.4`, `DWELL_S = 0.15`, `JITTER_GRACE_S = 0.02` (all in `pewpew.input.gaze`); `MAGNITUDE_STEPS = 20`, `TURN_MAX_MOUSE_DELTA = 40` (`pewpew.input.actions`); `FIRE_DEBOUNCE_S = 0.12` (`pewpew.input.fire`); `PULSE_HOLD_TICS = 2`, `IPC_TURN_CLAMP = 40` (C, `i_ipc_input.c`).
- **`IpcServer` is the sole owner of the socket path** (bind + unlink). `engine.stop()` never touches it. The client socket is **non-blocking**; `send()` retries a `BlockingIOError` with a bounded (`0.05 s`) `select` wait and treats an exhausted wait / reset as a disconnect. The listening socket's `accept` is non-blocking.
- **No menu-navigation action in 3a.** The gate reaches gameplay via `-warp`: `DoomProcess` appends `-warp <DOOMED_PRISM_WARP> -skill <DOOMED_PRISM_SKILL or 3>` to Crispy's argv only when `DOOMED_PRISM_WARP` is set.
- **The Crispy patch series (spec §13, R4).** `scripts/build_crispy.py` holds `PATCHES = ("patches/crispy-doom-fb-export.diff", "patches/crispy-doom-ipc-input.diff")` and applies it cumulatively on disk: `git -C <dir> reset --hard <lock.commit>` + `git -C <dir> clean -fd -- src/`, then `git -C <dir> apply <p1>`, then `git -C <dir> apply <p2>`, then write `.doomed-prism-applied` **once**. `--check` = same restore + real `git apply <p1>` + `git apply --check <p2>`, no marker. Patch 2 is authored against the patch-1-applied tree and touches **no** patch-1 line.
- **DRY / YAGNI / TDD.** New modules live under `src/pewpew/ipc/` and `src/pewpew/input/` (many small focused files). Fakes live under `tests/fakes/`.

---

## Checkpoint A — transport core (Tasks 1–4)

Tasks 1–4 deliver a tested IPC protocol, a tested `IpcServer`, the Crispy IPC-input patch (manually build-verified), and the multi-patch build script. They are a coherent, independently reviewable unit and a safe place to pause or resume (spec R1). Task 14's CI smoke is what exercises Task 3 at runtime.

---

## Task 1: IPC wire protocol

**Files:**
- Create: `src/pewpew/ipc/__init__.py` (empty)
- Create: `src/pewpew/ipc/protocol.py`
- Create: `tests/test_ipc_protocol.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - Constants: `IPC_PROTOCOL_VERSION = 1`, `IPC_FRAME_SIZE = 8`, `IPC_HANDSHAKE_TIMEOUT_S = 10.0`, `IPC_HELLO_TIMEOUT_S = 2.0`.
  - `class MessageType(enum.IntEnum)`: `HELLO = 0`, `ACTION = 1`, `PULSE = 2`, `DISCRETE = 3`, `TURN = 4`, `BYE = 6`.
  - `class IpcProtocolError(RuntimeError)`.
  - `@dataclass(frozen=True) class Message` with fields `type: MessageType`, `code: int`, `value: int`, and classmethods `hello() -> Message` (`HELLO, IPC_PROTOCOL_VERSION, 0`), `bye() -> Message` (`BYE, 0, 0`), `action(code: int, value: int) -> Message` (`ACTION`), `turn(code: int, value: int) -> Message` (`TURN`), `pulse(code: int) -> Message` (`PULSE, value 0`), `discrete(code: int) -> Message` (`DISCRETE, value 0`).
  - `encode(message: Message) -> bytes` — always exactly 8 bytes.
  - `decode(buffer: bytes) -> tuple[Message | None, bytes]` — consumes one whole frame; `(None, buffer)` when `len(buffer) < 8`; raises `IpcProtocolError` on an out-of-range `version` or an unknown/reserved `type`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ipc_protocol.py`:

```python
"""Tests for the fixed 8-byte IPC wire protocol."""

from __future__ import annotations

import struct

import pytest

from pewpew.ipc.protocol import (
    IPC_FRAME_SIZE,
    IPC_HANDSHAKE_TIMEOUT_S,
    IPC_HELLO_TIMEOUT_S,
    IPC_PROTOCOL_VERSION,
    IpcProtocolError,
    Message,
    MessageType,
    decode,
    encode,
)


def test_protocol_timeout_constants_are_named() -> None:
    assert IPC_HANDSHAKE_TIMEOUT_S == 10.0
    assert IPC_HELLO_TIMEOUT_S == 2.0


def test_every_frame_is_exactly_eight_bytes() -> None:
    for message in (
        Message.hello(), Message.bye(), Message.action(1, 10000),
        Message.turn(3, 40), Message.pulse(10), Message.discrete(20),
    ):
        assert len(encode(message)) == IPC_FRAME_SIZE


def test_encode_is_little_endian_BBHi() -> None:
    raw = encode(Message.turn(code=4, value=-7))
    assert raw == struct.pack("<BBHi", IPC_PROTOCOL_VERSION, MessageType.TURN, 4, -7)


def test_round_trips_every_message_type() -> None:
    for message in (
        Message.hello(), Message.bye(), Message.action(2, 0),
        Message.turn(3, 25), Message.pulse(11), Message.discrete(20),
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
    with pytest.raises(IpcProtocolError):
        decode(struct.pack("<BBHi", IPC_PROTOCOL_VERSION, 99, 0, 0))


def test_decode_rejects_the_reserved_type_five() -> None:
    with pytest.raises(IpcProtocolError):
        decode(struct.pack("<BBHi", IPC_PROTOCOL_VERSION, 5, 0, 0))


def test_decode_rejects_a_version_mismatch() -> None:
    with pytest.raises(IpcProtocolError):
        decode(struct.pack("<BBHi", IPC_PROTOCOL_VERSION + 1, MessageType.HELLO, 1, 0))


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
IPC_HANDSHAKE_TIMEOUT_S = 10.0
IPC_HELLO_TIMEOUT_S = 2.0

_FRAME = struct.Struct("<BBHi")  # version:u8, type:u8, code:u16, value:i32


class MessageType(enum.IntEnum):
    HELLO = 0
    ACTION = 1
    PULSE = 2
    DISCRETE = 3
    TURN = 4
    BYE = 6


class IpcProtocolError(RuntimeError):
    """Raised on a version mismatch or an unknown/reserved message type."""


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
  - `AddressFactory = Callable[[], tuple[socket.socket, str]]` — returns a **bound, listening, non-blocking** socket and its address string. Default: POSIX → `AF_UNIX` at `${XDG_RUNTIME_DIR or /tmp}/doomed-prism-ipc-<pid>-<token>.sock` (raises `OSError` if `len(path) >= 104`; `unlink`s a stale path first); Windows → `AF_INET` `("127.0.0.1", 0)`, address `"127.0.0.1:<port>"`.
  - `class IpcServer`:
    - `__init__(self, *, address_factory: AddressFactory | None = None, on_disconnect: Callable[[], None] | None = None) -> None`
    - `on_disconnect: Callable[[], None]` — public settable attribute (also set from the ctor); called at most once when the client leaves.
    - `start(self) -> str`
    - `poll(self) -> None` — non-blocking. Accept a pending client (a 2nd connection is accepted then immediately closed). While not connected, read up to 8 handshake bytes and check them raw (`buf[0] == IPC_PROTOCOL_VERSION and buf[1] == MessageType.HELLO`) → `is_connected = True`; a raw-byte mismatch → `protocol_mismatch = True` and close the client. While connected, a zero-length `recv` / reset → `is_connected = False` + `on_disconnect()` once.
    - `send(self, message: Message) -> None` — no-op unless connected; else write all 8 bytes non-blocking, retrying a `BlockingIOError` with `select.select([], [sock], [], 0.05)`; an exhausted wait or a `BrokenPipeError` / `ConnectionResetError` / `OSError` → disconnect.
    - `close(self) -> None` — `send(Message.bye())` if connected, close client + listening sockets, `unlink` the POSIX path. Idempotent.
    - `is_connected: bool` property; `protocol_mismatch: bool` property.
  - `tests/fakes/fake_ipc.py`: `class FakeIpcClient` (the child side). `__init__(self, address: str)` connects in-process. `send_hello(self, version: int = IPC_PROTOCOL_VERSION) -> None`. `recv_message(self, timeout: float = 1.0) -> Message`. `close(self) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/fakes/fake_ipc.py`:

```python
"""In-process stand-in for the Crispy Doom IPC client (the child side)."""

from __future__ import annotations

import socket
import struct

from pewpew.ipc.protocol import (
    IPC_FRAME_SIZE,
    IPC_PROTOCOL_VERSION,
    Message,
    MessageType,
    decode,
)


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
        # Hand-pack so a mismatched version is still a valid 8-byte frame on the wire.
        self._sock.sendall(struct.pack("<BBHi", version, MessageType.HELLO, version, 0))

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
    listener.listen(2)
    listener.setblocking(False)
    return listener, f"127.0.0.1:{listener.getsockname()[1]}"


def _connect(server: IpcServer):
    """Return a handshaken FakeIpcClient."""
    address = server.start()
    client = FakeIpcClient(address)
    for _ in range(20):
        server.poll()
        if server.is_connected:
            break
        try:
            client.recv_message(timeout=0.05)  # drain the server HELLO
        except Exception:
            pass
        client.send_hello(IPC_PROTOCOL_VERSION)
    return client


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
    client = _connect(server)
    assert server.is_connected is True
    assert server.protocol_mismatch is False
    client.close()


def test_handshake_rejects_a_version_mismatch(server: IpcServer) -> None:
    address = server.start()
    client = FakeIpcClient(address)
    client.send_hello(IPC_PROTOCOL_VERSION + 1)
    for _ in range(20):
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
    client = _connect(server)
    server.send(Message.action(1, 10000))
    assert client.recv_message() == Message.action(1, 10000)
    client.close()


def test_client_close_fires_on_disconnect_exactly_once() -> None:
    calls: list[int] = []
    srv = IpcServer(
        address_factory=_loopback_factory, on_disconnect=lambda: calls.append(1)
    )
    try:
        client = _connect(srv)
        client.close()
        for _ in range(20):
            srv.poll()
        assert calls == [1]
        assert srv.is_connected is False
    finally:
        srv.close()


def test_a_second_connection_is_accepted_then_closed_without_disturbing_the_first(
    server: IpcServer,
) -> None:
    first = _connect(server)
    second = FakeIpcClient(server.start.__self__._address if False else _current_addr(server))
    for _ in range(10):
        server.poll()
    assert server.is_connected is True  # first client still connected
    server.send(Message.pulse(10))
    assert first.recv_message() == Message.pulse(10)
    first.close()
    second.close()


def _current_addr(server: IpcServer) -> str:
    # the fixture-created server was already start()ed by _connect
    return server._address  # test-only introspection of the bound address


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

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/test_ipc_server.py -q`
Expected: FAIL — `pewpew.ipc.server` does not exist.

- [ ] **Step 3: Implement `src/pewpew/ipc/server.py`**

```python
"""PewPew-side IPC server: bind before launch, stream actions, detect the child leaving."""

from __future__ import annotations

import os
import secrets
import select
import socket
import sys
from collections.abc import Callable

from pewpew.ipc.protocol import (
    IPC_FRAME_SIZE,
    IPC_PROTOCOL_VERSION,
    Message,
    MessageType,
    encode,
)

AddressFactory = Callable[[], "tuple[socket.socket, str]"]
_SUN_PATH_LIMIT = 104
_SEND_WAIT_S = 0.05


def _default_factory() -> "tuple[socket.socket, str]":
    token = secrets.token_hex(4)
    if sys.platform == "win32":
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
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
    listener.listen(2)
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
        self.on_disconnect: Callable[[], None] = on_disconnect or (lambda: None)
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
        self._accept_pending()
        if self._client is None:
            return
        if not self._is_connected:
            self._drive_handshake()
        else:
            self._check_alive()

    def _accept_pending(self) -> None:
        try:
            extra, _ = self._listener.accept()
        except (BlockingIOError, InterruptedError, OSError):
            return
        extra.setblocking(False)
        if self._client is not None:
            extra.close()  # spec §6: a 2nd connection is accepted then dropped
            return
        self._client = extra
        try:
            self._raw_send(encode(Message.hello()))
        except OSError:
            self._drop()

    def _drive_handshake(self) -> None:
        assert self._client is not None
        try:
            chunk = self._client.recv(IPC_FRAME_SIZE - len(self._hello_buffer))
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._drop()
            return
        if not chunk:
            self._drop()
            return
        self._hello_buffer += chunk
        if len(self._hello_buffer) < IPC_FRAME_SIZE:
            return
        version, msg_type = self._hello_buffer[0], self._hello_buffer[1]
        self._hello_buffer = self._hello_buffer[IPC_FRAME_SIZE:]
        if version != IPC_PROTOCOL_VERSION or msg_type != int(MessageType.HELLO):
            self._protocol_mismatch = True
            self._close_client()
            return
        self._is_connected = True

    def _check_alive(self) -> None:
        assert self._client is not None
        try:
            chunk = self._client.recv(64)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._drop()
            return
        if not chunk:
            self._drop()

    def send(self, message: Message) -> None:
        if not self._is_connected or self._client is None:
            return
        try:
            self._raw_send(encode(message))
        except OSError:
            self._drop()

    def _raw_send(self, data: bytes) -> None:
        assert self._client is not None
        view = memoryview(data)
        sent = 0
        while sent < len(view):
            try:
                sent += self._client.send(view[sent:])
            except BlockingIOError:
                _, writable, _ = select.select([], [self._client], [], _SEND_WAIT_S)
                if not writable:
                    raise OSError("IPC send stalled")

    def close(self) -> None:
        if self._is_connected and self._client is not None:
            try:
                self._raw_send(encode(Message.bye()))
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
            self.on_disconnect()
```

- [ ] **Step 4: Run tests and the suite**

```bash
python -m pytest tests/test_ipc_server.py -q
python -m pytest -q
```

Expected: PASS. (`_current_addr` in the 2nd-client test reads `server._address` — test-only introspection; acceptable for a same-package white-box test.)

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/ipc/server.py tests/fakes/fake_ipc.py tests/test_ipc_server.py
git commit -m "feat: add the PewPew-side IPC server"
```

---

## Task 3: Crispy Doom IPC-input patch (patch 2 of the series)

Produces one tracked artifact — `patches/crispy-doom-ipc-input.diff` — plus a manual integration check. Needs a local C toolchain, SDL2/SDL2_mixer/SDL2_net dev libraries, CMake, and Git for Windows (not MSYS2 git — see the M2 README hazard). No pytest coverage; runtime verification is Task 14's CI smoke and the §17 gate.

**Files:**
- Create: `patches/crispy-doom-ipc-input.diff`
- Working tree only (not committed): `build/crispy/` with both patches applied.

**Interfaces:**
- Consumes: the Task 1 wire constants (frame layout, `MessageType` values, the action `code` table from Global Constraints) — replicated as C `#define`s.
- Produces: the patch adds `src/i_ipc_input.c` / `.h` and modifies `src/d_loop.c`, `src/i_video.c`, `src/CMakeLists.txt`. Public C API:
  - `void IPC_Input_Init(void);` — reads `DOOMED_PRISM_IPC_ADDR`; unset/empty → all functions no-op. Blocking `connect()`, then non-blocking; sends `HELLO`; spin-reads the server `HELLO` for ≤ `IPC_HELLO_TIMEOUT_MS` (2000); on timeout or a raw version/type mismatch, closes the socket and disables.
  - `void IPC_Input_Pump(void);` — non-blocking `recv` into an 8-byte staging buffer; per full frame, `D_PostEvent` per the mapping; decrements the `PULSE_HOLD_TICS` release scheduler; on EOF/error runs release-all and closes.
  - `void IPC_Input_Shutdown(void);` — release-all, close the socket, `WSACleanup` on Windows. Idempotent. Does **not** unlink (the server owns the path).

- [ ] **Step 1: Restore the checkout and apply patch 1**

```bash
COMMIT=$(python - <<'PY'
import tomllib, pathlib
print(tomllib.loads(pathlib.Path("crispy-doom.lock").read_text())["commit"])
PY
)
# clone if needed
test -d build/crispy/.git || git clone --branch crispy-doom-7.1 https://github.com/fabiangreffrath/crispy-doom build/crispy
git -C build/crispy reset --hard "$COMMIT"
git -C build/crispy clean -fd -- src/
git -C build/crispy apply "$(pwd)/patches/crispy-doom-fb-export.diff"
```

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

`key_up` / `key_down` / `key_fire` / `key_use` / `key_pause` are declared in `src/m_controls.h` in `crispy-doom-7.1`. `event_t` / `evtype_t` / `ev_keydown` / `ev_keyup` / `ev_mouse` and `D_PostEvent` are in `src/d_event.h`. Confirm both `#include` paths against the tag before generating the diff.

```c
//
// Copyright(C) 2026 DOOMed Prism contributors
// GPL-2.0-or-later — see i_ipc_input.h.
//

#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "d_event.h"
#include "i_ipc_input.h"
#include "m_controls.h"

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
typedef SOCKET ipc_sock_t;
#define IPC_INVALID INVALID_SOCKET
#define IPC_WOULDBLOCK (WSAGetLastError() == WSAEWOULDBLOCK)
#else
#include <arpa/inet.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
typedef int ipc_sock_t;
#define IPC_INVALID (-1)
#define IPC_WOULDBLOCK (errno == EWOULDBLOCK || errno == EAGAIN)
#endif

#define IPC_FRAME_SIZE 8
#define IPC_PROTOCOL_VERSION 1
#define IPC_HELLO_TIMEOUT_MS 2000
#define PULSE_HOLD_TICS 2
#define IPC_TURN_CLAMP 40

#define MT_HELLO 0
#define MT_ACTION 1
#define MT_PULSE 2
#define MT_DISCRETE 3
#define MT_TURN 4
#define MT_BYE 6

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

enum { H_FWD, H_BACK, H_COUNT };
static int held[H_COUNT];
static int held_key[H_COUNT];

static int pulse_key[4];
static int pulse_tics[4];

static void ipc_close_sock(void)
{
    if (ipc_sock != IPC_INVALID)
    {
#ifdef _WIN32
        closesocket(ipc_sock);
#else
        close(ipc_sock);
#endif
        ipc_sock = IPC_INVALID;
    }
}

static void ipc_set_nonblocking(void)
{
#ifdef _WIN32
    u_long nb = 1;
    ioctlsocket(ipc_sock, FIONBIO, &nb);
#else
    int fl = fcntl(ipc_sock, F_GETFL, 0);
    fcntl(ipc_sock, F_SETFL, fl | O_NONBLOCK);
#endif
}

static void ipc_post_key(evtype_t t, int key)
{
    event_t ev;
    memset(&ev, 0, sizeof(ev));
    ev.type = t;
    ev.data1 = key;
    ev.data2 = -1;
    ev.data3 = -1;
    D_PostEvent(&ev);
}

static void ipc_post_mouse_x(int dx)
{
    event_t ev;
    memset(&ev, 0, sizeof(ev));
    ev.type = ev_mouse;
    ev.data1 = 0;      /* mouse-button bitmap; 0 is safe with the SDL window unfocused */
    ev.data2 = dx;
    ev.data3 = 0;
    D_PostEvent(&ev);
}

static void ipc_release_all(void)
{
    int i;
    for (i = 0; i < H_COUNT; i++)
        if (held[i]) { ipc_post_key(ev_keyup, held_key[i]); held[i] = 0; }
    for (i = 0; i < 4; i++)
        if (pulse_tics[i] > 0) { ipc_post_key(ev_keyup, pulse_key[i]); pulse_tics[i] = 0; }
    ipc_post_key(ev_keyup, key_fire);
    ipc_post_key(ev_keyup, key_use);
}

static void ipc_disable(void)
{
    if (ipc_enabled || ipc_sock != IPC_INVALID)
        ipc_release_all();
    ipc_close_sock();
    ipc_enabled = 0;
}

static int ipc_connect(const char *addr)
{
    if (strncmp(addr, "127.0.0.1:", 10) == 0)
    {
        struct sockaddr_in sin;
        memset(&sin, 0, sizeof(sin));
        sin.sin_family = AF_INET;
        sin.sin_port = htons((unsigned short) atoi(addr + 10));
        sin.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        ipc_sock = socket(AF_INET, SOCK_STREAM, 0);
        if (ipc_sock == IPC_INVALID) return -1;
        if (connect(ipc_sock, (struct sockaddr *) &sin, sizeof(sin)) != 0)
        { ipc_close_sock(); return -1; }
    }
    else
    {
#ifdef _WIN32
        return -1;  /* AF_UNIX addresses are POSIX-only */
#else
        struct sockaddr_un sun;
        memset(&sun, 0, sizeof(sun));
        sun.sun_family = AF_UNIX;
        if (strlen(addr) >= sizeof(sun.sun_path)) return -1;
        strncpy(sun.sun_path, addr, sizeof(sun.sun_path) - 1);
        ipc_sock = socket(AF_UNIX, SOCK_STREAM, 0);
        if (ipc_sock == IPC_INVALID) return -1;
        if (connect(ipc_sock, (struct sockaddr *) &sun, sizeof(sun)) != 0)
        { ipc_close_sock(); return -1; }
#endif
    }
    ipc_set_nonblocking();
    return 0;
}

static void ipc_sleep_10ms(void)
{
#ifdef _WIN32
    Sleep(10);
#else
    struct timespec ts = { 0, 10 * 1000 * 1000 };
    nanosleep(&ts, NULL);
#endif
}

static void ipc_handshake(void)
{
    unsigned char out[IPC_FRAME_SIZE], in[IPC_FRAME_SIZE];
    int have = 0, waited = 0, n;

    memset(out, 0, sizeof(out));
    out[0] = IPC_PROTOCOL_VERSION;
    out[1] = MT_HELLO;
    out[2] = IPC_PROTOCOL_VERSION & 0xFF;
    out[3] = (IPC_PROTOCOL_VERSION >> 8) & 0xFF;
    if (send(ipc_sock, (const char *) out, IPC_FRAME_SIZE, 0) != IPC_FRAME_SIZE)
    { ipc_disable(); return; }

    while (have < IPC_FRAME_SIZE && waited < IPC_HELLO_TIMEOUT_MS)
    {
        n = (int) recv(ipc_sock, (char *) in + have, IPC_FRAME_SIZE - have, 0);
        if (n > 0) { have += n; continue; }
        if (n == 0) { ipc_disable(); return; }
        if (!IPC_WOULDBLOCK) { ipc_disable(); return; }
        ipc_sleep_10ms();
        waited += 10;
    }
    if (have < IPC_FRAME_SIZE || in[0] != IPC_PROTOCOL_VERSION || in[1] != MT_HELLO)
    { ipc_disable(); return; }
    ipc_enabled = 1;
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
    int slot, i, key, d;
    switch (type)
    {
        case MT_ACTION:
            slot = (code == AC_MOVE_FORWARD) ? H_FWD
                 : (code == AC_MOVE_BACKWARD) ? H_BACK : -1;
            if (slot < 0) break;
            if (value != 0 && !held[slot])
            { ipc_post_key(ev_keydown, held_key[slot]); held[slot] = 1; }
            else if (value == 0 && held[slot])
            { ipc_post_key(ev_keyup, held_key[slot]); held[slot] = 0; }
            break;
        case MT_TURN:
            d = value;
            if (d > IPC_TURN_CLAMP) d = IPC_TURN_CLAMP;
            if (d < 0) d = 0;
            if (d != 0) ipc_post_mouse_x(code == AC_TURN_LEFT ? -d : d);
            break;
        case MT_PULSE:
            key = (code == AC_FIRE) ? key_fire : (code == AC_USE) ? key_use : -1;
            if (key < 0) break;
            ipc_post_key(ev_keydown, key);
            for (i = 0; i < 4; i++)
                if (pulse_tics[i] == 0)
                { pulse_key[i] = key; pulse_tics[i] = PULSE_HOLD_TICS; break; }
            break;
        case MT_DISCRETE:
            if (code == AC_PAUSE)
            { ipc_post_key(ev_keydown, key_pause); ipc_post_key(ev_keyup, key_pause); }
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
        n = (int) recv(ipc_sock, (char *) ipc_buf + ipc_have,
                       IPC_FRAME_SIZE - ipc_have, 0);
        if (n == 0) { ipc_disable(); return; }
        if (n < 0)
        {
            if (IPC_WOULDBLOCK) break;
            ipc_disable();
            return;
        }
        ipc_have += n;
        if (ipc_have < IPC_FRAME_SIZE) continue;
        ipc_have = 0;
        {
            uint8_t version = ipc_buf[0], type = ipc_buf[1];
            uint16_t code = (uint16_t) (ipc_buf[2] | (ipc_buf[3] << 8));
            int32_t value = (int32_t) ((uint32_t) ipc_buf[4]
                          | ((uint32_t) ipc_buf[5] << 8)
                          | ((uint32_t) ipc_buf[6] << 16)
                          | ((uint32_t) ipc_buf[7] << 24));
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

- [ ] **Step 4: Wire the call sites in the checkout**

- `src/i_video.c`, `I_InitGraphics`: `#include "i_ipc_input.h"` in the include block; `IPC_Input_Init();` on the line immediately **after** patch 1's `FB_Export_Init();` (a distinct added line — not an edit of patch 1's line).
- `src/i_video.c`, `I_ShutdownGraphics`: `IPC_Input_Shutdown();` immediately before patch 1's `FB_Export_Shutdown();`.
- `src/d_loop.c`: `#include "i_ipc_input.h"` near the top; add a single `IPC_Input_Pump();` call so that **the binding invariant (spec §10) holds: exactly one pump per built game tic, after SDL events are drained (`loop_interface->ProcessEvents()` / `I_StartTic`) and before `G_BuildTiccmd` runs for that tic.** In `crispy-doom-7.1`'s Chocolate-derived `d_loop.c`, `ProcessEvents()` is called from `NetUpdate()`, and `BuildNewTic()` (which calls `loop_interface->BuildTiccmd`) runs in the tic-build loop after it — so the pump goes at the top of `BuildNewTic()` (once per tic actually built), *not* in `NetUpdate()` (which can build zero or several tics per call). Confirm the exact function + line against the tag and record it in the `i_ipc_input.c` header comment (M2 §0 precedent). Any hook that breaks the once-per-built-tic invariant is a design change, not an implementation detail.
- `src/CMakeLists.txt`: add `i_ipc_input.c        i_ipc_input.h` to `GAME_SOURCE_FILES` on a line **not adjacent** to patch 1's `i_framebuffer_export.*` line (e.g. next to `i_input.c`). Add a **separate** `if(WIN32)\n    list(APPEND EXTRA_LIBS ws2_32)\nendif()` block that does not touch patch 1's `winmm shlwapi` line.

- [ ] **Step 5: Build the doubly-patched engine**

```bash
cmake -S build/crispy -B build/crispy/build -DCMAKE_BUILD_TYPE=Release
cmake --build build/crispy/build
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
exe = "build/crispy/build/src/crispy-doom"  # or .exe on Windows
proc = subprocess.Popen([exe, "-iwad", sys.argv[1], "-window", "-width", "640",
                         "-height", "480", "-warp", "1", "1", "-skill", "3"], env=env)
reader = FrameReader(fb)
for _ in range(400):
    srv.poll()
    if srv.is_connected:
        break
    time.sleep(0.05)
assert srv.is_connected, "engine never completed the IPC handshake"
while not reader.try_open():
    time.sleep(0.05)
before = reader.latest().counter
for _ in range(60):
    srv.send(Message.turn(4, 30)); srv.poll(); time.sleep(1 / 35)
srv.send(Message.pulse(10))
time.sleep(0.5)
assert reader.latest().counter > before, "frame_counter did not advance under IPC input"
srv.close(); proc.terminate()
print("OK: engine connected, handshook, stayed live under IPC input")
```

Run with a lawful IWAD. Visually confirm in the Crispy window that `TURN_RIGHT` rotates the view and the `PULSE` fires. Close the engine; confirm no leftover socket file (POSIX).

- [ ] **Step 7: Generate the patch**

```bash
cd build/crispy
git add -A src/
git diff --cached src/ > ../../patches/crispy-doom-ipc-input.diff
git reset
cd ../..
git apply --stat patches/crispy-doom-ipc-input.diff   # record; net added lines well under ~400
python scripts/build_crispy.py --check                 # Task 4's multi-patch --check
```

The diff must be a single unified diff, `a/`/`b/` prefixes rooted at the checkout, containing only: new `src/i_ipc_input.c` / `.h`, and small hunks in `src/d_loop.c`, `src/i_video.c`, `src/CMakeLists.txt`.

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
- Consumes: `crispy-doom.lock` (`commit`), both patch files.
- Produces:
  - `PATCHES: tuple[Path, ...] = (_ROOT / "patches" / "crispy-doom-fb-export.diff", _ROOT / "patches" / "crispy-doom-ipc-input.diff")`.
  - `plan_commands(lock, *, build_dir, patches=PATCHES, check_only) -> list[list[str]]`:
    - **`check_only`:** optional `git clone`, then `git -C <build_dir> reset --hard <lock.commit>`, `git -C <build_dir> clean -fd -- src/`, `git -C <build_dir> apply <p1>` (real), then `git -C <build_dir> apply --check <p>` for every `p` after the first. No `cmake`.
    - **Real build, marker absent:** optional `git clone`, `reset --hard`, `clean -fd -- src/`, `git -C <build_dir> apply <p>` for every patch in order, then `cmake` configure + `cmake --build`.
    - **Real build, marker present:** optional `git clone` only (normally none), then straight to `cmake` configure + `cmake --build` — no `reset`/`clean`/`apply` (preserves `test_run_skips_git_apply_when_marker_present`).
  - `run(..., _patches=None)` writes the `.doomed-prism-applied` marker exactly once, only after the last non-`--check` `git apply` command succeeds.

- [ ] **Step 1: Update the failing tests**

Add to `tests/test_build_crispy.py`:

```python
def test_plan_commands_restores_then_applies_every_patch_in_order(tmp_path: Path) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    build_dir = tmp_path / "build" / "crispy"
    (build_dir / ".git").mkdir(parents=True)
    patches = (tmp_path / "p1.diff", tmp_path / "p2.diff")

    commands = build_crispy.plan_commands(
        lock, build_dir=build_dir, patches=patches, check_only=False
    )
    joined = [" ".join(c) for c in commands]

    assert joined[0] == f"git -C {build_dir} reset --hard {lock.commit}"
    assert joined[1] == f"git -C {build_dir} clean -fd -- src/"
    applies = [c for c in joined if " apply " in c]
    assert applies[0].endswith(f"apply {patches[0]}")
    assert applies[1].endswith(f"apply {patches[1]}")
    assert "--check" not in " ".join(applies)
    assert any("cmake" in c and "--build" in c for c in joined)


def test_plan_commands_check_only_applies_p1_for_real_then_checks_the_rest(
    tmp_path: Path,
) -> None:
    lock = build_crispy.load_lock(_write_lock(tmp_path))
    build_dir = tmp_path / "b"
    (build_dir / ".git").mkdir(parents=True)
    patches = (tmp_path / "p1.diff", tmp_path / "p2.diff")
    joined = [
        " ".join(c)
        for c in build_crispy.plan_commands(
            lock, build_dir=build_dir, patches=patches, check_only=True
        )
    ]
    assert any(c.endswith(f"apply {patches[0]}") and "--check" not in c for c in joined)
    assert any(c.endswith(f"apply --check {patches[1]}") for c in joined)
    assert not any("cmake" in c for c in joined)


def test_run_writes_the_marker_only_after_the_last_patch_applies(tmp_path: Path) -> None:
    build_dir = tmp_path / "build" / "crispy"
    (build_dir / ".git").mkdir(parents=True)
    p1, p2 = tmp_path / "p1.diff", tmp_path / "p2.diff"
    calls: list[list[str]] = []

    # _make_runner already answers `git rev-parse HEAD`; fail only the real `apply p2`.
    exit_code = build_crispy.run(
        [],
        runner=_make_runner(calls, head=_COMMIT, fail_cmd_substr=f"apply {p2}"),
        fetch=_fake_fetch(),
        _build_dir=build_dir,
        _lock_path=_write_lock(tmp_path),
        _patches=(p1, p2),
    )
    assert exit_code == 1
    assert not (build_dir / build_crispy._MARKER).exists()


def test_run_writes_the_marker_once_when_the_series_applies(tmp_path: Path) -> None:
    build_dir = tmp_path / "build" / "crispy"
    (build_dir / ".git").mkdir(parents=True)
    p1, p2 = tmp_path / "p1.diff", tmp_path / "p2.diff"
    calls: list[list[str]] = []

    exit_code = build_crispy.run(
        [],
        runner=_make_runner(calls, head=_COMMIT),
        fetch=_fake_fetch(),
        _build_dir=build_dir,
        _lock_path=_write_lock(tmp_path),
        _patches=(p1, p2),
    )
    assert exit_code == 0
    assert (build_dir / build_crispy._MARKER).read_text(encoding="utf-8") == "1"
    joined = [" ".join(c) for c in calls]
    assert any(c.endswith("reset --hard " + _COMMIT) for c in joined)
    assert any(c.endswith("clean -fd -- src/") for c in joined)
```

**Rename every existing use of the old single-patch seam.** In `tests/test_build_crispy.py`,
`plan_commands(..., patch=X, ...)` → `plan_commands(..., patches=(X, tmp_path / "p2.diff"), ...)`
and `run(..., _patch=tmp_path / "p.diff", ...)` → `run(..., _patches=(tmp_path / "p1.diff", tmp_path / "p2.diff"), ...)`
in all of: `test_plan_commands_clones_pinned_tag_applies_patch_then_builds`,
`test_plan_commands_check_only_stops_after_git_apply_check`,
`test_run_skips_git_apply_when_marker_present`, `test_clean_removes_the_build_directory`,
`test_run_happy_path_verifies_commit_then_applies_and_builds`,
`test_run_aborts_on_commit_mismatch_before_apply_or_cmake`,
`test_check_verifies_commit_before_git_apply_check`,
`test_run_happy_path_downloads_and_verifies_tarball`, `test_run_aborts_on_tarball_mismatch`,
`test_offline_skips_tarball_download_but_still_verifies_commit`,
`test_offline_still_aborts_on_commit_mismatch`. Their loose `any("apply" in c ...)` /
`any("clone" ...)` / `not any("cmake" ...)` assertions all still hold under the two-patch shape;
`test_plan_commands_check_only_stops_after_git_apply_check` still passes because a 2-tuple still
emits an `apply --check <p2>` command.

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/test_build_crispy.py -q`
Expected: FAIL — `PATCHES` / `patches=` / `_patches=` / the `reset --hard` prefix are absent.

- [ ] **Step 3: Update `scripts/build_crispy.py`**

- Add near `_DEFAULT_LOCK`:

```python
PATCHES = (
    _ROOT / "patches" / "crispy-doom-fb-export.diff",
    _ROOT / "patches" / "crispy-doom-ipc-input.diff",
)
```

- Rewrite `plan_commands`:

```python
def plan_commands(lock, *, build_dir, patches=PATCHES, check_only):
    git = ["git", "-C", str(build_dir)]
    commands: list[list[str]] = []
    if not (build_dir / ".git").exists():
        commands.append(
            ["git", "clone", "--branch", lock.tag, lock.repo, str(build_dir)]
        )
    if check_only:
        commands.append(git + ["reset", "--hard", lock.commit])
        commands.append(git + ["clean", "-fd", "--", "src/"])
        commands.append(git + ["apply", str(patches[0])])
        for patch in patches[1:]:
            commands.append(git + ["apply", "--check", str(patch)])
        return commands
    if not (build_dir / _MARKER).exists():
        commands.append(git + ["reset", "--hard", lock.commit])
        commands.append(git + ["clean", "-fd", "--", "src/"])
        for patch in patches:
            commands.append(git + ["apply", str(patch)])
    commands.append(
        ["cmake", "-S", str(build_dir), "-B", str(build_dir / "build"),
         "-DCMAKE_BUILD_TYPE=Release"]
    )
    commands.append(["cmake", "--build", str(build_dir / "build")])
    return commands
```

- In `run`: replace the `_patch: Path | None = None` parameter with `_patches: tuple[Path, ...] | None = None`. Bind `patches = _patches or PATCHES` and pass `patches=patches` into `plan_commands`. Bind `git = ["git", "-C", str(build_dir)]` and `last_apply = git + ["apply", str(patches[-1])]`. In the `pending` execution loop, replace the old per-`apply` marker write (the `if command[:4] == ["git", "-C", str(build_dir), "apply"] and "--check" not in command:` block) with:

```python
    for command in pending:
        result = runner(command, cwd=str(_ROOT))
        if getattr(result, "returncode", 0) != 0:
            print(f"command failed: {' '.join(command)}", file=sys.stderr)
            return 1
        if not args.check and command == last_apply:
            build_dir.mkdir(parents=True, exist_ok=True)
            (build_dir / _MARKER).write_text("1", encoding="utf-8")
```

- Keep `verify_commit` and `verify_tarball` unchanged — they still run between the optional clone and the `pending` loop; `reset --hard <lock.commit>` keeps HEAD at the pinned commit so `verify_commit` still passes. Delete the now-unused `_DEFAULT_PATCH` constant (nothing references it).

- [ ] **Step 4: Run tests and the suite**

```bash
python -m pytest tests/test_build_crispy.py -q
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Real end-to-end check (opt-in)**

```bash
python scripts/build_crispy.py --check
python scripts/build_crispy.py
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
  - `@dataclass(frozen=True) class HeldAction`: `action: Action`, `magnitude: float`.
  - `class ActionRouter`:
    - `__init__(self, sink: Callable[[Message], None]) -> None`
    - `set_held(self, held: frozenset[HeldAction]) -> None` — diffs against the previous held set; new/released `MOVE_*` → `Message.action(code, 10000 | 0)`; `TURN_*` → `Message.turn(code, _turn_value(magnitude))` whenever the quantised step (quantum `1/MAGNITUDE_STEPS`) changes or the action just became held (release → `Message.turn(code, 0)`).
    - `pulse(self, action: Action) -> None`; `discrete(self, action: Action) -> None`.
    - `release_all(self) -> None` — a `0`-value frame for every currently held action (stable order by int code), then clears; nothing for already-released actions.

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
    # round(0.99 * 20) == 20 — same bin as 1.0, so no new frame
    router.set_held(frozenset({HeldAction(Action.TURN_RIGHT, 0.99)}))
    router.set_held(frozenset({HeldAction(Action.TURN_RIGHT, 0.5)}))   # bin 10
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

- [ ] **Step 2: Run and confirm failure** — `python -m pytest tests/test_input_actions.py -q` — FAIL (module missing).

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
        self._held: dict[Action, int] = {}  # action -> last emitted quantum (MOVE uses 1)

    def set_held(self, held: frozenset[HeldAction]) -> None:
        incoming = {h.action: h.magnitude for h in held}
        for action in sorted(self._held):
            if action not in incoming:
                self._emit_zero(action)
                del self._held[action]
        for action in sorted(incoming):
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
        for action in sorted(self._held):
            self._emit_zero(action)
        self._held.clear()

    def _emit_zero(self, action: Action) -> None:
        if action in _MOVE:
            self._sink(Message.action(int(action), 0))
        else:
            self._sink(Message.turn(int(action), 0))
```

- [ ] **Step 4: Run tests and the suite** — green.

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
  - `class GazeZoneMap(surface_w, surface_h, *, dead_zone=(DEAD_ZONE_HALF_W, DEAD_ZONE_HALF_H), turn_exponent=TURN_RESPONSE_EXPONENT)`; `resolve(x, y) -> frozenset[HeldAction]` — dead zone (`|dx|<=hw and |dy|<=hh`) → empty; turn band (`|dx|>hw and |dy|<=hh`) → `{HeldAction(TURN_*, m)}` with `m = clamp((|dx|-hw)/(cx-hw), 0, 1) ** turn_exponent`; forward/back band (`|dy|>hh and |dx|<=hw`) → `{HeldAction(MOVE_*, 1.0)}`; corner (`|dx|>hw and |dy|>hh`) → union of `MOVE_*` (1.0) and `TURN_*` (raw float).
  - `class GazeFilter(*, dwell_s=DWELL_S, grace_s=JITTER_GRACE_S, ema_alpha=MAGNITUDE_EMA_ALPHA)`; `update(raw, now) -> frozenset[HeldAction]`; `reset()`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for gaze-zone resolution and the dwell / jitter filter."""

from __future__ import annotations

from pewpew.input.actions import Action, HeldAction
from pewpew.input.gaze import GazeFilter, GazeZoneMap


def _map() -> GazeZoneMap:
    return GazeZoneMap(640, 640)  # centre (320, 320); hw=180, hh=150


def _actions(s: frozenset[HeldAction]) -> set[Action]:
    return {h.action for h in s}


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
    assert _actions(gmap.resolve(320, 320 - 200)) == {Action.MOVE_FORWARD}
    assert _actions(gmap.resolve(320, 320 + 200)) == {Action.MOVE_BACKWARD}


def test_upper_right_corner_is_forward_plus_right_turn() -> None:
    assert _actions(_map().resolve(320 + 200, 320 - 200)) == {
        Action.MOVE_FORWARD,
        Action.TURN_RIGHT,
    }


def test_filter_requires_dwell_before_emitting() -> None:
    f = GazeFilter(dwell_s=0.15, grace_s=0.02)
    raw = frozenset({HeldAction(Action.TURN_LEFT, 1.0)})
    assert f.update(raw, now=0.0) == frozenset()
    assert f.update(raw, now=0.10) == frozenset()
    assert _actions(f.update(raw, now=0.16)) == {Action.TURN_LEFT}


def test_filter_rides_out_a_one_sample_dropout_but_releases_after_grace() -> None:
    f = GazeFilter(dwell_s=0.15, grace_s=0.02)
    raw = frozenset({HeldAction(Action.MOVE_FORWARD, 1.0)})
    f.update(raw, now=0.0)
    f.update(raw, now=0.20)  # now held
    assert _actions(f.update(frozenset(), now=0.205)) == {Action.MOVE_FORWARD}
    assert f.update(frozenset(), now=0.25) == frozenset()


def test_a_brief_dropout_and_return_does_not_re_require_full_dwell() -> None:
    f = GazeFilter(dwell_s=0.15, grace_s=0.05)
    raw = frozenset({HeldAction(Action.TURN_LEFT, 1.0)})
    f.update(raw, now=0.0)
    f.update(raw, now=0.20)          # held
    f.update(frozenset(), now=0.22)  # 20 ms dropout, within grace
    assert _actions(f.update(raw, now=0.24)) == {Action.TURN_LEFT}  # still held


def test_region_change_releases_the_outgoing_action_immediately() -> None:
    f = GazeFilter(dwell_s=0.0, grace_s=1.0)
    f.update(frozenset({HeldAction(Action.TURN_LEFT, 1.0)}), now=0.0)
    got = f.update(frozenset({HeldAction(Action.TURN_RIGHT, 1.0)}), now=0.01)
    assert _actions(got) == {Action.TURN_RIGHT}


def test_turn_magnitude_is_ema_smoothed() -> None:
    f = GazeFilter(dwell_s=0.0, grace_s=1.0, ema_alpha=0.5)
    m0 = next(iter(f.update(frozenset({HeldAction(Action.TURN_RIGHT, 1.0)}), now=0.0)))
    m1 = next(iter(f.update(frozenset({HeldAction(Action.TURN_RIGHT, 0.0)}), now=0.01)))
    assert m0.magnitude == 1.0
    assert 0.0 < m1.magnitude < 1.0
```

- [ ] **Step 2: Run and confirm failure** — FAIL.

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

_TURN = (Action.TURN_LEFT, Action.TURN_RIGHT)


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
        if out_x and not out_y:
            side = Action.TURN_LEFT if dx < 0 else Action.TURN_RIGHT
            return frozenset({HeldAction(side, self._turn_magnitude(dx))})
        if out_y and not out_x:
            move = Action.MOVE_FORWARD if dy < 0 else Action.MOVE_BACKWARD
            return frozenset({HeldAction(move, 1.0)})
        move = Action.MOVE_FORWARD if dy < 0 else Action.MOVE_BACKWARD
        side = Action.TURN_LEFT if dx < 0 else Action.TURN_RIGHT
        return frozenset(
            {HeldAction(move, 1.0), HeldAction(side, self._turn_magnitude(dx))}
        )


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
        self._since: dict[Action, float] = {}     # dwell start for a not-yet-emitted candidate
        self._emitted: dict[Action, float] = {}   # emitted action -> last time it was present
        self._ema: dict[Action, float] = {}

    def reset(self) -> None:
        self._since.clear()
        self._emitted.clear()
        self._ema.clear()

    def update(self, raw: frozenset[HeldAction], now: float) -> frozenset[HeldAction]:
        raw_by_action = {h.action: h.magnitude for h in raw}
        raw_nonempty = bool(raw_by_action)

        for action in list(self._since):
            if action not in raw_by_action:
                del self._since[action]
        for action in raw_by_action:
            self._since.setdefault(action, now)

        for action in list(self._emitted):
            if action in raw_by_action:
                self._emitted[action] = now
            elif raw_nonempty:  # a different region — release now
                del self._emitted[action]
                self._ema.pop(action, None)
            elif now - self._emitted[action] > self._grace_s:
                del self._emitted[action]
                self._ema.pop(action, None)

        for action, first_seen in list(self._since.items()):
            if action not in self._emitted and now - first_seen >= self._dwell_s:
                self._emitted[action] = now

        out: set[HeldAction] = set()
        for action in self._emitted:
            if action in _TURN:
                raw_m = raw_by_action.get(action, self._ema.get(action, 0.0))
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
- Create: `tests/fakes/fake_fire.py`
- Create: `tests/test_input_fire.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - Constant `FIRE_DEBOUNCE_S = 0.12`.
  - `class DeliberateActionSource(Protocol)`: `def activation_edge(self) -> bool: ...`.
  - `class SpokenFireSource(Protocol)`: `def spoken_fire_edge(self) -> bool: ...`.
  - `class NullSpokenFireSource`: `spoken_fire_edge()` always `False`.
  - `class FireArbiter(*, debounce_s=FIRE_DEBOUNCE_S)`: `deliberate_action()`, `spoken_fire()`, `poll(now) -> bool`, `reset()`.
  - `tests/fakes/fake_fire.py`: `class FakeSpokenFireSource` with `trigger()` and `spoken_fire_edge()` (one-shot).

- [ ] **Step 1: Write the failing tests**

Create `tests/fakes/fake_fire.py`:

```python
"""A manually triggered SpokenFireSource for fusion tests."""

from __future__ import annotations


class FakeSpokenFireSource:
    def __init__(self) -> None:
        self._pending = False

    def trigger(self) -> None:
        self._pending = True

    def spoken_fire_edge(self) -> bool:
        fired, self._pending = self._pending, False
        return fired
```

Create `tests/test_input_fire.py`:

```python
"""Tests for the debounced, dual-source fire arbiter."""

from __future__ import annotations

from fakes.fake_fire import FakeSpokenFireSource
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
    a.deliberate_action()             # inside the window
    assert a.poll(now=0.05) is False  # discarded, not queued
    a.deliberate_action()
    assert a.poll(now=0.20) is True


def test_deliberate_and_fake_spoken_edge_fuse_to_one_shot() -> None:
    a = FireArbiter(debounce_s=0.12)
    spoken = FakeSpokenFireSource()
    a.deliberate_action()
    spoken.trigger()
    if spoken.spoken_fire_edge():
        a.spoken_fire()
    assert a.poll(now=0.0) is True
    assert a.poll(now=0.05) is False


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
            self._pending = False  # discard, not queued
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
git add src/pewpew/input/fire.py tests/fakes/fake_fire.py tests/test_input_fire.py
git commit -m "feat: add the debounced dual-source fire arbiter"
```

---

## Task 8: Input source protocol, the simulator source, and the Prism stub

**Files:**
- Create: `src/pewpew/input/source.py`
- Create: `src/pewpew/input/simulator_source.py`
- Create: `tests/test_input_source.py`
- Create: `tests/test_input_source_qt.py`

**Interfaces:**
- Consumes: PySide6.
- Produces:
  - `@dataclass(frozen=True) class InputSample`: `gaze_xy: tuple[int, int] | None`, `activation_edge: bool`, `pause_edge: bool`, `debug_fire_edge: bool`.
  - `class InputSource(Protocol)`: `def sample(self, now: float) -> InputSample: ...`.
  - `class PrismInputSource`: `sample()` raises `NotImplementedError("Prism gaze/blink input arrives with the hardware phase")`.
  - `class SimulatorInputSource(QObject)` (in `simulator_source.py`): `__init__(self, widget)` installs a Qt event filter and enables mouse tracking. `MouseMove` → clamped `gaze_xy`; left `MouseButtonPress` → `activation_edge`; `KeyPress` `Return`/`Enter` → `pause_edge`; `KeyPress` `F9` **only when `DOOMED_PRISM_DEBUG_FIRE` is set** → `debug_fire_edge`; `Leave` → `gaze_xy = None`. `sample(now)` returns the accumulated `InputSample` and clears the three edges.

- [ ] **Step 1: Write the failing pure tests** (`tests/test_input_source.py`)

```python
"""Pure tests for the input-source protocol stubs (no Qt)."""

from __future__ import annotations

import pytest

from pewpew.input.source import InputSample, PrismInputSource


def test_prism_source_is_a_documented_stub() -> None:
    with pytest.raises(NotImplementedError, match="hardware phase"):
        PrismInputSource().sample(0.0)


def test_input_sample_fields() -> None:
    s = InputSample(
        gaze_xy=(1, 2), activation_edge=True, pause_edge=False, debug_fire_edge=False
    )
    assert s.gaze_xy == (1, 2) and s.activation_edge is True
```

- [ ] **Step 2: Write the failing Qt test** (`tests/test_input_source_qt.py`)

```python
"""Real pytest-qt coverage for SimulatorInputSource."""

from __future__ import annotations

import pytest

try:
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QKeyEvent, QMouseEvent
    from PySide6.QtWidgets import QApplication, QWidget
except ModuleNotFoundError as error:
    raise RuntimeError("PySide6 is required by the project's dev test extra") from error
except ImportError as error:
    if "libEGL.so.1" not in str(error):
        raise
    pytest.skip("PySide6 cannot initialize (no libEGL)", allow_module_level=True)

from pewpew.input.simulator_source import SimulatorInputSource


def _widget(qtbot) -> QWidget:
    w = QWidget()
    w.setFixedSize(640, 640)
    qtbot.addWidget(w)
    return w


def _mouse(kind, x, y, button=Qt.LeftButton):
    pos = QPointF(x, y)
    return QMouseEvent(kind, pos, pos, button, button, Qt.NoModifier)


def test_mouse_move_then_press_then_sample(qtbot) -> None:
    w = _widget(qtbot)
    src = SimulatorInputSource(w)
    QApplication.sendEvent(w, _mouse(QEvent.Type.MouseMove, 400, 300))
    QApplication.sendEvent(w, _mouse(QEvent.Type.MouseButtonPress, 400, 300))
    s = src.sample(0.0)
    assert s.gaze_xy == (400, 300)
    assert s.activation_edge is True
    assert src.sample(0.0).activation_edge is False  # one-shot


def test_return_key_sets_pause_edge_once(qtbot) -> None:
    w = _widget(qtbot)
    src = SimulatorInputSource(w)
    QApplication.sendEvent(
        w, QKeyEvent(QEvent.Type.KeyPress, Qt.Key_Return, Qt.NoModifier)
    )
    assert src.sample(0.0).pause_edge is True
    assert src.sample(0.0).pause_edge is False


def test_leave_clears_gaze(qtbot) -> None:
    w = _widget(qtbot)
    src = SimulatorInputSource(w)
    QApplication.sendEvent(w, _mouse(QEvent.Type.MouseMove, 10, 10))
    QApplication.sendEvent(w, QEvent(QEvent.Type.Leave))
    assert src.sample(0.0).gaze_xy is None


def test_f9_debug_fire_edge_only_with_env(qtbot, monkeypatch) -> None:
    monkeypatch.setenv("DOOMED_PRISM_DEBUG_FIRE", "1")
    w = _widget(qtbot)
    src = SimulatorInputSource(w)
    QApplication.sendEvent(w, QKeyEvent(QEvent.Type.KeyPress, Qt.Key_F9, Qt.NoModifier))
    assert src.sample(0.0).debug_fire_edge is True


def test_f9_is_inert_without_the_env(qtbot, monkeypatch) -> None:
    monkeypatch.delenv("DOOMED_PRISM_DEBUG_FIRE", raising=False)
    w = _widget(qtbot)
    src = SimulatorInputSource(w)
    QApplication.sendEvent(w, QKeyEvent(QEvent.Type.KeyPress, Qt.Key_F9, Qt.NoModifier))
    assert src.sample(0.0).debug_fire_edge is False
```

- [ ] **Step 3: Run and confirm failure** — FAIL (modules missing).

- [ ] **Step 4: Implement `src/pewpew/input/source.py`**

```python
"""Input-source protocol, the InputSample record, and the Prism stub."""

from __future__ import annotations

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
            self._gaze = (
                max(0, min(self._widget.width() - 1, p.x())),
                max(0, min(self._widget.height() - 1, p.y())),
            )
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
- Consumes: `pewpew.input.actions` (`ActionRouter`, `Action`), `pewpew.input.gaze` (`GazeZoneMap`, `GazeFilter`), `pewpew.input.fire` (`FireArbiter`, `SpokenFireSource`, `NullSpokenFireSource`), `pewpew.input.source` (`InputSource`), `pewpew.ipc.protocol` (`Message`).
- Produces:
  - `class InputPipeline(source, send, *, surface=(640, 640), spoken_fire=None)` — builds `GazeZoneMap`, `GazeFilter`, `FireArbiter`, `ActionRouter(send)`; `spoken_fire` defaults to `NullSpokenFireSource()`.
    - `tick(self, now: float) -> None`.
    - `toggle_pause(self) -> None` — `router.discrete(Action.PAUSE)`; flip `self.paused`.
    - `release_all(self) -> None` — `filter.reset()`, `fire.reset()`, `router.release_all()`, `self.paused = False`.
    - `paused: bool` (starts `False`).
  - `tests/fakes/fake_input.py`: `class FakeInputSource` with `queue: list[InputSample]`; `sample(now)` pops the front or returns an all-`None`/`False` sample.

- [ ] **Step 1: Write the failing tests**

Create `tests/fakes/fake_input.py`:

```python
"""A scripted InputSource for pipeline tests."""

from __future__ import annotations

from pewpew.input.source import InputSample

_EMPTY = InputSample(
    gaze_xy=None, activation_edge=False, pause_edge=False, debug_fire_edge=False
)


class FakeInputSource:
    def __init__(self, queue: list[InputSample]) -> None:
        self.queue = queue

    def sample(self, now: float) -> InputSample:
        return self.queue.pop(0) if self.queue else _EMPTY
```

Create `tests/test_input_pipeline.py`:

```python
"""Tests for the InputPipeline integration unit."""

from __future__ import annotations

import pytest

from fakes.fake_fire import FakeSpokenFireSource
from fakes.fake_input import FakeInputSource
from pewpew.input.pipeline import InputPipeline
from pewpew.input.source import InputSample
from pewpew.ipc.protocol import Message, MessageType


def _pipe(samples, *, spoken_fire=None):
    src = FakeInputSource(list(samples))
    sent: list[Message] = []
    return InputPipeline(src, sent.append, spoken_fire=spoken_fire), sent


def test_gaze_in_the_right_band_emits_a_turn_frame_after_dwell() -> None:
    far_right = InputSample((639, 320), False, False, False)
    pipe, sent = _pipe([far_right] * 40)
    for i in range(40):
        pipe.tick(now=i * 0.05)  # 2 s of ticks — the 0.15 s dwell is satisfied by tick 3
    turns = [m for m in sent if m.type is MessageType.TURN and m.value > 0]
    assert turns and turns[0].code == 4  # TURN_RIGHT, non-zero value


def test_activation_edge_produces_a_fire_pulse() -> None:
    pipe, sent = _pipe([InputSample((320, 320), True, False, False)])
    pipe.tick(now=0.0)
    assert Message.pulse(10) in sent


def test_debug_fire_edge_produces_a_fire_pulse() -> None:
    pipe, sent = _pipe([InputSample((320, 320), False, False, True)])
    pipe.tick(now=0.0)
    assert Message.pulse(10) in sent


def test_spoken_fire_source_produces_a_fire_pulse() -> None:
    spoken = FakeSpokenFireSource()
    pipe, sent = _pipe([InputSample((320, 320), False, False, False)], spoken_fire=spoken)
    spoken.trigger()
    pipe.tick(now=0.0)
    assert Message.pulse(10) in sent


def test_pause_edge_toggles_paused_and_sends_one_discrete() -> None:
    pipe, sent = _pipe([InputSample((320, 320), False, True, False)])
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
    assert sent and all(
        m.value == 0 for m in sent if m.type in (MessageType.TURN, MessageType.ACTION)
    )


def test_a_raising_send_does_not_propagate_out_of_tick() -> None:
    calls = {"n": 0}

    def flaky_send(_message):
        calls["n"] += 1
        if calls["n"] > 2:
            raise ConnectionError("peer gone")

    src = FakeInputSource([InputSample((639, 320), True, False, False)] * 6)
    pipe = InputPipeline(src, flaky_send)
    for i in range(6):
        pipe.tick(now=i * 0.05)  # must not raise
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
        self._router = ActionRouter(self._guarded_send)
        self._send = send
        self._spoken = spoken_fire or NullSpokenFireSource()
        self.paused = False

    def _guarded_send(self, message: Message) -> None:
        try:
            self._send(message)
        except OSError:
            pass  # a dead peer is handled by the host's disconnect path

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

Note: `_guarded_send` swallows `OSError` (and subclasses `ConnectionError`, `BrokenPipeError`) so a mid-track disconnect never propagates out of `tick` (spec §15). `IpcServer.send` already no-ops when disconnected, so this guard only matters for a fake/raising sink.

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
  - `DoomProcess.start(self, *, ipc_address: str | None = None) -> int` — adds `DOOMED_PRISM_IPC_ADDR=<addr>` to the child env alongside `DOOMED_PRISM_FB_NAME` when given.
  - `DoomProcess.ipc_address` property → `str | None` (set by `start`, untouched by `stop`).
  - `_command()` returns the existing 8-token list, then when `DOOMED_PRISM_WARP` is set and non-empty appends `["-warp", *shlex.split(env["DOOMED_PRISM_WARP"]), "-skill", env.get("DOOMED_PRISM_SKILL", "3")]`. `stop()` touches no socket path.

- [ ] **Step 1: Update the failing tests**

Add to `tests/test_engine.py`:

```python
def test_start_passes_the_ipc_address_through_the_child_environment(tmp_path: Path) -> None:
    factory = FakePopenFactory()
    engine = DoomProcess(_runtime_config(tmp_path), popen_factory=factory)
    engine.start(ipc_address="127.0.0.1:54321")
    assert engine.ipc_address == "127.0.0.1:54321"
    assert factory.processes[0].env["DOOMED_PRISM_IPC_ADDR"] == "127.0.0.1:54321"


def test_warp_env_appends_warp_and_skill_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOOMED_PRISM_WARP", "1 1")
    monkeypatch.delenv("DOOMED_PRISM_SKILL", raising=False)
    factory = FakePopenFactory()
    DoomProcess(_runtime_config(tmp_path), popen_factory=factory).start()
    assert factory.processes[0].arguments[-5:] == ["-warp", "1", "1", "-skill", "3"]
```

Add `monkeypatch: pytest.MonkeyPatch` to `test_start_launches_configured_windowed_engine_once_and_returns_its_pid` and begin its body with:

```python
    monkeypatch.delenv("DOOMED_PRISM_WARP", raising=False)
    monkeypatch.delenv("DOOMED_PRISM_SKILL", raising=False)
```

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


@property
def ipc_address(self) -> str | None:
    return self._ipc_address
```

- `_command`: assign the current literal to a local `command`, then before `return`:

```python
def _command(self) -> list[str]:
    command = [
        str(self._config.crispy_exe),
        "-iwad", str(self._config.iwad),
        "-window",
        "-width", str(self._config.viewport_width),
        "-height", str(self._config.viewport_height),
    ]
    warp = os.environ.get("DOOMED_PRISM_WARP")
    if warp:
        command += ["-warp", *shlex.split(warp), "-skill",
                    os.environ.get("DOOMED_PRISM_SKILL", "3")]
    return command
```

- Leave `_release_segment()` (the `/dev/shm` framebuffer unlink) unchanged; add no socket unlink.

- [ ] **Step 4: Run tests and the suite** — green.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/engine.py tests/test_engine.py
git commit -m "feat: pass the IPC address and optional warp target to Crispy"
```

---

## Task 11: Host widget — IPC server lifecycle and the input tick

**Files:**
- Modify: `src/pewpew/host_widget.py`
- Modify: `tests/test_host_widget_qt.py`

**Interfaces:**
- Consumes: `pewpew.ipc.server` (`IpcServer`), `pewpew.ipc.protocol` (`IPC_HANDSHAKE_TIMEOUT_S`), `pewpew.input.pipeline` (`InputPipeline`), `pewpew.input.simulator_source` (`SimulatorInputSource`), `pewpew.engine.DoomProcess.ipc_address`.
- Produces (added to `DoomHostWidget`, all keyword-only, test-injectable):
  - `__init__(..., *, ipc_server: IpcServer | None = None, input_pipeline: InputPipeline | None = None)`. When `ipc_server` / `input_pipeline` are given they are used verbatim; otherwise `showEvent` builds them.
  - `showEvent` (first-start branch): compute `now = self._clock()` **once** and use it for both deadlines — `self._deadline = now + self._SEGMENT_OPEN_TIMEOUT_S` (M2's existing line, changed to reuse `now`) and `self._ipc_deadline = now + IPC_HANDSHAKE_TIMEOUT_S`. `self._server = ipc_server or IpcServer()`; `self._server.on_disconnect = self._on_ipc_disconnect`; `addr = self._server.start()`; `self._engine.start(ipc_address=addr)` (replacing the bare `start()`); `self._pipeline = input_pipeline or InputPipeline(SimulatorInputSource(self.viewport), self._server.send)`.
  - `_on_tick` order:
    1. **First**, before every existing early return: `if self._server is not None: self._server.poll()`.
    2. **Then**, still before the M2 frame-wait early returns: `if self._server is not None and self._server.protocol_mismatch:` → `_cleanup_after_startup_failure()` then `raise RuntimeError("input protocol mismatch")`. A protocol mismatch is fatal regardless of frame state (spec §12), so it is checked here, not after the frame guard.
    3. The existing M2 frame-wait guard / early returns / `_seen_frame` logic, unchanged.
    4. Once past the frame guard: `if self._pipeline is not None: self._pipeline.tick(self._clock())`.
    5. `if self._server is not None and not self._server.is_connected and self._seen_frame and self._clock() > self._ipc_deadline:` → `_cleanup_after_startup_failure()` then `raise RuntimeError("engine did not connect input")`. This one *does* require frames (`_seen_frame`) — mirroring M2's "opened but no frames" logic — so a healthy engine that simply has not connected yet is not torn down prematurely.
    6. The existing counter / repaint logic.
  - `_on_ipc_disconnect`: `if self._pipeline is not None: self._pipeline.release_all()`; `if self._server is not None: self._server.close()`. **No `PAUSE`.**
  - `cleanup()` (extended in Task 12) already exists; Task 11 only adds `self._server` and `self._pipeline` fields (default `None`) and the wiring above.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_host_widget_qt.py` (a `_Server` / `_Pipeline` fake plus tests):

```python
class _Server:
    def __init__(self) -> None:
        self.started = False
        self.closed = 0
        self.sent: list = []
        self.is_connected = False
        self.protocol_mismatch = False
        self.on_disconnect = lambda: None
        self.poll_calls = 0

    def start(self) -> str:
        self.started = True
        return "127.0.0.1:0"

    def poll(self) -> None:
        self.poll_calls += 1

    def send(self, message) -> None:
        self.sent.append(message)

    def close(self) -> None:
        self.closed += 1


class _Pipeline:
    def __init__(self) -> None:
        self.ticks = 0
        self.releases = 0
        self.paused = False

    def tick(self, now: float) -> None:
        self.ticks += 1

    def release_all(self) -> None:
        self.releases += 1
        self.paused = False

    def toggle_pause(self) -> None:
        self.paused = not self.paused


def _ipc_host(qtbot, *, engine=None, reader=None, server=None, pipeline=None):
    engine = engine or _Engine()
    engine.start = lambda *, ipc_address=None: setattr(engine, "ipc_arg", ipc_address) or 8128
    reader = reader or _Reader()
    server = server or _Server()
    pipeline = pipeline or _Pipeline()
    config = SimpleNamespace(viewport_width=640, viewport_height=480)
    host = DoomHostWidget(
        config, engine=engine, frame_reader=reader,
        ipc_server=server, input_pipeline=pipeline,
    )
    qtbot.addWidget(host)
    return host, engine, reader, server, pipeline


def test_showevent_starts_server_before_engine_and_passes_the_address(qtbot) -> None:
    order: list[str] = []
    host, engine, _, server, _ = _ipc_host(qtbot)
    server.start = lambda: order.append("server") or "127.0.0.1:0"
    engine.start = lambda *, ipc_address=None: order.append(f"engine:{ipc_address}") or 8128
    host.show()
    assert order == ["server", "engine:127.0.0.1:0"]


def test_on_tick_polls_the_server_before_any_early_return(qtbot) -> None:
    reader = _Reader()
    reader.available = False  # forces the "waiting for segment" early return
    host, _, _, server, _ = _ipc_host(qtbot, reader=reader)
    host.show()
    host._on_tick()
    assert server.poll_calls >= 1


def test_ipc_disconnect_releases_all_and_closes_without_pause(qtbot) -> None:
    host, _, _, server, pipeline = _ipc_host(qtbot)
    host.show()
    host._on_ipc_disconnect()
    assert server.closed == 1
    assert pipeline.releases == 1
    assert not any(getattr(m, "code", None) == 20 for m in server.sent)


def test_protocol_mismatch_raises_after_cleanup(qtbot) -> None:
    # No frame is set: the mismatch check runs before the M2 frame-wait guard.
    host, engine, _, server, _ = _ipc_host(qtbot)
    server.protocol_mismatch = True
    host.show()
    with pytest.raises(RuntimeError, match="input protocol mismatch"):
        host._on_tick()
    assert engine.stop_calls == 1


def test_no_ipc_connection_past_deadline_raises(qtbot) -> None:
    reader = _Reader()
    now = [0.0]  # showEvent arms both deadlines from now[0]; the tick reads a later value
    host, engine, _, server, _ = _ipc_host(qtbot, reader=reader)
    host._clock = lambda: now[0]  # type: ignore[assignment]
    host.show()                    # _deadline = 10.0, _ipc_deadline = 10.0
    reader.try_open()
    reader.set_frame(counter=1, byte=0x20)  # frames flowing, but IPC never connects
    now[0] = 100.0                 # well past _ipc_deadline
    with pytest.raises(RuntimeError, match="engine did not connect input"):
        host._on_tick()
    assert engine.stop_calls == 1
```

- [ ] **Step 2: Run and confirm failure** — FAIL (`ipc_server=` kwarg / `_on_ipc_disconnect` / the wiring absent).

- [ ] **Step 3: Implement the changes** per the Interfaces block (the numbered `_on_tick` order is the contract). Keep the M2 framebuffer path (`_DoomViewport`, `_seen_frame`, the frame deadline) intact; the IPC concerns are additive. `showEvent` arms both `self._deadline` and `self._ipc_deadline` from a single `now = self._clock()` call.

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

## Task 12: Host widget — pause overlay, hide/show symmetry, cleanup ordering

**Files:**
- Modify: `src/pewpew/host_widget.py`
- Modify: `tests/test_host_widget_qt.py`

**Interfaces:**
- Consumes: Task 11's `self._server` / `self._pipeline`.
- Produces:
  - `class _PauseOverlay(QWidget)` — a translucent child of the host, `objectName() == "pause_overlay"`, covering the viewport rect, `paintEvent` draws `PAUSED` in an emitted-light colour. Created in `__init__` as a child of `self`, hidden initially.
  - `_sync_pause_overlay(self)` — `self._pause_overlay.setVisible(self._pipeline.paused if self._pipeline is not None else False)`. Called **as the first thing in `_on_tick` after `self._server.poll()`** (i.e. before any M2 early return, so a test that calls `_on_tick()` with no frame still updates the overlay), and at the end of `hideEvent` / the `showEvent` restart branch.
  - `hideEvent` (after the existing `super().hideEvent(event)` + `self._timer.stop()`; then `if self._shutdown_requested or not self._started: return`): `self._pipeline.release_all()`; if `not self._pipeline.paused`: `self._pipeline.toggle_pause()`; `self._sync_pause_overlay()`.
  - `showEvent` restart branch (already-started, not shutting down): if `self._pipeline.paused`: `self._pipeline.toggle_pause()`; `self._pipeline.release_all()`; `self._sync_pause_overlay()`; then the existing `self._timer.start()`.
  - `cleanup()` re-ordered: stop the timer → `if self._pipeline is not None:` try `self._pipeline.release_all()`, on success `self._pipeline = None` → `if self._server is not None:` try `self._server.close()`, on success `self._server = None` → (existing) `reader.close()` then `engine.stop()`, each keeping the existing retry-on-transient-failure / on-success-null pattern so a second `cleanup()` is a genuine no-op. `pipeline.release_all()` and `server.close()` are both safe on a dead child.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_host_widget_qt.py`:

```python
def test_pause_overlay_visibility_follows_pipeline_paused(qtbot) -> None:
    host, _, _, _, pipeline = _ipc_host(qtbot)
    host.show()
    overlay = host.findChild(QWidget, "pause_overlay")
    assert overlay is not None
    pipeline.paused = True
    host._on_tick()  # _sync_pause_overlay runs before the frame-wait early return
    assert overlay.isVisibleTo(host) is True


def test_hideevent_releases_all_pauses_and_shows_overlay(qtbot) -> None:
    host, _, _, _, pipeline = _ipc_host(qtbot)
    host.show()
    host.hide()
    assert pipeline.releases >= 1
    assert pipeline.paused is True
    # host is hidden, so isVisible() is False; isVisibleTo(host) reflects the overlay's own flag
    assert host.findChild(QWidget, "pause_overlay").isVisibleTo(host) is True


def test_showevent_after_start_unpauses_and_hides_overlay(qtbot) -> None:
    host, _, _, _, pipeline = _ipc_host(qtbot)
    host.show()
    host.hide()          # -> paused
    host.show()           # restart branch
    assert pipeline.paused is False
    assert host.findChild(QWidget, "pause_overlay").isVisibleTo(host) is False


def test_cleanup_order_includes_pipeline_release_and_server_close(qtbot) -> None:
    order: list[str] = []
    host, engine, reader, server, pipeline = _ipc_host(qtbot)
    pipeline.release_all = lambda: order.append("release")  # type: ignore[assignment]
    server.close = lambda: order.append("server")           # type: ignore[assignment]
    reader.close = lambda: order.append("reader")           # type: ignore[assignment]
    engine.stop = lambda: order.append("engine")            # type: ignore[assignment]
    host.cleanup()
    assert order == ["release", "server", "reader", "engine"]
    host.cleanup()  # idempotent: pipeline and server are None now, nothing re-runs
    assert order == ["release", "server", "reader", "engine"]
```

- [ ] **Step 2: Run and confirm failure** — FAIL (`_PauseOverlay` / `_sync_pause_overlay` / hide-show symmetry / cleanup order absent).

- [ ] **Step 3: Implement the changes** per the Interfaces block. The overlay is created in `__init__` as a child of `self`, geometry `self.viewport.geometry()`, hidden initially. `_sync_pause_overlay()` runs early in `_on_tick` (right after `server.poll()`). `hideEvent`/`showEvent` guards use the existing `self._shutdown_requested` and `self._started` flags. `cleanup()` nulls `self._pipeline` / `self._server` on success so the second call is a no-op.

- [ ] **Step 4: Run tests and the suite**

```bash
python -m pytest tests/test_host_widget.py tests/test_host_widget_qt.py -q
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pewpew/host_widget.py tests/test_host_widget_qt.py
git commit -m "feat: add the pause overlay and symmetric hide/show input release"
```

---

## Task 13: README refresh, distribution metadata, and the C/Python constant-sync test

**Files:**
- Modify: `README.md`
- Modify: `tests/test_distribution_metadata.py`

**Interfaces:**
- Consumes: `pewpew.input.actions.Action`, `pewpew.ipc.protocol.MessageType`, the committed `patches/crispy-doom-ipc-input.diff`.
- Produces: README "License" and "Building the patched engine" name **both** patches; "Current status" notes M3a in progress; "What comes next" says voice ships in 3b after an offline-speech licence review; a new metadata test asserting the License section names both patches and the `patches/` directory holds exactly the two diffs; a new test greps the committed `.diff` for the `#define AC_*` / `#define MT_*` lines and asserts equality with the Python enums.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_distribution_metadata.py`:

```python
def test_readme_names_both_engine_patches_in_the_license_section() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    license_section = text.split("## License", 1)[1].lower()
    assert "frame" in license_section and "ipc" in license_section
    diffs = {p.name for p in (ROOT / "patches").iterdir() if p.suffix == ".diff"}
    assert diffs == {"crispy-doom-fb-export.diff", "crispy-doom-ipc-input.diff"}


def test_c_patch_constants_match_the_python_enums() -> None:
    import re

    from pewpew.input.actions import Action
    from pewpew.ipc.protocol import MessageType

    diff = (ROOT / "patches" / "crispy-doom-ipc-input.diff").read_text(encoding="utf-8")
    defs = {n: int(v) for n, v in re.findall(r"#define\s+(AC_\w+|MT_\w+)\s+(\d+)", diff)}
    assert defs["AC_MOVE_FORWARD"] == Action.MOVE_FORWARD
    assert defs["AC_MOVE_BACKWARD"] == Action.MOVE_BACKWARD
    assert defs["AC_TURN_LEFT"] == Action.TURN_LEFT
    assert defs["AC_TURN_RIGHT"] == Action.TURN_RIGHT
    assert defs["AC_FIRE"] == Action.FIRE
    assert defs["AC_USE"] == Action.USE
    assert defs["AC_PAUSE"] == Action.PAUSE
    assert defs["MT_HELLO"] == MessageType.HELLO
    assert defs["MT_ACTION"] == MessageType.ACTION
    assert defs["MT_PULSE"] == MessageType.PULSE
    assert defs["MT_DISCRETE"] == MessageType.DISCRETE
    assert defs["MT_TURN"] == MessageType.TURN
    assert defs["MT_BYE"] == MessageType.BYE
```

- [ ] **Step 2: Run and confirm failure** — FAIL (README section unchanged; the two tests fail on the current README / absent grep matches — note `crispy-doom-ipc-input.diff` already exists from Task 3, so `test_c_patch_constants...` fails only on the README-independent grep if the diff's `#define`s differ from the enums, which they must not).

- [ ] **Step 3: Edit `README.md`**

- "Current status": add a bullet — *Milestone 3a (hands-free input over a local IPC socket) is in progress on `feature/doomed-prism-m3`.*
- "What comes next": reword to — *Milestone 3a delivers the input core and the IPC boundary. Voice — spoken menu/weapon commands and a spoken "pew pew" — ships in Milestone 3b, after an offline-speech-library licence review.*
- "Building the patched engine": where it currently describes the one committed patch, change to name **both** — the frame-export patch and the IPC-input patch — applied as a series by `scripts/build_crispy.py`.
- "License": change *"contains only the frame‑export patch and a pinned reference to Crispy Doom, never its source"* → *"contains only the frame‑export and IPC‑input patches and a pinned reference to Crispy Doom, never its source"*. (Preserve the existing U+2011 non-breaking hyphens in that sentence.)

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
git commit -m "docs: name the IPC-input patch in the README and add the C/Python constant-sync test"
```

---

## Task 14: CI IPC runtime smoke test

**Files:**
- Create: `scripts/ci_ipc_smoke.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `pewpew.ipc.server.IpcServer`, `pewpew.ipc.protocol.Message`, `pewpew.framebuffer.FrameReader`.
- Produces: a CI-only script (not a pytest module) taking `<crispy-doom-exe> <iwad>`; binds an `IpcServer` at the fixed path `/tmp/doomed-prism-ipc-ci.sock`; launches the engine with `DOOMED_PRISM_IPC_ADDR`, `DOOMED_PRISM_FB_NAME`, `DOOMED_PRISM_WARP="1 1"`; completes the handshake; streams a 500-frame action flood; asserts the framebuffer `frame_counter` advances throughout; then `server.close()` + `SIGINT`, asserting no orphan `crispy-doom` and no leftover socket. Prints only the socket basename + presence/absence. Exits 0 on success / non-POSIX, 1 on failure.

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

Do **not** `cat ipc-smoke.log` into the summary — the templated line above is the whole summary block.

- [ ] **Step 3: Run the suite** (`ci_ipc_smoke.py` is not collected by pytest; just confirm nothing regressed)

```bash
python -m pytest -q
```

- [ ] **Step 4: Commit**

```bash
git add scripts/ci_ipc_smoke.py .github/workflows/ci.yml
git commit -m "ci: add the POSIX IPC runtime smoke test"
```

---

## Task 15: Milestone 3a decision gate

**Files:**
- Create: `docs/validation/milestone-3a-checklist.md`
- Create: `docs/validation/milestone-3a-result.md`
- Create: `tests/test_validation_docs_m3.py`

**Interfaces:**
- Consumes: everything.
- Produces: the manual gate documents (mirroring `docs/validation/milestone-2-*.md` structure and safety rules) and the static contract test.

- [ ] **Step 1: Write `docs/validation/milestone-3a-checklist.md`**

Mirror the M2 checklist. Sections:

- *Scope and safety* — no Raven source / credentials / private paths / commercial IWAD identity; evidence under gitignored `artifacts/milestone-3/`; record the IPC address **only** as the placeholders `<tempdir>/doomed-prism-ipc-<pid>-<token>.sock` and `127.0.0.1:<port>`, and only its presence/absence + port.
- *Environment and launch* — `build_crispy.py` builds the series; `build_crispy.py --check` passes (restore + real `apply p1` + `apply --check p2`); record `git apply --stat patches/crispy-doom-ipc-input.diff` and confirm it adds only `src/i_ipc_input.c` / `.h` plus small hunks in `d_loop.c` / `i_video.c` / `src/CMakeLists.txt`, within the stated line ceiling; `doomed-prism validate` exits 0; `python -m pytest -q` green; `python scripts/check_publication_safety.py --root .` and `--root . --history` exit 0; establish the M2 before/after crispy-doom PID baseline; set `DOOMED_PRISM_WARP="1 1"` and `DOOMED_PRISM_DEBUG_FIRE=1`; launch `doomed-prism run-desktop`.
- *Objective checks* — exactly one new crispy-doom PID; the IPC socket present while running and gone after close; a `FrameReader` probe still shows `frame_counter` advancing (M2 path unbroken); **with Crispy's SDL window minimised or behind the Raven Simulator, and unfocused, for the whole run** (copy this phrasing verbatim from spec §17): left/right turn bands turn the view, returning to the dead zone stops the turn within ~2 ticks, gaze farther from the dead zone turns faster, upper/lower bands walk forward/back, an upper corner walks-and-turns, one click fires one shot, five fast clicks fire fewer than five shots, `F9` fires through the same path, a click and an `F9` within ~30 ms fire once, `Enter` shows the `PAUSED` overlay and pauses / `Enter` resumes; no `SetParent` anywhere.
- *Lifecycle checks* — sleep/conceal (or hide the host) → pause + overlay, resume → unpause + no stuck key (a held turn from before the hide does not persist); kill the PewPew process while a turn is held → DOOM stops turning, keeps running on SDL input, no orphan after its window is closed; normal close → `cleanup()` runs stop-tick → release-all → server-close → reader-close → engine-stop with no exception, one PID gone, socket removed.
- *Per-mode evidence* — Raw plus each available optical mode (Night, Day, Outdoors, Camera): one short local **Freedoom-only** video or two time-separated captures showing gaze-driven view motion and a fired shot inside the composited viewport with the SDL window unfocused; any clip promoted into tracked `docs/media/` is Freedoom-only and reviewed frame-by-frame for usernames, paths, and IWAD identity.
- *Hard decision rule* — the four strings from spec §17: `PASS — IPC input path viable`, `FAIL — IPC input path insufficient`, `BLOCKED/RETRY — implementation or environment failure`, `PENDING — incomplete evidence`, each with the spec §17 definition.
- *Final automated verification and commit* — `python -m pytest -q`; `git diff --check`; exact-path `git add -- docs/validation/milestone-3a-checklist.md docs/validation/milestone-3a-result.md`; `git diff --cached --name-status`; `git diff --cached --check`; both safety scans; `git commit -m "docs: record IPC input path result"`; `git status --short` empty.

- [ ] **Step 2: Write `docs/validation/milestone-3a-result.md`**

Mirror `milestone-2-result.md`: run identification, environment, launch/interaction, objective-check results, per-mode evidence table, lifecycle-check results, automated verification, and a single **Final decision** field starting at `PENDING — incomplete evidence`, followed by the four decision definitions verbatim from spec §17.

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
    lowered = d.lower()
    assert "release" in lowered and "held" in lowered


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

- [ ] **Step 4: Run the suite and the scans**

```bash
python -m pytest -q
python scripts/check_publication_safety.py --root .
python scripts/check_publication_safety.py --root . --history
```

Expected: all green (the M3 doc test now passes against the docs written in Steps 1–2); both scans exit 0.

- [ ] **Step 5: Commit the gate scaffolding**

```bash
git add docs/validation/milestone-3a-checklist.md docs/validation/milestone-3a-result.md tests/test_validation_docs_m3.py
git commit -m "docs: add the Milestone 3a decision-gate checklist and result template"
```

- [ ] **Step 6: Run the manual decision gate**

Follow `docs/validation/milestone-3a-checklist.md` on Windows against a separately installed Raven Framework. Record observations in `milestone-3a-result.md`. Set the single **Final decision** field per spec §17. This step is manual and gated — stop here and hand the result to the user; do not push, merge, or publish.

---

## Self-Review

**Spec coverage (spec §16 Plan 3a tasks ↔ this plan):** spec-task 1↔T1, 2↔T2, 3↔T3, 4↔T4, 5↔T5, 6↔T6, 7↔T7, 8↔T8, 9↔T9, 10↔T10, 11↔T11+T12 (host_widget split for reviewability), 12↔T13, 13↔T14, 14↔T15. Spec §5 code table → T1/T5 constraints + T5 `test_action_codes_match_the_wire_table` + T13 `test_c_patch_constants_match_the_python_enums`. Spec §6 (`InputSample`, sources) → T8. §7 (gaze) → T6. §8 (fire, `FakeSpokenFireSource`) → T7. §10 (C patch, `BuildNewTic` invariant, `PULSE_HOLD_TICS`, `ipc_connect`/`ipc_handshake` in full, `data1 = 0`) → T3. §11 (`-warp`) → T10. §12 (lifecycle: release-all, symmetric pause, `IPC_HANDSHAKE_TIMEOUT_S`, error strings) → T9 + T11 + T12. §13 (patch series, `ci_ipc_smoke`, `feature/doomed-prism-m3` trigger) → T4 + T14. §14 (GPL headers, corresponding source, diff-minimality, placeholder addresses) → T3 + T13 + T15. §17 gate → T15. §18 exit criteria → T14 (`ci_ipc_smoke` fixed minimum) + T15. No gap.

**Placeholder scan:** every code step carries real code, including T3's `ipc_connect` / `ipc_handshake` (now spelled out for both AF_INET and AF_UNIX, matching the M2 Task 2 detail level). No "TBD" / "similar to" / "add error handling".

**Type consistency:** `Action` codes (1/2/3/4/10/11/20) identical in T1/T5 constraints, T3 `#define`s, T5 enum + test, T13 grep test. `Message.turn(code, value)` / `Message.action(code, value)` take wire ints everywhere (T1/T5/T13/T14). `HeldAction(action, magnitude)` identical in T5/T6/T9. `InputSample(gaze_xy, activation_edge, pause_edge, debug_fire_edge)` identical in T8/T9. `InputPipeline(source, send, *, surface, spoken_fire)` / `tick(now)` / `release_all()` / `toggle_pause()` / `paused` identical in T9/T11/T12. `IpcServer(*, address_factory, on_disconnect)` + `on_disconnect` settable attr + `start()->str` / `poll()` / `send(Message)` / `close()` / `is_connected` / `protocol_mismatch` identical in T2/T11/T12/T14. `DoomProcess.start(*, ipc_address=None)` / `ipc_address` identical in T10/T11. `IPC_HANDSHAKE_TIMEOUT_S` / `IPC_HELLO_TIMEOUT_S` defined in T1, consumed in T11 (and mirrored C-side as `IPC_HELLO_TIMEOUT_MS` in T3).
