import asyncio
from datetime import date
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
import pytest

from main import app, _compute_connected_recovery, _compute_real_sleep
from mock_recovery import MockRecoveryClient

DAY = date(2026, 10, 7)


@pytest.mark.parametrize('route', ['/api/recovery', '/api/recovery?demo=estimate', '/api/recovery/analytics',
    '/api/sleep', '/api/sleep/analytics', '/api/sleep/consistency', '/api/sleep/consistency/score',
    '/api/sleep/efficiency', '/api/sleep/need', '/api/sleep/stress', '/api/sleep/stages/typical-ranges', '/api/sleep/heart-rate'])
def test_each_score_route_names_its_estimator(route):
    with patch('main._get_token', AsyncMock(return_value=None)), TestClient(app) as client:
        result = client.get(route, headers={'X-User-Date': DAY.isoformat(), 'X-User-Age': '30'})
    assert result.status_code == 200
    assert result.json()['estimator']


def test_connected_and_legacy_modes_report_actual_algorithms():
    async def run():
        client = MockRecoveryClient(DAY)
        assert (await _compute_connected_recovery(client, DAY, 30)).estimator == 'connected_recovery'
        assert (await _compute_real_sleep(client, DAY, None, 30)).estimator == 'legacy_composite_sleep'
    asyncio.run(run())
    with patch('main._get_token', AsyncMock(return_value=None)), TestClient(app) as client:
        dashboard = client.get('/api/dashboard', headers={'X-User-Date': DAY.isoformat()}).json()
    assert dashboard['recovery']['estimator'] == 'legacy_prototype'
    assert dashboard['sleep']['estimator'] == 'legacy_composite_sleep'
