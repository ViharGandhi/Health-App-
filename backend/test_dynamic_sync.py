"""Check strict HR deltas, allowed fetches, cadence and durable checkpoints."""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock

import pytest
from main import STRAIN_CONFIG
from dynamic_sync import sync_dynamic
from google_health_client import GoogleHealthClient
from health_read_store import HealthReadStore, read_range

NOW = datetime(2026, 10, 8, 11, tzinfo=timezone.utc)


def fixture(path):
    client = GoogleHealthClient('token', cache=True, account_id='user', store=HealthReadStore(path))
    client.strain_timezone = timezone.utc
    client.strain_sex, client.strain_sex_defaulted = 'm', True
    client.stored_only = True
    client._fetch_points = AsyncMock(return_value=[])
    client._fetch_daily_steps = AsyncMock(return_value={NOW.date(): 1234})
    return client


def test_session_force_delta_and_fifteen_minute_gate_survive_restart():
    async def run():
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'health.sqlite3'
            client = fixture(path)
            result = await sync_dynamic(client, 'visit-one', True, now=NOW, age=22, config=STRAIN_CONFIG)
            assert result['synced']
            calls = client._fetch_points.await_args_list
            assert [call.args[0] for call in calls] == ['heart-rate', 'exercise', 'sleep']
            query = read_range(calls[0].args[1])
            assert query.start == '2026-10-08T00:00:00.000000'
            assert query.end == '2026-10-08T11:00:00.000000'
            assert client._fetch_daily_steps.await_args.args == (NOW.date(), NOW.date())
            assert not (await sync_dynamic(client, 'visit-one', True, now=NOW + timedelta(minutes=2)))['synced']
            assert not (await sync_dynamic(client, 'visit-one', now=NOW + timedelta(minutes=14)))['synced']
            assert client._fetch_points.await_count == 3
            restarted = fixture(path)
            assert (await sync_dynamic(restarted, 'visit-two', True, now=NOW + timedelta(minutes=2), age=22))['synced']
            query = read_range(restarted._fetch_points.await_args_list[0].args[1])
            assert query.start == '2026-10-08T11:00:00.000000'
            assert query.end == '2026-10-08T11:02:00.000000'
            assert not (await sync_dynamic(restarted, 'visit-two', now=NOW + timedelta(minutes=16)))['synced']
            assert (await sync_dynamic(restarted, 'visit-two', now=NOW + timedelta(minutes=17), age=22))['synced']
            assert restarted.store.stored_steps(restarted.account_key, NOW.date(), NOW.date()) == {'2026-10-08': 1234}
    asyncio.run(run())


def test_failure_does_not_advance_checkpoint_and_same_session_can_retry():
    async def run():
        with tempfile.TemporaryDirectory() as directory:
            client = fixture(Path(directory) / 'health.sqlite3')
            client._fetch_daily_steps.side_effect = RuntimeError('offline')
            with pytest.raises(RuntimeError):
                await sync_dynamic(client, 'visit', True, now=NOW)
            assert client.store.dynamic_status(client.account_key)['cursor'] is None
            client._fetch_daily_steps.side_effect = None
            assert (await sync_dynamic(client, 'visit', True, now=NOW, age=22))['synced']
    asyncio.run(run())


def test_stored_pages_use_incremental_points_without_any_remote_fetch():
    async def run():
        with tempfile.TemporaryDirectory() as directory:
            client = fixture(Path(directory) / 'health.sqlite3')
            point = {'heartRate': {'sampleTime': {'physicalTime': '2026-10-08T10:59:00Z',
                'utcOffset': '0s', 'civilTime': {'date': {'year': 2026, 'month': 10, 'day': 8},
                'time': {'hours': 10, 'minutes': 59}}}, 'beatsPerMinute': 120}}
            async def fetch(kind, expression, **kwargs):
                assert kind in ('heart-rate', 'exercise', 'sleep'), 'unexpected health-data fetch'
                return [point] if kind == 'heart-rate' else []
            client._fetch_points.side_effect = fetch
            await sync_dynamic(client, 'visit', True, now=NOW, age=22)
            client._fetch_points.side_effect = AssertionError('page attempted network read')
            assert len(await client.get_intraday_heart_rate(NOW.date(), preserve_offset=True)) == 1
            assert await client.get_daily_steps(NOW.date(), NOW.date()) == {NOW.date(): 1234}
            assert await client.get_health_history(NOW.date(), NOW.date(), ('rhr', 'hrv')) == {'hrv': [], 'rhr': []}
            assert await client.get_sleep_stage_points(NOW.date(), NOW.date()) == []
    asyncio.run(run())


def test_simultaneous_app_visits_share_one_sync():
    async def run():
        with tempfile.TemporaryDirectory() as directory:
            client = fixture(Path(directory) / 'health.sqlite3')
            first, second = await asyncio.gather(
                sync_dynamic(client, 'tab-one', True, now=NOW, age=22),
                sync_dynamic(client, 'tab-two', True, now=NOW, age=22))
            assert sum(result['synced'] for result in (first, second)) == 1
            assert second['data_updated']
            assert client._fetch_points.await_count == 3
            assert client._fetch_daily_steps.await_count == 1
            assert client.store.dynamic_status(client.account_key, 'tab-two')['session_seen']
    asyncio.run(run())


def test_unknown_schema_does_not_mark_window_as_processed():
    async def run():
        with tempfile.TemporaryDirectory() as directory:
            client = fixture(Path(directory) / 'health.sqlite3')
            client._fetch_points.return_value = [{'unsupported': True}]
            with pytest.raises(ValueError):
                await sync_dynamic(client, 'visit', True, now=NOW)
            assert client.store.dynamic_status(client.account_key)['cursor'] is None
    asyncio.run(run())


def test_home_visit_gate_is_independent_of_automatic_sync_and_survives_reload(tmp_path):
    async def run():
        path = tmp_path / 'health.db'
        client = fixture(path)
        assert (await sync_dynamic(client, 'tab', True, home_visit=True, now=NOW, age=22))['synced']
        assert not (await sync_dynamic(client, 'reload', True, home_visit=True, now=NOW + timedelta(minutes=7)))['synced']
        assert client.store.dynamic_status(client.account_key)['home_visit'] == NOW.timestamp()
        assert (await sync_dynamic(client, 'tab', now=NOW + timedelta(minutes=15), age=22))['synced']
        assert client.store.dynamic_status(client.account_key)['home_visit'] == NOW.timestamp()
        # A same-tab Home return qualifies even though the automatic sync was recent.
        assert (await sync_dynamic(client, 'tab', True, home_visit=True, now=NOW + timedelta(minutes=17), age=22))['synced']
        restarted = fixture(path)
        assert not (await sync_dynamic(restarted, 'new-tab', True, home_visit=True, now=NOW + timedelta(minutes=20)))['synced']
        assert (await sync_dynamic(restarted, 'new-tab', now=NOW + timedelta(minutes=32), age=22))['synced']
    asyncio.run(run())


def test_explicit_reload_force_refreshes_steps_inside_home_visit_window(tmp_path):
    async def run():
        client = fixture(tmp_path / 'health.db')
        await sync_dynamic(client, 'home', True, home_visit=True, now=NOW, age=22)
        client._fetch_daily_steps.return_value = {NOW.date(): 12915}
        assert (await sync_dynamic(client, 'reload', True, now=NOW + timedelta(minutes=1), age=22))['synced']
        assert client.store.stored_steps(client.account_key, NOW.date(), NOW.date()) == {'2026-10-08': 12915}
        assert client.store.dynamic_status(client.account_key)['home_visit'] == NOW.timestamp()
        assert not (await sync_dynamic(client, 'reload', True, now=NOW + timedelta(minutes=2)))['synced']
    asyncio.run(run())
