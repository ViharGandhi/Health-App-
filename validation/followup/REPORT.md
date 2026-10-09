# Health backend audit and correction report

Audit: 8 October 2026. Branch: `fix/backend-audit`. Synthetic anchor: 7 October 2026; seed: `20261007`.

## Verdict

The five original findings were independently reproduced and corrected. The two scoring changes follow your explicit choices; other coefficients, weights, confidence thresholds and target bands were retained. Additional numerical, missing-data and integration defects were reproduced and corrected in separate commits.

Final verification: **381 backend tests plus 27 subtests passed**, **1,295/1,295 deterministic simulation checks passed**, and **7 offline live-runner checks passed**. Nineteen demo routes returned 200 with outbound HTTP blocked. There is one Starlette/AnyIO `BlockingPortal` deprecation warning. This establishes implementation behavior on the tested domains, not physiological accuracy, sensitivity or specificity.

Null is the correct result for unavailable or withheld data. Requiring every field to be numeric would contradict the existing missing-data and confidence rules. The replay checks finite numbers and meaningful missingness rather than replacing unknown values with invented scores.

| Module | Implementation verdict |
|---|---|
| Cardio strain | Equations consistent on tested domains; invalid RHR now rejected, counted and flagged. |
| Connected Recovery | Robust-reference calculations consistent; today now has exactly 30% log-signal weight. |
| Sleep need | Numerically consistent with supplied bounded logistic/debt heuristic; no retuning. |
| Composite sleep score | Approved continuous duration curve; unusable summaries now withhold scores. |
| Sleep efficiency | Valid-denominator and pooled-duration behavior verified; invalid periods withheld. |
| Sleep consistency | Clock-based four-night score and seven-night variability verified; distinct estimators. |
| Stage ranges | Complete partitions, denominators and personal bands verified; ranges remain descriptive. |
| Sleep stress | Unique-night baseline, main-sleep priority, finite HRV and episode rules corrected/verified. |
| Health trends | Invalid summaries excluded before all aggregates; connected VO2 range reads corrected. |
| Legacy helpers | Selected formulas verified; nonfinite log statistics and invalid current-vital fallback corrected. |
| API/cache assembly | Demo date/profile agreement verified; derived-cache namespaces changed to prevent stale results bypassing fixes. |

## Baseline and source drift

The untouched current suite had **258 passed, 1 failed, 27 subtests and 1 warning**, in **72.38 seconds**; subprocess wall time was 73.64 seconds. The existing simulation script passed all 1,295 checks in 6.74 seconds. The pre-existing failure was a synthetic connected-stage client missing `account_key`, which the newer client contract requires. Supplying that key repaired the fixture; production behavior was not weakened to accommodate it.

The old `source-hashes.json` did **not** match current sources. Ten previously inventoried files had substantive content changes, including after CRLF/LF normalization:

`backend/auth.py`, `backend/google_health_client.py`, `backend/main.py`, `backend/models.py`, `backend/sleep_stress.py`, `backend/sleep_stress_pipeline.py`, `backend/strain_service.py`, `backend/test_health.py`, `backend/test_sleep_need_integration.py`, `backend/test_sleep_stress.py`.

The comparison is against audit commit `9304073`; see [source-drift.json](source-drift.json). New durable-read, dynamic-sync, sleep-sync and page-snapshot layers also existed beyond the previous report's memory-cache description. The current connected path often reads stored observations and frozen page results, rather than issuing the earlier report's fixed number of network fetches. Sleep stress now infers HR cadence using a median and withholds scores when the HRV timestamp anchor is unverified. These pre-task changes were checked through the expanded regression suite and current source, rather than assuming the earlier report still described the implementation.

The original audit files are preserved in [previous/](previous/). The actual pre-fix run is in [baseline/](baseline/), with [baseline test log](baseline-tests.log), [XML](baseline-tests.xml), and [metadata](baseline-metadata.json). The baseline script refuses to overwrite an already recorded baseline. [Final source hashes](final/source-hashes.json) identify the corrected Python sources and audit scripts; [callable inventory](final/algorithm-inventory.md) records current functions. An inventory is not exhaustive branch coverage.

## Findings, root causes and fixes

Every production issue below has a reproducer that failed before its fix. Commit IDs identify separate local commits; nothing was pushed or deployed.

| ID | Module / severity | Reproduced root cause | Status / commit | Regression evidence |
|---|---|---|---|---|
| F01 | Sleep score / medium | `SleepCalculator.calculate_score`: sigmoid ended at 88.08, next branch started at 100; weighted jump ~3.22. | Done, approved rescaling; `5d9af3a` | `test_sleep_duration_continuity.py`; 5 failed/2 passed before. |
| F02 | Stress baseline / high | `sleep_stress.build_baseline` counted raw prepared rows, allowing one repeated night to satisfy seven-night minimum. | Done, ID and wake-date deduplication; `44c17dc` | `test_stress_baseline_uniqueness.py`: repeated ID, multiple sessions, nap/main. |
| F03 | Health trends / high | `build_health_response` filtered only absent values; invalid numbers entered reference medians and averages. | Done, approved existing/unit limits; `110ef8e` | `test_health_validity.py`: all eight metrics, zero/negative/NaN/inf, existing bounds, extreme finite values. |
| F04 | Strain / high | `calculate_strain` accepted RHR above HRmax, making HRR/load zero silently; strings also failed finite checks. | Done, rejection/default/count/calibration; `251e290` | `test_strain_rhr_validity.py`: >=HRmax, <30, 1000, nonfinite, numeric/invalid strings, mixed histories. |
| F05 | Recovery / medium | `recovery_from_history`: today entered both recent mean and current term, giving 40% weight with seven readings. | Done, approved prior-seven-date mean; `4dc6608` | `test_recovery_today_weight.py`: 20% up/down, doubled today, six prior nights, minimum count, D−7. |
| F06 | Stage integration fixture / low | Old fake client lacked the current `account_key` contract. | Done, fixture repair; `252dae5` | Existing connected-stage test failed in baseline and passed after. |
| F07 | Demo assembly / medium | Several helpers used server date; dashboard used default strain profile while detail honored headers. Legacy analytics also ignored selected profile. | Done; `db34832`, `a2cbeca` | `test_demo_alignment.py`: selected date, age 70, female, Berlin timezone, exact dashboard/detail/legacy-current agreement. |
| F08 | Stress numerics / high | `prepare_night` checked HRV <=0, allowing NaN and +inf into log references. | Done; `779e473` | `test_stress_numerical_validity.py`: 2 failed/3 passed before. |
| F09 | Derived caches / medium | Old strain/day and frozen page namespaces could serve results computed before corrections. | Done; `5c86881`, later issue-specific namespace updates | `test_audit_cache_versions.py`: old RHR=1000 result and old composite score cannot bypass recalculation. |
| F10 | Legacy numerics / medium | `log_hrv_stats` accepted +inf; invalid current HRV then fell through to scalar ratios and could produce 100. Invalid RHR also reached its component. | Done; `f823fed`, `29c7ffb` | `test_legacy_finite_hrv.py`: 6 helper failures and 4 current-vital fallback failures before. |
| F11 | Connected VO2 cache / medium | `health_read_store.read_range` regex omitted digits, rejecting `daily_vo2_max.date`; stored-only reads returned empty despite indexed observations. | Done; `47e5cc6` | `test_vo2_cache_ranges.py`: parser and real temporary-store round trip, both failed before. |
| F12 | Composite sleep missingness / high | `_compute_real_sleep` ignored the adapter's `sleep_duration_available` flag. | Done, reuse existing validity gate; `fe383ac` | `test_sleep_summary_validity.py`: pending, absent, NaN and impossible duration all failed before. |
| F13 | Stress session selection / medium | Adapter lost the distinction between explicitly main and unspecified sessions; a longer unspecified session could displace an explicitly main sleep. | Done, explicit designation first, then physical length/ID; `8dd6b01` | Added explicit-main-priority test failed before; matches stage store/HR selector priority. |

Current derived versions are `strain-v2`, `page-v8`, and `sleep-stress-5`. Old observations are retained; derived results use new namespaces. No confidence or strain coefficient was retuned.

### Why stress duplicates can reach the builder

`/api/sleep/stress` → `compute_connected_sleep_stress` → `GoogleHealthClient.get_sleep_stress_points` → `get_sleep_stage_points(reconcile=False)` → adapt/prepare each raw sleep → `score_night` → `build_baseline` → storage upsert.

Raw repeated records and multiple sessions on one wake date are prepared before persistence enforces ID uniqueness. Therefore storage keys cannot protect the earlier baseline calculation. The corrected builder excludes current/future dates, naps and non-main sessions; deduplicates IDs; chooses one eligible main session per wake date; and counts unique dates toward the unchanged seven-night threshold within 14 calendar dates. Explicit main designation has priority, followed by longest physical session and ID tie-break. Unspecified sessions can be fallback candidates.

## Approved numerical decisions

### Sleep duration

For positive total sleep and need, ratio `r = (night + nap) / need`. Below/equal to need:

`duration = 100 × (1 + exp(−2)) / (1 + exp(−8 × (r − 0.75)))`.

The plateau through 1.1 and existing oversleep penalty `max(30, 100 − 75 × (r − 1.1))` are unchanged. Duration contributes 27% to composite score. The displayed duration component now uses the same helper and includes naps, matching the total score.

| Ratio | Previous duration component | Approved component |
|---:|---:|---:|
| 0.60 | 23.15 | 26.28 |
| 0.75 | 50.00 | 56.77 |
| 0.90 | 76.85 | 87.25 |
| 1.00 | 88.08 | 100.00 |
| 1.10 | 100.00 | 100.00 |
| 1.30 | 85.00 | 85.00 |

The reference 7.5-hour example previously jumped from about 81.48 to 84.70 for an extra 0.000001 hour. It now remains about 84.70 on both sides. Continuity is verified at 1.0 and 1.1; slope changes are retained. The fine curve has **8,001 points** from 0.5 to 1.3 in increments of 0.0001: [CSV](sleep-duration-curve.csv), [plot](sleep-duration-curve.png), [SVG](sleep-duration-curve.svg), [boundary totals](sleep-boundaries.json).

### Recovery weighting

Scoring baseline stays D−67…D−8. Recent signal is now D−7…D−1, with today used only in its 30% term. Missing today uses the prior recent mean alone. Minimum counts remain 21 baseline and four recent; high/medium thresholds remain unchanged. Today can no longer fill one of the four required prior nights. Six prior nights still satisfy the six-night part of high confidence.

For reference HRV 40 ms and log spread 0.05:

| Scenario | Inclusive-today HRV z | Approved prior-only HRV z |
|---|---:|---:|
| Today equals reference/recent mean | ~0 | ~0 |
| Today 20% higher, prior seven flat | 1.458572 | 1.093929 |
| Today 20% lower, prior seven flat | −1.785148 | −1.338861 |
| Today doubled | 5.545177 | 4.158883 |
| One prior day doubled, today normal | 1.386294 | 1.386294 |

These are **HRV component z values before** RHR combination, sleep adjustment and final clipping. Tiny neutral residuals around 1e−14 are floating-point cancellation, not a physiological effect. Full inputs/results: [recovery-weighting.json](recovery-weighting.json).

### Validity gates

Health's HRV, deep-sleep HRV, respiration, absolute wrist temperature and VO2 values must be finite and positive. RHR/non-REM HR additionally use existing 30–230 bpm limits. SpO2 must be positive and <=100%. No new clinical ceilings were invented. Finite values such as 1e9 can still pass the unbounded metrics; tests deliberately demonstrate this remaining limitation.

Strain parses RHR numeric strings, accepts existing HR limits only and requires RHR strictly below estimated HRmax when age is known. It uses the median of the last seven valid supplied readings; with none, 60 bpm. Any rejection marks calibrating and appears in `params.rhr_rejected_count`. The original HR160/RHR1000 probe's zero load now becomes a positive load using the flagged default; exact values are preserved in the before/after finding snapshots.

## Formulas, inputs and components checked

Full generated inputs, expected values, actual values and tolerances: [final simulation JSON](final/simulation-results.json) and [CSV](final/simulation-results.csv). The generated formula report is [here](final/VALIDATION_REPORT.md).

| Quantity | Required inputs / computation |
|---|---|
| Cardio strain | Timestamped HR, physical day window, age, prior RHR, selected coefficient set, optional workout intervals. HRmax=208−0.7×age; pair-average HRR clamped 0…1.1; contributions below HRR .20 excluded. Load=`minutes × HRR × a × exp(b×HRR)`; male (.64,1.92), female (.86,1.67). Strain=`21×(1−exp(−load/90))`, capped below 21 internally. |
| Strain preprocessing/context | Sort physical UTC instants; deduplicate identical timestamps (first value); HR30…230; centered five-sample median spike limit35 bpm; gap<=300 s; coverage=counted/window minutes. Sleep-defined day windows require >=3h main sleep, with midnight fallback. Workout/incidental partition is checked for conservation; unlogged effort >=45% HRR for >=10min is suggested without double-counting. |
| Recovery | Daily dated RMSSD and same-method RHR, 60-date robust reference, prior recent HRV, current vitals, observed main-sleep minutes and preceding night's reconstructed need. Log-HRV median/MAD×1.4826 with .05 floor; inverse RHR z with 1 bpm floor. Combine HRV/RHR .6/.4, or HRV alone. |
| Recovery adjustments/output | Sleep<180min discarded; performance=min(sleep/need,1); adjustment=`−.5×clamp((.85−performance)/.25,0,1)`. Final z clipped ±3; respiratory/temperature anomaly cap −.5. Strict zones outside ±.5; normal-CDF percent withheld at low confidence. Confidence labels express availability, not prediction accuracy. |
| Sleep need | Minutes: baseline450 + normalized strain logistic (max26, slope .476, midpoint14.38, <1min cutoff) + .34×weighted debt − naps, bounded360…660. Prior debt weights1/.85/.7/.55/.4/.25/.1; incomplete pairs omitted, surplus offsets deficit, debt cap240. Need is a weighted mean debt, not cumulative missed sleep. |
| Sleep score | Seconds in `SleepData`, hours for need. Weights: duration27%, stage20%, efficiency10%, HRV5%, sleeping HR5%, HR dip18%, restfulness15%. Stage shares compare with required sleep: deep20% through age30, decrease .2 percentage points/year, floor10%; REM20%, core50%; mix40/40/20. |
| Other sleep components | Efficiency maps70…95% to0…100. HRV baseline ratio .7…1.3, inverted sleeping-HR ratio, dip0…25%. Restfulness=`clamp(100×exp(−.035×awake minutes)−min(15,2.5×interruptions),0,100)`. Missing HR-derived signals default to50; connected summaries currently lack several of those signals. |
| Efficiency/consistency | Standalone efficiency requires finite0<asleep<=period<=24h. Trend aggregate pools durations. Four-night consistency uses circular onset/wake drift, weights .4/.3/.2/.1, normalized sigmoid centered75min with slope .05 and cutoff240min; minimum two prior nights. Seven-night variability is a separate circular clock SD requiring consecutive dates. |
| Stage ranges | Processed, contiguous, nonoverlapping stage segments; >=3 asleep hours; naps excluded. Default denominator full physical sleep period. Prior up to7 unique wake dates, minimum4. Duration-pooled stage center; spread=max(1.4826×daily-percentage MAD,1 percentage point); bands clipped0…100. Restorative=deep+REM is not an extra partition category. |
| Sleep stress | Intraday HRV windows and HR aligned to physical UTC, verified start/end anchor; >=70% stage majority, no awakening overlap, HR35…130, >=60% inferred HR coverage. >=7 eligible prior dates within14; >=50% night coverage. Per-stage reference at30 windows else pooled; log/HR spread floors .02/.5. Joint HRV-drop and HR-rise z>=1, two exactly adjacent windows; stress%=episode minutes/valid minutes. |
| Health trends | Eight metric series; prior14-calendar-day median after7 valid readings; all current/reference/period averages use gates. Intraday chart uses15-minute medians, with latest raw reading separate. |
| Legacy | Recovery40%HRV+25%RHR+25%composite sleep+10%strain recovery; HRV EWMA log mean alpha.25 and sample SD, `50+25×z`; scalar fallback .5…1.5 ratio; RHR ±10bpm; optional ACR penalty0…10 above1.3. Other prototype debt, latency, bedtime and Ayurvedic clock helpers were spot-checked. |

These are application equations. This audit does not establish the empirical basis of age estimates, stage targets, coefficient sets, thresholds or training recommendations.

## Properties, calendar cases and missingness

[Property tests](../../backend/test_analytics_properties.py) use Hypothesis with deterministic generation, 200 examples per generated property and no timing deadline. The ten generated properties cover constant-HR strain monotonicity, observed-duration monotonicity, internal strain bounds, duration below the oversleep penalty, sleep component directions/total bounds, Recovery percent/HRV-z direction, need bounds, stage partition/efficiency and input-order invariance for unique observations. Examples are generated cases, not independent participants or classifier accuracy trials.

Unrestricted monotonicity would be false: oversleep intentionally reduces duration score above1.1; arbitrary HR increases can trigger spike removal. Raw conflicting duplicate HR timestamps use first-value selection; conflicting daily dates use last-value selection. Permutation invariance is asserted for unique/identical observations, not conflicting revisions without a revision-selection contract. Public strain serialization can round an internal value below21 to displayed21.0; the strict upper bound is an internal numerical guarantee, not a one-decimal display guarantee.

[Timezone/missingness tests](../../backend/test_audit_timezones_missingness.py) check:

- Berlin repeated hour, 25 October 2026: 02:58+02 to02:02+01 is **four physical minutes**, not a negative interval.
- Berlin skipped hour, 29 March 2026: 01:58+01 to03:02+02 is also **four physical minutes**.
- Full transition nights retain physical durations9h and7h; crossing UTC/local midnight assigns the device-offset wake date.
- Device wake date and user activity timezone can differ. Daily summaries remain device-local; strain windows use `X-User-Timezone`. Clock consistency intentionally measures wall-clock timing rather than physical exposure duration.
- Missing current HRV uses prior recent signal; <21 baseline or <4 prior recent readings withhold scores; missing middle dates are not imputed. Large HR holes are excluded from counted exposure, with low-coverage flags.
- Nap-only days do not establish a main-sleep strain window. A device that stops syncing does not forward-fill HRV; after the recent window empties, Recovery withholds its result.
- Zero denominators and nonfinite readings are checked; flat/MAD-zero references use the configured floors. Existing zone tests classify before output rounding, including exact/near±.5 boundaries. Fine sleep-curve evidence covers ratio1.0/1.1 and one-sided perturbations.

## Demo, adversarial and legacy results

[Demo replay](demo-replay.json) records each of 19 routes' status, top-level schema, complete synthetic payload, and null-field paths. It additionally checks W/M/6M serialization, rejected invalid date/age/timezone headers, selected-date alignment, exact dashboard/detail equality and exact estimated Recovery/current analytics equality. HTTP async sends and synchronous external transport are blocked. Auth/OAuth callbacks, sync mutation endpoints and webhooks are not demo analytics endpoints and were not called as live operations; existing mocked tests cover their contracts.

[Seven adversarial profiles](adversarial-profiles.json) pass through real Google-shaped normalization, need, composite sleep and connected Recovery computation, replacing network only. Each also runs all five correction probes. Twelve existing connected demo scenarios cover normal/above/below, sparse/reference/low-confidence states, absent RHR/current HRV/sleep, RHR method changes, short sleep and illness flag; see [scenario results](connected-demo-scenarios.json).

| Synthetic profile | Recovery % | z | Sleep score | Prior-night need min | Controlled strain: HR160,45min | Timing variability min |
|---|---:|---:|---:|---:|---:|---:|
| Fit: usual RHR45, HRV90 | 50 | −.01 | 69.1 | 432.28 | 14.8436 | 9.6 |
| Older: age70 | 50 | −.01 | 69.1 | 438.62 | 18.7750 | 9.6 |
| Sedentary: usual RHR72, HRV35 | 50 | −.01 | 69.1 | 428.00 | 13.7546 | 9.6 |
| Sleep-deprived week:270min | 31 | −.51 | 30.5 | 492.39 | 14.4975 | 9.6 |
| Illness-like week:HRV down/RHR up/temp up | 0 | −3.00 | 69.1 | 429.95 | 14.4975 | 9.6 |
| New user:5 daily-history dates | withheld | withheld | 69.1 | 430.48 | 14.4975 | 9.6 |
| Irregular schedule | 50 | −.01 | 69.1 | 430.56 | 14.4975 | 118.9 |

Inference is deliberately limited. Sleep deprivation increases need/debt and decreases the duration contribution; illness-like changes lower the baseline-relative estimate and trigger its flag; irregular timing increases timing variability. Normal personal-reference profiles all round to50 because each is compared with its own reference. Absolute HRV90 does not itself imply higher recovery than HRV35. At identical absolute exercise HR, the current age/RHR formula determines strain; these controlled inputs do not establish actual fitness, sex effects or physiological workload accuracy. The round percentages are expected from controlled references/CDF rounding, not a measured accuracy result.

The new-user fixture truncates daily vital history to five dates while retaining synthetic sleep/activity fixtures to isolate Recovery-reference missingness; it is not a claim of a complete five-day onboarding dataset. Both old and new Recovery calculations are compared on identical current inputs in [legacy-vs-connected.json](legacy-vs-connected.json). They diverge by design: reference estimator/window, scalar fallback, composite sleep vs duration penalty, strain component and confidence withholding differ.

API mode matters: disconnected `/api/recovery` defaults to legacy; `demo=estimate` and default Recovery analytics use the connected estimator on synthetic fixtures. Disconnected dashboard still uses legacy. Connected requests use device-based Recovery. Connected composite sleep uses provider summaries while descriptive stage/sleep analytics use segments; demo pages also retain distinct synthetic fixture families. Therefore cross-page equality of every underlying sleep/HRV reading is **not** established: dashboard/detail equality is verified, but summary-vs-segment and legacy-vs-estimate differences remain explicit. Summary main-session selection uses reported asleep duration; segment selectors use physical length after explicit-main priority, which can differ when multiple main sessions exist.

## Complete before/after accounting

[simulation-deltas.json](simulation-deltas.json) preserves **every changed JSON leaf**, with before, after, case and explanation. **1,189 of1,295 cases are completely unchanged**. The only changed formula cases are105 sleep-score cases affected by approved sigmoid normalization and one date-join case: D−7's outlier now correctly enters the approved prior window, changing final z0→3. Primitive random inputs and seed are retained; sleep rows also contain the corresponding changed duration-component reference values.

The original oracle was run against corrected code before its approved-spec updates: **106 mismatches** were recorded in [previous-spec-on-fixed-code.json](previous-spec-on-fixed-code.json). Updating the independently expressed duration equation and the explicitly approved D−7 inclusion is a specification change, not altering a test to hide a defect.

There are581 changed leaves:315 duration-reference/result leaves, two join leaves,201 demo alignment/duration leaves,32 estimated Recovery leaves, three RHR diagnostic additions, seven stress algorithm-version leaves and21 finding-data/text leaves. No other formula family changed. Every delta is retained even when it is metadata or explanatory text.

| Demo response | Changed leaves | Explanation |
|---|---:|---|
| Dashboard | 56 | Server-date fixture replaced by selected date/profile; strain/sleep fields and downstream legacy sleep/strain components align. |
| Health / HR detail | 62 /2 | Selected calendar day, ranges, dated fixture points/latest timestamp and resulting summaries align. |
| Estimated Recovery analytics / detail | 22 /5 | Prior-only recent count/components, rounded z/percent and historical aggregates reflect approved weighting. |
| Legacy Recovery detail | 5 | Selected-date sleep/strain inputs change score, components, status and recommendation. |
| Sleep detail / analytics / need | 26 /8 /3 | Selected-night fixture, continuous duration component, dependent sleep/debt/need values and current strain input. |
| Sleep consistency | 45 | Selected-date seeded records and their derived timing summary. |
| Sleep stress | 7 | Algorithm-version metadata; these ordinary synthetic scores are numerically unchanged. |
| Strain detail / analytics | 1 /1 | Added RHR rejection diagnostic; valid fixture strain unchanged. |

Additional invalid-data reproductions outside the original case set are documented by their dedicated tests: pending summary score49.1, missing summary0, NaN/impossible summary33.4 all become withheld; invalid legacy current HRV components previously0 or100 now use the existing missing fallback50; nonfinite stress windows and contaminated legacy statistics are excluded. Explicit-main stress priority prevents an unspecified long session from moving the test reference HR median60→75. VO2 temporary-store reads formerly returned an empty collection and now return the stored observation. These cases are not physiological outcome samples.

## Live access, remaining decisions and risks

OAuth client configuration exists, but **no accessible `GOOGLE_HEALTH_ACCESS_TOKEN` or server-side session token was available**. Session tokens are signed browser cookies. Cached SQLite files exist, but were not exported or labeled fresh live data. No real-device readings were pulled, and no provider comparisons or live confidence counts were fabricated.

[live_readonly.py](live_readonly.py) is ready for later execution; [exact scopes and setup](LIVE_README.md) are documented. It needs a valid bearer environment variable and actual age/sex/timezone. It scores30–60 days with67 extra daily reference dates, bounds intraday memory to weekly chunks, reuses production adapters/calculators without stores, permits only observation GET requests, and saves aggregates/field names/boolean timezone checks. Tokens, raw timestamps, IDs and daily personal readings are not saved. Its full fixture execution, missing-token behavior, GET allowance and write/resource guards passed seven offline tests. An HRV start/end anchor must be independently calibrated before live stress scoring.

Your sleep normalization, prior-only Recovery window and existing/unit validity gates have been implemented. No further decision blocks these fixes. Remaining product/validation decisions are:

1. **Metric ceilings:** retain current positivity/unit gates until agreed limits exist (implemented); alternatively specify metric/device-specific validated quality ceilings. Recommendation: establish units and empirical distributions before adding hardcoded clinical bounds.
2. **Conflicting revisions/multiple main sleeps:** keep reconciled provider selection and current layer-specific rules; alternatively adopt one documented latest-revision/main-selection contract across all layers. Recommendation: verify real correction timestamps and summary/segment semantics before changing selection.
3. **Physiological heuristics:** preserve current coefficients while collecting validation evidence; alternatively retune after a defined outcome/holdout study. Recommendation: use timestamped real-device data, calibrated HRV windows, independent outcomes, participant/day holdouts and device/subgroup analyses.

[Numeric constant inventory](numeric-constants.json) includes every numeric literal in the listed calculation/API/adaptation modules, with source line/context and inline comments. [Inventory guide](constants-inventory.md) distinguishes dimensional/control review from empirical validation. Comments describe intent, not evidence. Strain scale90, HRR thresholds, sex coefficients, age HRmax, workout inference, recovery bands/weights/CDF/confidence, illness thresholds, need/debt coefficients, sleep stage targets/component mappings, consistency cutoffs, stress thresholds/coverage/persistence and stage-reference choices all need appropriate validation. Mathematical scales, unit conversions and cache/calendar limits are conservatively inventoried too; they are not all clinical tuning parameters. No literature-based physiological validation was substituted for missing outcome data.

The legacy prototype is separate from connected Recovery; its training advice and Ayurvedic points remain unvalidated heuristics. Connected Recovery's RHR validity currently requires finite positivity and a comparable method; it does not apply Health's displayed 30–230 gate or strain's age-dependent HRmax gate. Agreeing one cross-layer quality contract remains a product decision. Connected composite sleep also lacks current daily HRV/RHR-derived component joins, so illness-like daily vital changes do not alter its neutral missing-component defaults; the profile table makes that limitation visible. Synthetic fixtures cannot establish sensor bias, medication/arrhythmia effects, motion artifacts, cross-device drift, real provider reconciliation, live permissions or production timing semantics. Historical sleep need/performance can remain unavailable. The frontend/browser experience was not built or audited in this backend task.

## Reproduce

```powershell
.venv/Scripts/python.exe -m pip install -r validation/followup/requirements.txt
.venv/Scripts/python.exe validation/followup/regress.py
.venv/Scripts/python.exe validation/followup/run_audit.py
.venv/Scripts/python.exe validation/followup/evidence.py
.venv/Scripts/python.exe -m pytest validation/followup/test_live_script.py -q -p no:cacheprovider
```

The final suite took63.94 seconds (64.97 subprocess wall seconds); simulations took5.24 seconds; the final live-runner fixture/guard checks took1.23 seconds. [Suite log](final/tests.log), [JUnit](final/test-results.xml), [live-script JUnit](live-script-tests.xml), [test metadata](final/test-metadata.json) and [simulation metadata](final-simulation-metadata.json) provide the execution evidence. On this host, sandboxed async thread/TestClient operations stalled; those checks ran outside the sandbox under tool approval. No failure was suppressed to declare success.
