from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest
from auth import COOKIE_NAME, _sign

from main import app


@pytest.mark.parametrize('route', ['/api/dashboard', '/api/recovery', '/api/recovery/analytics', '/api/sleep',
    '/api/sleep/need', '/api/sleep/analytics', '/api/sleep/efficiency', '/api/sleep/consistency',
    '/api/sleep/consistency/score', '/api/sleep/stress', '/api/sleep/heart-rate',
    '/api/sleep/stages/typical-ranges', '/api/health', '/api/health/heart-rate', '/api/strain'])
def test_expired_connected_session_never_falls_back_to_demo(route):
    with patch('main.get_session', return_value={'connected': True}), \
         patch('main.get_valid_access_token', AsyncMock(return_value=None)), TestClient(app) as client:
        result = client.get(route, headers={'X-User-Date': '2026-10-07'})
    assert result.status_code == 401
    assert result.json()['detail']


@pytest.mark.parametrize('cookie', ['tampered', _sign([]), _sign({}),
    _sign({'access_token': 'synthetic', 'expires_at': 'invalid'})],
    ids=['tampered', 'signed_list', 'empty_session', 'invalid_expiry'])
def test_invalid_present_cookie_is_rejected(cookie):
    with TestClient(app) as client:
        client.cookies.set(COOKIE_NAME, cookie)
        result = client.get('/api/health', headers={'X-User-Date': '2026-10-07'})
    assert result.status_code == 401


def test_invalid_cookie_does_not_block_explicit_demo():
    with TestClient(app) as client:
        client.cookies.set(COOKIE_NAME, 'tampered')
        result = client.get('/api/strain?demo=true', headers={'X-User-Date': '2026-10-07'})
    assert result.status_code == 200
    assert result.json()['is_mock']
