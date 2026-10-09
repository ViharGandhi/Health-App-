import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from hypothesis import given, settings, strategies as st

from google_health_client import GoogleHealthClient, _valid_sleep_summary
from mock_sleep_stage_ranges import mock_stage_points
from sleep_heart_rate import build_sleep_heart_rate
from sleep_stress import adapt_google_hr, adapt_google_hrv


DAY = date(2026, 10, 7)


@pytest.mark.parametrize('adapter', ['stress_hr', 'stress_hrv', 'intraday_hr'])
@settings(max_examples=200, derandomize=True, deadline=None, database=None)
@given(st.booleans(), st.integers(0, 10000))
def test_sample_adapters_never_coerce_booleans_to_numbers(adapter, value, seconds):
    stamp = datetime(2026, 10, 7, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    hr = {'heartRate': {'sampleTime': {'physicalTime': stamp.isoformat(), 'utcOffset': '0s'},
                        'beatsPerMinute': value}}
    with pytest.raises(ValueError):
        if adapter == 'stress_hr':
            adapt_google_hr(hr)
        elif adapter == 'stress_hrv':
            def point(time):
                return {'heartRateVariability': {'sampleTime': {'physicalTime': time.isoformat()},
                    'rootMeanSquareOfSuccessiveDifferencesMilliseconds': value}}
            adapt_google_hrv([point(stamp), point(stamp + timedelta(minutes=5))], 'start')
        else:
            client = GoogleHealthClient('synthetic')
            client._points = AsyncMock(return_value=[hr])
            asyncio.run(client.get_intraday_heart_rate(DAY))


@pytest.mark.parametrize('value', [True, False])
def test_sleep_hr_chart_drops_boolean_readings(value):
    point = mock_stage_points(DAY, 1)[0]
    interval = point['sleep']['interval']
    hr = {'heartRate': {'sampleTime': {'physicalTime': interval['startTime'],
                                     'utcOffset': interval['startUtcOffset']}, 'beatsPerMinute': value}}
    result = build_sleep_heart_rate(point, [hr], False)
    assert result['samples'] == []
    assert result['status'] == 'no_readings'


@pytest.mark.parametrize('value', [True, False])
def test_summary_stage_count_rejects_boolean(value):
    assert not _valid_sleep_summary({'minutesAsleep': 470, 'stagesSummary': [
        {'type': 'DEEP', 'minutes': 90, 'count': value}]})
