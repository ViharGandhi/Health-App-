import asyncio
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app, _compute_real_strain
from google_health_client import GoogleHealthClient, WEARABLES
from strain_service import _daily_cache
from strain_analytics import strain_day, strain_range_start


class StrainAnalyticsTests(unittest.TestCase):
    day = date(2026, 10, 6)

    def setUp(self):
        _daily_cache.clear()

    def session(self, start=10, end=20, kind="WEIGHTLIFTING", active=8):
        base = datetime(2026, 10, 6, 10, tzinfo=timezone.utc)
        return {"start": base + timedelta(minutes=start), "end": base + timedelta(minutes=end),
                "activity_name": "Weights", "exercise_type": kind, "active_minutes": active}

    def snapshot(self, samples, sessions, age=22):
        return asyncio.run(_compute_real_strain(None, self.day, age, samples=samples, sessions=sessions))

    def test_zone_one_is_counted_only_in_logged_activity_and_overlaps_once(self):
        base = datetime(2026, 10, 6, 10, tzinfo=timezone.utc)
        samples = [(base + timedelta(minutes=i), 110) for i in range(31)]
        sessions = [self.session(), self.session(start=15, end=18)]
        result = strain_day(self.day, samples, sessions, self.snapshot(samples, sessions), None)
        self.assertEqual(result["zones"]["zone1"], 10)
        self.assertEqual(sum(result["zones"].values()), 10)
        self.assertGreater(result["score"], 0)  # HRR/TRIMP can count load in display Zone 1.

    def test_ten_minute_heart_rate_gap_is_not_counted(self):
        base = datetime(2026, 10, 6, 10, 10, tzinfo=timezone.utc)
        samples = [(base, 180), (base + timedelta(minutes=10), 180)]
        sessions = [self.session()]
        result = strain_day(self.day, samples, sessions, self.snapshot(samples, sessions), 0)
        self.assertIsNone(result["zones"])
        self.assertEqual(result["steps"], 0)

    def test_missing_heart_rate_is_not_a_zero_score_or_measured_zone_total(self):
        session = self.session()
        result = strain_day(self.day, [], [session], self.snapshot([], [session]), None)
        self.assertIsNone(result["score"])
        self.assertIsNone(result["zones"])
        self.assertIsNone(result["steps"])
        empty = strain_day(self.day, [], [], self.snapshot([], []), None)
        self.assertEqual(sum(empty["zones"].values()), 0)

    def test_unset_age_does_not_claim_personal_zones(self):
        samples = [(datetime(2026, 10, 6, 10, i, tzinfo=timezone.utc), 150) for i in (10, 11)]
        snapshot = self.snapshot(samples, [self.session()], age=None)
        result = strain_day(self.day, samples, [self.session()], snapshot, None)
        self.assertIsNone(result["score"])
        self.assertIsNone(result["zones"])

    def test_heart_rate_outside_a_logged_activity_is_not_a_measured_zero(self):
        samples = [(datetime(2026, 10, 6, 9, i, tzinfo=timezone.utc), 150) for i in (10, 11)]
        sessions = [self.session()]
        result = strain_day(self.day, samples, sessions, self.snapshot(samples, sessions), None)
        self.assertIsNone(result["zones"])

    def test_strength_uses_active_duration_and_explicit_activity_types(self):
        sessions = [self.session(active=8), self.session(kind="WALKING", active=30), self.session(active=None)]
        result = strain_day(self.day, [], sessions, self.snapshot([], sessions), None)
        self.assertEqual(result["strength_minutes"], 18)
        self.assertEqual(result["strength_activities"], {"Weights": 18})
        self.assertEqual(len(result["activities"]), 3)

    def test_month_duration_uses_four_weeks_but_steps_use_thirty_days(self):
        self.assertEqual(strain_range_start(self.day, "M", "strength"), date(2026, 9, 9))
        self.assertEqual(strain_range_start(self.day, "M", "steps"), date(2026, 9, 7))

    def test_endpoint_reuses_samples_and_keeps_missing_days_and_client_date(self):
        samples = [(datetime(2026, 10, 6, 10, i, tzinfo=timezone.utc), 140) for i in (10, 11)]
        client = SimpleNamespace(get_intraday_heart_rate=AsyncMock(return_value=samples),
                                 get_workout_sessions=AsyncMock(return_value=[self.session()]),
                                 get_daily_steps=AsyncMock(return_value={self.day: 0}),
                                 get_sleep_stage_points=AsyncMock(return_value=[]), get_health_history=AsyncMock(return_value={}), account_key="fixture")
        with patch("main._get_token", AsyncMock(return_value="test-token")), patch("main.GoogleHealthClient", return_value=client), patch("main._compute_connected_recovery", AsyncMock(return_value=SimpleNamespace(score=None))):
            response = TestClient(app).get("/api/strain/analytics", headers={"X-User-Date": str(self.day), "X-User-Age": "22"})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result["is_mock"])
        self.assertEqual(result["today"], str(self.day))
        self.assertEqual(len(result["days"]), 7)
        self.assertEqual(len(result["previous_days"]), 7)
        self.assertIsNone(result["days"][0]["score"])
        self.assertIsNone(result["days"][0]["steps"])
        self.assertEqual(result["days"][-1]["steps"], 0)
        self.assertEqual(result["days"][-1]["score"], self.snapshot(samples, [self.session()]).model_dump(mode='json')['score_21'])
        client.get_intraday_heart_rate.assert_awaited_once_with(date(2026, 9, 4), date(2026, 10, 7), preserve_offset=True)
        client.get_workout_sessions.assert_awaited_once()
        client.get_daily_steps.assert_awaited_once()

    @pytest.mark.timeout(120)
    def test_demo_ranges_are_aligned_and_future_requests_rejected(self):
        with patch("main._get_token", AsyncMock(return_value=None)):
            for timeframe in ("W", "M", "6M"):
                for metric in ("strain", "zones_1_3", "zones_4_5", "strength", "steps"):
                    result = TestClient(app).get(f"/api/strain/analytics?timeframe={timeframe}&metric={metric}",
                                                 headers={"X-User-Date": str(self.day)}).json()
                    self.assertTrue(result["is_mock"])
                    self.assertEqual(result["days"][0]["date"], result["range_start"])
                    self.assertEqual(result["days"][-1]["date"], str(self.day))
                    self.assertEqual(result["previous_days"][-1]["date"], result["previous_range_end"])
                    self.assertLess(result["previous_range_end"], result["range_start"])
            response = TestClient(app).get("/api/strain/analytics?end_date=2026-10-07", headers={"X-User-Date": str(self.day)})
        self.assertEqual(response.status_code, 400)

    def test_steps_rollup_posts_pages_and_splits_at_ninety_days(self):
        requests = []
        def respond(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(200, json={"rollupDataPoints": [
                    {"civilStartTime": {"date": {"year": 2026, "month": 7, "day": 1}}, "steps": {"countSum": "0"}},
                    {"civilStartTime": {"date": {"year": 2026, "month": 7, "day": 2}}},
                ], "nextPageToken": "next"})
            return httpx.Response(200, json={"rollupDataPoints": []})
        client = GoogleHealthClient("test-token")
        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch("google_health_client.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(client.get_daily_steps(date(2026, 7, 1), date(2026, 10, 6)))
        self.assertEqual(result, {date(2026, 7, 1): 0})
        self.assertEqual(len(requests), 3)
        body = json.loads(requests[0].content)
        self.assertEqual(requests[0].method, "POST")
        self.assertTrue(requests[0].url.path.endswith("/steps/dataPoints:dailyRollUp"))
        self.assertEqual(body["dataSourceFamily"], WEARABLES)
        self.assertEqual(body["windowSizeDays"], 1)
        self.assertEqual(body["range"]["end"], {"date": {"year": 2026, "month": 9, "day": 29}})
        self.assertEqual(json.loads(requests[1].content)["pageToken"], "next")
        self.assertNotIn("pageToken", json.loads(requests[2].content))

    def test_exercise_duration_uses_active_time_or_physical_time_across_dst(self):
        client = GoogleHealthClient("test-token")
        interval = {"startTime": "2026-10-25T00:30:00Z", "endTime": "2026-10-25T01:30:00Z",
                    "startUtcOffset": "7200s", "endUtcOffset": "3600s"}
        client._points = AsyncMock(return_value=[{"exercise": {"interval": interval, "exerciseType": "WEIGHTLIFTING", "activeDuration": "1800s"}},
                                                {"exercise": {"interval": interval, "exerciseType": "WALKING"}}])
        sessions = asyncio.run(client.get_workout_sessions(self.day))
        self.assertEqual(sessions[0]["active_minutes"], 30)
        self.assertEqual(sessions[1]["active_minutes"], 60)
        self.assertEqual(sessions[0]["exercise_type"], "WEIGHTLIFTING")


if __name__ == "__main__":
    unittest.main()
