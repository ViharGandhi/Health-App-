"""Independent deterministic tests for the specified HRR/TRIMP equations."""
from datetime import date, datetime, timedelta, timezone
import math
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app
from google_health_client import GoogleHealthClient
from strain import StrainConfig, calculate_strain, clean_samples, day_window, strain_analytics, strain_label, strain_score
from strain_service import calculate_days, demo_inputs, sleep_windows, _daily_cache


BASE = datetime(2026, 10, 5, 7, tzinfo=timezone.utc)
WINDOW = {'start': BASE, 'end': BASE + timedelta(hours=15), 'source': 'sleep'}


def samples(bpm=160, minutes=45):
    return [(BASE + timedelta(minutes=i), bpm) for i in range(minutes + 1)]


def calc(points=None, workouts=(), age=30, sex='m', window=WINDOW, **kwargs):
    return calculate_strain(samples() if points is None else points, list(workouts), window, age, [56] * 7, sex, **kwargs)


@pytest.mark.parametrize('points', [[], [(BASE, 160)]])
def test_empty_and_single_have_zero_load_and_coverage(points):
    result = calc(points)
    assert result['strain'] == result['load'] == result['coverage'] == 0
    assert result['low_coverage']


def test_cleaning_sorts_deduplicates_rejects_spikes_and_impossible_values():
    points = [(BASE + timedelta(minutes=i), hr) for i, hr in enumerate([100, 100, 100, 200, 100, 100, 100, 29, 231])]
    points += [points[1], (BASE - timedelta(minutes=1), 100)]
    cleaned = clean_samples(list(reversed(points)), WINDOW)
    assert len(cleaned) == 6
    assert all(hr == 100 for _, hr in cleaned)
    assert len(set(t for t, _ in cleaned)) == 6


def test_reference_edge_padding_and_short_arrays():
    points = [(BASE + timedelta(minutes=i), hr) for i, hr in enumerate([200, 100, 100, 100, 100])]
    assert clean_samples(points, WINDOW)[0][1] == 200
    assert len(clean_samples(points[:4], WINDOW)) == 4


def test_four_minute_gap_bridges_ten_minute_gap_does_not():
    result = calc([(BASE, 160), (BASE + timedelta(minutes=4), 160), (BASE + timedelta(minutes=14), 160)])
    assert result['counted_minutes'] == 4
    assert sum(result['zone_minutes'].values()) == 4


@pytest.mark.parametrize('sex,a,b', [('m', .64, 1.92), ('f', .86, 1.67)])
def test_hand_computed_hrr_trimp_and_curve(sex, a, b):
    # Age 30 => HRmax 187, HRrest 56. HR 121.5 => exactly 50% HRR.
    expected = 4 * .5 * a * math.exp(b * .5)
    result = calc([(BASE, 121.5), (BASE + timedelta(minutes=4), 121.5)], sex=sex)
    assert result['load'] == pytest.approx(expected, abs=1e-12)
    assert result['strain'] == pytest.approx(21 * (1 - math.exp(-expected / 90)), abs=1e-12)


def test_min_hrr_and_clip():
    assert calc(samples(56 + .199 * 131))['load'] == 0
    assert calc(samples(56 + .2 * 131))['load'] > 0
    assert calc(samples(230, 1))['load'] == pytest.approx(1.1 * .64 * math.exp(1.92 * 1.1))


def test_curve_and_label_boundaries():
    scores = [strain_score(x) for x in [0, 1, 50, 90, 200, 500, 100000]]
    assert scores == sorted(scores)
    assert scores[0] == 0 and all(0 <= x < 21 for x in scores)
    assert [strain_label(x) for x in [9.9, 10, 13.9, 14, 17.9, 18]] == ['Light', 'Moderate', 'Moderate', 'High', 'High', 'All Out']


def test_midpoint_overlap_and_low_load_drop():
    first = {'start': BASE, 'end': BASE + timedelta(minutes=2), 'activity_name': 'First'}
    overlap = {'start': BASE + timedelta(minutes=1), 'end': BASE + timedelta(minutes=3), 'activity_name': 'Second'}
    result = calc(samples(160, 3), [overlap, first])
    assert [w['name'] for w in result['workouts']] == ['First', 'Second']
    assert result['workouts'][0]['load'] == pytest.approx(2 * result['workouts'][1]['load'])
    assert result['load'] == pytest.approx(sum(w['load'] for w in result['workouts']))
    tiny = {'start': BASE, 'end': BASE + timedelta(seconds=5), 'activity_name': 'Tiny'}
    assert calc([(BASE, 160), (BASE + timedelta(seconds=5), 160)], [tiny])['workouts'] == []


@pytest.mark.parametrize('fraction,zone', [(.5, 1), (.6, 2), (.7, 3), (.8, 4), (.9, 5)])
def test_zone_boundaries_are_display_only(fraction, zone):
    workout = {'start': BASE, 'end': BASE + timedelta(minutes=4), 'activity_name': 'Test'}
    result = calc(samples(187 * fraction, 4), [workout])
    assert result['zone_minutes'][f'zone{zone}'] == 4
    assert result['activity_zone_minutes'][f'zone{zone}'] == 4


def test_sleep_window_ignores_nap_uses_past_sleep_and_fallback():
    main = {'start': BASE - timedelta(hours=8), 'end': BASE, 'main_sleep': True}
    nap = {'start': BASE + timedelta(hours=4), 'end': BASE + timedelta(hours=5), 'nap': True}
    next_sleep = {'start': BASE + timedelta(hours=15), 'end': BASE + timedelta(days=1), 'main_sleep': True}
    current = day_window(BASE.date(), BASE + timedelta(hours=14), [main, nap], timezone.utc)
    assert current['start'] == BASE
    past = day_window(BASE.date(), BASE + timedelta(days=1, hours=12), [main, nap, next_sleep], timezone.utc)
    assert past['start'] == BASE and past['end'] == next_sleep['start']
    assert day_window(BASE.date(), BASE + timedelta(hours=14), [], timezone.utc)['source'] == 'midnight_fallback'


def test_dst_coverage_uses_elapsed_seconds_and_distinct_fold_samples():
    tz = ZoneInfo('Europe/Berlin')
    start = datetime(2026, 10, 25, 2, 58, tzinfo=tz, fold=0)
    end = datetime(2026, 10, 25, 2, 2, tzinfo=tz, fold=1)
    window = {'start': start, 'end': end, 'source': 'midnight_fallback'}
    result = calc([(start, 160), (end, 160)], window=window)
    assert result['counted_minutes'] == 4 and result['coverage'] == 1


def test_coverage_defaulted_params_and_missing_age():
    result = calc(samples(160, 9), window={'start': BASE, 'end': BASE + timedelta(minutes=15)})
    assert result['coverage'] == .6 and not result['low_coverage']
    missing = calc(age=None)
    assert missing['age_missing'] and missing['strain'] is None and missing['load'] is None
    assert missing['zone_minutes'] is None and missing['params']['hr_max'] is None
    assert not missing['calibrating']  # Missing age is withheld, never defaulted.
    defaulted = calculate_strain([], [], WINDOW, 30)
    assert defaulted['params']['hr_rest_source'] == 'default' and defaulted['calibrating']


def test_unlogged_effort_gaps_and_overlap_do_not_add_load():
    result = calc(samples(140, 15))
    assert len(result['suggested_workouts']) == 1
    workout = {'start': BASE + timedelta(minutes=5), 'end': BASE + timedelta(minutes=10), 'activity_name': 'Logged'}
    logged = calc(samples(140, 15), [workout])
    assert logged['suggested_workouts'] == [] and logged['load'] == result['load']
    assert calc([(BASE, 140), (BASE + timedelta(minutes=11), 140)])['suggested_workouts'] == []


@pytest.mark.parametrize('recovery,expected', [(33, (4, 10)), (34, (10, 14)), (66, (10, 14)), (67, (14, 18))])
def test_history_and_target_boundaries(recovery, expected):
    history = [{'date': BASE.date() - timedelta(days=i), 'strain': 10, 'load': 50 if i >= 7 else 100, 'coverage': 1} for i in range(28)]
    result = strain_analytics(history, BASE.date(), 12, recovery)
    assert result['avg_strain_7d'] == result['avg_strain_28d'] == 10
    assert result['acute_chronic_ratio'] == pytest.approx(100 / 62.5)
    assert (result['strain_target']['low'], result['strain_target']['high']) == expected
    assert strain_analytics(history[:20], BASE.date(), 12, None)['acute_chronic_ratio'] is None
    assert strain_analytics(history, BASE.date(), 12, None)['strain_target'] is None


@pytest.mark.parametrize('hr,minutes,expected', [(135, 45, 9.6310026881), (160, 45, 14.4548919987), (172, 60, 18.3713504781)])
def test_constant_hr_sanity_scenarios(hr, minutes, expected):
    result = calc(samples(hr, minutes))
    hrr = (hr - 56) / 131
    load = minutes * hrr * .64 * math.exp(1.92 * hrr)
    assert result['load'] == pytest.approx(load)
    assert result['strain'] == pytest.approx(21 * (1 - math.exp(-load / 90)))
    assert abs(result['strain'] - expected) < .05


def test_config_overrides_and_validation():
    assert StrainConfig.from_env({'STRAIN_L': '120', 'STRAIN_MAX_GAP_S': '240'}).strain_l == 120
    with pytest.raises(ValueError):
        StrainConfig.from_env({'STRAIN_L': '0'})


def test_connected_api_contract_error_and_demo_use_same_renderer():
    client = GoogleHealthClient('test')
    client.get_intraday_heart_rate = AsyncMock(return_value=samples())
    client.get_workout_sessions = AsyncMock(return_value=[{'start': BASE, 'end': BASE + timedelta(minutes=45), 'activity_name': 'Run', 'exercise_type': 'RUNNING'}])
    client.get_sleep_stage_points = AsyncMock(return_value=[])
    client.get_health_history = AsyncMock(return_value={'rhr': [{'date': str(BASE.date()), 'value': 56}]})
    with patch('main._get_token', AsyncMock(return_value='test')), patch('main.GoogleHealthClient', return_value=client), patch('main._compute_connected_recovery', AsyncMock(return_value=type('Recovery', (), {'score': 67})())):
        response = TestClient(app).get('/api/strain?date=2026-10-05', headers={'X-User-Age': '30', 'X-User-Sex': 'm'})
        assert response.status_code == 200
        payload = response.json()
        assert payload['mode'] == 'connected' and payload['strain'] == math.floor(calc()['strain'] * 10) / 10
        assert payload['params']['hr_max'] == 187 and payload['max_hr'] == 160
        assert payload['analytics']['strain_target']['status'] == 'on'
        client.get_intraday_heart_rate.side_effect = httpx.RequestError('offline')
        error = TestClient(app).get('/api/strain?date=2026-10-05', headers={'X-User-Age': '30'})
        assert error.status_code == 502 and 'strain' not in error.json()
    demo = TestClient(app).get('/api/strain?demo=true').json()
    assert set(demo) == set(payload) and demo['mode'] == 'demo' and demo['coverage'] == 1


def test_past_cache_is_scoped_by_profile_and_user():
    _daily_cache.clear()
    day = BASE.date()
    inputs, _ = demo_inputs(day, day, timezone.utc)
    first = calculate_days(day, day, BASE + timedelta(days=1), timezone.utc, 30, 'm', False, inputs, account='a')
    second = calculate_days(day, day, BASE + timedelta(days=1), timezone.utc, 30, 'm', False, ([], [], [], {}), account='a')
    other = calculate_days(day, day, BASE + timedelta(days=1), timezone.utc, 30, 'm', False, ([], [], [], {}), account='b')
    assert first[day] is second[day] and other[day]['load'] == 0


def test_demo_history_does_not_change_when_the_selected_end_date_changes():
    day = BASE.date()
    first, _ = demo_inputs(day, day, timezone.utc)
    later, _ = demo_inputs(day, day + timedelta(days=7), timezone.utc)
    assert [p for p in first[0] if p[0].date() == day] == [p for p in later[0] if p[0].date() == day]


def test_connected_missing_age_and_invalid_profile_headers():
    client = GoogleHealthClient('profile-fixture')
    client.get_intraday_heart_rate = AsyncMock(return_value=samples())
    client.get_workout_sessions = AsyncMock(return_value=[])
    client.get_sleep_stage_points = AsyncMock(return_value=[])
    client.get_health_history = AsyncMock(return_value={})
    with patch('main._get_token', AsyncMock(return_value='test')), patch('main.GoogleHealthClient', return_value=client), patch('main._compute_connected_recovery', AsyncMock(return_value=type('Recovery', (), {'score': None})())):
        result = TestClient(app).get('/api/strain?date=2026-10-05').json()
        assert result['age_missing'] and result['strain'] is None and result['zone_minutes'] is None
        assert TestClient(app).get('/api/strain', headers={'X-User-Age': '17'}).status_code == 400
        assert TestClient(app).get('/api/strain', headers={'X-User-Sex': 'x'}).status_code == 400
        assert TestClient(app).get('/api/strain', headers={'X-User-Timezone': 'Invalid/Zone'}).status_code == 400
