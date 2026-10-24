# Awake heart rate for sleep dip

Sleep date D uses the awake baseline for calendar date D-1. The calculation is
`(awake_mean - sleeping_hr) / awake_mean * 100`. The existing 0–25% dip-to-score
mapping and 18% sleep-score weight remain unchanged. Sleeping HR remains the
saved asleep-stage HR calculation.

`awake_heart_rate.py` downloads fresh raw reconciled HR and every page of exercise
and sleep sessions. It starts at the final wake time of the selected main sleep
on D-1 and ends at 22:00, exclusive. Every logged exercise interval and every
other sleep interval (including naps) is excluded. The mean is arithmetic over
valid raw BPM samples, never over the chart's 15-minute medians. Identical
timestamps count once; conflicting timestamps and invalid BPM are excluded.
Missing main sleep or missing readings leave the component unavailable.

The mean, sample count and exclusion metadata are stored by account, date and timezone in
`awake_heart_rate` in the existing health SQLite database. Recalculating replaces
the baseline and invalidates frozen Sleep, Home and Recovery snapshots. Raw awake
samples are used only in memory and discarded after calculation. The general
intraday mean is a separate daily summary and does not replace this filtered mean.

## Automatic collection

The backend lifespan starts `awake_hr_scheduler.py` for the personal account
configured in `backend/.env`:

```
GOOGLE_HEALTH_SESSION_COOKIE=<signed soma_session value>
AWAKE_HR_TIMEZONE=Asia/Calcutta
```

The scheduler wakes at 22:00 in that timezone, and checks for missed work on
startup and every five minutes. It repairs yesterday for today's score and,
after 22:00, saves today for tomorrow. Successful days are not downloaded again
unless explicitly recalculated. Failures/empty results retry every five minutes.
The backend and computer must remain running for collection at 22:00; after
downtime it catches up on startup. Provider upload lag can be repaired manually.
The cookie must identify the connected account and contain refresh credentials;
OAuth client credentials retain their original environment names.

## APIs

* `GET /api/health/awake-heart-rate?day=2026-10-14` returns a saved baseline and
  retained samples (default: yesterday).
* `POST /api/sleep/awake-heart-rate/recalculate?sleep_date=2026-10-15` freshly
  collects October 14, invalidates cached results and returns that baseline plus
  the recalculated October 15 sleep response. Default: today's sleep date.
* `GET /api/sleep` adds `waking_hr`, `waking_hr_date`,
  `waking_hr_sample_count` and `hr_dip_pct`.

These routes require the normal signed session cookie and honor
`X-User-Timezone`. The Sleep screen has a recalculation button for today's score.
Only recorded sleep and exercise can be excluded; missing device logs cannot be
inferred from high or low BPM alone.
