from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest

from main import app


@pytest.mark.parametrize('route', ['/api/sleep', '/api/health', '/api/recovery', '/api/strain?demo=true'])
@pytest.mark.parametrize('header,value', [('X-User-Date', 'bad'), ('X-User-Date', ''),
    ('X-User-Age', 'nan'), ('X-User-Age', '101'), ('X-User-Sex', 'invalid'),
    ('X-User-Timezone', '../UTC'), ('X-User-Timezone', 'bad/zone')])
def test_invalid_profile_headers_return_clear_four_xx(route, header, value):
    headers = {'X-User-Date': '2026-10-07', header: value}
    with patch('main._get_token', AsyncMock(return_value=None)), TestClient(app) as client:
        result = client.get(route, headers=headers)
    assert 400 <= result.status_code < 500
    assert result.json()['detail']
