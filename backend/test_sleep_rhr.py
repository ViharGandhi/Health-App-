import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from google_health_client import GoogleHealthClient
from health_read_store import HealthReadStore, read_range
from health_trends import build_health_response
from sleep_rhr import METHOD, calculate_sleep_rhr
from sleep_sync import sync_sleep_day
from recovery_analytics import typical_ranges
from recovery_score import recovery_from_history


DAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 9, tzinfo=timezone.utc)


def night():
    def stage(start, end, kind):
        return {'startTime': f'{DAY}T{start}Z', 'endTime': f'{DAY}T{end}Z', 'type': kind}
    return {'name': 'sleep/main', 'sleep': {
        'interval': {'startTime': f'{DAY}T00:00:00Z', 'endTime': f'{DAY}T04:00:00Z',
                     'startUtcOffset': '0s', 'endUtcOffset': '0s'},
        'metadata': {'mainSleep': True, 'processed': True, 'stagesStatus': 'SUCCEEDED'},
        'type': 'STAGES', 'summary': {'minutesAsleep': 210},
        'stages': [stage('00:00:00', '01:00:00', 'LIGHT'),
                   stage('01:00:00', '01:30:00', 'AWAKE'),
                   stage('01:30:00', '02:30:00', 'DEEP'),
                   stage('02:30:00', '04:00:00', 'REM')]}}


def reading(seconds, bpm):
    return {'heartRate': {'sampleTime': {
        'physicalTime': (datetime.combine(DAY, datetime.min.time(), timezone.utc) + timedelta(seconds=seconds)).isoformat(),
        'utcOffset': '0s'}, 'beatsPerMinute': bpm}}


def test_irregular_cadence_is_time_weighted_and_awake_excluded():
    # Support: [8,11] at 40, [11,15] at 80, [15,19] at 100.
    # Large surrounding gaps cannot be counted as hours of measured sleep.
    result = calculate_sleep_rhr(night(), [reading(10, 40), reading(12, 80), reading(18, 100),
                                         reading(9, 40), reading(20, 100), reading(4000, 200)])
    assert result['covered_seconds'] < 180
    assert result['sample_count'] == 5
    assert result['asleep_seconds'] == 210 * 60
    assert result['method'] == METHOD
    # Independently computed nearest-sample cells, clipped at the 30s gap limit.
    assert result['value'] == pytest.approx((40*9.5 + 40*1.5 + 80*4 + 100*4 + 100*31) / 50)


def test_duplicates_and_invalid_samples_do_not_change_result():
    points = [reading(10, 60), reading(12, 70)]
    expected = calculate_sleep_rhr(night(), points)
    assert calculate_sleep_rhr(night(), points + points + [reading(13, True), reading(14, 'nan')]) == expected
    assert calculate_sleep_rhr(night(), [])['value'] is None


def test_short_main_sleep_can_still_have_rhr():
    point = night()
    point['sleep']['interval']['endTime'] = f'{DAY}T01:00:00Z'
    point['sleep']['stages'] = point['sleep']['stages'][:1]
    assert calculate_sleep_rhr(point, [reading(10, 64)])['value'] == 64


def test_sleep_sync_calculates_once_and_survives_refresh_and_restart(tmp_path):
    async def run():
        path = tmp_path / 'health.db'
        client = GoogleHealthClient('token', cache=True, account_id='user', store=HealthReadStore(path))
        calls = []
        async def fetch(kind, *args, **kwargs):
            calls.append(kind)
            assert kind != 'daily-resting-heart-rate'
            return [night()] if kind == 'sleep' else [reading(10, 64), reading(12, 66)] if kind == 'heart-rate' else []
        client._fetch_points = fetch
        assert await sync_sleep_day(client, DAY, NOW, 0)
        value = await client.get_resting_heart_rate(DAY)
        assert value is not None
        calls.clear()
        with patch('sleep_sync.calculate_sleep_rhr', side_effect=AssertionError('recalculation')):
            assert not await sync_sleep_day(client, DAY, NOW, 0)
            assert not calls
        client.store.expire_recent(client.account_key)
        restarted = GoogleHealthClient('token', cache=True, account_id='user', store=HealthReadStore(path))
        assert await restarted.get_resting_heart_rate(DAY) == value
        other = GoogleHealthClient('token', cache=True, account_id='other', store=client.store)
        assert await other.get_resting_heart_rate(DAY) is None
        history = await restarted.get_health_history(DAY, DAY, ('rhr',))
        assert history['rhr'][0]['method'] == METHOD
    asyncio.run(run())


def test_baseline_uses_only_saved_calculations_and_excludes_today(tmp_path):
    async def run():
        client = GoogleHealthClient('token', cache=True, account_id='user', store=HealthReadStore(tmp_path / 'health.db'))
        for offset in range(8):
            day = DAY - timedelta(days=offset)
            client.store.save_sleep_rhr(client.account_key, day, str(day), {'value': 100 if offset == 0 else 60 + offset}, 0)
        history = await client.get_health_history(DAY - timedelta(days=14), DAY, ('rhr',))
        result = build_health_response(history, [], DAY - timedelta(days=7), DAY, '1W', False)
        assert result.metrics['rhr'][-1].baseline == 64
        assert result.metrics['rhr'][-2].baseline is None
    asyncio.run(run())


def test_provider_rhr_is_never_requested_without_store():
    async def run():
        client = GoogleHealthClient('token')
        with patch.object(client, '_fetch_points', side_effect=AssertionError('provider RHR')):
            assert await client.get_resting_heart_rate(DAY) is None
    asyncio.run(run())


def test_existing_logged_sleep_is_converted_from_cache_once(tmp_path):
    async def run():
        client = GoogleHealthClient('token', cache=True, account_id='user', store=HealthReadStore(tmp_path / 'health.db'))
        sleep_query = read_range(f'sleep.interval.civil_end_time >= "{DAY}" AND sleep.interval.civil_end_time < "{DAY + timedelta(days=1)}"')
        hr_query = read_range(f'heart_rate.sample_time.physical_time >= "{DAY}T00:00:00Z" AND heart_rate.sample_time.physical_time < "{DAY}T04:00:00Z"')
        client.store.range_write(client.account_key, 'sleep', sleep_query, False, [night()])
        client.store.range_write(client.account_key, 'heart-rate', hr_query, True, [reading(10, 64), reading(12, 66)])
        client.store.finish_sleep_day(client.account_key, DAY, 'sleep/main', 0)
        with patch.object(client, '_fetch_points', side_effect=AssertionError('remote read')):
            assert await sync_sleep_day(client, DAY, NOW, 0)
            assert not await sync_sleep_day(client, DAY, NOW, 0)
        assert await client.get_resting_heart_rate(DAY) is not None
    asyncio.run(run())


def test_empty_calculation_stays_missing_and_does_not_retry(tmp_path):
    async def run():
        client = GoogleHealthClient('token', cache=True, account_id='user', store=HealthReadStore(tmp_path / 'health.db'))
        client.store.finish_sleep_day(client.account_key, DAY, 'sleep/main', 0, calculate_sleep_rhr(night(), []))
        with patch('sleep_sync.calculate_sleep_rhr', side_effect=AssertionError('recalculation')):
            assert not await sync_sleep_day(client, DAY, NOW, 0)
        assert await client.get_resting_heart_rate(DAY) is None
    asyncio.run(run())


def test_recovery_accepts_custom_method_and_excludes_other_methods():
    from test_recovery_score import reference_history, DAY as RECOVERY_DAY
    history = reference_history()
    for point in history['rhr']:
        point['method'] = METHOD
    result = recovery_from_history(history, RECOVERY_DAY)
    assert result.rhr_baseline_days == 60
    assert result.components['z_rhr'] is not None
    assert typical_ranges(history, RECOVERY_DAY)['rhr'] is not None
    for point in history['rhr']:
        if point['date'] != RECOVERY_DAY.isoformat():
            point['method'] = 'WITH_SLEEP'
    assert typical_ranges(history, RECOVERY_DAY)['rhr'] is None
