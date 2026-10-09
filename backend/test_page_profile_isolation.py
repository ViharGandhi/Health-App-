import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from fastapi import Request, Response

from health_read_store import HealthReadStore
from main import _cached_data_page


def test_two_accounts_and_profile_inputs_never_share_page_results(tmp_path):
    async def run():
        store = HealthReadStore(tmp_path / 'profiles.db')
        calls = []
        async def compute(request, response):
            identity = request.headers['account']
            result = dict(account=identity, age=request.headers['x-user-age'],
                          sex=request.headers['x-user-sex'], zone=request.headers['x-user-timezone'],
                          day=request.headers['x-user-date'], query=request.url.query)
            calls.append(result)
            return result
        def client(token, request):
            return SimpleNamespace(store=store, account_key=request.headers['account'],
                strain_timezone=ZoneInfo(request.headers['x-user-timezone']),
                strain_sex=request.headers['x-user-sex'], strain_sex_defaulted=False)
        specs = [('a', '30', 'm', 'UTC', '2026-10-07', ''),
                 ('b', '30', 'm', 'UTC', '2026-10-07', ''),
                 ('a', '70', 'm', 'UTC', '2026-10-07', ''),
                 ('a', '30', 'f', 'UTC', '2026-10-07', ''),
                 ('a', '30', 'm', 'Etc/GMT+8', '2026-10-07', ''),
                 ('a', '30', 'm', 'UTC', '2026-10-06', ''),
                 ('a', '30', 'm', 'UTC', '2026-10-07', 'demo=estimate')]
        wrapped = _cached_data_page(compute)
        with patch('main.get_session', return_value={'health_user_id': 'fixture'}), \
             patch('main._get_token', AsyncMock(return_value='synthetic')), patch('main._google_client', client):
            for account, age, sex, zone, day, query in specs:
                headers = dict(account=account, **{'x-user-age': age, 'x-user-sex': sex,
                    'x-user-timezone': zone, 'x-user-date': day})
                request = Request(dict(type='http', method='GET', path='/api/strain',
                    query_string=query.encode(), headers=[(k.encode(), v.encode()) for k, v in headers.items()]))
                response = Response()
                value = await wrapped(request=request, response=response)
                assert value == dict(account=account, age=age, sex=sex, zone=zone, day=day, query=query)
                assert response.headers['X-Data-Cache'] == 'miss'
                assert await wrapped(request=request, response=Response()) == value
        assert len(calls) == len(specs)
    asyncio.run(asyncio.wait_for(run(), 10))
