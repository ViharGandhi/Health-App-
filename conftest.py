"""No outbound HTTP in tests; loopback sockets only support Windows asyncio IPC."""
import httpx
import pytest


@pytest.fixture(autouse=True)
def block_real_http(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Outbound HTTP blocked by the test session')
    async def async_blocked(*args, **kwargs):
        blocked()
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', async_blocked)
