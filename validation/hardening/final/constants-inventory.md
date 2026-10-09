# Numeric constants and provenance

1906 numeric literals across 40 production/support sources; booleans and test oracles are excluded. Mathematical constants, unit conversions, calendar lengths, cache controls, mock-generation values and physiological heuristics are deliberately all retained with line-level context in [numeric-constants.json](numeric-constants.json). An inline comment explains intent, not empirical validity. No coefficients or cutoffs were retuned.

| Source | Literals |
|---|---:|
| backend/auth.py | 19 |
| backend/backfill_sleep_stage_ranges.py | 5 |
| backend/backfill_sleep_stress.py | 4 |
| backend/calibrate_sleep_stress.py | 8 |
| backend/dynamic_sync.py | 1 |
| backend/google_health_client.py | 92 |
| backend/health_read_store.py | 57 |
| backend/health_trends.py | 17 |
| backend/main.py | 207 |
| backend/mock_data.py | 172 |
| backend/mock_recovery.py | 65 |
| backend/mock_sleep_stage_ranges.py | 39 |
| backend/mock_sleep_stress.py | 84 |
| backend/models.py | 21 |
| backend/page_snapshots.py | 2 |
| backend/read_metrics.py | 2 |
| backend/recovery_analytics.py | 58 |
| backend/recovery_score.py | 37 |
| backend/sleep_analytics.py | 43 |
| backend/sleep_heart_rate.py | 23 |
| backend/sleep_need.py | 36 |
| backend/sleep_need_inputs.py | 3 |
| backend/sleep_selection.py | 1 |
| backend/sleep_stage_pipeline.py | 1 |
| backend/sleep_stage_ranges.py | 19 |
| backend/sleep_stage_store.py | 25 |
| backend/sleep_stage_webhooks.py | 17 |
| backend/sleep_stress.py | 112 |
| backend/sleep_stress_pipeline.py | 1 |
| backend/sleep_stress_store.py | 1 |
| backend/sleep_sync.py | 3 |
| backend/sleep_trends.py | 56 |
| backend/strain_analytics.py | 12 |
| backend/strain_service.py | 82 |
| backend/validity.py | 17 |
| recovery.py | 93 |
| sleep_consistency.py | 53 |
| sleep_efficiency.py | 5 |
| sleepscore.py | 289 |
| strain.py | 124 |
