"""Detect today's completed main sleep and freeze its inputs once per day."""
import asyncio
from datetime import timedelta

from health_read_store import read_range
from sleep_heart_rate import select_sleep
from sleep_rhr import calculate_sleep_rhr


async def save_cached_sleep_rhr(client, today, now, epoch):
    """One-time conversion for an already logged sleep; no remote requests."""
    store, account = client.store, client.account_key
    if await asyncio.to_thread(store.sleep_rhr_saved, account, today):
        return False
    query = read_range(f'sleep.interval.civil_end_time >= "{today}" AND sleep.interval.civil_end_time < "{today + timedelta(days=1)}"')
    points = await asyncio.to_thread(store.local_read, account, 'sleep', query, False)
    sleep_id = await asyncio.to_thread(store.saved_sleep_id, account, today)
    night = select_sleep(points, today, sleep_id, now=now)
    if night is None:
        return False
    interval = night['sleep']['interval']
    query = read_range(f'heart_rate.sample_time.physical_time >= "{interval["startTime"]}" AND heart_rate.sample_time.physical_time < "{interval["endTime"]}"')
    readings = await asyncio.to_thread(store.local_read, account, 'heart-rate', query)
    result = calculate_sleep_rhr(night, readings)
    await asyncio.to_thread(store.save_sleep_rhr, account, today, night['name'], result, epoch)
    await _persist_normalized_rhr(client, today, night['name'], result)
    client._invalidate_calculations()
    return True


async def sync_sleep_day(client, today, now, epoch):
    store, account = client.store, client.account_key
    if await asyncio.to_thread(store.sleep_day_saved, account, today):
        return await save_cached_sleep_rhr(client, today, now, epoch)
    query = read_range(f'sleep.interval.civil_end_time >= "{today}" AND sleep.interval.civil_end_time < "{today + timedelta(days=1)}"')
    points = await client._fetch_points('sleep', query.expression(query.start, query.end), reconcile=False)
    ready = [p for p in points if p.get('sleep', {}).get('metadata', {}).get('processed') is not False
             and p.get('sleep', {}).get('summary', {}).get('minutesAsleep') is not None]
    night = select_sleep(ready, today, now=now)
    if night is None:
        return False  # No daily lock until a completed main sleep is recognised.

    requests = []
    for kind, field in (
        ('daily-heart-rate-variability', 'daily_heart_rate_variability.date'),
        ('daily-respiratory-rate', 'daily_respiratory_rate.date'),
        ('daily-sleep-temperature-derivations', 'daily_sleep_temperature_derivations.date'),
    ):
        requests.append((kind, read_range(f'{field} >= "{today}" AND {field} < "{today + timedelta(days=1)}"')))
    interval = night['sleep']['interval']
    for kind, field in (('heart-rate', 'heart_rate'), ('heart-rate-variability', 'heart_rate_variability')):
        sample_query = read_range(f'{field}.sample_time.physical_time >= "{interval["startTime"]}" AND {field}.sample_time.physical_time < "{interval["endTime"]}"')
        # Reuse any already-stored HR coverage; fetch only gaps within this sleep.
        _, missing = await asyncio.to_thread(store.range_read, account, kind, sample_query, True, now=0)
        for start, end in missing:
            requests.append((kind, type(sample_query)(sample_query.field, start, end)))
    values = await asyncio.gather(*(client._fetch_points(kind, q.expression(q.start, q.end), reconcile=True)
                                   for kind, q in requests))
    # Save both forms because sleep-stage and summary consumers use different modes.
    for reconciled in (False, True):
        if not await asyncio.to_thread(store.range_write, account, 'sleep', query, reconciled, points, epoch=epoch):
            raise ValueError('Unsupported sleep schema; day remains unlocked for retry')
    for (kind, q), payload in zip(requests, values):
        if not await asyncio.to_thread(store.range_write, account, kind, q, True, payload, epoch=epoch):
            raise ValueError('Unsupported sleep measurement schema; day remains unlocked for retry')
    # Empty optional measurements are frozen too, as requested; no later daily retry.
    sample_query = read_range(f'heart_rate.sample_time.physical_time >= "{interval["startTime"]}" AND heart_rate.sample_time.physical_time < "{interval["endTime"]}"')
    readings = await asyncio.to_thread(store.local_read, account, 'heart-rate', sample_query)
    result = calculate_sleep_rhr(night, readings)
    await asyncio.to_thread(store.finish_sleep_day, account, today, night['name'], epoch, result)
    await _persist_normalized_rhr(client, today, night['name'], result)
    client._invalidate_calculations()
    return True


async def _persist_normalized_rhr(client, day, sleep_id, result):
    if getattr(client, 'database', None) is not None:
        from health_results import Results
        await asyncio.to_thread(Results(client.database, client.db_account['user_id'], day).sleeping_hr,
                                day, sleep_id, result)
