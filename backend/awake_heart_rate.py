"""Daily raw-sample awake HR, excluding recorded sleeps and exercise.

The baseline for sleep date D belongs to civil date D-1, from that day's
main-sleep wake time to 22:00. Never average the chart's 15-minute medians.
"""
import asyncio
from datetime import datetime, time, timedelta, timezone
import json
import math
from statistics import mean

from sleep_selection import main_sleep_key
from provider_payload import payload_boundary

METHOD = 'AWAKE_RAW_MEAN_EXCLUDING_SLEEP_EXERCISE_V1'
_locks = {}


def instant(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('An observation timestamp must include its UTC offset')
    return stamp.astimezone(timezone.utc)


@payload_boundary
def calculate_awake_hr(day, tz, heart, sleeps, activities):
    cutoff = datetime.combine(day, time(22), tzinfo=tz).astimezone(timezone.utc)
    windows, candidates = [], []
    for point in sleeps:
        sleep = point['sleep']
        interval, meta = sleep['interval'], sleep.get('metadata', {})
        start, end = instant(interval['startTime']), instant(interval['endTime'])
        if end <= start:
            raise ValueError('Invalid sleep interval')
        windows.append((start, end))  # Naps and awake portions in bed excluded too.
        offset = timezone(timedelta(seconds=float(interval.get('endUtcOffset', '0s').removesuffix('s'))))
        if end.astimezone(offset).date() != day or end > cutoff or meta.get('nap') or meta.get('processed') is False:
            continue
        key = main_sleep_key(meta.get('mainSleep'), start, end, point.get('name', ''))
        if key is not None:
            minutes = sleep.get('summary', {}).get('minutesAfterWakeUp', 0)
            if isinstance(minutes, bool) or not math.isfinite(float(minutes)) or float(minutes) < 0:
                raise ValueError('Invalid wake offset')
            wake = end - timedelta(minutes=float(minutes))
            if not start < wake <= end:
                raise ValueError('Invalid wake time')
            candidates.append((key, wake))
    result = {'date': str(day), 'timezone': str(tz), 'method': METHOD,
              'cutoff': cutoff.isoformat(), 'wake_time': None, 'value': None,
              'sample_count': 0, 'excluded_sleep_samples': 0,
              'excluded_activity_samples': 0, 'status': 'no_main_sleep',
              'activity_intervals': []}
    if not candidates:
        return result
    wake = max(candidates, key=lambda item: item[0])[1]
    result['wake_time'] = wake.isoformat()
    # Use actual final wake time; the interval's post-wake in-bed tail is awake.
    windows = [(start, min(end, wake)) if start < wake <= end else (start, end)
               for start, end in windows]
    exercise = []
    for point in activities:
        interval = point['exercise']['interval']
        start, end = instant(interval['startTime']), instant(interval['endTime'])
        if end <= start:
            raise ValueError('Invalid activity interval')
        if start < cutoff and end > wake:
            exercise.append((start, end))
    result['activity_intervals'] = [{'start': start.isoformat(), 'end': end.isoformat()}
                                    for start, end in sorted(set(exercise))]
    samples, conflicts = {}, set()
    for point in heart:
        metric = point.get('heartRate', {})
        clock = metric.get('sampleTime', {})
        stamp = instant(clock['physicalTime'])
        raw = metric.get('beatsPerMinute')
        if isinstance(raw, bool):
            continue
        try:
            bpm = float(raw)
        except (ValueError, TypeError):
            continue
        if not math.isfinite(bpm) or not 30 <= bpm <= 230 or not wake <= stamp < cutoff:
            continue
        if stamp in samples and samples[stamp] != bpm:
            conflicts.add(stamp)
        samples[stamp] = bpm
    retained = []
    for stamp, bpm in sorted(samples.items()):
        if stamp in conflicts:
            continue
        if any(start <= stamp < end for start, end in windows):
            result['excluded_sleep_samples'] += 1
        elif any(start <= stamp < end for start, end in exercise):
            result['excluded_activity_samples'] += 1
        else:
            retained.append({'timestamp': stamp.isoformat(), 'bpm': bpm})
    result.update(value=mean(p['bpm'] for p in retained) if retained else None,
                  sample_count=len(retained), status='ok' if retained else 'no_readings',
                  )
    return result


def read_baseline(store, account, day, tz):
    with store.connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS awake_heart_rate (
            account TEXT NOT NULL, day TEXT NOT NULL, timezone TEXT NOT NULL,
            payload TEXT NOT NULL, PRIMARY KEY(account,day,timezone))''')
        row = conn.execute('SELECT payload FROM awake_heart_rate WHERE account=? AND day=? AND timezone=?',
                           (account, str(day), str(tz))).fetchone()
    return json.loads(row[0]) if row else None


def save_baseline(store, account, day, tz, result, epoch):
    read_baseline(store, account, day, tz)
    with store.connection() as conn, conn:
        store._check_epoch(conn, account, epoch)
        conn.execute('INSERT OR REPLACE INTO awake_heart_rate VALUES (?,?,?,?)',
                     (account, str(day), str(tz), json.dumps({k: v for k, v in result.items() if k != 'samples'})))
        store._invalidate_days(conn, account)
        # Frozen sleep pages must also be recalculated when a baseline changes.
        conn.execute('DELETE FROM page_snapshots WHERE account=?', (account,))
        conn.execute('INSERT INTO cache_epochs VALUES (?,1) ON CONFLICT(account) DO UPDATE SET epoch=epoch+1', (account,))


async def collect_awake_hr(client, day, *, force=False, now=None):
    if client.store is None:
        raise ValueError('A connected account is required')
    tz = client.strain_timezone
    now = now or datetime.now(timezone.utc)
    cutoff = datetime.combine(day, time(22), tzinfo=tz)
    if now < cutoff:
        raise ValueError('Awake heart rate can be finalized after 22:00 local time')
    lock = _locks.setdefault((asyncio.get_running_loop(), client.account_key, str(day), str(tz)), asyncio.Lock())
    async with lock:
        saved = await asyncio.to_thread(read_baseline, client.store, client.account_key, day, tz)
        if saved and saved['status'] == 'ok' and not force:
            return saved
        epoch = await asyncio.to_thread(client.store.epoch, client.account_key)
        # Fresh provider reads, independent of foreground stored-only mode.
        # Include the prior day's starts for sessions crossing midnight, plus
        # the next wake date so overnight sleeps overlapping the cutoff count.
        first, last = day - timedelta(days=1), day + timedelta(days=2)
        expressions = [
            ('heart-rate', f'heart_rate.sample_time.civil_time >= "{day}" AND heart_rate.sample_time.civil_time < "{day}T22:00:00"', True),
            ('sleep', f'sleep.interval.civil_end_time >= "{day}" AND sleep.interval.civil_end_time < "{last}"', False),
            ('exercise', f'exercise.interval.civil_start_time >= "{first}" AND exercise.interval.civil_start_time < "{day}T22:00:00"', True),
        ]
        heart, sleeps, activities = await asyncio.gather(*(
            client._fetch_points(kind, expression, reconcile=reconcile)
            for kind, expression, reconcile in expressions))
        result = calculate_awake_hr(day, tz, heart, sleeps, activities)
        result['calculated_at'] = now.isoformat()
        await asyncio.to_thread(save_baseline, client.store, client.account_key, day, tz, result, epoch)
        if getattr(client, 'database', None) is not None:
            from health_results import Results
            await asyncio.to_thread(Results(client.database, client.db_account['user_id'], day).awake, day, result)
        client._invalidate_calculations()
        return result


async def previous_awake_hr(client, sleep_day):
    if getattr(client, 'store', None) is None:
        return None
    day = sleep_day - timedelta(days=1)
    saved = await asyncio.to_thread(read_baseline, client.store, client.account_key, day, client.strain_timezone)
    if saved is None and getattr(client, 'database', None) is not None:
        from health_normalized_reads import awake_baseline
        saved = await asyncio.to_thread(awake_baseline, client.database, client.db_account['user_id'], day)
    return saved
