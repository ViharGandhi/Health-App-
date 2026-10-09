import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

import httpx
import pytest
from hypothesis import given, settings

from google_health_client import GoogleHealthClient
from sleep_stage_pipeline import sync_stage_ranges
from sleep_analytics import sleep_observations
from mock_sleep_stage_ranges import mock_stage_points
from test_adapter_fuzz import payload, finite_tree


@pytest.mark.parametrize('adapter', ['points_response', 'steps_response', 'stage_pipeline', 'sleep_summary'])
@settings(max_examples=200, derandomize=True, deadline=None, database=None)
@given(payload)
def test_provider_response_and_pipeline_types_are_validated(adapter, value):
    async def run():
        client = GoogleHealthClient('synthetic')
        original = httpx.AsyncClient
        def respond(request):
            return httpx.Response(200, json=value)
        with patch('google_health_client.httpx.AsyncClient',
                   side_effect=lambda **kw: original(transport=httpx.MockTransport(respond), **kw)):
            if adapter == 'points_response':
                return await client._fetch_points('sleep', '')
            if adapter == 'steps_response':
                return await client._fetch_daily_steps(date(2026, 10, 7), date(2026, 10, 7))
        if adapter == 'stage_pipeline':
            client.get_sleep_stage_points = AsyncMock(return_value=[value])
            store = SimpleNamespace(has_sessions=lambda user: False, sync=lambda *a: None, results=lambda *a: [])
            return await sync_stage_ranges(client, 'synthetic', store, date(2026, 10, 7), date(2026, 10, 7))
        point = mock_stage_points(date(2026, 10, 7), 1)[0]
        point['sleep']['summary'] = value
        return sleep_observations([point], date(2026, 10, 7))
    try:
        result = asyncio.run(run())
    except ValueError:
        return
    finite_tree(result)


@pytest.mark.parametrize('adapter', ['points', 'steps'])
def test_repeated_pagination_token_stops_with_explicit_provider_error(adapter):
    async def run():
        client = GoogleHealthClient('synthetic')
        original = httpx.AsyncClient
        calls = []
        def respond(request):
            calls.append(request)
            assert len(calls) <= 3, 'Pagination did not detect lack of progress'
            return httpx.Response(200, json={'nextPageToken': 'synthetic-repeat'})
        with patch('google_health_client.httpx.AsyncClient',
                   side_effect=lambda **kw: original(transport=httpx.MockTransport(respond), **kw)):
            with pytest.raises(ValueError):
                if adapter == 'points':
                    await client._fetch_points('sleep', '')
                else:
                    await client._fetch_daily_steps(date(2026, 10, 7), date(2026, 10, 7))
    asyncio.run(run())
