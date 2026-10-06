# Connected Recovery estimate

`recovery_score.py` contains pure functions and all requested tuning constants.
This implements the supplied app heuristic. Its normal-CDF percentage is a
rescaling of the combined signal, not a probability of recovery, a validated
clinical score, or WHOOP's proprietary calculation. Higher than usual HRV is
described as **above normal**, without claiming it is necessarily better.

## Google Health data mapping

The [official Google v4 schema](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints)
calls daily RMSSD `dailyHeartRateVariability.averageHeartRateVariabilityMilliseconds`
(milliseconds), rather than `dailyRmssd`. Deep-sleep RMSSD and non-REM HR are
different optional fields and are not substituted. RHR uses
`dailyRestingHeartRate.beatsPerMinute` (a numeric string), with
`dailyRestingHeartRateMetadata.calculationMethod`. Only `WITH_SLEEP` or
`ONLY_WITH_AWAKE_DATA` can establish a comparable RHR reference. Missing or
unspecified methods fall back to HRV alone.

Daily records use Google's wearer-local date; the endpoint honors `X-User-Date`.
Each reconciled date counts once. Baseline: D−67 through D−8 inclusive; recent:
D−6 through D inclusive. Nonpositive, missing and nonfinite HRV/RHR values are
discarded. No gaps are imputed. Intraday HRV coverage filtering is not enabled:
daily summaries supply no coverage duration, and live intraday access has not
been verified.

## Calculation and missing data

- HRV uses ln(RMSSD), median/MAD reference with a .05 ln-unit spread floor,
  and .7 recent-mean/.3 current-night weighting. Missing current HRV uses the
  recent mean, provided at least four recent readings exist.
- RHR uses an inverted robust z-score, with a 1 bpm floor and at least 21
  same-method reference dates. When usable it contributes .4 and HRV .6;
  otherwise HRV contributes alone.
- The last completed main sleep uses actual `summary.minutesAsleep`, excluding
  pending, impossible or unfinished readings. Below 180 minutes, that sleep is
  excluded from the duration modifier. This cutoff does not infer missing
  duration/coverage for historical daily HRV summaries.
- Last night's need is reconstructed by `SleepNeedInputs.for_tonight(D−1)`
  from the existing sleep, activity-day strain and nap calculations. It excludes
  the current sleep ending D; tonight's need is never substituted. Missing
  preceding-day HR means missing strain and therefore missing need. With
  missing sleep or need, the modifier is zero and confidence cannot be high.
- Sleep performance is capped at 1. At 85% or above there is no penalty;
  at 60% or below the penalty is −.5. Efficiency, stages, composite sleep score
  and strain are not additional Recovery components.
- Respiratory rate and wrist skin temperature use their own D−67…D−8
  references. An absolute deviation strictly above 2 × robust SD sets
  `illness_flag`. As selected, fewer than 21 valid readings or a zero-spread
  reference leaves that signal unassessed. Absent signals also leave the flag
  false. This is an anomaly heuristic, not an illness diagnosis.
- Final z is bounded to ±3, then capped at −.5 when flagged. Exact −.5 is
  **normal** under the supplied strict zone boundaries; the flag is separate.
  Classification and CDF rescaling happen before z is rounded for output.

The sleep modifier inherits the app's existing strain capacity and age-based
heart-rate-zone estimates. Confidence labels describe data availability under
the requested thresholds; they do not validate wearable measurement accuracy.

## Response and scope

Connected `/api/recovery` adds `z`, `percent`, `zone`, `confidence`, `estimated`,
`components`, `sleep_context`, `baseline_days`, `recent_nights`,
`rhr_baseline_days`, `illness_flag` and `status_reason`.

- `building_reference`: fewer than 21 baseline HRV days or four recent nights;
  z/zone/percent/confidence are null. Counts and an explanation remain present.
- `ok`: zone available. Percent (and legacy `score`, its alias) is present only
  at medium/high confidence; both are null at low confidence.
- High requires 45 baseline days, six recent nights, usable RHR and sleep.
  Medium requires 28 baseline days and five recent nights. Otherwise low.
- The existing `today_hrv`, `today_rhr`, 14-day medians and reference counts
  remain descriptive comparison fields. They are distinct from the 60-day
  scoring reference and its new counts.

Home and Recovery now preview this calculator through `/api/recovery/analytics`.
The old disconnected demo remains available with `demo=legacy`; the default
`/api/recovery` response keeps that legacy demo for existing consumers. Connected
requests always use device readings. An expired connected session gets a
reconnect response instead of silently falling back to demo data.

The connected endpoint makes nine range fetches before pagination/retries: four
daily vital types, current main sleep, historical main sleeps, naps, and one
range each for HR samples and exercises. Eight daily strain calculations reuse
those fetched activity records. Historical need matches the existing daily
calculation, with no new derived storage or stale cache. API errors propagate;
unavailable optional fields/empty collections remain missing.

## UI trends

`GET /api/recovery/analytics?timeframe=W|M|6M&end_date=YYYY-MM-DD&demo=estimate|legacy`
honors `X-User-Date`, rejects future dates, and returns daily readings, current
Recovery, personal typical ranges, previous-period averages, six monthly buckets,
prior-30-day comparisons, available sleep context and Health Monitor coverage.
W is seven days, M is 30 days, and 6M is six calendar months. Previous/next arrows
move by these same periods. Missing readings remain gaps and are excluded from
averages. RHR trends and comparisons include only the current reading's known
calculation method. Typical bands use the scoring reference's median ± robust SD
(HRV in log space), with the existing HRV/RHR spread floors; other flat or
insufficient bands are unassessed. These are descriptive personal ranges.

Historical Recovery recalculates the documented HRV/RHR-only fallback separately
for each date, since historical sleep need is not stored. Its confidence cannot
be high. Each plotted day exposes this missing sleep context. Current Recovery
uses the same sleep/need path as `/api/recovery`; historical connected composite
sleep performance remains unavailable without historical need. No score or sleep
algorithm is changed for the UI. Six-month vital plots overlay monthly averages
on a faint daily trace; percentage plots retain bars.

Disconnected UI fixtures provide date-seeded varied vitals, outliers and gaps,
using the existing sleep mock fixtures and calculation. The footer labels all
demo values synthetic and lets users switch to the older prototype score. That
prototype has no stored historical scores, so its earlier bars remain blank.
Stress Monitor and Behavior Insights retain their layouts with unavailable
states, rather than inventing daytime stress or causal claims. Activity times,
device battery and streak are unavailable when the data layer does not supply
them; workout badges show recorded heart-rate-zone minutes, not a fabricated
workout strain score.

The connected analytics endpoint makes ten range fetches before pagination and
retries: five daily vital types, main sleep history and the four existing
sleep-need inputs. The returned `current` fields match `/api/recovery`.

## Demo and tests

`mock_recovery.py` supplies twelve seeded Google v4-shaped scenarios through the
real normalization and connected computation path, replacing only network I/O.
These are synthetic fixtures, not measured physiological data. They do not
replace the app's default demo-mode algorithm.

Run from the repository root in PowerShell:

```powershell
& .\.venv\Scripts\python.exe backend/mock_recovery.py
$env:PYTHONPATH = 'backend'
& .\.venv\Scripts\python.exe -m unittest backend.test_recovery_score backend.test_recovery_integration backend.test_health
```

Live Google Health/Fitbit device verification remains pending API access.
