from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest

from main import app


@pytest.mark.parametrize('route', ['/api/strain?demo=true', '/api/strain/analytics?demo=true'])
@pytest.mark.parametrize('session', [None, {'health_user_id': 'synthetic-account'}])
def test_explicit_demo_does_not_read_or_refresh_real_token(route, session):
    with patch('main.get_session', return_value=session), \
         patch('main._get_token', AsyncMock(side_effect=AssertionError('Real token path reached'))), TestClient(app) as client:
        result = client.get(route, headers={'X-User-Date': '2026-10-07', 'X-User-Age': '30'})
    assert result.status_code == 200
    assert result.json()['is_mock'] is True
