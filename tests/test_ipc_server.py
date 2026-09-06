"""Tests for the PewPew-side IPC server (real in-process loopback, no child process)."""

from __future__ import annotations

import socket
import sys

import pytest

from fakes.fake_ipc import FakeIpcClient
from pewpew.ipc.protocol import IPC_PROTOCOL_VERSION, Message
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
    # _connect already called server.start(); reuse the bound address (white-box,
    # same-package test).
    second = FakeIpcClient(server._address)
    for _ in range(10):
        server.poll()
    assert server.is_connected is True  # first client still connected
    server.send(Message.pulse(10))
    assert first.recv_message() == Message.pulse(10)
    first.close()
    second.close()


def test_close_is_idempotent(server: IpcServer) -> None:
    server.start()
    server.close()
    server.close()


@pytest.mark.skipif(sys.platform == "win32", reason="AF_UNIX path-length guard is POSIX")
def test_default_posix_factory_rejects_an_over_long_path(monkeypatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/" + "x" * 200)
    with pytest.raises(OSError):
        IpcServer().start()
