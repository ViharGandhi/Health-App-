import asyncio
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import Response
import pytest
from health_read_store import HealthReadStore, CacheInvalidated
from page_snapshots import cached_page_result


def test_authenticated_route_reload_uses_snapshot_and_explicit_refresh_bypasses_it():
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from google_health_client import GoogleHealthClient
    from main import app, compute_mock_strain
    with tempfile.TemporaryDirectory() as directory:
        store = HealthReadStore(Path(directory) / 'health.sqlite3')
        client = GoogleHealthClient('fixture', cache=True, account_id='fixture', store=store)
        calculation = AsyncMock(return_value=compute_mock_strain())
        with patch('main.get_session', return_value={'user_email': 'fixture@example.test'}), \
             patch('main._get_token', AsyncMock(return_value='fixture')), \
             patch('main.GoogleHealthClient', return_value=client), \
             patch('main._compute_real_strain', calculation), \
             patch('main._compute_connected_recovery', AsyncMock(return_value=SimpleNamespace(score=60))):
            with TestClient(app) as browser:
                first = browser.get('/api/strain', headers={'X-User-Age': '22'})
                second = browser.get('/api/strain', headers={'X-User-Age': '22'})
                assert first.status_code == second.status_code == 200
                assert first.json() == second.json()
                assert second.headers['X-Data-Cache'] == 'hit'
                assert calculation.await_count == 1
                assert browser.get('/api/strain', headers={'X-User-Age': 'invalid'}).status_code == 400
                assert browser.post('/api/data/refresh').status_code == 200
                assert browser.get('/api/strain', headers={'X-User-Age': '22'}).headers['X-Data-Cache'] == 'miss'
                assert calculation.await_count == 2


def test_snapshot_survives_restart_and_stale_page_does_not_wait_for_calculation():
    async def run():
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'health.sqlite3'
            store = HealthReadStore(path)
            client = SimpleNamespace(store=store, account_key='user')
            compute = AsyncMock(return_value={'strain': 8})
            assert await cached_page_result(client, 'page', '/api/strain', Response(), compute) == {'strain': 8}
            client.store = HealthReadStore(path)
            assert await cached_page_result(client, 'page', '/api/strain', Response(), compute) == {'strain': 8}
            compute.assert_awaited_once()
            store.snapshot_write('user', 'page', {'strain': 8}, store.epoch('user'), now=time.time() - 121)
            started, release = asyncio.Event(), asyncio.Event()
            async def delayed():
                started.set()
                await release.wait()
                return {'strain': 9}
            response = Response()
            assert await cached_page_result(client, 'page', '/api/strain', response, delayed) == {'strain': 8}
            assert response.headers['X-Data-Cache'] == 'stale'
            await started.wait()
            # Another reload shares the pending refresh and still returns saved data.
            unused = AsyncMock(side_effect=AssertionError('duplicate calculation'))
            assert await cached_page_result(client, 'page', '/api/strain', Response(), unused) == {'strain': 8}
            release.set()
            from page_snapshots import _jobs
            await asyncio.gather(*list(_jobs.values()))
            assert store.snapshot_read('user', 'page')[1] == {'strain': 9}
            assert store.snapshot_read('other', 'page') is None
            store.expire_recent('user')
            assert store.snapshot_read('user', 'page') is None
            with pytest.raises(CacheInvalidated):
                store.snapshot_write('user', 'page', {'strain': 1}, 0)
    asyncio.run(asyncio.wait_for(run(), 10))


def test_failed_calculation_is_not_cached():
    async def run():
        with tempfile.TemporaryDirectory() as directory:
            store = HealthReadStore(Path(directory) / 'health.sqlite3')
            client = SimpleNamespace(store=store, account_key='user')
            compute = AsyncMock(side_effect=RuntimeError('failed'))
            with pytest.raises(RuntimeError):
                await cached_page_result(client, 'page', '/api/strain', Response(), compute)
            assert store.snapshot_read('user', 'page') is None
    asyncio.run(asyncio.wait_for(run(), 10))
