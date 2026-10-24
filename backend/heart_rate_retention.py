"""Persist daily HR summaries and main-sleep traces, never daytime samples."""
from datetime import datetime, timedelta, timezone
import math


SUMMARY_SQL = '''CREATE TABLE IF NOT EXISTS daily_intraday_hr (
    owner TEXT NOT NULL, day TEXT NOT NULL, average_bpm REAL,
    sample_count INTEGER NOT NULL, updated_at REAL NOT NULL,
    coverage_end TEXT NOT NULL,
    PRIMARY KEY(owner,day))'''


def sample(point):
    try:
        hr = point['heartRate']; clock = hr['sampleTime']
        stamp = datetime.fromisoformat(clock['physicalTime'].replace('Z', '+00:00'))
        raw = hr['beatsPerMinute']
        if stamp.tzinfo is None or isinstance(raw, bool):
            return None
        bpm = float(raw)
        if not math.isfinite(bpm) or not 30 <= bpm <= 230:
            return None
        local = stamp.astimezone(timezone(timedelta(seconds=float(clock.get('utcOffset', '0s').removesuffix('s')))))
        return stamp.timestamp(), local, bpm
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def night_windows(sleeps):
    windows = []
    for point in sleeps:
        try:
            sleep = point['sleep']; meta = sleep.get('metadata', {})
            if meta.get('nap') or meta.get('mainSleep') is False or meta.get('processed') is False:
                continue
            interval = sleep['interval']
            start = datetime.fromisoformat(interval['startTime'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(interval['endTime'].replace('Z', '+00:00'))
            if start.tzinfo and end.tzinfo and start < end:
                windows.append((start.timestamp(), end.timestamp()))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(set(windows))


def keep_night(points, windows):
    return [point for point in points if (value := sample(point)) is not None
            and any(start <= value[0] < end for start, end in windows)]


def save_daily(conn, owner, points, expression, fetched):
    """Replace a day's mean from a fresh midnight-to-now/full-day read.

    A sleep-only read or a delta must never overwrite a whole-day average.
    Timestamp deduplication prevents overlapping provider pages adding weight.
    """
    from health_read_store import read_range
    query = read_range(expression) if expression else None
    if query is None:
        return
    groups, conflicts = {}, set()
    for point in points:
        value = sample(point)
        if value is None:
            continue
        stamp, local, bpm = value
        key = (str(local.date()), stamp)
        if key in groups and groups[key][0] != bpm:
            conflicts.add(key)
        groups[key] = (bpm, local)
    days, ends = {}, {}
    for key, (bpm, local) in groups.items():
        if key in conflicts:
            continue
        # Compare query bounds in the same clock domain as the provider filter.
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
        if query.field.endswith('.physical_time'):
            midnight = midnight.astimezone(timezone.utc)
        start = midnight.replace(tzinfo=None).isoformat(timespec='microseconds')
        if not query.start <= start < query.end:
            continue
        days.setdefault(key[0], []).append(bpm)
        end = datetime.fromisoformat(query.end)
        if query.field.endswith('.physical_time'):
            end = end.replace(tzinfo=timezone.utc).astimezone(local.tzinfo).replace(tzinfo=None)
        ends[key[0]] = min(end, (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)).isoformat(timespec='microseconds')
    if not groups and query.start.endswith('T00:00:00.000000'):
        cursor = datetime.fromisoformat(query.start)
        until = datetime.fromisoformat(query.end)
        while cursor < until:
            day = str(cursor.date())
            days[day] = []
            ends[day] = min(until, cursor + timedelta(days=1)).isoformat(timespec='microseconds')
            cursor += timedelta(days=1)
    for day, values in days.items():
        conn.execute('''INSERT INTO daily_intraday_hr VALUES (?,?,?,?,?,?)
            ON CONFLICT(owner,day) DO UPDATE SET average_bpm=excluded.average_bpm,
            sample_count=excluded.sample_count,updated_at=excluded.updated_at,
            coverage_end=excluded.coverage_end
            WHERE excluded.updated_at>=daily_intraday_hr.updated_at
            AND excluded.coverage_end>=daily_intraday_hr.coverage_end''',
                     (str(owner), day, math.fsum(values)/len(values) if values else None, len(values), fetched,
                      ends[day]))


def cache_windows(conn, account):
    import json
    rows = conn.execute("SELECT DISTINCT payload FROM read_points WHERE account=? AND kind='sleep'", (account,))
    return night_windows(json.loads(row[0]) for row in rows)


def without_day_traces(payload):
    """Avoid reintroducing daytime traces via presentation caches."""
    if isinstance(payload, list):
        return [without_day_traces(item) for item in payload]
    if not isinstance(payload, dict):
        return payload
    return {key: ([] if key == 'heart_rate' else without_day_traces(value))
            for key, value in payload.items()
            if not (key == 'samples' and payload.get('method', '').startswith('AWAKE_'))}
