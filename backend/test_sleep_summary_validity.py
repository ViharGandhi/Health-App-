import asyncio
from datetime import date

import pytest

from main import _compute_real_sleep
from mock_recovery import MockRecoveryClient
from sleep_need import calculate_sleep_need


@pytest.mark.parametrize('problem', ['pending', 'missing', 'nan', 'too_long'])
def test_unusable_provider_sleep_summary_cannot_produce_composite_score(problem):
    day = date(2026, 10, 7)
    client = MockRecoveryClient(day)
    point = next(p for p in client.points['sleep'] if p['name'] == f'demo-main-{day}')
    if problem == 'pending': point['sleep']['metadata']['processed'] = False
    elif problem == 'missing': point['sleep']['summary'].pop('minutesAsleep')
    elif problem == 'nan': point['sleep']['summary']['minutesAsleep'] = 'nan'
    else: point['sleep']['summary']['minutesAsleep'] = '1000'
    raw = asyncio.run(client.get_sleep_session(day))
    assert raw['sleep_duration_available'] is False
    result = asyncio.run(_compute_real_sleep(client, day, calculate_sleep_need(50), 30))
    assert result.score is None
    assert result.efficiency_pct is None
