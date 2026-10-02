import asyncio
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from google_health_client import GoogleHealthClient
from health_trends import build_health_response, METRICS
from main import app, _compute_real_recovery
from mock_data import get_mock_health


class HealthTests(unittest.TestCase):
    def test_demo_series_are_aligned_and_labeled(self):
        result = get_mock_health()
        self.assertTrue(result.is_mock)
        self.assertEqual(set(result.metrics), set(METRICS))
        self.assertTrue(all(len(points) == 7 for points in result.metrics.values()))
        self.assertEqual(result.metrics["hrv"][-1].value, 44.8)
        self.assertTrue(result.metrics["vo2_max"][-1].estimated)
        self.assertGreater(len(result.heart_rate), 0)
        year = get_mock_health("1Y")
        self.assertGreaterEqual(len(year.metrics["hrv"]), 365)
        self.assertTrue(any(point.value is None for point in year.metrics["hrv"]))

    def test_google_daily_vital_fields_and_missing_values(self):
        client = GoogleHealthClient("token")
        calls = []

        async def points(data_type, filter_expr):
            calls.append((data_type, filter_expr))
            if data_type == "daily-oxygen-saturation":
                return [{"dailyOxygenSaturation": {
                    "date": {"year": 2026, "month": 10, "day": 1},
                    "averagePercentage": 97.2,
                }}]
            if data_type == "daily-sleep-temperature-derivations":
                return [{"dailySleepTemperatureDerivations": {
                    "date": {"year": 2026, "month": 10, "day": 1},
                    "nightlyTemperatureCelsius": 32.6,
                }}]
            return []

        client._points = points
        result = asyncio.run(client.get_health_history(date(2026, 9, 30), date(2026, 10, 1)))
        self.assertEqual(result["spo2"], [{"date": "2026-10-01", "value": 97.2, "estimated": None, "method": None}])
        self.assertEqual(result["skin_temperature"][0]["value"], 32.6)
        self.assertEqual(result["hrv"], [])
        self.assertEqual(len(calls), 6)
        self.assertIn('dailyOxygenSaturation.date >= "2026-09-30"', calls[2][1])

    def test_health_endpoint_aligns_missing_days_and_bins_heart_rate(self):
        today = date.today().isoformat()
        history = {key: [] for key in METRICS}
        history["hrv"] = [{"date": today, "value": 45.0, "estimated": None}]
        client = type("Client", (), {
            "get_health_history": AsyncMock(return_value=history),
            "get_intraday_heart_rate": AsyncMock(return_value=[
                (datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=8), 60.0),
                (datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=8, minutes=5), 80.0),
            ]),
        })()
        with patch("main._get_token", new=AsyncMock(return_value="token")), patch("main.GoogleHealthClient", return_value=client):
            response = TestClient(app).get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["is_mock"])
        self.assertEqual(data["metrics"]["hrv"][-1]["value"], 45.0)
        self.assertIsNone(data["metrics"]["rhr"][-1]["value"])
        self.assertEqual(data["heart_rate"], [{"time": "08:00", "value": 70.0}])
        self.assertEqual(len(data["metrics"]["hrv"]), 7)

    def test_baseline_uses_only_previous_days_and_leaves_gaps(self):
        start = date(2026, 9, 15)
        end = date(2026, 9, 16)
        history = {"hrv": [
            {"date": (start - timedelta(days=offset)).isoformat(), "value": 40.0}
            for offset in range(1, 8)
        ] + [{"date": start.isoformat(), "value": 80.0}]}
        result = build_health_response(history, [], start, end, "W", False)
        self.assertEqual(result.metrics["hrv"][0].baseline, 40.0)
        self.assertEqual(result.metrics["hrv"][0].value, 80.0)
        self.assertIsNone(result.metrics["hrv"][1].value)

    def test_optional_deep_sleep_hrv_is_distinct_from_daily_average(self):
        client = GoogleHealthClient("token")
        client._points = lambda *args: asyncio.sleep(0, result=[{
            "dailyHeartRateVariability": {
                "date": {"year": 2026, "month": 10, "day": 1},
                "averageHeartRateVariabilityMilliseconds": 44.0,
                "deepSleepRootMeanSquareOfSuccessiveDifferencesMilliseconds": 51.0,
            },
        }])
        self.assertEqual(asyncio.run(client.get_deep_sleep_hrv(date(2026, 10, 1))), 51.0)
        self.assertEqual(asyncio.run(client.get_daily_hrv(date(2026, 10, 1))), 44.0)

    def test_connected_recovery_hides_score_without_personal_history(self):
        client = type("Client", (), {
            "get_daily_hrv": AsyncMock(return_value=44.0),
            "get_resting_heart_rate": AsyncMock(return_value=55.0),
            "get_health_history": AsyncMock(return_value={"hrv": [], "rhr": []}),
        })()
        result = asyncio.run(_compute_real_recovery(client, date(2026, 10, 1), 80.0, 10.0))
        self.assertTrue(result.is_calibrating)
        self.assertIsNone(result.score)
        self.assertIsNone(result.hrv_component)
        self.assertEqual(result.status, "calibrating")

    def test_connected_recovery_uses_prior_device_medians(self):
        history = {
            "hrv": [{"value": value} for value in [38, 39, 40, 41, 42, 43, 44]],
            "rhr": [{"value": value} for value in [52, 53, 54, 55, 56, 57, 58]],
        }
        client = type("Client", (), {
            "get_daily_hrv": AsyncMock(return_value=46.0),
            "get_resting_heart_rate": AsyncMock(return_value=52.0),
            "get_health_history": AsyncMock(return_value=history),
        })()
        result = asyncio.run(_compute_real_recovery(client, date(2026, 10, 1), 80.0, 10.0))
        self.assertFalse(result.is_calibrating)
        self.assertIsNotNone(result.score)
        self.assertEqual(result.hrv_baseline, 41.0)
        self.assertEqual(result.rhr_baseline, 55.0)
        client.get_health_history.assert_awaited_once_with(date(2026, 9, 17), date(2026, 9, 30))


if __name__ == "__main__":
    unittest.main()
