# Backend hardening report

2026-10-09 · branch `fix/backend-hardening` · synthetic anchor 2026-10-07 · formula seed 20261007 · option seed 20261009.

The tested backend paths pass: **704 JUnit cases**, no failures, errors, skipped tests or warnings; **1,295/1,295 independent formula checks**, all unchanged from the audit baseline; **14,300 passing generated examples in 71 property batches**, at least 200 each. Nineteen demo routes and nine synthetic profiles were replayed offline. This is implementation verification, not clinical validation.

No read-only access token was available (yes/no check: **no**). Live Phase 5 was not run. No device measurements were invented or substituted for live data.

## Module verdicts

| Module | Verdict on tested domains |
|---|---|
| `strain.py` / strain service | HRR/TRIMP, gaps, conservation and monotonic bounds pass; finite RHR/age gates and JSON flooring verified. |
| Connected `recovery_score.py` | Prior-only joins, valid-reading counts, robust spreads, method gates, confidence and bounded CDF pass. |
| `sleep_need.py` / inputs | Minute units, seven-night weighted debt, nap subtraction and 360–660 minute limits pass. |
| `sleepscore.py` | Component equations and bounds pass; connected missing inputs remain neutral with explicit weighted availability. |
| `sleep_efficiency.py` | Valid physical durations and pooled aggregation pass; missing/invalid durations remain absent. |
| `sleep_consistency.py` / trends | Circular timing, consecutive dates, calendar boundaries and DST/offset checks pass. |
| Stage ranges / selection / store | Shared UTC main selection, complete partitions, <=24 h eligibility, prior unique dates and scoped persistence pass. |
| Sleep stress / pipeline / store | Joint persistent signals, valid coverage, unique nights, account isolation and withholding reasons pass; real anchor calibration remains unverified. |
| Health / Recovery analytics | Shared metric gates and finite robust medians pass; overflowing personal ranges are explicitly withheld. |
| Legacy `recovery.py` / clock helpers | Prototype equations and scalar validation pass; estimator is disclosed and retained as the demo default. |
| Provider / API assembly | Malformed types, repeated page tokens, profile headers, date bounds, missing data and privacy-safe errors pass. |
| Auth / webhooks | Anonymous demos remain; invalid/expired cookies reject with 401; malformed OAuth responses and authenticated webhook payloads fail closed. |
| Cache / sync / SQLite | Account/profile keys, version bypass, transaction/upsert idempotence and existing concurrency tests pass. |

## Reproduced fixes

Locations refer to current source. The commit contains the surgical change and its regression test. The machine-readable [findings](final/findings.json) link retained failing output files; all bounded before/after logs and XML remain in this directory. Every row below is reproduced and fixed.

| ID | Source / callable / line | Severity | Root cause and correction | Regression | Commit |
|---|---|---|---|---|---|
| H01 | `backend/validity.py:31` `resting_hr` | medium | unify inconsistent vital gates and flag Recovery rejections | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_shared_validity.py](../../backend/test_shared_validity.py) | `79f5eb3` |
| H02 | `backend/main.py:362` `_compute_real_sleep` | medium | disclose defaulted connected sleep components without retuning | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_score_transparency.py](../../backend/test_score_transparency.py) | `32ee23d` |
| H03 | `backend/validity.py:44` `valid_metric` | medium | enforce provider sample HRV and daily VO2 ceilings | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_health_validity.py](../../backend/test_health_validity.py), [test_provider_validity.py](../../backend/test_provider_validity.py) | `c968fce` |
| H04 | `backend/sleep_selection.py:10` `main_sleep_key` | medium | replace inconsistent main-sleep rankings with UTC duration and ID | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_main_selection_inventory.py](../../backend/test_main_selection_inventory.py) | `623fc73` |
| H05 | `backend/models.py:99` `RecoveryResponse` | low | unnamed score estimators: expose actual algorithm identity and invalidate page-v12 | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_estimator_identity.py](../../backend/test_estimator_identity.py) | `a47cfcb` |
| H06 | `backend/models.py:58` `StrainResponse` | low | rounded strain JSON reaching 21: floor raw values only in JSON and invalidate page-v13 | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_cardio_strain.py](../../backend/test_cardio_strain.py), [test_strain_serialization.py](../../backend/test_strain_serialization.py) | `b578a51` |
| H07 | `backend/sleep_stress_pipeline.py:12` `compute_connected_sleep_stress` | medium | opaque sleep-stress nulls: expose withholding reasons and operator anchor provenance | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_stress_withheld_reasons.py](../../backend/test_stress_withheld_reasons.py) | `d37a4ad` |
| H08 | `backend/sleep_analytics.py:110` `build_sleep_analytics` | medium | caller mutation in sleep analytics: copy observations before derived fields | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_sleep_analytics_inputs.py](../../backend/test_sleep_analytics_inputs.py) | `341979e` |
| H09 | `backend/sleep_stage_ranges.py:104` `stage_stats` | medium | session identifier disclosure in stage warnings: log rejection reason only | [test_private_stage_logging.py](../../backend/test_private_stage_logging.py) | `b30f21e` |
| H10 | `backend/main.py:120` `data_timings` | medium | inconsistent profile header validation and timezone ValueError crashes: reject before data access | [test_request_header_validation.py](../../backend/test_request_header_validation.py) | `656ed78` |
| H11 | `backend/main.py:206` `_client_day` | medium | server-local fallback day: derive missing client date in request timezone and invalidate snapshots | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_request_day_fallback.py](../../backend/test_request_day_fallback.py) | `0959afe` |
| H12 | `backend/google_health_client.py:62` `_valid_sleep_summary` | medium | invalid sleep summaries producing scores or crashes: validate finite nonnegative day-bounded inputs | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_sleep_summary_hardening.py](../../backend/test_sleep_summary_hardening.py) | `f3696c3` |
| H13 | `backend/google_health_client.py:477` `_sleep_records` | medium | DST sessions lost by wall-clock and text ordering: compare physical timestamps and retain offsets | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_sleep_dst_elapsed.py](../../backend/test_sleep_dst_elapsed.py) | `3d8157f` |
| H14 | `backend/main.py:258` `_cached_data_page` | high | explicit demo touching connected token/cache paths: bypass account wrapper for demo | [test_explicit_demo_isolation.py](../../backend/test_explicit_demo_isolation.py) | `269d5c2` |
| H15 | `backend/main.py:186` `_get_token` | high | expired and invalid sessions silently yielding demos or crashing: reject centrally with 401 | [test_expired_session_consistency.py](../../backend/test_expired_session_consistency.py) | `462437e` |
| H16 | `backend/validity.py:18` `finite_number` | medium | comparison-only validation accepting NaN or overflowing integers: enforce finite inputs and stable saturation | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_numeric_missingness_hardening.py](../../backend/test_numeric_missingness_hardening.py) | `bf33b64` |
| H17 | `backend/provider_payload.py:10` `payload_boundary` | high | malformed provider parsing causing 500s: expose privacy-safe 502 payload errors | [test_provider_error_boundaries.py](../../backend/test_provider_error_boundaries.py) | `2bd38e3` |
| H18 | `backend/provider_payload.py:10` `payload_boundary` | high | raw adapter type errors under malformed payloads: preserve explicit validation errors | [test_adapter_fuzz.py](../../backend/test_adapter_fuzz.py) | `626641d` |
| H19 | `backend/sleep_stress.py:215` `prepare_night` | medium | invalid stress stage partitions: withhold before baseline entry | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_stress_partition_hardening.py](../../backend/test_stress_partition_hardening.py) | `70ede57` |
| H20 | `backend/google_health_client.py:263` `get_daily_hrv` | high | malformed daily provider adapters: validate scalar values and physical clocks | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_daily_adapter_fuzz.py](../../backend/test_daily_adapter_fuzz.py) | `b873319` |
| H21 | `strain.py:102` `strain_score` | medium | scalar type errors in public calculators: validate finite numbers before arithmetic | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_public_calculator_fuzz.py](../../backend/test_public_calculator_fuzz.py) | `eb7f98e` |
| H22 | `backend/sleep_stress_store.py:26` `_key` | high | cross-account stress record collisions: namespace stored keys by account | [test_stress_account_isolation.py](../../backend/test_stress_account_isolation.py) | `925213f` |
| H23 | `backend/sleep_heart_rate.py:40` `build_sleep_heart_rate` | high | malformed sleep HR chart parser crashes: explicit provider boundary | [test_sleep_chart_fuzz.py](../../backend/test_sleep_chart_fuzz.py) | `7225925` |
| H24 | `backend/sleep_stage_ranges.py:104` `stage_stats` | medium | overlong stage nights: reject partitions beyond one day | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_stage_day_limit.py](../../backend/test_stage_day_limit.py) | `af85696` |
| H25 | `sleepscore.py:206` `compute_duration_score` | medium | overflow in custom sleep duration sigmoid: stable log-space fallback | [test_sigmoid_overflow.py](../../backend/test_sigmoid_overflow.py) | `45f57d0` |
| H26 | `backend/recovery_analytics.py:17` `typical_ranges` | medium | infinite personal Recovery ranges: withhold and expose overflow reasons | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_range_overflow.py](../../backend/test_range_overflow.py) | `97833bd` |
| H27 | `sleepscore.py:67` `compute_baseline` | medium | unvalidated sleep helper scalars: finite means, counts and latency gates | [test_public_helper_fuzz.py](../../backend/test_public_helper_fuzz.py) | `489fd3d` |
| H28 | `backend/validity.py:6` `finite_median` | medium | overflowing even medians on finite vitals: stable midpoint fallback | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_unbounded_median.py](../../backend/test_unbounded_median.py) | `9909e5f` |
| H29 | `backend/google_health_client.py:320` `get_health_history` | medium | boolean vitals coerced to valid numbers: preserve rejected-reading diagnostics | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_provider_boolean.py](../../backend/test_provider_boolean.py) | `b5d96aa` |
| H30 | `backend/auth.py:138` `get_valid_access_token` | high | malformed auth tokens and OAuth responses: fail closed with validated payloads | [test_auth_payload_fuzz.py](../../backend/test_auth_payload_fuzz.py) | `0f410b5` |
| H31 | `backend/google_health_client.py:203` `_fetch_points` | high | unchecked provider pages: validate parser types and pagination progress | [test_provider_transport_fuzz.py](../../backend/test_provider_transport_fuzz.py) | `2125b38` |
| H32 | `backend/main.py:155` `unrepresentable_range` | high | date arithmetic overflow at API boundaries: clear client range errors | [test_extreme_request_dates.py](../../backend/test_extreme_request_dates.py) | `08e988a` |
| H33 | `backend/sleep_trends.py:38` `build_sleep_trend` | high | arithmetic on missing sleep durations: withhold trend values | [test_adapter_fuzz.py](../../backend/test_adapter_fuzz.py), [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_sleep_trend_missing_duration.py](../../backend/test_sleep_trend_missing_duration.py), [test_structured_calculator_fuzz.py](../../backend/test_structured_calculator_fuzz.py) | `2f05440` |
| H34 | `backend/google_health_client.py:430` `_fetch_daily_steps` | high | silently coerced step counts and stale rollups: reject invalid counts | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_provider_step_counts.py](../../backend/test_provider_step_counts.py) | `206f2dd` |
| H35 | `backend/sleep_stage_webhooks.py:53` `enqueue_sleep_notifications` | high | webhook interval parser crashes: explicit invalid-payload rejection | [test_webhook_payload_fuzz.py](../../backend/test_webhook_payload_fuzz.py) | `b1e11d0` |
| H36 | `backend/strain_analytics.py:59` `build_strain_analytics` | low | historical strain rows bypassing JSON flooring: preserve aggregate inputs | [test_audit_cache_versions.py](../../backend/test_audit_cache_versions.py), [test_strain_analytics.py](../../backend/test_strain_analytics.py), [test_strain_history_serialization.py](../../backend/test_strain_history_serialization.py) | `4688814` |

## Decisions and retained policies

No decision is waiting. [The decision record](DECISIONS.md) retains options, numerical effects and the accepted contracts.

- Composite sleep: keep defaults, expose partial/availability. Missing HRV, sleeping HR and HR dip have 28% total weight and add 14 neutral points. Normal connected fixtures have 72% weighted availability; the illness fixture remains 69.1 sleep despite its abnormal vitals.
- Main sleep: explicit main, otherwise unspecified, longest physical UTC duration, greatest stable ID. The reproduced A/B example now selects 400 asleep minutes in a 9 h session over 450 asleep minutes in an 8 h session. Naps/secondary exclusions and calculator eligibility thresholds remain.
- Ceilings: existing HR 30–230 bpm and unit SpO2 limits, provider RMSSD <=200 ms and daily VO2 <=100. Unsupported daily/deep HRV, respiration and temperature ceilings remain deferred; 1e9 still passes their finite/positive gate.
- Serialization: floor public 0–21 strain fields and historical rows to one decimal; preserve model/calculation values and inputs to averages/Recovery. 16.86 serializes as 16.8 while its model remains 16.9; values just below 21 serialize as 20.9.
- Duplicates: first raw strain HR arrival, last daily vital arrival, sleep HR chart excludes conflicts. This inconsistency is intentionally retained. No common revision timestamp was established for these fields; an eventual shared policy needs provider revision metadata.
- Auth: preserve anonymous demos and explicit strain demos; present invalid/expired cookies return 401. Deliberate invalid pure-helper calls retain ValueError; client header/range errors return 400, malformed upstream data returns privacy-safe 502.

## Before/after counts and accounting

| Check | Preserved baseline | Final |
|---|---|---|
| Backend | 380 passed, 1 failed, 27 subtests; 1 deprecation warning; 80.883 s | See combined count below; all pass |
| Live-runner offline tests | 7 passed; 1.116 s | 7 pass, included in combined suite |
| Combined final suite | Baseline backend and runner were separate | 704 JUnit cases; 123.375 s; 0 failures/errors/skips/warnings |
| Independent formula checks | 1,295/1,295; 6.909 s | 1,295/1,295; all case inputs/expected/actual/tolerance/status unchanged |
| Generated properties | Prior audit had property tests | 71 batches; 14,300 passing examples; generator retries are not test skips |
| Offline replay / profiles | 19 routes; 7 profiles | 19 routes plus W/M/6M replay; 9 profiles; original five and eight hardening probes on each |

The baseline source identity matched all 82 listed hashes with zero drift. [Baseline metadata](baseline/metadata.json), [final suite log](final/tests.log), [XML](final/test-results.xml), [property statistics](fuzz-statistics.log), [source hashes](final/source-hashes.json) and [read-only verification script](../followup/verify_artifacts.py) retain the evidence.

Exactly **122 response leaves** changed against both the preserved audit and execution baselines. The [complete before/after leaf table](final/audit-deltas.json) assigns a specific cause/commit to each. No numerical formula case changed and no unexplained delta remains.

| Delta cause | Leaves |
|---|---:|
| Shared validity/rejection diagnostics schema (79f5eb3) | 18 |
| Estimator identity schema (a47cfcb) | 15 |
| Approved component availability schema (32ee23d) | 22 |
| Approved JSON-only flooring of the unchanged raw workout strain (b578a51) | 3 |
| Personal-range withholding diagnostics schema (97833bd) | 5 |
| Main selection and overlong-stage cache namespace (623fc73, af85696) | 8 |
| Provider bounds, main selection, reasons and partition cache namespace (c968fce, 623fc73, d37a4ad, 70ede57) | 7 |
| Stress reason/anchor/selection provenance schema (d37a4ad, 623fc73) | 28 |
| Approved JSON-only historical display flooring; aggregate/model inputs unchanged (4688814) | 16 |

The only changed numeric outputs in the original replay are display flooring: three workout copies 9.2→9.1, and historical row/activity displays 13.9→13.8, 6.4→6.3, 3.6→3.5 or 9.2→9.1. Other added numeric leaves are availability/provenance/zero rejection counts, not score retuning. The repeated dashboard/detail/current values agree. Historical averages and comparisons retain their previous model inputs.

Cache namespaces: `strain-v2` retains raw formula values; `page-v30` replaces page-v8 through all intervening versions; `sleep-stress-9`, `sleep-stage-ranges-3` and `steps-rollup-v2` invalidate affected derivations/rollups. [Cache tests](../../backend/test_audit_cache_versions.py) and [step-cache tests](../../backend/test_provider_step_counts.py) prove old keys cannot serve the reproduced bad results. Invalid stored historical step counts are excluded. Previously truncated fractional counts cannot be distinguished from genuine integers without fetching source data again.

## Profile data, results and inference

All inputs are generated, not participant observations. [Full profile inputs/components/reasons/probes](final/adversarial-profiles.json) and [legacy vs connected comparison](final/legacy-vs-connected.json) are retained. The latter compares the original seven profiles.

| Profile | Connected Recovery % | Composite sleep | Need (min) | Controlled 160 bpm / 45 min strain |
|---|---:|---:|---:|---:|
| fit | 50 | 69.100 | 432.279 | 14.844 |
| older | 50 | 69.100 | 438.617 | 18.775 |
| sedentary | 50 | 69.100 | 428.000 | 13.755 |
| sleep_deprived | 31 | 30.500 | 492.394 | 14.497 |
| illness | 0 | 69.100 | 429.946 | 14.497 |
| new_user | withheld | 69.100 | 430.479 | 14.497 |
| irregular_schedule | 50 | 69.100 | 430.565 | 14.497 |
| stopped_sync_10_days | withheld | withheld | withheld | 14.497 |
| remote_timezone | 38 | withheld | withheld | 14.497 |

Sleep deprivation reduces sleep score and applies the Recovery duration penalty; illness-like HRV/RHR changes lower Recovery. The retained composite sleep score does not encode those missing vitals. New users and stopped sync withhold rather than fabricate current estimates. A higher age increases strain for identical HR under the retained HRmax formula; this confirms that formula, not a measured physiological age effect. The controlled strain probe in the stopped-sync row is a separate synthetic experiment, not current activity imputed to that user.

The stopped-sync fixture retains 58 reference HRV days but zero recent nights; Recovery is building_reference, sleep score is absent with sleep_duration_unavailable. The remote-timezone fixture uses device +02:00 and user -08:00: physical instant equality is true, while device wake date 2026-10-07 maps to user date 2026-10-06. Provider civil wake dates select summary sleep and request timezone selects activity days. Its sleep score is withheld with sleep_need_unavailable. This is a calendar/data-availability result, not evidence of physiological deterioration or proof that device/user date labels should be unified.

The 1,000-night options experiment retains all inputs and candidate results in [sleep-component-options.json](sleep-component-options.json). Defaults produce 23.277–84.712, mean 57.717. Removing neutral points gives 9.277–70.712; renormalizing gives 12.885–98.211. The accepted default policy leaves profile scores unchanged. These distributions do not establish which policy is clinically better.

## Formula and source-review detail

[Formulas, numerical examples and inference](final/FORMULAS_AND_RESULTS.md) include HRR/TRIMP, recovery z/CDF, sleep need/debt, seven sleep components, pooled efficiency, circular consistency, stage bands and persistent stress windows. [The duration curve](final/sleep-duration-curve.png) and [boundary values](final/sleep-boundaries.json) show the previously approved normalization. [All 1,295 inputs/expected/actual values](final/simulation-results.json) and [CSV](final/simulation-results.csv) retain tolerances and per-case results. [The callable index](final/algorithm-inventory.md) lists 326 reviewed production/support callables, including nested/new helpers. [The constants inventory](final/constants-inventory.md) includes 1906 numeric literals with source context. [The property matrix](final/fuzz-coverage.json) lists actual counts by entry point. Source review and calculator/adapter chains do not establish exhaustive branch coverage.

Review covered truthiness, finite statistics, units, calendar windows, physical vs wall time, duplicates, mutation, provider types/partitions, account/profile/cache keys, transactions, logging, auth and webhook validation. Existing deterministic tests cover DST transitions in 2026/2027, midnight, leap/calendar boundaries, invalid headers and missing observations. CLI defaults legitimately use today when no request date exists; unused convenience/demo date helpers were not refactored.

## Test infrastructure and evidence corrections

Starlette 0.38.6 imported the deprecated BlockingPortal alias exposed by AnyIO 4.15.1. Pinning AnyIO 4.14.2 removed the warning; import and suite checks use warnings as errors. The fresh environment was installed from downloaded wheels with --no-index. External socket destinations and both real httpx transports are blocked. Loopback is allowed only because Windows asyncio uses a socket pair for IPC.

Sandboxed async runs were bounded failures in Windows socket-pair initialization, not evidence of a backend deadlock. Their timeout logs remain retained. Tests default to 30 seconds; one measured 15-route/6-month replay has a scoped 120-second limit; whole-suite capture has a 300-second limit. Final unrestricted-IPC runs still block external network. No warning filter hides deprecations; expected blocked-socket UserWarning is asserted.

The baseline failure was a fixed October fixture evaluated against a moving recent-refresh clock. Its test clock was frozen; cache behavior was not patched to satisfy it. An existing sleep-analytics fixture gained the approved availability fields. The historical API assertion was changed to compare JSON output under the approved display spec, while dedicated tests preserve its model/average expectations. A new generic-mean property incorrectly prohibited signed means; its oracle was corrected to the documented generic mean contract. Evidence-script collection/import and stress-call signature mistakes were corrected; no production result was claimed from those failed scripts. Initial new route probes also contained obsolete route spellings; those probes were corrected to existing route definitions, rather than adding routes to satisfy the tests. The candidate join table initially used 45 ms instead of connected 41.2 ms; corrected values are disclosed in the decision record. Original independent numerical oracles were not retuned to pass.

The verifier formerly rewrote script hashes before checking them. It now performs read-only comparisons; hash regeneration is an explicit artifact-build step. This avoids a self-refreshing identity check without changing product algorithms.

## Limits and heuristics needing validation

Verified on synthetic data: selected equations, documented thresholds, domain invariants, missing-data handling, API assembly, privacy-safe failures, cache isolation and the exercised storage/concurrency paths. Verified on live data: **nothing; access was unavailable**. No clinical sensitivity, specificity, p-values, outcome prediction or real-device permission/schema certification is inferred.

The stress finding reproduced an account collision in persisted records. No API-served cross-account disclosure was demonstrated; that path currently recomputes results. The high severity reflects the incorrect storage isolation contract.

Retained product heuristics needing empirical provenance include HRmax age coefficients, TRIMP sex coefficients/scale, spike and gap rules, target bands/ACR penalty, robust spread floors, reference counts/confidence, illness limits, sleep weights/stage targets/duration curve, need/debt coefficients and bounds, consistency curve, stage bands, stress joint thresholds/persistence/coverage and timestamp anchor choice. Their comments and synthetic tests establish implementation intent, not clinical validity.

Needed evidence: timestamped raw data and independently confirmed HRV window start/end semantics across devices, DST and travel; matched device summaries and segment timelines; representative distributions for unsupported ceilings; independent readiness/sleep/illness outcomes; participant and day holdouts, prespecified missingness/confidence analyses and repeated-device comparisons. Provider output is a reference, not ground truth.

Source-review concerns not claimed as reproduced defects: long-lived lock dictionaries may grow with many account/range keys; no memory-growth experiment established a user-visible failure. Arbitrary caller-supplied configurations and every possible combination of overlapping legacy clock intervals were not exhaustively validated. Stage-summary totals and complete segment partitions remain distinct measurement contracts; this audit does not assert universal equality between them. These were not patched speculatively. No frontend/browser or deployment security audit was requested or performed.

All scoring coefficients and existing clinical/product thresholds remain unchanged in this hardening task. Approved provider/unit validity limits, selection, availability, error contracts and display/cache behavior changed as documented. Nothing was merged, rebased onto main, pushed or deployed; no remote was modified.

## Reproduce

```powershell
.venv/hardening-clean/Scripts/python.exe validation/hardening/regress.py final-suite-complete backend validation/followup/test_live_script.py
.venv/Scripts/python.exe validation/hardening/evidence.py
.venv/Scripts/python.exe validation/hardening/simulations.py
.venv/Scripts/python.exe validation/hardening/build_artifacts.py final-suite-complete
.venv/Scripts/python.exe validation/hardening/report.py
.venv/Scripts/python.exe validation/followup/verify_artifacts.py
```
