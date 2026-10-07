"""Durable, account-scoped Google reads and authoritative range coverage.

Recent slices stay fresh for 15 minutes, older slices for a day. Successful
empty reads count as coverage; failed/partial paginated reads never do.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time


RECENT_TTL = 15 * 60
HISTORY_TTL = 24 * 60 * 60


class CacheInvalidated(Exception):
    """An explicit refresh happened while a Google read was in flight."""


def clock(value: str) -> str:
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo:
        stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
    return stamp.isoformat(timespec='microseconds')


@dataclass(frozen=True)
class ReadRange:
    field: str
    start: str
    end: str

    def expression(self, start: str, end: str) -> str:
        def bound(value):
            if self.field.endswith('.physical_time'):
                return value + 'Z'
            if value.endswith('T00:00:00.000000'):
                return value[:10]
            return value
        return f'{self.field} >= "{bound(start)}" AND {self.field} < "{bound(end)}"'


def read_range(expression: str) -> ReadRange | None:
    match = re.fullmatch(r'([a-z_.]+) >= "([^"]+)" AND \1 < "([^"]+)"', expression)
    if not match:
        return None
    try:
        field, start, end = match.groups()
        return ReadRange(field, clock(start), clock(end)) if clock(start) < clock(end) else None
    except ValueError:
        return None


def _camel(value: str) -> str:
    words = value.split('_')
    return words[0] + ''.join(w.title() for w in words[1:])


def point_clock(point: dict, field: str) -> str | None:
    """Read JSON observation times, including Google's synthetic civil filters."""
    try:
        parts = field.split('.')
        value = point
        for part in parts[:-1]:
            value = value[_camel(part)]
        last = parts[-1]
        if last in ('civil_end_time', 'civil_start_time'):
            prefix = 'end' if last == 'civil_end_time' else 'start'
            instant = datetime.fromisoformat(value[prefix + 'Time'].replace('Z', '+00:00'))
            offset = float(value.get(prefix + 'UtcOffset', '0s').removesuffix('s'))
            return clock((instant.astimezone(timezone.utc).replace(tzinfo=None) + timedelta(seconds=offset)).isoformat())
        item = value[_camel(last)]
        if isinstance(item, str):
            return clock(item)
        day = item if last == 'date' else item['date']
        tod = {} if last == 'date' else item.get('time', {})
        return clock(datetime(day['year'], day['month'], day['day'], tod.get('hours', 0),
                              tod.get('minutes', 0), tod.get('seconds', 0),
                              tod.get('nanos', 0) // 1000).isoformat())
    except (KeyError, ValueError, TypeError, OverflowError):
        return None


class HealthReadStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS read_slices (
                    account TEXT NOT NULL, kind TEXT NOT NULL, field TEXT NOT NULL,
                    reconciled INTEGER NOT NULL, lower_bound TEXT NOT NULL, upper_bound TEXT NOT NULL,
                    fetched REAL NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(account,kind,field,reconciled,lower_bound,upper_bound));
                CREATE INDEX IF NOT EXISTS read_slice_ranges ON read_slices(account,kind,field,reconciled,lower_bound,upper_bound);
                CREATE TABLE IF NOT EXISTS exact_reads (
                    account TEXT NOT NULL, key TEXT NOT NULL, fetched REAL NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(account,key));
                CREATE TABLE IF NOT EXISTS cache_epochs (account TEXT PRIMARY KEY, epoch INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS calculation_versions (account TEXT PRIMARY KEY, version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS page_snapshots (
                    account TEXT NOT NULL, key TEXT NOT NULL, epoch INTEGER NOT NULL,
                    updated REAL NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(account,key));
                CREATE TABLE IF NOT EXISTS calculated_days (
                    account TEXT NOT NULL, key TEXT NOT NULL, version INTEGER NOT NULL,
                    expires REAL NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(account,key));
                CREATE TABLE IF NOT EXISTS read_points (
                    account TEXT NOT NULL, kind TEXT NOT NULL, field TEXT NOT NULL,
                    reconciled INTEGER NOT NULL, lower_bound TEXT NOT NULL, upper_bound TEXT NOT NULL,
                    stamp TEXT NOT NULL, point_key TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(account,kind,field,reconciled,lower_bound,upper_bound,stamp,point_key));
            ''')
            if 'indexed' not in {r[1] for r in conn.execute('PRAGMA table_info(read_slices)')}:
                conn.execute('ALTER TABLE read_slices ADD COLUMN indexed INTEGER NOT NULL DEFAULT 0')
            # Upgrade existing snapshots once; subsequent reads use indexed times.
            with conn:
                for row in conn.execute('SELECT account,kind,field,reconciled,lower_bound,upper_bound,payload FROM read_slices WHERE indexed=0').fetchall():
                    self._index_slice(conn, row[:6], json.loads(row[6]))

    @staticmethod
    def _index_slice(conn, identity, points):
        conn.execute('DELETE FROM read_points WHERE account=? AND kind=? AND field=? AND reconciled=? AND lower_bound=? AND upper_bound=?', identity)
        values = []
        for point in points:
            stamp = point_clock(point, identity[2])
            payload = json.dumps(point, sort_keys=True, separators=(',', ':'))
            key = point.get('name') or hashlib.sha256(payload.encode()).hexdigest()
            if stamp is not None:
                values.append((*identity, stamp, key, payload))
        conn.executemany('INSERT OR IGNORE INTO read_points VALUES (?,?,?,?,?,?,?,?,?)', values)
        conn.execute('UPDATE read_slices SET indexed=1 WHERE account=? AND kind=? AND field=? AND reconciled=? AND lower_bound=? AND upper_bound=?', identity)

    def connection(self):
        return closing(sqlite3.connect(self.path, timeout=30))

    @staticmethod
    def cutoff(now: float) -> str:
        # Three complete days of overlap catch late sleep and wearable updates.
        return clock((datetime.fromtimestamp(now, timezone.utc) - timedelta(days=3)).date().isoformat())

    def range_read(self, account: str, kind: str, query: ReadRange, reconciled: bool,
                   *, now: float | None = None) -> tuple[list[dict], list[tuple[str, str]]]:
        now = time.time() if now is None else now
        with self.connection() as conn:
            rows = conn.execute('''SELECT lower_bound,upper_bound,fetched FROM read_slices
                WHERE account=? AND kind=? AND field=? AND reconciled=?
                AND lower_bound < ? AND upper_bound > ? ORDER BY fetched DESC,rowid DESC''',
                (account, kind, query.field, reconciled, query.end, query.start)).fetchall()
        fresh = [r for r in rows if now - r[2] < (HISTORY_TTL if r[1] <= self.cutoff(now) else RECENT_TTL)]
        coverage = sorted((max(query.start, r[0]), min(query.end, r[1])) for r in fresh)
        missing, cursor = [], query.start
        for lower, upper in coverage:
            if lower > cursor:
                missing.append((cursor, lower))
            cursor = max(cursor, upper)
        if cursor < query.end:
            missing.append((cursor, query.end))
        points, seen, newer = [], set(), []
        # A newer slice is authoritative even when empty (corrections/deletions).
        with self.connection() as conn:
            for lower, upper, _ in fresh:
                rows = conn.execute('''SELECT stamp,point_key,payload FROM read_points
                    WHERE account=? AND kind=? AND field=? AND reconciled=? AND lower_bound=? AND upper_bound=?
                    AND stamp>=? AND stamp<? ORDER BY stamp''',
                    (account, kind, query.field, reconciled, lower, upper, query.start, query.end))
                for stamp, key, payload in rows:
                    if any(a <= stamp < b for a, b in newer):
                        continue
                    if key not in seen:
                        seen.add(key)
                        points.append(json.loads(payload))
                newer.append((lower, upper))
        return points, missing

    def range_write(self, account: str, kind: str, query: ReadRange, reconciled: bool,
                    points: list[dict], *, now: float | None = None, epoch: int | None = None) -> bool:
        now = time.time() if now is None else now
        positions = [point_clock(p, query.field) for p in points]
        if any(p is None for p in positions):
            return False  # Unknown schema must not become falsely empty coverage.
        cutoff = self.cutoff(now)
        bounds = [query.start] + ([cutoff] if query.start < cutoff < query.end else []) + [query.end]
        with self.connection() as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            self._check_epoch(conn, account, epoch)
            for lower, upper in zip(bounds, bounds[1:]):
                payload = [p for p, stamp in zip(points, positions) if lower <= stamp < upper]
                serialized = json.dumps(payload)
                identity = (account, kind, query.field, reconciled, lower, upper)
                previous = conn.execute('SELECT payload FROM read_slices WHERE account=? AND kind=? AND field=? AND reconciled=? AND lower_bound=? AND upper_bound=?', identity).fetchone()
                unchanged = previous is not None and previous[0] == serialized
                if not unchanged and kind in ('heart-rate', 'sleep', 'exercise', 'daily-resting-heart-rate'):
                    # Only changed readings invalidate scores; a freshness check
                    # with identical data must retain saved historical results.
                    lower_day = datetime.fromisoformat(lower).date() - timedelta(days=2)
                    upper_day = datetime.fromisoformat(upper).date() + timedelta(days=7 if kind == 'daily-resting-heart-rate' else 2)
                    self._invalidate_days(conn, account, lower_day.isoformat(), upper_day.isoformat())
                if unchanged:
                    conn.execute('UPDATE read_slices SET fetched=? WHERE account=? AND kind=? AND field=? AND reconciled=? AND lower_bound=? AND upper_bound=?', (now, *identity))
                    continue
                conn.execute('''INSERT OR REPLACE INTO read_slices
                    (account,kind,field,reconciled,lower_bound,upper_bound,fetched,payload) VALUES (?,?,?,?,?,?,?,?)''',
                             (*identity, now, serialized))
                self._index_slice(conn, identity, payload)
                conn.execute('''DELETE FROM read_points WHERE account=? AND kind=? AND field=? AND reconciled=?
                    AND lower_bound>=? AND upper_bound<=? AND (lower_bound!=? OR upper_bound!=?)
                    AND EXISTS (SELECT 1 FROM read_slices s WHERE s.account=read_points.account AND s.kind=read_points.kind
                        AND s.field=read_points.field AND s.reconciled=read_points.reconciled
                        AND s.lower_bound=read_points.lower_bound AND s.upper_bound=read_points.upper_bound AND s.fetched<?)''',
                    (account, kind, query.field, reconciled, lower, upper, lower, upper, now))
                conn.execute('''DELETE FROM read_slices WHERE account=? AND kind=? AND field=? AND reconciled=?
                    AND lower_bound>=? AND upper_bound<=? AND fetched<?''',
                             (account, kind, query.field, reconciled, lower, upper, now))
        return True

    def exact_read(self, account: str, key: str, *, now: float | None = None):
        with self.connection() as conn:
            row = conn.execute('SELECT fetched,payload FROM exact_reads WHERE account=? AND key=?', (account, key)).fetchone()
        if row and (time.time() if now is None else now) - row[0] < RECENT_TTL:
            return json.loads(row[1])
        return None

    def exact_write(self, account: str, key: str, value, *, now: float | None = None, epoch: int | None = None):
        with self.connection() as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            self._check_epoch(conn, account, epoch)
            conn.execute('INSERT OR REPLACE INTO exact_reads VALUES (?,?,?,?)',
                         (account, key, time.time() if now is None else now, json.dumps(value)))

    def expire_recent(self, account: str):
        with self.connection() as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            self._invalidate_days(conn, account)
            conn.execute('INSERT INTO cache_epochs VALUES (?,1) ON CONFLICT(account) DO UPDATE SET epoch=epoch+1', (account,))
            conn.execute('UPDATE read_slices SET fetched=0 WHERE account=? AND upper_bound>?', (account, self.cutoff(time.time())))
            conn.execute('DELETE FROM exact_reads WHERE account=?', (account,))

    @staticmethod
    def _invalidate_days(conn, account, start=None, end=None):
        conn.execute('INSERT INTO calculation_versions VALUES (?,1) ON CONFLICT(account) DO UPDATE SET version=version+1', (account,))
        if start is None:
            conn.execute('DELETE FROM calculated_days WHERE account=?', (account,))
        else:
            conn.execute('DELETE FROM calculated_days WHERE account=? AND substr(key,-10)>=? AND substr(key,-10)<=?', (account, start, end))

    def calculation_version(self, account):
        with self.connection() as conn:
            row = conn.execute('SELECT version FROM calculation_versions WHERE account=?', (account,)).fetchone()
        return row[0] if row else 0

    def days_read(self, account, keys, *, now=None):
        if not keys:
            return {}
        with self.connection() as conn:
            rows = conn.execute(f'''SELECT key,payload FROM calculated_days WHERE account=?
                AND expires>?
                AND key IN ({','.join('?' for _ in keys)})''',
                (account, time.time() if now is None else now, *keys)).fetchall()
        return dict(rows)

    def days_write(self, account, entries, version):
        with self.connection() as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            current = conn.execute('SELECT version FROM calculation_versions WHERE account=?', (account,)).fetchone()
            if version != (current[0] if current else 0):
                return False
            conn.executemany('INSERT OR REPLACE INTO calculated_days VALUES (?,?,?,?,?)',
                             [(account, key, version, expires, payload) for key, expires, payload in entries])
        return True

    def epoch(self, account: str) -> int:
        with self.connection() as conn:
            row = conn.execute('SELECT epoch FROM cache_epochs WHERE account=?', (account,)).fetchone()
        return row[0] if row else 0

    def snapshot_read(self, account, key, *, now=None):
        with self.connection() as conn:
            row = conn.execute('''SELECT updated,payload FROM page_snapshots WHERE account=? AND key=?
                AND epoch=COALESCE((SELECT epoch FROM cache_epochs WHERE account=?),0)''',
                (account, key, account)).fetchone()
        if row and (time.time() if now is None else now) - row[0] < 86400:
            return row[0], json.loads(row[1])
        return None

    def snapshot_write(self, account, key, payload, epoch, *, now=None):
        with self.connection() as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            self._check_epoch(conn, account, epoch)
            conn.execute('INSERT OR REPLACE INTO page_snapshots VALUES (?,?,?,?,?)',
                         (account, key, epoch, time.time() if now is None else now, json.dumps(payload)))

    @staticmethod
    def _check_epoch(conn, account, epoch):
        row = conn.execute('SELECT epoch FROM cache_epochs WHERE account=?', (account,)).fetchone()
        if epoch is not None and epoch != (row[0] if row else 0):
            raise CacheInvalidated()

    def status(self, account: str):
        with self.connection() as conn:
            row = conn.execute('''SELECT MAX(fetched), COUNT(*) FROM (
                SELECT fetched FROM read_slices WHERE account=? UNION ALL
                SELECT fetched FROM exact_reads WHERE account=?)''', (account, account)).fetchone()
        return {'last_synced_at': datetime.fromtimestamp(row[0], timezone.utc).isoformat() if row[0] else None,
                'stored_ranges': row[1]}


def exact_key(kind: str, expression: str, reconciled: bool) -> str:
    return hashlib.sha256(json.dumps([kind, expression, reconciled]).encode()).hexdigest()
