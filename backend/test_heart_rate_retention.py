from datetime import date
import json

import pytest

from health_database import HealthDatabase
from health_read_store import HealthReadStore, read_range
from compact_heart_rate import compact_cache, compact_normalized


DAY = '2026-10-15'
EXPRESSION = f'heart_rate.sample_time.physical_time >= "{DAY}" AND heart_rate.sample_time.physical_time < "2026-10-16"'


def hr(hour, bpm):
    return {'heartRate': {'sampleTime': {'physicalTime': f'{DAY}T{hour:02}:00:00Z', 'utcOffset': '0s'}, 'beatsPerMinute': bpm}}


def sleep():
    return {'name': 'night', 'sleep': {'interval': {'startTime': f'{DAY}T00:00:00Z', 'endTime': f'{DAY}T06:00:00Z'},
        'metadata': {'mainSleep': True, 'processed': True}, 'summary': {}}}


def test_normalized_keeps_only_night_and_replaces_daily_mean(tmp_path):
    db = HealthDatabase(tmp_path/'normalized.db')
    account = db.ensure_account('one'); provider = account['provider_account_id']
    db.ingest(provider, 'sleep', [sleep()])
    points = [hr(1, 60), hr(12, 90), hr(13, 120), hr(12, 90)]
    db.ingest(provider, 'heart-rate', points, expression=EXPRESSION)
    db.ingest(provider, 'heart-rate', points + [hr(14, 130)], expression=EXPRESSION)
    with db.connect() as conn:
        assert [r[0] for r in conn.execute('SELECT bpm FROM hr_samples')] == [60]
        assert conn.execute("SELECT COUNT(*) FROM raw_payloads WHERE dataset='heart-rate'").fetchone()[0] == 0
        row = conn.execute('SELECT average_bpm,sample_count FROM daily_intraday_hr').fetchone()
        assert tuple(row) == (100, 4)
    other = db.ensure_account('two')
    db.ingest(other['provider_account_id'], 'heart-rate', [hr(12, 70)], expression=EXPRESSION)
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM daily_intraday_hr').fetchone()[0] == 2


def test_cache_has_no_daytime_coverage_and_sleep_does_not_replace_average(tmp_path):
    store = HealthReadStore(tmp_path/'cache.db')
    sq = read_range(f'sleep.interval.civil_end_time >= "{DAY}" AND sleep.interval.civil_end_time < "2026-10-16"')
    store.range_write('one', 'sleep', sq, False, [sleep()])
    query = read_range(EXPRESSION)
    points = [hr(1, 60), hr(12, 90), hr(13, 120)]
    assert store.range_write('one', 'heart-rate', query, True, points, now=10)
    assert store.local_read('one', 'heart-rate', query) == [points[0]]
    assert store.intraday_summary('one', DAY) == {'average_bpm': 90, 'sample_count': 3}
    night = read_range(f'heart_rate.sample_time.physical_time >= "{DAY}T00:00:00Z" AND heart_rate.sample_time.physical_time < "{DAY}T06:00:00Z"')
    store.range_write('one', 'heart-rate', night, True, [hr(1, 50)], now=11)
    assert store.intraday_summary('one', DAY)['average_bpm'] == 90
    assert store.range_read('one', 'heart-rate', night, True, now=11)[1] == []
    assert store.range_read('one', 'heart-rate', query, True, now=11)[1]


def test_compaction_preserves_average_and_sleep_and_is_repeatable(tmp_path):
    store = HealthReadStore(tmp_path/'cache.db')
    sq = read_range(f'sleep.interval.civil_end_time >= "{DAY}" AND sleep.interval.civil_end_time < "2026-10-16"')
    store.range_write('one', 'sleep', sq, False, [sleep()])
    points = [hr(1, 60), hr(12, 100)]
    q = read_range(EXPRESSION)
    identity = ('one', 'heart-rate', q.field, True, q.start, q.end)
    with store.connection() as conn, conn:
        conn.execute('INSERT INTO read_slices (account,kind,field,reconciled,lower_bound,upper_bound,fetched,payload) VALUES (?,?,?,?,?,?,?,?)', (*identity, 1, json.dumps(points)))
        store._index_slice(conn, identity, points)
    assert compact_cache(store)['sleep_samples_retained'] == 1
    assert store.intraday_summary('one', DAY)['average_bpm'] == 80
    compact_cache(store)
    assert store.intraday_summary('one', DAY)['average_bpm'] == 80
    db = HealthDatabase(tmp_path/'normalized.db')
    a = db.ensure_account('one')
    db.ingest(a['provider_account_id'], 'sleep', [sleep()])
    with db.connect() as conn:
        conn.execute('INSERT INTO hr_samples VALUES (?,?,?,?,?)', (a['user_id'], 1792022400, 100, 0, None))
    compact_normalized(db)
    with db.connect() as conn:
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
