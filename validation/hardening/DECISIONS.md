# Hardening decisions — accepted and implemented

All requested decisions have been answered. The implemented contracts are listed first; the original options remain below as the decision record. Seed: 20261009. Full 1,000-night input/output table: [sleep-component-options.json](sleep-component-options.json).

- Keep connected sleep's neutral defaults; expose component availability, defaulted values, weighted coverage and partial status. Do not join daily vitals or renormalize.
- Unify representative main sleep by explicit-main priority, otherwise unspecified, then longest UTC physical duration and greatest stable ID. Preserve calculator eligibility gates and strain's separate activity boundary.
- Apply provider ceilings only: sample RMSSD 200 ms and daily VO2 100 ml/kg/min. Retain existing HR 30–230 bpm and SpO2 0–100 unit limits; defer unsupported daily/deep HRV, respiration and temperature ceilings.
- Preserve deliberate pure-helper validation exceptions; provider/API boundaries reject malformed inputs explicitly.
- Floor strain model fields only in JSON serialization. Preserve raw calculation, Python model values, Recovery contributions and comparisons.
- Preserve duplicate policies: strain first HR arrival, daily vitals last arrival, sleep HR chart excludes conflicting timestamps. No common provider revision field was established.
- Keep anonymous demos and explicitly requested strain demos; reject present invalid or expired session cookies with 401.

The earlier audit's approved duration normalization and prior-only Recovery recent window remain in effect. No scoring coefficients or thresholds were retuned in this hardening task.

## Composite sleep inputs

`GoogleHealthClient._sleep_records` explicitly sets sleeping HRV, sleeping HR and waking HR to None. These are separate data types, not omitted fields within the provider's sleep object. `get_health_history` can fetch daily HRV, deep-sleep HRV and NREM HR; intraday HR can be selected inside/outside sleep. At score time `_compute_real_sleep` fetches only deep HRV for display, after scoring. It does not join these physiological inputs. The seven existing profiles have daily HRV, but no NREM HR or overnight/current-day waking HR observations. RHR is available but is not equivalent to waking HR.

The defaulted 28% contributes exactly 14 points; the remaining observed components contribute 72% of nominal weight. Three components at 50 constrain the theoretical score to 14–86. Baseline global references are retained in the experiments (connected HRV 41.2 ms, sleeping HR 60 bpm); joining relative to personal references is a separate contract, not an assumed improvement. An early candidate table incorrectly used the demo HRV reference 45 ms. The corrected values below and JSON use the connected reference; this correction does not affect the selected defaults policy.

| Option | Illness profile | Sleep-deprived profile | 1,000 random nights range / mean |
|---|---:|---:|---|
| Keep existing defaults; expose availability/partial flag (recommended) | 69.11 | 30.50 | 23.28–84.71 / 57.72 |
| Join the available daily HRV only; other inputs still absent | 67.90 | 31.07 | 21.84–87.21 / 59.08 |
| Renormalize the observed 72% | 76.54 | 22.92 | 12.88–98.21 / 60.72 |
| Withhold below an example 75% coverage threshold | None | None | All 1,000 withheld |

If all three compatible vitals existed, the hypothetical random joined range is 10.34–93.88 (mean 60.68). Those are generated candidate inputs, not verified provider signals. Removing defaults without renormalizing leaves 9.28–70.71 (mean 43.72). Renormalization raises the illness score because the currently observed components do not encode its vital abnormalities. Full seven-profile effects and all inputs are in the JSON. These distributions are not evidence of physiological accuracy. The selected defaults policy leaves these profile scores unchanged.

## Main-session selection

| Location | Priority / ranking | Tie-break and fallback |
|---|---|---|
| `google_health_client._sleep_records` | Explicit main, then greatest reported asleep seconds | First input on ties; unspecified fallback suppressed if any session has a non-null designation, even false |
| `sleep_heart_rate.select_sleep` | Latest eligible wake date; explicit main; greatest UTC physical length | Greatest ID; unspecified eligible alongside secondary false sessions; excludes naps/false/unfinished/future |
| `sleep_analytics.sleep_observations` | Delegates per date to HR selector | Same as above |
| `SleepStageStore.sync` | Explicit main, else unspecified; physical UTC length | Greatest ID; excludes nap/short states; pending main remains selected with withheld result |
| `sleep_stress.build_baseline` | Valid prior explicit main, physical length | Greatest ID; only baseline-eligible nights; one ID/date; excludes naps/secondary/low-coverage |
| `sleep_stress.summarize_nights` | First main result in date group | Incoming order; does not independently rank physical length |
| `strain.day_window` / `strain_service.sleep_windows` | Last eligible wake, then next sleep start for the activity boundary | Not a representative-sleep scoring selector; same-day input-order ties; unspecified eligible; physical >=3 h |
| `sleep_stage_ranges.personal_ranges` | Last end/ID on each prior date | Assumes upstream main selection; last seven dates with data |

Reproduced: A has 9 h physical / 400 min asleep, B has 8 h / 450 min asleep. Summary chooses B (450 min); HR selector and stage/stress ranking choose A (400 min). Summary efficiency would be 93.75% for B versus 74.07% for A using physical denominators. The same ranking disagreement occurs on both 2026/2027 DST dates; separate offset tests will assess physical arithmetic. When one session is explicit false and another unspecified, summary returns None while HR selects the unspecified session. Equal asleep lengths depend on summary input order. Tests: `backend/test_main_selection_inventory.py`.

Implemented contract: exclude naps/explicit false and invalid physical intervals; choose explicit main if any, otherwise unspecified; rank UTC physical length, then greatest stable ID, per provider local wake date. Preserve each calculator's existing eligibility/withholding thresholds. Keep strain's activity-boundary semantics separate. Consequence: A replaces B, unspecified can fill a date with secondary sleeps, ties become deterministic. The table above describes the reproduced pre-fix rules.

## Upper limits

[Google's v4 field specification](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints) explicitly bounds sample RMSSD at 1–200 ms and daily VO2 at 0–100 ml/kg/min. It does not give these same ceilings for daily/deep HRV, daily respiration, or nightly sleep-temperature derivations. Applying the sample RMSSD ceiling to a different daily field would be an unsupported extrapolation.

| Option | Exact new ceilings | Numerical effect / exclusion |
|---|---|---|
| Provider-specific schema bounds only (recommended) | Sample RMSSD 200 ms; daily VO2 100 ml/kg/min | 1e9 becomes rejected for these fields; valid fixtures unchanged. Excludes provider-out-of-contract values; no claim about biology. Other daily metrics remain unbounded pending agreed limits. |
| Conservative app sanity policy, explicitly unvalidated | Daily/deep/sample HRV 2000 ms; respiration 120 breaths/min; nightly temperature 60 C; daily VO2 100 ml/kg/min | 1e9 rejected everywhere. HRV bound follows a maximum 2 s RR interval only if HR >=30; respiration is 2 breaths/s and temperature a gross thermal outlier. These are policy candidates, not proved universal physical impossibility. Real exclusion rates unknown without live data. Sample RMSSD would additionally obey its provider ceiling. |
| Retain finite/positive/unit gates | No new ceilings | 1e9 remains accepted for unbounded metrics; explicitly documented. |

Provider-specific ceilings were selected and implemented. Daily/deep HRV, respiration and temperature retain finite/positive gates; 1e9 therefore remains accepted for those metrics. Broader limits were explicitly deferred and need a device-specific quality contract and representative raw distributions. The proposed alternatives are unvalidated policies, not universal physical bounds.
