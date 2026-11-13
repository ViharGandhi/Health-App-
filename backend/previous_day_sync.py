"""Finalize yesterday from fresh samples before calculating today's sleep."""
import asyncio
from datetime import datetime, time, timedelta, timezone
import json

from health_read_store import read_range
from sleep_sync import sync_sleep_day
from strain import StrainConfig
from strain_service import calculate_days, fetch_strain_inputs, finalized_key, _encode_day


async def sync_previous_day(client, today, now, age, config=None):
    config = config or StrainConfig()
    store, account = client.store, client.account_key
    day = today - timedelta(days=1)
    key = finalized_key(client, day, age, config)
    saved = await asyncio.to_thread(store.days_read, account, [key])
    if key in saved:
        return False
    tz = client.strain_timezone
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(today, time.min, tzinfo=tz)
    utc = lambda stamp: stamp.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    heart_query = read_range(f'heart_rate.sample_time.physical_time >= "{utc(start)}" AND heart_rate.sample_time.physical_time < "{utc(end)}"')
    # Include workouts crossing into yesterday from the preceding date.
    exercise_query = read_range(f'exercise.interval.civil_start_time >= "{day - timedelta(days=1)}" AND exercise.interval.civil_start_time < "{today}"')
    epoch = await asyncio.to_thread(store.epoch, account)
    # Sleep, nightly vitals and asleep-stage HR remain stored under their normal policy.
    await sync_sleep_day(client, day, now, epoch)
    heart, exercises, steps = await asyncio.gather(
        client._fetch_points('heart-rate', heart_query.expression(heart_query.start, heart_query.end), reconcile=True),
        client._fetch_points('exercise', exercise_query.expression(exercise_query.start, exercise_query.end), reconcile=True),
        client._fetch_daily_steps(day, day))
    for kind, query, points in (('heart-rate', heart_query, heart), ('exercise', exercise_query, exercises)):
        if not await asyncio.to_thread(store.range_write, account, kind, query, True, points, epoch=epoch):
            raise ValueError('Unsupported previous-day data; retry retained')
    await asyncio.to_thread(store.save_steps, account, steps)
    # HR is exposed only to this calculation in process memory.
    client.remember_intraday(heart)
    client.stored_only = True
    try:
        inputs = await fetch_strain_inputs(client, day, day)
        values = await asyncio.to_thread(calculate_days, day, day, now, tz, age,
            getattr(client, 'strain_sex', 'm'), getattr(client, 'strain_sex_defaulted', True), inputs, config,
            None, getattr(client, 'strain_hr_max', None))
        result = values[day]
        if result['strain'] is None or result['coverage'] <= 0:
            return False  # No fabricated zero; missing data can be retried next sync.
        result['_sessions'] = inputs[1]
        if getattr(client, 'database', None) is not None:
            from health_results import Results
            await asyncio.to_thread(Results(client.database, client.db_account['user_id'], day).strain, result, day)
        version = await asyncio.to_thread(store.calculation_version, account)
        if not await asyncio.to_thread(store.days_write, account,
                [(key, 253402300799, json.dumps(result, default=_encode_day))], version):
            raise ValueError('Previous-day inputs changed; retry retained')
        # Repair a page previously frozen while its sleep-need dependency was missing.
        await asyncio.to_thread(store.reset_sleep_preparation, account, today)
        return True
    finally:
        client.remember_intraday([])
