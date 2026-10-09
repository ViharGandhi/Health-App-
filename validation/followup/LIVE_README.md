# Read-only device audit

No accessible bearer token or server-side session token was available during the audit. OAuth client ID/secret configuration exists; those values alone do not authorize device reads. The application stores session tokens in a signed browser cookie rather than a database token store. Existing SQLite caches were not treated as fresh live data or exported.

The runner needs a currently valid `GOOGLE_HEALTH_ACCESS_TOKEN`, obtained through the existing connection flow. Keep it in the process environment; never put it in a command argument, commit, or report. It does not refresh tokens. Provider 401/403 errors are reported as status codes without raw exceptions.

Required granted scopes, taken from `backend/auth.py`:

- `https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly`
- `https://www.googleapis.com/auth/googlehealth.sleep.readonly`
- `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly`

Run from the repository root after securely setting that environment variable:

```powershell
.venv/Scripts/python.exe validation/followup/live_readonly.py --days 60 --age 30 --sex m --timezone Europe/Berlin --output validation/followup/live-aggregate-report.json
```

Replace the age, sex and timezone with the actual profile. An optional `--end YYYY-MM-DD` selects the final device calendar day. No dates are written to the output. `--anchor start` or `--anchor end` is allowed only after real-device HRV timestamp calibration; without it, stress remains explicitly unassessed. The application's `SLEEP_STRESS_HRV_ANCHOR` is not silently assumed to be calibrated.

The runner scores the last 30–60 days, fetching 67 additional daily summary dates for the proper Recovery reference. Intraday HR/HRV is processed in weekly chunks, retaining only derived windows. It reuses production adapters and pure strain, need, Recovery, composite sleep, stage-range and stress calculators. It creates no stores, page snapshots, OAuth requests or webhooks. An HTTP hook allows only GET observation reads under `health.googleapis.com/v4/users/me/dataTypes/`.

Saved evidence contains counts, rejection reasons, aggregate provider-minus-calculated differences, field names and boolean timezone checks. It contains no tokens, raw dates, sleep IDs or raw daily readings. The live runner conservatively disables logs; production partition warnings were also made identifier-free during hardening. The script reports provider errors and exits nonzero; missing access is not a success.

Provider duration/efficiency/stage summaries are reference measurements, not ground truth. Segment totals can differ because composite sleep uses summary values while stage ranges require a complete partition. Timezone checks compare historical device wake offsets with the selected user activity timezone. Differences can be intentional during travel. Approved provider ceilings apply to sample RMSSD (200 ms) and daily VO2 (100 ml/kg/min). Daily/deep HRV, respiration and sleep-temperature ceilings were explicitly deferred; finite positivity does not establish physiological plausibility.

Offline script checks:

```powershell
.venv/Scripts/python.exe -m pytest validation/followup/test_live_script.py -q -p no:cacheprovider
```

These verify execution against Google-shaped fixtures and the missing-token path. They do not certify provider permissions, real-device schemas or physiological accuracy.
