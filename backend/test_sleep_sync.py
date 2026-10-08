import asyncio
from datetime import timedelta

import pytest

from test_dynamic_sync import fixture, NOW
from dynamic_sync import sync_dynamic
from sleep_sync import sync_sleep_day


def night(day='2026-10-08', **metadata):
    return {'name': 'sleep/' + day, 'sleep': {
        'interval': {'startTime': day + 'T01:00:00Z', 'endTime': day + 'T07:00:00Z',
                     'startUtcOffset': '0s', 'endUtcOffset': '0s'},
        'metadata': {'mainSleep': True, 'processed': True, **metadata},
        'summary': {'minutesAsleep': 350}}}


def test_first_visit_saves_sleep_and_daily_lock_survives_restart(tmp_path):
    async def run():
        path = tmp_path / 'health.db'
        client = fixture(path)
        async def fetch(kind, expression, **kwargs):
            if kind == 'sleep':
                return [night()]
            if kind == 'daily-heart-rate-variability':
                return [{'dailyHeartRateVariability': {'date': {'year': 2026, 'month': 10, 'day': 8},
                         'averageHeartRateVariabilityMilliseconds': 65}}]
            if kind == 'daily-resting-heart-rate':
                return [{'dailyRestingHeartRate': {'date': {'year': 2026, 'month': 10, 'day': 8},
                         'beatsPerMinute': 55}}]
            return []
        client._fetch_points.side_effect = fetch
        result = await sync_dynamic(client, 'first', True, now=NOW, age=22)
        assert result['sleep_updated']
        kinds = [c.args[0] for c in client._fetch_points.await_args_list]
        assert kinds.count('sleep') == 1
        assert kinds.count('heart-rate') == 1  # Dynamic coverage already contains the sleep.
        assert set(kinds) == {'heart-rate', 'exercise', 'sleep', 'daily-heart-rate-variability',
                              'daily-resting-heart-rate', 'daily-respiratory-rate',
                              'daily-sleep-temperature-derivations', 'heart-rate-variability'}
        assert await client.get_sleep_session(NOW.date()) is not None
        assert len(await client.get_sleep_stage_points(NOW.date(), NOW.date())) == 1
        client._fetch_points.side_effect = AssertionError('page attempted a remote read')
        assert await client.get_daily_hrv(NOW.date()) == 65
        assert await client.get_resting_heart_rate(NOW.date()) == 55
        restarted = fixture(path)
        result = await sync_dynamic(restarted, 'second', True, now=NOW + timedelta(minutes=2), age=22)
        assert not result['sleep_updated']
        assert [c.args[0] for c in restarted._fetch_points.await_args_list] == ['heart-rate', 'exercise']
        assert restarted.store.dynamic_status(restarted.account_key)['sleep_revision'] == 1
    asyncio.run(run())


def test_overnight_readings_are_limited_to_sleep_and_reuse_dynamic_coverage(tmp_path):
    async def run():
        client = fixture(tmp_path / 'health.db')
        point = night()
        point['sleep']['interval']['startTime'] = '2026-10-07T23:00:00Z'
        client._fetch_points.side_effect = lambda kind, expression, **kwargs: [point] if kind == 'sleep' else []
        await sync_dynamic(client, 'first', True, now=NOW, age=22)
        heart = [c.args[1] for c in client._fetch_points.await_args_list if c.args[0] == 'heart-rate']
        assert len(heart) == 2
        from health_read_store import read_range
        gap = read_range(heart[1])
        assert gap.start == '2026-10-07T23:00:00.000000'
        assert gap.end == '2026-10-08T00:00:00.000000'
    asyncio.run(run())


@pytest.mark.parametrize('metadata', [{'nap': True}, {'processed': False}, {'mainSleep': False}])
def test_no_lock_or_recovery_reads_for_unrecognised_sleep(tmp_path, metadata):
    async def run():
        client = fixture(tmp_path / 'health.db')
        client._fetch_points.return_value = [night(**metadata)]
        assert not await sync_sleep_day(client, NOW.date(), NOW, 0)
        assert client._fetch_points.await_count == 1
        assert not client.store.sleep_day_saved(client.account_key, NOW.date())
    asyncio.run(run())


def test_failure_retries_without_daily_lock_and_next_day_checks_again(tmp_path):
    async def run():
        client = fixture(tmp_path / 'health.db')
        async def fetch(kind, expression, **kwargs):
            if kind == 'sleep':
                return [night()]
            raise RuntimeError('offline')
        client._fetch_points.side_effect = fetch
        with pytest.raises(RuntimeError):
            await sync_sleep_day(client, NOW.date(), NOW, 0)
        assert not client.store.sleep_day_saved(client.account_key, NOW.date())
        client._fetch_points.side_effect = lambda kind, expression, **kwargs: [night()] if kind == 'sleep' else []
        assert await sync_sleep_day(client, NOW.date(), NOW, 0)
        client._fetch_points.reset_mock()
        assert not await sync_sleep_day(client, NOW.date(), NOW, 0)
        client._fetch_points.assert_not_awaited()
        client._fetch_points.side_effect = None
        client._fetch_points.return_value = []
        assert not await sync_sleep_day(client, NOW.date() + timedelta(days=1), NOW + timedelta(days=1), 0)
        assert client._fetch_points.await_count == 1
    asyncio.run(run())
