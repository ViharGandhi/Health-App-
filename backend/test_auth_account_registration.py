from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import router, COOKIE_NAME, _unsign
from health_read_store import HealthReadStore


def browser():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def login(client):
    with patch('auth.CLIENT_ID', 'client'), patch('auth.CLIENT_SECRET', 'secret'):
        response = client.get('/api/auth/login', follow_redirects=False)
    return parse_qs(urlparse(response.headers['location']).query)['state'][0]


@pytest.mark.parametrize('identity', [{}, {'healthUserId': None}, {'healthUserId': 123},
                                      {'healthUserId': ''}, {'healthUserId': ' '}, []])
def test_callback_cannot_connect_without_stable_health_identity(identity):
    client = browser()
    state = login(client)
    def respond(request):
        return httpx.Response(200, json={'access_token': 'access', 'expires_in': 3600}
                              if request.url.path == '/token' else identity)
    original = httpx.AsyncClient
    with patch('auth.httpx.AsyncClient', side_effect=lambda: original(transport=httpx.MockTransport(respond))):
        result = client.get(f'/api/auth/callback?code=sample&state={state}', follow_redirects=False)
    assert 'error=health_access_failed' in result.headers['location']
    assert COOKIE_NAME not in result.cookies


def test_login_registers_account_before_returning_connected_cookie(tmp_path):
    store = HealthReadStore(tmp_path / 'health.db')
    client = browser()
    state = login(client)
    def respond(request):
        if request.url.path == '/token':
            payload = {'access_token': 'access', 'refresh_token': 'refresh', 'expires_in': 3600}
        elif request.url.path.endswith('/identity'):
            payload = {'healthUserId': '123'}
        else:
            payload = {'email': 'profile@example.test', 'name': 'Profile'}
        return httpx.Response(200, json=payload)
    original = httpx.AsyncClient
    with patch('auth.httpx.AsyncClient', side_effect=lambda: original(transport=httpx.MockTransport(respond))), \
         patch('google_health_client.read_store', return_value=store):
        result = client.get(f'/api/auth/callback?code=sample&state={state}', follow_redirects=False)
    assert result.headers['location'].endswith('/?connected=true')
    assert _unsign(result.cookies[COOKIE_NAME])['health_user_id'] == '123'
    with store.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM health_account_aliases').fetchone()[0] == 1
