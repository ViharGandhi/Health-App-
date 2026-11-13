"""Read-only loader for real Fitbit Air readings in the local Google Health cache.

Nothing is written to the cache. Account keys are hashes; no identity is printed.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'backend' / 'data' / 'health_cache.sqlite3'


def _connect():
    return sqlite3.connect(f'file:{CACHE.as_posix()}?mode=ro', uri=True)


def _instant(text: str, offset: str | None) -> datetime:
    stamp = datetime.fromisoformat(text.replace('Z', '+00:00'))
    seconds = int(float((offset or '0s').rstrip('s')))
    return stamp.astimezone(timezone(timedelta(seconds=seconds)))


def accounts_with_heart_rate(min_samples: int = 100_000) -> list[str]:
    with _connect() as c:
        rows = c.execute("SELECT account, COUNT(*) FROM read_points WHERE kind='heart-rate' GROUP BY account").fetchall()
    return [account for account, count in rows if count >= min_samples]


def heart_rate(account: str) -> list[tuple[datetime, float]]:
    """Unique samples by physical time, in the wearer's recorded UTC offset."""
    unique = {}
    with _connect() as c:
        for (payload,) in c.execute("SELECT payload FROM read_points WHERE account=? AND kind='heart-rate'", (account,)):
            value = json.loads(payload)['heartRate']
            clock = value['sampleTime']
            stamp = _instant(clock['physicalTime'], clock.get('utcOffset'))
            unique.setdefault(stamp.astimezone(timezone.utc), (stamp, float(value['beatsPerMinute'])))
    return [unique[key] for key in sorted(unique)]


def exercises(account: str) -> list[dict]:
    found = {}
    with _connect() as c:
        for (payload,) in c.execute("SELECT payload FROM read_points WHERE account=? AND kind='exercise'", (account,)):
            value = json.loads(payload)
            exercise = value['exercise']
            interval = exercise['interval']
            start = _instant(interval['startTime'], interval.get('startUtcOffset'))
            end = _instant(interval['endTime'], interval.get('endUtcOffset'))
            found[(start, end)] = {'start': start, 'end': end, 'activity_name': exercise.get('displayName', 'Exercise'),
                                   'exercise_type': exercise.get('exerciseType'),
                                   'active_minutes': float(exercise.get('activeDuration', '0s').rstrip('s')) / 60}
    return sorted(found.values(), key=lambda s: s['start'])


def daily(account: str, kind: str, root: str, field: str) -> dict[date, float]:
    values = {}
    with _connect() as c:
        for (payload,) in c.execute("SELECT payload FROM read_points WHERE account=? AND kind=?", (account, kind)):
            value = json.loads(payload)[root]
            day = date(**value['date'])
            if field in value:
                values[day] = float(value[field])
    return dict(sorted(values.items()))
