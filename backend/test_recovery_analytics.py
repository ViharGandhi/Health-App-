import asyncio
import math
import unittest
from datetime import date, timedelta
from statistics import mean
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import app, _compute_connected_recovery, _compute_real_sleep, _demo_recovery_analytics, _recovery_sleep_need
from mock_data import get_mock_dashboard
from mock_recovery import MockRecoveryClient
from recovery_analytics import build_recovery_analytics, mock_recovery_history, typical_ranges
from recovery_score import recovery_from_history


DAY = date(2026, 10, 4)


class RecoveryAnalyticsTests(unittest.TestCase):
    def test_mock_dates_are_stable_across_ranges_and_vary(self):
        week = mock_recovery_history(DAY - timedelta(days=6), DAY)
        month = mock_recovery_history(DAY - timedelta(days=29), DAY)
        for metric in week:
            self.assertEqual(week[metric], [p for p in month[metric] if p['date'] >= (DAY - timedelta(days=6)).isoformat()])
        self.assertGreater(len({p['value'] for p in month['hrv']}), 20)
        self.assertLess(len(month['hrv']), 30)  # An intentional missing day.

    def test_daily_estimates_match_pure_calculator_with_reduced_confidence(self):
        data = asyncio.run(_demo_recovery_analytics(DAY, 'W', 'estimate'))
        history = mock_recovery_history(DAY - timedelta(days=100), DAY)
        for row in data['days'][:-1]:
            expected = recovery_from_history(history, date.fromisoformat(row['date']))
            self.assertEqual(row['recovery'], expected.percent)
            self.assertEqual(row['zone'], expected.zone)
            self.assertTrue(row['sleep_context_missing'])
            self.assertNotEqual(row['confidence'], 'high')
        self.assertEqual(data['days'][-1]['recovery'], data['current']['score'])
        self.assertFalse(data['days'][-1]['sleep_context_missing'])
        self.assertTrue(data['is_mock'])

    def test_missing_vitals_stay_gaps_and_zero_percent_is_included(self):
        history = mock_recovery_history(DAY - timedelta(days=100), DAY)
        history['hrv'] = [p for p in history['hrv'] if p['date'] != DAY.isoformat()]
        history['respiratory_rate'].append({'date': DAY.isoformat(), 'value': math.nan})
        data = build_recovery_analytics(history, [], DAY, 'W', {'score': 0}, is_mock=True)
        self.assertIsNone(data['days'][-1]['hrv'])
        self.assertIsNone(data['days'][-1]['respiratory_rate'])
        self.assertEqual(data['days'][-1]['recovery'], 0)
        self.assertAlmostEqual(data['averages']['recovery'], mean(d['recovery'] for d in data['days'] if d['recovery'] is not None))
        self.assertIsNone(data['averages']['sleep_performance'])

    def test_rhr_reference_and_averages_exclude_other_methods(self):
        history = mock_recovery_history(DAY - timedelta(days=100), DAY)
        changed = DAY - timedelta(days=1)
        for row in history['rhr']:
            if row['date'] == changed.isoformat():
                row.update(value=150, method='ONLY_WITH_AWAKE_DATA')
        data = build_recovery_analytics(history, [], DAY, 'W', {'score': None}, is_mock=True)
        self.assertIsNone(next(d for d in data['days'] if d['date'] == changed.isoformat())['rhr'])
        self.assertLess(data['averages']['rhr'], 70)
        self.assertLess(data['prior_30_day_averages']['rhr'], 70)

    def test_flat_optional_ranges_and_insufficient_references_unassessed(self):
        history = mock_recovery_history(DAY - timedelta(days=100), DAY)
        for point in history['skin_temperature']:
            point['value'] = 33
        history['spo2'] = history['spo2'][-20:]
        ranges = typical_ranges(history, DAY)
        self.assertIsNone(ranges['skin_temperature'])
        self.assertIsNone(ranges['spo2'])
        self.assertGreater(ranges['hrv']['high'], ranges['hrv']['low'])

    def test_six_month_buckets_partition_every_day_once_including_month_ends(self):
        data = asyncio.run(_demo_recovery_analytics(date(2026, 8, 31), '6M', 'estimate'))
        covered = []
        for bucket in data['monthly_buckets']:
            rows = [d for d in data['days'] if bucket['start_date'] <= d['date'] <= bucket['end_date']]
            covered.extend(d['date'] for d in rows)
            self.assertEqual(bucket['counts']['hrv'], sum(d['hrv'] is not None for d in rows))
        self.assertEqual(covered, [d['date'] for d in data['days']])
        self.assertEqual(len(data['monthly_buckets']), 6)

    def test_mock_endpoint_estimate_agrees_with_analytics_and_keeps_legacy(self):
        client = TestClient(app)
        with patch('main._get_token', new=AsyncMock(return_value=None)):
            analytics = client.get('/api/recovery/analytics?timeframe=M', headers={'X-User-Date': DAY.isoformat()})
            current = client.get('/api/recovery?demo=estimate', headers={'X-User-Date': DAY.isoformat()})
            legacy = client.get('/api/recovery/analytics?demo=legacy', headers={'X-User-Date': DAY.isoformat()})
        self.assertEqual(analytics.status_code, 200)
        self.assertEqual(analytics.json()['current'], current.json())
        self.assertEqual(len(analytics.json()['days']), 30)
        self.assertEqual(legacy.json()['current'], get_mock_dashboard(DAY).recovery.model_dump())
        self.assertTrue(all(d['recovery'] is None for d in legacy.json()['days'][:-1]))

    def test_period_navigation_date_validation_and_expired_session(self):
        client = TestClient(app)
        with patch('main._get_token', new=AsyncMock(return_value=None)):
            past = client.get('/api/recovery/analytics?end_date=2026-09-27', headers={'X-User-Date': DAY.isoformat()})
            future = client.get('/api/recovery/analytics?end_date=2026-10-05', headers={'X-User-Date': DAY.isoformat()})
        self.assertEqual(past.json()['range_end'], '2026-09-27')
        self.assertEqual(past.json()['previous_range_end'], '2026-09-20')
        self.assertEqual(future.status_code, 400)
        with patch('main._get_token', new=AsyncMock(return_value=None)), patch('main.get_session', return_value={'access_token': 'expired'}):
            self.assertEqual(client.get('/api/recovery/analytics').status_code, 401)

    def test_connected_analytics_preserves_current_calculation_and_historical_fallback(self):
        client = MockRecoveryClient(DAY)
        client.points['daily-oxygen-saturation'] = []
        expected = asyncio.run(_compute_connected_recovery(client, DAY, 30))
        client.calls.clear()
        with patch('main._get_token', new=AsyncMock(return_value='token')), patch('main.GoogleHealthClient', return_value=client):
            response = TestClient(app).get('/api/recovery/analytics', headers={'X-User-Date': DAY.isoformat(), 'X-User-Age': '30'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['is_mock'])
        self.assertEqual(data['current'], expected.model_dump())
        self.assertEqual(data['days'][-1]['recovery'], expected.score)
        self.assertIsNotNone(data['days'][-1]['sleep_performance'])
        self.assertEqual(len(client.calls), 12)
        need = asyncio.run(_recovery_sleep_need(client, DAY, 30))
        existing_sleep = asyncio.run(_compute_real_sleep(client, DAY, need, 30))
        self.assertEqual(data['days'][-1]['sleep_performance'], existing_sleep.score)
        self.assertTrue(all(d['sleep_performance'] is None for d in data['days'][:-1]))
        self.assertTrue(all(d['sleep_context_missing'] for d in data['days'][:-1]))


if __name__ == '__main__':
    unittest.main()
