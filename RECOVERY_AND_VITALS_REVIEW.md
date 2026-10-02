# Recovery and Fitbit Air vitals review

This review uses peer-reviewed work for physiological interpretation. Google Health's API documentation is used only to identify data fields and units. The current Recovery formula remains unchanged pending review.

## What the device supplies

| Screen label | Google Health v4 field | Meaning in the app |
| --- | --- | --- |
| HRV | `dailyHeartRateVariability.averageHeartRateVariabilityMilliseconds` | Daily device RMSSD in ms; use the returned value, not a calculation from heart-rate samples. |
| Deep-sleep HRV | `dailyHeartRateVariability.deepSleepRootMeanSquareOfSuccessiveDifferencesMilliseconds` | Optional deep-sleep RMSSD in ms. This is a different observation from the daily average. |
| Non-REM HR | `dailyHeartRateVariability.nonRemHeartRateBeatsPerMinute` | Optional non-REM heart rate in bpm. |
| RHR | `dailyRestingHeartRate.beatsPerMinute` | Daily device estimate in bpm; its optional `calculationMethod` says whether sleep data were used. |
| HR | `heartRate.beatsPerMinute` with `sampleTime` | Timestamped sample in bpm; chart uses the median of samples within each recorded 15-minute bin and leaves unsampled periods blank. |
| SpO₂ | `dailyOxygenSaturation.averagePercentage` | Overnight average percentage; not a spot reading or a diagnostic threshold. |
| Breathing | `dailyRespiratoryRate.breathsPerMinute` | Average rate during the main sleep. |
| Skin temperature | `dailySleepTemperatureDerivations.nightlyTemperatureCelsius` | Mean nightly skin temperature in °C, not core temperature. |
| VO₂ max | `dailyVo2Max.vo2Max` and optional `estimated` | Device-supplied fitness estimate in mL/kg/min; do not derive it again from heart rate. |

The [Fitbit Air compatibility list](https://developers.google.com/health/data-types/device-compatibility) includes these types. The [Google Health data-point schema](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints) specifies the fields and units. Optional fields are omitted rather than imputed. No Fitbit Air validation study was found in this review, so results from other Fitbit models cannot establish its accuracy.

## Interpretation supported by research

- **HRV:** Repeated RMSSD readings under comparable conditions are more useful than comparing one person's absolute number with another's. HRV-guided training studies use different recording and decision methods, and do not validate a universal daily readiness percentage. [HRV-guided training methodological review and meta-analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC8507742/).
- **RHR:** Large longitudinal wearable data show substantial differences between people and meaningful variation within individuals. Use a personal prior-period reference. [Natarajan et al., 2020](https://pubmed.ncbi.nlm.nih.gov/32023264/).
- **Heart rate and HRV measurement:** Wrist photoplethysmography accuracy varies by device and situation. A study of six wearables compared sleep, HR and HRV against references but did not test Fitbit Air. [Miller et al., 2022](https://pubmed.ncbi.nlm.nih.gov/36016077/).
- **Breathing and SpO₂:** Nocturnal respiratory rate can change with illness but is not disease-specific. Wearable oxygen saturation has material measurement uncertainty; an overnight average should not diagnose a condition. [Natarajan et al., 2021](https://pubmed.ncbi.nlm.nih.gov/34526602/); [wearable vital-sign systematic review](https://pubmed.ncbi.nlm.nih.gov/35947876/).
- **VO₂ max:** A Fitbit Charge 2 cardio-fitness estimate had acceptable agreement with laboratory VO₂ max in a study of healthy adults aged 18–45 who could run. That result does not validate Fitbit Air or other populations. [Klepin et al., 2019](https://pubmed.ncbi.nlm.nih.gov/31107835/).

The Health screen therefore shows measured values, their dates, gaps, and a median of the preceding 14 calendar days only after at least seven prior readings. That median is descriptive context, not a medical normal range. The 1W, 6M and 1Y views retain missing dates as gaps. The demo series is explicitly labeled.

## Recovery formula decision before changing code

The existing `recovery.py` score weights HRV/RHR/sleep/previous-day strain at 40/25/25/10. Those weights and its 0–100 mapping have not been validated for Fitbit Air. Connected mode now requires today's HRV, RHR and sleep plus at least seven prior HRV and seven prior RHR readings within 14 days. It uses the median of those prior readings as the personal reference and returns `score: null` with `status: calibrating` until the inputs are present. This is a display gate and reference correction, **not validation of the formula**. The formula and its score cutoffs remain experimental; the interface shows HRV/RHR trends separately from historical Recovery scores.

**Proposed calculation for review; not implemented:**

1. Keep daily Fitbit RMSSD, deep-sleep RMSSD, and daily RHR distinct. Require comparable dates and a prior-only reference. Use `ln(RMSSD)` for a signal trend because HRV is skewed; present the measured value in ms. The choice of a 14-day window and seven readings is a provisional product rule, not a research-derived optimum. [HRV-guided training methodological review](https://pmc.ncbi.nlm.nih.gov/articles/PMC8507742/).
2. Display each signal's signed deviation from its prior median: `ΔHRV = ln(today RMSSD) − median(ln(prior RMSSD))` and `ΔRHR = today RHR − median(prior RHR)`. Mark unavailable inputs, measurement dates, and the count behind each reference. Do not equate a median with a clinical normal range. [RHR longitudinal cohort](https://pubmed.ncbi.nlm.nih.gov/32023264/).
3. Treat sleep duration and efficiency as separate context; keep the existing sleep-score formula untouched. Add an optional daily self-report of fatigue or perceived recovery before offering training advice: a systematic review found subjective well-being measures more responsive to training load than the studied objective measures. [Saw et al., 2016](https://pmc.ncbi.nlm.nih.gov/articles/PMC4789708/).
4. Do not assign new weighted points or green/yellow/red thresholds from these studies. First define a measurable target, such as next-day perceived recovery plus completed training quality. Compare candidate features against that target on held-out Fitbit Air data; assess discrimination, calibration, missingness and subgroup/device error. Only then fit and publish a 0–100 mapping. The literature does not establish a WHOOP-equivalent formula or universal cutoffs. [HRV-guided training review](https://pmc.ncbi.nlm.nih.gov/articles/PMC8507742/); [wearable HRV reliability tutorial](https://pmc.ncbi.nlm.nih.gov/articles/PMC10346338/).

For Health, the same prior-only descriptive reference applies to HRV, RHR, nocturnal respiratory rate, SpO₂, skin temperature and device VO₂ max. HR samples remain a separate intraday chart. A reading outside a user's prior pattern is a prompt to inspect the trend and measurement context, not an illness label. Device validation papers for other models cannot establish Fitbit Air accuracy. [Wearable vital-sign systematic review](https://pubmed.ncbi.nlm.nih.gov/35947876/); [Fitbit Charge 2 VO₂ validation](https://pubmed.ncbi.nlm.nih.gov/31107835/).

WHOOP's [Health Monitor](https://www.whoop.com/us/en/thelocker/health-monitor-feature/) and [design guidelines](https://developer.whoop.com/assets/files/WHOOP%20-%20Brand%20%26%20Design%20Guidelines-bdea3554e94b4ea09e68695b1e8dc8e7.pdf) informed the dark layout, score ring, personal-reference presentation, and semantic color choices. Ojas keeps its own name and does not claim WHOOP-equivalent calculations.
