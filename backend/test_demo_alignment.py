from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app


HEADERS = {'X-User-Date': '2026-09-30', 'X-User-Age': '70',
           'X-User-Sex': 'f', 'X-User-Timezone': 'Europe/Berlin'}


@pytest.mark.parametrize('path,date_key', [('/api/dashboard', 'date'),
    ('/api/health', 'date'), ('/api/health/heart-rate', 'date'),
    ('/api/sleep/consistency', 'range_end')])
def test_demo_honors_selected_calendar_day(path, date_key):
    with patch.object(httpx.AsyncClient, 'request', side_effect=AssertionError('Outbound HTTP')):
        response = TestClient(app).get(path, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()[date_key] == HEADERS['X-User-Date']


def test_dashboard_and_detail_use_identical_date_and_profile():
    client = TestClient(app)
    with patch.object(httpx.AsyncClient, 'request', side_effect=AssertionError('Outbound HTTP')):
        dashboard = client.get('/api/dashboard', headers=HEADERS).json()
        for key in ('strain', 'sleep', 'recovery'):
            detail = client.get('/api/' + key, headers=HEADERS).json()
            assert dashboard[key] == detail
        analytics = client.get('/api/recovery/analytics?demo=legacy', headers=HEADERS).json()
        assert analytics['current'] == dashboard['recovery']
