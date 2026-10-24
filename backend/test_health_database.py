import asyncio
from datetime import date
import json
import sqlite3
from types import SimpleNamespace

import pytest

from health_database import HealthDatabase, age_on
from health_read_store import read_range
from health_results import Results, persist_response


@pytest.fixture
def fixture(tmp_path):
    db = HealthDatabase(tmp_path / 'health.sqlite3')
    account = db.ensure_account('provider-one', email='one@example.test', timezone_name='Asia/Calcutta')
    db.save_profile(account['user_id'], '2004-01-31', birth_date='2004-01-31', timezone_name='Asia/Calcutta')
    return db, account


def sleep_point():
    return {'name': 'users/one/dataTypes/sleep/night', 'sleep': {
        'interval': {'startTime': '2026-10-14T18:30:00Z', 'endTime': '2026-10-15T02:30:00Z', 'startUtcOffset': '19800s', 'endUtcOffset': '19800s'},
        'metadata': {'mainSleep': True, 'processed': True},
        'summary': {'minutesAsleep': 450, 'minutesAwake': 30, 'minutesInSleepPeriod': 480, 'minutesToFallAsleep': 10, 'minutesAfterWakeUp': 5,
                    'stagesSummary': [{'type': 'DEEP', 'minutes': 100, 'count': 3}]},
        'stages': [{'type': 'DEEP', 'startTime': '2026-10-14T18:40:00Z', 'endTime': '2026-10-14T20:20:00Z'}]}}


def test_full_schema_and_connection_pragmas(fixture):
    db, _ = fixture
    HealthDatabase(db.path)  # Reopening never replays seeds/DDL.
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0] == 49
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert conn.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
        assert conn.execute("SELECT strict FROM pragma_table_list WHERE name='hr_samples'").fetchone()[0] == 1


def test_birth_date_historical_age_and_account_isolation(fixture):
    db, account = fixture
    assert age_on('2004-01-31', '2026-01-30') == 21
    assert age_on('2004-01-31', '2026-01-31') == 22
    assert db.profile(account['user_id'], '2026-10-15')['birth_date'] == '2004-01-31'
    assert db.profile(account['user_id'], '2027-01-31')['age'] == 23
    other = db.ensure_account('provider-two')
    assert db.profile(other['user_id'], '2026-10-15') is None
    with pytest.raises(ValueError):
        db.save_profile(account['user_id'], '2004-01-31', birth_date='2003-01-31')


def test_raw_import_dedup_corrections_and_strict_provider_metrics(fixture):
    db, account = fixture
    db.ingest(account['provider_account_id'], 'sleep', [sleep_point()])
    point = {'heartRate': {'sampleTime': {'physicalTime': '2026-10-15T01:00:00Z', 'utcOffset': '19800s'}, 'beatsPerMinute': '80'}}
    for _ in range(2):
        db.ingest(account['provider_account_id'], 'heart-rate', [point])
    point['heartRate']['beatsPerMinute'] = '90'
    db.ingest(account['provider_account_id'], 'heart-rate', [point])
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM hr_samples').fetchone()[0] == 1
        assert conn.execute('SELECT bpm FROM hr_samples').fetchone()[0] == 90
        assert conn.execute("SELECT COUNT(*) FROM raw_payloads WHERE dataset='heart-rate'").fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO daily_measurements(user_id,metric_code,metric_date,value) VALUES (?,'awake_hr','2026-10-15',80)", (account['user_id'],))
    query = read_range('heart_rate.sample_time.civil_time >= "2026-10-15T06:00:00" AND heart_rate.sample_time.civil_time < "2026-10-15T07:00:00"')
    assert len(db.raw_points(account['user_id'], 'heart-rate', query)) == 1


def test_invalid_hr_is_discarded_and_does_not_advance_cursor(fixture):
    db, account = fixture
    point = {'heartRate': {'sampleTime': {'physicalTime': '2026-10-15T01:00:00Z'}, 'beatsPerMinute': True}}
    db.ingest(account['provider_account_id'], 'heart-rate', [point])
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM hr_samples').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM raw_payloads').fetchone()[0] == 0
        assert conn.execute('SELECT status FROM sync_runs').fetchone()[0] == 'partial'
        assert conn.execute('SELECT COUNT(*) FROM sync_cursors').fetchone()[0] == 0


def test_sleep_raw_children_and_original_payload_fallback(fixture):
    db, account = fixture
    point = sleep_point()
    db.ingest(account['provider_account_id'], 'sleep', [point])
    with db.connect() as conn:
        assert conn.execute('SELECT sleep_date FROM sleep_sessions').fetchone()[0] == '2026-10-15'
        assert conn.execute('SELECT deep_minutes FROM sleep_summaries').fetchone()[0] == 100
        assert conn.execute('SELECT COUNT(*) FROM sleep_segments').fetchone()[0] == 1
    query = read_range('sleep.interval.civil_end_time >= "2026-10-15" AND sleep.interval.civil_end_time < "2026-10-16"')
    assert db.raw_points(account['user_id'], 'sleep', query) == [point]


def sleep_result():
    return {'is_mock': False, 'score': 60.4, 'sleep_need': {'baseline_min': 450, 'strain_add_min': 20, 'debt_add_min': 10, 'nap_credit_min': 0, 'total_need_min': 480, 'sleep_debt_min': 30},
            'total_sleep_hours': 7.5, 'stages': {'deep_minutes': 100, 'rem_minutes': 90, 'core_minutes': 260, 'awake_minutes': 30},
            'efficiency_pct': 93.75, 'restfulness_score': 80, 'sleeping_hr': 64, 'waking_hr': 89, 'hr_dip_pct': 28, 'hr_dip_score': 100,
            'waking_hr_date': '2026-10-14', 'sleeping_hrv': 50, 'hrv_baseline': 45, 'rhr_baseline': 65, 'baseline_start': '2026-08-16', 'baseline_end': '2026-10-14',
            'components_available': {}, 'defaulted_components': {'sleeping_hrv': 50}, 'partial': True, 'component_coverage': .95}


def test_sleep_results_lineage_versions_and_current_view(fixture):
    db, account = fixture; user = account['user_id']
    db.ingest(account['provider_account_id'], 'sleep', [sleep_point()])
    writer = Results(db, user, '2026-10-15')
    data = sleep_result()
    writer.sleep(data); writer.sleep(data)
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM sleep_scores').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM sleep_score_components').fetchone()[0] == 7
        assert conn.execute('SELECT profile_version_id FROM calc_runs LIMIT 1').fetchone()[0] is not None
        assert conn.execute('SELECT COUNT(*) FROM calc_run_dependencies').fetchone()[0] >= 3
    data['score'] = 61
    writer.sleep(data)
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM sleep_scores').fetchone()[0] == 2
        assert conn.execute('SELECT overall_score FROM v_sleep_score_current').fetchone()[0] == 61
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()


def test_fractional_stress_and_mock_isolation(fixture):
    db, account = fixture
    Results(db, account['user_id'], '2026-10-15').stress({'days': [{'date': '2026-10-15', 'coverage': 1, 'points': [{'start': '2026-10-15T06:00:00Z', 'end': '2026-10-15T06:05:00Z', 'score': 1.4}]}]})
    client = SimpleNamespace(database=db, db_account=account)
    persist_response(client, '/api/sleep', {'is_mock': True}, '2026-10-15')
    with db.connect() as conn:
        assert conn.execute('SELECT score FROM stress_intervals').fetchone()[0] == 1.4
        assert conn.execute('SELECT COUNT(*) FROM sleep_scores').fetchone()[0] == 0


def test_failed_download_has_no_observations_or_success_cursor(fixture):
    from health_persistence import normalized_fetch, capture_page
    db, account = fixture
    client = SimpleNamespace(database=db, db_account=account)
    @normalized_fetch
    async def download(client, kind, expression):
        capture_page({'dataPoints': [sleep_point()]})
        raise RuntimeError('second page failed')
    with pytest.raises(RuntimeError):
        asyncio.run(download(client, 'sleep', 'filter'))
    with db.connect() as conn:
        assert conn.execute('SELECT status FROM sync_runs').fetchone()[0] == 'failed'
        assert conn.execute('SELECT COUNT(*) FROM sleep_sessions').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM sync_cursors').fetchone()[0] == 0


def test_encrypted_credentials_never_store_plaintext(fixture, monkeypatch):
    from cryptography.fernet import Fernet
    db, account = fixture
    monkeypatch.setenv('HEALTH_CREDENTIAL_KEY', Fernet.generate_key().decode())
    session = {'access_token': 'test-access-secret', 'refresh_token': 'test-refresh-secret', 'expires_at': 2000000000}
    assert db.save_credentials(account['provider_account_id'], session)
    assert db.credentials(account['provider_account_id']) == session
    with db.connect() as conn:
        row = conn.execute('SELECT * FROM provider_credentials').fetchone()
        assert isinstance(row['access_token_enc'], bytes)
        assert b'test-access-secret' not in row['access_token_enc']
        assert b'test-refresh-secret' not in row['refresh_token_enc']


def test_request_age_uses_birth_date_over_stale_browser_age(fixture):
    import main
    from starlette.requests import Request
    from unittest.mock import patch
    db, account = fixture
    request = Request({'type': 'http', 'headers': [(b'x-user-age', b'21'), (b'x-user-date', b'2026-10-15')]})
    with patch('main.get_session', return_value={'health_user_id': 'provider-one'}), patch('health_database.database', return_value=db):
        assert main._client_age(request) == 22
    request = Request({'type': 'http', 'headers': [(b'x-user-date', b'2026-01-30')]})
    with patch('main.get_session', return_value={'health_user_id': 'provider-one'}), patch('health_database.database', return_value=db):
        assert main._client_age(request) == 21


def test_empty_authoritative_slice_removes_only_its_range_and_owner(fixture):
    db, account = fixture
    other = db.ensure_account('provider-other')
    point = {'heartRate': {'sampleTime': {'physicalTime': '2026-10-15T01:00:00Z', 'utcOffset': '19800s'}, 'beatsPerMinute': 80}}
    for owner in (account, other):
        db.ingest(owner['provider_account_id'], 'sleep', [sleep_point()])
        db.ingest(owner['provider_account_id'], 'heart-rate', [point])
    db.ingest(account['provider_account_id'], 'heart-rate', [], expression='heart_rate.sample_time.civil_time >= "2026-10-15" AND heart_rate.sample_time.civil_time < "2026-10-16"')
    with db.connect() as conn:
        assert conn.execute('SELECT user_id FROM hr_samples').fetchone()[0] == other['user_id']


def test_migration_is_repeatable_and_preserves_original_cache(fixture, tmp_path, monkeypatch):
    from health_read_store import HealthReadStore
    from google_health_client import GoogleHealthClient
    from migrate_health_database import migrate
    db, account = fixture
    monkeypatch.setenv('HEALTH_DB_PATH', str(db.path))
    store = HealthReadStore(tmp_path / 'legacy.sqlite3')
    client = GoogleHealthClient('test', cache=True, account_id='provider-one', store=store)
    query = read_range('sleep.interval.civil_end_time >= "2026-10-15" AND sleep.interval.civil_end_time < "2026-10-16"')
    assert store.range_write(client.account_key, 'sleep', query, False, [sleep_point()])
    for _ in range(2):
        result = migrate(client, birth_date=date(2004, 1, 31), session={'health_user_id': 'provider-one'})
        assert result['foreign_key_issues'] == 0
    assert result['counts']['sleep_sessions'] == 1
    assert len(store.local_read(client.account_key, 'sleep', query, False)) == 1


def test_step_pages_and_measurement_provenance_commit_together(fixture):
    from health_persistence import normalized_steps, capture_page
    db, account = fixture
    client = SimpleNamespace(database=db, db_account=account)
    @normalized_steps
    async def download(client, start, end):
        capture_page({'rollupDataPoints': [{'civilStartTime': {'date': {'year': 2026, 'month': 10, 'day': 15}}, 'steps': {'countSum': 1234}}]})
        return {date(2026, 10, 15): 1234}
    asyncio.run(download(client, date(2026, 10, 15), date(2026, 10, 15)))
    with db.connect() as conn:
        row = conn.execute("SELECT value,sync_run_id,payload_id FROM daily_measurements WHERE metric_code='steps'").fetchone()
        assert row['value'] == 1234 and row['sync_run_id'] and row['payload_id']
        assert conn.execute('SELECT status FROM sync_runs WHERE sync_run_id=?', (row['sync_run_id'],)).fetchone()[0] == 'ok'
