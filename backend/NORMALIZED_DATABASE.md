# Normalized health database

The supplied SQLite schema is installed in `data/health.sqlite3` (override with
`HEALTH_DB_PATH`). It contains the original 48 tables plus `daily_intraday_hr`
and the supplied indexes, views,
STRICT constraints and supersession trigger. Connections enable foreign keys,
WAL, busy timeout and NORMAL synchronous mode.

`migrations/003_normalized_health.sql` is the saved schema. One precision correction
is intentional: `stress_intervals.score` is REAL because current scores are
fractional values on 0–3. The single-valued `training_trend_results.strain_target`
cannot represent the existing low/high target band; that band is retained in
the run's config JSON rather than converted to an invented midpoint.

## Ownership and profile

Provider Health user ID identifies the account. Email does not merge owners.
The connected personal user's birth date is **2004-01-31** in an immutable profile
version. Age is calculated for the requested result date, including birthday
rollover, and takes priority over an older browser age. Unknown sex remains
unknown in the profile; existing calculation defaults remain flagged as defaults.

`GET /api/profile` returns birth date, age, timezone and profile version for the
authenticated account. The DOB is not applied to other/new accounts.

OAuth tokens are encrypted with Fernet before being stored as BLOBs. A generated
`HEALTH_CREDENTIAL_KEY` is stored in the ignored backend `.env`; keep this key
with a protected configuration backup and do not commit it. Key IDs identify the
encryption key. No plaintext token is inserted into the database. The existing
signed-cookie login remains compatible. Disconnect removes stored credentials
and disables the account's scheduled jobs.

## Ingestion and calculations

Completed provider fetches record sync runs, normalized observations and successful
cursors. HR retains one daily summary and main-sleep samples; its raw JSON pages
are discarded. Other datasets retain exact JSON pages.
Failed pagination records a failed run without committing a partial dataset or
advancing success. Invalid HR rows are discarded; other invalid rows remain in
raw payloads. Invalid rows make the run partial and
do not advance its success cursor. Authoritative successful empty slices remove
old normalized rows in that slice, scoped to the correct user. Provider fields
outside the strict normalized contract remain available in raw JSON.

Current observation reads prefer normalized records, with the existing transport
cache as a compatibility fallback. This preserves the
existing sync cadence, freeze-once daily sleep policy and API response contracts.
The old databases are retained during this compatibility transition. They have
not been dropped or presented as part of the new normalized schema.

Connected API responses persist versioned Sleep, nightly vitals, need, Strain,
workout, Recovery, consistency, stage-range and stress results plus presentation
snapshots. Saved RHR and scheduled awake means also persist directly. Runs record
profile versions, algorithm/config metadata, quality/default flags, source/target
dates and available dependency/input links. Current-run views select superseding
results; previous runs are retained. Demo responses are excluded.

Sleep-stress evidence windows are persisted when that pipeline executes. Unknown
HRV timing does not become verified timing during migration. Low-confidence or
withheld results stay NULL with reasons. Optional result fields without an actual
source are not filled with fabricated values. Integer duration columns follow
the supplied schema; full response precision remains in payloads/snapshots.

## Migration

```
python backend/migrate_health_database.py --birth-date 2004-01-31 --timezone Asia/Calcutta
```

This command validates the configured signed session locally, imports only its
legacy account partition, retains the original database, registers the profile,
encrypts credentials and imports raw observations, daily steps, saved RHR/awake
means, cached daily strain and recognizable saved result snapshots. A completion
marker makes a completed import repeatable without duplicating business rows.
`--resume-results` is only for a run whose raw-data phase already completed.

Legacy caches contain parsed points rather than exact HTTP pages; imported raw
payloads are labeled `legacy-cache:read_points`. Future downloads preserve actual
provider JSON pages. Legacy presentation snapshots are archived with their
original cache key. Other results are populated from their normal connected
feature paths rather than manufactured during migration.

Do not remove `health_cache.sqlite3`, `sleep_stage_ranges.sqlite3` or
`sleep_stress.sqlite3` yet: legacy range/queue consumers still use them. Their
normalized business records/results are now persisted in the new database, but
removing the compatibility layer is a separate cutover requiring its own checks.

## Validation

Tests cover schema installation/reopening, foreign keys and STRICT constraints,
account isolation, historical birthday age, immutable profiles, encrypted tokens,
raw deduplication/corrections/empty slices, failed pagination, result history and
current views, mock isolation, legacy import and repeatability. The live profile,
Sleep, Strain, Recovery, consistency and stage APIs are checked without an age
header. Audit output is in `local-exports/normalized-database-live-audit.json`.
