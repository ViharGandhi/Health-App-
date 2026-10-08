# Dynamic activity sync and persistent storage

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

## Remote data scope

Only the dedicated sync endpoint downloads Google data:

- Heart rate: physical timestamps in `[last successful cursor, request time)`.
  No overlap, historical range refresh, or monthly backfill is performed.
- Activities: today's sessions, using the supported `civil_start_time` filter.
  This small check catches workouts started before the HR cursor but logged later.
- Steps: today's updated daily total, rather than thousands of raw step samples.
- Sleep: check sessions ending today until a completed, processed main sleep is
  recognised. Then download today's HRV, RHR, respiratory rate and sleep
  temperature summaries, plus missing HR/RMSSD coverage only inside that sleep.
  Persist a per-account/day lock after all downloads and writes succeed. Subsequent
  syncs, including forced app openings and server restarts, skip sleep and these
  measurements for that day. Empty optional metrics are frozen too: they remain
  unavailable if Google publishes them later. A new local day starts a new check.

The first ever dynamic sync starts at today's local midnight because no dynamic
checkpoint exists yet. Afterward, the checkpoint persists across backend restarts.
The cursor is the successfully processed upper bound, not the latest reading's
timestamp, so successful empty windows are not repeatedly queried.
All three downloads finish before storage updates begin; failures never advance
the checkpoint. Steps and the final cursor are committed after Strain succeeds
and any detected sleep's standard views have been prepared successfully.
Strict timestamp deltas can miss older readings uploaded late; no automatic
overlap or reconciliation is added in this stage, as requested.

## Page reads and calculations

Connected page clients are `stored_only`: they use persisted observations and
daily totals even after old cache TTLs, and never fall back to a Google download.
Sleep and Recovery pages never download remotely. Their saved inputs are updated
only when dynamic sync recognises that day's completed main sleep. Prior history
is reused without a historical backfill. Strain uses stored sleep/RHR inputs
where available and its existing documented calibration behavior otherwise.

New HR/activity inputs invalidate affected daily Strain results. Empty HR deltas
and unchanged activity lists retain prior results. Strain is recalculated from
stored readings; no network calls occur inside that calculation. Heavy daily
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
