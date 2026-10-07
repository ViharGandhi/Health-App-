"""Causal date joins, Google-shaped inputs, and unchanged sleep-card contracts."""

import asyncio
from copy import deepcopy
from dataclasses import asdict
from datetime import date, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from google_health_client import GoogleHealthClient
from main import app, _load_sleep_need_inputs, _compute_real_sleep
from sleep_need_inputs import SleepNeedInputs
from sleep_need import calculate_sleep_need


DAY = date(2020, 10, 4)


def sleep_point(day=DAY, minutes='350', nap=False, name='main'):
    return {'name': name, 'sleep': {'interval': {
        'startTime': f'{day - timedelta(days=1)}T22:00:00Z', 'endTime': f'{day}T06:00:00Z',
        'startUtcOffset': '7200s', 'endUtcOffset': '7200s'},
        'metadata': {'mainSleep': not nap, 'nap': nap, 'processed': True},
        'summary': {'minutesAsleep': minutes, 'minutesInSleepPeriod': '480'}}}


class SleepNeedIntegrationTests(unittest.TestCase):
    def test_pre_sleep_estimate_excludes_the_sleep_being_compared(self):
        inputs = SleepNeedInputs({DAY: 0, DAY - timedelta(days=1): 350},
                                 {DAY: 100, DAY - timedelta(days=1): 0, DAY - timedelta(days=2): 0}, {})
        last = inputs.for_tonight(DAY - timedelta(days=1))
        self.assertEqual(last.total_need_min, 484)
        self.assertGreater(inputs.for_tonight(DAY).total_need_min, last.total_need_min)

    def test_each_sleep_uses_the_preceding_activity_date(self):
        inputs = SleepNeedInputs({DAY: 476}, {DAY: 0, DAY - timedelta(days=1): 100}, {})
        self.assertEqual(inputs.for_tonight(DAY).sleep_debt_min, 0)

    def test_missing_slots_keep_age_weights_and_naps_use_activity_day(self):
        inputs = SleepNeedInputs({DAY: 350, DAY - timedelta(days=2): 500},
                                 {DAY: 0, DAY - timedelta(days=1): 0, DAY - timedelta(days=3): 0}, {DAY: 30})
        result = inputs.for_tonight(DAY)
        self.assertAlmostEqual(result.sleep_debt_min, (100 - .7 * 50) / 1.7)
        self.assertAlmostEqual(result.total_need_min, 420 + result.sleep_debt_min * .34)
        self.assertIsNone(inputs.for_tonight(DAY + timedelta(days=1)))

    def test_google_missing_pending_zero_and_completed_summary(self):
        points = [sleep_point(DAY - timedelta(days=i)) for i in range(4)]
        points[0]['sleep']['summary'].pop('minutesAsleep')
        points[1]['sleep']['metadata']['processed'] = False
        points[2]['sleep']['summary']['minutesAsleep'] = '0'
        client = GoogleHealthClient('token')
        client._points = AsyncMock(return_value=points)
        result = asyncio.run(client.get_sleep_need_history(DAY - timedelta(days=3), DAY))
        self.assertEqual(len(result), 4)
        self.assertIsNone(result[DAY])
        self.assertIsNone(result[DAY - timedelta(days=1)])
        self.assertEqual(result[DAY - timedelta(days=2)], 0)
        self.assertEqual(result[DAY - timedelta(days=3)], 350)

    def test_google_future_or_impossible_summary_is_not_zero_sleep(self):
        points = [sleep_point(minutes='481'), sleep_point(date(2099, 1, 1))]
        client = GoogleHealthClient('token')
        client._points = AsyncMock(return_value=points)
        result = asyncio.run(client.get_sleep_need_history(DAY, date(2099, 1, 1)))
        self.assertTrue(all(value is None for value in result.values()))

    def test_naps_use_actual_asleep_minutes_and_are_deduplicated(self):
        nap = sleep_point(minutes='25.5', nap=True, name='nap')
        nap['sleep']['interval'].update(startTime=f'{DAY}T21:00:00Z', endTime=f'{DAY}T22:00:00Z')
        pending = deepcopy(nap)
        pending['name'] = 'pending'
        pending['sleep']['metadata']['processed'] = False
        missing = deepcopy(nap)
        missing['name'] = 'missing'
        missing['sleep']['summary'].pop('minutesAsleep')
        client = GoogleHealthClient('token')
        client._points = AsyncMock(return_value=[sleep_point(), nap, deepcopy(nap), pending, missing])
        result = asyncio.run(client.get_nap_minutes_history(DAY, DAY + timedelta(days=1)))
        self.assertEqual(result, {DAY + timedelta(days=1): 25.5})

    def test_loader_does_not_turn_missing_strain_into_zero(self):
        client = GoogleHealthClient('token')
        client.get_sleep_need_history = AsyncMock(return_value={DAY: 350})
        client.get_nap_minutes_history = AsyncMock(return_value={DAY: 20})
        from datetime import datetime, timezone
        base = datetime.combine(DAY, datetime.min.time(), tzinfo=timezone.utc)
        raw = ([(base, 60), (base + timedelta(minutes=1), 60)], [], [], {})
        with patch('main.fetch_strain_inputs', AsyncMock(return_value=raw)) as fetch:
            inputs = asyncio.run(_load_sleep_need_inputs(client, DAY, 30))
        fetch.assert_awaited_once_with(client, DAY - timedelta(days=8), DAY)
        self.assertEqual(inputs.for_tonight(DAY).total_need_min, 430)
        self.assertIsNone(inputs.for_tonight(DAY - timedelta(days=1)))
        client.get_sleep_need_history.assert_awaited_once_with(DAY - timedelta(days=7), DAY)

    def test_connected_endpoint_recomputes_when_inputs_change(self):
        sleep, strain, naps = {DAY: 350}, {DAY: 0, DAY - timedelta(days=1): 0}, {}
        inputs = SleepNeedInputs(sleep, strain, naps)
        with patch('main._get_token', AsyncMock(return_value='token')), \
             patch('main._load_sleep_need_inputs', AsyncMock(return_value=inputs)):
            client = TestClient(app)
            first = client.get('/api/sleep/need', headers={'X-User-Date': DAY.isoformat()}).json()
            self.assertEqual(first['total_need_min'], 484)
            naps[DAY] = 30
            second = client.get('/api/sleep/need', headers={'X-User-Date': DAY.isoformat()}).json()
            self.assertEqual(second['total_need_min'], 454)
            sleep[DAY] = 500
            strain[DAY] = 100
            third = client.get('/api/sleep/need', headers={'X-User-Date': DAY.isoformat()}).json()
            self.assertEqual(third['total_need_min'], 446)
            self.assertFalse(third['is_mock'])
            self.assertIsNotNone(third['last_night'])

    def test_missing_today_strain_and_expired_session(self):
        with patch('main._get_token', AsyncMock(return_value='token')), \
             patch('main._load_sleep_need_inputs', AsyncMock(return_value=SleepNeedInputs({}, {}, {}))):
            response = TestClient(app).get('/api/sleep/need').json()
            self.assertEqual(response['status'], 'missing_strain')
            self.assertIsNone(response['formatted_total_need'])
            self.assertNotIn('total_need_min', response)
        with patch('main._get_token', AsyncMock(return_value=None)), patch('main.get_session', return_value={'connected': True}):
            self.assertEqual(TestClient(app).get('/api/sleep/need').status_code, 401)

    def test_demo_joins_last_night_and_tonight_across_existing_endpoints(self):
        with patch('main._get_token', AsyncMock(return_value=None)), patch('main.get_session', return_value=None):
            client = TestClient(app)
            need = client.get('/api/sleep/need').json()
            detail = client.get('/api/sleep').json()
            analytics = client.get('/api/sleep/analytics').json()
        self.assertEqual(need['last_night'], detail['sleep_need'])
        self.assertEqual(detail['sleep_need_hours'] * 60, analytics['days'][-1]['need_minutes'])
        self.assertEqual(detail['tonight_sleep_need'], analytics['tonight_sleep_need'])
        self.assertEqual(detail['tonight_sleep_need']['total_need_min'], need['total_need_min'])

    def test_real_sleep_without_a_record_does_not_invent_eight_hour_need(self):
        client = GoogleHealthClient('token')
        client.get_sleep_session = AsyncMock(return_value=None)
        result = asyncio.run(_compute_real_sleep(client, DAY, None))
        self.assertIsNone(result.sleep_need_hours)
        self.assertIsNone(result.score)
        estimate = calculate_sleep_need(100)
        result = asyncio.run(_compute_real_sleep(client, DAY, estimate))
        self.assertEqual(result.sleep_need, asdict(estimate))
        self.assertEqual(result.sleep_need_hours * 60, 476)

    def test_real_completed_sleep_uses_new_need_and_retains_observed_metrics(self):
        client = GoogleHealthClient('token')
        client._points = AsyncMock(return_value=[sleep_point()])
        raw = asyncio.run(client.get_sleep_session(DAY))
        client.get_sleep_session = AsyncMock(return_value=raw)
        client.get_sleep_history_nights = AsyncMock(return_value=[])
        client.get_deep_sleep_hrv = AsyncMock(return_value=None)
        result = asyncio.run(_compute_real_sleep(client, DAY, calculate_sleep_need(100)))
        self.assertEqual(result.sleep_need_hours * 60, 476)
        self.assertEqual(result.stages.total_minutes, 350)
        self.assertIsNotNone(result.score)
        missing = asyncio.run(_compute_real_sleep(client, DAY, None))
        self.assertIsNone(missing.score)
        self.assertIsNone(missing.duration_score)
        self.assertEqual(missing.stages, result.stages)
        self.assertEqual(missing.efficiency_pct, result.efficiency_pct)


if __name__ == '__main__':
    unittest.main()
