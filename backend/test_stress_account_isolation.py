import asyncio
import json
import sqlite3
from contextlib import closing
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sleep_stress_pipeline import compute_connected_sleep_stress
from sleep_stress_store import SleepStressStore


def test_two_accounts_with_same_fallback_sleep_id_have_separate_records(tmp_path):
    point = {'sleep': {
        'interval': {'startTime': '2026-10-06T23:00:00Z', 'endTime': '2026-10-07T05:00:00Z'},
        'type': 'STAGES', 'metadata': {'processed': True, 'stagesStatus': 'SUCCEEDED', 'mainSleep': True},
        'stages': [{'startTime': '2026-10-06T23:00:00Z', 'endTime': '2026-10-07T05:00:00Z', 'type': 'LIGHT'}],
    }}
    store = SleepStressStore(tmp_path / 'stress.sqlite3')
    async def run():
        for account in ('synthetic-a', 'synthetic-b'):
            client = SimpleNamespace(account_key=account,
                get_sleep_stress_points=AsyncMock(return_value=([point], [], [])))
            await compute_connected_sleep_stress(client, date(2026, 10, 7), date(2026, 10, 7), 'start', store)
    asyncio.run(run())
    with closing(sqlite3.connect(store.path)) as connection:
        records = connection.execute('SELECT payload FROM sleep_stress').fetchall()
    assert len(records) == 2
    assert len({json.loads(record[0])['sleep_id'] for record in records}) == 1
    sleep_id = json.loads(records[0][0])['sleep_id']
    assert store.get(sleep_id) is None
    assert store.get(sleep_id, account='synthetic-a') is not None
    assert store.get(sleep_id, account='synthetic-b') is not None
    assert store.get(sleep_id, account='synthetic-c') is None
