"""Approved physical-duration/ID contract replaces the reproduced disagreements."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from google_health_client import GoogleHealthClient
from sleep_heart_rate import select_sleep


def point(name, day, physical_minutes, asleep_minutes, main=True):
    end = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=9)
    return {'name': name, 'sleep': {'interval': {'startTime': (end - timedelta(minutes=physical_minutes)).isoformat(),
        'endTime': end.isoformat(), 'startUtcOffset': '0s', 'endUtcOffset': '0s'},
        'metadata': {'mainSleep': main, 'processed': True}, 'summary': {'minutesAsleep': asleep_minutes}}}


@pytest.mark.parametrize('day', [date(2026, 10, 7), date(2026, 10, 25), date(2026, 3, 29), date(2027, 3, 28), date(2027, 10, 31)])
def test_summary_and_segment_selection_use_physical_duration(day):
    points = [point('physical-longest', day, 540, 400), point('asleep-longest', day, 480, 450)]
    client = GoogleHealthClient('synthetic')
    client._points = AsyncMock(return_value=points)
    summary = asyncio.run(client.get_sleep_session(day))
    selected = select_sleep(points, day, now=datetime(2028, 1, 1, tzinfo=timezone.utc))
    assert summary['total_duration'] == 400 * 60
    assert selected['name'] == 'physical-longest'


def test_unspecified_fallback_remains_eligible_with_secondary_sessions():
    day = date(2026, 10, 7)
    points = [point('explicit-secondary', day, 540, 450, False), point('unspecified', day, 480, 400, None)]
    client = GoogleHealthClient('synthetic')
    client._points = AsyncMock(return_value=points)
    assert asyncio.run(client.get_sleep_session(day))['total_duration'] == 400 * 60
    assert select_sleep(points, day)['name'] == 'unspecified'


def test_equal_summary_lengths_are_permutation_invariant():
    day = date(2026, 10, 7)
    points = [point('a', day, 540, 450), point('b', day, 480, 450)]
    client = GoogleHealthClient('synthetic')
    client._points = AsyncMock(return_value=points)
    first = asyncio.run(client.get_sleep_session(day))
    client._points.return_value = list(reversed(points))
    second = asyncio.run(client.get_sleep_session(day))
    assert first['sleep_start_time'] == second['sleep_start_time']


def test_equal_physical_lengths_use_stable_id():
    day = date(2026, 10, 7)
    points = [point('a', day, 540, 400), point('b', day, 540, 450)]
    client = GoogleHealthClient('synthetic')
    client._points = AsyncMock(return_value=list(reversed(points)))
    assert asyncio.run(client.get_sleep_session(day))['sleep_id'] == 'b'
