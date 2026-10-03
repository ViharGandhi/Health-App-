# Sleep Stage Typical Range

Backend only. Existing sleep scores, stress calculations and frontend components are unchanged.

## Discovery and assumptions

This adapter follows the **official Google Health v4 schema**, not an observed Fitbit Air payload. Live validation is pending; no device/API credentials were available. The user approved implementation with the documented schema and synthetic fixtures.

- [Sleep schema](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints#Sleep): `sleep.interval.startTime/endTime` and `sleep.stages[].startTime/endTime` are RFC3339 physical timestamps. Stage classification is `sleep.stages[].type`. Metadata is `sleep.metadata.processed`, `stagesStatus`, `mainSleep`, and `nap`.
- Stage processing must have `processed=true` and `stagesStatus=SUCCEEDED`. Pending records have no stats/range, stay queued, and are fetched again. Rejected stages and CLASSIC records return an explicit unavailable status.
- [Sleep guide](https://developers.google.com/health/data-types/sleep): primary stages partition a contiguous, non-overlapping timeline. `shortAwakenings` can overlap them. This feature ignores short awakenings and summary totals; it never adds or subtracts them from stage minutes.
- UTC durations handle DST transitions. Historical local wake dates use `sleep.interval.endUtcOffset`, a duration string such as `7200s`. A missing offset is an adapter error rather than silently assuming the user's timezone is UTC. No guessed timezone is applied to historical records.
- [List endpoint](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/list): request `/v4/users/me/dataTypes/sleep/dataPoints`, following every `nextPageToken`. Use `sleep.interval.civil_end_time` for local wake-date ranges. Sleep **list** does not support `dataSourceFamily`; setting it can fail. Listing preserves identifiers for session upserts. Known non-FITBIT platforms are excluded locally; records without optional provenance are accepted provisionally and must be checked in live discovery. Device names are not assumed to be stable IDs.
- Sessions explicitly flagged as main sleep take precedence. Without a flag, choose the longest non-nap candidate on that local wake date. Explicitly non-main records are excluded. Naps and nights with less than three hours in LIGHT+DEEP+REM are excluded. Malformed partitions are logged and have no score; zero minutes in an individual stage is valid.

When access becomes available, set a short-lived `GOOGLE_HEALTH_ACCESS_TOKEN` in `backend/.env`, then inspect a real completed night:

```powershell
.\.venv\Scripts\python.exe backend\backfill_sleep_stage_ranges.py --end-date 2026-10-02 --raw-output "$env:TEMP\ojas-sleep-discovery.json"
```

The output contains private health data, but no token. Keep it out of Git. Verify processing flags, identifiers, historical offsets, provenance and exact stage boundaries before claiming live Fitbit Air verification.

## Algorithm and interpretation

One `StageRangeConfig` sets window=7 qualifying nights, minimum=4, time_in_bed denominator, MAD scale=1.4826, floor=1 percentage point, and minimum asleep duration=3 hours. The scored night and later dates never enter its baseline. Missing calendar nights do not reduce the qualifying-night window.

`time_in_bed` here means the sum of the four primary stage durations, per the specification. It is not an independent lights-out measurement. A `time_asleep` configuration instead uses LIGHT+DEEP+REM and reports awake minutes without a percentage or comparison.

For each stage, the center is the pooled minute ratio. Spread is scaled MAD of nightly percentages, floored at one point. Endpoints are center +/- spread, clipped to 0–100. Restorative is the **deep+REM combination**, with its own nightly percentages, center and spread. It is not a separately detected physiological stage, nor a validated measure of restoration.

Example: light minutes 270,258,300,282 with totals 540,600,660,600 produce center 46.25, spread 2.9652, range 43.2848–49.2152. The pooled center is duration-weighted and can move with outliers even when MAD remains robust.

With fewer than four qualifying nights, return `building_baseline`, the available count, and null reference ranges. The supplied population bands were not used because their source, denominator compatibility, age basis and restorative reference were not verified. With four to six nights, reliability is `low`; a full configured window is `ok`, meaning **complete**, not clinically reliable. All ranges carry `range_is_provisional=true` and the baseline IDs/count/config snapshot.

The range is a descriptive recent pattern, **not** a prediction interval, a confidence interval, a healthy target, or a clinical normal range. Status is neutral: below/within/above. Interpret all four stages together because their percentages sum to 100.

### Peer-reviewed context

- [How many nights are needed? (SLEEP, 2026)](https://doi.org/10.1093/sleep/zsag040) found that variability of sleep duration, timing and fragmentation required substantially longer observation than the means. The reported 41–65 nights do **not** directly establish the sample size for stage-percentage MAD, nor validate this seven-night pooled-center formula.
- [Objective multi-night sleep monitoring at home (SLEEP, 2023)](https://pubmed.ncbi.nlm.nih.gov/36583300/) examined night-to-night variability including sleep-stage endpoints; it supports reporting uncertainty and observing multiple nights. It does not establish these particular personal range limits.

The exact pooled-ratio +/- MAD formula, four-night minimum and one-point floor are product choices in the user's specification. No claim is made that those choices were clinically validated.

## API and synthetic data

`GET /api/sleep/stages/typical-ranges?days=10` (1–366 days).

Without an OAuth session it returns `is_mock=true` and date-seeded mixed history: stage percentages/durations vary, some days are absent, some records are CLASSIC/pending, and some have zero deep sleep. Fixtures carry Google-shaped stages and overlapping short awakenings. They are synthetic, not examples of real Fitbit Air readings.

Connected calls refresh the account-scoped store using Google's `healthUserId` from [getIdentity](https://developers.google.com/health/reference/rest/v4/users/getIdentity). No data are shared between users. Existing but expired sessions return 401 with a reconnect message, rather than falling back to mock data. API failures are propagated; 429/503 use the existing capped retry backoff.

Each scored record includes minute/percentage/range/comparison details, dependent baseline IDs, the configuration snapshot, algorithm version and computed timestamp. Ineligible main records return an unavailable/pending status with empty stages. Unrecorded dates stay absent.

## Persistence and jobs

Migration `migrations/002_sleep_stage_ranges.sql` creates user-scoped session stats, result records and durable jobs. Default database: `backend/data/sleep_stage_ranges.sqlite3`; override with `SLEEP_STAGE_DB_PATH`.

On first sync, fetch all earlier history through the requested end date to avoid truncating the previous-N qualifying nights at an arbitrary calendar cutoff. On later syncs, refresh the requested interval and at least the latest ten dates. Store normalized per-night stats, then recompute results from stored minutes. A changed, pending, CLASSIC, deleted or moved record invalidates its previous stats and dependent baselines. Unchanged outputs retain `computed_at`; repeat syncs are idempotent. A changed denominator recomputes both sides from stored stage minutes. Lowering the minimum-duration threshold requires a full historical backfill to recover previously excluded nights.

Run a ten-day late-sync backfill from the repo root:

```powershell
.\.venv\Scripts\python.exe backend\backfill_sleep_stage_ranges.py
```

Run a worker pass for the authenticated personal account:

```powershell
.\.venv\Scripts\python.exe backend\backfill_sleep_stage_ranges.py --jobs
```

Run the worker periodically (one instance) and the backfill daily through your scheduler. Pending stages/transient failures retain durable jobs; stage-processing retries wait five minutes. OAuth tokens are not stored in the analytics database. The manual worker needs a current token; expired credentials need renewal through the existing consent/refresh flow. Multiuser unattended OAuth credential storage/refresh is not supplied by this personal-app worker.

## Webhook setup (live registration pending)

Receiver: `POST /api/webhooks/google-health/sleep-stages`.

Set `GOOGLE_HEALTH_WEBHOOK_AUTHORIZATION` to the exact header secret registered with Google, such as `Bearer <random-secret>`. Unconfigured receivers fail closed. Google's authorized `{"type":"verification"}` handshake returns 200, the unauthorized challenge returns 401. Notifications require both that secret and a valid `GOOGLE-HEALTH-API-SIGNATURE` over the **unchanged raw request bytes**, verified using Google's Tink public keyset. Cache keys for an hour, refreshing after verification failure to handle rotation.

The receiver enqueues sleep UPSERT/DELETE notifications and then returns 204. With a record ID, the job is keyed by user and that record; otherwise it is keyed by the notified interval, since Google notifications may omit a session ID. The worker fetches authoritative sleep sessions for the notified interval and upserts by their actual `sleep_id`. Notifications arriving during processing increment the job generation and cannot be lost when the older job completes. Physical times are stored in UTC; civil notification intervals drive local-date fetches.

Register the subscriber with an approved Cloud project and a public HTTPS receiver using [Google's webhook setup](https://developers.google.com/health/webhooks). For the subscriber creation request, use:

```json
{
  "endpointUri": "https://YOUR_HOST/api/webhooks/google-health/sleep-stages",
  "subscriberConfigs": [{"dataTypes": ["sleep"], "subscriptionCreatePolicy": "AUTOMATIC"}],
  "endpointAuthorization": {"secret": "Bearer YOUR_RANDOM_SECRET"}
}
```

This payload is a setup template, not a registered subscription. Cloud credentials, endpoint ownership verification, actual delivery, current project access and live Fitbit payload validation remain pending.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend -p test_sleep_stage_ranges.py -v
.\.venv\Scripts\python.exe backend\backfill_sleep_stage_ranges.py --demo --days 10
```

Tests cover the worked example, pooled centers, MAD/floor/outlier behavior, baseline exclusion and gaps, building-baseline behavior, neutral labels, both denominators, independent restorative spread, naps/CLASSIC/pending stages, overlapping awakenings, invalid partitions, UTC/DST offsets, user isolation, correction/deletion cascades, upsert idempotence, raw-list pagination, mixed demo responses, expired sessions, signature verification/tampering, subscriber challenges and durable job generation/retries.
