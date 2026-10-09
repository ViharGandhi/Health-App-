"""User-scoped SQLite stats, results and durable webhook jobs (no OAuth tokens)."""

from contextlib import closing
from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
from sleep_selection import main_sleep_key

from sleep_stage_ranges import (
    DEFAULT_CONFIG, ALGO_VERSION, STAGES, METRICS, score_stages, stats_from_dict, stats_to_dict,
)


class SleepStageStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.executescript((Path(__file__).with_name("migrations") / "002_sleep_stage_ranges.sql").read_text())

    def has_sessions(self, user_id):
        with closing(sqlite3.connect(self.path)) as conn:
            return conn.execute("SELECT 1 FROM sleep_stage_sessions WHERE user_id=? LIMIT 1", (user_id,)).fetchone() is not None

    def sync(self, user_id, observations, start: date | None, end: date, config=DEFAULT_CONFIG):
        """Replace the authoritative fetched wake-date slice, then recompute dependent baselines.

        Incomplete/CLASSIC corrections remove the old stats. Deleted or moved
        sessions disappear from the replaced interval. One transaction prevents
        readers observing half a resync. Unchanged results retain computed_at.
        """
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("DELETE FROM sleep_stage_sessions WHERE user_id=? AND night_date<=? AND (? IS NULL OR night_date>=?)",
                         (user_id, end.isoformat(), start.isoformat() if start else None, start.isoformat() if start else None))
            for night, stats, state in observations:
                conn.execute("INSERT INTO sleep_stage_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                             "ON CONFLICT(user_id,sleep_id) DO UPDATE SET night_date=excluded.night_date, "
                             "start_utc=excluded.start_utc,end_utc=excluded.end_utc,main_sleep=excluded.main_sleep,"
                             "state=excluded.state,stats=excluded.stats",
                             (user_id, night.sleep_id, night.night_date.isoformat(), night.start_utc.isoformat(),
                              night.end_utc.isoformat(), night.main_sleep, state, json.dumps(stats_to_dict(stats)) if stats else None))
            rows = conn.execute("SELECT sleep_id,night_date,start_utc,end_utc,main_sleep,state,stats "
                                "FROM sleep_stage_sessions WHERE user_id=? ORDER BY night_date,end_utc,sleep_id", (user_id,)).fetchall()
            by_date = {}
            for row in rows:
                if row[5] not in ("nap_excluded", "short_sleep_excluded"):
                    by_date.setdefault(row[1], []).append(row)
            selected = []
            for sessions in by_date.values():
                candidates = [(main_sleep_key(None if r[4] is None else bool(r[4]),
                    datetime.fromisoformat(r[2]), datetime.fromisoformat(r[3]), r[0]), r) for r in sessions]
                candidates = [(key, row) for key, row in candidates if key is not None]
                if candidates:
                    selected.append(max(candidates, key=lambda item: item[0])[1])
            stats = []
            for row in selected:
                if row[6]:
                    item = stats_from_dict(json.loads(row[6]))
                    # Persist stage minutes; the denominator is recomputed consistently on both sides.
                    asleep = sum(item.minutes[s] for s in ("light", "deep", "rem"))
                    if asleep < config.min_sleep_hours * 60:
                        continue
                    total = sum(item.minutes[s] for s in STAGES) if config.denominator == "time_in_bed" else asleep
                    stats.append(replace(item, total_minutes=total, denominator=config.denominator,
                                         pct={s: None if s == "awake" and config.denominator == "time_asleep"
                                              else 100 * item.minutes[s] / total for s in METRICS}))
            previous = {r[0]: json.loads(r[1]) for r in conn.execute(
                "SELECT sleep_id,payload FROM sleep_stage_results WHERE user_id=?", (user_id,))}
            conn.execute("DELETE FROM sleep_stage_results WHERE user_id=?", (user_id,))
            for row in selected:
                item = next((s for s in stats if s.sleep_id == row[0]), None)
                result = score_stages(item, stats, config) if item else {
                    "sleep_id": row[0], "night_date": row[1],
                    "status": "short_sleep_excluded" if row[6] else row[5], "stages": {},
                    "algo_version": ALGO_VERSION, "denominator": config.denominator,
                }
                old = previous.get(row[0], {})
                timestamp = old.get("computed_at") if {k: v for k, v in old.items() if k != "computed_at"} == result else None
                result["computed_at"] = timestamp or datetime.now(timezone.utc).isoformat()
                conn.execute("INSERT INTO sleep_stage_results VALUES (?, ?, ?, ?)",
                             (user_id, row[0], row[1], json.dumps(result)))

    def results(self, user_id, start: date, end: date):
        with closing(sqlite3.connect(self.path)) as conn:
            return [json.loads(r[0]) for r in conn.execute(
                "SELECT payload FROM sleep_stage_results WHERE user_id=? AND night_date BETWEEN ? AND ? ORDER BY night_date",
                (user_id, start.isoformat(), end.isoformat()))]

    def enqueue(self, user_id, key, start: date, end: date):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("INSERT INTO sleep_stage_jobs(user_id,job_key,start_date,end_date) VALUES(?,?,?,?) "
                         "ON CONFLICT(user_id,job_key) DO UPDATE SET start_date=min(start_date,excluded.start_date),"
                         "end_date=max(end_date,excluded.end_date),next_attempt=0,generation=generation+1",
                         (user_id, key, start.isoformat(), end.isoformat()))

    def jobs(self, user_id):
        with closing(sqlite3.connect(self.path)) as conn:
            return conn.execute("SELECT job_key,start_date,end_date,generation FROM sleep_stage_jobs "
                                "WHERE user_id=? AND next_attempt<=?", (user_id, time.time())).fetchall()

    def finish_job(self, user_id, key, generation, retry=False):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            if retry:
                conn.execute("UPDATE sleep_stage_jobs SET attempts=attempts+1,next_attempt=? WHERE user_id=? AND job_key=? AND generation=?",
                             (time.time() + 300, user_id, key, generation))
            else:
                conn.execute("DELETE FROM sleep_stage_jobs WHERE user_id=? AND job_key=? AND generation=?", (user_id, key, generation))
