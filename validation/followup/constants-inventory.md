# Numeric constants and provenance

Every numeric literal in the listed computation/adaptation layers is inventoried, including inline values and defaults. Comments explain intent; they do not establish empirical validity. Zero/one, seconds-per-minute, normalization scales, calendar counts and cache limits are included conservatively and need dimensional/engineering review rather than physiological calibration. Scoring coefficients and cutoffs need held-out outcome validation. No coefficients were retuned.

| Source | Literals |
|---|---:|
| strain.py | 124 |
| sleepscore.py | 285 |
| recovery.py | 95 |
| sleep_consistency.py | 53 |
| sleep_efficiency.py | 5 |
| backend/recovery_score.py | 38 |
| backend/sleep_need.py | 36 |
| backend/sleep_need_inputs.py | 3 |
| backend/sleep_stress.py | 105 |
| backend/sleep_stage_ranges.py | 19 |
| backend/health_trends.py | 20 |
| backend/sleep_trends.py | 54 |
| backend/strain_analytics.py | 11 |
| backend/recovery_analytics.py | 56 |
| backend/sleep_analytics.py | 43 |
| backend/main.py | 195 |
| backend/strain_service.py | 82 |
| backend/google_health_client.py | 86 |
| backend/sleep_heart_rate.py | 23 |

Full line-level context and nearby inline comments: numeric-constants.json.
