# Stress Monitor: evidence and implementation constraints

Research date: 2026-10-10. App integration updated 2026-10-11. The shared HR-based model now powers Home and the detailed Stress page. It remains unvalidated.

## Product methods that are publicly documented

- **WHOOP:** uses current heart rate and HRV, a personal baseline from the prior 14 days, and motion context. The display is 0–3 physiological stress. Its public explanation does not disclose a reproducible formula, feature weights, artifact rejection rules, or calibration mapping. A matching display does not establish matching scores.
  - [Introducing Stress Monitor](https://www.whoop.com/us/en/thelocker/introducing-stress-monitor-a-new-way-to-monitor-manage-stress/)
  - [Launch announcement](https://www.whoop.com/us/en/press-center/whoop-launches-new-stress-monitor-feature-first-wearable-to-measure-daily-stress-levels-and-implement-stress-reduction-interventions-in-real-time/)
- **Bevel:** describes combining HR and HRV while accounting for movement, with a 0–100 display. Its HRV explanation distinguishes sleeping HRV for Recovery from measurements throughout the day for Stress. Its public pages do not supply a reproducible stress equation. Dividing its score by 100 and multiplying by 3 would not reproduce WHOOP.
  - [Stress Monitor](https://www.bevel.health/blog/stress-monitor)
  - [Heart Rate Variability](https://www.bevel.health/blog/the-basics-heart-rate-variability)

## Peer-reviewed evidence

1. **Quigley et al., 2024, Psychophysiology**, DOI 10.1111/psyp.14604. Measurement and interpretation guidance for HR/HRV, including ECG and PPG limitations in ambulatory settings. Use it to define acquisition, quality checks, and reporting; it does not validate a consumer 0–3 scale.
   [PubMed](https://pubmed.ncbi.nlm.nih.gov/38873876/)
2. **Immanuel et al., 2023, Psychotherapy and Psychosomatics**, DOI 10.1159/000530376. Review of 15 studies using repeated HRV measurements and validated stress assessments. RMSSD was commonly associated with stress, but protocols and assessment methods varied. Supports collecting contextual and subjective measurements for validation.
   [PubMed](https://pubmed.ncbi.nlm.nih.gov/37290411/)
3. **Hernando et al., 2018, Sensors**, DOI 10.3390/s18082619. Study of 20 healthy volunteers during relaxation and mild cognitive stress. Apple Watch RR-derived RMSSD reflected stress-related changes; missing intervals affected some frequency-domain measures. These results concern that device/protocol, not Fitbit or our proposed scoring model.
   [PubMed](https://pubmed.ncbi.nlm.nih.gov/30103376/)
4. **Stress Watch pilot study, 2022.** Used ECG and Fitbit heart rate during induced stress in two cohorts of 30 participants. It found changes between rest and stress but no ubiquitous pattern of HR and HRV changes. This argues against claiming that an arbitrary weighted formula is accurate for everyone.
   [PubMed](https://pubmed.ncbi.nlm.nih.gov/35009696/)

## Current data availability

Google's sleep guide describes HRV collection during sleep. The schema exposes timestamped RMSSD/SDNN summaries, but the examined HRV schema does not specify an analysis-window duration or whether the timestamp anchors its start or end. The existing Sleep Stress integration already withholds scores until timing is verified.

- [Google sleep data guide](https://developers.google.com/health/data-types/sleep)
- [Google HRV schema](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints#HeartRateVariability)

A read-only audit of the local cache on 2026-10-10 found 274 distinct HRV timestamps, from October 5 to October 10 UTC. All 274 fell inside a cached sleep interval. No awake HRV samples were observed. This describes the current stored data, not a guarantee about every device or future API response. The integration has recorded HR, sleep, and exercise sessions, but does not ingest a raw motion stream for this feature.

Nightly HRV must not be repeated across daytime as if it were measured then. Sampled BPM must not be converted into fabricated beat-to-beat HRV. A heart-rate-only activation estimate would be a different, experimental metric.

## Proposed calculation and display contract

Implementation contract:

1. Align genuine HR and RMSSD observations to verified measurement intervals. Reject invalid values and insufficient coverage; retain gaps.
2. Use earlier observations for a personal reference, with sleep and activity context. The 14-day lookback is informed by WHOOP's public description; minimum sample counts and quality thresholds would be our own explicit engineering choices.
3. Candidate features are HR elevation and reduction in log-RMSSD relative to that reference. Robust median/spread normalization is an inspectable approach, not WHOOP's disclosed formula. Do not claim a particular set of weights or 0–3 mapping is peer-reviewed without directly applicable validation.
4. Mark recorded sleep and exercise on the chart. Logged sessions alone cannot identify all movement or distinguish psychological from physical causes.
5. Display a clearly identified estimate on the requested 0–3 UI. The latest measurement time, sync completion time, and data coverage are different facts. Empty or stale periods must not become low stress.
6. Count low/medium/high time only over scored intervals. Keep missing time separate. Any category thresholds are display conventions until validated.

The existing binary Sleep Stress detector cannot simply be relabeled as this continuous score: it currently detects elevated sleep stress and does not classify every other window as low or medium.

## Implemented app model (unvalidated)

`stress_inputs.py` adapts stored Google observations into `stressmon.pipeline.score_inputs`; the app and optional export diagnostics share this engine. Physiological bounds and trailing Hampel filtering precede minute medians requiring ten samples. Five-minute HR windows require three valid minutes. Activity-level intervals provide recorded sedentary context; unknown activity remains ambiguous and cannot enter the sedentary baseline.

HR references pool sleep and sedentary windows over 14 reference days. Robust spread is `max(4 bpm, 1.4826 * MAD)`. At least three reference days are required; fewer than seven are low confidence. With at least 14 available dates, references use prior dates only. Shorter histories use bounded retrospective references, potentially including the scored date and later dates, explicitly marked `baseline_leaks` in the response and UI.

Awake features use standardized HR plus an optional previous completed-night context term. Verified sleep HRV uses ln(RMSSD), coverage at least 0.8, physiological bounds, known window anchoring, and sleep containment. Unknown coverage removes HRV from both paired sleep features and previous-night context, as the user confirmed. The documented Google schema has no coverage field, so connected API observations currently contribute no HRV. Synthetic demo observations have explicitly known coverage and end anchoring.

The default mapping is `3 / (1 + exp(-0.6 * (z - 2)))`, with configurable feature weights and robust spread floors in `stressmon/config.yaml`. Causal EMA smoothing never crosses gaps or sleep/wake transitions. These parameters are engineering choices, not peer-reviewed or WHOOP coefficients. Vigorous workouts and recovery buffers remain unscored; lower-effort activity can be scored with explicit context.

Low is below 1, medium is 1 to below 2, high is 2 to 3. Durations use unrounded scores and elapsed seconds; averages are duration weighted. Missing intervals are reported separately and never enter category totals. The current score is withheld after 15 minutes without a reading. Demo HR/HRV values and reference values are synthetic, with a fixed 14:45 cutoff and a two-hour missing-data gap. The demo validates plumbing and numerical behavior only.

The demo reuses Home's activity showcase and sleep fixtures. Synthetic raw HR and RMSSD pass through the actual app calculation. Only sessions before the 14:45 cutoff appear in today's Stress window.

The live adapter reads account-scoped Google storage and returns estimated HR-based scores only with adequate HR sampling and reference observations. Missing HR, inadequate baselines, masked exercise, and stale current readings remain unavailable. Foreground sync includes activity levels with a bounded initial baseline backfill; existing HR/workout delta policies remain intact. No Takeout path or CLI run is required in the app.

## Verification

- Deterministic tests: time alignment, duplicate timestamps, missing HRV, motion/activity context, sparse HR, spikes, stale values, DST and local midnight, baseline leakage, bounded outputs, and duration accounting.
- Synthetic examples: restful periods, exercise, plausible elevated activation, and missing data. These verify implementation behavior only.
- Empirical validation: time-aligned measurements and repeated self-reports; separate calibration from held-out dates/people. Report coverage, agreement, error, and failure cases. Agreement with WHOOP/Bevel would measure agreement with another proprietary estimate, not establish a physiological ground truth.

## Confirmed scope and data policy

- Home card plus a detailed Stress page, daily category durations, overlays, and trends.
- The later user-supplied stressmon specification authorizes HR-based awake estimates and optional verified nighttime context. It supersedes the earlier paired-only prototype policy. No fabricated daytime HRV or substitution of unknown-quality nightly HRV is permitted.
- Synthetic tests and an explicitly unvalidated estimate; no simultaneous WHOOP/Bevel comparison readings are available.
- Official API recheck: Google lists `heart-rate-variability` and `daily-heart-rate-variability`, but no stress score in its data-type catalog. Its sleep guide explicitly describes sleep-only HRV collection. The legacy [Fitbit intraday HRV endpoint](https://dev.fitbit.com/build/reference/web-api/intraday/get-hrv-intraday-by-date/) likewise limits collection to sleep despite the word "intraday".
- A fresh account audit was attempted through a temporary authenticated localhost service. The in-app browser blocked that navigation; no fresh provider result was obtained. The 274-record finding above remains a cache observation only.
