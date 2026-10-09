import asyncio
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

from google_health_client import GoogleHealthClient
from mock_sleep_stage_ranges import mock_stage_points
from sleep_heart_rate import build_sleep_heart_rate
from strain import clean_samples


DAY = date(2026, 10, 3)


def test_raw_strain_conflict_uses_first_arrival():
    start = datetime(2026, 10, 3, tzinfo=timezone.utc)
    points = [(start, 60.), (start, 80.)]
    window = {'start': start, 'end': start + timedelta(hours=1)}
    assert clean_samples(points, window)[0][1] == 60.
    assert clean_samples(list(reversed(points)), window)[0][1] == 80.


def test_daily_conflict_uses_last_arrival():
    def point(value):
        return {'dailyRestingHeartRate': {'date': {'year': DAY.year, 'month': DAY.month, 'day': DAY.day},
                                         'beatsPerMinute': value}}
    client = GoogleHealthClient('synthetic')
    points = [point(56), point(60)]
    client._points = AsyncMock(return_value=points)
    assert asyncio.run(client.get_health_history(DAY, DAY, ('rhr',)))['rhr'][0]['value'] == 60
    client._points = AsyncMock(return_value=list(reversed(points)))
    assert asyncio.run(client.get_health_history(DAY, DAY, ('rhr',)))['rhr'][0]['value'] == 56


def test_sleep_heart_rate_conflict_excludes_timestamp():
    sleep = mock_stage_points(DAY, 1)[0]
    interval = sleep['sleep']['interval']
    point = {'heartRate': {'sampleTime': {'physicalTime': interval['startTime'],
                                        'utcOffset': interval['startUtcOffset']}, 'beatsPerMinute': 60}}
    conflict = deepcopy(point)
    conflict['heartRate']['beatsPerMinute'] = 80
    assert build_sleep_heart_rate(sleep, [point, conflict], False)['samples'] == []
    assert build_sleep_heart_rate(sleep, [conflict, point], False)['samples'] == []
