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
    try:
        os.chmod(path, 0o600)  # owner-only: no local user can race-connect
    except OSError:
        pass  # some platforms no-op / reject chmod on a socket node
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
