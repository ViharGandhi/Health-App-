# Overnight heart-rate graph

`GET /api/sleep/heart-rate?night_date=YYYY-MM-DD&sleep_id=...` returns the
identified main sleep and its observed BPM samples. The frontend passes the same
record ID and wake date as the stage breakdown. With no parameters, select the
latest completed main sleep within ten wake dates. Exclude naps and known
non-Fitbit platforms; prioritize an explicit `mainSleep`, otherwise the longest
sleep on the latest date. Pending or CLASSIC stages do not prevent reading HR.

## Google Health v4 contract

1. List sleep records by `sleep.interval.civil_end_time`; retain the session ID,
   `sleep.interval.startTime/endTime`, and `startUtcOffset/endUtcOffset`.
2. Request `/v4/users/me/dataTypes/heart-rate/dataPoints:reconcile` with
   `dataSourceFamily=users/me/dataSourceFamilies/google-wearables` and:

   `heart_rate.sample_time.physical_time >= "<sleep start UTC>" AND heart_rate.sample_time.physical_time < "<sleep end UTC>"`

3. Follow every `nextPageToken`. Read `heartRate.sampleTime.physicalTime`,
   `heartRate.sampleTime.utcOffset`, and `heartRate.beatsPerMinute` (a JSON string
   integer, documented range 1–300). Keep UTC instants for chronological plotting
   and the supplied offset for historical local labels, including DST/travel.
4. Sort and deduplicate samples. Reject invalid/out-of-window observations and
   conflicting samples at one timestamp. Empty data stays empty. Expired connected
   sessions return 401 instead of synthetic readings.

Scopes already requested by app OAuth:
`googlehealth.sleep.readonly` and
`googlehealth.health_metrics_and_measurements.readonly`.

Google lists Fitbit Air as compatible and HR storage resolution as 1 second.
Storage resolution does **not** guarantee a reading every second: use timestamps
actually returned. Wearable reconciliation includes Google/Fitbit trackers, not
only one particular paired device; multi-device attribution needs live checking.

## Presentation and demo

- Hover/tap selects an actual sample, displaying BPM, local date/time and UTC offset.
- Keyboard arrows, Home, End and Escape inspect/dismiss the same samples.
- Gaps greater than five minutes remain disconnected. This is a display rule,
  not a physiological or API sampling rule. No values are interpolated for gaps.
- Dense curves retain first/last and min/max observations per SVG column; tooltip
  lookup still uses the complete sample stream.
- Date-seeded **synthetic** demo readings share the stage fixture's sleep session,
  vary across the night and include a twelve-minute missing-data interval. Demo
  sampling every approximately 45 seconds is a fixture choice.

Schema and fixture tests are available; a live Fitbit Air account response is
still required before claiming device integration is verified.

Sources checked 2026-10-03:
- https://developers.google.com/health/data-types/vitals
- https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints#HeartRate
- https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/list
- https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/reconcile
