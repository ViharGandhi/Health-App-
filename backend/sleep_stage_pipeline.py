"""Fetch -> normalize -> persist stage stats -> recompute personal ranges."""

from datetime import date, datetime, timedelta, timezone

from sleep_stage_ranges import DEFAULT_CONFIG, adapt_google_sleep, stage_stats


async def sync_stage_ranges(client, user_id, store, start: date, end: date, config=DEFAULT_CONFIG):
    # First sync retrieves complete history, so missing calendar days cannot shrink
    # the previous-N-qualifying-night baseline. Subsequent jobs refresh late syncs.
    fetch_start = min(start, end - timedelta(days=9)) if store.has_sessions(user_id) else None
    points = await client.get_sleep_stage_points(fetch_start, end)
    observations = []
    for point in points:
        platform = point.get("dataSource", {}).get("platform")
        if platform and platform != "FITBIT":
            continue  # Do not pool another platform's stage classifications with Fitbit.
        night = adapt_google_sleep(point)
        if not (night.night_date <= end and (fetch_start is None or night.night_date >= fetch_start)):
            continue
        if night.end_utc > datetime.now(timezone.utc):
            continue
        stats, state = stage_stats(night, config)
        observations.append((night, stats, state))
    store.sync(user_id, observations, fetch_start, end, config)
    return store.results(user_id, start, end)


async def run_stage_jobs(client, user_id, store, config=DEFAULT_CONFIG):
    """One worker pass; unfinished stages and transient failures stay queued."""
    for key, start, end, generation in store.jobs(user_id):
        try:
            results = await sync_stage_ranges(client, user_id, store, date.fromisoformat(start), date.fromisoformat(end), config)
        except Exception:
            store.finish_job(user_id, key, generation, retry=True)
            raise
        store.finish_job(user_id, key, generation, retry=any(r["status"] == "stages_pending" for r in results))
