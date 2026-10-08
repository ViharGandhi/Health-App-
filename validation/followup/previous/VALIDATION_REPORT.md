# Backend formula and simulation validation report

Audit date: 2026-10-07 (Europe/Berlin). Synthetic anchor: 2026-10-07. Random seed: 20261007.

## Verdict

Existing backend suite: **220 top-level tests plus 27 subtests (247 JUnit cases total), 0 failures, 0 errors, 0 skipped**. Independent simulation checks: **1295/1295 passed**. See findings below: passing formula checks does not mean every implementation assumption is correct.

No production algorithms were changed. This is an offline implementation audit, not clinical validation or a live Fitbit/Google integration certification. The independent oracles use published-in-code constants and separate numerical calculations; they verify those equations, not the validity of their chosen coefficients.

## Reproduce and inspect evidence

Run from the project root:

```powershell
.venv/Scripts/python.exe -m pytest backend -q --junitxml=validation/test-results.xml
.venv/Scripts/python.exe validation/run_simulations.py
```

The XML records every existing test outcome. simulation-results.json and CSV preserve every generated input, expected value, actual value, tolerance and pass/fail result. JSON also includes 28 date-anchored demo daily results. source-hashes.json identifies the exact audited Python sources. algorithm-inventory.md lists backend callables; it is not an assertion that every branch is tested.

All new numerical checks use fixed dates/seeds and are offline. No credentials or live APIs were used. Existing integration tests use mocked Google data/HTTP transports and temporary SQLite databases. Demo endpoints were replayed in-process with outbound async HTTP explicitly forbidden; complete responses are in simulation-results.json. Demo computation timestamps can change between runs; numerical simulation cases are deterministic. No frontend build or browser audit was performed.

Oracle calibration: an initial sweep exposed a mistake in this audit script: its sleep-score reference used a 25% REM target, while source specifies 20%. That independent reference was corrected to the actual source constant; production code was not changed. The initial 110 mismatches are therefore audit-oracle errors, not backend defects. An initial endpoint replay also used an incorrect stage-range URL and received 404; the replay was corrected to /api/sleep/stages/typical-ranges. Final results below come from the corrected rerun.

## Scope and check counts

| Family | Checks | Passed |
|---|---:|---:|
| cardio strain | 313 | 313 |
| cardio integration | 100 | 100 |
| strain analytics | 1 | 1 |
| demo integrity | 1 | 1 |
| connected recovery | 210 | 210 |
| date joins | 1 | 1 |
| sleep need | 202 | 202 |
| sleep score | 203 | 203 |
| sleep efficiency | 106 | 106 |
| sleep consistency | 8 | 8 |
| stage ranges | 101 | 101 |
| sleep stress | 5 | 5 |
| legacy recovery | 8 | 8 |
| legacy sleep helpers | 13 | 13 |
| health trends | 3 | 3 |
| sleep trends | 1 | 1 |
| calendar windows | 2 | 2 |
| demo API replay | 17 | 17 |

## Current formula specification

### Cardio strain — strain.py

The current algorithm supersedes the old weighted-zone/capacity implementation described earlier in chat. HRmax = 208 - 0.7*age. RHR = median of up to seven supplied valid positive readings, fallback 60 bpm. Clean samples by physical UTC time, deduplicate timestamps (first value wins), remove nonfinite/outside 30–230 bpm values, and remove values more than 35 bpm from a centered five-sample median with repeated edge padding. Arrays shorter than five skip the spike filter.

For adjacent cleaned samples with 0 < physical gap <= 300 seconds: minutes = gap/60; HR = pair average; HRR = clamp((HR-RHR)/max(HRmax-RHR,1),0,1.1). Below HRR 0.20 gives zero load; otherwise load = minutes*HRR*a*exp(b*HRR). Coefficients: male a=0.64,b=1.92; female a=0.86,b=1.67. Total strain = 21*(1-exp(-total_load/90)), numerically capped just below 21. Zones are display-only, not load weights.

Coverage = counted interval minutes / physical window minutes, capped at 1; below 60% is low coverage. Missing age withholds strain/load. Default RHR or defaulted sex marks calibrating. Current window starts after latest eligible main sleep of at least three hours; historical days run to next eligible sleep start, with midnight fallbacks. Midpoints assign each interval once to the first sorted matching workout. Workout details below 0.5 load are dropped, while total load retains them. Unlogged effort >=45% HRR lasting >=10 minutes is suggested without adding load twice.

Seven/28-day strain averages use available days with positive coverage; acute/chronic uses mean recent seven-day raw load / mean 28-day raw load with at least 21 valid rows. Recovery-based target bands are 4–10 below 34, 10–14 from 34 to below 67, and 14–18 at 67+. These thresholds remain product heuristics.

### Connected Recovery — backend/recovery_score.py

Baseline spans day-67 through day-8 inclusive (60 dates). Recent spans day-6 through today inclusive. Require 21 valid baseline HRV days and four recent HRV readings. In log HRV space: center=median; spread=max(1.4826*MAD,0.05). Signal=0.7*mean(recent ln HRV)+0.3*ln(today HRV), or recent mean alone if today is missing. zHRV=(signal-center)/spread.

RHR uses at least 21 baseline readings with the same known device calculation method as today. zRHR=(median RHR-today RHR)/max(1.4826*MAD,1 bpm). Combined z=0.6*zHRV+0.4*zRHR when RHR is available, otherwise HRV alone. Sleep performance=min(sleep/need,1); sleep shorter than 180 minutes is discarded. Sleep adjustment=-0.5*clamp((0.85-performance)/0.25,0,1); no modifier for missing context. Final z clips to [-3,3]; illness flag caps z at -0.5. Respiratory/skin-temperature deviation beyond two robust spreads triggers that flag if the baseline has >=21 valid points and nonzero spread.

Zones: below_normal for z<-0.5, above_normal for z>0.5, otherwise normal. High confidence requires >=45 baseline, >=6 recent, RHR and sleep context; medium >=28 baseline and >=5 recent; otherwise low. Percentage=rounded 100*normal CDF(z), withheld at low confidence. This is a baseline-relative mapping, not a probability of physiological recovery. Independent oracle uses statistics.NormalDist.cdf rather than the implementation erf expression.

### Sleep need — backend/sleep_need.py

All durations in minutes. Baseline 450. Convert strain percentage to 0–21 via *0.21 and clamp. Let L(s)=1/(1+exp(-0.476*(s-14.38))). Strain addition=26*(L(s)-L(0))/(L(21)-L(0)); additions below one minute become zero. Prior seven nights, most recent first, use weights [1,0.85,0.7,0.55,0.4,0.25,0.1]. Debt=clamp(weighted mean of baseline+historical strain addition-actual sleep,0,240), ignoring incomplete nights; surpluses offset deficits. Debt addition=34% of debt. Need=clamp(baseline+strain addition+debt addition-today nap minutes,360,660). This is weighted average debt, not cumulative debt.

### Sleep score — sleepscore.py

SleepData durations are seconds; sleep_need is hours. Duration ratio includes naps. At ratio<=1, duration=100/(1+exp(-8*(ratio-0.75))); at 1<ratio<=1.1, duration=100; above 1.1, duration=max(30,100-75*(ratio-1.1)). Stage denominator is required sleep seconds: deep target 20% through age30, then -0.2 percentage points/year floored at10%; REM20%, core50%. Each stage component caps at100; stage mix=40% deep+40%REM+20%core.

Efficiency component maps asleep/period 70%–95% to0–100. HRV component maps baseline ratio0.7–1.3 to0–100; sleeping-HR uses the inverted mapping. Dip maps (wakingHR-sleepingHR)/wakingHR 0–25% to0–100. Restfulness=clamp(100*exp(-0.035*awake_minutes)-min(15,2.5*interruptions),0,100). Final weights: duration27%, stages20%, efficiency10%, HRV5%, HR5%, dip18%, restfulness15%. Missing HR-derived values default to50. Zero total sleep or nonpositive need returns0.

### Efficiency, timing, ranges and sleep stress

Standalone efficiency=round(100*asleep_seconds/period_seconds,1), only for finite 0<asleep<=period<=86400; otherwise None. Trend aggregate uses ratio of summed durations, not average of daily percentages. Four-night consistency uses circular onset/wake differences, average drift per pair, sigmoid centered75 minutes with slope0.05, normalized to100 at0 and0 at240 minutes. Weights0.4/0.3/0.2/0.1, renormalized for missing nights, at least two prior nights. Seven-night timing variability requires consecutive dates and uses circular clock mean plus population SD of wrapped deviations.

Stage ranges require complete nonoverlapping contiguous processed stage partition and at least three asleep hours; naps excluded. Default denominator is full recorded sleep period. Restorative=deep+REM. Last up to seven unique prior wake dates, minimum four: center=100*sum(stage minutes)/sum(period minutes); spread=max(1.4826*MAD of daily stage percentages,1 percentage point). Band=center±spread clipped0–100. These are descriptive provisional bands.

Sleep stress validates HRV windows, awake overlap, >=70% stage majority, HR35–130 bpm and >=60% inferred HR sample coverage. Baseline needs seven eligible main nights within14 dates, >=50% night coverage; use per-stage robust medians/spreads if >=30 windows, else pooled fallback. Log HRV spread floor0.02; HR spread floor0.5 bpm. Candidate requires both HRV drop z>=1 and HR rise z>=1. At least two exactly adjacent candidate windows form an episode. Stress%=100*episode minutes/valid window minutes; it is not a fraction of the entire night unless coverage is complete. Seeded stress cases here deliberately have full six-hour coverage.

### Trend and legacy helpers

Health: prior-only14-calendar-day median after seven readings, date-aligned gaps; intraday HR uses15-minute median bins, latest HR is a separate raw sample. Weekly windows have7 dates, monthly30; six/12-month windows use calendar arithmetic. Recovery analytics retain missing sleep-context flags on historical estimates and filter RHR method; strength minutes/steps are display aggregates, not additional cardio load.

Legacy recovery.py remains a separate prototype:40%HRV+25%RHR+25%sleep+10%(1-strain/21)*100, ACR penalty0–10 above1.3, optional adjustment, clipped0–100. Legacy HRV uses EWMA ln baseline alpha0.25 and sample SD, mapped50+25*z; fallback scalar ratio0.5–1.5. Legacy sleep helpers include debt hours, clock consistency, latency score, bedtime subtraction and Ayurvedic clock-window points. They are inventoried and spot-checked, not asserted to have exhaustive branch coverage.

## Selected data and numerical results

| Family / case | Input | Expected | Actual | Pass |
|---|---|---|---|---|
| cardio strain / constant HR 0 | {"age": 30, "rhr": 56.0, "hr": 135, "minutes": 45, "sex": "m", "sample_interval_s": 60} | {"load": 55.2842750986139, "strain": 9.638247004121036, "coverage": 1.0} | {"load": 55.28427509861388, "strain": 9.638247004121032, "coverage": 1.0} | True |
| cardio strain / constant HR 1 | {"age": 30, "rhr": 56.0, "hr": 135, "minutes": 45, "sex": "f", "sample_interval_s": 60} | {"load": 63.89169383123545, "strain": 10.674518950757239, "coverage": 1.0} | {"load": 63.89169383123544, "strain": 10.674518950757237, "coverage": 1.0} | True |
| cardio strain / constant HR 2 | {"age": 30, "rhr": 56.0, "hr": 160, "minutes": 45, "sex": "m", "sample_interval_s": 60} | {"load": 104.98776003238365, "strain": 14.45964287205955, "coverage": 1.0} | {"load": 104.98776003238368, "strain": 14.459642872059552, "coverage": 1.0} | True |
| cardio strain / DST repeated hour | {"start": "2026-10-25T02:58:00+02:00", "end": "2026-10-25T02:02:00+01:00"} | {"counted_minutes": 4.0, "coverage": 1.0} | {"counted_minutes": 4.0, "coverage": 1.0} | True |
| cardio integration / irregular sinusoidal trace 0 | {"age": 30, "rhr": 56.0, "sex": "m", "samples": [["2026-10-07T07:00:00+00:00", 125.0], ["2026-10-07T07:01:30+00:00", 125.0], ["2026-10-07T07:06:30+00:00", 126.6632394276493], ["2026-10-07T07:07:00+00:00", 128.30596615184183], ["2026-10-0... (full data in JSON) | {"load": 206.17906285767273, "workout_load": 67.81130451253489, "incidental_load": 138.36775834513784, "counted_minutes": 204.0, "coverage": 0.6538461538461539} | {"load": 206.17906285767273, "workout_load": 67.81130451253489, "incidental_load": 138.36775834513784, "counted_minutes": 204.0, "coverage": 0.6538461538461539} | True |
| cardio integration / irregular sinusoidal trace 1 | {"age": 30, "rhr": 56.0, "sex": "m", "samples": [["2026-10-07T07:00:00+00:00", 125.0], ["2026-10-07T07:06:00+00:00", 125.0], ["2026-10-07T07:06:30+00:00", 126.6632394276493], ["2026-10-07T07:07:30+00:00", 128.30596615184183], ["2026-10-0... (full data in JSON) | {"load": 194.5234460077629, "workout_load": 74.65104258275343, "incidental_load": 119.87240342500948, "counted_minutes": 199.5, "coverage": 0.6616915422885572} | {"load": 194.5234460077629, "workout_load": 74.65104258275343, "incidental_load": 119.87240342500948, "counted_minutes": 199.5, "coverage": 0.6616915422885572} | True |
| cardio integration / irregular sinusoidal trace 2 | {"age": 30, "rhr": 56.0, "sex": "m", "samples": [["2026-10-07T07:00:00+00:00", 125.0], ["2026-10-07T07:01:30+00:00", 125.0], ["2026-10-07T07:06:30+00:00", 126.6632394276493], ["2026-10-07T07:10:30+00:00", 128.30596615184183], ["2026-10-0... (full data in JSON) | {"load": 221.45848050774146, "workout_load": 72.59437728469359, "incidental_load": 148.86410322304786, "counted_minutes": 218.5, "coverage": 0.6947535771065183} | {"load": 221.45848050774146, "workout_load": 72.59437728469359, "incidental_load": 148.86410322304786, "counted_minutes": 218.5, "coverage": 0.6947535771065183} | True |
| cardio integration / irregular sinusoidal trace 99 | {"age": 30, "rhr": 56.0, "sex": "m", "samples": [["2026-10-07T07:00:00+00:00", 125.0], ["2026-10-07T07:00:30+00:00", 125.0], ["2026-10-07T07:04:30+00:00", 126.6632394276493], ["2026-10-07T07:05:00+00:00", 128.30596615184183], ["2026-10-0... (full data in JSON) | {"load": 205.80748101841053, "workout_load": 66.9762670630751, "incidental_load": 138.83121395533544, "counted_minutes": 206.0, "coverage": 0.6821192052980133} | {"load": 205.80748101841053, "workout_load": 66.9762670630751, "incidental_load": 138.83121395533544, "counted_minutes": 206.0, "coverage": 0.6821192052980133} | True |
| strain analytics / acute chronic ratio | {"last_7_load": 100, "preceding_21_load": 50} | 1.6 | 1.6 | True |
| demo integrity / raw strain inputs replay | {"days": 28, "seed": "date anchored"} | [{"date": "2026-09-10", "load": 147.85056374003597, "strain": 16.93774435807225, "coverage": 0.9375, "steps": 10725}, {"date": "2026-09-11", "load": 16.686572296292844, "strain": 3.5539008564607704, "coverage": 0.9375, "steps": 4200}, {"date": "2026-09-12", "load": 68.69574823150076, "strain": 11.211224753026137, "coverage": 0.9375, "steps": 107... (full result in JSON) | [{"date": "2026-09-10", "load": 147.85056374003597, "strain": 16.93774435807225, "coverage": 0.9375, "steps": 10725}, {"date": "2026-09-11", "load": 16.686572296292844, "strain": 3.5539008564607704, "coverage": 0.9375, "steps": 4200}, {"date": "2026-09-12", "load": 68.69574823150076, "strain": 11.211224753026137, "coverage": 0.9375, "steps": 107... (full result in JSON) | True |
| connected recovery / robust reference 0 | {"baseline_hrv": [40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.... (full data in JSON) | {"z": -0.0, "percent": 50, "zone": "normal", "confidence": "high", "components": {"z_hrv": -8.881784197001252e-15, "z_rhr": 0.0, "sleep_adj": -0.0}} | {"z": -0.0, "percent": 50, "zone": "normal", "confidence": "high", "components": {"z_hrv": -8.881784197001252e-15, "z_rhr": -0.0, "sleep_adj": -0.0}} | True |
| connected recovery / robust reference 1 | {"baseline_hrv": [40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.... (full data in JSON) | {"z": -0.25, "percent": 40, "zone": "normal", "confidence": "high", "components": {"z_hrv": -8.881784197001252e-15, "z_rhr": 0.0, "sleep_adj": -0.25}} | {"z": -0.25, "percent": 40, "zone": "normal", "confidence": "high", "components": {"z_hrv": -8.881784197001252e-15, "z_rhr": -0.0, "sleep_adj": -0.25}} | True |
| connected recovery / robust reference 2 | {"baseline_hrv": [40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.... (full data in JSON) | {"z": 2.5, "percent": 99, "zone": "above_normal", "confidence": "high", "components": {"z_hrv": 4.1588830833596635, "z_rhr": 0.0, "sleep_adj": -0.0}} | {"z": 2.5, "percent": 99, "zone": "above_normal", "confidence": "high", "components": {"z_hrv": 4.1588830833596635, "z_rhr": -0.0, "sleep_adj": -0.0}} | True |
| connected recovery / availability 45/6 | {"baseline_nights": 45, "recent_nights": 6} | {"status": "ok", "confidence": "high", "percent": 50} | {"status": "ok", "confidence": "high", "percent": 50} | True |
| date joins / recovery dedup and excluded dates | {"raw_rows": 70, "baseline_start": "2026-08-01", "baseline_end": "2026-09-29"} | {"baseline_days": 60, "recent_nights": 7, "z": 0} | {"baseline_days": 60, "recent_nights": 7, "z": -0.0} | True |
| sleep need / logistic and debt 0 | {"strain_pct": 0, "historical_sleep_min": 450, "nap_min": 0, "history_nights": 7} | {"strain_add_min": 0, "sleep_debt_min": 0, "debt_add_min": 0.0, "total_need_min": 450.0} | {"strain_add_min": 0.0, "sleep_debt_min": 0.0, "debt_add_min": 0.0, "total_need_min": 450.0} | True |
| sleep need / logistic and debt 1 | {"strain_pct": 100, "historical_sleep_min": 450, "nap_min": 0, "history_nights": 7} | {"strain_add_min": 26.0, "sleep_debt_min": 25.999999999999996, "debt_add_min": 8.84, "total_need_min": 484.84} | {"strain_add_min": 26.0, "sleep_debt_min": 26.0, "debt_add_min": 8.84, "total_need_min": 484.84} | True |
| sleep need / logistic and debt 2 | {"strain_pct": 51.54775758354023, "historical_sleep_min": 286.4901372078503, "nap_min": 177.51486213935036, "history_nights": 7} | {"strain_add_min": 4.191626234549858, "sleep_debt_min": 167.70148902669953, "debt_add_min": 57.01850626907785, "total_need_min": 360} | {"strain_add_min": 4.191626234549858, "sleep_debt_min": 167.70148902669956, "debt_add_min": 57.018506269077854, "total_need_min": 360.0} | True |
| sleep need / logistic and debt 201 | {"strain_pct": 91.57899808079482, "historical_sleep_min": 339.20620705593, "nap_min": 85.35044812117951, "history_nights": 7} | {"strain_add_min": 24.661745087562707, "sleep_debt_min": 135.45553803163273, "debt_add_min": 46.05488293075513, "total_need_min": 435.3661798971383} | {"strain_add_min": 24.661745087562707, "sleep_debt_min": 135.45553803163273, "debt_add_min": 46.05488293075513, "total_need_min": 435.3661798971383} | True |
| sleep score / weighted score 0 | {"hours": 7.5, "need_h": 7.5, "age": 30, "awake_min": 20, "interruptions": 2, "hrv": 45, "sleeping_hr": 56, "waking_hr": 72, "components": {"duration": 88.07970779778823, "stage": 100.0, "efficiency": 100.0, "hrv": 50.000000000000014, "h... (full data in JSON) | 81.48030066 | 81.48030066 | True |
| sleep score / weighted score 1 | {"hours": 7.500001, "need_h": 7.5, "age": 30, "awake_min": 20, "interruptions": 2, "hrv": 45, "sleeping_hr": 56, "waking_hr": 72, "components": {"duration": 100, "stage": 100.0, "efficiency": 100.0, "hrv": 50.000000000000014, "hr": 50.00... (full data in JSON) | 84.69877956 | 84.69877956 | True |
| sleep score / weighted score 2 | {"hours": 3.75, "need_h": 7.5, "age": 30, "awake_min": 20, "interruptions": 2, "hrv": 45, "sleeping_hr": 56, "waking_hr": 72, "components": {"duration": 11.920292202211755, "stage": 56.0, "efficiency": 87.34693877551022, "hrv": 50.000000... (full data in JSON) | 50.85195233 | 50.85195233 | True |
| sleep score / weighted score 202 | {"hours": 4.703994269712636, "need_h": 7.5, "age": 72, "awake_min": 112.1646223164984, "interruptions": 2, "hrv": 45, "sleeping_hr": 56, "waking_hr": 72, "components": {"duration": 27.24146193599083, "stage": 72.35370386053997, "efficien... (full data in JSON) | 43.45033655 | 43.45033655 | True |
| sleep efficiency / 27000/28800 | {"asleep_s": "27000", "period_s": 28800} | 93.8 | 93.8 | True |
| sleep efficiency / 0/28800 | {"asleep_s": "0", "period_s": 28800} | null | null | True |
| sleep efficiency / 30000/28800 | {"asleep_s": "30000", "period_s": 28800} | null | null | True |
| sleep efficiency / random 99 | {"asleep_s": 25007.849222769215, "period_s": 46792.85006741804} | 53.4 | 53.4 | True |
| sleep consistency / clock drift 0 | {"drift_min": 0, "prior_nights": 4} | {"score": 100.0, "drift_minutes": 0} | {"score": 100.00000000000001, "drift_minutes": 0.0} | True |
| sleep consistency / clock drift 30 | {"drift_min": 30, "prior_nights": 4} | {"score": 92.59060687264022, "drift_minutes": 30} | {"score": 92.59060687264025, "drift_minutes": 30.000000000000004} | True |
| sleep consistency / clock drift 75 | {"drift_min": 75, "prior_nights": 4} | {"score": 51.1628315096191, "drift_minutes": 75} | {"score": 51.16283150961911, "drift_minutes": 75.00000000000001} | True |
| sleep consistency / missing calendar night | {"nights": 6} | null | null | True |
| stage ranges / partition 0 | {"minutes": [52, 281, 30, 114]} | {"status": "ok", "pct": {"awake": 10.90146750524109, "light": 58.909853249475894, "deep": 6.289308176100629, "rem": 23.89937106918239}} | {"status": "ok", "pct": {"awake": 10.90146750524109, "light": 58.909853249475894, "deep": 6.289308176100629, "rem": 23.89937106918239}} | True |
| stage ranges / partition 1 | {"minutes": [2, 276, 39, 144]} | {"status": "ok", "pct": {"awake": 0.43383947939262474, "light": 59.869848156182215, "deep": 8.459869848156183, "rem": 31.23644251626898}} | {"status": "ok", "pct": {"awake": 0.43383947939262474, "light": 59.869848156182215, "deep": 8.459869848156183, "rem": 31.23644251626898}} | True |
| stage ranges / partition 2 | {"minutes": [7, 186, 57, 133]} | {"status": "ok", "pct": {"awake": 1.8276762402088773, "light": 48.56396866840731, "deep": 14.882506527415144, "rem": 34.72584856396867}} | {"status": "ok", "pct": {"awake": 1.8276762402088773, "light": 48.56396866840731, "deep": 14.882506527415144, "rem": 34.72584856396867}} | True |
| stage ranges / unequal-length pooled center | {"light_minutes": [270, 258, 300, 282], "total_minutes": [540, 600, 660, 600]} | {"center": 46.25, "spread": 2.9652, "low": 43.2848, "high": 49.2152} | {"center": 46.25, "spread": 2.9652, "low": 43.2848, "high": 49.2152} | True |
| sleep stress / all normal | {"window_count": 72, "window_min": 5, "readings": [[40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40,... (full data in JSON) | {"stressed_minutes": 0, "stress_pct": 0.0} | {"stressed_minutes": 0, "stress_pct": 0.0} | True |
| sleep stress / all joint | {"window_count": 72, "window_min": 5, "readings": [[20, 80, 5], [20, 80, 5], [20, 80, 5], [20, 80, 5], [20, 80, 5], [20, 80, 5], [20, 80, 5], [20, 80, 5], [20, 80, 5], [20, 80, 5], [20, 80, 5], [20, 80, 5], [20, 80, 5], [20, 80, 5], [20,... (full data in JSON) | {"stressed_minutes": 360, "stress_pct": 100.0} | {"stressed_minutes": 360, "stress_pct": 100.0} | True |
| sleep stress / HRV only | {"window_count": 72, "window_min": 5, "readings": [[20, 60, 5], [20, 60, 5], [20, 60, 5], [20, 60, 5], [20, 60, 5], [20, 60, 5], [20, 60, 5], [20, 60, 5], [20, 60, 5], [20, 60, 5], [20, 60, 5], [20, 60, 5], [20, 60, 5], [20, 60, 5], [20,... (full data in JSON) | {"stressed_minutes": 0, "stress_pct": 0.0} | {"stressed_minutes": 0, "stress_pct": 0.0} | True |
| sleep stress / two joint | {"window_count": 72, "window_min": 5, "readings": [[20, 80, 5], [20, 80, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40, 60, 5], [40,... (full data in JSON) | {"stressed_minutes": 10, "stress_pct": 2.78} | {"stressed_minutes": 10, "stress_pct": 2.78} | True |
| legacy recovery / HRV fallback 0.5 | {"hrv_ratio": 0.5, "rhr": 56, "rhr_baseline": 56, "sleep_score": 80, "strain_21": 10.5} | 37.5 | 37.5 | True |
| legacy recovery / HRV fallback 1.0 | {"hrv_ratio": 1.0, "rhr": 56, "rhr_baseline": 56, "sleep_score": 80, "strain_21": 10.5} | 57.5 | 57.5 | True |
| legacy recovery / HRV fallback 1.5 | {"hrv_ratio": 1.5, "rhr": 56, "rhr_baseline": 56, "sleep_score": 80, "strain_21": 10.5} | 77.5 | 77.5 | True |
| legacy recovery / log EWMA and sample SD | {"history": [38, 41, 36.5, 40.2, 43.1, 39.8, 42.5, 44, 37.9, 41.3], "today_hrv": 44} | 82.83 | 82.83 | True |
| legacy sleep helpers / latency 0 | {"latency_min": 0} | 50 | 50 | True |
| legacy sleep helpers / latency 5 | {"latency_min": 5} | 75 | 75 | True |
| legacy sleep helpers / latency 10 | {"latency_min": 10} | 100 | 100 | True |
| legacy sleep helpers / sleep debt hours | {"need_actual_h": [[8, 6], [8, 9], [7, 5]]} | 4 | 4 | True |
| health trends / prior-only median | {"prior_hrv": [41, 42, 43, 44, 45, 46, 47], "today": 999} | 44 | 44 | True |
| health trends / 15-minute medians | {"readings": [["07:00", 60], ["07:05", 80], ["07:16", 100]]} | [70, 100] | [70.0, 100.0] | True |
| health trends / latest distinct from bin median | {"readings": 3} | 100 | 100 | True |
| sleep trends / duration-weighted efficiency with gaps | {"asleep": [240, 570], "period": [300, 600]} | {"average": 90.0, "days": 7, "recorded": 2, "scored": 2} | {"average": 90.0, "days": 7, "recorded": 2, "scored": 2} | True |
| calendar windows / W | {"end": "2026-10-07"} | 7 | 7 | True |
| calendar windows / M | {"end": "2026-10-07"} | 30 | 30 | True |
| demo API replay / /api/dashboard | {"headers": {"X-User-Date": "2026-10-07", "X-User-Age": "30", "X-User-Sex": "m", "X-User-Timezone": "Europe/Berlin"}, "network": "forbidden"} | 200 | 200 | True |
| demo API replay / /api/strain?demo=true | {"headers": {"X-User-Date": "2026-10-07", "X-User-Age": "30", "X-User-Sex": "m", "X-User-Timezone": "Europe/Berlin"}, "network": "forbidden"} | 200 | 200 | True |
| demo API replay / /api/strain/analytics?demo=true | {"headers": {"X-User-Date": "2026-10-07", "X-User-Age": "30", "X-User-Sex": "m", "X-User-Timezone": "Europe/Berlin"}, "network": "forbidden"} | 200 | 200 | True |
| demo API replay / /api/health/heart-rate | {"headers": {"X-User-Date": "2026-10-07", "X-User-Age": "30", "X-User-Sex": "m", "X-User-Timezone": "Europe/Berlin"}, "network": "forbidden"} | 200 | 200 | True |

## Numerical examples and inference by algorithm

At age 30 and resting HR 56 bpm, the male-coefficient constant-HR cases yield:

| HR | Duration | Raw load | Strain |
|---:|---:|---:|---:|
| 135 bpm | 45 min | 55.284275 | 9.638247 |
| 160 bpm | 45 min | 104.987760 | 14.459643 |
| 172 bpm | 60 min | 186.159345 | 18.345954 |

Inference: higher HR and longer time increase load on these controlled cases, but strain compresses nonlinearly toward 21. Male/female coefficient sets yield different scores for the same input; this verifies the selected formula rather than demonstrating a measured sex difference. The 100 irregular traces check actual pair averaging, five-minute gap exclusion, coverage and workout/incidental conservation; raw samples are saved in JSON.

Recovery: a flat 40 ms HRV / 56 bpm RHR reference with identical recent/current readings and adequate sleep gives z=0, 50%, normal, high confidence. Sleep at 326.25 of 450 minutes gives performance0.725 and adjustment-0.25 z. The illness cap produces z=-0.5 and 31%, while the exact boundary remains normal. Inference: this percentage describes position on a normal-CDF mapping; it cannot be interpreted as the probability of readiness. Low-confidence withholding, same-method RHR and prior-only dates are covered by the existing suite and the new threshold/join checks.

Sleep need: 0 strain, seven450-minute nights and no naps gives450 minutes. 100% strain with the same historical sleep gives26 extra strain minutes,26 weighted debt minutes,8.84 repayment minutes and484.84 total minutes. Inference: the debt calculation includes each historical strain-adjusted need; it is not merely the shortfall against450. Naps reduce need, subject to the360-minute floor. Sweeps include negative/above100 strain percentages to verify the implemented clamp.

Sleep efficiency:450 minutes asleep within480 minutes gives93.8%. Two unequal periods with240/300 and570/600 give90% pooled efficiency, rather than87.5% arithmetic mean of the daily ratios. Inference: longer sessions contribute more to this aggregate; invalid periods stay missing. Clock consistency checks distinguish four-night heuristic scores from seven-night SD and verify missing-date withholding.

Stage ranges: prior light minutes[270,258,300,282] over total minutes[540,600,660,600] yield pooled center46.25%, robust spread2.9652 percentage points, and band43.2848–49.2152%. Inference: the center is duration-weighted while spread is based on daily percentages. The range is descriptive and does not constitute a population normal range.

Sleep stress:72 five-minute joint HRV-drop/HR-rise windows against seven full six-hour reference nights give360 stressed minutes and100% of valid time. HRV drop alone gives0 stressed minutes; an isolated joint window gives0; two adjacent joint windows give10 minutes and2.78%. Inference: persistence and joint signals drive the detector, not HRV alone. These clear synthetic contrasts do not establish real-world sensitivity or specificity.

Demo endpoints:17 routes returned200 with outbound async HTTP blocked. Full dashboard, legacy/estimated Recovery, strain, trend, sleep, stage-range and stress responses are retained. This establishes runnable demo assembly/API serialization; status checks alone are not independent physiological/numerical validation of every field.

Existing suite emitted one Starlette/AnyIO deprecation warning (BlockingPortal alias); it did not fail a test. Total console runtime was52.46 seconds.

## Reproduced issues and assumptions needing review

### 1. Sleep duration score discontinuity at 100% of need

Evidence: `{"at_7_5_h": 81.48030066227396, "at_7_500001_h": 84.69877955687114, "jump_points": 3.218478894597183}`

The undersleep sigmoid ends at 88.0797, but the next branch begins at 100. Weighted total jumps about 3.22 points for an arbitrarily small duration increase. Formula matches source, but continuity fails; review before changing.

### 2. Sleep stress baseline assumes unique sessions

Evidence: `{"unique_sleep_ids": 1, "supplied_rows": 7, "nights_used": 7, "status": "ok"}`

The pure baseline builder counts rows rather than unique wake dates/session IDs. Repeating one prior night satisfies the seven-night minimum. Persistence keys by sleep ID, but the connected pipeline feeds prepared raw rows to score_night before storage, so storage uniqueness does not itself protect this baseline. Actual reconciled input duplication and multiple main sleeps on a date need review.

### 3. Health trend adapter trusts daily summary values

Evidence: `{"seven_prior_hrv_values": -1, "returned_baseline": -1.0}`

Nonpositive daily HRV is accepted into the descriptive median. HR chart and connected Recovery filter invalid readings, but this trend helper does not. This can display an impossible reference if invalid device/fixture data reach it.

### 4. Strain resting-HR baseline lacks an upper plausibility bound

Evidence: `{"resting_hr": 1000, "hr_max": 187, "hr": 160, "load": 0.0, "params": {"hr_max": 187.0, "hr_rest": 1000, "hr_rest_source": "recovery", "strain_l": 90, "sex": "m", "sex_source": "profile"}}`

The function accepts finite positive RHR even above estimated maximum HR; the HRR denominator is floored at 1 and load becomes zero in this case. Realistic valid-input cases pass; malformed RHR should be rejected or flagged upstream.

### 5. Today HRV participates in both recent and today terms

Evidence: `{"today_hrv": 80, "other_recent_hrv": 40, "z_hrv": 5.545177444479554, "effective_today_log_weight": 0.39999999999999997}`

The recent seven-date window includes today; with all seven readings, today receives 40% total log-signal weight, not 30%. This is deterministic source behavior; clarify whether the intended recent signal should exclude today. Existing tests codify the inclusive window.

## Existing suite evidence by file

| Test file | Cases | Failures/errors |
|---|---:|---:|
| backend | 220 | 0 |

## Interpretation and limits

The continuous-HR closed-form and seeded sweeps support numerical equivalence for strain across ages18–100, both coefficient sets, low/above-maximum HRR, different durations and gap thresholds. Recovery sweeps independently reproduce robust-reference components, confidence, zones and percentages. Sleep need, score, efficiency, timing, stage ranges and stress examples agree with the specified equations on their tested domains. Unit/integration suite covers API contracts, HTTP errors, pagination/cache isolation, DST, sleep session selection, stage/stress stores, webhook verification and missing-data rules.

Five probes expose assumptions/behavior that passing regression tests do not establish as correct. Formula equivalence is distinct from desirable behavior: in particular sleep-score continuity and invalid baseline handling need review. No p-values, sensitivity, specificity, device accuracy, or medical normal ranges are inferred from synthetic data. No held-out real-device target was supplied; coefficients, confidence labels, illness flag and training targets have not been physiologically validated by this audit.

Random cases are controlled synthetic data, not population samples: they do not model sensor bias, medication, illness, arrhythmia, motion artifacts, or cross-device drift. The new script samples plausible and boundary inputs plus selected invalid cases; it does not exercise every configuration, every auth route, every storage failure, or every event ordering. Existing mocks cannot prove live API field accuracy or production persistence correctness.

## Recommended next decisions

1. Review the sleep-score discontinuity and decide whether the duration curve should be normalized at100% need.
2. Define whether today should be included in Recovery’s recent signal as well as its separate today term.
3. Apply metric-aware validity gates to daily trend summaries and constrain/flag resting HR relative to plausible bounds.
4. Deduplicate or explicitly count unique nights in the sleep-stress baseline builder.
5. Validate physiological claims separately using timestamped real Fitbit data, independent outcomes and held-out participants/days.

No fixes were made during this audit; the evidence preserves current behavior.
