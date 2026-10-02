# Strain calculation review — proposal, not implemented

The connected 0–21 Strain score is currently an experimental app estimate. It is not WHOOP's proprietary Strain calculation and has not been validated for Fitbit Air. No formula change is included in this pass.

## Current inputs and limits

`backend/main.py` reads timestamped Fitbit heart-rate samples and exercise intervals. `strain.py` counts at most one minute between consecutive samples, drops heart rates below 50% of estimated maximum, weights time in five heart-rate zones, then divides by a capacity value. The app now asks for age and uses it for connected zone estimates; without it, the server still falls back to `USER_AGE=22` and the connected UI hides the age-dependent load. Capacity still uses a fixed, seeded 14-day load history. The 0–100 result is multiplied by 0.21 to create a 0–21 number. This is a display mapping, not an evidence-based conversion to WHOOP Strain; connected UI does not show that number.

The Tanaka equation (`208 − 0.7 × age`) estimates population-average maximum heart rate; individual error remains substantial. A device-observed peak is not necessarily a measured physiological maximum. [Tanaka et al., 2001](https://pubmed.ncbi.nlm.nih.gov/11153730/); [comparison of age-prediction equations](https://pubmed.ncbi.nlm.nih.gov/21691228/).

Heart-rate training impulse methods combine intensity and duration, but their outputs are method-specific arbitrary units. A review found relationships among HR-based TRIMP, wearable load and session effort, with variation across settings and activities. These studies do not establish a universal 0–21 daily scale or validate this app's zone weights for Fitbit Air. [Training-load systematic review](https://pubmed.ncbi.nlm.nih.gov/36679623/); [session-RPE comparison](https://pmc.ncbi.nlm.nih.gov/articles/PMC5377554/).

## Proposed next calculation

1. Age entry is implemented. Use a device-provided maximum heart rate only if the API explicitly supplies a measured maximum; otherwise label `208 − 0.7 × age` as an estimate. Never treat the highest observed sample as a proven maximum.
2. Calculate a transparent daily **HR load in arbitrary units** from recorded samples with explicit coverage and gap rules. Show recorded zone time and workout versus non-workout contribution. Mark low coverage as incomplete instead of interpreting it as low effort.
3. Build any personal reference from actual prior days only. Include the number of observed days and missing days; do not use the fixed seeded history in connected mode.
4. Compare candidate HR-load summaries with an independent target, such as session rating of perceived exertion and next-day fatigue, in held-out Fitbit Air data. Examine activity type, missing samples and individual error before considering a normalized score.
5. Keep a 0–21 display mapping in demo mode unless validation establishes what its values mean. A WHOOP-equivalent score cannot be inferred from the published research.

This proposal leaves the sleep-score algorithm unchanged. The current sleep score still receives the experimental previous-day Strain value; that dependency needs separate review when changing the sleep-score calculation is authorized.
