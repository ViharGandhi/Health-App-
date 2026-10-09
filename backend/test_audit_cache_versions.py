import asyncio
import hashlib
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import Request, Response

from strain import StrainConfig
from strain_service import load_strain_days, _encode_day
from main import _cached_data_page, STRAIN_CONFIG
import pytest


def test_previous_strain_cache_cannot_bypass_corrected_rhr_gate():
    async def run():
        day = date(2026, 10, 7)
        config = StrainConfig()
        old = hashlib.sha256(repr(('strain-v1', 'UTC', 30, 'm', False, config)).encode()).hexdigest()
        stale = {'strain': 0., 'params': {'hr_rest': 1000.}, 'date': day,
                 'day_window': {'start': datetime(2026, 10, 7, tzinfo=timezone.utc), 'end': datetime(2026, 10, 8, tzinfo=timezone.utc)}}
        store = SimpleNamespace(days_read=lambda account, keys, **kw: {f'{old}:{day}': json.dumps(stale, default=_encode_day)},
            calculation_version=lambda account: 0, days_write=lambda *args: None)
        client = SimpleNamespace(store=store, account_key='synthetic', strain_timezone=timezone.utc,
                                 strain_sex='m', strain_sex_defaulted=False)
        fetch = AsyncMock(return_value=([], [], [], {day: 1000.}))
        with patch('strain_service.fetch_strain_inputs', fetch):
            values, _ = await load_strain_days(client, day, day, datetime(2026, 10, 9, tzinfo=timezone.utc), 30, config)
        assert values[day]['params']['hr_rest'] == 60.
        fetch.assert_awaited_once()
    asyncio.run(run())


@pytest.mark.parametrize('version', ['page-v4', 'page-v8'])
def test_updated_algorithms_use_new_page_snapshot_namespace(version):
    async def run():
        scope = {'type': 'http', 'method': 'GET', 'path': '/api/sleep', 'query_string': b'',
                 'headers': [(b'x-user-date', b'2026-10-07')]}
        request = Request(scope)
        store = SimpleNamespace(dynamic_status=lambda account: {}, sleep_day_prepared=lambda *args: True)
        client = SimpleNamespace(store=store, account_key='synthetic', strain_timezone=timezone.utc,
                                 strain_sex='m', strain_sex_defaulted=False)
        old_key = hashlib.sha256(json.dumps([version, '/api/sleep', [], '2026-10-07', None,
            'UTC', 'm', False, repr(STRAIN_CONFIG), 0, 0], default=str).encode()).hexdigest()
        async def cached(client, key, path, response, compute, **kw):
            return {'score': 81.5} if key == old_key else await compute()
        async def compute(request, response):
            return {'score': 84.7}
        with patch('main.get_session', return_value={'health_user_id': 'synthetic'}), \
             patch('main._get_token', AsyncMock(return_value='synthetic')), \
             patch('main._google_client', return_value=client), patch('main.cached_page_result', cached):
            result = await _cached_data_page(compute)(request=request, response=Response())
        assert result == {'score': 84.7}
    asyncio.run(run())
