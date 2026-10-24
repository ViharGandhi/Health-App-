"""One-time retention migration. Run while the backend is stopped.

Build daily averages before deleting daytime HR, keep main-sleep traces,
remove redundant HR payloads, then VACUUM to reclaim the file space.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time

from health_database import HealthDatabase
from health_read_store import HealthReadStore, read_range
from heart_rate_retention import cache_windows, sample, without_day_traces


def compact_cache(store):
    with store.connection() as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''CREATE TEMP TABLE compact_hr (
            account TEXT, ts REAL, day TEXT, bpm REAL, payload TEXT, fetched REAL,
            PRIMARY KEY(account,ts))''')
        # Latest successful slice wins, regardless of civil/physical cache copies.
        rows = conn.execute('''SELECT p.account,p.payload,s.fetched FROM read_points p
            JOIN read_slices s USING(account,kind,field,reconciled,lower_bound,upper_bound)
            WHERE p.kind='heart-rate' AND NOT EXISTS (
                SELECT 1 FROM read_slices newer WHERE newer.account=s.account
                AND newer.kind=s.kind AND newer.field=s.field AND newer.reconciled=s.reconciled
                AND newer.lower_bound<=p.stamp AND newer.upper_bound>p.stamp
                AND (newer.fetched>s.fetched OR (newer.fetched=s.fetched AND newer.rowid>s.rowid)))
            ORDER BY s.fetched,s.rowid''')
        for account, raw, fetched in rows:
            value = sample(json.loads(raw))
            if value is not None:
                ts, local, bpm = value
                conn.execute('INSERT OR REPLACE INTO compact_hr VALUES (?,?,?,?,?,?)',
                             (account, ts, str(local.date()), bpm, raw, fetched))
        conn.execute('''INSERT INTO daily_intraday_hr
            SELECT account,day,AVG(bpm),COUNT(*),MAX(fetched),date(day,'+1 day')||'T00:00:00.000000'
            FROM compact_hr GROUP BY account,day
            ON CONFLICT(owner,day) DO NOTHING''')
        before = conn.execute('SELECT COUNT(*) FROM compact_hr').fetchone()[0]
        conn.execute("DELETE FROM read_points WHERE kind='heart-rate'")
        conn.execute("DELETE FROM read_slices WHERE kind='heart-rate'")
        accounts = [r[0] for r in conn.execute('SELECT DISTINCT account FROM compact_hr')]
        retained = 0
        for account in accounts:
            for start, end in cache_windows(conn, account):
                rows = conn.execute('SELECT payload,fetched FROM compact_hr WHERE account=? AND ts>=? AND ts<? ORDER BY ts', (account, start, end)).fetchall()
                if not rows:
                    continue
                points = [json.loads(r[0]) for r in rows]
                lower = datetime.fromtimestamp(start, timezone.utc).replace(tzinfo=None).isoformat(timespec='microseconds')
                upper = datetime.fromtimestamp(end, timezone.utc).replace(tzinfo=None).isoformat(timespec='microseconds')
                identity = (account, 'heart-rate', 'heart_rate.sample_time.physical_time', True, lower, upper)
                conn.execute('''INSERT OR REPLACE INTO read_slices
                    (account,kind,field,reconciled,lower_bound,upper_bound,fetched,payload)
                    VALUES (?,?,?,?,?,?,?,?)''', (*identity, max(r[1] for r in rows), json.dumps(points)))
                store._index_slice(conn, identity, points)
                retained += len(points)
        # Exact cache keys are hashes; inspect payloads to identify old HR copies.
        for account, key, raw in conn.execute('SELECT account,key,payload FROM exact_reads').fetchall():
            payload = json.loads(raw)
            if isinstance(payload, list) and any(isinstance(p, dict) and 'heartRate' in p for p in payload):
                conn.execute('DELETE FROM exact_reads WHERE account=? AND key=?', (account, key))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'awake_heart_rate' in tables:
            for account, day, tz, raw in conn.execute('SELECT * FROM awake_heart_rate').fetchall():
                payload = json.loads(raw); payload.pop('samples', None)
                conn.execute('UPDATE awake_heart_rate SET payload=? WHERE account=? AND day=? AND timezone=?', (json.dumps(payload), account, day, tz))
        for account, key, raw in conn.execute('SELECT account,key,payload FROM page_snapshots').fetchall():
            conn.execute('UPDATE page_snapshots SET payload=? WHERE account=? AND key=?', (json.dumps(without_day_traces(json.loads(raw))), account, key))
    return {'unique_samples_before': before, 'sleep_samples_retained': retained}


def compact_normalized(db):
    with db.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        before = conn.execute('SELECT COUNT(*) FROM hr_samples').fetchone()[0]
        conn.execute('''INSERT INTO daily_intraday_hr
            SELECT CAST(user_id AS TEXT),date(ts+utc_offset_min*60,'unixepoch'),AVG(bpm),COUNT(*),?,
                date(ts+utc_offset_min*60,'unixepoch','+1 day')||'T00:00:00.000000'
            FROM hr_samples GROUP BY user_id,date(ts+utc_offset_min*60,'unixepoch')
            ON CONFLICT(owner,day) DO NOTHING''', (time.time(),))
        conn.execute('''DELETE FROM hr_samples WHERE NOT EXISTS (
            SELECT 1 FROM sleep_sessions s WHERE s.user_id=hr_samples.user_id
            AND s.is_main_sleep=1 AND s.is_nap=0 AND s.is_processed=1
            AND hr_samples.ts>=s.start_ts AND hr_samples.ts<s.end_ts)''')
        conn.execute("DELETE FROM raw_payloads WHERE dataset='heart-rate'")
        for sid, raw in conn.execute('SELECT snapshot_id,payload FROM presentation_snapshots').fetchall():
            conn.execute('UPDATE presentation_snapshots SET payload=? WHERE snapshot_id=?', (json.dumps(without_day_traces(json.loads(raw))), sid))
        retained = conn.execute('SELECT COUNT(*) FROM hr_samples').fetchone()[0]
    return {'samples_before': before, 'sleep_samples_retained': retained}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=Path(__file__).parent/'data'/'health_cache.sqlite3')
    parser.add_argument('--database', type=Path, default=Path(__file__).parent/'data'/'health.sqlite3')
    args = parser.parse_args()
    cache, db = HealthReadStore(args.cache), HealthDatabase(args.database)
    print(json.dumps({'cache': compact_cache(cache), 'normalized': compact_normalized(db)}), flush=True)
    # Transfer the authoritative cache aggregates to normalized account owners.
    import hashlib
    with cache.connection() as source, db.connect() as dest:
        for account in dest.execute('SELECT user_id,provider_user_id FROM provider_accounts').fetchall():
            identity = hashlib.sha256(('account:'+account['provider_user_id']).encode()).hexdigest()
            alias = source.execute('SELECT account FROM health_account_aliases WHERE identity_key=?', (identity,)).fetchone()
            for row in source.execute('SELECT day,average_bpm,sample_count,updated_at,coverage_end FROM daily_intraday_hr WHERE owner=?', (alias[0] if alias else identity,)):
                dest.execute('INSERT OR REPLACE INTO daily_intraday_hr VALUES (?,?,?,?,?,?)', (str(account['user_id']), *row))
    for path in (args.cache, args.database):
        import sqlite3
        with sqlite3.connect(path, timeout=60) as conn:
            conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            conn.execute('VACUUM')
        print(f'{path.name}: {path.stat().st_size:,} bytes', flush=True)


if __name__ == '__main__':
    main()
