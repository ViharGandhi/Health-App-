"""Normalized SQLite ownership, observations, profiles and calculation lineage.

The existing read-store remains a transport/range cache during migration. This
database contains business records using the supplied 48-table schema.
"""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time

MIGRATION = Path(__file__).with_name('migrations') / '003_normalized_health.sql'
DAILY = {
    'daily-heart-rate-variability': ('dailyHeartRateVariability', {
        'averageHeartRateVariabilityMilliseconds': 'hrv_rmssd_avg',
        'deepSleepRootMeanSquareOfSuccessiveDifferencesMilliseconds': 'hrv_deep_rmssd',
        'nonRemHeartRateBeatsPerMinute': 'non_rem_hr'}),
    'daily-oxygen-saturation': ('dailyOxygenSaturation', {'averagePercentage': 'spo2_avg_pct'}),
    'daily-respiratory-rate': ('dailyRespiratoryRate', {'breathsPerMinute': 'respiratory_rate'}),
    'daily-sleep-temperature-derivations': ('dailySleepTemperatureDerivations', {'nightlyTemperatureCelsius': 'skin_temp_c'}),
    'daily-vo2-max': ('dailyVo2Max', {'vo2Max': 'vo2_max'}),
}


def json_text(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False, default=str)


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def integer(value):
    value = number(value)
    return int(value) if value is not None and value.is_integer() else None


def epoch(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, datetime):
        stamp = value
    else:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Physical timestamps require an offset')
    return int(stamp.timestamp())


def offset(value):
    return int(float(str(value or '0s').removesuffix('s')) / 60)


def age_on(birth_date, day):
    birth, day = date.fromisoformat(str(birth_date)), date.fromisoformat(str(day))
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))


@lru_cache(maxsize=16)
def database(path=None):
    target = Path(path or os.getenv('HEALTH_DB_PATH', str(Path(__file__).parent / 'data' / 'health.sqlite3')))
    if not target.is_absolute():
        target = Path(__file__).parent / target
    return HealthDatabase(target)


def database_for_store(store):
    configured = os.getenv('HEALTH_DB_PATH')
    path = Path(store.path)
    target = configured or (path.with_name('health.sqlite3') if path.name == 'health_cache.sqlite3'
                            else path.with_name(path.stem + '.normalized.sqlite3'))
    return database(str(target))


class HealthDatabase:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone():
                # DDL and seeds commit together; failed installation is retryable.
                sql = MIGRATION.read_text(encoding='utf-8-sig').replace('PRAGMA journal_mode = WAL;', '')
                conn.executescript('BEGIN IMMEDIATE;\n' + sql + '\nCOMMIT;')
            from heart_rate_retention import SUMMARY_SQL
            conn.execute(SUMMARY_SQL)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=30000')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def ensure_account(self, provider_user_id, *, email=None, name=None, timezone_name='UTC'):
        if not isinstance(provider_user_id, str) or not provider_user_id.strip():
            raise ValueError('Provider identity is required')
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            found = conn.execute("SELECT * FROM provider_accounts WHERE provider='google_health' AND provider_user_id=?", (provider_user_id,)).fetchone()
            if found:
                # Provider identity is authoritative. Never merge owners by email.
                conn.execute('UPDATE provider_accounts SET email=COALESCE(?,email),display_name=COALESCE(?,display_name) WHERE provider_account_id=?',
                             (email or None, name or None, found['provider_account_id']))
                conn.execute('UPDATE users SET display_name=COALESCE(?,display_name) WHERE user_id=?', (name or None, found['user_id']))
                if email and not conn.execute('SELECT 1 FROM users WHERE email=? AND user_id<>?', (email, found['user_id'])).fetchone():
                    conn.execute('UPDATE users SET email=COALESCE(email,?) WHERE user_id=?', (email, found['user_id']))
                return dict(conn.execute('SELECT * FROM provider_accounts WHERE provider_account_id=?', (found['provider_account_id'],)).fetchone())
            user = conn.execute('INSERT INTO users(email,display_name,timezone) VALUES (?,?,?)',
                                (email or None, name or None, timezone_name)).lastrowid
            account = conn.execute('INSERT INTO provider_accounts(user_id,provider_user_id,email,display_name) VALUES (?,?,?,?)',
                                   (user, provider_user_id, email or None, name or None)).lastrowid
            return dict(conn.execute('SELECT * FROM provider_accounts WHERE provider_account_id=?', (account,)).fetchone())

    def account(self, provider_user_id):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM provider_accounts WHERE provider='google_health' AND provider_user_id=?", (provider_user_id,)).fetchone()
            return dict(row) if row else None

    def profile(self, user, day):
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM user_profile_versions WHERE user_id=? AND effective_from_date<=? ORDER BY effective_from_date DESC LIMIT 1',
                               (user, str(day))).fetchone()
        if row is None:
            return None
        result = dict(row)
        result['age'] = age_on(row['birth_date'], day) if row['birth_date'] else row['age_years']
        return result

    def save_profile(self, user, effective, *, birth_date=None, age_years=None, sex='unknown', timezone_name='UTC'):
        from zoneinfo import ZoneInfo
        effective = date.fromisoformat(str(effective))
        ZoneInfo(timezone_name)
        if birth_date is not None:
            birth_date = date.fromisoformat(str(birth_date))
            if birth_date > effective or not 0 <= age_on(birth_date, effective) <= 120:
                raise ValueError('Birth date must precede the profile date and imply a valid age')
        with self.connect() as conn:
            # A recorded profile version is immutable. A different update on the
            # same date requires an explicit future effective date, not mutation.
            existing = conn.execute('SELECT * FROM user_profile_versions WHERE user_id=? AND effective_from_date=?', (user, str(effective))).fetchone()
            values = (str(birth_date) if birth_date else None, age_years, sex, timezone_name)
            if existing:
                if tuple(existing[k] for k in ('birth_date', 'age_years', 'sex', 'timezone')) != values:
                    raise ValueError('A different profile version already exists for this date')
                return existing['profile_version_id']
            result = conn.execute('INSERT INTO user_profile_versions(user_id,effective_from_date,birth_date,age_years,sex,timezone) VALUES (?,?,?,?,?,?)',
                                  (user, str(effective), *values)).lastrowid
            conn.execute('UPDATE users SET timezone=? WHERE user_id=?', (timezone_name, user))
            conn.execute('UPDATE presentation_snapshots SET is_stale=1 WHERE user_id=?', (user,))
            return result

    def start_sync(self, account, kind, expression=None, trigger='scheduled'):
        from health_read_store import read_range
        query = read_range(expression) if expression else None
        with self.connect() as conn:
            return conn.execute('INSERT INTO sync_runs(provider_account_id,dataset,trigger,range_start_date,range_end_date) VALUES (?,?,?,?,?)',
                                (account, kind, trigger, query.start[:10] if query else None, query.end[:10] if query else None)).lastrowid

    def fail_sync(self, sync_id, reason):
        with self.connect() as conn:
            conn.execute("UPDATE sync_runs SET status='failed',error_message=?,finished_at=? WHERE sync_run_id=?",
                         (reason, int(time.time()), sync_id))

    def ingest(self, account, kind, points, *, pages=None, endpoint=None, sync_id=None, fetched=None, trigger='scheduled', expression=None):
        fetched = int(fetched or time.time())
        pages = pages if pages is not None else [{'dataPoints': points}]
        with self.connect() as conn:
            owner = conn.execute('SELECT user_id FROM provider_accounts WHERE provider_account_id=?', (account,)).fetchone()
            if owner is None:
                raise ValueError('Unknown provider account')
            user = owner[0]
            invalid_hr = 0
            if kind == 'heart-rate':
                from heart_rate_retention import save_daily, keep_night, sample
                invalid_hr = sum(sample(point) is None for point in points)
                save_daily(conn, user, points, expression, fetched)
                windows = [(r[0], r[1]) for r in conn.execute(
                    'SELECT start_ts,end_ts FROM sleep_sessions WHERE user_id=? AND is_nap=0 AND is_processed=1 AND is_main_sleep=1', (user,))]
                # Provider pages also contain every sample: retain no HR pages.
                points = keep_night(points, windows)
                pages = []
            if sync_id is None:
                sync_id = conn.execute('INSERT INTO sync_runs(provider_account_id,dataset,trigger,started_at) VALUES (?,?,?,?)', (account, kind, trigger, fetched)).lastrowid
            sync = conn.execute('SELECT range_start_date,range_end_date FROM sync_runs WHERE sync_run_id=?', (sync_id,)).fetchone()
            payload_ids = {}
            first_payload = None
            for page in pages:
                raw = json_text(page)
                digest = hashlib.sha256(raw.encode()).hexdigest()
                conn.execute('INSERT OR IGNORE INTO raw_payloads(provider_account_id,sync_run_id,dataset,endpoint,http_status,payload_sha256,payload,fetched_at,range_start_date,range_end_date) VALUES (?,?,?,?,?,?,?,?,?,?)',
                             (account, sync_id, kind, endpoint, 200, digest, raw, fetched, sync[0], sync[1]))
                payload = conn.execute('SELECT payload_id FROM raw_payloads WHERE provider_account_id=? AND dataset=? AND payload_sha256=?', (account, kind, digest)).fetchone()[0]
                first_payload = first_payload or payload
                for point in page.get('dataPoints', []):
                    if point.get('name'):
                        payload_ids[point['name']] = payload
            accepted, rejected = 0, invalid_hr
            for point in points:
                # A malformed row remains in the raw payload with a partial sync.
                # Each row is atomic, including child segments and summaries.
                conn.execute('SAVEPOINT observation')
                try:
                    self._observation(conn, user, account, sync_id, payload_ids.get(point.get('name'), first_payload), kind, point, fetched)
                    accepted += 1
                except (KeyError, TypeError, ValueError, OverflowError, sqlite3.IntegrityError):
                    conn.execute('ROLLBACK TO observation')
                    rejected += 1
                finally:
                    conn.execute('RELEASE observation')
            conn.execute('UPDATE sync_runs SET status=?,records_upserted=?,error_message=?,finished_at=? WHERE sync_run_id=?',
                         ('partial' if rejected else 'ok', accepted, (f'{rejected} invalid observations discarded' if kind == 'heart-rate' else f'{rejected} invalid observations retained in raw payloads') if rejected else None, int(time.time()), sync_id))
            if not rejected:
                if expression:
                    self._prune(conn, user, kind, points, expression)
                conn.execute('INSERT INTO sync_cursors(provider_account_id,dataset,last_success_run_id,last_synced_ts) VALUES (?,?,?,?) ON CONFLICT(provider_account_id,dataset) DO UPDATE SET last_success_run_id=excluded.last_success_run_id,last_synced_ts=excluded.last_synced_ts,updated_at=excluded.last_synced_ts',
                             (account, kind, sync_id, fetched))
            return accepted

    def _prune(self, conn, user, kind, points, expression):
        """An empty successful authoritative slice removes stale observations."""
        from health_read_store import read_range
        query = read_range(expression)
        if query is None:
            return
        lower = int(datetime.fromisoformat(query.start).replace(tzinfo=timezone.utc).timestamp())
        upper = int(datetime.fromisoformat(query.end).replace(tzinfo=timezone.utc).timestamp())
        table = column = clock = None
        keys = []
        extra, args = '', []
        if kind in ('heart-rate', 'heart-rate-variability'):
            table, root = ('hr_samples', 'heartRate') if kind == 'heart-rate' else ('hrv_samples', 'heartRateVariability')
            column = 'ts'; clock = 'ts+utc_offset_min*60' if query.field.endswith('.civil_time') else 'ts'
            keys = [str(epoch(p[root]['sampleTime']['physicalTime'])) for p in points]
        elif kind in ('sleep', 'exercise'):
            if kind == 'sleep':
                table, column, clock = 'sleep_sessions', 'provider_sleep_id', 'end_ts+end_offset_min*60'
            else:
                table, column, clock = 'activities', 'provider_activity_id', 'start_ts+start_offset_min*60'
            keys = [p.get('name') or hashlib.sha256(json_text([p['exercise']['interval'], p['exercise'].get('exerciseType')]).encode()).hexdigest() for p in points]
        elif kind == 'activity-level':
            table, column, clock = 'activity_level_intervals', 'start_ts', 'start_ts+utc_offset_min*60'
            keys = [str(epoch(p['activityLevel']['interval']['startTime'])) for p in points]
        elif kind in DAILY:
            table, column, clock = 'daily_measurements', "metric_code||':'||metric_date", "CAST(strftime('%s',metric_date) AS INTEGER)"
            root, fields = DAILY[kind]
            extra = f' AND metric_code IN ({",".join("?" for _ in fields)})'
            args = list(fields.values())
            for point in points:
                item = point[root]; stamp = item['date']; day = str(date(stamp['year'], stamp['month'], stamp['day']))
                keys.extend(code+':'+day for field, code in fields.items() if number(item.get(field)) is not None)
        if table is None:
            return
        conn.execute('CREATE TEMP TABLE IF NOT EXISTS retained_raw_keys (key TEXT PRIMARY KEY)')
        conn.execute('DELETE FROM retained_raw_keys')
        conn.executemany('INSERT OR IGNORE INTO retained_raw_keys VALUES (?)', [(key,) for key in keys])
        removed = conn.execute(f'DELETE FROM {table} WHERE user_id=? AND {clock}>=? AND {clock}<?{extra} AND CAST({column} AS TEXT) NOT IN (SELECT key FROM retained_raw_keys)', (user, lower, upper, *args)).rowcount
        if removed:
            conn.execute('UPDATE presentation_snapshots SET is_stale=1 WHERE user_id=?', (user,))
            conn.execute('UPDATE calc_runs SET is_current=0 WHERE user_id=? AND target_date>=? AND target_date<=?', (user, query.start[:10], query.end[:10]))

    def _observation(self, conn, user, account, run, payload, kind, point, fetched):
        if kind == 'heart-rate':
            metric = point['heartRate']; clock = metric['sampleTime']
            bpm = integer(metric['beatsPerMinute'])
            if bpm is None:
                raise ValueError('Non-integer HR cannot be represented in the supplied schema')
            conn.execute('INSERT INTO hr_samples VALUES (?,?,?,?,?) ON CONFLICT(user_id,ts) DO UPDATE SET bpm=excluded.bpm,utc_offset_min=excluded.utc_offset_min,sync_run_id=excluded.sync_run_id',
                         (user, epoch(clock['physicalTime']), bpm, offset(clock.get('utcOffset')), run))
        elif kind == 'heart-rate-variability':
            metric = point['heartRateVariability']; clock = metric['sampleTime']
            rmssd = number(metric['rootMeanSquareOfSuccessiveDifferencesMilliseconds'])
            if rmssd is None:
                raise ValueError('Invalid RMSSD')
            conn.execute('INSERT INTO hrv_samples VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id,ts) DO UPDATE SET rmssd_ms=excluded.rmssd_ms,utc_offset_min=excluded.utc_offset_min,sync_run_id=excluded.sync_run_id',
                         (user, epoch(clock['physicalTime']), None, rmssd, 'unverified', 'unknown', offset(clock.get('utcOffset')), run))
        elif kind in DAILY:
            root, fields = DAILY[kind]; metric = point[root]; stamp = metric['date']
            day = str(date(stamp['year'], stamp['month'], stamp['day']))
            for field, code in fields.items():
                value = number(metric.get(field))
                if value is None:
                    continue
                conn.execute('INSERT INTO daily_measurements(user_id,metric_code,metric_date,value,is_estimated,provider_account_id,sync_run_id,payload_id,fetched_at) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,metric_code,metric_date) DO UPDATE SET value=excluded.value,is_estimated=excluded.is_estimated,sync_run_id=excluded.sync_run_id,payload_id=excluded.payload_id,fetched_at=excluded.fetched_at',
                             (user, code, day, value, int(metric.get('estimated') is True), account, run, payload, fetched))
        elif kind == 'sleep':
            metric = point['sleep']; interval = metric['interval']; meta = metric.get('metadata', {})
            conn.execute('INSERT INTO sleep_sessions(user_id,provider_account_id,provider_sleep_id,start_ts,end_ts,start_offset_min,end_offset_min,is_main_sleep,is_nap,is_processed,sync_run_id,payload_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,provider_sleep_id) DO UPDATE SET start_ts=excluded.start_ts,end_ts=excluded.end_ts,start_offset_min=excluded.start_offset_min,end_offset_min=excluded.end_offset_min,is_main_sleep=excluded.is_main_sleep,is_nap=excluded.is_nap,is_processed=excluded.is_processed,sync_run_id=excluded.sync_run_id,payload_id=excluded.payload_id',
                         (user, account, point['name'], epoch(interval['startTime']), epoch(interval['endTime']), offset(interval.get('startUtcOffset')), offset(interval.get('endUtcOffset')), int(meta.get('mainSleep') is True), int(meta.get('nap') is True), int(meta.get('processed') is not False), run, payload))
            sid = conn.execute('SELECT sleep_session_id FROM sleep_sessions WHERE user_id=? AND provider_sleep_id=?', (user, point['name'])).fetchone()[0]
            summary = metric.get('summary', {})
            values = [integer(summary.get(k)) for k in ('minutesAsleep', 'minutesAwake', 'minutesInSleepPeriod', 'minutesToFallAsleep', 'minutesAfterWakeUp')]
            stages = {s['type']: s for s in summary.get('stagesSummary', [])}
            for field in ('minutes', 'count'):
                values.extend(integer(stages.get(stage, {}).get(field)) for stage in ('DEEP', 'LIGHT', 'REM', 'AWAKE'))
            conn.execute('INSERT OR REPLACE INTO sleep_summaries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (sid, *values))
            conn.execute('DELETE FROM sleep_segments WHERE sleep_session_id=?', (sid,))
            for key, fixed in (('stages', None), ('shortAwakenings', 'short_awakening'), ('outOfBedSegments', 'out_of_bed')):
                for segment in metric.get(key, []):
                    stage = fixed or segment['type'].lower()
                    if stage == 'core':
                        stage = 'light'
                    conn.execute('INSERT OR REPLACE INTO sleep_segments VALUES (?,?,?,?)', (sid, epoch(segment['startTime']), epoch(segment['endTime']), stage))
        elif kind == 'exercise':
            metric = point['exercise']; interval = metric['interval']
            identity = point.get('name') or hashlib.sha256(json_text([interval, metric.get('exerciseType')]).encode()).hexdigest()
            duration = number(str(metric.get('activeDuration', '')).removesuffix('s'))
            conn.execute('INSERT INTO activities(user_id,provider_account_id,provider_activity_id,activity_type,name,start_ts,end_ts,start_offset_min,end_offset_min,active_duration_s,sync_run_id,payload_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,provider_activity_id) DO UPDATE SET activity_type=excluded.activity_type,name=excluded.name,start_ts=excluded.start_ts,end_ts=excluded.end_ts,start_offset_min=excluded.start_offset_min,end_offset_min=excluded.end_offset_min,active_duration_s=excluded.active_duration_s,sync_run_id=excluded.sync_run_id,payload_id=excluded.payload_id',
                         (user, account, identity, metric.get('exerciseType'), metric.get('displayName'), epoch(interval['startTime']), epoch(interval['endTime']), offset(interval.get('startUtcOffset')), offset(interval.get('endUtcOffset')), round(duration) if duration is not None else None, run, payload))
        elif kind == 'activity-level':
            metric = point['activityLevel']; interval = metric['interval']
            level = {'SEDENTARY': 'sedentary', 'LIGHTLY_ACTIVE': 'light', 'MODERATELY_ACTIVE': 'moderate', 'VERY_ACTIVE': 'very_active'}[metric['activityLevelType']]
            conn.execute('INSERT INTO activity_level_intervals VALUES (?,?,?,?,?,?) ON CONFLICT(user_id,start_ts) DO UPDATE SET end_ts=excluded.end_ts,level=excluded.level,utc_offset_min=excluded.utc_offset_min,sync_run_id=excluded.sync_run_id',
                         (user, epoch(interval['startTime']), epoch(interval['endTime']), level, offset(interval.get('startUtcOffset')), run))

    def save_steps(self, account, values, *, pages=None, sync_id=None):
        points = [{'dailySteps': {'date': str(day), 'value': value}} for day, value in values.items()]
        with self.connect() as conn:
            user = conn.execute('SELECT user_id FROM provider_accounts WHERE provider_account_id=?', (account,)).fetchone()[0]
            payload_id = None
            payload_by_day = {}
            for page in pages or []:
                raw = json_text(page); digest = hashlib.sha256(raw.encode()).hexdigest()
                conn.execute("INSERT OR IGNORE INTO raw_payloads(provider_account_id,sync_run_id,dataset,endpoint,http_status,payload_sha256,payload) VALUES (?,?,'steps','https://health.googleapis.com/v4/users/me/dataTypes/steps/dataPoints:dailyRollUp',200,?,?)", (account, sync_id, digest, raw))
                payload_id = conn.execute("SELECT payload_id FROM raw_payloads WHERE provider_account_id=? AND dataset='steps' AND payload_sha256=?", (account, digest)).fetchone()[0]
                for item in page.get('rollupDataPoints', []):
                    stamp = item.get('civilStartTime', {}).get('date')
                    if stamp:
                        payload_by_day[str(date(stamp['year'], stamp['month'], stamp['day']))] = payload_id
            for point in points:
                metric = point['dailySteps']; value = integer(metric['value'])
                if value is not None and value >= 0:
                    conn.execute("INSERT INTO daily_measurements(user_id,metric_code,metric_date,value,provider_account_id,sync_run_id,payload_id) VALUES (?,'steps',?,?,?,?,?) ON CONFLICT(user_id,metric_code,metric_date) DO UPDATE SET value=excluded.value,sync_run_id=excluded.sync_run_id,payload_id=excluded.payload_id", (user, metric['date'], value, account, sync_id, payload_by_day.get(metric['date'])))
            if sync_id is not None:
                stamp = int(time.time())
                conn.execute("UPDATE sync_runs SET status='ok',records_upserted=?,finished_at=? WHERE sync_run_id=?", (len(values), stamp, sync_id))
                conn.execute("INSERT INTO sync_cursors(provider_account_id,dataset,last_success_run_id,last_synced_ts) VALUES (?,'steps',?,?) ON CONFLICT(provider_account_id,dataset) DO UPDATE SET last_success_run_id=excluded.last_success_run_id,last_synced_ts=excluded.last_synced_ts", (account, sync_id, stamp))

    def save_credentials(self, account, session):
        key = os.getenv('HEALTH_CREDENTIAL_KEY')
        if not key:
            return False  # Never put plaintext credentials into the database.
        from cryptography.fernet import Fernet
        cipher = Fernet(key.encode())
        encrypt = lambda value: cipher.encrypt(value.encode()) if value else None
        with self.connect() as conn:
            conn.execute('INSERT INTO provider_credentials(provider_account_id,access_token_enc,refresh_token_enc,key_id,access_expires_at) VALUES (?,?,?,?,?) ON CONFLICT(provider_account_id) DO UPDATE SET access_token_enc=excluded.access_token_enc,refresh_token_enc=excluded.refresh_token_enc,key_id=excluded.key_id,access_expires_at=excluded.access_expires_at,updated_at=CAST(strftime(\'%s\',\'now\') AS INTEGER)',
                         (account, encrypt(session.get('access_token')), encrypt(session.get('refresh_token')), hashlib.sha256(key.encode()).hexdigest()[:16], int(session.get('expires_at', 0))))
        return True

    def credentials(self, account):
        key = os.getenv('HEALTH_CREDENTIAL_KEY')
        if not key:
            return None
        from cryptography.fernet import Fernet
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM provider_credentials WHERE provider_account_id=?', (account,)).fetchone()
        if row is None:
            return None
        if row['key_id'] != hashlib.sha256(key.encode()).hexdigest()[:16]:
            raise ValueError('Credential encryption key does not match the stored key ID')
        cipher = Fernet(key.encode())
        return {'access_token': cipher.decrypt(row['access_token_enc']).decode() if row['access_token_enc'] else '',
                'refresh_token': cipher.decrypt(row['refresh_token_enc']).decode() if row['refresh_token_enc'] else '',
                'expires_at': row['access_expires_at']}

    def raw_points(self, user, kind, query):
        """Normalized observations -> lossless original Google JSON for adapters.

        Only used as a fallback for a legacy cache gap; unknown/pending Google
        fields remain available from the referenced raw payload.
        """
        from health_read_store import point_clock
        lower = int(datetime.fromisoformat(query.start).replace(tzinfo=timezone.utc).timestamp())
        upper = int(datetime.fromisoformat(query.end).replace(tzinfo=timezone.utc).timestamp())
        with self.connect() as conn:
            if kind == 'heart-rate':
                civil = query.field.endswith('.civil_time')
                clock = 'ts+utc_offset_min*60' if civil else 'ts'
                rows = conn.execute(f'SELECT ts,bpm,utc_offset_min FROM hr_samples WHERE user_id=? AND ts>=? AND ts<? AND {clock}>=? AND {clock}<? ORDER BY ts', (user, lower-86400 if civil else lower, upper+86400 if civil else upper, lower, upper))
                points = [{'heartRate': {'beatsPerMinute': r['bpm'], 'sampleTime': {'physicalTime': datetime.fromtimestamp(r['ts'], timezone.utc).isoformat(), 'utcOffset': f"{r['utc_offset_min']*60}s"}}} for r in rows]
                return points  # The SQL already applied civil/physical bounds.
            elif kind == 'heart-rate-variability':
                rows = conn.execute('SELECT * FROM hrv_samples WHERE user_id=? AND ts>=? AND ts<? ORDER BY ts', (user, lower, upper))
                return [{'heartRateVariability': {'sampleTime': {'physicalTime': datetime.fromtimestamp(r['ts'], timezone.utc).isoformat(), 'utcOffset': f"{r['utc_offset_min']*60}s"}, 'rootMeanSquareOfSuccessiveDifferencesMilliseconds': r['rmssd_ms']}} for r in rows]
            elif kind == 'activity-level':
                types = {'sedentary': 'SEDENTARY', 'light': 'LIGHTLY_ACTIVE', 'moderate': 'MODERATELY_ACTIVE', 'very_active': 'VERY_ACTIVE'}
                clock = 'start_ts+utc_offset_min*60' if query.field.endswith('.civil_start_time') else 'start_ts'
                rows = conn.execute(f'SELECT * FROM activity_level_intervals WHERE user_id=? AND {clock}>=? AND {clock}<? ORDER BY start_ts', (user, lower, upper))
                return [{'activityLevel': {'activityLevelType': types[r['level']], 'interval': {'startTime': datetime.fromtimestamp(r['start_ts'], timezone.utc).isoformat(), 'endTime': datetime.fromtimestamp(r['end_ts'], timezone.utc).isoformat(), 'startUtcOffset': f"{r['utc_offset_min']*60}s", 'endUtcOffset': f"{r['utc_offset_min']*60}s"}}} for r in rows]
            elif kind in ('sleep', 'exercise'):
                table, identity = ('sleep_sessions', 'provider_sleep_id') if kind == 'sleep' else ('activities', 'provider_activity_id')
                selected = conn.execute(f'SELECT {identity},payload_id FROM {table} WHERE user_id=? AND end_ts>=? AND start_ts<?', (user, lower-86400, upper+86400)).fetchall()
                pages = {}
                points = []
                for row in selected:
                    pid = row['payload_id']
                    if pid not in pages:
                        payload = conn.execute('SELECT payload FROM raw_payloads WHERE payload_id=?', (pid,)).fetchone()
                        pages[pid] = {p.get('name'): p for p in json.loads(payload[0]).get('dataPoints', [])} if payload else {}
                    if row[identity] in pages[pid]:
                        points.append(pages[pid][row[identity]])
            elif kind in DAILY:
                root, fields = DAILY[kind]
                codes = tuple(fields.values())
                rows = conn.execute(f'SELECT * FROM daily_measurements WHERE user_id=? AND metric_code IN ({",".join("?" for _ in codes)}) AND metric_date>=? AND metric_date<?', (user, *codes, query.start[:10], query.end[:10])).fetchall()
                grouped = {}
                reverse = {code: field for field, code in fields.items()}
                for row in rows:
                    day = date.fromisoformat(row['metric_date'])
                    metric = grouped.setdefault(row['metric_date'], {'date': {'year': day.year, 'month': day.month, 'day': day.day}})
                    metric[reverse[row['metric_code']]] = row['value']
                    if kind == 'daily-vo2-max':
                        metric['estimated'] = bool(row['is_estimated'])
                points = [{root: metric} for metric in grouped.values()]
            else:
                # Payload dedup by resource ID; latest successful observation wins.
                rows = conn.execute('SELECT payload FROM raw_payloads p JOIN provider_accounts a USING(provider_account_id) WHERE a.user_id=? AND p.dataset=? ORDER BY p.fetched_at,p.payload_id', (user, kind))
                indexed = {}
                for row in rows:
                    for point in json.loads(row['payload']).get('dataPoints', []):
                        indexed[point.get('name') or json_text(point)] = point
                points = list(indexed.values())
        return [p for p in points if (stamp := point_clock(p, query.field)) is not None and query.start <= stamp < query.end]
