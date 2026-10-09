"""Assemble Google inputs, cache daily calculations, and serialize cardio strain."""
import asyncio
from bisect import bisect_left, bisect_right
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
import math
import time
import hashlib
import json

from google_health_client import _local_datetime
from models import StrainResponse
from strain import StrainConfig, calculate_strain, day_window, strain_analytics


_daily_cache = OrderedDict()
_calculation_locks = {}


def _encode_day(value):
    if isinstance(value, datetime):
        return {'_datetime': value.isoformat()}
    if isinstance(value, date):
        return {'_date': value.isoformat()}
    raise TypeError(type(value).__name__)


def _decode_day(value):
    if set(value) == {'_datetime'}:
        return datetime.fromisoformat(value['_datetime'])
    if set(value) == {'_date'}:
        return date.fromisoformat(value['_date'])
    return value


async def load_strain_days(client, start, end, now, age, config=StrainConfig()):
    """Reuse durable daily results before loading any raw heart-rate history."""
    tz = getattr(client, 'strain_timezone', timezone.utc)
    sex = getattr(client, 'strain_sex', 'm')
    defaulted = getattr(client, 'strain_sex_defaulted', True)
    store = getattr(client, 'store', None)
    if store is None:
        inputs = await fetch_strain_inputs(client, start, end)
        values = calculate_days(start, end, now, tz, age, sex, defaulted, inputs, config,
                                getattr(client, 'account_key', None))
        return values, inputs[1]
    account = client.account_key
    profile = hashlib.sha256(repr(('strain-v2', str(tz), age, sex, defaulted, config)).encode()).hexdigest()
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    keys = {day: f'{profile}:{day}' for day in days}
    lock = _calculation_locks.setdefault((asyncio.get_running_loop(), account, profile), asyncio.Lock())
    async with lock:
        cached = await asyncio.to_thread(store.days_read, account, list(keys.values()),
                                         now=0 if getattr(client, 'stored_only', False) else None)
        values = {day: json.loads(cached[key], object_hook=_decode_day) for day, key in keys.items() if key in cached}
        missing = [day for day in days if day not in values]
        if missing:
            # Only expired/missing days need raw inputs, rather than the whole month.
            lower, upper = min(missing), max(missing)
            inputs = await fetch_strain_inputs(client, lower, upper)
            version = await asyncio.to_thread(store.calculation_version, account)
            calculated = await asyncio.to_thread(calculate_days, lower, upper, now, tz,
                                                 age, sex, defaulted, inputs, config)
            entries = []
            today = now.astimezone(tz).date()
            for day, value in calculated.items():
                window = value['day_window']
                value['_sessions'] = [s for s in inputs[1] if s['end'] >= window['start'] and s['start'] <= window['end']]
                ttl = 60 if day == today else 900 if day >= today - timedelta(days=3) else 86400
                entries.append((keys[day], time.time() + ttl, json.dumps(value, default=_encode_day)))
            await asyncio.to_thread(store.days_write, account, entries, version)
            values.update(calculated)
        sessions = {}
        for value in values.values():
            for session in value.get('_sessions', []):
                sessions[(session['start'], session['end'], session['activity_name'])] = session
        return {day: values[day] for day in days}, list(sessions.values())


def sleep_windows(points: list[dict]) -> list[dict]:
    sleeps = {}
    for point in points:
        sleep = point.get('sleep', {})
        interval = sleep.get('interval', {})
        if not interval.get('startTime') or not interval.get('endTime'):
            continue
        start = _local_datetime(interval['startTime'], interval.get('startUtcOffset', '0s'), preserve_offset=True)
        end = _local_datetime(interval['endTime'], interval.get('endUtcOffset', '0s'), preserve_offset=True)
        if end <= start:
            continue
        metadata = sleep.get('metadata', {})
        sleeps[(start, end)] = {'start': start, 'end': end, 'nap': metadata.get('nap', False),
                                'main_sleep': metadata.get('mainSleep')}
    return list(sleeps.values())


async def fetch_strain_inputs(client, start: date, end: date):
    # Extra dates cover sleeps and activities spanning midnight, plus 7 RHR nights.
    samples, sessions, points, health = await asyncio.gather(
        client.get_intraday_heart_rate(start - timedelta(days=2), end + timedelta(days=1), preserve_offset=True),
        client.get_workout_sessions(start - timedelta(days=2), end + timedelta(days=1), preserve_offset=True),
        client.get_sleep_stage_points(start - timedelta(days=2), end + timedelta(days=2)),
        client.get_health_history(start - timedelta(days=6), end, ('rhr',)),
    )
    rhrs = {date.fromisoformat(item['date']): item['value'] for item in health.get('rhr', [])}
    return samples, sessions, sleep_windows(points), rhrs


def calculate_days(start: date, end: date, now: datetime, tz, age, sex, sex_defaulted,
                   inputs, config=StrainConfig(), account=None):
    samples, sessions, sleeps, rhrs = inputs
    timestamps = None
    results = {}
    day = start
    while day <= end:
        key = (account, day, str(tz), age, sex, sex_defaulted, config)
        cached = _daily_cache.get(key) if account else None
        if cached and cached[0] > time.monotonic():
            results[day] = cached[1]
            _daily_cache.move_to_end(key)
        else:
            if timestamps is None:
                samples = sorted(samples, key=lambda item: item[0].astimezone(timezone.utc))
                timestamps = [stamp.astimezone(timezone.utc) for stamp, _ in samples]
            window = day_window(day, now, sleeps, tz, config)
            rest = [rhrs[day - timedelta(days=i)] for i in range(6, -1, -1) if day - timedelta(days=i) in rhrs]
            left = bisect_left(timestamps, window['start'].astimezone(timezone.utc))
            right = bisect_right(timestamps, window['end'].astimezone(timezone.utc))
            value = calculate_strain(samples[left:right], sessions, window, age, rest, sex, sex_defaulted, config)
            value.update(date=day, day_window=window)
            results[day] = value
            if account:
                expiry = 60 if day == now.astimezone(tz).date() else 6 * 3600
                _daily_cache[key] = (time.monotonic() + expiry, value)
                while len(_daily_cache) > 4096:
                    _daily_cache.popitem(last=False)
        day += timedelta(days=1)
    return results


def strain_response(current, history, mode, age, recovery=None, config=StrainConfig()):
    def rounded(value, places=1):
        return round(value, places) if value is not None else None
    score = current['strain']
    response = StrainResponse(
        date=current['date'].isoformat(), mode=mode, day_window=current['day_window'],
        strain=rounded(score), label=current['label'], load=rounded(current['load']),
        coverage=current['coverage'], low_coverage=current['low_coverage'], calibrating=current['calibrating'],
        age_missing=current['age_missing'], params=current['params'],
        analytics=strain_analytics(list(history.values()), current['date'], score, recovery, config),
        suggested_workouts=[{**w, 'avg_hr': rounded(w['avg_hr'])} for w in current['suggested_workouts']],
        score_21=rounded(score), score_100=rounded(score / 21 * 100) if score is not None else None,
        workout_strain=rounded(current['workout_load']), incidental_strain=rounded(current['incidental_load']),
        zone_minutes=current['zone_minutes'], activity_zone_minutes=current['activity_zone_minutes'],
        workouts=[{**w, 'strain': rounded(w['strain']), 'load': rounded(w['load']), 'avg_hr': rounded(w['avg_hr'])} for w in current['workouts']],
        avg_hr=rounded(current['avg_hr']), max_hr=current['max_hr'], age_used=age,
        age_is_default=current['age_missing'], is_calibrating=current['calibrating'], is_mock=mode == 'demo',
        sample_count=current['sample_count'], counted_minutes=current['counted_minutes'],
    )
    response._raw_strain = score
    for workout, raw in zip(response.workouts, current['workouts']):
        workout._raw_strain = raw['strain']
    return response


def demo_inputs(start: date, end: date, tz):
    """Replay deterministic raw readings, never preset scores or load values."""
    samples, sessions, sleeps, rhrs, steps = [], [], [], {}, {}
    scenarios = [(135, 45), (160, 45), (None, 0), (135, 45), (160, 45), (172, 60), (160, 45)]
    day = start - timedelta(days=7)
    while day <= end + timedelta(days=1):
        wake = datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(hours=7)
        sleeps.append({'start': wake - timedelta(hours=8), 'end': wake, 'main_sleep': True})
        rhrs[day] = 56.
        hr, duration = scenarios[(day - date(2026, 10, 7)).days % 7]
        workout_start = wake + timedelta(hours=10)
        workout_end = workout_start + timedelta(minutes=duration)
        if hr:
            sessions.append({'start': workout_start, 'end': workout_end, 'activity_name': 'Tempo Run' if hr == 160 else 'Easy Jog' if hr == 135 else 'Hard Run',
                             'exercise_type': 'RUNNING', 'active_minutes': duration})
        if day.weekday() in (0, 3):
            sessions.append({'start': wake + timedelta(hours=5), 'end': wake + timedelta(hours=5, minutes=35),
                             'activity_name': 'Weightlifting', 'exercise_type': 'WEIGHTLIFTING', 'active_minutes': 30})
        for minute in range(901):
            stamp = wake + timedelta(minutes=minute)
            bpm = 68 + 6 * math.sin(minute / 83.333)
            if hr and workout_start <= stamp <= workout_end:
                ramp = min((stamp - workout_start).total_seconds() / 300, 1)
                bpm = 68 + (hr - 68) * ramp
            if day.weekday() in (0, 3) and wake + timedelta(hours=5) <= stamp <= wake + timedelta(hours=5, minutes=35):
                bpm = 125
            if wake + timedelta(hours=3) <= stamp <= wake + timedelta(hours=3, minutes=20):
                bpm = 120  # Unlogged effort: included once in day load, suggested separately.
            samples.append((stamp, bpm))
        steps[day] = 4200 + (duration * 145 if hr else 0)
        day += timedelta(days=1)
    return (samples, sessions, sleeps, rhrs), steps
