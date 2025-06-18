"""
Testing the Spektralwerk class
"""

import socket
import threading

import pytest

from spektralwerk_scpi_client.devices import SpektralwerkCore
from spektralwerk_scpi_client.exceptions import (
    SpektralwerkConnectionError,
    SpektralwerkTimeoutError,
)


class TCPServerMock:
    """
    A mocked TCP server
    """

    def __init__(self) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def __enter__(self):
        self._socket.bind(("127.0.0.1", 5678))
        return self

    def __exit__(self, *args, **kwargs):
        self._socket.close()

    def listen_for_traffic(self):
        while True:
            self._socket.listen(5)
            connection, _ = self._socket.accept()
            message = connection.recv(1024).decode()
            if message != b"":
                break
        connection.close()


@pytest.fixture
def mocked_tcp_server():
    tcp_server = TCPServerMock()
    with tcp_server as example_server:
        thread = threading.Thread(target=example_server.listen_for_traffic)
        thread.start()
        yield example_server


def test_specktralwerk_core_connection(monkeypatch):
    """
    Provide a wrong/non-existing host and/or port should raise a ConnectionRefusedError which will
    raise a SpektralwerkConnectionError
    """
    spw = SpektralwerkCore(host="127.0.0.1", port=5678)

    def mock_busy_resource(*args, **kwargs):
        raise ConnectionRefusedError

    monkeypatch.setattr("pyvisa.ResourceManager.open_resource", mock_busy_resource)

    with pytest.raises(SpektralwerkConnectionError) as exc_info:
        spw.get_identity()
    assert exc_info.type is SpektralwerkConnectionError


def test_spektralwerk_core_communication(monkeypatch, mocked_tcp_server):
    """
    Provide non-existing/invalid scpi query command leads to
    """
    spw = SpektralwerkCore(host="127.0.0.1", port=5678)

    def mock_idn(*args, **kwargs):
        return "NON_EXISTING_IDN_COMMAND?"

    monkeypatch.setattr("spektralwerk_scpi_client.scpi.commands.SCPICommand", mock_idn)

    with pytest.raises(SpektralwerkTimeoutError) as exc_info:
        spw.get_identity()
    assert exc_info.type is SpektralwerkTimeoutError
