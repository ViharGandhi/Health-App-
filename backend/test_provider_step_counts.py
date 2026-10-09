import asyncio
from datetime import date
from unittest.mock import patch

import httpx
import pytest
from hypothesis import given, settings, strategies as st

from google_health_client import GoogleHealthClient
from health_read_store import HealthReadStore, exact_key


@settings(max_examples=200, derandomize=True, deadline=None, database=None)
@given(st.one_of(st.booleans(), st.integers(max_value=-1),
                 st.floats(0.01, 0.99, allow_nan=False, allow_infinity=False)))
def test_invalid_step_count_is_rejected_instead_of_truncated(value):
    day = date(2026, 10, 7)
    payload = {'rollupDataPoints': [{'civilStartTime': {'date': {'year': 2026, 'month': 10, 'day': 7}},
                                   'steps': {'countSum': value}}]}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    real_client = httpx.AsyncClient
    with patch('google_health_client.httpx.AsyncClient', lambda **kwargs: real_client(transport=transport, **kwargs)):
        with pytest.raises(ValueError):
            asyncio.run(GoogleHealthClient('synthetic')._fetch_daily_steps(day, day))


@pytest.mark.parametrize('value', [0, '0', 123, '123'])
def test_zero_and_provider_integer_strings_are_valid(value):
    day = date(2026, 10, 7)
    payload = {'rollupDataPoints': [{'civilStartTime': {'date': {'year': 2026, 'month': 10, 'day': 7}},
                                   'steps': {'countSum': value}}]}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    real_client = httpx.AsyncClient
    with patch('google_health_client.httpx.AsyncClient', lambda **kwargs: real_client(transport=transport, **kwargs)):
        assert asyncio.run(GoogleHealthClient('synthetic')._fetch_daily_steps(day, day)) == {day: int(value)}


def test_previous_rollup_cache_cannot_bypass_validation(tmp_path):
    from unittest.mock import AsyncMock
    day = date(2026, 10, 7)
    store = HealthReadStore(tmp_path / 'steps.db')
    client = GoogleHealthClient('synthetic', cache=True, account_id='fixture', store=store)
    store.exact_write(client.account_key, exact_key('steps-rollup', f'{day}/{day}', True), {str(day): -1})
    client._fetch_daily_steps = AsyncMock(return_value={day: 0})
    assert asyncio.run(client.get_daily_steps(day, day)) == {day: 0}
    client._fetch_daily_steps.assert_awaited_once()


def test_stored_only_excludes_invalid_historical_counts(tmp_path):
    day = date(2026, 10, 7)
    store = HealthReadStore(tmp_path / 'stored-steps.db')
    client = GoogleHealthClient('synthetic', cache=True, account_id='fixture', store=store)
    store.exact_write(client.account_key, exact_key('steps-rollup', f'{day}/{day}', True), {str(day): -1})
    client.stored_only = True
    assert asyncio.run(client.get_daily_steps(day, day)) == {}
