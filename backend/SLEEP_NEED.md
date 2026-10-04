# Sleep Need

`sleep_need.py` contains the pure calculation, immutable inputs/results, display
formatter and all tuning constants. This is the requested app estimate, not a
validated WHOOP formula or a sleep requirement supplied by Google Health.

- Default baseline: 450 minutes. An explicit `baseline_need_min` overrides it in
  the pure functions. No baseline setting exists in the current app, so no new
  settings or persistence are added.
- Strain percentages convert to 0–21 before the normalized logistic addition
  (0–26 minutes, contributions below one minute become zero).
- Debt uses the seven latest calendar-night slots, newest first, weighted
  1/.85/.7/.55/.4/.25/.1. Missing sleep or strain retains an empty slot and is
  excluded from the numerator and denominator. Surpluses offset shortfalls.
- Each night's reference need is baseline plus its preceding activity day's
  strain addition. Debt repayment is never included in that reference need.
- Total is baseline + strain addition + 34% of debt − actual nap sleep, bounded
  to 360–660 minutes. Minutes remain floats until the display formatter is used.

## Data and date alignment

Google v4 sleep `summary.minutesAsleep` is in minutes and may be a numeric string.
Main sleeps are selected using the existing Fitbit main-sleep selection. Missing,
pending, incomplete or impossible durations are excluded from debt; a reported
zero remains a reading. The historical `endUtcOffset` determines the wake date;
physical UTC endpoints determine elapsed duration, including DST changes.
Processed naps use their actual asleep minutes, not elapsed session duration,
and are summed by local completion date. Reconciled duplicate nap IDs count once.

Activity-day strain is the existing app-calculated `score_100`, derived from
Google heart-rate and exercise records. Google does not provide this strain
score. An absent HR stream yields missing strain, rather than a zero-strain day.

For a sleep ending on D, its pre-sleep estimate uses activity D−1, main sleeps
ending D−1 through D−7, and their respective preceding activity days. The sleep
ending D cannot change its own pre-sleep need. Tonight's estimate uses activity D,
the main sleeps ending D through D−6, and naps completed on D.

## API integration

- `/api/sleep/need`: tonight's six requested float fields, `formatted_total_need`,
  `date`, `is_mock`, `status`, and a separate `last_night` result. When today's
  strain is missing, status is `missing_strain`, the formatted total is null and
  no tonight calculation fields are returned.
- `/api/sleep` and dashboard sleep: existing hour fields keep their last-night
  meaning. `sleep_need` contains the exact six-field pre-sleep result;
  `tonight_sleep_need` is separate. Need/debt and dependent score fields are null
  if preceding-day strain is unavailable.
- `/api/sleep/analytics`: existing `need_minutes` and `need_components` power
  the unchanged cards. `nap_credit` is an additional component field, and
  `tonight_sleep_need` is separate. Connected historical estimates remain blank;
  the current comparison must still match the identified main sleep.

The app reads wearable data on API requests; it has no sleep, nap or strain save
route. Each request recalculates from the latest source values, so the next fetch
reflects changes without a stale derived cache. Historical strain requests use
bounded concurrency. Demo history uses the existing varied identifiable sleep
fixtures and date-seeded strain; today's demo strain uses the existing strain
calculation. Live Google/device verification remains pending access.

## Verification

From the repository root with `backend` on `PYTHONPATH`:

```text
python -m unittest backend.test_sleep_need backend.test_sleep_need_integration backend.test_sleep_analytics backend.test_google_health_client
```
