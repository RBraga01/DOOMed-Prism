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
