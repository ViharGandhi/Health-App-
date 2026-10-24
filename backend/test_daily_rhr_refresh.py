import asyncio
from datetime import timedelta

from dynamic_sync import sync_dynamic
from health_read_store import read_range
from test_dynamic_sync import fixture, NOW


def test_force_sync_never_refetches_rhr_after_main_sleep_is_locked(tmp_path):
    async def run():
        client = fixture(tmp_path / 'health.db')
        query = read_range('daily_resting_heart_rate.date >= "2026-10-08" AND daily_resting_heart_rate.date < "2026-10-09"')
        def reading(value):
            return [{'dailyRestingHeartRate': {'date': {'year': 2026, 'month': 10, 'day': 8}, 'beatsPerMinute': str(value)}}]
        client.store.range_write(client.account_key, 'daily-resting-heart-rate', query, True, reading(70))
        client.store.finish_sleep_day(client.account_key, NOW.date(), 'main-sleep', 0, {'value': 64.79})
        client._fetch_points.side_effect = lambda kind, *args, **kwargs: reading(63) if kind == 'daily-resting-heart-rate' else []
        await sync_dynamic(client, 'refresh', True, now=NOW + timedelta(minutes=20), age=22)
        assert await client.get_resting_heart_rate(NOW.date()) == 64.79
        assert (await client.get_health_history(NOW.date(), NOW.date(), ('rhr',)))['rhr'][0]['value'] == 64.79
        assert 'daily-resting-heart-rate' not in [call.args[0] for call in client._fetch_points.await_args_list]
        frozen = client.store.sleep_rhr_points(client.account_key, query)
        assert frozen[0]['dailyRestingHeartRate']['beatsPerMinute'] == 64.79
    asyncio.run(run())
