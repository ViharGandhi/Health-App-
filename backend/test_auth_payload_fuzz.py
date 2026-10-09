import asyncio
from unittest.mock import AsyncMock, patch
import time
import httpx
from fastapi.testclient import TestClient
import pytest
from hypothesis import given, settings, strategies as st
from auth import get_valid_access_token
from test_adapter_fuzz import payload
from main import app


@pytest.mark.parametrize('kind', ['session', 'refresh_payload'])
@settings(max_examples=200, derandomize=True, deadline=None, database=None)
@given(payload)
def test_session_and_refresh_payloads_fail_closed(kind, value):
    async def run():
        session = value if kind == 'session' else {'refresh_token': 'synthetic', 'expires_at': 0}
        refresh = value if kind == 'refresh_payload' else None
        with patch('auth.refresh_access_token', AsyncMock(return_value=refresh)):
            result = await get_valid_access_token(session)
        assert result is None or isinstance(result, str) and result
    asyncio.run(run())


def test_huge_expiry_fails_closed():
    assert asyncio.run(get_valid_access_token({'expires_at': 10**1000, 'access_token': 'synthetic'})) is None


@pytest.mark.parametrize('value', [True, 7, ['synthetic'], {'unexpected': 'synthetic'}])
def test_nonstring_access_token_fails_closed(value):
    assert asyncio.run(get_valid_access_token({'expires_at': time.time() + 3600, 'access_token': value})) is None


@settings(max_examples=200, derandomize=True, deadline=None, database=None)
@given(payload)
def test_callback_malformed_token_response_fails_closed(value):
    original = httpx.AsyncClient
    def respond(request):
        return httpx.Response(200, json=value if request.url.path == '/token' else {'healthUserId': 'synthetic'})
    with patch('auth._unsign', return_value={'state': 'synthetic', 'verifier': 'synthetic'}), \
         patch('auth.httpx.AsyncClient', side_effect=lambda: original(transport=httpx.MockTransport(respond))):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get('/api/auth/callback?code=synthetic&state=synthetic', follow_redirects=False)
    assert response.status_code == 307
    assert 'error=token_exchange_failed' in response.headers['location']
    assert 'soma_session' not in response.cookies
