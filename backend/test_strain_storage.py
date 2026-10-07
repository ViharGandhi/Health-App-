"""Durable daily results must bypass raw history and remain correction-aware."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

from main import STRAIN_CONFIG
from google_health_client import GoogleHealthClient
from health_read_store import HealthReadStore, read_range
from strain_service import demo_inputs, load_strain_days


def test_restart_reuses_calculated_days_without_loading_raw_samples():
    async def check():
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'health.sqlite3'
            client = GoogleHealthClient('first', cache=True, account_id='user', store=HealthReadStore(path))
            day = date(2026, 10, 1)
            now = datetime(2026, 10, 7, tzinfo=timezone.utc)
            inputs, _ = demo_inputs(day, day, timezone.utc)
            with patch('strain_service.fetch_strain_inputs', AsyncMock(return_value=inputs)) as fetch:
                original = await load_strain_days(client, day, day, now, 22, STRAIN_CONFIG)
                restarted = GoogleHealthClient('rotated', cache=True, account_id='user', store=HealthReadStore(path))
                restored = await load_strain_days(restarted, day, day, now, 22, STRAIN_CONFIG)
                assert restored == original
                assert fetch.await_count == 1
                await load_strain_days(restarted, day, day, now, 30, STRAIN_CONFIG)
                assert fetch.await_count == 2
                restarted.store.expire_recent(restarted.account_key)
                await load_strain_days(restarted, day, day, now, 22, STRAIN_CONFIG)
                assert fetch.await_count == 3
    asyncio.run(check())


def test_simultaneous_day_requests_calculate_only_once():
    async def check():
        with tempfile.TemporaryDirectory() as directory:
            client = GoogleHealthClient('token', cache=True, account_id='user', store=HealthReadStore(Path(directory) / 'health.sqlite3'))
            day = date(2026, 10, 1)
            inputs, _ = demo_inputs(day, day, timezone.utc)
            with patch('strain_service.fetch_strain_inputs', AsyncMock(return_value=inputs)) as fetch:
                args = (client, day, day, datetime(2026, 10, 7, tzinfo=timezone.utc), 22)
                first, second = await asyncio.gather(load_strain_days(*args), load_strain_days(*args))
                assert first == second
                fetch.assert_awaited_once()
    asyncio.run(check())


def test_corrections_expire_affected_scores_and_reject_late_calculation():
    with tempfile.TemporaryDirectory() as directory:
        store = HealthReadStore(Path(directory) / 'health.sqlite3')
        entries = [('profile:2026-09-01', 9999999999, '{}'), ('profile:2026-10-06', 9999999999, '{}')]
        version = store.calculation_version('user')
        assert store.days_write('user', entries, version)
        query = read_range('heart_rate.sample_time.physical_time >= "2026-10-06T00:00:00Z" AND heart_rate.sample_time.physical_time < "2026-10-07T00:00:00Z"')
        store.range_write('user', 'heart-rate', query, True, [])
        assert store.days_read('user', [key for key, _, _ in entries]) == {'profile:2026-09-01': '{}'}
        assert not store.days_write('user', entries, version)


def test_identical_refetch_keeps_daily_results():
    with tempfile.TemporaryDirectory() as directory:
        store = HealthReadStore(Path(directory) / 'health.sqlite3')
        query = read_range('heart_rate.sample_time.physical_time >= "2026-10-06T00:00:00Z" AND heart_rate.sample_time.physical_time < "2026-10-07T00:00:00Z"')
        store.range_write('user', 'heart-rate', query, True, [])
        version = store.calculation_version('user')
        entries = [('profile:2026-10-06', 9999999999, '{}')]
        store.days_write('user', entries, version)
        store.range_write('user', 'heart-rate', query, True, [])
        assert store.calculation_version('user') == version
        assert store.days_read('user', ['profile:2026-10-06']) == {'profile:2026-10-06': '{}'}
