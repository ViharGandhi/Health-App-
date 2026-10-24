import asyncio
from datetime import date
import pytest

from google_health_client import GoogleHealthClient
from health_read_store import HealthReadStore, read_range


@pytest.mark.parametrize('saved', [55, None])
def test_main_sleep_rhr_survives_nap_refresh_and_restart(tmp_path, saved):
    async def run():
        path = tmp_path / 'health.db'
        store = HealthReadStore(path)
        client = GoogleHealthClient('token', cache=True, account_id='user', store=store)
        client.stored_only = True
        day = date(2026, 10, 8)
        query = read_range('daily_resting_heart_rate.date >= "2026-10-08" AND daily_resting_heart_rate.date < "2026-10-09"')
        def reading(bpm):
            return [{'dailyRestingHeartRate': {'date': {'year': 2026, 'month': 10, 'day': 8}, 'beatsPerMinute': bpm}}]
        store.range_write(client.account_key, 'daily-resting-heart-rate', query, True, reading(saved) if saved else [])
        store.finish_sleep_day(client.account_key, day, 'main-sleep', 0, {'value': saved})
        store.range_write(client.account_key, 'daily-resting-heart-rate', query, True, reading(68))
        client.store = HealthReadStore(path)
        assert await client.get_resting_heart_rate(day) == saved
        history = await client.get_health_history(day, day, ('rhr',))
        assert [point['value'] for point in history['rhr']] == ([saved] if saved else [])
        frozen = client.store.sleep_rhr_points(client.account_key, query)
        assert [p['dailyRestingHeartRate']['beatsPerMinute'] for p in frozen] == ([saved] if saved else [])
        # Another account must still see its own daily reading.
        other = GoogleHealthClient('token', cache=True, account_id='other', store=client.store)
        other.stored_only = True
        store.range_write(other.account_key, 'daily-resting-heart-rate', query, True, reading(70))
        store.save_sleep_rhr(other.account_key, day, 'other-sleep', {'value': 70}, 0)
        assert await other.get_resting_heart_rate(day) == 70
    asyncio.run(run())
