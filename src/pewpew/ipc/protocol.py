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
