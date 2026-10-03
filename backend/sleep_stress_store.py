"""SQLite upserts for reproducible sleep stress results and valid windows."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from sleep_stress import NightWindows


MIGRATION = Path(__file__).with_name("migrations") / "001_sleep_stress.sql"


class SleepStressStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(MIGRATION.read_text(encoding="utf-8"))

    def upsert(self, result: dict, source: NightWindows) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                "INSERT INTO sleep_stress (sleep_id, night_date, computed_at, algo_version, payload) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(sleep_id) DO UPDATE SET "
                "night_date=excluded.night_date, computed_at=excluded.computed_at, "
                "algo_version=excluded.algo_version, payload=excluded.payload",
                (result["sleep_id"], result["night_date"], result["computed_at"],
                 result["algo_version"], json.dumps(result)),
            )
            connection.execute("DELETE FROM sleep_stress_windows WHERE sleep_id = ?", (result["sleep_id"],))
            connection.executemany(
                "INSERT INTO sleep_stress_windows VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(result["sleep_id"], window.start_utc.isoformat(), window.end_utc.isoformat(),
                  window.stage, window.ln_hrv, window.hr, window.minutes)
                 for window in source.windows],
            )

    def get(self, sleep_id: str) -> dict | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT payload FROM sleep_stress WHERE sleep_id = ?", (sleep_id,)).fetchone()
        return json.loads(row[0]) if row else None
