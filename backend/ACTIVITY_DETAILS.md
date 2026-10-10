# Home dashboard and activity details

`/api/home/metrics` returns the dashboard rows, daily cardio Strain and recorded activities. `/api/activity?id=…` returns an activity's cleaned heart-rate trace, Zones 0–5, measured HR coverage, and comparisons with the same exercise type in the previous 30 days. Dates and activity times retain the recorded UTC offset.

The Strain algorithm and zone thresholds are unchanged. Zone 0 is counted usable time below 50% of estimated HRmax; missing HR intervals are reported separately. Overlapping intervals belong to the first logged session, matching the Strain calculator. Unknown measurements remain null.

Dashboard comparisons use prior recorded values. Weekly HR-zone and strength durations compare complete seven-day totals; incomplete HR weeks are excluded. Historical sleep-performance comparisons can remain unavailable because historical sleep-need results are not stored. VO₂ max uses the most recent available reading in the displayed month.

Connected activity steps, calories, muscular contribution, routes and personal typical ranges are unavailable in this presentation adapter. Daily step totals are still read from the provider. No workout totals or maps are inferred from them.

`/?demo=true` opens a separate Home preview with deterministic walking, running and weightlifting sessions, raw synthetic HR and calculated cardio scores. Example steps, calories, muscular splits, typical ranges, route diagrams and daytime stress are labeled illustrative. This preview does not refresh or disconnect the live account. Activity links preserve the day and demo mode. Existing Strain previews use `source=strain` to retain their original fixture.

The Home aggregate invokes the underlying sleep/health functions directly because the page cache keys use the incoming request URL; re-entering decorated endpoints with a Home request would collide with Home's own cache entry.

Regression tests: `backend/test_activity_details.py` and `frontend/lib/activity.test.mjs`.
