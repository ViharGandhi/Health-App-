# stressmon

Shared calculation engine for the app's 0–3 Stress Monitor. The backend serves connected observations through `/api/stress`; Home and `/stress` display scores, context, gaps, daily summaries and trends. The export commands below are optional diagnostic tools.

## App integration

Install `backend/requirements.txt` and start the backend and frontend normally. Open `/stress` for connected data or `/stress?demo=true` for a clearly labeled synthetic replay. The app reads account-scoped Google Health storage, including HR, sleep, exercise and activity levels. Activity levels join foreground sync with a bounded initial baseline backfill. No Takeout folder or CLI command is needed to use the app.

The app uses trailing HR filtering and causal EMA smoothing. Insufficient HR sampling, missing periods and vigorous exercise/recovery remain unscored. Unknown motion stays ambiguous and cannot supply sedentary baseline observations. HRV with unknown measurement coverage is excluded from both sleep pairing and previous-night context; unverified window anchoring also prevents sleep pairing. Live API data does not get synthetic coverage. The demo supplies explicitly synthetic HRV quality and timing.

Short histories use an explicitly flagged retrospective baseline; adequate histories use prior days only. The UI reports reference days, low confidence, coverage, stale readings, and an Estimated label. Synthetic verification establishes implementation behavior, not physiological accuracy or agreement with WHOOP.

## Run

From the repository root, with Python 3.11 and the dependencies in `requirements.txt` available:

```powershell
python -m pip install -e ./stressmon
stressmon probe --takeout "C:\path\Takeout\Google Health"
stressmon score --takeout "C:\path\Takeout\Google Health"
stressmon plot --takeout "C:\path\Takeout\Google Health" --date 2026-10-10
```

Installing is optional: `python -m stressmon` exposes the same commands from the repository root. Installation requires an existing local package cache or a separate network-enabled setup; the CLI itself never uses the network.

Every command accepts `--config path.yaml`. Score, plot and calibration accept `--out directory`; the default output directory is `stressmon-output`, ignored by Git. Outputs contain private, derived wearable information: do not publish them without reviewing them.

In this workspace, the existing offline Python 3.11 environment can run it through WSL:

```powershell
wsl.exe -d Ubuntu-24.04 -- bash -lc 'cd /mnt/e/Projects/Health-App- && /root/miniforge3/envs/metaquest/bin/python -m stressmon probe --takeout "/mnt/c/Users/devpa/Downloads/takeout-20261010T144304Z-1-001/Takeout/Google Health"'
```

Replace `probe` with `score`, or with `plot --date YYYY-MM-DD`. Windows drive paths become `/mnt/c/...` inside WSL.

## Inputs and alignment

Only the named HR, HRV detail, sleep stages, exercises and activity-level patterns are opened. Steps JSON is optional and used only when the timezone alignment correlation check succeeds. Activity probabilities are off by default and, when enabled, read in chunks to extract STILL probability. GPS, profile, security and unrelated export directories are never opened; exercise location columns are excluded. Raw data rows are never printed.

Missing required files or columns stop the command. Internal timestamps are UTC. Display dates use the single source offset from sleep/exercises, with an optional display override. Mixed source offsets require a per-night policy and are rejected rather than guessed.

The automatic probe compares UTC and the source offset for naive HRV times, requires at least 90% within sleep and reports ambiguity. Exercise median HR is checked against the tracker average within 15%; discrepancies are reported. Steps alignment is a heuristic based on activity-level correlation, with overlap and winning-margin thresholds in config; uncertain steps are ignored.

**HRV window anchor is unverified by default.** Timezone alignment does not establish whether a timestamp is the beginning or end of a measurement. The probe reports sleep containment under both interpretations. Until independently confirmed, within-sleep scoring uses HR only. Set `time.hrv_window_anchor` to `start` or `end` only after confirmation. Previous completed-night median HRV is still available as labeled context; it is never presented as daytime HRV.

## Calculation and outputs

HR filtering: physiological bounds, local Hampel filter, minute medians requiring ten samples, then five-minute medians requiring three valid minutes. HRV requires coverage ≥0.8 and 5 < RMSSD <250; features use ln(RMSSD). All configurable thresholds, weights, plotting settings and calibration bounds are in `config.yaml`.

State priority is OFFWRIST → SLEEP → EXERCISE → ACTIVE → STILL → AMBIG. Short awake sleep stages stay SLEEP but use HR only. Vigorous/high-HR exercises and their recovery buffers are masked. Lower-effort logged activities, such as a walk, remain scored as ACTIVE. Missing sensor coverage remains unavailable, never zero stress.

Baselines pool SLEEP and STILL HR, sleep ln(RMSSD), and nightly HRV medians. At least three reference days are required; fewer than seven are flagged low confidence. Auto mode uses retrospective reference dates below 14 available days, including the scored day and potentially future days: `baseline_leaks` explicitly marks this. With at least 14 days it uses prior days only. Force `baselines.mode: causal` to withhold scores during the initial warm-up.

Sleep IDs sharing a wake date count as one night for context and resting-HR references. HRV timestamps in overlapping/revised sessions are counted once; a duplicate sleep ID cannot inflate confidence or context weight.

Sleep blends standardized HR and verified sleep HRV; missing HRV uses HR only. Awake scores use standardized HR plus a small previous-night HRV context term. A logistic function maps these features to 0–3. Savitzky–Golay/Gaussian smoothing stays within contiguous sleep or awake segments and never crosses gaps or wake transitions. Live mode uses trailing HR filtering and causal EMA smoothing; the CLI is still an offline export processor, not a live feed.

- `scores_5min.csv`: UTC start/end, state, coverage, standardized features, raw/smoothed scores and the exact reference dates/parameters.
- `daily_summary.csv`: elapsed-time-weighted sleep, non-activity and total means, high minutes, scored duration and coverage. Coverage uses the observed day window, including leading missing periods; a separate probe reports coverage against a full 24-hour day.
- `probe.json`: file counts, timezone checks, coverage and warnings.
- `stress_YYYY-MM-DD.png`: 1600×900, 00:00–24:00 display-time chart. Hatched sections are unavailable or masked. An incomplete export uses a “Data through” line; it is not falsely labeled as the current time. Running/walking symbols are local vector drawings.

## Calibration

```powershell
stressmon calibrate --takeout "C:\path\Takeout\Google Health" --anchors --config my-config.yaml
stressmon calibrate --takeout "C:\path\Takeout\Google Health" --reference reference.csv --config my-config.yaml
```

Calibration writes fitted parameters to the supplied config and a report to `calibration.json`. Copy the default config first if you want to preserve it.

Anchors fit medians to SLEEP 0.5, STILL 1.2 and ACTIVE 2.2. With fewer than ten scored ACTIVE windows only the midpoint is fitted, with slope 0.6. This tunes chart appearance; it is **not validation**.

A reference CSV must have `timestamp,score`, timezone-qualified timestamps and scores within 0–3. Points are matched to five-minute window centers within the configured tolerance; masked/missing windows are rejected and duplicate matched windows are averaged. Five or more reference dates allow fitting all five parameters; otherwise only slope and midpoint are fitted. Sleep HR weights are normalized, so their relative share matters, not their absolute scale.

Leave-one-day-out evaluation fits training reference points only, excludes the held-out date from fold baselines and reports Pearson correlation, MAE, state means and HR-only / +sleep-HRV / +night-context ablations. Insufficient folds are reported, not silently treated as success. Agreement with a digitized curve does not establish physiological validity. A synthetic reference generated by this same model can legitimately fit almost perfectly; that is an implementation check, not real-world accuracy.

## Limitations

WHOOP's algorithm is proprietary. This is an independent approximation of HR/HRV versus personal baselines with activity-aware masking, **not an exact reproduction of WHOOP**. Sleep-only HRV makes awake scores less specific: caffeine, heat, posture and illness can all elevate HR. Around five days of data means low-confidence baselines. Default weights and logistic parameters are starting points, not clinically established parameters. Scores are wellness estimates, not medical measurements or diagnoses.

## Synthetic verification

```powershell
python -m pytest -c stressmon/pytest.ini stressmon/tests -q
```

Tests generate exports in temporary directories; they never open your real Takeout. They check timezone selection, data-quality rejection, masked runs, scored walks, smoothing boundaries, causal baselines, restricted columns, calibration and CLI output dimensions.
