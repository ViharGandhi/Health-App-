-- =====================================================================
--  HEALTH / WEARABLE APP  -  SQLite schema  (v1)
--  Requires SQLite >= 3.37 (STRICT tables). Tested on 3.45.
--
--  CONVENTIONS
--   * Instants      : INTEGER, Unix epoch SECONDS, UTC        (*_ts)
--   * Local time    : ts + utc_offset_min * 60   (offset stored beside every raw instant)
--   * Calendar days : TEXT 'YYYY-MM-DD'                       (*_date)
--   * Booleans      : INTEGER 0/1
--   * Percentages   : REAL on a 0-100 scale
--   * MISSING != 0  : unknown / withheld values are NULL + a status column, never 0
--   * Layers        : (1) ownership  (2) raw observations  (3) calculation framework
--                     (4) calculated results  (5) caches/ops.
--                     Layers 4 and 5 can be dropped and rebuilt from layers 1-2.
--
--  CONNECTION-LEVEL PRAGMAS (run on EVERY connection, they are not stored in the file):
--      PRAGMA foreign_keys = ON;
--      PRAGMA busy_timeout = 5000;
--      PRAGMA synchronous  = NORMAL;      -- safe with WAL
--  journal_mode=WAL below IS persistent in the file.
-- =====================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 0. SCHEMA VERSIONING
-- ---------------------------------------------------------------------
CREATE TABLE schema_migrations (
  version     INTEGER PRIMARY KEY,
  description TEXT    NOT NULL,
  applied_at  INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
) STRICT;

-- ---------------------------------------------------------------------
-- 1. OWNERSHIP
-- ---------------------------------------------------------------------
CREATE TABLE users (
  user_id      INTEGER PRIMARY KEY,
  email        TEXT,
  display_name TEXT,
  timezone     TEXT    NOT NULL DEFAULT 'UTC',         -- IANA name, e.g. 'Asia/Kolkata'
  created_at   INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
) STRICT;
CREATE UNIQUE INDEX ux_users_email ON users(email) WHERE email IS NOT NULL;

-- Age / sex / timezone are INPUTS to calculations, so they are versioned.
-- Every calc_run records which profile version it used.
CREATE TABLE user_profile_versions (
  profile_version_id  INTEGER PRIMARY KEY,
  user_id             INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  effective_from_date TEXT    NOT NULL CHECK (effective_from_date = date(effective_from_date)),
  birth_date          TEXT    CHECK (birth_date IS NULL OR birth_date = date(birth_date)),
  age_years           INTEGER CHECK (age_years IS NULL OR age_years BETWEEN 0 AND 120),  -- used if no birth_date
  sex                 TEXT    NOT NULL DEFAULT 'unknown' CHECK (sex IN ('female','male','other','unknown')),
  timezone            TEXT    NOT NULL,
  max_hr_override_bpm INTEGER,
  resting_hr_override_bpm INTEGER,
  created_at          INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
  UNIQUE (user_id, effective_from_date)
) STRICT;

CREATE TABLE provider_accounts (
  provider_account_id INTEGER PRIMARY KEY,
  user_id             INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  provider            TEXT    NOT NULL DEFAULT 'google_health',
  provider_user_id    TEXT    NOT NULL,                -- Google Health user ID
  email               TEXT,
  display_name        TEXT,
  status              TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked','error','disconnected')),
  connected_at        INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
  disconnected_at     INTEGER,
  UNIQUE (provider, provider_user_id)
) STRICT;
CREATE INDEX ix_provider_accounts_user ON provider_accounts(user_id);

-- Tokens MUST be encrypted by the app before insert (key id recorded for rotation).
-- Strongly consider keeping this table in a separate database file.
CREATE TABLE provider_credentials (
  provider_account_id INTEGER PRIMARY KEY REFERENCES provider_accounts(provider_account_id) ON DELETE CASCADE,
  access_token_enc    BLOB,
  refresh_token_enc   BLOB,
  key_id              TEXT,
  scopes              TEXT,
  access_expires_at   INTEGER,
  updated_at          INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
) STRICT;

-- ---------------------------------------------------------------------
-- 2a. OPERATIONS: SYNC + RAW PAYLOADS
-- ---------------------------------------------------------------------
CREATE TABLE sync_runs (
  sync_run_id         INTEGER PRIMARY KEY,
  provider_account_id INTEGER NOT NULL REFERENCES provider_accounts(provider_account_id) ON DELETE CASCADE,
  dataset             TEXT    NOT NULL,                -- 'heart_rate','sleep','activities','hrv_daily',...
  range_start_date    TEXT,
  range_end_date      TEXT,
  trigger             TEXT    NOT NULL DEFAULT 'scheduled' CHECK (trigger IN ('scheduled','manual','backfill')),
  status              TEXT    NOT NULL DEFAULT 'running' CHECK (status IN ('running','ok','partial','failed')),
  records_upserted    INTEGER NOT NULL DEFAULT 0,
  error_message       TEXT,
  started_at          INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
  finished_at         INTEGER
) STRICT;
CREATE INDEX ix_sync_runs_acct ON sync_runs(provider_account_id, dataset, started_at DESC);

CREATE TABLE sync_cursors (
  provider_account_id INTEGER NOT NULL REFERENCES provider_accounts(provider_account_id) ON DELETE CASCADE,
  dataset             TEXT    NOT NULL,
  last_synced_date    TEXT,
  last_synced_ts      INTEGER,
  last_success_run_id INTEGER REFERENCES sync_runs(sync_run_id) ON DELETE SET NULL,
  updated_at          INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
  PRIMARY KEY (provider_account_id, dataset)
) STRICT, WITHOUT ROWID;

-- Verbatim provider responses so formulas can change without re-downloading.
-- Hash-deduplicated. If this grows large, move it to an attached DB file.
CREATE TABLE raw_payloads (
  payload_id          INTEGER PRIMARY KEY,
  provider_account_id INTEGER NOT NULL REFERENCES provider_accounts(provider_account_id) ON DELETE CASCADE,
  sync_run_id         INTEGER REFERENCES sync_runs(sync_run_id) ON DELETE SET NULL,
  dataset             TEXT    NOT NULL,
  endpoint            TEXT,
  range_start_date    TEXT,
  range_end_date      TEXT,
  http_status         INTEGER,
  payload_sha256      TEXT    NOT NULL,
  payload             TEXT    NOT NULL CHECK (json_valid(payload)),
  fetched_at          INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
  UNIQUE (provider_account_id, dataset, payload_sha256)
) STRICT;

CREATE TABLE scheduled_jobs (
  job_id              INTEGER PRIMARY KEY,
  user_id             INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
  provider_account_id INTEGER REFERENCES provider_accounts(provider_account_id) ON DELETE CASCADE,
  job_type            TEXT    NOT NULL,                -- 'sync','recalculate','snapshot_rebuild'
  schedule_expr       TEXT    NOT NULL,                -- cron or interval text
  enabled             INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
  last_run_at         INTEGER,
  last_status         TEXT,
  next_run_at         INTEGER
) STRICT;

-- ---------------------------------------------------------------------
-- 2b. RAW OBSERVATIONS
-- ---------------------------------------------------------------------

-- Catalog of every daily metric (provider-sourced AND calculated).
CREATE TABLE metric_types (
  metric_code  TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  unit         TEXT NOT NULL,
  source       TEXT NOT NULL CHECK (source IN ('provider','calculated')),
  description  TEXT
) STRICT, WITHOUT ROWID;

INSERT INTO metric_types VALUES
 ('hrv_rmssd_avg',    'HRV (avg RMSSD)',        'ms',          'provider',   'Daily average RMSSD'),
 ('hrv_deep_rmssd',   'Deep-sleep HRV',         'ms',          'provider',   'Optional'),
 ('non_rem_hr',       'Non-REM heart rate',     'bpm',         'provider',   'Optional'),
 ('spo2_avg_pct',     'SpO2 average',           '%',           'provider',   NULL),
 ('respiratory_rate', 'Respiratory rate',       'breaths/min', 'provider',   NULL),
 ('skin_temp_c',      'Nightly skin temp',      'degC',        'provider',   NULL),
 ('vo2_max',          'VO2 max',                'mL/kg/min',   'provider',   'is_estimated flag on the row'),
 ('steps',            'Daily steps',            'count',       'provider',   'Daily roll-up only; NOT per workout'),
 ('resting_hr_calc',  'Resting HR (calculated)','bpm',         'calculated', 'From sleeping_hr_results; not downloaded from provider'),
 ('sleeping_hr',      'Sleeping HR',            'bpm',         'calculated', NULL),
 ('awake_hr',         'Awake HR',               'bpm',         'calculated', NULL);

-- One narrow table for all per-date provider measurements.
-- Date = the date the provider attributes the value to (for sleep-linked metrics, the wake date).
CREATE TABLE daily_measurements (
  user_id             INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  metric_code         TEXT    NOT NULL REFERENCES metric_types(metric_code),
  metric_date         TEXT    NOT NULL CHECK (metric_date = date(metric_date)),
  value               REAL    NOT NULL,                -- missing day => no row (never 0)
  is_estimated        INTEGER NOT NULL DEFAULT 0 CHECK (is_estimated IN (0,1)),
  provider_account_id INTEGER REFERENCES provider_accounts(provider_account_id) ON DELETE SET NULL,
  sync_run_id         INTEGER REFERENCES sync_runs(sync_run_id) ON DELETE SET NULL,
  payload_id          INTEGER REFERENCES raw_payloads(payload_id) ON DELETE SET NULL,
  fetched_at          INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
  PRIMARY KEY (user_id, metric_code, metric_date)
) STRICT, WITHOUT ROWID;

CREATE TRIGGER trg_daily_measurements_provider_only
BEFORE INSERT ON daily_measurements
WHEN (SELECT source FROM metric_types WHERE metric_code = NEW.metric_code) <> 'provider'
BEGIN
  SELECT RAISE(ABORT, 'daily_measurements only accepts provider-sourced metrics; store calculated values in result tables');
END;

-- Individual raw HR samples (highest-volume table). Clustered on (user, time).
CREATE TABLE hr_samples (
  user_id        INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  ts             INTEGER NOT NULL,
  bpm            INTEGER NOT NULL CHECK (bpm BETWEEN 1 AND 300),
  utc_offset_min INTEGER NOT NULL DEFAULT 0,
  sync_run_id    INTEGER REFERENCES sync_runs(sync_run_id) ON DELETE SET NULL,
  PRIMARY KEY (user_id, ts)
) STRICT, WITHOUT ROWID;

CREATE TABLE hrv_samples (
  user_id        INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  ts             INTEGER NOT NULL,                     -- window start
  window_seconds INTEGER,
  rmssd_ms       REAL    NOT NULL CHECK (rmssd_ms >= 0),
  timing_status  TEXT    NOT NULL DEFAULT 'unverified' CHECK (timing_status  IN ('verified','unverified')),
  quality_status TEXT    NOT NULL DEFAULT 'unknown'    CHECK (quality_status IN ('good','poor','rejected','unknown')),
  utc_offset_min INTEGER NOT NULL DEFAULT 0,
  sync_run_id    INTEGER REFERENCES sync_runs(sync_run_id) ON DELETE SET NULL,
  PRIMARY KEY (user_id, ts)
) STRICT, WITHOUT ROWID;

-- Sleep ------------------------------------------------------------------
CREATE TABLE sleep_sessions (
  sleep_session_id    INTEGER PRIMARY KEY,
  user_id             INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  provider_account_id INTEGER REFERENCES provider_accounts(provider_account_id) ON DELETE SET NULL,
  provider_sleep_id   TEXT    NOT NULL,
  start_ts            INTEGER NOT NULL,
  end_ts              INTEGER NOT NULL CHECK (end_ts > start_ts),
  start_offset_min    INTEGER NOT NULL DEFAULT 0,
  end_offset_min      INTEGER NOT NULL DEFAULT 0,
  is_main_sleep       INTEGER NOT NULL DEFAULT 0 CHECK (is_main_sleep IN (0,1)),
  is_nap              INTEGER NOT NULL DEFAULT 0 CHECK (is_nap IN (0,1)),
  is_processed        INTEGER NOT NULL DEFAULT 1 CHECK (is_processed IN (0,1)),
  -- Local calendar date of waking = the "sleep date" used by scores.
  sleep_date          TEXT GENERATED ALWAYS AS (date(end_ts + end_offset_min*60, 'unixepoch')) VIRTUAL,
  sync_run_id         INTEGER REFERENCES sync_runs(sync_run_id) ON DELETE SET NULL,
  payload_id          INTEGER REFERENCES raw_payloads(payload_id) ON DELETE SET NULL,
  UNIQUE (user_id, provider_sleep_id)
) STRICT;
CREATE INDEX ix_sleep_user_date ON sleep_sessions(user_id, sleep_date);
CREATE INDEX ix_sleep_user_time ON sleep_sessions(user_id, start_ts, end_ts);

CREATE TABLE sleep_summaries (
  sleep_session_id     INTEGER PRIMARY KEY REFERENCES sleep_sessions(sleep_session_id) ON DELETE CASCADE,
  minutes_asleep       INTEGER,
  minutes_awake        INTEGER,
  minutes_in_bed       INTEGER,
  minutes_to_fall_asleep INTEGER,
  minutes_after_waking INTEGER,
  deep_minutes         INTEGER,
  light_minutes        INTEGER,
  rem_minutes          INTEGER,
  wake_minutes         INTEGER,
  deep_count           INTEGER,
  light_count          INTEGER,
  rem_count            INTEGER,
  wake_count           INTEGER
) STRICT;

CREATE TABLE sleep_segments (
  sleep_session_id INTEGER NOT NULL REFERENCES sleep_sessions(sleep_session_id) ON DELETE CASCADE,
  start_ts         INTEGER NOT NULL,
  end_ts           INTEGER NOT NULL CHECK (end_ts > start_ts),
  kind             TEXT    NOT NULL CHECK (kind IN ('awake','light','deep','rem','short_awakening','out_of_bed')),
  PRIMARY KEY (sleep_session_id, start_ts, kind)
) STRICT, WITHOUT ROWID;

-- Activities --------------------------------------------------------------
CREATE TABLE activities (
  activity_id          INTEGER PRIMARY KEY,
  user_id              INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  provider_account_id  INTEGER REFERENCES provider_accounts(provider_account_id) ON DELETE SET NULL,
  provider_activity_id TEXT    NOT NULL,
  activity_type        TEXT,
  name                 TEXT,
  start_ts             INTEGER NOT NULL,
  end_ts               INTEGER NOT NULL CHECK (end_ts > start_ts),
  start_offset_min     INTEGER NOT NULL DEFAULT 0,
  end_offset_min       INTEGER NOT NULL DEFAULT 0,
  active_duration_s    INTEGER,
  start_local_date     TEXT GENERATED ALWAYS AS (date(start_ts + start_offset_min*60, 'unixepoch')) VIRTUAL,
  sync_run_id          INTEGER REFERENCES sync_runs(sync_run_id) ON DELETE SET NULL,
  payload_id           INTEGER REFERENCES raw_payloads(payload_id) ON DELETE SET NULL,
  -- NOTE: no calories / per-workout steps / GPS / cardio-muscular split columns.
  --       Those are demo-only today. Add dedicated tables when real provider data exists.
  UNIQUE (user_id, provider_activity_id)
) STRICT;
CREATE INDEX ix_activities_user_date ON activities(user_id, start_local_date);
CREATE INDEX ix_activities_user_time ON activities(user_id, start_ts, end_ts);

CREATE TABLE activity_level_intervals (
  user_id  INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  start_ts INTEGER NOT NULL,
  end_ts   INTEGER NOT NULL CHECK (end_ts > start_ts),
  level    TEXT    NOT NULL CHECK (level IN ('sedentary','light','moderate','very_active')),
  utc_offset_min INTEGER NOT NULL DEFAULT 0,
  sync_run_id INTEGER REFERENCES sync_runs(sync_run_id) ON DELETE SET NULL,
  PRIMARY KEY (user_id, start_ts)
) STRICT, WITHOUT ROWID;

-- ---------------------------------------------------------------------
-- 3. CALCULATION FRAMEWORK  (lineage, versioning, reuse)
--    calc_run = ONE execution of ONE algorithm for ONE subject.
--    Every result table below is keyed by calc_run_id, so every result
--    inherits: algorithm version, profile used, config, computed_at,
--    coverage, partial/default flags, input lineage.
-- ---------------------------------------------------------------------
CREATE TABLE algorithms (
  algorithm_code TEXT PRIMARY KEY,
  description    TEXT
) STRICT, WITHOUT ROWID;

INSERT INTO algorithms VALUES
 ('sleeping_hr',      'Time-weighted HR across light/deep/REM'),
 ('awake_hr',         'Mean HR wake-up to 22:00, excluding sleep/naps/activities'),
 ('sleep_nightly_vitals', 'HRV, sleeping HR, previous-day awake HR, HR dip'),
 ('sleep_metrics',    'Timing, duration, stages, efficiency, restfulness'),
 ('sleep_need',       'Baseline + strain + debt - nap credit'),
 ('sleep_score',      'Weighted composite sleep score'),
 ('sleep_consistency','Bed/wake timing consistency'),
 ('sleep_stage_compare','Stage minutes vs personal range'),
 ('daily_strain',     'TRIMP-based 0-21 strain'),
 ('workout',          'Per-workout load, zones, comparisons'),
 ('training_trend',   '7/28-day strain averages, acute:chronic ratio, strain target'),
 ('recovery',         'Recovery score from HRV/RHR vs personal reference + sleep'),
 ('stress_monitor',   'General Stress Monitor intervals + daily summary'),
 ('sleep_stress',     'High-stress detector during sleep');

CREATE TABLE algorithm_versions (
  algorithm_version_id INTEGER PRIMARY KEY,
  algorithm_code       TEXT NOT NULL REFERENCES algorithms(algorithm_code),
  version_label        TEXT NOT NULL,                  -- e.g. '1.0.0'
  params_json          TEXT CHECK (params_json IS NULL OR json_valid(params_json)),  -- weights, thresholds
  released_at          INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
  is_active            INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  UNIQUE (algorithm_code, version_label),
  UNIQUE (algorithm_version_id, algorithm_code)        -- target for composite FK
) STRICT;

CREATE TABLE calc_runs (
  calc_run_id          INTEGER PRIMARY KEY,
  user_id              INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  algorithm_code       TEXT    NOT NULL,
  algorithm_version_id INTEGER NOT NULL,
  profile_version_id   INTEGER REFERENCES user_profile_versions(profile_version_id),
  target_date          TEXT    NOT NULL CHECK (target_date = date(target_date)),   -- date the OUTPUT belongs to (e.g. sleep date)
  source_date          TEXT    CHECK (source_date IS NULL OR source_date = date(source_date)), -- date of SOURCE activity (e.g. Oct-14 awake HR for Oct-15 sleep)
  subject_key          TEXT    NOT NULL DEFAULT '',    -- e.g. sleep_session_id / activity_id when >1 per day
  config_json          TEXT    CHECK (config_json IS NULL OR json_valid(config_json)),
  status               TEXT    NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','partial','withheld','failed')),
  withheld_reason      TEXT,
  coverage_pct         REAL    CHECK (coverage_pct IS NULL OR coverage_pct BETWEEN 0 AND 100),
  is_partial           INTEGER NOT NULL DEFAULT 0 CHECK (is_partial IN (0,1)),
  has_defaults         INTEGER NOT NULL DEFAULT 0 CHECK (has_defaults IN (0,1)),
  input_fingerprint    TEXT,                           -- hash of inputs; skip recompute if unchanged
  computed_at          INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
  is_current           INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1)),
  FOREIGN KEY (algorithm_version_id, algorithm_code)
    REFERENCES algorithm_versions(algorithm_version_id, algorithm_code)
) STRICT;
-- exactly one "current" run per user/algorithm/date/subject; older runs kept as history
CREATE UNIQUE INDEX ux_calc_runs_current
  ON calc_runs(user_id, algorithm_code, target_date, subject_key) WHERE is_current = 1;
CREATE INDEX ix_calc_runs_lookup ON calc_runs(user_id, algorithm_code, target_date);

-- Auto-retire the previous current run when a new current run is inserted.
CREATE TRIGGER trg_calc_runs_supersede
BEFORE INSERT ON calc_runs
WHEN NEW.is_current = 1
BEGIN
  UPDATE calc_runs SET is_current = 0
   WHERE user_id = NEW.user_id AND algorithm_code = NEW.algorithm_code
     AND target_date = NEW.target_date AND subject_key = NEW.subject_key
     AND is_current = 1;
END;

-- Which raw rows / dates / ranges fed a calculation.
CREATE TABLE calc_run_inputs (
  calc_run_input_id INTEGER PRIMARY KEY,
  calc_run_id       INTEGER NOT NULL REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  role              TEXT    NOT NULL,                  -- 'sleep_session','hr_range','reference_window','activity',...
  ref_table         TEXT,
  ref_id            INTEGER,
  ref_date          TEXT,
  range_start_ts    INTEGER,
  range_end_ts      INTEGER,
  row_count         INTEGER
) STRICT;
CREATE INDEX ix_calc_inputs_run ON calc_run_inputs(calc_run_id);
CREATE INDEX ix_calc_inputs_ref ON calc_run_inputs(ref_table, ref_id);   -- "what must I recompute if this row changes?"

-- Upstream results this run consumed (e.g. sleep_score <- sleeping_hr, awake_hr, need).
CREATE TABLE calc_run_dependencies (
  calc_run_id            INTEGER NOT NULL REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  depends_on_calc_run_id INTEGER NOT NULL REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  PRIMARY KEY (calc_run_id, depends_on_calc_run_id)
) STRICT, WITHOUT ROWID;
CREATE INDEX ix_calc_deps_reverse ON calc_run_dependencies(depends_on_calc_run_id);

-- Quality flags + missing-input reasons (any algorithm).
CREATE TABLE calc_flags (
  calc_flag_id INTEGER PRIMARY KEY,
  calc_run_id  INTEGER NOT NULL REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  flag_code    TEXT    NOT NULL,                       -- 'missing_age','baseline_building','hrv_unverified',...
  severity     TEXT    NOT NULL DEFAULT 'info' CHECK (severity IN ('info','warning','blocking')),
  detail       TEXT
) STRICT;
CREATE INDEX ix_calc_flags_run ON calc_flags(calc_run_id);

-- Intervals removed from a calculation (awake HR + stress share this).
CREATE TABLE calc_exclusion_intervals (
  calc_run_id INTEGER NOT NULL REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  start_ts    INTEGER NOT NULL,
  end_ts      INTEGER NOT NULL CHECK (end_ts > start_ts),
  reason      TEXT    NOT NULL CHECK (reason IN
                ('sleep','nap','activity','exercise_mask','recovery_mask','missing_hr','long_gap','baseline_building','outlier')),
  activity_id INTEGER REFERENCES activities(activity_id) ON DELETE SET NULL,
  sleep_session_id INTEGER REFERENCES sleep_sessions(sleep_session_id) ON DELETE SET NULL,
  PRIMARY KEY (calc_run_id, start_ts, reason)
) STRICT, WITHOUT ROWID;

-- Personal baselines (HRV/RHR refs, sleep stage ranges, health-trend baselines, ...).
CREATE TABLE reference_statistics (
  ref_stat_id       INTEGER PRIMARY KEY,
  user_id           INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  metric_code       TEXT    NOT NULL,                  -- metric_types code OR e.g. 'sleep_deep_min'
  as_of_date        TEXT    NOT NULL CHECK (as_of_date = date(as_of_date)),
  window_start_date TEXT    NOT NULL,
  window_end_date   TEXT    NOT NULL,
  window_days       INTEGER NOT NULL,
  ref_count         INTEGER NOT NULL,                  -- how many nights/days actually used
  mean_value        REAL,
  median_value      REAL,
  stddev_value      REAL,
  low_value         REAL,                              -- personal typical range
  high_value        REAL,
  method            TEXT    NOT NULL DEFAULT 'default',
  calc_run_id       INTEGER REFERENCES calc_runs(calc_run_id) ON DELETE SET NULL,
  computed_at       INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
  UNIQUE (user_id, metric_code, as_of_date, window_days, method)
) STRICT;

-- ---------------------------------------------------------------------
-- 4a. CALCULATED: HEART RATE
-- ---------------------------------------------------------------------
CREATE TABLE sleeping_hr_results (
  calc_run_id      INTEGER PRIMARY KEY REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id          INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  sleep_session_id INTEGER NOT NULL REFERENCES sleep_sessions(sleep_session_id) ON DELETE CASCADE,
  sleep_date       TEXT    NOT NULL,
  bpm              REAL,                               -- NULL when withheld
  method           TEXT    NOT NULL,
  sample_count     INTEGER,
  counted_seconds  INTEGER,
  max_gap_seconds  INTEGER,
  coverage_pct     REAL
) STRICT;
CREATE INDEX ix_sleeping_hr_user_date ON sleeping_hr_results(user_id, sleep_date);

CREATE TABLE awake_hr_results (
  calc_run_id             INTEGER PRIMARY KEY REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id                 INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  source_date             TEXT    NOT NULL,            -- the activity day (e.g. Oct 14)
  window_start_ts         INTEGER,                     -- wake-up
  window_end_ts           INTEGER,                     -- 22:00 local
  wake_sleep_session_id   INTEGER REFERENCES sleep_sessions(sleep_session_id) ON DELETE SET NULL,
  mean_bpm                REAL,
  lower_bound_bpm         REAL,
  upper_bound_bpm         REAL,
  retained_count          INTEGER,
  excluded_sleep_count    INTEGER NOT NULL DEFAULT 0,
  excluded_nap_count      INTEGER NOT NULL DEFAULT 0,
  excluded_activity_count INTEGER NOT NULL DEFAULT 0,
  excluded_outlier_count  INTEGER NOT NULL DEFAULT 0
) STRICT;
CREATE INDEX ix_awake_hr_user_date ON awake_hr_results(user_id, source_date);

-- ---------------------------------------------------------------------
-- 4b. CALCULATED: SLEEP
--     sleep_date (waking day) and source_date (previous day) kept apart.
-- ---------------------------------------------------------------------
CREATE TABLE sleep_nightly_vitals (
  calc_run_id         INTEGER PRIMARY KEY REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id             INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  sleep_session_id    INTEGER NOT NULL REFERENCES sleep_sessions(sleep_session_id) ON DELETE CASCADE,
  sleep_date          TEXT    NOT NULL,
  source_date         TEXT    NOT NULL,                -- date of the awake HR used
  sleeping_hr_run_id  INTEGER REFERENCES calc_runs(calc_run_id) ON DELETE SET NULL,
  awake_hr_run_id     INTEGER REFERENCES calc_runs(calc_run_id) ON DELETE SET NULL,
  hrv_rmssd           REAL,
  deep_hrv_rmssd      REAL,
  sleeping_hr_bpm     REAL,
  prev_awake_hr_bpm   REAL,
  hr_dip_pct          REAL,                            -- (prev awake - sleeping) / prev awake * 100
  dip_component_score REAL,
  hrv_ref_stat_id     INTEGER REFERENCES reference_statistics(ref_stat_id) ON DELETE SET NULL,
  rhr_ref_stat_id     INTEGER REFERENCES reference_statistics(ref_stat_id) ON DELETE SET NULL
) STRICT;
CREATE INDEX ix_nightly_vitals_user_date ON sleep_nightly_vitals(user_id, sleep_date);

CREATE TABLE sleep_metrics (
  calc_run_id      INTEGER PRIMARY KEY REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id          INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  sleep_session_id INTEGER NOT NULL REFERENCES sleep_sessions(sleep_session_id) ON DELETE CASCADE,
  sleep_date       TEXT    NOT NULL,
  bedtime_ts       INTEGER,
  sleep_onset_ts   INTEGER,
  final_wake_ts    INTEGER,
  sleep_end_ts     INTEGER,
  total_asleep_min REAL,
  in_bed_min       REAL,
  awake_min        REAL,
  latency_min      REAL,
  nap_min          REAL,
  deep_min         REAL,
  rem_min          REAL,
  light_min        REAL,
  awake_stage_min  REAL,
  deep_pct         REAL,
  rem_pct          REAL,
  light_pct        REAL,
  efficiency_pct   REAL,
  wake_events      INTEGER,
  restfulness_score REAL
) STRICT;
CREATE INDEX ix_sleep_metrics_user_date ON sleep_metrics(user_id, sleep_date);

CREATE TABLE sleep_need_results (
  calc_run_id         INTEGER PRIMARY KEY REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id             INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  sleep_date          TEXT    NOT NULL,
  source_date         TEXT    NOT NULL,                -- pre-sleep day (strain, debt, naps)
  strain_run_id       INTEGER REFERENCES calc_runs(calc_run_id) ON DELETE SET NULL,
  baseline_min        REAL,
  strain_addition_min REAL,
  debt_addition_min   REAL,
  nap_credit_min      REAL,
  total_need_min      REAL,
  sleep_debt_min      REAL
) STRICT;
CREATE INDEX ix_sleep_need_user_date ON sleep_need_results(user_id, sleep_date);

CREATE TABLE sleep_scores (
  calc_run_id      INTEGER PRIMARY KEY REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id          INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  sleep_session_id INTEGER NOT NULL REFERENCES sleep_sessions(sleep_session_id) ON DELETE CASCADE,
  sleep_date       TEXT    NOT NULL,
  source_date      TEXT,
  overall_score    REAL    CHECK (overall_score IS NULL OR overall_score BETWEEN 0 AND 100),
  score_status     TEXT    NOT NULL CHECK (score_status IN ('complete','partial','withheld')),
  CHECK (score_status <> 'withheld' OR overall_score IS NULL)
) STRICT;
CREATE INDEX ix_sleep_scores_user_date ON sleep_scores(user_id, sleep_date);

-- Weights live in the row (not only in algorithm params) so history stays exact.
-- Current weights: duration .27, stage_mix .20, efficiency .10, sleeping_hrv .05,
--                  sleeping_hr .05, hr_dip .18, restfulness .15
CREATE TABLE sleep_score_components (
  calc_run_id     INTEGER NOT NULL REFERENCES sleep_scores(calc_run_id) ON DELETE CASCADE,
  component       TEXT    NOT NULL CHECK (component IN
                    ('duration','stage_mix','efficiency','sleeping_hrv','sleeping_hr','hr_dip','restfulness')),
  weight          REAL    NOT NULL CHECK (weight BETWEEN 0 AND 1),
  raw_value       REAL,
  component_score REAL    CHECK (component_score IS NULL OR component_score BETWEEN 0 AND 100),
  is_available    INTEGER NOT NULL DEFAULT 1 CHECK (is_available IN (0,1)),
  is_default      INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0,1)),
  default_reason  TEXT,
  PRIMARY KEY (calc_run_id, component)
) STRICT, WITHOUT ROWID;

CREATE TABLE sleep_consistency_results (
  calc_run_id      INTEGER PRIMARY KEY REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id          INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  sleep_date       TEXT    NOT NULL,
  score            REAL,
  drift_min        REAL,
  avg_bedtime_min  REAL,                               -- minutes after local midnight, may exceed 1440
  avg_wake_min     REAL,
  variability_min  REAL,
  window_days      INTEGER,
  nights_used      INTEGER
) STRICT;
CREATE INDEX ix_sleep_consistency_user_date ON sleep_consistency_results(user_id, sleep_date);

CREATE TABLE sleep_stage_comparisons (
  calc_run_id     INTEGER NOT NULL REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  stage           TEXT    NOT NULL CHECK (stage IN ('deep','rem','light','awake')),
  value_min       REAL,
  ref_low_min     REAL,
  ref_high_min    REAL,
  reference_nights INTEGER,
  status          TEXT    NOT NULL CHECK (status IN ('within','above','below','insufficient_data')),
  ref_stat_id     INTEGER REFERENCES reference_statistics(ref_stat_id) ON DELETE SET NULL,
  PRIMARY KEY (calc_run_id, stage)
) STRICT, WITHOUT ROWID;

-- ---------------------------------------------------------------------
-- 4c. CALCULATED: TRAINING / STRAIN
-- ---------------------------------------------------------------------
CREATE TABLE daily_strain_results (
  calc_run_id        INTEGER PRIMARY KEY REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id            INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  strain_date        TEXT    NOT NULL,
  score              REAL    CHECK (score IS NULL OR score BETWEEN 0 AND 21),
  score_pct          REAL,
  label              TEXT,
  trimp_load         REAL,
  workout_load       REAL,
  incidental_load    REAL,
  max_hr_est_bpm     REAL,
  max_hr_source      TEXT,
  resting_hr_param_bpm REAL,
  resting_hr_source  TEXT,
  age_used           INTEGER,
  sex_used           TEXT,
  sample_count       INTEGER,
  counted_seconds    INTEGER,
  missing_age_flag   INTEGER NOT NULL DEFAULT 0 CHECK (missing_age_flag IN (0,1)),
  missing_calibration_flag INTEGER NOT NULL DEFAULT 0 CHECK (missing_calibration_flag IN (0,1))
) STRICT;
CREATE INDEX ix_strain_user_date ON daily_strain_results(user_id, strain_date);

-- scope: daily strain uses ALL HR (incidental effort included);
--        displayed activity-zone totals use LOGGED ACTIVITIES only.
CREATE TABLE strain_zone_durations (
  calc_run_id INTEGER NOT NULL REFERENCES daily_strain_results(calc_run_id) ON DELETE CASCADE,
  scope       TEXT    NOT NULL CHECK (scope IN ('all_hr','logged_activities')),
  zone        INTEGER NOT NULL CHECK (zone BETWEEN 1 AND 5),
  seconds     INTEGER NOT NULL,
  lower_bpm   REAL,
  upper_bpm   REAL,
  PRIMARY KEY (calc_run_id, scope, zone)
) STRICT, WITHOUT ROWID;

CREATE TABLE workout_results (
  calc_run_id  INTEGER PRIMARY KEY REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id      INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  activity_id  INTEGER NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
  strain       REAL,
  load         REAL,
  avg_hr_bpm   REAL,
  max_hr_bpm   REAL,
  duration_s   INTEGER,
  sample_count INTEGER
  -- HR trace is NOT stored: read hr_samples between activities.start_ts and end_ts.
) STRICT;
CREATE INDEX ix_workout_results_activity ON workout_results(activity_id);

CREATE TABLE workout_zone_durations (
  calc_run_id INTEGER NOT NULL REFERENCES workout_results(calc_run_id) ON DELETE CASCADE,
  zone        INTEGER NOT NULL CHECK (zone BETWEEN 1 AND 5),
  seconds     INTEGER NOT NULL,
  lower_bpm   REAL,
  upper_bpm   REAL,
  PRIMARY KEY (calc_run_id, zone)
) STRICT, WITHOUT ROWID;

CREATE TABLE workout_comparisons (
  calc_run_id      INTEGER NOT NULL REFERENCES workout_results(calc_run_id) ON DELETE CASCADE,
  comparison_key   TEXT    NOT NULL,                   -- 'load','avg_hr','zone_3_share',...
  value            REAL,
  prior_avg        REAL,
  typical_low      REAL,
  typical_high     REAL,
  comparison_count INTEGER,
  PRIMARY KEY (calc_run_id, comparison_key)
) STRICT, WITHOUT ROWID;

CREATE TABLE training_trend_results (
  calc_run_id        INTEGER PRIMARY KEY REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id            INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  as_of_date         TEXT    NOT NULL,
  avg_7d_strain      REAL,
  avg_28d_strain     REAL,
  acute_chronic_ratio REAL,
  recovery_run_id    INTEGER REFERENCES calc_runs(calc_run_id) ON DELETE SET NULL,
  strain_target      REAL,
  target_basis       TEXT
) STRICT;
CREATE INDEX ix_trend_user_date ON training_trend_results(user_id, as_of_date);

-- ---------------------------------------------------------------------
-- 4d. CALCULATED: RECOVERY
-- ---------------------------------------------------------------------
CREATE TABLE recovery_results (
  calc_run_id        INTEGER PRIMARY KEY REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id            INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  recovery_date      TEXT    NOT NULL,
  sleep_session_id   INTEGER REFERENCES sleep_sessions(sleep_session_id) ON DELETE SET NULL,
  score_pct          REAL    CHECK (score_pct IS NULL OR score_pct BETWEEN 0 AND 100),
  status             TEXT    NOT NULL CHECK (status IN ('computed','withheld')),
  withheld_reason    TEXT,
  zone               TEXT,
  confidence_value   REAL,
  confidence_label   TEXT,
  current_hrv_ms     REAL,
  current_rhr_bpm    REAL,
  hrv_ref_stat_id    INTEGER REFERENCES reference_statistics(ref_stat_id) ON DELETE SET NULL,
  rhr_ref_stat_id    INTEGER REFERENCES reference_statistics(ref_stat_id) ON DELETE SET NULL,
  hrv_z              REAL,
  rhr_z              REAL,
  combined_z         REAL,
  sleep_adjustment   REAL,
  sleep_duration_min REAL,
  required_sleep_min REAL,
  sleep_performance_pct REAL,
  rejected_reading_count INTEGER NOT NULL DEFAULT 0,
  training_recommendation TEXT,
  CHECK (status <> 'withheld' OR score_pct IS NULL)    -- withheld is NULL, never 0
) STRICT;
CREATE INDEX ix_recovery_user_date ON recovery_results(user_id, recovery_date);

-- ---------------------------------------------------------------------
-- 4e. CALCULATED: STRESS
-- ---------------------------------------------------------------------
CREATE TABLE stress_intervals (
  stress_interval_id INTEGER PRIMARY KEY,
  calc_run_id        INTEGER NOT NULL REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id            INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  start_ts           INTEGER NOT NULL,
  end_ts             INTEGER NOT NULL CHECK (end_ts > start_ts),
  utc_offset_min     INTEGER NOT NULL DEFAULT 0,
  score              REAL CHECK (score IS NULL OR score BETWEEN 0 AND 3),   -- Preserve fractional app scores; NULL = unscored
  state              TEXT,
  hr_bpm             REAL,
  source             TEXT,
  UNIQUE (calc_run_id, start_ts)
) STRICT;
CREATE INDEX ix_stress_intervals_user_time ON stress_intervals(user_id, start_ts);

CREATE TABLE stress_daily_summaries (
  calc_run_id        INTEGER PRIMARY KEY REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id            INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  stress_date        TEXT    NOT NULL,
  avg_score          REAL,
  low_min            INTEGER,
  medium_min         INTEGER,
  high_min           INTEGER,
  scored_min         INTEGER,
  unscored_min       INTEGER,
  coverage_pct       REAL,
  baseline_count     INTEGER,
  confidence         REAL,
  hrv_timing_status  TEXT CHECK (hrv_timing_status  IS NULL OR hrv_timing_status  IN ('verified','unverified')),
  hrv_quality_status TEXT CHECK (hrv_quality_status IS NULL OR hrv_quality_status IN ('good','poor','rejected','unknown')),
  hrv_gated          INTEGER NOT NULL DEFAULT 0 CHECK (hrv_gated IN (0,1))   -- HRV contribution suppressed
) STRICT;
CREATE INDEX ix_stress_daily_user_date ON stress_daily_summaries(user_id, stress_date);

CREATE TABLE sleep_stress_results (
  calc_run_id        INTEGER PRIMARY KEY REFERENCES calc_runs(calc_run_id) ON DELETE CASCADE,
  user_id            INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  sleep_session_id   INTEGER NOT NULL REFERENCES sleep_sessions(sleep_session_id) ON DELETE CASCADE,
  sleep_date         TEXT    NOT NULL,
  stressed_min       REAL,
  stressed_pct       REAL,
  episode_count      INTEGER,
  valid_window_count INTEGER,
  total_window_count INTEGER,
  coverage_pct       REAL,
  confidence         REAL,
  hrv_timing_status  TEXT CHECK (hrv_timing_status  IS NULL OR hrv_timing_status  IN ('verified','unverified')),
  hrv_quality_status TEXT CHECK (hrv_quality_status IS NULL OR hrv_quality_status IN ('good','poor','rejected','unknown')),
  stage_references_json TEXT CHECK (stage_references_json IS NULL OR json_valid(stage_references_json))
) STRICT;
CREATE INDEX ix_sleep_stress_user_date ON sleep_stress_results(user_id, sleep_date);

CREATE TABLE sleep_stress_windows (
  calc_run_id     INTEGER NOT NULL REFERENCES sleep_stress_results(calc_run_id) ON DELETE CASCADE,
  window_start_ts INTEGER NOT NULL,
  window_end_ts   INTEGER NOT NULL,
  stage           TEXT,
  is_valid        INTEGER NOT NULL CHECK (is_valid IN (0,1)),
  is_high_stress  INTEGER CHECK (is_high_stress IS NULL OR is_high_stress IN (0,1)),  -- NULL if invalid
  PRIMARY KEY (calc_run_id, window_start_ts)
) STRICT, WITHOUT ROWID;

CREATE TABLE sleep_stress_episodes (
  episode_id  INTEGER PRIMARY KEY,
  calc_run_id INTEGER NOT NULL REFERENCES sleep_stress_results(calc_run_id) ON DELETE CASCADE,
  start_ts    INTEGER NOT NULL,
  end_ts      INTEGER NOT NULL CHECK (end_ts > start_ts)
) STRICT;
CREATE INDEX ix_sleep_stress_episodes_run ON sleep_stress_episodes(calc_run_id);

-- ---------------------------------------------------------------------
-- 5. REBUILDABLE PRESENTATION CACHE  (safe to TRUNCATE any time)
-- ---------------------------------------------------------------------
CREATE TABLE presentation_snapshots (
  snapshot_id INTEGER PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  view_key    TEXT    NOT NULL,                        -- 'home','sleep','recovery','strain','stress','health_trends',...
  as_of_date  TEXT    NOT NULL,
  params_hash TEXT    NOT NULL DEFAULT '',
  payload     TEXT    NOT NULL CHECK (json_valid(payload)),
  built_at    INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
  is_stale    INTEGER NOT NULL DEFAULT 0 CHECK (is_stale IN (0,1)),
  UNIQUE (user_id, view_key, as_of_date, params_hash)
) STRICT;

-- ---------------------------------------------------------------------
-- 6. CONVENIENCE VIEWS  (current results only; derived values never stored twice)
-- ---------------------------------------------------------------------
CREATE VIEW v_latest_hr AS
SELECT h.user_id, h.ts, h.bpm, h.utc_offset_min
FROM hr_samples h
WHERE h.ts = (SELECT MAX(ts) FROM hr_samples x WHERE x.user_id = h.user_id);

-- 15-minute median is computed in app code (SQLite has no median); store nothing here.

CREATE VIEW v_sleep_score_current AS
SELECT s.user_id, s.sleep_date, s.source_date, s.sleep_session_id,
       s.overall_score, s.score_status,
       cr.calc_run_id, cr.algorithm_version_id, cr.coverage_pct, cr.is_partial, cr.has_defaults, cr.computed_at
FROM sleep_scores s
JOIN calc_runs cr ON cr.calc_run_id = s.calc_run_id AND cr.is_current = 1;

CREATE VIEW v_recovery_current AS
SELECT r.*, cr.algorithm_version_id, cr.coverage_pct, cr.computed_at
FROM recovery_results r
JOIN calc_runs cr ON cr.calc_run_id = r.calc_run_id AND cr.is_current = 1;

CREATE VIEW v_daily_strain_current AS
SELECT d.*, cr.algorithm_version_id, cr.coverage_pct, cr.computed_at
FROM daily_strain_results d
JOIN calc_runs cr ON cr.calc_run_id = d.calc_run_id AND cr.is_current = 1;

-- Stress "now": latest interval + stale flag (stale = older than 30 min).
CREATE VIEW v_stress_current AS
SELECT i.user_id, i.score, i.state, i.start_ts, i.end_ts,
       (CAST(strftime('%s','now') AS INTEGER) - i.end_ts > 1800) AS is_stale
FROM stress_intervals i
JOIN calc_runs cr ON cr.calc_run_id = i.calc_run_id AND cr.is_current = 1
WHERE i.end_ts = (SELECT MAX(i2.end_ts) FROM stress_intervals i2
                  JOIN calc_runs c2 ON c2.calc_run_id = i2.calc_run_id AND c2.is_current = 1
                  WHERE i2.user_id = i.user_id);

-- Weekly zone totals from logged workouts (ISO-ish week via %Y-%W).
CREATE VIEW v_weekly_zone_totals AS
SELECT a.user_id, strftime('%Y-%W', a.start_local_date) AS year_week,
       z.zone, SUM(z.seconds) AS seconds
FROM workout_zone_durations z
JOIN workout_results w ON w.calc_run_id = z.calc_run_id
JOIN calc_runs cr      ON cr.calc_run_id = w.calc_run_id AND cr.is_current = 1
JOIN activities a      ON a.activity_id = w.activity_id
GROUP BY a.user_id, year_week, z.zone;

-- Strength time = RECORDED ACTIVITY TIME, not a muscular-load score.
-- Adjust the type match to the provider's real activity names.
CREATE VIEW v_strength_daily AS
SELECT user_id, start_local_date AS activity_date,
       SUM(COALESCE(active_duration_s, end_ts - start_ts)) AS recorded_seconds
FROM activities
WHERE lower(COALESCE(activity_type,'')) LIKE '%strength%'
   OR lower(COALESCE(activity_type,'')) LIKE '%weight%'
GROUP BY user_id, start_local_date;

INSERT INTO schema_migrations(version, description) VALUES (1, 'initial schema');
PRAGMA user_version = 1;
