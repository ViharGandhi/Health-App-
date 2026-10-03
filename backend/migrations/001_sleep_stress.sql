CREATE TABLE IF NOT EXISTS sleep_stress (
    sleep_id TEXT PRIMARY KEY,
    night_date TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    algo_version TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sleep_stress_windows (
    sleep_id TEXT NOT NULL,
    start_utc TEXT NOT NULL,
    end_utc TEXT NOT NULL,
    stage TEXT NOT NULL,
    ln_hrv REAL NOT NULL,
    hr REAL NOT NULL,
    minutes REAL NOT NULL,
    PRIMARY KEY (sleep_id, start_utc),
    FOREIGN KEY (sleep_id) REFERENCES sleep_stress(sleep_id) ON DELETE CASCADE
);
