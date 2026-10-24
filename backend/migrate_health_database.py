"""Non-destructive, account-scoped import of the existing app data into v1."""
import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name('.env'))

from auth import _unsign
from google_health_client import GoogleHealthClient
from health_database import database_for_store
from health_results import Results, persist_response
from health_read_store import point_clock


def migrate(client, *, birth_date=None, timezone_name='Asia/Calcutta', session=None, resume_results=False):
    db = database_for_store(client.store)
    account = db.ensure_account(session['health_user_id'], email=session.get('user_email'), name=session.get('user_name'), timezone_name=timezone_name)
    user, provider = account['user_id'], account['provider_account_id']
    if session.get('access_token'):
        if not os.getenv('HEALTH_CREDENTIAL_KEY'):
            from cryptography.fernet import Fernet
            key = Fernet.generate_key().decode()
            with Path(__file__).with_name('.env').open('a', encoding='utf-8') as env:
                env.write('\nHEALTH_CREDENTIAL_KEY=' + key + '\n')
            os.environ['HEALTH_CREDENTIAL_KEY'] = key
        db.save_credentials(provider, session)
    if birth_date:
        db.save_profile(user, birth_date, birth_date=birth_date, sex={'m': 'male', 'f': 'female'}.get(os.getenv('USER_SEX'), 'unknown'), timezone_name=timezone_name)
    client.database, client.db_account = db, account
    marker = 'legacy-cache-v1:' + hashlib.sha256(str(client.store.path).encode()).hexdigest()[:16]
    with db.connect() as conn:
        done = conn.execute('SELECT 1 FROM scheduled_jobs WHERE user_id=? AND job_type=? AND last_status=?', (user, marker, 'ok')).fetchone()
    if done:
        return summary(db, user)
    legacy = sqlite3.connect(client.store.path)
    legacy.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        seen = defaultdict(set)
        buffers = defaultdict(list)
        rows = [] if resume_results else legacy.execute('''SELECT p.kind,p.payload FROM read_points p JOIN read_slices s
            USING(account,kind,field,reconciled,lower_bound,upper_bound)
            WHERE p.account=? AND NOT EXISTS (
              SELECT 1 FROM read_slices newer WHERE newer.account=s.account AND newer.kind=s.kind
              AND newer.field=s.field AND newer.reconciled=s.reconciled
              AND newer.lower_bound<=p.stamp AND newer.upper_bound>p.stamp
              AND (newer.fetched>s.fetched OR (newer.fetched=s.fetched AND newer.rowid>s.rowid)))
            ORDER BY s.fetched DESC,s.rowid DESC''', (client.account_key,))
        for row in rows:
            kind, point = row['kind'], json.loads(row['payload'])
            identity = point_clock(point, 'heart_rate.sample_time.physical_time') if kind == 'heart-rate' else point.get('name')
            identity = identity or hashlib.sha256(row['payload'].encode()).hexdigest()
            if identity in seen[kind]:
                continue
            seen[kind].add(identity)
            buffers[kind].append(point)
            if len(buffers[kind]) >= 2000:
                db.ingest(provider, kind, buffers.pop(kind), endpoint='legacy-cache:read_points', trigger='backfill')
        for kind, points in buffers.items():
            db.ingest(provider, kind, points, endpoint='legacy-cache:read_points', trigger='backfill')
        steps = {r['day']: r['count'] for r in legacy.execute('SELECT day,count FROM dynamic_steps WHERE account=?', (client.account_key,))}
        db.save_steps(provider, steps)
        writer = Results(db, user, date.today())
        for row in legacy.execute('SELECT day,sleep_id,payload FROM sleep_rhr WHERE account=? ORDER BY day', (client.account_key,)):
            writer.sleeping_hr(row['day'], row['sleep_id'], json.loads(row['payload']))
        if 'awake_heart_rate' in tables:
            for row in legacy.execute('SELECT day,payload FROM awake_heart_rate WHERE account=? ORDER BY day', (client.account_key,)):
                writer.awake(row['day'], json.loads(row['payload']))
        from strain_service import _decode_day
        for row in legacy.execute('SELECT payload FROM calculated_days WHERE account=? ORDER BY expires', (client.account_key,)):
            value = json.loads(row['payload'], object_hook=_decode_day)
            if 'strain' in value and 'day_window' in value:
                writer.strain(value, value['date'])
        for row in legacy.execute('SELECT key,payload,updated FROM page_snapshots WHERE account=?', (client.account_key,)):
            value = json.loads(row['payload'])
            if value.get('is_mock') is True:
                continue
            day = value.get('date') or value.get('range_end') or str(date.today())
            with db.connect() as conn:
                conn.execute('INSERT OR IGNORE INTO presentation_snapshots(user_id,view_key,as_of_date,params_hash,payload,built_at) VALUES (?,?,?,?,?,?)',
                             (user, 'legacy-cache', day, row['key'], row['payload'], int(row['updated'])))
            path = ('/api/dashboard' if all(k in value for k in ('sleep', 'strain', 'recovery')) else
                    '/api/home/metrics' if 'rows' in value and 'activities' in value else
                    '/api/sleep' if 'hr_dip_score' in value else
                    '/api/strain' if 'zone_minutes' in value and 'params' in value else
                    '/api/recovery' if value.get('estimator') == 'connected_recovery' else None)
            if path:
                persist_response(client, path, value, day, row['key'])
        with db.connect() as conn:
            conn.execute('INSERT INTO scheduled_jobs(user_id,provider_account_id,job_type,schedule_expr,enabled,last_run_at,last_status) VALUES (?,?,?,?,0,?,?)',
                         (user, provider, marker, str(client.store.path), int(time.time()), 'ok'))
            # The personal-account scheduler still owns execution. This row
            # makes its schedule visible in the normalized operations model.
            if not conn.execute("SELECT 1 FROM scheduled_jobs WHERE user_id=? AND job_type='awake_hr'", (user,)).fetchone():
                conn.execute("INSERT INTO scheduled_jobs(user_id,provider_account_id,job_type,schedule_expr) VALUES (?,?, 'awake_hr', ?)", (user, provider, '0 22 * * *; timezone=' + timezone_name))
    finally:
        legacy.close()
    return summary(db, user)


def summary(db, user):
    with db.connect() as conn:
        counts = {table: conn.execute(f'SELECT COUNT(*) FROM {table} WHERE user_id=?', (user,)).fetchone()[0]
                  for table in ('hr_samples', 'hrv_samples', 'daily_measurements', 'sleep_sessions', 'activities', 'activity_level_intervals', 'calc_runs', 'sleep_scores', 'awake_hr_results', 'sleeping_hr_results', 'daily_strain_results', 'recovery_results')}
        errors = conn.execute('PRAGMA foreign_key_check').fetchall()
    return {'database': str(db.path), 'user_id': user, 'profile': db.profile(user, str(date.today())), 'counts': counts, 'foreign_key_issues': len(errors)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--birth-date', type=date.fromisoformat)
    parser.add_argument('--timezone', default='Asia/Calcutta')
    parser.add_argument('--resume-results', action='store_true', help='Resume only after raw observations were fully imported')
    args = parser.parse_args()
    cookie = os.getenv('GOOGLE_HEALTH_SESSION_COOKIE', '')
    if cookie.startswith('soma_session='):
        cookie = cookie.split('=', 1)[1].split(';', 1)[0]
    session = _unsign(cookie)
    if not session or not session.get('health_user_id'):
        raise SystemExit('A valid connected GOOGLE_HEALTH_SESSION_COOKIE is required; no accounts were imported')
    client = GoogleHealthClient('migration-no-network', cache=True, account_id=session['health_user_id'])
    print(json.dumps(migrate(client, birth_date=args.birth_date, timezone_name=args.timezone, session=session, resume_results=args.resume_results), indent=2))
