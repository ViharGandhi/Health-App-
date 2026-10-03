CREATE TABLE IF NOT EXISTS sleep_stage_sessions (
    user_id TEXT NOT NULL,
    sleep_id TEXT NOT NULL,
    night_date TEXT NOT NULL,
    start_utc TEXT NOT NULL,
    end_utc TEXT NOT NULL,
    main_sleep INTEGER,
    state TEXT NOT NULL,
    stats TEXT,
    PRIMARY KEY (user_id, sleep_id)
);

CREATE TABLE IF NOT EXISTS sleep_stage_results (
    user_id TEXT NOT NULL,
    sleep_id TEXT NOT NULL,
    night_date TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (user_id, sleep_id)
);

CREATE TABLE IF NOT EXISTS sleep_stage_jobs (
    user_id TEXT NOT NULL,
    job_key TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt REAL NOT NULL DEFAULT 0,
    generation INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, job_key)
);
