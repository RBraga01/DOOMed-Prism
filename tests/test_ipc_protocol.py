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
