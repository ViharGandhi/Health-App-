# Cardio Strain model

The connected API and synthetic demo use the same pure HRR/TRIMP calculator in `strain.py`. This is the supplied WHOOP-style approximation; matching these equations does not establish equivalence to WHOOP's proprietary score. Muscular Load is excluded.

## Calculation

- The current day starts at the latest main wake time; a main sleep lasts at least three hours and is not marked as a nap. Without one, use local midnight. Past days start at their main wake time and end at the next main sleep's start, or midnight.
- Keep timezone-aware HR readings within that window, sort and deduplicate timestamps, reject readings outside 30–230 bpm, and reject deviations greater than 35 bpm from the centered five-sample median. Match the supplied reference's repeated edge padding; fewer than five readings skip spike filtering.
- HRmax is `208 - 0.7 * age`. HRrest is the median of available resting HR values from the last seven calendar nights, or a flagged 60 bpm default. The optional observed sustained HRmax uplift is deferred.
- Consecutive intervals up to 300 seconds count their actual duration; longer gaps contribute no coverage or load. HRR uses the pair's mean HR and is clipped to 0–1.1. Below HRR 0.20, load is zero.
- Load is `minutes * HRR * a * exp(b * HRR)`: male coefficients 0.64/1.92, female coefficients 0.86/1.67.
- Strain is `21 * (1 - exp(-load / STRAIN_L))`, default L=90. API score/load presentation rounds to one decimal; calculations retain precision. Labels use the unrounded score: Light <10, Moderate <14, High <18, All Out otherwise.
- Workout loads use interval midpoints. The earliest-starting workout owns an overlapping interval. Loads below 0.5 are omitted from computed workouts. Workout scores are not additive to Day Strain.
- Coverage includes every usable interval, even below the load threshold. Below 60% coverage is flagged. Unlogged high-effort suggestions are already included in day load and do not add load again.

## API and UI

`GET /api/strain?date=YYYY-MM-DD` supports connected data and `demo=true`. The demo explicitly supplies a synthetic profile if no age is provided; connected Strain never falls back to `USER_AGE`.

| Contract change | Meaning |
| --- | --- |
| `strain`, `label`, `load` | Absolute 0–21 cardio score and raw TRIMP load |
| `date`, `mode`, `day_window` | Selected date, connected/demo mode, aware boundaries and source |
| `coverage`, `low_coverage`, `sample_count`, `counted_minutes` | Data quality and usable duration |
| `age_missing`, `calibrating`, `params` | Missing age is withheld; calibration flags defaulted resting HR or sex coefficients |
| `analytics` | 7/28-day mean strain, load-based acute/chronic ratio, optional Recovery target |
| `suggested_workouts` | Unlogged effort intervals without additional load |
| `activity_zone_minutes` | Logged-activity zone minutes for the screenshot-based UI |
| `workouts[].strain` | Now the real calculated 0–21 workout score; `load` carries raw TRIMP |
| `max_hr` | Observed maximum cleaned HR; physiological HRmax is now `params.hr_max` |

No HTTP response fields were removed. Deprecated aliases remain: `score_21` aliases `strain`; `score_100` is `strain / 21 * 100`, without personal capacity normalization; `workout_strain` and `incidental_strain` retain raw load under legacy names. `age_is_default` is a legacy missing-age flag; use `age_missing` instead. `is_calibrating` aliases `calibrating`. Old capacity and linear-conversion Python helpers were removed after checking their consumers.

Day `zone_minutes` includes all usable HR intervals above 50% HRmax. The UI's zone charts use logged activities only, as requested. Missing workout HR coverage leaves activity zones unavailable. No HR produces API strain 0/coverage 0 with known age; trend bars remain blank for unrecorded days. Missing age returns null load, score and zones. Google failures return a clear error rather than fabricated scores.

Age is validated from `X-User-Age` (18–100). Sex accepts `X-User-Sex` or `USER_SEX` (`m`/`f`); an absent setting uses flagged male coefficients. The frontend sends the browser's IANA timezone through `X-User-Timezone`; direct API callers without that header use UTC. API timestamps preserve supplied UTC offsets, with physical elapsed-time arithmetic across DST.

`/api/strain/analytics` supports W/M/6M for Day Strain, zones 1–3, zones 4–5, strength activity time and steps. The ring, workout badges, historical strain bars, labels and breakdown bands all read the new model. Recovery target bands are the supplied configurable defaults, not learned recommendations. Connected targets stay unavailable when Recovery withholds its score. Demo Recovery is explicitly labeled 72%.

## Sleep-need dependency

`_load_sleep_need_inputs` now calculates historical Strain with this same model. It supplies the unrounded `strain / 21 * 100` to the existing percent-shaped `SleepNeedInputs` contract; the existing adapter multiplies by 0.21 to recover the same 0–21 value. Missing age or zero HR coverage supplies no strain value. Personal-capacity normalization is gone.

Sleep's logistic addition and caps are unchanged: Strain adds 0–26 minutes; total sleep need remains capped at 360–660 minutes (6–11 hours). Recovery and Sleep scoring formulas were not changed.

## Inputs, caching and limits

The existing Google client handles every pagination token, request pacing and 429/503 retries. The service fetches HR, exercise intervals, sleep sessions and the same daily resting-HR summaries used by Recovery. Extra surrounding dates cover midnight-crossing sessions. Daily results are cached in process by account, date, timezone, age, sex and config: today 60 seconds, historical days six hours. Raw request caching is 60 seconds. Restart clears these caches.

Google shapes, units, civil-time filters and pagination were checked against the [workout documentation](https://developers.google.com/health/data-types/workouts), [sleep documentation](https://developers.google.com/health/data-types/sleep) and [data-point list reference](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/list), then exercised with the connected account. HR and exercise reuse existing parsers with offset preservation. Sleep uses its interval and optional `metadata.mainSleep`/`metadata.nap`; absent metadata uses the duration rule. No unverified new required API field is used. A connected account cannot verify all optional workout types, absent-data patterns or optical artifacts; deterministic tests cover those cases.

## Verification

Backend regression run: **220 tests and 27 subtests passed**. After the final calibration-flag correction, all **31 cardio-specific tests passed** again. Frontend: TypeScript `--noEmit` passed and all **7 Strain helper/chart tests passed**.

Browser verification: all five demo metrics rendered in W/M/6M; keyboard bar selection and Escape clearing showed the corresponding zone breakdown. Connected Strain and activity-zone history rendered, and both overview tabs were left open. An upstream Google error during repeated requests recovered through Retry. The demo API and UI agree on age 22: Day Strain 10.6, workout Strain 8.6, coverage 100%, target 14–18.

Independent constant-HR sanity cases, age 30, resting HR 56, L=90:

| Scenario | Calculated score |
| --- | ---: |
| 45 minutes at 135 bpm | 9.64 |
| 45 minutes at 160 bpm | 14.46 |
| 60 minutes at 172 bpm | 18.35 |

These follow the specified curve. The visual demo also contains a workout ramp, incidental effort and selectable profile age, so its scores differ from the constant-HR cases. Demo history is deterministic by calendar date across range navigation.

Tests cover hand-computed sex coefficients, filtering, gaps, missing age, empty/single samples, midpoint/overlap allocation, zone boundaries, main sleep/naps, DST coverage, targets, history, user/profile cache isolation, date-stable demos, mocked API failures and the Sleep adapter. Existing regressions were updated where they asserted the removed capacity model, one-minute gap substitution, old physiology-max field or old fetch counts; the new service additionally fetches sleep and resting-HR context.

## Configuration and tuning

All model settings live in `StrainConfig`. Environment names use `STRAIN_` plus the uppercase field name; the curve uses `STRAIN_L` (for example `STRAIN_MAX_GAP_S`, `STRAIN_MIN_HRR`, `STRAIN_AUTO_WORKOUT_MIN`, `STRAIN_MIN_MAIN_SLEEP_H`, `STRAIN_LOW_COVERAGE_THRESHOLD`). Invalid values fail at startup. Restart after changing config.

Keep L fixed while comparing effort logs. Higher L lowers the score for the same load; lower L raises it. For a representative observed load T and desired score S between 0 and 21, `L = -T / ln(1 - S / 21)`. Compare several well-covered sessions rather than calibrating from a missing-data day. This personal tuning does not validate equivalence to WHOOP.

## Files in this upgrade

- Calculator: `strain.py`.
- Added: `backend/strain_service.py`, `backend/test_cardio_strain.py`, `backend/requirements-dev.txt`, this report.
- Backend integration: `backend/main.py`, `backend/models.py`, `backend/google_health_client.py`, `backend/strain_analytics.py`, `backend/mock_data.py`, `backend/mock_recovery.py`, `backend/requirements.txt`.
- Regression adaptations: `backend/test_health.py`, `backend/test_recovery_analytics.py`, `backend/test_recovery_integration.py`, `backend/test_sleep_need_integration.py`, `backend/test_strain_analytics.py`.
- Documentation: `backend/SLEEP_NEED.md` now describes the adapter; `STRAIN_REVIEW.md` points its historical review to this implemented model.
- UI connection: `frontend/lib/api.ts`, `frontend/lib/types.ts`, `frontend/lib/strain.ts`, `frontend/lib/strain.test.mjs`, `frontend/app/strain/page.tsx`, `frontend/components/StrainTrendDetail.tsx`, `frontend/components/StrainBreakdown.tsx`, `frontend/components/StrainGuide.tsx`, and the missing-score display in `frontend/app/page.tsx`. The existing screenshot-based layout is retained.
