# Sleep Stress backend

`GET /api/sleep/stress?timeframe=W|M|6M` returns one record per sleep session
ending in the selected rolling range (7 days, 30 days, or six months).
`days=1..31` remains available. `nights` holds each scored sleep session and `totals` combines sessions
with the same local wake date, identifying the main sleep. Without a connected
Google account it uses date-seeded sample data. The
sample includes ordinary nights, elevated-stress episodes, awakenings, sensor spikes,
missing HR windows, and different confidence levels. It is illustrative, not a
clinical validation set. Run the mock threshold comparison with:

```powershell
cd backend
..\.venv\Scripts\python.exe calibrate_sleep_stress.py --nights 14
```

The score requires **both** log-RMSSD below and median HR above stage-specific
personal baselines for two adjacent windows. Its baseline uses only the previous
14 local wake dates, so requesting a longer chart cannot change a night’s score.
It reports summed stressed minutes,
hours, percentage of valid sleep windows, episode details, and coverage/confidence.
The 1.0 spread thresholds are starting settings, not published clinical cutoffs.
Only sleep stage, sample RMSSD, and sample HR enter this calculation.

## API mapping and unresolved observation timing

The [Google Health v4 DataPoint reference](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints)
documents `sleep.interval.startTime/endTime`, `sleep.stages[].startTime/endTime/type`,
`sleep.shortAwakenings[]`, `sleep.metadata.processed/stagesStatus`,
`heartRate.sampleTime.physicalTime`, `heartRate.beatsPerMinute`, and
`heartRateVariability.sampleTime.physicalTime` with
`rootMeanSquareOfSuccessiveDifferencesMilliseconds`. SDNN is ignored. Physical
timestamps use RFC 3339; sleep intervals include UTC offsets. HR is in bpm and
RMSSD is in milliseconds. The existing Google client follows pagination tokens.

The public schema does **not** identify whether an HRV `sampleTime` marks the
start or end of the RMSSD analysis window, or supply its duration. The adapter
infers typical cadence from neighboring samples and leaves long gaps blank.
The mock explicitly places timestamps at window starts. Without a verified
`SLEEP_STRESS_HRV_ANCHOR` (`start` or `end`), connected requests inspect both
alignments and return baseline progress with all stress scores withheld. Unverified
results are not stored as scored records. Once there is enough baseline history,
the status is `timing_unverified` until measurement timing is independently verified.
Do not infer start/end semantics just from equally spaced sample timestamps.

A connected Fitbit night ending 2026-10-07 supplied 71 HRV observations and 9,065
heart-rate observations. Both alignments produced usable windows after correcting
HR cadence inference to use the median interval instead of the fastest decile.
Only three sleep sessions were available in the preceding 14-day query, below
the seven-previous-night baseline minimum. This inspection did not verify HRV
start/end semantics. HR coverage still rejects gaps and invalid BPM readings.

Connected results are upserted by sleep ID into the local SQLite database at
`backend/data/sleep_stress.sqlite3`; valid windows are stored alongside each
record. Override with `SLEEP_STRESS_DB_PATH`. The schema is in
`migrations/001_sleep_stress.sql`. A manual late-sync backfill script defaults to
the last three days and requires a live access token plus the verified HRV anchor:

```powershell
cd backend
..\.venv\Scripts\python.exe backfill_sleep_stress.py --days 3
```

Google's [webhook documentation](https://developers.google.com/health/webhooks)
requires a registered public HTTPS subscriber, an authorization challenge, and
verification of its rotating signed payloads. This local cookie-session app has
no subscriber credentials or server-side user token mapping, so it does not
register or expose a webhook receiver. Connected page requests and the manual
backfill recompute late syncs. A live subscription must be completed after Cloud
access and signed webhook fixtures are available.
