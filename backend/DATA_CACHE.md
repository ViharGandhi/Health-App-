# Dynamic activity sync and persistent storage

## Heart-rate retention

Only recognized main-sleep HR traces are stored. Daytime samples are used in
memory for calculations, then discarded. Each account/date has one row in
`daily_intraday_hr` containing the raw-sample mean, count, coverage end and
update time. Foreground sync fetches midnight-to-now on each eligible refresh,
replacing this row so retries, overlapping reads and provider corrections do
not double-count. A shorter sleep-only range cannot replace a longer daily
summary. The awake baseline remains a separate sleep/exercise-excluded mean;
its sample array is no longer persisted.

Before today's downloads, sync completes yesterday if no finalized result exists
for the current profile/configuration: fetch its sleep/nightly vitals, full-day
HR, workouts and steps, calculate Strain from individual HR readings, then save
the calculated score, load, zones and workout summaries. Raw daytime readings
are discarded. Finalized results in `calculated_days` use the
`finalized-strain:` prefix and survive ordinary cache invalidation and restart.
Profile or algorithm/configuration changes use a different key. Empty/missing
HR never becomes an invented zero and remains retryable. Today's Strain is
recalculated from each fresh midnight-to-now read. Sleep need uses yesterday's
saved full-day Strain, and a previously frozen missing-score page is rebuilt
when that dependency is repaired.

Detailed HR pages are excluded from normalized `raw_payloads`, and daytime
traces are excluded from presentation snapshots. Current-day readings may
remain in process memory for 15 minutes. After a restart, detailed daytime
history is unavailable until a sync downloads it again; historical calculations
retain their saved results, but raw daytime inputs cannot be replayed offline.
`/api/health/heart-rate` also returns `daily_average_bpm` and `daily_sample_count`.

Run `python backend/compact_heart_rate.py` with the backend stopped to summarize
existing HR before deleting daytime observations and redundant raw copies.
The migration preserves main-sleep traces and calculated results, is repeatable,
and compacts both SQLite files to reclaim space.

Home entry and returning/focusing the same Home tab submit a visit
check. A durable per-account qualifying Home-visit timestamp gates forced syncs:
the first visit qualifies; subsequent visits qualify only after 15 minutes. A
skipped visit leaves this timestamp and the automatic timer unchanged. Browser
reloads (normal or hard) bypass this visit gate and force one sync per document,
using a separate request ID. Reloads retain the saved Sleep/Recovery day lock.
The rule
survives reloads, new tabs and backend restarts. Automatic syncs do not change
the Home-visit timestamp. Manual Sync now remains independently available.

The root scheduler automatically checks 15 minutes after successful completion.
Navigating to other pages keeps that schedule; hidden tabs pause and catch up
when visible. Home returns during automatic work queue one visit check. Failed
checks retry after 30 seconds. The backend serializes work per account so
overlapping checks share already-completed work. Last synced displays the durable
successful completion timestamp in the viewer's local timezone; failed/skipped
attempts never advance it.

## Account ownership across reconnects

Google Health's stable `healthUserId` identifies connected data. Email addresses
are profile metadata and access tokens are temporary credentials; neither may
select a connected database partition. OAuth validates the Health identity and
registers its permanent mapping in `health_account_aliases` before completing
login. Even an empty account is pinned immediately. The mapping is persisted
across token refreshes, reconnects, changed email addresses and backend restarts.
First registration is serialized in a database transaction.

An older email-keyed cache can be adopted once only when its provider resource
names prove the same Health account owns the data. Mixed-owner caches and
partitions already registered to another identity are excluded. An existing
mapping is never reassigned based on which partition has more data. Connected
sessions missing a Health identity must reconnect instead of silently opening
an email- or token-keyed partition.

## Remote data scope

Only the dedicated sync endpoint downloads Google data:

- Previous-day finalization is a separate operation for explicit one-time work.
  Foreground sync does not check for or download yesterday's missing Strain inputs.
- Heart rate: physical timestamps in `[today's local midnight, request time)`.
  Replace today's single average; retain detailed samples only during main sleep.
- Activities: today's sessions, using the supported `civil_start_time` filter.
  This small check catches workouts started before the HR cursor but logged later.
- Steps: today's updated daily total, rather than thousands of raw step samples.
- Sleep: check sessions ending today until a completed, processed main sleep is
  recognised. Then download today's HRV, respiratory rate and sleep
  temperature summaries, plus missing HR/RMSSD coverage only inside that sleep.
  Persist a per-account/day lock after all downloads and writes succeed. Subsequent
  syncs, including forced app openings and server restarts, skip sleep and these
  measurements for that day. Empty optional metrics are frozen too: they remain
  unavailable if Google publishes them later. A new local day starts a new check.
  RHR is calculated once from stored HR readings in LIGHT/DEEP/REM stages using
  nearest-sample time weighting, excluding awake stages and long gaps. Its daily
  value and provenance are immutable in `sleep_rhr`; provider daily RHR is never
  fetched. All RHR trends and baselines use these saved values.

Today's HR refresh starts at today's local midnight. The activity checkpoint
persists across backend restarts.
The cursor is the successfully processed upper bound, not the latest reading's
timestamp, so successful empty windows are not repeatedly queried.
All three downloads finish before storage updates begin; failures never advance
the checkpoint. Steps and the final cursor are committed after Strain succeeds
and any detected sleep's standard views have been prepared successfully.
Midnight-to-now HR reads include readings uploaded late and provider corrections.

## Page reads and calculations

Connected Sleep scores use nightly HRV and saved asleep-only RHR. Each baseline
is the arithmetic mean of valid daily readings from the prior 60 calendar days,
excluding the scored night. Available history is used immediately, even with
fewer than seven or 60 readings; missing days are not filled. RHR references
retain the same calculation method. The response records the baseline values,
window and reading counts. A missing reference remains absent rather than using
a hardcoded HRV/HR baseline. The personal RHR mean is not offset by four bpm or
used as an assumed waking heart rate for the HR-dip component. New completed
main sleeps save daily inputs and prepare that day's scores with the new means.

Connected page clients are `stored_only`: they use persisted observations and
daily totals even after old cache TTLs, and never fall back to a Google download.
Sleep and Recovery pages never download remotely. Their saved inputs are updated
only when dynamic sync recognises that day's completed main sleep. Prior history
is reused without a historical backfill. Strain uses stored sleep/RHR inputs
where available and its existing documented calibration behavior otherwise.

New HR/activity inputs invalidate affected daily Strain results. Empty HR reads
and unchanged activity lists retain prior results. Strain is recalculated from
the current sync's in-memory readings; no network calls occur inside that calculation. Heavy daily
calculations run outside the API event loop. Browser sync completion refreshes
the Home Strain and Strain analytics displays. A separate sleep-completion event
refreshes Home/Recovery, Sleep, Consistency, Efficiency, Stress and sleep detail
views from the database, including a page opened while the sync was running.

When a completed main sleep is saved, the sync prepares Sleep performance, need,
analytics, consistency scores/trends, efficiency, stages, overnight HR, Stress,
Recovery and Recovery analytics for the standard supported ranges. It then marks
the day prepared. A failed calculation leaves this marker unset and retries the
preparation using saved inputs, without downloading sleep measurements again.
Days saved by an older version are prepared on the next sync without refetching
their sleep inputs. Missing baseline data stays explicitly unavailable.

Prepared Sleep/Recovery responses are frozen for the day; their 15-minute TTL
does not trigger any recalculation. Additional custom date/range combinations
are calculated from stored inputs on first request and then frozen too.
Other complete page responses are persisted and fresh for 15 minutes. Older saved
responses return immediately while one background task rebuilds them locally.
All snapshot keys include the saved-sleep revision; Strain/dashboard keys also
include the dynamic revision, so a completed sync
cannot leave the previous Strain response cached. Auth, account, date/range,
age, timezone, sex and configuration are checked/scoped before serving results.
Errors never replace a successful saved response. `X-Data-Cache`,
`X-Data-Updated-At`, `Server-Timing` and `X-Google-Requests` aid verification.

## Persistence and deployment

SQLite defaults to `backend/data/health_cache.sqlite3`; `HEALTH_DATA_DB_PATH` can
place it on a persistent disk. WAL and indexed timestamps support range reads.
Raw observations, computed daily results, page responses, steps, cursor and
session receipts persist. Browser response memory lasts two minutes and clears
after a full reload or successful sync; it is not the durable storage layer.
No tokens or signed cookies are stored in this database. Account partitions use
the signed Health user ID, with signed email as a fallback for older sessions.

Connection's **Sync now** requests the same restricted dynamic sync, then uses
client navigation to Home; it does not erase Sleep/Recovery or reload the app
into a second forced sync. The legacy `/api/data/refresh` remains an explicit
cache-reset endpoint; normal navigation and the Sync now button do not call it.
There are no webhooks, cron jobs, or syncs while the browser is closed.
