import socket

import httpx
import pytest


def test_suite_has_a_timeout_and_blocks_outbound_connections(pytestconfig):
    assert float(pytestconfig.getini('timeout') or 0) == 30
    assert pytestconfig.getoption('allow_hosts') == '127.0.0.1,::1'
    from pytest_socket import SocketConnectBlockedError
    with socket.socket() as connection:
        with pytest.warns(UserWarning, match='tried to use socket.socket.connect'), pytest.raises(SocketConnectBlockedError):
            connection.connect(('203.0.113.1', 443))


def test_real_http_transports_are_blocked_even_for_localhost():
    with pytest.raises(AssertionError, match='Outbound HTTP blocked'):
        httpx.HTTPTransport().handle_request(httpx.Request('GET', 'http://127.0.0.1:12345'))
