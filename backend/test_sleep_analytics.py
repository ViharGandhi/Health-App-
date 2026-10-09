"""Sleep-card joins, missing data, local clocks, and unchanged score calculations."""

from copy import deepcopy
from datetime import date, timedelta
import unittest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace

from fastapi.testclient import TestClient
from main import app
from mock_sleep_stage_ranges import mock_stage_points
from sleep_analytics import sleep_observations, build_sleep_analytics
from sleep_need_inputs import SleepNeedInputs


DAY = date(2026, 10, 4)


class SleepAnalyticsTests(unittest.TestCase):
    def test_demo_joins_to_stages_and_consistency(self):
        client = TestClient(app)
        headers = {"X-User-Date": DAY.isoformat()}
        with patch("main._get_token", AsyncMock(return_value=None)), patch("main.get_session", return_value=None):
            analytics = client.get('/api/sleep/analytics', headers=headers).json()
            stages = client.get('/api/sleep/stages/typical-ranges', headers=headers).json()['nights'][-1]
            consistency = client.get('/api/sleep/consistency/score', headers=headers).json()
            efficiency = client.get('/api/sleep/efficiency', headers=headers).json()
        night = analytics['days'][-1]
        self.assertEqual(night['sleep_id'], stages['sleep_id'])
        self.assertEqual(night['period_minutes'], stages['total_minutes'])
        self.assertAlmostEqual(night['consistency'], consistency['latest_score'], places=1)
        self.assertAlmostEqual(night['efficiency'], efficiency['days'][-1]['value'], places=1)
        self.assertGreater(night['need_components']['debt'], 0)
        self.assertAlmostEqual(sum(night['need_components'].values()), night['need_minutes'])

    def test_unavailable_stages_are_not_zero_readings(self):
        point = mock_stage_points(DAY, 1)[0]
        point['sleep']['metadata']['processed'] = False
        night = sleep_observations([point], DAY, is_mock=True)[0]
        self.assertEqual(night['status'], 'stages_pending')
        for key in ['asleep_minutes', 'efficiency', 'performance', 'deep_minutes', 'wake_events']:
            self.assertIsNone(night[key])
        self.assertGreater(night['period_minutes'], 0)

    def test_naps_and_incomplete_future_sleeps_are_excluded(self):
        point = mock_stage_points(DAY, 1)[0]
        point['sleep']['metadata']['nap'] = True
        self.assertEqual(sleep_observations([point], DAY, is_mock=True), [])
        point['sleep']['metadata']['nap'] = False
        point['sleep']['interval']['endTime'] = '2026-10-05T05:00:00Z'
        self.assertEqual(sleep_observations([point], DAY, is_mock=True), [])

    def test_short_awakenings_overlap_without_double_counting(self):
        point = mock_stage_points(DAY, 1)[0]
        awake = next(s for s in point['sleep']['stages'] if s['type'] == 'AWAKE')
        point['sleep']['shortAwakenings'] = [awake, deepcopy(awake)]
        night = sleep_observations([point], DAY, is_mock=True)[0]
        self.assertEqual(night['wake_events'], 4)
        self.assertAlmostEqual(night['asleep_minutes'] + night['awake_minutes'], night['period_minutes'])

    def test_historical_offsets_and_physical_duration(self):
        point = mock_stage_points(DAY, 1)[0]
        point['sleep']['interval'].update(startTime='2026-10-03T21:00:00Z', endTime='2026-10-04T05:00:00Z',
                                         startUtcOffset='7200s', endUtcOffset='3600s')
        night = sleep_observations([point], DAY, is_mock=True)[0]
        self.assertEqual(night['period_minutes'], 480)
        self.assertEqual(night['bed_time'], '2026-10-03T23:00:00+02:00')
        self.assertEqual(night['wake_time'], '2026-10-04T06:00:00+01:00')
        self.assertEqual(night['date'], DAY.isoformat())

    def test_summary_latency_changes_onset_not_period(self):
        point = mock_stage_points(DAY, 1)[0]
        point['sleep']['summary'] = {'minutesToFallAsleep': '20', 'minutesAfterWakeUp': '10'}
        night = sleep_observations([point], DAY, is_mock=True)[0]
        from datetime import datetime
        self.assertEqual((datetime.fromisoformat(night['onset_time']) - datetime.fromisoformat(night['bed_time'])).total_seconds(), 1200)
        self.assertEqual((datetime.fromisoformat(night['wake_time']) - datetime.fromisoformat(night['sleep_wake_time'])).total_seconds(), 600)

    def test_connected_history_does_not_invent_need_or_performance(self):
        nights = sleep_observations(mock_stage_points(DAY, 60), DAY)
        result = build_sleep_analytics(nights, DAY, 'M', False)
        self.assertIsNone(result['averages']['performance'])
        self.assertIsNone(result['averages']['need_minutes'])
        self.assertIsNotNone(result['averages']['period_minutes'])

    def test_ranges_gaps_averages_and_varied_stable_demo(self):
        points = mock_stage_points(DAY, 400)
        nights = sleep_observations(points, DAY, is_mock=True)
        self.assertEqual(nights, sleep_observations(points, DAY, is_mock=True))
        for timeframe, count in [('W', 7), ('M', 30), ('6M', 183)]:
            result = build_sleep_analytics(deepcopy(nights), DAY, timeframe, True)
            self.assertEqual(len(result['days']), count)
            values = [n['period_minutes'] for n in result['days'] if n.get('period_minutes') is not None]
            self.assertAlmostEqual(result['averages']['period_minutes'], sum(values) / len(values))
        self.assertGreater(len({n['asleep_minutes'] for n in nights}), 100)
        self.assertTrue(any(n['status'] == 'no_sleep' for n in result['days']))

    def test_expired_connection_never_returns_demo(self):
        with patch('main._get_token', AsyncMock(return_value=None)), patch('main.get_session', return_value={'connected': True}):
            response = TestClient(app).get('/api/sleep/analytics')
        self.assertEqual(response.status_code, 401)

    def test_current_connected_estimate_requires_matching_sleep(self):
        day = date(2020, 10, 4)
        points = mock_stage_points(day, 2)
        night = sleep_observations(points, day)[-1]
        from datetime import datetime
        current = SimpleNamespace(score=81, sleep_need_hours=7.8,
                                  components_available={}, defaulted_components={},
                                  component_coverage=1., partial=False,
                                  sleep_start=datetime.fromisoformat(night['bed_time']).strftime('%I:%M %p'),
                                  sleep_end=datetime.fromisoformat(night['wake_time']).strftime('%I:%M %p'),
                                  stages=SimpleNamespace(total_minutes=night['asleep_minutes']))
        inputs = SleepNeedInputs({day - timedelta(days=1): 350},
                                 {day - timedelta(days=1): 0, day - timedelta(days=2): 0}, {})
        with patch('main._get_token', AsyncMock(return_value='connected')), \
             patch('main.GoogleHealthClient.get_sleep_stage_points', AsyncMock(return_value=points)), \
             patch('main._load_sleep_need_inputs', AsyncMock(return_value=inputs)), \
             patch('main._compute_real_sleep', AsyncMock(return_value=current)):
            client = TestClient(app)
            result = client.get('/api/sleep/analytics', headers={'X-User-Date': day.isoformat()}).json()
            self.assertEqual(result['days'][-1]['performance'], 81)
            self.assertEqual(result['days'][-1]['need_minutes'], 484)
            self.assertIsNone(result['days'][-2].get('performance'))
            current.sleep_end = '11:59 PM'
            mismatch = client.get('/api/sleep/analytics', headers={'X-User-Date': day.isoformat()}).json()
            self.assertIsNone(mismatch['days'][-1]['performance'])


if __name__ == '__main__':
    unittest.main()
