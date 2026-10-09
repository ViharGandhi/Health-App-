import asyncio
from copy import deepcopy
from datetime import date

import pytest

from main import _compute_real_sleep
from mock_recovery import MockRecoveryClient
from sleep_need import calculate_sleep_need


@pytest.mark.parametrize('field,value', [('minutesAsleep', 'junk'), ('minutesAsleep', None),
    ('minutesAwake', None), ('minutesInSleepPeriod', 'nan'), ('minutesAwake', '-1'),
    ('minutesToFallAsleep', 'nan'), ('stagesSummary', None),
    ('stagesSummary', [{'type': 'DEEP', 'minutes': 'nan'}]),
    ('stagesSummary', [{'type': 'DEEP', 'minutes': '-1'}])])
def test_invalid_summary_never_crashes_or_produces_score(field, value):
    day = date(2026, 10, 7)
    client = MockRecoveryClient(day)
    point = next(p for p in client.points['sleep'] if p['name'] == f'demo-main-{day}')
    point['sleep']['summary'][field] = deepcopy(value)
    result = asyncio.run(_compute_real_sleep(client, day, calculate_sleep_need(50), 30))
    assert result.score is None
    assert result.status_reason


def test_physical_sleep_over_twenty_four_hours_is_unavailable():
    day = date(2026, 10, 7)
    client = MockRecoveryClient(day)
    point = next(p for p in client.points['sleep'] if p['name'] == f'demo-main-{day}')
    point['sleep']['interval']['startTime'] = '2026-10-05T00:00:00Z'
    point['sleep']['summary']['minutesAsleep'] = '1800'
    result = asyncio.run(_compute_real_sleep(client, day, calculate_sleep_need(50), 30))
    assert result.score is None
