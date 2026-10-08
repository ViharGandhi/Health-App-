"""Foreground sync: activity deltas plus a once-per-day recognised sleep."""
import asyncio
import json
from datetime import datetime, time, timezone

from health_read_store import read_range
from strain_service import load_strain_days
from sleep_sync import sync_sleep_day

INTERVAL_SECONDS = 900
_locks = {}


def utc_text(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


async def sync_dynamic(client, session, force=False, *, now=None, age=None, config=None, prepare_sleep=None, home_visit=False):
    supplied_now = now is not None
    now = now or datetime.now(timezone.utc)
    received = now.timestamp()
    store, account = client.store, client.account_key
    lock = _locks.setdefault((asyncio.get_running_loop(), account), asyncio.Lock())
    async with lock:
        state = await asyncio.to_thread(store.dynamic_status, account, session)
        home_eligible = home_visit and (state['home_visit'] is None or received - state['home_visit'] >= INTERVAL_SECONDS)
        first_visit = home_eligible if home_visit else force and not state['session_seen']
        concurrent_completed = state['completed'] is not None and state['completed'] >= received
        if concurrent_completed or (not first_visit and state['completed'] is not None and received - state['completed'] < INTERVAL_SECONDS):
            if home_eligible:
                await asyncio.to_thread(store.remember_home_visit, account, received)
            await asyncio.to_thread(store.remember_session, account, session)
            return {**state, 'synced': False, 'data_updated': concurrent_completed,
                    'sleep_updated': concurrent_completed and state.get('sleep_completed') is not None
                    and state['sleep_completed'] >= received}
        tz = client.strain_timezone
        today = now.astimezone(tz).date()
        midnight = datetime.combine(today, time.min, tzinfo=tz)
        # No old backfill: the first checkpoint bootstraps today's readings only.
        start = datetime.fromisoformat(state['cursor'].replace('Z', '+00:00')) if state['cursor'] else midnight
        if start >= now:
            return {**state, 'synced': False}
        heart_query = read_range(f'heart_rate.sample_time.physical_time >= "{utc_text(start)}" AND heart_rate.sample_time.physical_time < "{utc_text(now)}"')
        # Google supports exercise civil start filters, not an upload-time delta.
        # Today's small session list catches workouts started before the cursor.
        activity_query = read_range(f'exercise.interval.civil_start_time >= "{today}" AND exercise.interval.civil_start_time < "{now.astimezone(tz).replace(tzinfo=None).isoformat()}"')
        epoch = await asyncio.to_thread(store.epoch, account)
        heart, activities, steps = await asyncio.gather(
            client._fetch_points('heart-rate', heart_query.expression(heart_query.start, heart_query.end), reconcile=True),
            client._fetch_points('exercise', activity_query.expression(activity_query.start, activity_query.end), reconcile=True),
            client._fetch_daily_steps(today, today),
        )
        # Stage all remote reads first. Failed downloads never advance the cursor.
        previous = await asyncio.to_thread(store.local_read, account, 'exercise', activity_query)
        activity_changed = {json.dumps(p, sort_keys=True) for p in previous} != {json.dumps(p, sort_keys=True) for p in activities}
        stored_heart = await asyncio.to_thread(store.range_write, account, 'heart-rate', heart_query, True, heart, epoch=epoch, invalidate=bool(heart))
        stored_activity = await asyncio.to_thread(store.range_write, account, 'exercise', activity_query, True, activities, epoch=epoch, invalidate=activity_changed)
        if not stored_heart or not stored_activity:
            raise ValueError('Unsupported dynamic reading schema; checkpoint retained')
        sleep_updated = await sync_sleep_day(client, today, now, epoch)
        client.stored_only = True
        options = {'config': config} if config is not None else {}
        await load_strain_days(client, today, today, now, age, **options)
        if prepare_sleep is not None and await asyncio.to_thread(store.sleep_day_saved, account, today):
            if not await asyncio.to_thread(store.sleep_day_prepared, account, today):
                await prepare_sleep()
                await asyncio.to_thread(store.finish_sleep_preparation, account, today, epoch)
                sleep_updated = True
        await asyncio.to_thread(store.dynamic_finish, account, session, utc_text(now), steps,
                                completed=received if supplied_now else None)
        if home_eligible:
            await asyncio.to_thread(store.remember_home_visit, account, received)
        result = await asyncio.to_thread(store.dynamic_status, account, session)
        return {**result, 'synced': True, 'sleep_updated': sleep_updated, 'heart_readings': len(heart), 'activities': len(activities)}
