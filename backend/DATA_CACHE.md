# Stored Google Health reads

All connected data routes share `health_read_store.py`. The SQLite file defaults
to `backend/data/health_cache.sqlite3`; override with `HEALTH_DATA_DB_PATH` to place
it on persistent storage. SQLite data and journal files are ignored by Git. No
OAuth tokens or signed session cookies are written into this database.

The store partitions reads by signed-in account, data type, filter field, and
raw/reconciled mode. Parsed time/date ranges carry authoritative coverage,
including successful empty responses. Overlapping requests reuse stored slices
and fetch only gaps. Newer slices replace corrections and remove readings that
disappeared. The write happens only after every Google page succeeds.
Observation timestamps are indexed in SQLite, so subset reads do not reparse and
scan an entire heart-rate snapshot. Existing stored snapshots are indexed once
when the backend first opens the upgraded database.

Recent data (the last three UTC days and future/padded ranges) expires after
15 minutes. Older coverage expires after 24 hours. When recent coverage expires,
the next request fetches only those expired slices, leaving fresh older coverage
in place. Unsupported filter/point schemas and step rollups use an exact-query
15-minute cache instead of assuming range coverage. Google request pacing and
permission checks are retained.

Memory holds identical raw reads for 60 seconds and browser responses for two
minutes. Frontend keys include endpoint, range, date, age, and timezone; account
changes, disconnects, auth failures and explicit refreshes invalidate browser
responses. New stored readings invalidate dependent daily Strain calculations.
Identical refetches update freshness without discarding saved Strain results or
rewriting the timestamp index. Changed readings invalidate dependent results.
Account identity is stable across token refreshes. Existing sessions without a
Health user ID use their signed Google email until the next login establishes the
Health identity.

Calculated daily Strain results also persist in SQLite, keyed by account, date,
age, sex, timezone, configuration and algorithm version. Home, Strain analytics,
Sleep Need and Recovery check these before loading raw heart-rate history.
Only missing/expired days load raw inputs. Today's calculation expires after one
minute, other recent days after 15 minutes, and older days after 24 hours.
Corrections invalidate affected dates (including adjacent wake-based windows and
RHR baseline dependencies); explicit refresh invalidates all calculated days.
Version checks prevent a calculation in flight from storing results after a
correction. Heavy calculations run outside the API event loop.

Health overview no longer fetches intraday heart-rate history or polls every
minute. Its central reading is the stored daily RHR summary. Sleep heart-rate
charts and sleep stress retain the readings required for their calculations.

Complete connected API page responses also persist in `page_snapshots`, keyed
by account, endpoint, selected date/range, age, sex, timezone and configuration.
A browser reload reads this small response instead of rerunning each pipeline.
Responses are fresh for two minutes. Older responses (up to 24 hours, for the
same requested date) return immediately while one on-demand background task
rebuilds them. The updated response is used on a later read. No scheduler or
webhook is introduced. A first visit without a snapshot still awaits computation.
`X-Data-Cache` reports `hit`, `stale`, or `miss`; `X-Data-Updated-At` gives the
saved response timestamp. Explicit Sync now invalidates all page snapshots;
epoch checks prevent an earlier refresh task from repopulating them.
Authentication is checked before a snapshot is served; public/demo requests
without a signed account identity bypass this cache. Failed rebuilds do not
replace the last successful response.

Connect shows the last successful fetch and a **Sync now** button. This expires
recent stored coverage and clears memory results, then opens Home to fetch fresh
data. It does not force Fitbit to upload from the wearable. Refresh epochs keep
in-flight older reads from overwriting an explicit refresh.

This stage is on-demand storage and caching. It does not add scheduled syncing,
webhook registrations, or automatic background ingestion. First visits to uncached
ranges and visits after expiration still need Google. Cached data survives backend
restarts, but must have a persistent disk after deployment.

Backend data responses expose `Server-Timing` and `X-Google-Requests` and log total
endpoint time plus database/memory hits. The Google timing sums individual calls,
so it can exceed wall-clock time when calls run concurrently. Timing logs contain
paths and counts, not tokens, user IDs, query parameters or measurement values.
