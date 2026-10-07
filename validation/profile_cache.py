"""Offline profiling of stored reads; never downloads health data."""
import asyncio
import cProfile
from datetime import datetime, timezone
import io
from pathlib import Path
import pstats
import sys
import time
import tempfile
import sqlite3
from contextlib import closing
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from google_health_client import GoogleHealthClient
from health_read_store import HealthReadStore
from main import _compute_real_strain, _compute_connected_recovery

class OfflineStore(HealthReadStore):
    def range_read(self, *args, **kwargs):
        return super().range_read(*args, **{**kwargs, 'now': 0})
    def exact_read(self, *args, **kwargs):
        return super().exact_read(*args, **{**kwargs, 'now': 0})

async def run():
    directory = tempfile.TemporaryDirectory()
    source = Path(__file__).resolve().parents[1] / 'backend/data/health_cache.sqlite3'
    path = Path(directory.name) / 'profile.sqlite3'
    with closing(sqlite3.connect(source)) as original, closing(sqlite3.connect(path)) as copy:
        original.backup(copy)
    store = OfflineStore(path)
    with store.connection() as conn:
        row = conn.execute('SELECT account FROM read_slices ORDER BY fetched DESC LIMIT 1').fetchone()
    client = GoogleHealthClient('offline', cache=True, account_id='offline', store=store)
    client.account_key = row[0]
    client.strain_timezone = ZoneInfo('Asia/Calcutta')
    client.strain_sex, client.strain_sex_defaulted = 'm', True
    async def no_network(*args, **kwargs):
        raise RuntimeError('Requested range is not stored; offline benchmark stopped')
    client._fetch_points = no_network
    today = datetime.now(client.strain_timezone).date()
    if '--timing' in sys.argv:
        for attempt in range(2):
            if attempt:
                from google_health_client import _point_cache
                from strain_service import _daily_cache
                _point_cache.clear()
                _daily_cache.clear()
                client.store = OfflineStore(path)
            started = time.perf_counter()
            await asyncio.gather(_compute_real_strain(client, today, 22),
                                 _compute_connected_recovery(client, today, 22))
            print(f'Stored Strain + Recovery, pass {attempt + 1}: {time.perf_counter() - started:.3f}s', flush=True)
        return
    for label, function in [('strain', _compute_real_strain), ('recovery', _compute_connected_recovery)]:
        profiler = cProfile.Profile()
        profiler.enable()
        await function(client, today, 22)
        profiler.disable()
        output = io.StringIO()
        pstats.Stats(profiler, stream=output).sort_stats('cumtime').print_stats(18)
        print(label, output.getvalue())

asyncio.run(run())
