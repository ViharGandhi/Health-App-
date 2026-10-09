from datetime import date
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest

from google_health_client import GoogleHealthClient
from main import app


@pytest.mark.parametrize('route,payload', [
    ('/api/health', {'dailyRestingHeartRate': {'date': {'year': 2026, 'month': 10, 'day': 7}, 'beatsPerMinute': 'junk'}}),
    ('/api/sleep/stress', {}),
    ('/api/sleep/stages/typical-ranges', {}),
    ('/api/sleep', {'sleep': None}),
])
def test_malformed_provider_response_is_explicit_502(route, payload, tmp_path):
    client = GoogleHealthClient('synthetic')
    client._points = AsyncMock(return_value=[payload])
    with patch('main._get_token', AsyncMock(return_value='synthetic')), \
         patch('main.get_session', return_value=None), patch('main.GoogleHealthClient', return_value=client), \
         patch.dict('main.os.environ', {'SLEEP_STRESS_DB_PATH': str(tmp_path / 'stress.sqlite3'),
                                       'SLEEP_STAGE_DB_PATH': str(tmp_path / 'stages.sqlite3')}), \
         TestClient(app, raise_server_exceptions=False) as test_client:
        result = test_client.get(route, headers={'X-User-Date': date(2026, 10, 7).isoformat()})
    assert result.status_code == 502
    assert result.json()['reason'] == 'invalid_provider_payload'
    assert 'junk' not in result.text
