"""Serve durable page results immediately; refresh stale snapshots on demand."""
import asyncio
from datetime import datetime, timezone
import logging
import time

from fastapi.encoders import jsonable_encoder
from health_read_store import CacheInvalidated
from read_metrics import count, read_metrics

FRESH_SECONDS = 120
_jobs = {}


async def cached_page_result(client, key, path, response, compute):
    store, account = client.store, client.account_key
    snapshot = await asyncio.to_thread(store.snapshot_read, account, key)
    job_key = (asyncio.get_running_loop(), account, key)

    async def rebuild(background):
        context = read_metrics.set({}) if background else None
        try:
            epoch = await asyncio.to_thread(store.epoch, account)
            value = jsonable_encoder(await compute())
            await asyncio.to_thread(store.snapshot_write, account, key, value, epoch)
            return value
        finally:
            if context is not None:
                read_metrics.reset(context)

    def complete(task):
        if _jobs.get(job_key) is task:
            _jobs.pop(job_key, None)
        if not task.cancelled() and task.exception() is not None:
            logging.getLogger('uvicorn.error').warning('Page refresh failed for %s (%s)', path, type(task.exception()).__name__)

    if snapshot:
        updated, value = snapshot
        stale = time.time() - updated >= FRESH_SECONDS
        response.headers['X-Data-Updated-At'] = datetime.fromtimestamp(updated, timezone.utc).isoformat()
        response.headers['X-Data-Cache'] = 'stale' if stale else 'hit'
        count('snapshot_hits')
        if stale and job_key not in _jobs:
            task = asyncio.create_task(rebuild(True))
            _jobs[job_key] = task
            task.add_done_callback(complete)
        return value
    response.headers['X-Data-Cache'] = 'miss'
    if job_key not in _jobs:
        task = asyncio.create_task(rebuild(False))
        _jobs[job_key] = task
        task.add_done_callback(complete)
    try:
        return await asyncio.shield(_jobs[job_key])
    except CacheInvalidated:
        # A refresh won the race. Never expose the old snapshot as refreshed.
        return await compute()
