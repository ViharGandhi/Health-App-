import asyncio

from google_health_client import GoogleHealthClient
from health_read_store import HealthReadStore, read_range


def test_vo2_date_range_is_parsed():
    query = read_range('daily_vo2_max.date >= "2026-10-01" AND daily_vo2_max.date < "2026-10-08"')
    assert query is not None
    assert query.field == 'daily_vo2_max.date'


def test_stored_only_vo2_trend_uses_indexed_range(tmp_path):
    expression = 'daily_vo2_max.date >= "2026-10-01" AND daily_vo2_max.date < "2026-10-08"'
    store = HealthReadStore(tmp_path / 'health.db')
    client = GoogleHealthClient('synthetic', cache=True, account_id='synthetic', store=store)
    client.stored_only = True
    from health_read_store import ReadRange, clock
    query = ReadRange('daily_vo2_max.date', clock('2026-10-01'), clock('2026-10-08'))
    point = {'dailyVo2Max': {'date': {'year': 2026, 'month': 10, 'day': 7}, 'vo2Max': 44.5}}
    store.range_write(client.account_key, 'daily-vo2-max', query, True, [point])
    assert asyncio.run(client._points('daily-vo2-max', expression)) == [point]
