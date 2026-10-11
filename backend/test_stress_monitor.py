import asyncio
import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from stress_monitor import category, summarize, stress_monitor, _day, recording_timezone

UTC = timezone.utc
START = datetime(2026, 10, 10, tzinfo=UTC)
def test_shared_mapping_matches_independent_logistic_equation():
    import numpy as np
    import pandas as pd
    from stressmon.config import load_config
    from stressmon.pipeline import map_scores
    cfg = load_config()
    cfg['smoothing']['mode'] = 'live'
    frame = pd.DataFrame({'state': ['STILL', 'SLEEP', 'EXERCISE', 'OFFWRIST'],
                          'z_hr': [2., 2., 2., 2.], 'z_hrv': [np.nan, 0., np.nan, np.nan],
                          'z_night': [0., 0., 0., 0.], 'context_fraction': [0., 0., 0., 0.]})
    _, raw, _ = map_scores(frame, cfg)
    assert raw[0] == pytest.approx(1.5)
    assert raw[1] == pytest.approx(3 / (1 + math.exp(-.6 * (1.1 - 2))))
    assert np.isnan(raw[2:]).all()
    assert [category(v) for v in [0, .999, 1, 1.999, 2, 3]] == ['low', 'low', 'medium', 'medium', 'high', 'high']


def test_duration_weighting_and_missing_time():
    points = [{'start': START, 'end': START + timedelta(minutes=5), 'score': .5},
              {'start': START + timedelta(minutes=10), 'end': START + timedelta(minutes=20), 'score': 2.5}]
    result = summarize(START, START + timedelta(minutes=30), points)
    assert result['minutes'] == {'low': 5, 'medium': 0, 'high': 10}
    assert result['unscored_minutes'] == 15
    assert result['coverage'] == .5
    assert result['average'] == 1.83
    points.append({'start': START + timedelta(minutes=15), 'end': START + timedelta(minutes=25), 'score': 1})
    with pytest.raises(ValueError):
        summarize(START, START + timedelta(minutes=30), points)


@pytest.mark.parametrize('day,hours', [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25)])
def test_local_day_accounts_for_dst(day, hours):
    tz = ZoneInfo('Europe/Berlin')
    result = _day(day, tz, datetime(2026, 11, 1, tzinfo=UTC), [], [], [])
    assert result['unscored_minutes'] == hours * 60
    assert result['latest_score'] is None
    assert result['average'] is None


def test_stale_score_is_not_presented_as_current():
    point = {'start': START, 'end': START + timedelta(minutes=5), 'score': 1.5}
    result = _day(START.date(), UTC, START + timedelta(hours=1), [point], [], [])
    assert result['stale']
    assert result['latest_score'] is None
    assert result['latest_at'] == point['end']


def test_demo_has_computed_scores_context_gaps_and_accounted_time():
    result = asyncio.run(stress_monitor(None, START.date(), UTC, demo=True))
    assert result['is_mock'] and result['validated'] is False
    assert len(result['days']) == 7
    for day in result['days']:
        assert day['points'] and day['overlays']
        assert day['unscored_minutes'] >= 120
        assert sum(day['minutes'].values()) + day['unscored_minutes'] == day['elapsed_minutes']
        assert day['scored_minutes'] > 0
        assert all(p['score'] is None or 0 <= p['score'] <= 3 for p in day['points'])
    assert result['current']['latest_score'] is not None
    assert result['current']['sleep_hrv_enabled']
    assert result['current']['night_context_enabled']
    assert any(p['source'] == 'hr_plus_sleep_hrv' and p['score'] is not None for p in result['current']['points'])
    activities = [o for o in result['current']['overlays'] if o['kind'] == 'activity']
    assert [(o['name'], o['start'].hour) for o in activities] == [('Walking', 9), ('Running', 11)]
    from mock_sleep_stage_ranges import mock_stage_points
    sleep = next(o for o in result['current']['overlays'] if o['kind'] == 'sleep')
    expected_wake = datetime.fromisoformat(mock_stage_points(START.date(), 1)[0]['sleep']['interval']['endTime'])
    assert sleep['end'] == expected_wake


def test_live_sleep_hrv_never_fills_daytime_or_creates_zero_stress():
    class Client:
        async def get_intraday_heart_rate(self, *args, **kwargs):
            return []
        async def get_activity_level_points(self, *args):
            return []
        async def _points(self, kind, expr):
            assert kind == 'heart-rate-variability'
            return [{'heartRateVariability': {'sampleTime': {'physicalTime': '2026-10-10T03:00:00Z'}}}] * 2
        async def get_sleep_stage_points(self, start, end):
            return [{'sleep': {'interval': {'startTime': '2026-10-10T02:00:00Z', 'endTime': '2026-10-10T07:00:00Z'}}}]
        async def get_workout_sessions(self, *args, **kwargs):
            return [{'activity_name': 'Walking', 'start': START + timedelta(hours=10), 'end': START + timedelta(hours=11)}]
    result = asyncio.run(stress_monitor(Client(), START.date(), UTC, now=START + timedelta(hours=12)))
    current = result['current']
    assert not result['is_mock']
    assert current['hrv_samples'] == 1
    assert current['awake_hrv_samples'] == 0
    assert current['status'] == 'no_hr'
    assert current['latest_score'] is current['average'] is None
    assert current['points'] == []
    assert current['unscored_minutes'] == 720
    assert current['scored_minutes'] == 0
    assert len(current['overlays']) == 2


@pytest.mark.parametrize('reference_days', [1, 4])
def test_live_hr_model_and_unknown_hrv_coverage_gate(reference_days):
    import numpy as np
    import pandas as pd
    class Client:
        async def get_intraday_heart_rate(self, *args, **kwargs):
            stamps = pd.date_range(START - timedelta(days=reference_days - 1), START + timedelta(hours=12), freq='5s', inclusive='left')
            values = 65 + np.sin(np.arange(len(stamps)) / 30)
            values[stamps >= START + timedelta(hours=10)] += 15
            return list(zip(stamps, values))
        async def get_activity_level_points(self, *args):
            return [{'activityLevel': {'activityLevelType': 'SEDENTARY', 'interval': {
                'startTime': (START - timedelta(days=reference_days - 1)).isoformat(),
                'endTime': (START + timedelta(hours=12)).isoformat()}}}]
        async def get_sleep_stage_points(self, *args):
            return []
        async def get_workout_sessions(self, *args, **kwargs):
            return [{'activity_name': 'Running', 'start': START + timedelta(hours=10), 'end': START + timedelta(minutes=620)}]
        async def _points(self, *args):
            return [{'heartRateVariability': {'sampleTime': {'physicalTime': START.isoformat()},
                     'rootMeanSquareOfSuccessiveDifferencesMilliseconds': 55}}]
    result = asyncio.run(stress_monitor(Client(), START.date(), UTC, now=START + timedelta(hours=12)))
    current = result['current']
    assert current['baseline_days'] == reference_days
    assert current['low_confidence'] and current['baseline_leaks']
    assert current['hrv_quality_rejected'] == 1
    assert not current['sleep_hrv_enabled'] and not current['night_context_enabled']
    assert all(p['source'] in ('hr_only', 'unavailable') for p in current['points'])
    if reference_days == 1:
        assert current['status'] == 'baseline_building'
        assert current['average'] is None and current['scored_minutes'] == 0
    else:
        assert current['status'] == 'estimated'
        assert current['scored_minutes'] > 0 and current['latest_score'] is not None
        masked = [p for p in current['points'] if p['reason'] == 'exercise_recovery']
        assert len(masked) >= 8 and all(p['score'] is None for p in masked)
        assert sum(current['minutes'].values()) + current['unscored_minutes'] == current['elapsed_minutes']


def test_endpoint_demo_and_input_validation():
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as client:
        headers = {'X-User-Date': '2026-10-09', 'X-User-Timezone': 'Europe/Berlin'}
        response = client.get('/api/stress?demo=true&days=7', headers=headers)
        assert response.status_code == 200
        assert response.json()['current']['date'] == '2026-10-09'
        assert response.json()['is_mock']
        monthly = client.get('/api/stress?demo=true&days=28', headers=headers).json()
        assert len(monthly['days']) == 28
        assert monthly['current']['points'] == response.json()['current']['points']
        assert client.get('/api/stress?days=365').status_code == 422
        assert client.get('/api/stress?demo=true', headers={'X-User-Date': '2099-01-01'}).status_code == 400


def test_live_recording_offset_aligns_sleep_bands_day_boundary_and_hr_queries():
    class Client:
        async def get_sleep_stage_points(self, *args):
            return [{'sleep': {'interval': {
                'startTime': '2026-10-10T19:50:00Z', 'endTime': '2026-10-11T01:53:00Z',
                'startUtcOffset': '19800s', 'endUtcOffset': '19800s'},
                'metadata': {'mainSleep': True, 'processed': True}}},
                {'sleep': {'interval': {
                    'startTime': '2026-10-11T08:54:00Z', 'endTime': '2026-10-11T10:34:00Z',
                    'endUtcOffset': '7200s'}, 'metadata': {'nap': True, 'processed': True}}}]
        async def get_intraday_heart_rate(self, *args, **kwargs):
            return []
        async def get_activity_level_points(self, *args):
            return []
        async def get_workout_sessions(self, *args, **kwargs):
            return []
        async def _points(self, kind, expression):
            assert '2026-10-11T18:30:00+00:00' in expression
            return []
    result = asyncio.run(stress_monitor(Client(), date(2026, 10, 11), ZoneInfo('Europe/Berlin'),
                                       now=datetime(2026, 10, 12, tzinfo=UTC)))
    assert result['timezone'] == 'UTC+05:30'
    current = result['current']
    assert current['start'].astimezone(UTC) == datetime(2026, 10, 10, 18, 30, tzinfo=UTC)
    assert current['elapsed_minutes'] == 1440
    sleep, nap = current['overlays']
    assert (sleep['start'].hour, sleep['start'].minute, sleep['end'].hour, sleep['end'].minute) == (1, 20, 7, 23)
    assert (nap['start'].hour, nap['start'].minute, nap['end'].hour, nap['end'].minute) == (14, 24, 16, 4)


def test_recording_timezone_uses_latest_completed_sleep_and_browser_fallback():
    browser = ZoneInfo('Europe/Berlin')
    now = datetime(2026, 10, 11, 12, tzinfo=UTC)
    def point(end, offset, **metadata):
        return {'sleep': {'interval': {'endTime': end, 'endUtcOffset': offset}, 'metadata': metadata}}
    rows = [point('2026-10-10T01:00:00Z', '7200s', mainSleep=True),
            point('2026-10-11T01:53:00Z', '19800s', mainSleep=True),
            point('2026-10-11T10:00:00Z', '-14400s', processed=False),
            point('2026-10-11T11:00:00Z', '-14400s', nap=True),
            point('2026-10-12T01:00:00Z', '-14400s', mainSleep=True)]
    assert str(recording_timezone(rows, date(2026, 10, 11), now, browser)) == 'UTC+05:30'
    assert recording_timezone([], date(2026, 10, 11), now, browser) is browser
    assert recording_timezone([point('2026-10-11T01:00:00Z', 'invalid')], date(2026, 10, 11), now, browser) is browser
