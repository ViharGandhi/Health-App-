# Current application data inventory

Code audit: October 15, 2026. Describes the current implementation, not a promise
that every optional Google measurement is present for this account/device.
Proposed normalized tables below are design suggestions, not an implemented migration.

## 1. Identity, profile and account connection

| Field | Current source | Purpose |
|---|---|---|
| Google Health user ID | Google Health `/v4/users/me/identity`, `healthUserId` | Permanent provider account identity; data ownership |
| Email, display name | Google OAuth user info | Connection status/profile display |
| Age | Browser `ojas_age`, sent as `X-User-Age`; configured USER_AGE used by manual requests/selected fallbacks | HRmax, zones, strain, age-dependent sleep calculations |
| Sex and default flag | `X-User-Sex` or USER_SEX; existing default m | TRIMP parameters and provenance |
| IANA timezone | `X-User-Timezone`; AWAKE_HR_TIMEZONE for the personal scheduled job | Civil day boundaries and scheduled collection |
| Client date | `X-User-Date` or current date in client timezone | Requested reporting day; not a measurement timestamp |
| Access token, refresh token, expiry | Google OAuth | Provider access; currently carried in a signed session cookie |
| Connected / mock state | Application | Distinguish connected observations from synthetic demos |

Do not use email, session ID or access token as the permanent health-data owner.
No date-of-birth field is currently collected. Credentials belong in a protected
credential store if migrating auth to a database, separate from health tables.

## 2. Provider measurements and fields actually consumed

Normal reconciled reads use
`GET https://health.googleapis.com/v4/users/me/dataTypes/{type}/dataPoints:reconcile`
and `dataSourceFamily=users/me/dataSourceFamilies/google-wearables`.
Identifiable raw sleep-session listing uses `.../sleep/dataPoints` without
`:reconcile`. All pages are followed. Filters use snake_case; JSON uses camelCase.

| Provider type | Fields consumed | Grain / unit | Used by |
|---|---|---|---|
| `heart-rate` | `heartRate.sampleTime.physicalTime`, `utcOffset`, `beatsPerMinute` | One irregular timestamped sample; BPM | HR charts, asleep RHR, awake mean, strain, workouts, stress |
| `sleep` | Resource `name`; interval start/end and start/end UTC offsets; metadata `mainSleep`, `nap`, `processed`, optional external ID | One sleep session, including naps | Sleep selection, timing, exclusion masks, all sleep features |
| `sleep` summary | `minutesAsleep`, `minutesAwake`, `minutesInSleepPeriod`, `minutesToFallAsleep`, `minutesAfterWakeUp`; `stagesSummary` type/minutes/count | One session summary; minutes/counts | Duration, stage mix, latency, restfulness, wake time |
| `sleep` segments | `stages`, `shortAwakenings`, `outOfBedSegments`: type, startTime, endTime | Many intervals per sleep | Stage timeline, asleep RHR, sleep stress, stage ranges |
| `exercise` | Resource name retained in provider payload; interval start/end/offsets, `displayName`, `exerciseType`, optional `activeDuration` | One logged activity; seconds/minutes | Activity timeline, workout strain, strength duration, awake-HR exclusion |
| `activity-level` | Interval start/end and `activityLevelType` | Timestamped interval; sedentary/light/moderate/very active | Stress state and baseline preparation |
| `daily-heart-rate-variability` | Date; `averageHeartRateVariabilityMilliseconds`, optional `deepSleepRootMeanSquareOfSuccessiveDifferencesMilliseconds`, optional `nonRemHeartRateBeatsPerMinute` | Daily RMSSD ms; deep-sleep RMSSD ms; non-REM BPM | Sleep, Recovery, Health |
| `heart-rate-variability` | `sampleTime.physicalTime`, `rootMeanSquareOfSuccessiveDifferencesMilliseconds`; quality/coverage checked where applicable | Timestamped HRV sample/window, ms | Sleep-stress and stress pipelines; gated by timing/quality |
| `daily-oxygen-saturation` | Date, `averagePercentage` | Daily SpO2, percent | Health and Home |
| `daily-respiratory-rate` | Date, `breathsPerMinute` | Daily/nightly breaths per minute | Health, Home, Recovery analytics |
| `daily-sleep-temperature-derivations` | Date, `nightlyTemperatureCelsius` | Nightly temperature, degrees C | Health, Home, Recovery context |
| `daily-vo2-max` | Date, `vo2Max`, optional `estimated` | Daily fitness estimate, mL/kg/min | Health and Home |
| `steps` | `steps.countSum`, roll-up civil date | Daily step count | Home and Strain analytics |

Steps use `POST .../steps/dataPoints:dailyRollUp` with the requested date range.
Raw provider payloads may contain other fields; retaining a payload does not mean
the app parses, calculates with, or displays all of them.

### Important RHR distinction

Although the adapter has a `daily-resting-heart-rate` mapping, its `_points`
method intercepts it. Current connected RHR is read from the locally saved
asleep-stage calculation, not downloaded from that Google endpoint.

## 3. Calculated heart-rate datasets

| Dataset | Inputs / calculation | Stored or displayed fields |
|---|---|---|
| Intraday chart | Raw valid HR grouped into civil 15-minute bins; median of each bin | Local time label, median BPM; latest raw timestamp and BPM separately |
| Sleep HR chart | HR inside the selected completed main sleep | sleep ID/date, UTC and local bounds, timestamp/local time/BPM samples, stage intervals, availability status |
| Nightly resting/sleeping HR | Time-weighted HR during light/deep/REM; awake stages and long gaps excluded | Value, method `ASLEEP_TIME_WEIGHTED_V1`, sleep ID, sample count, covered/asleep seconds, status |
| Awake daily mean | Arithmetic mean of valid raw HR from the selected main-sleep wake time to 22:00; exclude other sleep/naps and all logged exercise intervals | Date/timezone, wake/cutoff, raw mean, retained samples/count, excluded counts, activity intervals, calculation timestamp, method/status |
| HR dip | `(previous_day_awake_mean - current_sleeping_hr) / previous_day_awake_mean * 100` | Awake source date/mean/count, sleeping HR, dip percent, normalized dip component score |

Awake means are collected at 22:00 by the backend personal-account scheduler.
It uses the configured signed cookie and timezone, catches up yesterday on
startup, and retries missing/failed results. The backend must be running.
Successful days can be recalculated via API. The UI recalculation button was removed.
The 15-minute-median comparison export is an analysis artifact; the awake baseline
still uses raw samples. The raw stream must remain recoverable for recalculation.

## 4. Sleep calculations and displays

### Main daily sleep response

- Sleep date, selected sleep ID, bed/start time, end time, actual onset and final wake time.
- Total sleep, time in bed/period, awake time, latency, interruptions/wake events.
- Deep, REM, light/core and awake durations; stage segments; nap duration.
- Sleep score 0–100, sleep need, tonight's need, debt, efficiency percent.
- Daily HRV, deep-sleep HRV, locally calculated sleeping HR, previous-day awake HR and dip.
- Prior 60-day mean HRV/RHR references, reference counts and window start/end.
- Component scores, availability, applied defaults, weighted coverage, partial/status reason.
- Average bed/wake times and timing variability.

Composite weights: duration 27%, stage mix 20%, efficiency 10%, sleeping HRV 5%,
sleeping HR 5%, HR dip 18%, restfulness 15%. The dip component maps 0–25% dip
to 0–100 and caps at those limits. A component score is distinct from its raw value.
Missing components can receive explicit existing defaults; persist those flags.

### Sleep need

Store the calculation's baseline minutes, strain addition, debt addition, nap
credit, total required minutes and sleep debt minutes. The configured baseline
is 450 minutes. The calculation joins prior sleep, daily strain and naps.
Sleep date D uses the pre-sleep estimate for activity date D-1. Keep both dates.
Missing required strain/age/coverage can make sleep need and the score unavailable.

### Sleep analytics

- Performance score, hours-versus-need percentage, asleep minutes, needed minutes.
- Period/in-bed minutes, efficiency, restorative minutes (deep + REM), wake events.
- Bed, wake, onset and final-wake timestamps; stage segments.
- W/M/6M daily or bucketed history; range, previous-range and prior-30-day averages.
- Current connected composite performance is attached only when it matches the
  identified sleep. Earlier connected performance/need can remain null; the UI
  response is not proof that a full historical score series was calculated.

### Consistency and stage ranges

- Four-night clock-consistency score, drift minutes, label, latest/average score,
  band counts, previous-period change and trend points.
- Separate legacy bed/wake timing-variability measures also exist; retain estimator names.
- Stage minutes/percentages for awake/light/deep/REM/restorative; percentage denominator.
- Personal stage-range low/high/center/spread, reference-night count, reference
  dates/IDs, building-reference/within/above/below status, algorithm version/config.
- Default stage reference: prior 7 qualifying nights, at least 4; minimum main
  sleep 3 hours; default denominator time in bed.

## 5. Strain and activity calculations and displays

### Daily strain

- Local calendar midnight-to-now/day-end window; strain 0–21 and 0–100 mapping.
- HR-reserve/TRIMP load, strain label, cleaned mean/maximum observed HR.
- Five zone durations; sample count, counted minutes, coverage/low-coverage.
- Workout load, incidental load, workout-level results and suggested workout intervals.
- Estimated HRmax (`208 - 0.7 * age`), resting-HR parameter and source,
  sex parameter and source, age used/missing, calibration state, configuration.
- Seven- and 28-day strain means, acute/chronic ratio, recovery-based target
  low/high and under/on/over status.

Day strain includes incidental cardio effort. Display activity-zone totals use
logged activities. `workout_strain` and `incidental_strain` are legacy names for
TRIMP loads, not additive 0–21 scores. Persist units and semantics explicitly.

### Activity details and history

- Activity ID, provider exercise type, display name, start/end, active/elapsed duration.
- Workout strain/load, mean/max HR, timestamped HR trace, zone minutes and percentages.
- Zone boundaries, typical zone ranges, comparison averages/count, coverage and unrecorded minutes.
- Strength-session minutes grouped by type/name; daily steps; weekly activity-zone
  and strength totals; W/M/6M trends and prior-30-day comparison averages.
- Current UI activity IDs are hashes of start/end/type/name; preserve the provider
  resource ID too when normalizing, because corrected activity fields can change the hash.

Connected per-workout steps/calories, GPS routes, and cardio/muscular splits are
not currently populated. Their demo values/placeholders must not become real observations.
Daily steps are real provider roll-ups; strength time is logged duration, not measured muscular load.

## 6. Recovery calculations and displays

- Current HRV/RHR and reference values/counts; RHR method.
- Recent HRV signal, HRV/RHR z components, combined z, sleep adjustment.
- Recovery percent/score, zone below/normal/above personal reference, confidence,
  estimated flag, building-reference/status reason, rejected-reading counts/data-quality flag.
- Sleep duration/need/performance context and context-missing flag.
- Respiratory-rate/temperature reference-deviation context; code's `illness_flag`
  is an algorithm flag, not a diagnosis.
- Training recommendation; historical recovery, HRV, RHR, respiratory rate,
  sleep performance, averages, typical ranges, monthly buckets and Health assessed/within counts.

Connected estimator uses a 60-day reference excluding the latest 7 days, at least
21 reference HRV days and 4 recent nights; recent HRV uses 7 prior dates. Recent/today
HRV weights are 70/30; HRV/RHR weights are 60/40 when RHR is available.
Low confidence can withhold a percentage. Demo/legacy response fields remain in
the API contract; they are not all independent connected measurements.

## 7. Stress calculations and displays

### Daytime/general Stress Monitor

- HR-based score 0–3 per interval, interval start/end, HR, state and source.
- Low/medium/high minutes, average, scored/unscored/elapsed minutes and coverage.
- Latest score/level/time and stale flag; daily history.
- Sleep/activity overlays; exercise and recovery masks; missing-HR/reference-building reasons.
- Baseline day count/mode, confidence flags and baseline-leak flag.
- Observed HRV counts, quality-rejected counts and enablement flags;
  separate sleep/non-activity stress aggregates and model/limitations metadata.

Current connected daytime HRV contributions are gated off when quality/window
coverage is unverified. Receiving HRV data is not sufficient to enable it.

### Sleep high-stress detector

- Sleep ID/date, main-sleep/processed/timing status; algorithm/config/computed time.
- Valid HR+HRV windows: start/end, sleep stage, ln(RMSSD), HR and represented minutes.
- Prior stage-specific baseline statistics/counts; stressed minutes/hours/percent.
- Valid/asleep minutes, coverage, confidence, episodes, peak/mean levels, fallback flags.
- Alignment/anchor verification and withheld reason.

This feature detects high sleep stress only. Missing/configuration-unverified
HRV timing can withhold the result; do not turn this into a zero-stress observation.

## 8. Health and Home presentation

Health has eight series: HRV, deep-sleep HRV, non-REM HR, locally calculated RHR,
SpO2, respiratory rate, skin temperature and VO2 max. Each point has date, value,
optional baseline, method and estimated flag. Trends have selected and previous
range averages; the descriptive Health baseline is a prior-14-calendar-day median
after at least seven valid readings. This differs from the Sleep/Recovery references.

Home combines Recovery/Sleep/Strain and activities, plus metric rows carrying key,
title, current value, previous comparison, unit and navigation link. It shows sleep
and health readings, steps, day strain, weekly activity zones and strength time.
UI labels, colors, navigation links and axis guide lines are presentation metadata;
they need not be authoritative health-table columns.

## 9. Current persistence

- Health SQLite tables: `health_account_aliases`, `read_slices`, `read_points`,
  `exact_reads`, `cache_epochs`, `calculation_versions`, `dynamic_state`,
  `dynamic_sessions`, `home_visits`, `dynamic_steps`, `sleep_days`, `sleep_rhr`,
  `calculated_days`, `page_snapshots`, `awake_heart_rate`.
- Sleep-stage SQLite: `sleep_stage_sessions`, `sleep_stage_results`, `sleep_stage_jobs`.
- Sleep-stress SQLite: `sleep_stress`, `sleep_stress_windows`.
- There are also process-memory/browser caches, profile values in browser localStorage,
  auth credentials in the signed cookie, and the configured scheduler cookie in `.env`.
- Existing JSON snapshots mix input references, scores and presentation data.
  Treat these as caches/results, not as a normalized schema to copy unchanged.
- Normal sync checks are throttled to 15 minutes; HR/activity streams use deltas,
  and recognized sleep inputs are saved once per day. Other reads are cached or
  served from local storage. This is not an uninterrupted real-time device stream.

## 10. Suggested normalized entities

| Proposed table | Grain / main relationship |
|---|---|
| users, user_profile_versions | Internal user; age/sex/timezone with effective dates |
| provider_accounts, provider_credentials | User/provider/health user ID; protected OAuth credentials |
| provider_observations | Provider ID, type, source, raw payload, observed/upload/fetch metadata where actually available |
| heart_rate_samples | User/source/physical timestamp; raw BPM and recorded offset |
| hrv_samples | User/source/timestamp or verified window; RMSSD, timing/quality status |
| daily_measurements | User/local date/type/source; value/unit/method/estimated status |
| sleep_sessions | Provider sleep ID/user; UTC bounds, civil wake date, offsets and metadata |
| sleep_segments | Sleep ID; typed start/end intervals, including short awakenings/out-of-bed |
| sleep_summaries | Sleep ID; provider summary durations, counts and availability |
| activity_sessions | Provider exercise ID/user; UTC bounds, type/name/active duration |
| activity_level_intervals | User/source/start/end; recorded activity classification |
| daily_steps | User/civil date/source; step count and roll-up provenance |
| asleep_hr_results | User/sleep ID/date; method, weighted HR, sample count/coverage |
| awake_hr_results | User/date/timezone/method; mean, bounds, exclusion counts and input references |
| awake_hr_exclusions | Awake result/activity or sleep ID; excluded interval |
| sleep_need_results | User/activity date/target sleep date; baseline/strain/debt/nap/total and version |
| sleep_score_results, sleep_score_components | User/sleep ID/date/version; score, inputs, components/defaults |
| strain_daily_results, workout_results, zone_results | User/date or activity ID; load/score/zones/quality/profile/version |
| recovery_results, personal_references | User/date/metric/estimator/window; value/stats/counts/quality/version |
| sleep_consistency_results, stage_range_results | User/sleep/date; reference IDs, denominator, score/range/version |
| stress_intervals, stress_daily_results | User/time interval or date; state/score/masks/coverage/version |
| sleep_stress_results, sleep_stress_windows, stress_episodes | Sleep ID; nightly result and evidence intervals |
| sync_runs, sync_cursors, scheduled_jobs | Account/type/range; progress, successful coverage, errors/retries |
| calculation_runs, result_dependencies | Result/version and exact source IDs/ranges/profile/config used |
| presentation_snapshots | Optional account/profile/range cache; safe to rebuild |

Core joins: user -> provider account -> raw samples/sessions -> daily or per-session
calculations -> trends/displays. A sleep has many segments and can overlap multiple
calendar dates; an activity excludes HR by physical-time overlap. An awake baseline
on D belongs to the sleep score dated D+1. Avoid forcing all those into one date column.

## 11. Common columns and rules

For observations keep internal user/account IDs, provider resource ID/source,
physical timestamp or start/end UTC, recorded UTC offset and reporting timezone,
local date where applicable, metric/unit, original value/payload, fetched time and
availability/quality. Store upload/modified timestamps only when the provider supplies them.

For calculations keep target date and source dates, sleep/activity IDs, estimator
and version, configuration/profile snapshot, computed time, input references,
baseline window/reference counts, sample counts, covered duration, validity/default
flags and withheld reason. This supports corrections and reproducible recalculation.

Use null for missing/withheld values; zero only for a known zero. Keep raw data,
calculated results and demo data distinguishable. Keep full calculation precision;
round for display. Use explicit units (BPM, ms, minutes/seconds, percent, degrees C).
Retain UTC instants and local/recorded offsets; a time label such as `08:30` is not
a unique sample key. Never count a cached copy as a new observation. Persist provider
corrections/deletions and invalidate dependent results. Different baselines and
different score estimators must retain distinct method/version names.

## 12. Source references and API field manifest

Provider adapter: `backend/google_health_client.py`; live routes/calculations:
`backend/main.py`; typed responses: `backend/models.py`; dynamic response contracts:
`frontend/lib/types.ts`, `frontend/lib/stress.ts`; algorithms: `sleepscore.py`,
`strain.py`, `backend/recovery_score.py`, `backend/awake_heart_rate.py`,
`backend/sleep_rhr.py`, `backend/sleep_analytics.py`, `backend/stress_monitor.py`.

`DATABASE_API_FIELD_MANIFEST.json` accompanies this document with exact declared
backend response fields, route signatures and frontend interface/type declarations.
It is a code-derived contract inventory, not proof that every field is displayed
or populated for connected users. Dynamic dictionary contracts are preserved in
the frontend declarations and described above.
