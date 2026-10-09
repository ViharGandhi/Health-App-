"""Raw daily adapters must fail with explicit validation errors, never parser crashes."""
import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest
from hypothesis import given, settings, strategies as st

from google_health_client import GoogleHealthClient
from test_adapter_fuzz import payload, finite_tree


DAY = date(2026, 10, 7)
RECIPES = {
    'daily_hrv': lambda c: c.get_daily_hrv(DAY),
    'deep_hrv': lambda c: c.get_deep_sleep_hrv(DAY),
    'rhr': lambda c: c.get_resting_heart_rate(DAY),
    'hrv_history': lambda c: c.get_hrv_history(),
    'health_history': lambda c: c.get_health_history(DAY, DAY),
    'intraday_hr': lambda c: c.get_intraday_heart_rate(DAY, preserve_offset=True),
    'workouts': lambda c: c.get_workout_sessions(DAY, preserve_offset=True),
    'naps': lambda c: c.get_nap_minutes_history(DAY, DAY),
    'sleep_records': lambda c: c._sleep_records(DAY, DAY),
}


@pytest.mark.parametrize('adapter', RECIPES)
@settings(max_examples=200, derandomize=True, deadline=None, database=None)
@given(payload)
def test_daily_provider_adapters_validate_types(adapter, value):
    async def run():
        client = GoogleHealthClient('synthetic')
        client._points = AsyncMock(return_value=[value])
        try:
            result = await RECIPES[adapter](client)
        except ValueError:
            return
        finite_tree(result)
    asyncio.run(run())


def test_physical_provider_timestamp_requires_offset():
    from google_health_client import _local_datetime
    with pytest.raises(ValueError):
        _local_datetime('2026-10-07T00:00:00', '0s')


@pytest.mark.parametrize('adapter,field,key', [
    ('daily_hrv', 'dailyHeartRateVariability', 'averageHeartRateVariabilityMilliseconds'),
    ('deep_hrv', 'dailyHeartRateVariability', 'deepSleepRootMeanSquareOfSuccessiveDifferencesMilliseconds'),
    ('rhr', 'dailyRestingHeartRate', 'beatsPerMinute'),
])
@settings(max_examples=200, derandomize=True, deadline=None, database=None)
@given(st.one_of(st.booleans(), st.floats(), st.text(max_size=20), st.integers()))
def test_daily_scalar_outputs_are_finite_and_not_boolean(adapter, field, key, value):
    async def run():
        client = GoogleHealthClient('synthetic')
        client._points = AsyncMock(return_value=[{field: {key: value}}])
        try:
            result = await RECIPES[adapter](client)
        except ValueError:
            return
        if isinstance(value, bool):
            assert result is None
        finite_tree(result)
    asyncio.run(run())
