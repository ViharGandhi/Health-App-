import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from google_health_client import GoogleHealthClient, _transient_heart
from health_read_store import HealthReadStore
from previous_day_sync import sync_previous_day
from strain import StrainConfig
from strain_service import load_strain_days, finalized_key


TODAY = date(2026, 10, 17)
NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def fixture(tmp_path):
    client = GoogleHealthClient('test', cache=True, account_id='previous-day-test', store=HealthReadStore(tmp_path/'cache.sqlite3'))
    client.strain_timezone = timezone.utc
    client.strain_sex, client.strain_sex_defaulted = 'm', False
    client.stored_only = True
    heart = [{'heartRate': {'beatsPerMinute': 120, 'sampleTime': {
        'physicalTime': (datetime(2026, 10, 16, tzinfo=timezone.utc)+timedelta(minutes=i)).isoformat(), 'utcOffset': '0s'}}}
        for i in range(1440)]
    client._fetch_points = AsyncMock(side_effect=lambda kind, expression, **kw: heart if kind == 'heart-rate' else [])
    client._fetch_daily_steps = AsyncMock(return_value={TODAY-timedelta(days=1): 1234})
    return client


def test_yesterday_survives_restart_and_invalidation_without_daytime_rows(tmp_path):
    async def run():
        client = fixture(tmp_path)
        config = StrainConfig()
        with patch('previous_day_sync.sync_sleep_day', AsyncMock(return_value=False)):
            assert await sync_previous_day(client, TODAY, NOW, 22, config)
        calls = client._fetch_points.await_args_list
        assert calls[0].args[0] == 'heart-rate'
        assert '2026-10-16' in calls[0].args[1]
        assert '2026-10-17' in calls[0].args[1]
        assert not _transient_heart[client.account_key][1]
        with client.store.connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM read_points WHERE kind='heart-rate'").fetchone()[0] == 0
            client.store._invalidate_days(conn, client.account_key)
            conn.commit()
        client._fetch_points.side_effect = AssertionError('completed yesterday fetched again')
        assert not await sync_previous_day(client, TODAY, NOW, 22, config)
        restarted = fixture(tmp_path)
        restarted._fetch_points.side_effect = AssertionError('page requested network')
        values, _ = await load_strain_days(restarted, TODAY-timedelta(days=1), TODAY, NOW, 22, config)
        yesterday = values[TODAY-timedelta(days=1)]
        assert yesterday['strain'] is not None and yesterday['coverage'] > 0
        from sleep_need_inputs import SleepNeedInputs
        need = SleepNeedInputs({}, {TODAY-timedelta(days=1): yesterday['strain']/21*100}, {}).for_tonight(TODAY-timedelta(days=1))
        assert need is not None and need.total_need_min > 0
    asyncio.run(run())


def test_empty_yesterday_is_retryable_and_never_saved_as_zero(tmp_path):
    async def run():
        client = fixture(tmp_path)
        client._fetch_points.return_value = []
        client._fetch_points.side_effect = None
        with patch('previous_day_sync.sync_sleep_day', AsyncMock(return_value=False)):
            assert not await sync_previous_day(client, TODAY, NOW, 22)
        key = finalized_key(client, TODAY-timedelta(days=1), 22, StrainConfig())
        assert not client.store.days_read(client.account_key, [key])
    asyncio.run(run())


def test_separate_yesterday_finalization_is_not_repeated_by_foreground_sync(tmp_path):
    from dynamic_sync import sync_dynamic
    async def run():
        client = fixture(tmp_path)
        yesterday_points = client._fetch_points.side_effect('heart-rate', '')
        today_points = [{'heartRate': {'beatsPerMinute': 100, 'sampleTime': {
            'physicalTime': (datetime(2026, 10, 17, tzinfo=timezone.utc)+timedelta(minutes=i)).isoformat(), 'utcOffset': '0s'}}}
            for i in range(720)]
        def fetch(kind, expression, **kwargs):
            if kind != 'heart-rate':
                return []
            return yesterday_points if '2026-10-16T00:00:00' in expression else today_points
        client._fetch_points.side_effect = fetch
        with patch('previous_day_sync.sync_sleep_day', AsyncMock(return_value=False)):
            assert await sync_previous_day(client, TODAY, NOW, 22)
        client._fetch_points.reset_mock()
        with patch('dynamic_sync.sync_sleep_day', AsyncMock(return_value=False)):
            result = await sync_dynamic(client, 'first-open', True, now=NOW, age=22)
        assert result['synced'] and not result['sleep_updated']
        hearts = [c.args[1] for c in client._fetch_points.await_args_list if c.args[0] == 'heart-rate']
        assert len(hearts) == 1
        assert '2026-10-17T00:00:00' in hearts[0]
        values, _ = await load_strain_days(client, TODAY-timedelta(days=1), TODAY, NOW, 22)
        assert all(value['strain'] is not None and value['coverage'] > 0 for value in values.values())
        with client.store.connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM read_points WHERE kind='heart-rate'").fetchone()[0] == 0
    asyncio.run(run())
