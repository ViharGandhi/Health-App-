from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from activity_details import activity_id, build_activity, showcase_inputs
from main import app
from strain import calculate_strain
from strain_service import calculate_days


@pytest.fixture(scope='module')
def replay():
    day = date(2026, 10, 9)
    inputs, steps = showcase_inputs(day - timedelta(days=30), day, timezone(timedelta(hours=5, minutes=30)))
    now = datetime(2026, 10, 9, 22, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    values = calculate_days(day - timedelta(days=30), day, now, now.tzinfo, 22, 'm', False, inputs)
    return day, inputs, values


def test_demo_has_three_activities_and_conserves_counted_zone_minutes(replay):
    day, inputs, values = replay
    sessions = [s for s in inputs[1] if s['start'].date() == day]
    assert {s['exercise_type'] for s in sessions} == {'WALKING', 'RUNNING', 'WEIGHTLIFTING'}
    for session in sessions:
        result = build_activity(session, values[day], inputs[0], values, inputs[1], day, True)
        workout = next(w for w in values[day]['workouts'] if w['start'] == session['start'])
        assert result['strain'] == int(workout['strain'] * 10) / 10
        assert sum(z['minutes'] for z in result['zones']) == pytest.approx(result['duration_min'])
        assert result['coverage'] == pytest.approx(1)
        assert result['start'].endswith('+05:30')
        assert result['comparison_count'] == 30
        assert all(z['typical'] is not None for z in result['zones'])


def test_live_never_invents_steps_calories_route_or_typical_ranges(replay):
    day, inputs, values = replay
    session = next(s for s in inputs[1] if s['start'].date() == day)
    result = build_activity(session, values[day], inputs[0], values, inputs[1], day, False)
    assert result['steps'] is result['calories'] is result['muscular_split'] is None
    assert not result['route_sample']
    assert all(z['typical'] is None for z in result['zones'])


def test_gap_time_is_unknown_not_zone_zero():
    start = datetime(2026, 10, 9, 9, tzinfo=timezone.utc)
    session = {'start': start, 'end': start + timedelta(minutes=30), 'activity_name': 'Walking', 'exercise_type': 'WALKING'}
    samples = [(start, 110), (start + timedelta(minutes=1), 110), (start + timedelta(minutes=29), 110), (session['end'], 110)]
    window = {'start': start, 'end': session['end']}
    current = calculate_strain(samples, [session], window, 22)
    current['day_window'] = window
    result = build_activity(session, current, samples, {start.date(): current}, [session], start.date(), False)
    assert sum(z['minutes'] for z in result['zones']) == 2
    assert result['unrecorded_minutes'] == 28
    assert sum(z['percent'] for z in result['zones']) == pytest.approx(100 * 2 / 30)


def test_missing_hr_does_not_become_zero_strain():
    start = datetime(2026, 10, 9, 9, tzinfo=timezone.utc)
    session = {'start': start, 'end': start + timedelta(minutes=30), 'activity_name': 'Walk'}
    window = {'start': start, 'end': session['end']}
    current = calculate_strain([], [session], window, 22)
    current['day_window'] = window
    result = build_activity(session, current, [], {}, [session], start.date(), False)
    assert result['strain'] is None
    assert all(z['minutes'] is None for z in result['zones'])


def test_same_type_prior_only_comparisons(replay):
    day, inputs, values = replay
    session = next(s for s in inputs[1] if s['start'].date() == day and s['exercise_type'] == 'WALKING')
    result = build_activity(session, values[day], inputs[0], values, inputs[1], day, False)
    past = [w['strain'] for d, value in values.items() if d < day for w in value['workouts'] if w['exercise_type'] == 'WALKING']
    assert result['averages']['strain'] == pytest.approx(sum(past) / 30)


def test_explicit_demo_home_and_activity_do_not_read_account_token():
    with patch('main.get_session', return_value={'health_user_id': 'real-account'}), patch('main._get_token', AsyncMock(side_effect=AssertionError('Account accessed'))), TestClient(app) as client:
        headers = {'X-User-Date': '2026-10-09', 'X-User-Age': '22'}
        response = client.get('/api/home/metrics?demo=true', headers=headers)
        assert response.status_code == 200, response.text
        home = response.json()
        assert home['is_mock'] is True
        assert len(home['rows']) == 12
        assert len(home['activities']) == 3
        assert next(row for row in home['rows'] if row['key'] == 'strain')['value'] == home['strain']['strain']
        detail = client.get('/api/activity', params={'id': home['activities'][0]['id'], 'demo': 'true'}, headers=headers)
        assert detail.status_code == 200, detail.text
        assert detail.json()['strain'] == home['activities'][0]['strain']
        assert client.get('/api/activity?id=missing&demo=true', headers=headers).status_code == 404
        overview = client.get('/api/recovery/analytics?sample=true', headers=headers)
        assert overview.status_code == 200
        assert overview.json()['is_mock'] is True


def test_connected_home_does_not_reenter_its_own_page_cache(replay):
    import main
    day, inputs, values = replay
    store = SimpleNamespace(dynamic_status=lambda account: {})
    provider = SimpleNamespace(store=store, account_key='test', strain_timezone=timezone.utc, strain_sex='m', strain_sex_defaulted=False)
    sleep = {'days': [{'date': str(day)}], 'prior_30_averages': {'performance': None, 'consistency': None, 'asleep_minutes': None}}
    nested_paths = []
    async def cached(client, key, path, response, compute, **kwargs):
        nested_paths.append(path)
        return await compute()
    with patch('main.get_session', return_value={'health_user_id': 'test'}), \
         patch('main._get_token', AsyncMock(return_value='test')), \
         patch('main._google_client', return_value=provider), \
         patch('main._activity_inputs', AsyncMock(return_value=(day, provider, 22, False, values, inputs[1], {}, None))), \
         patch('main.cached_page_result', side_effect=cached), \
         patch.object(main.sleep_analytics_endpoint, '__wrapped__', AsyncMock(return_value=sleep)), \
         patch.object(main.health_endpoint, '__wrapped__', AsyncMock(return_value={'metrics': {}})), TestClient(app) as client:
        result = client.get('/api/home/metrics', headers={'X-User-Date': str(day), 'X-User-Age': '22'})
    assert result.status_code == 200, result.text
    assert nested_paths == ['/api/home/metrics']
    assert result.json()['is_mock'] is False
