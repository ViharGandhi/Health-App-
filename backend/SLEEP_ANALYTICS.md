# Sleep overview and detail data

`GET /api/sleep/analytics?timeframe=W|M|6M` powers the daily cards and new trend details.

- W: seven wake dates. M: thirty wake dates. 6M: a rolling six-month interval.
- One completed Fitbit main sleep per historical local wake date; naps are excluded.
- `sleep.interval.startTime/endTime` determine physical elapsed duration. Historical
  `startUtcOffset/endUtcOffset` preserve the device's local bed/wake clock times.
- The UI's **Time in Bed** is the recorded sleep period, not measured physical bed occupancy.
- Processed, valid stage intervals determine asleep, awake, deep and REM durations.
  Pending, invalid or unavailable stage partitions have null durations rather than zeros.
- Summary latency/post-wake minutes determine onset/wake; otherwise validated sleep
  segments provide those boundaries. Timing scores use the existing four-night algorithm.
- Restorative sleep is deep + REM. Efficiency is asleep / recorded period × 100.
- Wake events count the union of awake stage bouts and short awakenings; overlapping
  short awakenings are never added to stage duration totals.
- Range comparisons use observed daily values and exclude missing values. 6M charts
  average each rolling seven-day block; range averages still use individual nights.
- Daily dashed timing guides describe the prior four displayed nights, not an optimal
  sleep schedule or a clinical reference range.

The sleep score formula is unchanged; its sleep-need input now uses the requested
Sleep Need module (`sleep_need.py`). Synthetic historical scores call the existing
score calculator with date-seeded inputs. The existing component fields now carry
the baseline, logistic strain addition and weighted debt repayment; nap credit is
subtracted from the total. See `SLEEP_NEED.md` for the calculation and date joins.

For a connected device, the current score/need is attached only when its local
endpoints and asleep duration match the identified sleep. Earlier connected app
score/need estimates are unavailable, so those historical points remain blank.
Other observed metrics can show their available history. These derived scores are
not supplied by Google Health or WHOOP.

Stage, heart-rate, efficiency and consistency demo views share identifiable sleep
fixtures. Stress retains its existing separate synthetic samples and high-stress
detector; the overview labels that distinction. Connected stress is joined by sleep
ID, and unmeasured windows are never classified as stress-free.

Schema reference: [Google Health v4 DataPoint / Sleep](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints#Sleep).
Live Fitbit Air verification remains pending device/API access.

Verification: `python -m unittest backend.test_sleep_analytics backend.test_sleep_trends backend.test_sleep_heart_rate`
with the project root and `backend` on `PYTHONPATH`.
