"""A user-entered max heart rate replaces the age estimate in cardio Strain."""
import asyncio
from datetime import datetime, timedelta, timezone
import math
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from google_health_client import GoogleHealthClient
from strain import calculate_strain, sustained_peak
from strain_service import calculate_days, load_strain_days, _daily_cache


BASE = datetime(2026, 10, 5, 7, tzinfo=timezone.utc)
WINDOW = {'start': BASE, 'end': BASE + timedelta(hours=15), 'source': 'sleep'}


def steady(bpm=160, minutes=45, step_s=60, start=BASE):
    return [(start + timedelta(seconds=i * step_s), bpm) for i in range(minutes * 60 // step_s + 1)]


def calc(points, age=30, **kwargs):
    return calculate_strain(points, [], WINDOW, age, [56] * 7, 'm', **kwargs)


def test_personal_max_replaces_the_age_estimate():
    estimated, personal = calc(steady()), calc(steady(), hr_max=200)
    assert estimated['params']['hr_max'] == pytest.approx(187) and estimated['params']['hr_max_source'] == 'age_estimate'
    assert personal['params']['hr_max'] == 200 and personal['params']['hr_max_source'] == 'profile'
    hrr = (160 - 56) / (200 - 56)
    assert personal['load'] == pytest.approx(45 * hrr * .64 * math.exp(1.92 * hrr))
    assert personal['strain'] < estimated['strain']  # A higher ceiling makes the same effort relatively easier.


@pytest.mark.parametrize('value', [119, 231, float('nan'), float('inf')])
def test_personal_max_outside_range_is_rejected(value):
    with pytest.raises(ValueError):
        calc(steady(), hr_max=value)


def test_personal_max_does_not_substitute_for_missing_age():
    result = calc(steady(), age=None, hr_max=200)
    assert result['age_missing'] and result['strain'] is None
    assert result['params']['hr_max'] is None and result['params']['hr_max_source'] is None


def test_sustained_peak_needs_a_densely_sampled_minute():
    dense = steady(190, minutes=2, step_s=5)
    assert sustained_peak(dense) == pytest.approx(190)
    assert sustained_peak(dense[:5]) is None  # 20 seconds is not a held minute.
    assert sustained_peak(steady(190, minutes=10, step_s=60)) is None  # One reading a minute cannot show it.
    assert sustained_peak([]) is None


def test_peak_above_the_max_in_use_is_flagged_not_applied():
    points = steady(120, minutes=10, step_s=5) + steady(190, minutes=2, step_s=5, start=BASE + timedelta(minutes=11))
    flagged = calc(points)
    assert flagged['peak_hr_sustained'] == pytest.approx(190) and flagged['hr_max_exceeded']
    assert flagged['params']['hr_max'] == pytest.approx(187)  # The estimate is not raised automatically.
    assert not calc(points, hr_max=195)['hr_max_exceeded']


def test_day_cache_is_scoped_by_personal_max():
    _daily_cache.clear()
    day, now = BASE.date(), BASE + timedelta(days=1)
    inputs = (steady(), [], [], {})
    first = calculate_days(day, day, now, timezone.utc, 30, 'm', False, inputs, account='a')
    second = calculate_days(day, day, now, timezone.utc, 30, 'm', False, inputs, account='a', hr_max=200)
    assert first[day]['params']['hr_max_source'] == 'age_estimate' and second[day]['params']['hr_max'] == 200


class Store:
    def __init__(self):
        self.saved = {}

    def days_read(self, account, keys, now=None):
        return {key: self.saved[key] for key in keys if key in self.saved}

    def days_write(self, account, entries, version):
        self.saved.update({key: payload for key, _, payload in entries})

    def calculation_version(self, account):
        return 1


def test_personal_max_applies_from_today_and_keeps_saved_days():
    today, now = BASE.date(), BASE + timedelta(hours=14)
    client = type('Client', (), {})()
    client.account_key, client.store, client.strain_timezone = 'a', Store(), timezone.utc
    client.get_intraday_heart_rate = AsyncMock(return_value=steady() + steady(start=BASE - timedelta(days=1)))
    client.get_workout_sessions = AsyncMock(return_value=[])
    client.get_sleep_stage_points = AsyncMock(return_value=[])
    client.get_health_history = AsyncMock(return_value={})
    yesterday = today - timedelta(days=1)
    before, _ = asyncio.run(load_strain_days(client, yesterday, today, now, 30))
    client.strain_hr_max = 200
    after, _ = asyncio.run(load_strain_days(client, yesterday, today, now, 30))
    assert after[today]['params']['hr_max'] == 200 and after[today]['strain'] < before[today]['strain']
    assert after[yesterday]['strain'] == before[yesterday]['strain']
    assert after[yesterday]['params']['hr_max'] == pytest.approx(187)


def test_max_hr_header_is_validated_and_used():
    client = GoogleHealthClient('max-hr-fixture')
    client.get_intraday_heart_rate = AsyncMock(return_value=steady())
    client.get_workout_sessions = AsyncMock(return_value=[])
    client.get_sleep_stage_points = AsyncMock(return_value=[])
    client.get_health_history = AsyncMock(return_value={})
    with patch('main._get_token', AsyncMock(return_value='test')), patch('main.GoogleHealthClient', return_value=client), patch('main._compute_connected_recovery', AsyncMock(return_value=type('Recovery', (), {'score': None})())):
        headers = {'X-User-Age': '30', 'X-User-Sex': 'm'}
        result = TestClient(app).get('/api/strain?date=2026-10-05', headers={**headers, 'X-User-Max-HR': '200'}).json()
        assert result['params']['hr_max'] == 200 and result['params']['hr_max_source'] == 'profile'
        for bad in ('119', '231', 'abc', 'nan'):
            assert TestClient(app).get('/api/strain', headers={**headers, 'X-User-Max-HR': bad}).status_code == 400
