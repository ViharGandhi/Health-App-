import asyncio
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import pytest

from awake_heart_rate import calculate_awake_hr, collect_awake_hr, previous_awake_hr, read_baseline
from health_read_store import HealthReadStore
from sleepscore import SleepCalculator

DAY = date(2026, 10, 14)
TZ = ZoneInfo('Asia/Calcutta')


def stamp(hour, minute=0, day=DAY):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ).isoformat()


def interval(start, end):
    return {'startTime': start, 'endTime': end, 'startUtcOffset': '19800s', 'endUtcOffset': '19800s'}


def sleep(start=None, end=None, nap=False):
    return {'name': 'main' if not nap else 'nap', 'sleep': {
        'interval': interval(start or stamp(23, day=DAY-timedelta(days=1)), end or stamp(6)),
        'metadata': {'mainSleep': not nap, 'nap': nap, 'processed': True}}}


def hr(hour, value, minute=0):
    return {'heartRate': {'sampleTime': {'physicalTime': stamp(hour, minute)}, 'beatsPerMinute': value}}


def test_raw_mean_excludes_all_exercises_sleep_and_cutoff():
    readings = [hr(5, 50), hr(6, 70), hr(7, 180), hr(8, 80), hr(13, 55),
                hr(17, 160), hr(18, 90), hr(21, 100), hr(22, 200)]
    sleeps = [sleep(), sleep(stamp(12), stamp(14), True)]
    activities = [{'exercise': {'interval': interval(stamp(a), stamp(b))}} for a, b in [(7, 8), (17, 18)]]
    result = calculate_awake_hr(DAY, TZ, readings, sleeps, activities)
    assert result['value'] == 85
    assert result['sample_count'] == 4
    assert result['excluded_sleep_samples'] == 1
    assert result['excluded_activity_samples'] == 2
    assert result['wake_time'] == datetime.fromisoformat(stamp(6)).astimezone(ZoneInfo('UTC')).isoformat()


def test_duplicates_conflicts_invalid_values_and_empty_data():
    result = calculate_awake_hr(DAY, TZ, [hr(6, 70), hr(6, 70), hr(8, 90), hr(8, 100),
        hr(9, True), hr(10, float('nan')), hr(11, 0)], [sleep()], [])
    assert result['sample_count'] == 1 and result['value'] == 70
    assert calculate_awake_hr(DAY, TZ, [], [sleep()], [])['status'] == 'no_readings'
    assert calculate_awake_hr(DAY, TZ, [hr(8, 90)], [], [])['status'] == 'no_main_sleep'


def test_post_wake_tail_is_awake_and_main_sleep_beats_nap():
    main = sleep(end=stamp(6, 15))
    main['sleep']['summary'] = {'minutesAfterWakeUp': 15}
    result = calculate_awake_hr(DAY, TZ, [hr(6, 80), hr(6, 60, 10), hr(14, 100)],
        [main, sleep(stamp(12), stamp(14), True)], [])
    assert result['sample_count'] == 3
    assert result['value'] == 80


def client_fixture(tmp_path):
    client = SimpleNamespace(store=HealthReadStore(tmp_path / 'test.sqlite3'), account_key='one', strain_timezone=TZ, headers={},
                             _fetch_points=AsyncMock(), _invalidate_calculations=Mock())
    def fetch(kind, expression, **kwargs):
        return {'heart-rate': [hr(6, 80), hr(8, 100)], 'sleep': [sleep()], 'exercise': []}[kind]
    client._fetch_points.side_effect = fetch
    return client


def test_persistence_previous_date_force_and_frozen_snapshot_invalidation(tmp_path):
    async def run():
        client = client_fixture(tmp_path)
        client.store.snapshot_write('one', 'frozen-sleep', {'score': 50}, 0)
        now = datetime.fromisoformat(stamp(22))
        result = await collect_awake_hr(client, DAY, now=now)
        assert result['value'] == 90
        assert await previous_awake_hr(client, DAY) is None
        assert (await previous_awake_hr(client, DAY + timedelta(days=1)))['value'] == 90
        assert client.store.snapshot_read('one', 'frozen-sleep', now=0) is None
        assert read_baseline(client.store, 'other', DAY, TZ) is None
        await collect_awake_hr(client, DAY, now=now)
        assert client._fetch_points.await_count == 3
        await collect_awake_hr(client, DAY, now=now, force=True)
        assert client._fetch_points.await_count == 6
        assert SleepCalculator.compute_hr_dip_score(72, result['value']) == pytest.approx(80)
    asyncio.run(run())


def test_before_22_and_failed_provider_never_finalize(tmp_path):
    async def run():
        client = client_fixture(tmp_path)
        with pytest.raises(ValueError, match='22:00'):
            await collect_awake_hr(client, DAY, now=datetime.fromisoformat(stamp(21, 59)))
        assert client._fetch_points.await_count == 0
        client._fetch_points.side_effect = RuntimeError('provider failure')
        with pytest.raises(RuntimeError):
            await collect_awake_hr(client, DAY, now=datetime.fromisoformat(stamp(22)))
        assert read_baseline(client.store, 'one', DAY, TZ) is None
    asyncio.run(run())


def test_fresh_provider_filters_and_stored_only_bypass(tmp_path):
    async def run():
        client = client_fixture(tmp_path)
        client.stored_only = True
        await collect_awake_hr(client, DAY, now=datetime.fromisoformat(stamp(22)))
        calls = client._fetch_points.await_args_list
        assert 'heart_rate.sample_time.civil_time' in calls[0].args[1]
        assert '2026-10-14T22:00:00' in calls[0].args[1]
        assert calls[1].kwargs['reconcile'] is False
        assert '2026-10-13' in calls[2].args[1]
    asyncio.run(run())


@pytest.mark.parametrize('hour,expected_days', [(21, [DAY]), (22, [DAY, DAY + timedelta(days=1)])])
def test_scheduler_local_22_boundary_and_startup_catchup(tmp_path, hour, expected_days):
    from awake_hr_scheduler import run_due
    client = client_fixture(tmp_path)
    settings = {'GOOGLE_HEALTH_SESSION_COOKIE': 'soma_session=signed; Path=/',
                'AWAKE_HR_TIMEZONE': 'Asia/Calcutta'}
    with patch('awake_hr_scheduler.dotenv_values', return_value=settings), patch.dict('os.environ', {}, clear=True), \
         patch('auth._unsign', return_value={'health_user_id': 'account'}), \
         patch('auth.get_valid_access_token', AsyncMock(return_value='test-token')), \
         patch('google_health_client.GoogleHealthClient', return_value=client), \
         patch('awake_hr_scheduler.collect_awake_hr', AsyncMock()) as collect:
        asyncio.run(run_due(datetime.fromisoformat(stamp(hour, day=DAY+timedelta(days=1)))))
    assert [call.args[1] for call in collect.await_args_list] == expected_days


def test_recalculation_endpoint_uses_yesterday_and_returns_new_score(tmp_path):
    import main
    from fastapi.testclient import TestClient
    client = client_fixture(tmp_path)
    expected = SimpleNamespace(model_dump=lambda: {'score': 88, 'waking_hr': 90})
    inputs = SimpleNamespace(for_tonight=lambda day: None)
    with patch('main._get_token', AsyncMock(return_value='test')), patch('main._google_client', return_value=client), \
         patch('awake_heart_rate.collect_awake_hr', AsyncMock(return_value={'value': 90})) as collect, \
         patch('main._load_sleep_need_inputs', AsyncMock(return_value=inputs)), \
         patch('main._compute_real_sleep', AsyncMock(return_value=expected)):
        response = TestClient(main.app).post('/api/sleep/awake-heart-rate/recalculate?sleep_date=2026-10-15')
    assert response.status_code == 200
    assert response.json()['sleep']['score'] == 88
    assert collect.await_args.args[1] == DAY
    assert collect.await_args.kwargs['force'] is True
