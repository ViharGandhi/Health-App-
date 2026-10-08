import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request, Response

from test_dynamic_sync import fixture, NOW
from test_sleep_sync import night
from dynamic_sync import sync_dynamic
from main import _prepare_sleep_pages, sleep_consistency_score_endpoint, recovery_endpoint


def request(path='/api/data/sync'):
    return Request({'type': 'http', 'method': 'GET', 'path': path, 'query_string': b'',
                    'headers': [(b'x-user-date', b'2026-10-08'), (b'x-user-timezone', b'UTC'),
                                (b'x-user-age', b'22')], 'state': {}})


def test_all_sleep_views_prepared_before_daily_ready_and_reused_after_restart(tmp_path):
    async def run():
        client = fixture(tmp_path / 'health.db')
        client._fetch_points.side_effect = lambda kind, expression, **kwargs: [night()] if kind == 'sleep' else []
        client.get_health_user_id = AsyncMock(side_effect=AssertionError('unexpected identity download'))
        with patch('main.get_session', return_value={'health_user_id': 'user'}), \
             patch('main._get_token', AsyncMock(return_value='token')), \
             patch('main.GoogleHealthClient', return_value=client):
            result = await sync_dynamic(client, 'first', True, now=NOW, age=22,
                                        prepare_sleep=lambda: _prepare_sleep_pages(request()))
            assert result['sleep_updated']
            assert client.store.sleep_day_prepared(client.account_key, NOW.date())
            with client.store.connection() as conn, conn:
                assert conn.execute('SELECT COUNT(*) FROM page_snapshots').fetchone()[0] >= 28
                conn.execute('UPDATE page_snapshots SET updated=0')
            from health_read_store import HealthReadStore
            client.store = HealthReadStore(client.store.path)
            client._fetch_points.side_effect = AssertionError('unexpected remote fetch')
            with patch('main.build_consistency_scores', side_effect=AssertionError('unexpected recalculation')), \
                 patch('main._compute_connected_recovery', AsyncMock(side_effect=AssertionError('unexpected recalculation'))):
                response = Response()
                await sleep_consistency_score_endpoint(request=request('/api/sleep/consistency/score'), response=response)
                assert response.headers['X-Data-Cache'] == 'hit'
                response = Response()
                await recovery_endpoint(request=request('/api/recovery'), response=response, demo='estimate')
                assert response.headers['X-Data-Cache'] == 'hit'
    asyncio.run(run())


def test_failed_preparation_does_not_freeze_day_or_advance_sync(tmp_path):
    async def run():
        client = fixture(tmp_path / 'health.db')
        client._fetch_points.side_effect = lambda kind, expression, **kwargs: [night()] if kind == 'sleep' else []
        prepare = AsyncMock(side_effect=RuntimeError('calculation failed'))
        with pytest.raises(RuntimeError):
            await sync_dynamic(client, 'first', True, now=NOW, age=22, prepare_sleep=prepare)
        assert client.store.sleep_day_saved(client.account_key, NOW.date())
        assert not client.store.sleep_day_prepared(client.account_key, NOW.date())
        assert client.store.dynamic_status(client.account_key)['cursor'] is None
        client._fetch_points.reset_mock()
        prepare.side_effect = None
        assert (await sync_dynamic(client, 'first', True, now=NOW, age=22, prepare_sleep=prepare))['sleep_updated']
        assert client.store.sleep_day_prepared(client.account_key, NOW.date())
        assert [c.args[0] for c in client._fetch_points.await_args_list] == ['heart-rate', 'exercise']
    asyncio.run(run())
